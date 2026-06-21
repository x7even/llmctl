#!/usr/bin/env python3
"""
Dense FP8 block GEMM autotuner for AMD Radeon R9700 (RDNA4/gfx1201).

Sweeps Triton tile configs for the dense W8A8 block-FP8 GEMM shapes that
vLLM logs as "Config file not found" at startup. For each (N, K) shape and
each batch size M, finds the fastest (BLOCK_SIZE_M/N/K, GROUP_SIZE_M,
num_warps, num_stages) combo and saves a JSON config file that vLLM picks up
on the next startup, eliminating the "sub-optimal" fallback.

Run inside the vLLM container — see scripts/tune-dense-fp8 for the wrapper.

Usage:
    python3 /scripts/tune-dense-fp8-kernel.py [--output DIR] [--shapes N:K,...]
"""
import argparse
import itertools
import json
import os
import sys
import time

import torch
import triton
import triton.testing

sys.path.insert(0, "/usr/local/lib/python3.12/dist-packages")
from vllm.model_executor.layers.quantization.utils.fp8_utils import (
    _w8a8_triton_block_scaled_mm,
)

# Shapes missing R9700 configs (post-TP=4 per-GPU shards, from startup warnings)
DEFAULT_SHAPES = [
    (4096, 5120),
    (5120, 1536),
    (5120, 4352),
    (8704, 5120),
    (3584, 5120),
]

# Batch sizes covering decode (1-32) and prefill (64-2048)
BATCH_SIZES = [1, 2, 4, 8, 16, 24, 32, 64, 128, 256, 512, 1024, 2048]

BLOCK_N = 128  # quantization block size (block_shape=[128,128])
BLOCK_K = 128

# Search space: ~240 configs (N%BLOCK_SIZE_N==0 and K%BLOCK_SIZE_K==0 enforced below)
BLOCK_SIZE_M_VALS  = [16, 32, 64, 128]
BLOCK_SIZE_N_VALS  = [32, 64, 128]
BLOCK_SIZE_K_VALS  = [128, 256]   # must be multiples of BLOCK_K=128
GROUP_SIZE_M_VALS  = [1, 4, 8, 16, 32]
NUM_WARPS_VALS     = [4, 8]
NUM_STAGES         = 2


def build_search_space(N: int, K: int) -> list[dict]:
    configs = []
    for bsm, bsn, bsk, gsm, nw in itertools.product(
        BLOCK_SIZE_M_VALS, BLOCK_SIZE_N_VALS, BLOCK_SIZE_K_VALS,
        GROUP_SIZE_M_VALS, NUM_WARPS_VALS,
    ):
        if N % bsn != 0 or K % bsk != 0:
            continue
        configs.append({
            "BLOCK_SIZE_M": bsm,
            "BLOCK_SIZE_N": bsn,
            "BLOCK_SIZE_K": bsk,
            "GROUP_SIZE_M": gsm,
            "num_warps":    nw,
            "num_stages":   NUM_STAGES,
        })
    return configs


