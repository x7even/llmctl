#!/usr/bin/env python3
"""Standalone FP8 MoE Triton kernel tuner for AMD R9700 — no Ray required.

Replicates BenchmarkWorker.tune() from vllm/benchmarks/kernels/benchmark_moe.py
but runs sequentially on a single GPU, avoiding the 10+ minute Ray/ROCm
raylet RegisterClient hang on this platform.

Target: E=64,N=512,device_name=AMD_Radeon_R9700,dtype=fp8_w8a8,block_shape=[128,128].json
Usage inside vllm-openai-rocm container:
  ROCR_VISIBLE_DEVICES=0 python3 /bench/tune_moe_r9700.py \
    --save-dir /vllm-tuned-configs
"""

import argparse
import gc
import json
import os
import time
from contextlib import nullcontext
from itertools import product

import torch

# ─── vllm imports (require --device=/dev/kfd) ──────────────────────────────
from vllm.model_executor.layers.fused_moe import fused_topk, override_config
from vllm.model_executor.layers.fused_moe.config import (
    FusedMoEQuantConfig,
    _get_config_dtype_str,
)
from vllm.model_executor.layers.fused_moe.fused_moe import (
    disable_inplace,
    fused_experts,
    get_config_file_name,
)
from vllm.platforms import current_platform
from vllm.triton_utils import triton

# ─── Model dimensions for Qwen3.6-35B-A3B-FP8 with EP=True, TP=4 ──────────
# Full: E=256, intermediate=512, hidden=2048, topk=8
# After EP: E=256//4=64, shard_N=2*512=1024
E = 64
SHARD_INTERMEDIATE_SIZE = 1024  # 2 * moe_intermediate_size
HIDDEN_SIZE = 2048
TOPK = 8
DTYPE = torch.float16  # activation dtype for ROCm
USE_FP8_W8A8 = True
BLOCK_QUANT_SHAPE = [128, 128]

BATCH_SIZES = [1, 2, 4, 8, 16, 24, 32, 48, 64, 96, 128, 256, 512, 1024, 1536, 2048, 3072, 4096]

FP8_DTYPE = current_platform.fp8_dtype()


def get_rocm_tuning_space():
    block_mn_range = [16, 32, 64, 128, 256]
    block_k_range = [32, 64, 128, 256]  # 16 excluded for fp8
    num_warps_range = [1, 2, 4, 8]
    group_m_range = [1, 4, 8, 16, 32]
    num_stage_range = [2]
    waves_per_eu_range = [0, 1, 2, 4]

    keys = ["BLOCK_SIZE_M", "BLOCK_SIZE_N", "BLOCK_SIZE_K",
            "GROUP_SIZE_M", "num_warps", "num_stages", "waves_per_eu"]
    values = [block_mn_range, block_mn_range, block_k_range,
              group_m_range, num_warps_range, num_stage_range, waves_per_eu_range]
    configs = [dict(zip(keys, v)) for v in product(*values)]

    # FP8 block constraint: BLOCK_N and BLOCK_K must be multiples of 128
    block_n, block_k = BLOCK_QUANT_SHAPE
    configs = [c for c in configs
               if c["BLOCK_SIZE_K"] % block_k == 0
               and c["BLOCK_SIZE_N"] % block_n == 0]
    return configs


def prune_rocm_configs(M, N, K, configs):
    pruned = []
    mfma = 16 if M < 32 or N < 32 else 32
    large_gemm = M >= 2048 and N >= 2048

    for c in configs:
        BSM = c["BLOCK_SIZE_M"]
        BSN = c["BLOCK_SIZE_N"]
        BSK = c["BLOCK_SIZE_K"]
        nw = c["num_warps"]
        GROUP_M = c["GROUP_SIZE_M"]

        if mfma == 4 and BSK < 64:
            continue
        if BSM * BSN < 64:
            continue
        if M * 2 < BSM and BSM != 16:
            continue
        if N * 2 < BSN and BSN != 16:
            continue
        if GROUP_M * BSM > M and GROUP_M != 1:
            continue
        # LDS check
        LDS = BSK * BSM + BSK * BSN  # fp8: 1 byte each
        if LDS > 65536:
            continue
        if large_gemm:
            if BSM < 64 or BSN < 64 or BSK < 64 or nw < 4:
                continue
        pruned.append(c)
    return pruned


