# Long-context decode on gfx1201: parallelism starvation in the attention kernels

A Qwen3.8-27B profile on this stack could lose **24× of its decode throughput** between a
1K and a 131K context, and the cause was not bandwidth, not the PCIe link and not the
decode band. It was that every available split-KV decode kernel had been gated off, leaving
attention to run in a handful of workgroups on a 64-CU GPU, each walking the whole context
serially.

This document records the mechanism, the measurements, and which profile settings turn it on
and off. Companion documents: `docs/rdna4-decode-bands.md` (a different ~2× loss, with
overlapping symptoms) and `docs/gpu-counts.md`.

---

## The symptom

Serial decode, Qwen3.8-27B-FP8, TP4, `--no-thinking`, `gen 128`, measured with
`bench/depth_bench.py`. Three configurations, same image, same weights, same host, all
drawn in the fast decode band:

| depth | A0 `27b-code`: MTP + ROCM_ATTN | A3: no MTP + TRITON_ATTN | A4 `27b-think`: no MTP + ROCM_ATTN |
|---|---|---|---|
| 1,023 | 72.3 | 46.3 | 40.0 |
| 4,096 | 51.6 | 47.5 | 26.6 |
| 16,387 | 25.7 | 45.6 | 11.4 |
| 32,775 | 17.6 | 43.4 | 6.4 |
| 65,551 | 10.2 | 39.4 | 3.4 |
| 98,327 | 6.5 | 36.1 | 2.0 |
| 130,911 | — | 33.4 | 1.4 |

Read the columns, not the rows. A0 decays 11× across the range and A4 decays **28×**, while
A3 decays 1.39× — its curve is essentially flat out to the full 131K window. At 131K, A3 is
**24× faster than A4**.

The counter-intuitive part: **A4 differs from A0 only by having MTP removed, and it is three
times worse.** Removing speculative decoding did not free up capacity, it destroyed it. That
is the clue that the problem is not arithmetic throughput at all.

---

## Why: four gates, all keyed on `query_len`

Attention decode on this model at TP4 can take one of four code paths. Which one it takes is
decided by the attention backend and by the number of query tokens per decode step — and
*every* path that parallelises over the context length is gated off by something this stack
was doing.

Three of the gates are properties of a profile, and the fix below opens all three. The
fourth is a property of each individual step, cannot be configured away, and is what
separates the benchmark numbers from what a mixed-traffic fleet will see; it is documented
after the first three because it only becomes relevant once they are open.

The model shape matters, so take it from the checkpoint config: 64 layers at
`full_attention_interval=4` (16 full-attention, 48 gated-delta-net), `head_dim=256`,
`num_attention_heads=24`, `num_key_value_heads=4`. **At TP4 that is 6 query heads and 1 KV
head per rank.** A grid dimension of `num_kv_heads` is therefore a grid dimension of *one*.

### Gate 1 — the ROCm custom paged-attention kernel is permanently disqualified

`vllm/platforms/rocm.py`'s `use_rocm_custom_paged_attention()` requires `head_size == 128`.
This model has `head_dim=256`, so the fast hand-written kernel is unavailable no matter what
else is configured. (It also wants `block_size == 16`, and the attention block size is forced
to 800 by the GDN layers' requirements — `platforms/interface.py` only ever *raises* the
block size, so `--block-size 16` cannot claw it back. But the head size alone settles it.)

Block size was an early red herring here. It is not the reason.

### Gate 2 — with MTP, decode is routed to the prefill kernel

`chunked_prefill_paged_decode.py:303`:

```python
if max_query_len > 1:
    context_attention_fwd(..., skip_decode=True)
```

With MTP at `num_speculative_tokens: 2`, **every decode step carries query_len=3**, so the
branch is taken and decode is serviced by `prefix_prefill._fwd_kernel`. That kernel's grid is
`(batch, num_q_heads, cdiv(max_query_len, BLOCK_M))` — at conc=1, TP4, that is
`(1, 6, cdiv(3,32)=1)` = **6 workgroups**, each looping over the full context in steps of 32.

