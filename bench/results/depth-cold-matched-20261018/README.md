# Matched cold pair: TRITON_ATTN vs the auto-selected ROCM_ATTN at 98K depth

The depth tables in `docs/rdna4-long-context.md` are all `--prewarm`, i.e. prefix-cache hits
with almost no real prefill in them. That isolates decode, which is where the fault was, but it
leaves two things unmeasured: the **prefill kernel**, which the backend flag also swaps, and
**gate 4**, where a co-batched prefill chunk drops the decoders beside it to the 2D grid.

These four files close that gap.

## Files

| file | arm | what it is |
|---|---|---|
| `triton-attn-cold-98k.json` | `qwen3.8-27b-think` via llama-swap | cold, unique prompts, conc 1/4/7 |
| `rocm-attn-cold-98k.json` | same checkpoint, no flag, side port | cold, unique prompts, conc 1/4 |
| `triton-attn-prewarmed-serial.json` | shipping profile | prewarmed serial 1K / 65K / 131K |
| `triton-attn-needle.json` | shipping profile | retrieval, 3 depths x 3 positions, 9/9 |

## Controls

Both cold arms: same FP8 checkpoint, no MTP, `--max-model-len 131072`,
`--gpu-memory-utilization 0.95`, `--max-num-seqs 32`, `-e GPU_MAX_HW_QUEUES=1`, TP4,
98,304-token unique prompts, `gen=256`, no prefix cache. The only difference is
`--attention-backend TRITON_ATTN` against auto-selection.

Two checks that the arms really are comparable:

- **KV pool is identical** — `GPU KV cache size: 1,126,917 tokens`, `8.60x` at 131,072 on both.
  The win is not extra KV room.
- **Both carry the band flag**, so neither arm can be a slow decode-band draw
  (`docs/rdna4-decode-bands.md`). Without that control the decode column would be worthless.

## Result

| conc | backend | per-stream decode | mean TTFT | max TTFT | agg prefill | e2e max |
|---|---|---|---|---|---|---|
| 1 | TRITON_ATTN | **35.9** tok/s | **46.8 s** | 46.8 s | 2,099 tok/s | **53.9 s** |
| 1 | ROCM_ATTN (auto) | 2.0 tok/s | 50.5 s | 50.5 s | 1,949 tok/s | 180.4 s |
| 4 | TRITON_ATTN | **10.6** tok/s | **82.2 s** | 140.7 s | 2,794 tok/s | **149.4 s** |
| 4 | ROCM_ATTN (auto) | 1.3 tok/s | 166.3 s | 292.1 s | 1,346 tok/s | 406.8 s |

The `conc=7` TRITON row (not matched, run only on the shipping arm as canary item 4) is
6.1 tok/s per stream, 4,853 tok/s aggregate prefill, 7/7 completed, no errors.

## Reading it

- **The prefill kernel is not a regression.** `conc=1` is the clean comparison — one request in
  flight, nothing to interleave with, so TTFT is pure prefill. 46.8 s against 50.5 s: TRITON is
  **7.7% faster**.
- **Do not read the `conc=4` TTFT gap as a prefill result.** It is confounded in TRITON's favour:
  ROCM_ATTN decodes 8-18x slower, so its decode steps hold the GPU and push queued prefill
  chunks behind them. Decode speed inflates TTFT at concurrency.
- **Gate 4 is expensive and not decisive.** Continuous real prefill costs TRITON most of its
  serial margin (35.9 → 10.6 tok/s from one stream to four), because co-batched prefill keeps
  closing the 3D path. It still wins the cell **8.0x**, and 2.7x end to end.
- **`agg t/s` in the tool's own table is not a decode rate here.** With a 256-token reply behind
  a 47-292 s prefill it is a wall-clock proxy over a staggered window. Use
  `per_stream_tok_s_mean`, which is what `bench/CLAUDE.md` canary item 4 asks to be recorded.

## A metric fixed while writing this

`depth_bench.py` originally reported `prefill_tok_s` as `sum(prompt_tokens) / mean(TTFT)` — a
batch total over a mean, which is not a rate. It rewards a scheduler that front-loads a few
streams and rises with concurrency even when the batch took longer overall; on the TRITON arm it
read 4,783 and 10,226 tok/s at conc 4 and 7, implying ~4.9x scaling that did not happen. It now
divides by `max(TTFT)`, the point at which the batch's prefills are actually done, giving 2,794
and 4,853 (~2.3x). Numbers in any older JSON under the old key are inflated at conc > 1.