def prune_search_space(num_tokens, search_space):
    N1, K1 = SHARD_INTERMEDIATE_SIZE, HIDDEN_SIZE
    N2, K2 = HIDDEN_SIZE, SHARD_INTERMEDIATE_SIZE // 2
    p1 = prune_rocm_configs(num_tokens * TOPK, N1, K1, search_space)
    p2 = prune_rocm_configs(num_tokens * TOPK, N2, K2, search_space)
    combined, seen = [], set()
    for c in p1 + p2:
        key = tuple(sorted(c.items()))
        if key not in seen:
            seen.add(key)
            combined.append(c)
    return combined


def make_tensors(num_tokens, num_iters):
    init_dtype = torch.float16  # fp8 weights init in fp16 then cast
    N = SHARD_INTERMEDIATE_SIZE // 2  # after silu_and_mul
    block_n, block_k = BLOCK_QUANT_SHAPE

    x = torch.randn(num_tokens, HIDDEN_SIZE, dtype=DTYPE, device="cuda")
    w1 = torch.randn(E, SHARD_INTERMEDIATE_SIZE, HIDDEN_SIZE, dtype=init_dtype, device="cuda").to(FP8_DTYPE)
    w2 = torch.randn(E, HIDDEN_SIZE, N, dtype=init_dtype, device="cuda").to(FP8_DTYPE)

    n_tiles_w1 = (SHARD_INTERMEDIATE_SIZE + block_n - 1) // block_n
    k_tiles_w1 = (HIDDEN_SIZE + block_k - 1) // block_k
    n_tiles_w2 = (HIDDEN_SIZE + block_n - 1) // block_n
    k_tiles_w2 = (N + block_k - 1) // block_k
    scale_factor = 1e-2
    w1_scale = torch.rand((E, n_tiles_w1, k_tiles_w1), dtype=torch.float32, device="cuda") * scale_factor
    w2_scale = torch.rand((E, n_tiles_w2, k_tiles_w2), dtype=torch.float32, device="cuda") * scale_factor
    a1_scale = torch.randn(1, dtype=torch.float32, device="cuda")
    a2_scale = torch.randn(1, dtype=torch.float32, device="cuda")

    gating_output = torch.randn(num_iters, num_tokens, E, dtype=torch.float32, device="cuda")
    input_gating = torch.empty(num_tokens, E, dtype=torch.float32, device="cuda")

    quant_config = FusedMoEQuantConfig.make(
        quant_dtype=torch.float8_e4m3fn,
        w1_scale=w1_scale,
        w2_scale=w2_scale,
        a1_scale=a1_scale,
        a2_scale=a2_scale,
        block_shape=BLOCK_QUANT_SHAPE,
    )
    return x, w1, w2, quant_config, gating_output, input_gating


def benchmark_config(config, x, w1, w2, quant_config, gating_output, input_gating,
                     num_iters=20):
    def prepare(i):
        input_gating.copy_(gating_output[i])

    def run():
        with override_config(config):
            topk_weights, topk_ids, _ = fused_topk(x, input_gating, TOPK, renormalize=True)
            return fused_experts(x, w1, w2, topk_weights, topk_ids,
                                 inplace=not disable_inplace(), quant_config=quant_config)

    # JIT warmup
    prepare(0)
    run()
    torch.accelerator.synchronize()

    # CUDA graph capture
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        for _ in range(10):
            run()
    torch.accelerator.synchronize()

    for _ in range(5):
        graph.replay()
    torch.accelerator.synchronize()

    start_event = torch.Event(enable_timing=True)
    end_event = torch.Event(enable_timing=True)
    latencies = []
    for i in range(num_iters):
        prepare(i % len(gating_output))
        torch.accelerator.synchronize()
        start_event.record()
        graph.replay()
        end_event.record()
        end_event.synchronize()
        latencies.append(start_event.elapsed_time(end_event))

    avg_us = sum(latencies) / (num_iters * 10) * 1000
    graph.reset()
    return avg_us