Without MTP, the fallback is `kernel_paged_attention_2d[(num_seqs, num_kv_heads)]` with
`filter_by_query_len=True`. That kernel **has no KV-split dimension at all**, and at conc=1
with 1 KV head per rank its grid is `(1, 1)` — **one workgroup** for the entire attention
computation. This is A4, and it is why A4 is the worst column in the table.

### Gate 3 — with MTP, TRITON_ATTN's 3D split-KV path is also closed

`triton_unified_attention.py`'s `use_3d` predicate, verbatim:

```python
use_3d = not (
    seq_threshold_3D is None
    or num_par_softmax_segments is None
    or softmax_segm_output is None
    or softmax_segm_max is None
    or softmax_segm_expsum is None
    or max_seqlen_q > 1          # <-- MTP sets this to 3
    or num_seqs > seq_threshold_3D
    or is_batch_invariant
)
...
if not use_3d:
    grid = (total_num_q_blocks, num_kv_heads)
else:
    grid = (total_num_q_blocks, num_kv_heads, num_par_softmax_segments)
```

So `max_seqlen_q > 1` closes the 3D path too. **MTP is the single gate that shuts every
context-parallel decode path on this model**, which is the whole explanation for why removing
it (A4) and adding TRITON_ATTN (A3) behave so differently: A4 removed the gate but had no
kernel able to use the opening, A3 removed the gate *and* selected the backend that can.

### What the open gate buys

`triton_attn.py` sets `NUM_PAR_SOFTMAX_SEGMENTS = 16`, so the 3D grid gains a third dimension
of 16 and each program walks 1/16 of the context. Serial loop iterations at 98K:

| arm | decode path | grid at conc=1, TP4 | serial iterations at 98K |
|---|---|---|---|
| A0 | `prefix_prefill._fwd_kernel` | `(1, 6, 1)` = 6 | `cdiv(98304, 32)` = 3072 |
| A4 | `kernel_paged_attention_2d` | `(1, 1)` = 1 | full context, one program |
| A3 | unified 3D, 16 segments | `(q_blocks, 1, 16)` | `cdiv(98304, 16*16)` = **384** |

384 against 3072 is the 8× that shows up as A3's flat curve.

---

## Gate 4 — a prefill chunk in the batch closes the path for the decoders beside it

The three gates above are properties of a profile. This one is a property of each *step*,
and it is what bounds the win on a real fleet rather than on a benchmark.

`use_3d` is evaluated per batch, from a single batch-wide scalar:

```python
# vllm/v1/attention/backends/triton_attn.py, TritonAttentionBuilder.build
max_query_len = common_attn_metadata.max_query_len      # passed straight through
```

`common_attn_metadata.max_query_len` is `max_num_scheduled_tokens` — the **maximum over all
requests in the batch** of tokens scheduled for that request (`gpu_model_runner.py`). A
decoding request contributes 1. A chunked-prefill request contributes its whole chunk.

So with `--enable-chunked-prefill` on, any step that carries a prefill chunk has
`max_seqlen_q` equal to that chunk length, `use_3d` is false, and **every deep decoder
sharing that step falls back to the 2D grid** — the same single-workgroup walk the fix was
meant to avoid. It is not partial: the predicate is one boolean for the whole batch.

TRITON_ATTN has no mitigation for this. Unlike several other backends it defines no
`reorder_batch` and never calls `split_decodes_and_prefills`, so it cannot build separate
decode metadata with its own smaller `max_query_len`:

```console
$ grep -n 'split_decodes\|reorder_batch\|def build' .../triton_attn.py
185:    def build_for_cudagraph_capture(
195:    def build(
```

What this does and does not change:

- **It does not change the profile comparison, for decode.** The auto-selected ROCM_ATTN path
  is on a 2D grid in *every* step, mixed or not. TRITON_ATTN is on the 3D path in pure-decode
  steps and falls back to the same 2D grid otherwise, so on the decode side it is never worse.
  The fix stands.