def make_tensors(M: int, N: int, K: int):
    fp8 = torch.float8_e4m3fn
    A  = torch.randn(M, K, device="cuda", dtype=torch.bfloat16).to(fp8)
    B  = torch.randn(N, K, device="cuda", dtype=torch.bfloat16).to(fp8)
    As = torch.ones(M, K // BLOCK_K, device="cuda", dtype=torch.float32)
    Bs = torch.ones(N // BLOCK_N, K // BLOCK_K, device="cuda", dtype=torch.float32)
    C  = torch.empty(M, N, device="cuda", dtype=torch.bfloat16)
    return A, B, As, Bs, C


def bench_config(A, B, As, Bs, C, N: int, K: int, config: dict) -> float | None:
    M = A.shape[0]
    grid = lambda META: (
        triton.cdiv(M, META["BLOCK_SIZE_M"]) * triton.cdiv(N, META["BLOCK_SIZE_N"]),
    )

    def run():
        _w8a8_triton_block_scaled_mm[grid](
            A, B, C, As, Bs,
            M, N, K, BLOCK_N, BLOCK_K,
            A.stride(0), A.stride(1),
            B.stride(1), B.stride(0),
            C.stride(0), C.stride(1),
            As.stride(0), As.stride(1),
            Bs.stride(1), Bs.stride(0),
            **config,
        )

    try:
        ms = triton.testing.do_bench(run, warmup=3, rep=20)
        return ms
    except Exception:
        return None


def tune_shape(N: int, K: int, output_dir: str) -> dict:
    print(f"\n{'='*64}", flush=True)
    print(f"  Tuning N={N}, K={K}", flush=True)
    print(f"{'='*64}", flush=True)

    search_space = build_search_space(N, K)
    print(f"  Search space: {len(search_space)} configs", flush=True)
    print(f"  Batch sizes:  {BATCH_SIZES}", flush=True)
    print(flush=True)

    results: dict[int, dict] = {}

    for M in BATCH_SIZES:
        A, B, As, Bs, C = make_tensors(M, N, K)

        best_ms   = float("inf")
        best_cfg  = None

        for cfg in search_space:
            ms = bench_config(A, B, As, Bs, C, N, K, cfg)
            if ms is not None and ms < best_ms:
                best_ms  = ms
                best_cfg = cfg

        del A, B, As, Bs, C
        torch.cuda.empty_cache()

        if best_cfg is not None:
            tflops = (2 * M * N * K) / (best_ms * 1e-3) / 1e12
            print(
                f"  M={M:5d}: {best_ms:.3f}ms  {tflops:.1f} TFLOP/s  "
                f"BSM={best_cfg['BLOCK_SIZE_M']:3d} BSN={best_cfg['BLOCK_SIZE_N']:3d} "
                f"BSK={best_cfg['BLOCK_SIZE_K']:3d} GSM={best_cfg['GROUP_SIZE_M']:2d} "
                f"W={best_cfg['num_warps']}",
                flush=True,
            )
            results[M] = dict(best_cfg)
        else:
            print(f"  M={M:5d}: no valid config found", flush=True)

    if results:
        device_name = "AMD_Radeon_R9700"
        fname = (
            f"N={N},K={K},device_name={device_name},"
            f"dtype=fp8_w8a8,block_shape=[{BLOCK_N},{BLOCK_K}].json"
        )
        fpath = os.path.join(output_dir, fname)
        with open(fpath, "w") as f:
            json.dump({str(k): v for k, v in results.items()}, f, indent=4)
        print(f"\n  Saved → {fpath}", flush=True)

    return results


def main():
    ap = argparse.ArgumentParser(description="Dense FP8 block GEMM autotuner")
    ap.add_argument("--output", default="/dense-fp8-configs",
                    help="Output directory for JSON config files")
    ap.add_argument("--shapes", default=None,
                    help="Comma-separated N:K pairs, e.g. 4096:5120,5120:1536 "
                         "(default: all 5 missing shapes)")
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)

    shapes = DEFAULT_SHAPES
    if args.shapes:
        shapes = [tuple(int(x) for x in s.split(":")) for s in args.shapes.split(",")]

    print("Dense FP8 block GEMM autotuner — AMD Radeon R9700")
    print(f"Output dir : {args.output}")
    print(f"Shapes     : {shapes}")
    print(f"Search size: ~{len(build_search_space(shapes[0][0], shapes[0][1]))} configs per shape")
    print(f"Batch sizes: {BATCH_SIZES}")

    t0 = time.time()
    for N, K in shapes:
        tune_shape(N, K, args.output)

    elapsed = time.time() - t0
    print(f"\n{'='*64}")
    print(f"Total time: {elapsed/60:.1f} min")
    print(f"Config files written to: {args.output}")
    print(f"{'='*64}")


if __name__ == "__main__":
    main()