def tune_batch(num_tokens, search_space):
    pruned = prune_search_space(num_tokens, search_space)
    print(f"  batch={num_tokens}: {len(pruned)} configs after pruning", flush=True)

    x, w1, w2, quant_config, gating_output, input_gating = make_tensors(num_tokens, num_iters=20)

    best_config = None
    best_time = float("inf")
    for idx, config in enumerate(pruned):
        try:
            t = benchmark_config(config, x, w1, w2, quant_config,
                                  gating_output, input_gating, num_iters=20)
        except triton.runtime.autotuner.OutOfResources:
            continue
        if t < best_time:
            best_time = t
            best_config = config
        if (idx + 1) % 50 == 0:
            print(f"    [{idx+1}/{len(pruned)}] best so far: {best_time:.1f} us", flush=True)

    gc.collect()
    torch.accelerator.empty_cache()
    return best_config, best_time


def sort_config(config):
    keys = ["BLOCK_SIZE_M", "BLOCK_SIZE_N", "BLOCK_SIZE_K", "GROUP_SIZE_M",
            "num_warps", "num_stages", "waves_per_eu"]
    return {k: config[k] for k in keys if k in config}


def save_configs(best_configs, save_dir):
    dtype_str = _get_config_dtype_str(DTYPE, use_fp8_w8a8=USE_FP8_W8A8)
    filename = get_config_file_name(E, SHARD_INTERMEDIATE_SIZE // 2,
                                    dtype_str, BLOCK_QUANT_SHAPE)
    os.makedirs(save_dir, exist_ok=True)
    filepath = os.path.join(save_dir, filename)
    print(f"Writing config to {filepath}", flush=True)
    payload = {"triton_version": triton.__version__, **best_configs}
    with open(filepath, "w") as f:
        json.dump(payload, f, indent=4)
        f.write("\n")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Standalone MoE FP8 tuner for R9700")
    parser.add_argument("--save-dir", default="/vllm-tuned-configs",
                        help="Directory to save tuned configs")
    parser.add_argument("--batch-sizes", nargs="+", type=int, default=BATCH_SIZES,
                        help="Batch sizes to tune (default: all 18)")
    args = parser.parse_args()

    print(f"Tuner: E={E}, N={SHARD_INTERMEDIATE_SIZE//2}, hidden={HIDDEN_SIZE}, "
          f"topk={TOPK}, dtype=fp8_w8a8, block={BLOCK_QUANT_SHAPE}", flush=True)
    print(f"Device: {torch.cuda.get_device_name(0)}", flush=True)

    search_space = get_rocm_tuning_space()
    print(f"Full search space: {len(search_space)} configs", flush=True)

    best_configs = {}
    start = time.time()
    for bs in args.batch_sizes:
        t0 = time.time()
        best, best_time = tune_batch(bs, search_space)
        elapsed = time.time() - t0
        print(f"  batch={bs}: best={best_time:.1f} us  config={best}  ({elapsed:.0f}s)", flush=True)
        best_configs[str(bs)] = sort_config(best)
        save_configs(best_configs, args.save_dir)  # incremental save after each batch

    filepath = save_configs(best_configs, args.save_dir)
    total = time.time() - start
    print(f"Done. Tuning took {total:.0f}s. Config: {filepath}", flush=True)


if __name__ == "__main__":
    main()