- **That argument covers decode only, and the backend flag also changes prefill.** Selecting
  TRITON_ATTN swaps the prefill kernel as well: its unified kernel replaces ROCM_ATTN's
  `context_attention_fwd`. Nothing here measures that, because every depth × concurrency cell
  in this document is `--prewarm`, i.e. a prefix-cache hit with almost no real prefill in it.
  A 24× decode win dominates any plausible prefill delta on a long reply, so this does not
  put the fix in doubt — but a long-prompt / short-reply workload (one big context, a few
  tokens back) is **not characterised**, and that is exactly the shape of some agent traffic.
  Measure it before recommending the flag for that regime.
- **It does bound the magnitude.** The depth × concurrency matrix in this document was
  measured with `--prewarm`, i.e. on prefix-cache hits, so almost every step was a pure
  decode and the 3D path was open almost always. A fleet sending *unique* long prompts
  interleaves real prefill chunks continuously, and in that regime the measured speedups are
  a ceiling, not an expectation.
- **The number to quote for a mixed fleet has not been measured yet.** Do not interpolate
  it: the fraction of steps carrying a prefill depends on arrival rate, prompt length and
  `--max-num-batched-tokens`, none of which the matrix varied.

This is also the reason a long-context stress test must record **decode rate during the
run**, not merely that no request timed out. "Everything finished" is compatible with every
decoder having run on the 2D path the whole time.

## The threshold that can silently close the path again

`use_3d` also requires `num_seqs <= seq_threshold_3D`. That threshold is **not** a constant:

```
MIN_LAUNCH_GRID_SIZE_2D = 128
seq_threshold_3D = MIN_LAUNCH_GRID_SIZE_2D // num_heads_kv      # 128 // 1 = 128
# then, when full cudagraphs are enabled, it snaps to the nearest capture size:
seq_threshold_3D = min(capture_sizes, key=lambda x: abs(x - 128))
```

With `--cudagraph-capture-sizes 1 2 4 8 16 32` the nearest capture size to 128 is **32**, and
the profile's `--max-num-seqs` is also 32 — so the path stays open across the whole serving
range, but only just.

**Raising `--max-num-seqs` above 32, or changing the capture-size list, can switch the 3D path
off with nothing in the log to say so.** Both profile comments carry this warning. Re-measure
with `bench/depth_bench.py` after any change to either flag.

---

## Correctness: a split-KV kernel must be checked, not assumed

A kernel that splits the context into 16 segments and reduces across them can combine those
segments wrongly and lose whole stretches of context — and it would still benchmark
perfectly, because `depth_bench.py` sends filler with `ignore_eos` and never reads the reply.
Speed at depth is worthless if the model can no longer see the depth.

`bench/needle_check.py` exists for this. It plants a unique code in a long filler body, asks
for it back, and grades on exact substring — sweeping the needle's **position** as well as the
depth, because position is the discriminator for this bug class: a needle at 30% depth and one
at 70% land in different softmax segments. A uniform failure means retrieval is broken;
failures clustered at particular positions mean the segment reduction is.

Measured 2026-10-18, 5 positions (0.05/0.25/0.50/0.75/0.95) at each of 16K, 64K and 131K,
identical needles on both arms:

| arm | retrieved |
|---|---|
| A4, ROCM_ATTN (reference) | 15/15 |
| A3, TRITON_ATTN 3D | **15/15** |

The segment reduction is correct. Run this before shipping any attention backend, kernel or
block-size change:

```bash
python3 bench/needle_check.py --model <profile> --no-thinking \
    --depths 16384,65536,131072 --positions 0.05,0.25,0.5,0.75,0.95 \
    --max-model-len 131072        # required through llama-swap, which does not report it
```

Exit status is 0 only if every cell retrieved its needle.

---

## Concurrency: the win is not only a single-stream win

Prewarmed matrix (steady-state decode from a prefix-cache hit — see `--prewarm` in
`bench/depth_bench.py` and the note below), aggregate tok/s per cell:

| depth | conc | A0 MTP+ROCM | A3 no-MTP+TRITON | A4 no-MTP+ROCM |
|---|---|---|---|---|
| 4,096 | 1 | 44.4 | 47.7 | 26.6 |
| 4,096 | 4 | 131.4 | 140.0 | 93.9 |
| 4,096 | 8 | 175.1 | **269.6** | 172.1 |
| 16,384 | 1 | 25.8 | 45.6 | 11.4 |
| 16,384 | 4 | 72.5 | 128.8 | 40.7 |
| 16,384 | 8 | 109.2 | **192.3** | 73.2 |
| 65,536 | 1 | 10.2 | 39.4 | 3.4 |
| 65,536 | 4 | 26.2 | 107.8 | 12.8 |
| 65,536 | 8 | 36.6 | **143.4** | 24.5 |

