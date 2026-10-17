# Block-FP8 GEMM kernels on gfx1201 (R9700)

vLLM ships tuned Triton configs for the W8A8 block-FP8 GEMM for 219 device/shape
combinations. None of them is an R9700. A boot of the 27B FP8 profile therefore
emits twenty warnings - four ranks times five distinct shapes:

    Using default W8A8 Block FP8 kernel config. Performance might be sub-optimal!
    Config file not found at .../configs/N=8704,K=5120,device_name=AMD_Radeon_R9700,dtype=fp8_w8a8,block_shape=[128,128].json

The five shapes, all `dtype=fp8_w8a8, block_shape=[128,128]`, as the warnings name
them (which of the model's projections each one is has not been traced):

    N=5120, K=1536
    N=3584, K=5120
    N=4096, K=5120
    N=5120, K=4352
    N=8704, K=5120

## The path is live, not cosmetic

Worth establishing before spending GPU hours on it, because a warning emitted at
load time proves nothing about what runs at decode time. Here it does, by
elimination: the only call site of `get_w8a8_block_fp8_configs` - the function
that emits the warning - is inside `w8a8_triton_block_scaled_mm` itself
(`model_executor/layers/quantization/utils/fp8_utils.py:941`). There is no
separate inspection or validation path that could log it without also running
the matmul. The warning firing *is* the kernel executing.

Reaching it takes three hops, which is why a naive grep for the kernel name
finds no caller at all:

    TritonFp8BlockScaledMMKernel.apply_block_scaled_mm      (kernels/linear/scaled_mm/triton.py)
      -> torch.ops.vllm.w8a8_triton_block_scaled_mm_func    (direct_register_custom_op)
        -> w8a8_triton_block_scaled_mm                      (imported inside the function body)

The in-body import is what hides it: the name appears nowhere at module scope.
`Fp8BlockScaledDynamicMMLinearKernel` picks a `base_type` and a `fallback_type`;
on ROCm the base (DeepGEMM) is unsupported, so the Triton fallback carries every
block-FP8 linear at every batch size. There is no AITER alternative here either -
that path is gfx942/gfx950 only.

## Why the default config is unlikely to suit decode

With no tuned file the kernel falls back to one hardcoded config for every M:

    BLOCK_SIZE_M=64, BLOCK_SIZE_N=128, BLOCK_SIZE_K=128, GROUP_SIZE_M=32,
    num_warps=4, num_stages=2

A single config cannot be right across the whole range of M, and the range here is
wide: at decode with MTP the M dimension is a multiple of three - 3 at batch 1, 96
at the top of the capture set - while prefill arrives in chunks of up to 32768.
`BLOCK_SIZE_M=64` is a prefill-shaped choice, and at M=3 it means roughly a
twentieth of each tile's rows carry real data.

How much that actually costs is an open question rather than a derivation, because
the grid does not change: `cdiv(3, 64)` and `cdiv(3, 16)` are both 1, so a smaller
`BLOCK_SIZE_M` launches the same number of blocks and wins only through cheaper
work and better occupancy per block. The upside has to be measured.

The tuner's search space is wider than the default in every dimension, including
the one the default's own comment calls constrained:

    num_stages   [2, 3, 4, 5]
    BLOCK_SIZE_M [16, 32, 64, 128, 256]
    BLOCK_SIZE_K [64, 128]
    BLOCK_SIZE_N [32, 64, 128, 256]
    num_warps    [4, 8]
    GROUP_SIZE_M [1, 16, 32, 64]

Note the discrepancy: the fallback config is annotated "BLOCK_SIZE_N must be
divisible by block_size[0]" (128 here), yet `get_configs_compute_bound()` offers 32
and 64, and the only filter applied before benchmarking is on `BLOCK_SIZE_K`. One of
the two is wrong. Treat a tuned config that lands on `BLOCK_SIZE_N < 128` as
suspect until its output is checked against the default config's, not just its
latency.

So the headroom is plausible and it is specifically at the batch sizes the mission
cares about, but it is a hypothesis to test, not a predicted win. It is at least an
independent lever: it changes GEMM tiling only - not the scheduler, the KV budget or
the graph capture set.

## Deployment: bind mounts, not VLLM_TUNED_CONFIG_FOLDER

The repo already has a tuned-config convention for MoE - build into
`vllm-tuned-configs/`, mount it read-only, point `VLLM_TUNED_CONFIG_FOLDER` at
it. **That convention does not work for these configs.** The env var is honoured
by `fused_moe.py`, `mamba_ssm.py` and the LoRA Triton ops, and nowhere else.
`get_w8a8_block_fp8_configs` builds its path with no override at all:

    os.path.join(os.path.dirname(os.path.realpath(__file__)), "configs", json_file_name)

It will only ever read the `configs/` directory inside the installed package. So
a tuned file has to be bind-mounted onto its exact destination path, one `-v` per
file. Mounting the whole directory would shadow the 219 shipped configs and break
every other device, so that is not an option.

Config selection inside the kernel is nearest-M, not interpolation:

    config = configs[min(configs.keys(), key=lambda x: abs(x - M))]

which means the tuned file only needs entries near the M values that actually
occur, but it does need to bracket them - a file tuned only at large M would be
selected at M=3 and could easily be worse than the default.

## Tuning notes

`get_weight_shapes()` in the benchmark script is hardcoded to DeepSeek-V3 and
carries a note saying so, so it has to be replaced with the five shapes above.
The default batch-size list (1, 2, 4, 8, 16, 24, 32, 48, 64, 96, 128, 256, 512,
1024, 1536, 2048, 3072, 4096) brackets both the MTP decode multiples and the
prefill chunk sizes, which is what nearest-M selection needs.

## Gating

A tuned config changes the batch-1 kernel, so `llmband` cannot gate a comparison
of it: the baseline it compares against was calibrated with the untuned kernel,
and a legitimate improvement is indistinguishable from a band draw by step rate
alone. Any measurement here needs interleaved arms and best-of-N draws instead.

## The shapes depend on the tensor-parallel size

The five shapes above were collected at TP4. Booting the same profile at TP2 emits a warning for
`N=8192,K=5120`, which is the TP4 shape `N=4096,K=5120` with N doubled: a column-parallel shard's
N scales with the number of ranks, and a row-parallel shard's K does the same. So the untuned set
is a property of the profile *and* its TP size, not of the model alone.

Two consequences for tuning. A tuned config deployed for TP4 does nothing for the same model run
at TP2, because the kernel looks up a different file name. And anyone collecting the shape list
has to collect it at the TP size they intend to serve at - reading it off a TP4 boot and then
serving at TP2 would leave every linear untuned while appearing to be covered.
