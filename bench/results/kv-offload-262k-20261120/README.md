# `qwen3.8-27b-think` at 262,144 — evidence for PR #34

All of this comes from **one** container: `llmstack-vllm-qwen3.8-27b-think`, started
`2026-11-09 19:26:19 UTC`, serving `--max-model-len 262144` with
`SimpleCPUOffloadConnector` continuously for **10 d 11 h**. It was never restarted while
these files were gathered. It was stopped afterwards, to load `qwen3.8-flash-next-vllm`.

| file | what it is |
|---|---|
| `needle-262k.json` | retrieval gate: 3 depths x 5 needle positions, **15/15** |
| `metrics-27b-think-20261120.prom` | `/metrics` at 06:24 UTC |
| `metrics-27b-think-post-needle.prom` | `/metrics` at 06:39 UTC, after the needle run |
| `startup-facts-27b-think.txt` | KV pool, connector allocation, backend, non-default args |
| `container-argv-27b-think.json` | what was actually passed to `vllm serve` |

## Separating production traffic from this PR's own needle run

**Neither snapshot is pure production.** The needle run started 06:01 UTC, so the 06:24
dump already contains 11 of its requests (1 calibration probe at 4,059 tokens, five cells
at ~131,10x and five at ~196,65x) and the 06:39 dump contains all 16 (the five ~258,11x
cells included). Both numbers below are therefore stated as *snapshot minus known needle
requests*, not read off the file raw.

06:24 snapshot, prompt-length histogram (bucket edges are 100,000 and 200,000):

| band | snapshot | needle in it | **production** |
|---|---|---|---|
| <= 100,000 tokens | 1,388 | 1 | 1,387 |
| (100,000, 200,000] | 1,344 | 10 | **1,334** |
| > 200,000 tokens | 2 | 1 | **1** |
| total | 2,734 | 11 | 2,723 |

Outcomes, 06:24 snapshot: `stop` 2,671, `length` 63, **`error` 0, `abort` 0**,
`num_preemptions_total` **0**.

So **about 1,334 production requests carried prompts in the (100K, 200K] band, and one
production request exceeded 200,000 tokens** — unservable at the old 131,072 limit. The
histogram's edges cannot resolve how many crossed 131,072 exactly; only that the
population above it is large.

## The window is justified; the offload is not

- `GPU KV cache size: 1,126,219 tokens` / `Maximum concurrency for 262,144 tokens per
  request: 4.30x` — 4.3 full-length streams fit in VRAM **alone**. The window does not
  need the offload. The same profile at `131072` reported 1,126,917 tokens / 8.60x, so
  doubling the window cost **0.06%** of pool capacity, not half of it. It is a per-request
  reach policy, not a memory trade.
- GPU prefix cache: 247,101,904 / 260,488,773 = **94.86%**.
- External (CPU offload) prefix cache: 102,704 / 12,991,981 = **0.79%**. The tier works —
  it returns real hits, it is not dead code — but it served well under 1% of what it was
  asked for, because the GPU pool answers ~95% by itself.
- `num_preemptions_total = 0` across 2,734 requests: the GPU pool never came under the
  pressure the offload exists to relieve.
- The needle run sharpened this rather than muddying it. Between the two snapshots, 15
  prompts of 131K-258K added **1.30 million** external-cache queries and **zero**
  additional hits — 102,704 in both files. Even deliberately deep traffic did not make the
  CPU tier pay.

96 GiB of pinned host RAM (`cpu_bytes_to_use: 103079215104`, 24.00 GB x 4 ranks = 2006 CPU
blocks per rank) buys that 0.79%.

## What these files do NOT establish

- **No A/B against the 131072 arm.** No throughput or latency figure for the offload was
  measured. `docs/fp8-kv-cache.md` is the precedent: on this same profile a 1.89x KV-pool
  win hid a **6x latency loss** that only a matched depth ladder exposed. These counters
  show the window is *used* and *reliable*; they say nothing about whether it is *fast*.
  `bench/depth_bench.py` against both arms is still the way to answer that.
- **TP2 is not re-measured** in this configuration.
- The retrieval gate ran against the offload-enabled server only, so it does not isolate
  the window from the connector. It gates correctness at depth, nothing more.