A3 wins every cell in the matrix, including the shallow ones. TTFT improves too: at
65K × conc=8, 1.81 s against A0's 10.59 s.

The KV pool is unaffected — 1,126,917 tokens on both A3 and A4 at `--max-model-len 131072`,
so the 3D path's segment buffers cost about 0.06 GiB. 8 × 65K is 47% of the pool; these cells
are not pool-starved and preemption does not explain anything here.

### Two measurement cautions

- **Deep cells at conc>1 measure prefill contention unless prewarmed.** With unique prompts
  and chunked prefill, every stream's prefill tokens ride inside every other stream's decode
  steps. A cold 65K × conc=4 cell measured 181 s TTFT against 13.7 s of serial end-to-end,
  and at conc=8 two requests timed out. That is a real regime — it is what a cold fleet
  hitting long unique documents costs — but it is not the regime an agent fleet runs in, where
  context grows a turn at a time and prefix caching covers nearly all of it. Say which one a
  number came from.
- **TTFT is only comparable within a single cold pass.** The prefix cache survives between
  runs: the same 65K conc=1 prompt reported 1.23 s in one run and 25.79 s in another.

---

## What this is *not*

Each of these was ruled out by measurement or arithmetic, and each is a plausible-sounding
explanation someone will reach for again:

- **Memory bandwidth.** Step time grew by ~318 ms at 98K. KV at 98K is ~6.4 GB total, ~1.6
  GB/GPU/step, i.e. ~2.5 ms at ~640 GB/s. That is **~127× too small** to explain the loss.
- **The PCIe slot link.** Per-step TP collective traffic for this model is ~2 MB over one
  rank's link: ~35 µs at Gen5 against ~76 µs at Gen4, a 41 µs difference against a ~25 ms
  step. ~600× too small. See `docs/rdna4-decode-bands.md` for why a downtrained link is still
  worth fixing, just not for throughput.
- **The gfx1201 decode band.** A different effect, and already handled by
  `-e GPU_MAX_HW_QUEUES=1`. It is a *fixed per-step tax* of roughly 2× that amortises with
  batch size; it cannot produce a 28× slide that grows with depth. All three arms above carried
  the flag and all were confirmed in the fast band (`mem_busy` 48% under load, against 26%
  slow / 46% fast).
- **KV pool starvation / preemption.** 47% of the pool in use at the deepest concurrent cell.
- **`--block-size 16`.** Block-size unification only ever raises the block size, and the head
  size disqualifies the custom kernel anyway.
- **`--decode-context-parallel-size` (DCP).** This would shard KV along the sequence
  dimension — precisely the missing parallelism — but it is implemented only in the
  FlashInfer, FlashAttention and MLA backends, none of which exist on gfx1201.
- **`VLLM_ATTENTION_BACKEND`.** This env var **does not exist in vLLM 0.26.0**. The selector
  is the CLI flag `--attention-backend`, and an invalid name **silently falls through to
  auto-selection**. Always confirm in the log:
  `rocm.py:570 Using TRITON_ATTN backend (selected via --attention-backend).`
  Auto-selection on this model logs instead:
  `rocm.py:615 Found incompatible backend(s) [TURBOQUANT] ... Overriding with ROCM_ATTN out of potential backends: ['ROCM_ATTN', 'TRITON_ATTN'].`

---

## Current profile settings

| profile | MTP | backend | rationale |
|---|---|---|---|
| `qwen3.8-27b-think` | no | **TRITON_ATTN** (explicit) | no MTP, so the 3D path is available; 24× at 131K over the auto-selected ROCM_ATTN |
| `qwen3.8-27b-code` | yes | ROCM_ATTN (auto) | MTP gates the 3D path shut, so the flag would do nothing; keeps its short-context MTP advantage |
| `qwen3.8-27b-fast` | yes | ROCM_ATTN (auto) | as above |

**What "auto" actually resolves to.** The selector does not simply prefer ROCM_ATTN — it first
picks a backend that turns out to be unusable, then falls back. On a cold boot of the no-MTP
profile *without* the flag, all four ranks log:

```
rocm.py:615] Found incompatible backend(s) [TURBOQUANT] with AttentionType.DECODER.
             Overriding with ROCM_ATTN out of potential backends: ['ROCM_ATTN', 'TRITON_ATTN'].
```

TRITON_ATTN is in the candidate list the whole time; it is simply ordered second, and nothing in
that message hints that the ordering costs 24× at depth. With the flag the line instead reads
`rocm.py:570] Using TRITON_ATTN backend (selected via --attention-backend)`.

Those two lines are the only reliable way to know which kernel is actually serving. An
unrecognised `--attention-backend` value falls through to auto-selection **without an error**,
and `VLLM_ATTENTION_BACKEND` is not read at all in 0.26.0 — so a profile can look correct and
silently serve on the collapsing path. Check the log, not the config.

One useful control from the same matched pair: the KV pool is **identical** on both arms —
`GPU KV cache size: 1,126,917 tokens`, `Maximum concurrency for 131,072 tokens per request:
8.60x`. Whatever the backend changes, it is not how much context fits.

**The flag does nothing on an MTP profile.** Adding `--attention-backend TRITON_ATTN` to
`27b-code` leaves `max_seqlen_q = 3`, so `use_3d` is still false and decode still goes to a 2D
grid. Choosing the long-context path means giving up MTP; it is one decision, not two.

Which profile to reach for therefore depends on context depth, and the crossover is between
4K and 16K:

- **below ~8K**, MTP's extra tokens per step win — use `27b-code`
- **above ~16K**, the flat curve wins by a growing margin — use `27b-think`

Whether `27b-code` should also give up MTP to get the flat curve is a policy question about
the default workload, not a measurement question; the measurements are above.

### The `27b-code` default: the evidence points both ways

This is left as the user's call because the two benchmarks that bear on it disagree, and
each is right about its own workload.

`medium-256` (a 256-token prompt, `--requests 32`, free generation) says keep MTP. The
no-MTP + TRITON configuration loses at every concurrency:

| conc | `27b-code` (MTP, shipped) | no-MTP + TRITON | ratio |
|---|---|---|---|
| 1 | 66 | 46.2 | 0.70× |
| 2 | 113 | 80.6 | 0.71× |
| 4 | 194 | 150.8 | 0.78× |
| 8 | 361 | 267.3 | 0.74× |
| 16 | 549 | 457.7 | 0.83× |

The prewarmed depth matrix (`gen 128`, prefix-cache hit, aggregate tok/s) says the opposite
from 4K upwards:

| depth | conc | MTP + ROCM | no-MTP + TRITON | ratio |
|---|---|---|---|---|
| 4,096 | 8 | 175.1 | 269.6 | 1.54× |
| 16,384 | 8 | 109.2 | 192.3 | 1.76× |
| 65,536 | 8 | 36.6 | 143.4 | 3.92× |

Both are real; they measure different regimes, and neither is a general claim. `medium-256`
is a 256-token prompt, which is far below any agent's working context — `bench/CLAUDE.md`
says plainly that it tells you nothing about depth. The depth cells are prefix-cache hits
with a fixed 128-token generation, so they isolate decode and exclude the unique-prefill
contention a real fleet pays.

What follows for routing, and what does not:

- **Keep `27b-code`'s flags as they are.** Nothing here shows the shipped default is wrong
  for short-prompt, high-concurrency work, and flipping it would cost 17–30% there.
- **Route long-context agent work to `27b-think` explicitly.** Coding-agent contexts start
  well above 4K and grow, which is the region where every cell favours it.
- **The default alias is still an open question**, because which of the two tables describes
  the real fleet depends on prompt-depth distribution, and that has not been measured here —
  vLLM does not log per-request token counts at INFO, so it cannot be recovered from the
  existing logs. Measuring it is the prerequisite for changing the default, not another
  benchmark of either profile.
