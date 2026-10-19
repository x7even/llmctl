# Benchmarks: the full campaign

The headline peak-throughput table is in the [README](../README.md#benchmarks).
This file is everything behind it: the caveats that decide whether a figure means
anything, depth against concurrency per profile, prefill behaviour, and the
reproduction commands.

All figures here and in the README's table were measured on the same hardware
(4× R9700, 128 GB total) across a single campaign, on the pinned `v0.26.0` image
(`qwen3.8-flash-next-vllm` on its nightly pin), with `--no-thinking`.

Two harnesses, two output conventions, and the difference matters. The depth
tables below come from `bench/depth_bench.py` with **output pinned at 1,024
tokens** (`--gen 1024`, `ignore_eos`): without pinning it, a faster model writes
longer answers and the latency column silently compares answer lengths instead of
speeds. The README's short-prompt table comes from `bench/concurrent_bench.py
--prompt medium-256`, where the generation is **capped** at 256 tokens rather than
pinned, and the models stop well short of the cap. So the two sets of figures are
not interchangeable, and `medium-256` names the cap -- the prompt itself is 41
words.

## Read these three caveats first, or the numbers will mislead you

**1. Aggregate throughput is not responsiveness.** A box can deliver 500 tok/s
in total while every individual client reads at 15 and waits two minutes for a
first token. Both columns are given for every cell. Pick the one that matches
what you are building: `aggregate` for a batch fleet, `per-stream` and `TTFT
p90` for anything a human waits on.

**2. Cold and prewarmed are different workloads, and the gap is large.** Cold,
every stream pays its own prefill. Prewarmed, the prefix cache is hot and TTFT
collapses. Both are published separately below. Never compare across them.

**3. On this GPU a server's decode band is drawn at spawn.** A profile can come
up in a slow band and serve its whole life at roughly half speed with nothing in
the log to say so. Every table states the band and how it was established. A
figure without a band is not a measurement — see `docs/rdna4-decode-bands.md`.

## Depth is the axis a short-prompt sweep cannot see, and it dominates

Prompt depth costs far more than prompt count, and the two 27B profiles diverge
completely as it grows. Cold, at 16,384 tokens:

| conc | `qwen3.8-27b-code` (MTP) | `qwen3.8-27b-think` (no MTP, TRITON_ATTN) |
|---|---|---|
| 1 | 34.9 agg | 45.0 agg |
| 8 | 66.3 agg | 136.1 agg |
| 16 | 46.9 agg | 162.1 agg |
| 32 | 22.5 agg, **29/32** (3 lost: client timeout, engine alive) | 180.9 agg |

`27b-code`'s aggregate **peaks at concurrency 8 and then falls**, while
`27b-think` rises monotonically to 32. At 65,536 tokens cold, `27b-code` goes
further and scales *negatively* — four streams deliver less in total than one:

| | conc=1 | conc=4 |
|---|---|---|
| `qwen3.8-27b-code` aggregate | 11.6 | 9.6 |
| `qwen3.8-27b-think` aggregate | 39.0 | 49.3 |

**That reversal is specific to a cold burst.** Prewarmed, `27b-code` scales up
normally at the same depth (see its prewarmed table below), so the failure is in
paying many deep prefills at once, not in deep decode as such.

**Do not attribute the whole gap to MTP.** The two profiles differ in three
settings at once — MTP, attention backend (`auto` vs `TRITON_ATTN`) and prefill
chunk (16384 vs 32768) — and the wide cold cells include the documented prefill
trade. The cells that isolate decode are the deep single-stream ones, where
`27b-think` reads 39.0 against 11.6 at 65,536 and 33.1 against 5.5 at 130,000.
The mechanism is documented in `docs/rdna4-long-context.md`: MTP closes
`TRITON_ATTN`'s 3D split-KV path, which is the only kernel here that
parallelises over context length.

## Per-profile depth × concurrency

### `qwen3.8-27b-think`

Decode band: **fast (inferred)** — no stored reference; its 46.9 tok/s at 4K and 33.1 at 130K match the documented TRITON_ATTN 46.3 -> 33.4.

Cold — every stream pays its own prefill:

| depth | conc | ok | TTFT mean | TTFT p90 | prefill tok/s | per-stream tok/s | **aggregate tok/s** |
|---|---|---|---|---|---|---|---|
| 4,096 | 1 | 1/1 | 0.9 s | 0.9 s | 4504 | 46.9 | **46.9** |
| 4,096 | 8 | 8/8 | 6.4 s | 7.2 s | 4560 | 35.4 | **237.1** |
| 4,096 | 32 | 32/32 | 22.7 s | 28.8 s | 4554 | 22.3 | **476.9** |
| 16,384 | 1 | 1/1 | 4.1 s | 4.1 s | 3965 | 45.0 | **45.0** |
| 16,384 | 8 | 8/8 | 25.1 s | 33.2 s | 3945 | 27.4 | **136.1** |
| 16,384 | 16 | 16/16 | 45.0 s | 66.6 s | 3937 | 18.8 | **162.1** |
| 16,384 | 32 | 32/32 | 79.7 s | 133.0 s | 3931 | 11.3 | **180.9** |
| 65,536 | 1 | 1/1 | 25.4 s | 25.4 s | 2584 | 39.0 | **39.0** |
| 65,536 | 4 | 4/4 | 81.1 s | 101.3 s | 2590 | 23.3 | **49.3** |
| 129,984 | 1 | 1/1 | 73.7 s | 73.7 s | 1763 | 33.1 | **33.1** |

Prewarmed — prefix cache hot, steady-state decode:

| depth | conc | TTFT mean | per-stream tok/s | **aggregate tok/s** |
|---|---|---|---|---|
| 16,384 | 1 | 0.26 s | 44.9 | **44.9** |
| 16,384 | 8 | 1.56 s | 32.8 | **251.9** |
| 65,536 | 1 | 0.41 s | 39.0 | **39.0** |
| 65,536 | 4 | 1.07 s | 32.5 | **127.1** |

*(A prefill column is deliberately omitted here: with the cache hot it would
read 160,000–270,000 tok/s, which is cache reuse, not compute.)*

### `qwen3.8-27b-code`

Decode band: **fast** — llmband.

Cold — every stream pays its own prefill:

| depth | conc | ok | TTFT mean | TTFT p90 | prefill tok/s | per-stream tok/s | **aggregate tok/s** |
|---|---|---|---|---|---|---|---|
| 4,096 | 1 | 1/1 | 0.9 s | 0.9 s | 4482 | 62.7 | **62.7** |
| 4,096 | 8 | 8/8 | 7.0 s | 8.7 s | 3756 | 45.5 | **323.9** |
| 4,096 | 32 | 32/32 | 25.5 s | 44.8 s | 2922 | 18.0 | **369.6** |
| 16,384 | 1 | 1/1 | 4.0 s | 4.0 s | 4110 | 34.9 | **34.9** |
| 16,384 | 8 | 8/8 | 55.0 s | 92.4 s | 1418 | 16.4 | **66.3** |
| 16,384 | 16 | 16/16 | 147.2 s | 294.0 s | 881 | 7.2 | **46.9** |
| 16,384 | 32 | **29/32** ⚠ | 397.4 s | 1006.2 s | 416 | 1.5 | 22.5 |
| 65,536 | 1 | 1/1 | 28.4 s | 28.4 s | 2310 | 11.6 | **11.6** |
| 65,536 | 4 | 4/4 | 202.5 s | 368.0 s | 713 | 5.4 | **9.6** |
| 129,984 | 1 | 1/1 | 90.4 s | 90.4 s | 1438 | 5.5 | **5.5** |

- ⚠ **16,384 × 32** — 3 of 32 requests lost: client timeout -- the benchmark's own read timeout expired; the server kept serving the other streams

Prewarmed — prefix cache hot, steady-state decode:

| depth | conc | TTFT mean | per-stream tok/s | **aggregate tok/s** |
|---|---|---|---|---|
| 16,384 | 1 | 0.46 s | 34.9 | **34.9** |
| 16,384 | 8 | 3.20 s | 26.3 | **178.8** |
| 65,536 | 1 | 1.23 s | 11.8 | **11.8** |
| 65,536 | 4 | 4.76 s | 10.8 | **40.6** |

*(A prefill column is deliberately omitted here: with the cache hot it would
read 160,000–270,000 tok/s, which is cache reuse, not compute.)*

### `qwen3.8-flash-next-vllm`

Decode band: **fast** — llmband.

Cold — every stream pays its own prefill:

| depth | conc | ok | TTFT mean | TTFT p90 | prefill tok/s | per-stream tok/s | **aggregate tok/s** |
|---|---|---|---|---|---|---|---|
| 4,096 | 1 | 1/1 | 1.5 s | 1.5 s | 2688 | 56.4 | **56.4** |
| 4,096 | 8 | 8/8 | 11.6 s | 14.8 s | 2218 | 22.4 | **145.9** |
| 4,096 | 32 | 32/32 | 28.2 s | 47.6 s | 2745 | 12.6 | **297.2** |
| 16,384 | 1 | 1/1 | 6.2 s | 6.2 s | 2652 | 55.6 | **55.6** |
| 16,384 | 8 | 8/8 | 30.7 s | 48.0 s | 2732 | 17.9 | **99.8** |
| 16,384 | 16 | 16/16 | 54.9 s | 94.7 s | 2720 | 10.6 | **108.7** |
| 65,536 | 1 | 1/1 | 24.5 s | 24.5 s | 2673 | 55.3 | **55.3** |
| 65,536 | 4 | 4/4 | 64.9 s | 98.7 s | 2658 | 13.7 | **34.4** |
| 131,072 | 1 | 1/1 | 49.8 s | 49.8 s | 2633 | 56.4 | **56.4** |
| 249,856 | 1 | 1/1 | 98.8 s | 98.8 s | 2528 | 55.5 | **55.5** |

Prewarmed — prefix cache hot, steady-state decode:

| depth | conc | TTFT mean | per-stream tok/s | **aggregate tok/s** |
|---|---|---|---|---|
| 16,384 | 1 | 0.33 s | 56.9 | **56.9** |
| 16,384 | 8 | 1.96 s | 24.2 | **186.1** |
| 65,536 | 1 | 0.33 s | 56.7 | **56.7** |
| 65,536 | 4 | 0.82 s | 21.6 | **85.6** |

*(A prefill column is deliberately omitted here: with the cache hot it would
read 160,000–270,000 tok/s, which is cache reuse, not compute.)*

### `qwen3.6-27b-code`

Decode band: **fast** — llmband.

Cold — every stream pays its own prefill:

| depth | conc | ok | TTFT mean | TTFT p90 | prefill tok/s | per-stream tok/s | **aggregate tok/s** |
|---|---|---|---|---|---|---|---|
| 4,096 | 1 | 1/1 | 0.9 s | 0.9 s | 4473 | 61.1 | **61.1** |
| 4,096 | 8 | 8/8 | 7.0 s | 8.9 s | 3683 | 45.7 | **304.2** |
| 4,096 | 32 | 32/32 | 25.5 s | 45.6 s | 2779 | 17.5 | **368.9** |
| 16,384 | 1 | 1/1 | 4.0 s | 4.0 s | 4112 | 34.7 | **34.7** |
| 16,384 | 8 | 8/8 | 54.9 s | 92.4 s | 1419 | 16.6 | **64.5** |
| 16,384 | 16 | 16/16 | 147.6 s | 294.4 s | 880 | 7.4 | **46.8** |
| 16,384 | 32 | **29/32** ⚠ | 397.4 s | 1006.0 s | 416 | 1.5 | 22.5 |
| 65,536 | 1 | 1/1 | 28.4 s | 28.4 s | 2307 | 12.0 | **12.0** |
| 65,536 | 4 | 4/4 | 202.3 s | 367.7 s | 713 | 5.4 | **9.4** |

- ⚠ **16,384 × 32** — 3 of 32 requests lost: client timeout -- the benchmark's own read timeout expired; the server kept serving the other streams

Prewarmed — prefix cache hot, steady-state decode:

| depth | conc | TTFT mean | per-stream tok/s | **aggregate tok/s** |
|---|---|---|---|---|
| 16,384 | 1 | 0.47 s | 34.7 | **34.7** |
| 16,384 | 8 | 3.20 s | 26.1 | **168.0** |
| 65,536 | 1 | 1.24 s | 12.0 | **12.0** |
| 65,536 | 4 | 4.76 s | 10.5 | **37.0** |

*(A prefill column is deliberately omitted here: with the cache hot it would
read 160,000–270,000 tok/s, which is cache reuse, not compute.)*

### `qwen3.6-35b-code`

Decode band: **unclassified** — no stored reference; its conc=16 legacy figure is above the stored baseline, so not a slow draw.

Cold — every stream pays its own prefill:

| depth | conc | ok | TTFT mean | TTFT p90 | prefill tok/s | per-stream tok/s | **aggregate tok/s** |
|---|---|---|---|---|---|---|---|
| 4,096 | 1 | 1/1 | 0.4 s | 0.4 s | 11377 | 53.8 | **53.8** |
| 4,096 | 8 | 8/8 | 2.6 s | 3.0 s | 11097 | 50.7 | **327.0** |
| 4,096 | 32 | 32/32 | 8.7 s | 12.9 s | 9724 | 30.5 | **726.5** |
| 16,384 | 1 | 1/1 | 1.4 s | 1.4 s | 11944 | 32.5 | **32.5** |
| 16,384 | 8 | 8/8 | 15.6 s | 23.3 s | 5620 | 29.7 | **155.5** |
| 65,536 | 1 | 1/1 | 9.7 s | 9.7 s | 6790 | 13.2 | **13.2** |
| 65,536 | 4 | 4/4 | 93.5 s | 150.3 s | 1745 | 9.8 | **19.8** |

### `gemma4-26b-a4b`

Decode band: **unclassified** — no stored reference; its conc=16 legacy figure is above the stored baseline, so not a slow draw.

Cold — every stream pays its own prefill:

| depth | conc | ok | TTFT mean | TTFT p90 | prefill tok/s | per-stream tok/s | **aggregate tok/s** |
|---|---|---|---|---|---|---|---|
| 4,096 | 1 | 1/1 | 0.5 s | 0.5 s | 7947 | 53.9 | **53.9** |
| 4,096 | 8 | 8/8 | 4.4 s | 4.9 s | 6629 | 36.6 | **256.7** |
| 4,096 | 32 | 32/32 | 9.8 s | 16.0 s | 8177 | 20.3 | **544.0** |
| 16,384 | 1 | 1/1 | 3.9 s | 3.9 s | 4203 | 43.3 | **43.3** |
| 16,384 | 8 | 8/8 | 18.8 s | 30.8 s | 4255 | 22.8 | **133.5** |
| 65,536 | 1 | 1/1 | 45.8 s | 45.8 s | 1430 | 33.0 | **33.0** |
| 65,536 | 4 | 4/4 | 113.9 s | 182.1 s | 1440 | 13.4 | **23.5** |

## What happens to prefill as the batch widens

`prefill tok/s` is batch prompt tokens divided by the slowest TTFT in the cell,
so it is a whole-batch rate, not a per-stream budget. Measured, it splits cleanly
by whether the profile runs MTP, at 16,384 tokens cold:

| profile | MTP | conc=1 | conc=8 | conc=16 | conc=32 |
|---|---|---|---|---|---|
| `qwen3.8-27b-think` | no | 3965 | 3945 | 3937 | 3931 |
| `qwen3.8-27b-code` | yes | 4110 | 1418 | 881 | — |
| `qwen3.8-flash-next-vllm` | no | 2652 | 2732 | 2720 | — |
| `qwen3.6-27b-code` | yes | 4112 | 1419 | 880 | — |
| `qwen3.6-35b-code` | yes | 11944 | 5620 | — | — |
| `gemma4-26b-a4b` | no | 4203 | 4255 | — | — |

The non-MTP profiles hold flat as the batch widens; the MTP ones fall away. That
is the measured pattern — this table does not claim a mechanism for it.

## The short-prompt sweep, in detail

The table itself is in the [README](../README.md#benchmarks).

`qwen3.8-flash-next-vllm` is the one row to read with care, in three ways.

**Its row is a different spawn from the other six, and a flagged one.** This
profile gained `GPU_MAX_HW_QUEUES=1` on 2026-10-19 after a long-generation
matched pair found the flag worth 1.66x on it (4 concurrent 8,192-token streams:
104.0 / 104.3 unflagged against 173.0 / 171.3 / 172.3 flagged, two fresh spawns
per arm). The published row is therefore a fresh flagged spawn measured the same
day with the same harness, `llmband`-classified fast before (57.78 steps/s,
`mem_busy` 31.9%) and after (57.5, 31.7%) its sweep.

**Only one cell of this sweep moved with the flag, and it is not the headline
one.** conc=8 went from 181.5 / 154.4 / 140.1 / 140.5 / 187.4 across five
unflagged spawns -- a ~33% span, which is why earlier versions of this page told
you to read it as a band rather than a figure -- to 197.2 / 204.3 / 204.1 across
three flagged ones, a 3.5% span. So the flag appears to raise *and* stabilise
that cell, on three spawns against five. conc=16 and conc=32 did not move:
unflagged they span 222.6 / 244.5 / 251.3 and 359.1 / 390.7 / 441.5 / 451.0 /
452.9, and the published 250.6 and 459.6 sit inside both. Serial is flat either
way (55.4-55.6). An earlier version of this page said conc=16 and conc=32
"reproduce earlier readings to within 0.5%" -- that was two spawns agreeing, and
the spans above are what five show.

**Its one-stream cells are intermittently spoiled by a latency tail, and the
whole server has been seen running at half rate.** Five one-stream cells were
measured on one server: three clean, at 55.48, 55.38 and 55.37 tok/s with p90
around 3.0 s and a spread of 0.2%, and two contaminated, at 42.90 (p90 5.72 s)
and 29.6 (p90 10.21 s). The episodes last minutes and do not trend -- a clean
cell ran immediately before the 42.90 one and a normal conc=8 cell immediately
after it -- and `scripts/llmband` classified the server fast throughout.
Separately, one unflagged spawn in five came up at **23.0 tok/s** single-stream
at both 2K and 131K and 22.6 on this sweep's serial cell, served two long loads
and a full sweep at that rate, and then read 56.9 on the next probe. So the state
moves in both directions mid-process. **Neither cause is established, both are
open issues**, and they are plausibly the same one: a flip inside a cell produces
exactly the stretched-tail shape above rather than a shifted mode. Two practical
consequences. `llmband` classifying a server fast at one probe does not clear the
cell that runs minutes later, so classify after a run as well as before. And a
degraded server is only visible in the one-stream cells -- the 22.6-serial spawn
still turned in 452.9 at conc=32, near the top of the normal range.

No other profile in the sweep showed the same shape, but that is weak evidence
on its own: each got a single 8-sample one-stream cell, which is far too short to
rule out an episode that lasts minutes. What the data does support is that the
p90/mean latency ratio separates the two states cleanly -- 1.09 to 1.27 across
all six other profiles, and 1.08 to 1.10 on Flash-Next's clean cells, against
1.57 and 1.84 on its two contaminated ones. So none of the six looked
contaminated in the cell that was measured, and that ratio is the cheap check to
run on any future one-stream baseline.

### Profiles this campaign did not re-measure

The two vision profiles run on llama-server (Vulkan), not vLLM, and were
left out of the sweep. Their last figures are older and were taken
with thinking **on** and on a different vLLM-era baseline, so they are not
comparable with the tables here and are not reproduced here:

- `gemma4-26b-q8` — Q8 GGUF + mmproj, ~32 GB, the vision workhorse
- `gemma4-12b-q4` — Q4 GGUF + mmproj, ~13 GB, lightest vision option,
  co-loadable alongside any vLLM profile

Both are in `docs/models.md` with their original numbers. Gemma 4 IT turns
on extended reasoning by default; `chat_template_kwargs: {enable_thinking:
false}` does suppress `<think>` output but does not meaningfully change
their throughput (differences sit inside session noise).

## Reproducing any row

```bash
# depth x concurrency, output pinned -- the primary harness
python3 bench/depth_bench.py --model <profile> \
    --depths 16384 --concurrency 1,8,16,32 --gen 1024 --no-thinking

# add --prewarm for the steady-state (hot prefix cache) numbers

# classify the decode band BEFORE trusting any of it
scripts/llmband --model <profile>        # 0 fast / 1 slow / 2 undecided

# long-context correctness gate -- a split-KV kernel that mis-combines its
# softmax segments benchmarks perfectly while losing the context
python3 bench/needle_check.py --model <profile>
```

## Reading a live `llmpanel` peak against these tables

`llmpanel` will show a higher number than anything above, and both are
right. They are different statistics:

- the panel's **cur**/**peak** are computed from
  `vllm:generation_tokens_total` over one poll tick (1 s by default), so
  **peak** is the maximum of a few hundred one-second difference
  quotients;
- the **aggregate tok/s** column above is a run average over the whole
  decode span -- from the first stream's first token to the last
  stream's last token.

Measured on `qwen3.6-35b-code`, 2,048-token prompts, 1,024 tokens
generated per request, with the sampler running inside the benchmark
(`depth_bench.py --metrics-url`):

| conc | run average | p10 | median | p90 | peak | peak / run avg |
|---|---|---|---|---|---|---|
| 8  | 359.6 | 339 | 406 | 457 | 480 | 1.33x |
| 16 | 673.3 | 486 | 775 | 901 | 923 | 1.37x |
| 32 | 977.0 | 1138 | 1276 | 1377 | 1405 | 1.44x |

The percentiles are over the samples taken while the server was within
10% of its high-water running-request count, which is what makes the
median a steady-state figure rather than an average over ramp-in,
plateau and drain. The gap splits into two parts, both measured:

- **ramp dilution, 1.13-1.31x** -- the run-average window opens at the
  *first* stream's first token while the others are still prefilling, so
  it averages in a period that is not steady state.
- **max-of-a-noisy-derivative, 1.10-1.19x** -- the maximum of a few
  hundred one-second quotients lands on the most favourably-jittered
  sample, and is biased high even when the true rate is flat.

So quote the median when you mean "what this hardware sustains", and
the run average when you mean "how long will this batch take". A peak
alone is the least informative of the three. Both surfaces use the same
percentile convention -- nearest-rank, round-half-up, no interpolation --
so a figure read off the panel and a figure read out of a saved baseline
are directly comparable.

The split is not a constant of the hardware -- it depends on how much
of the run is ramp. The same 2,048 x 32 shape on `qwen3.6-27b-code`
dilutes harder: run average 642.3 against a saturated median of 1008
and a peak of 1105, i.e. 1.57x of ramp against only 1.10x of noise.
Deeper prompts and wider batches push it further the same way.

One consequence worth stating, because a high panel reading is easy to
mistake for an error: the refreshed `medium-256` table in the README has the
two fastest profiles averaging 1443 and 1199 tok/s over the whole run at
conc=32. A peak reading sits above a run average by both mechanisms
described here, so four-figure peaks are the normal reading for a wide
batch on this stack rather than an anomaly.

Do not convert one into the other with the 1.33-1.44x figures above.
Those came from `depth_bench` runs that launch their streams once, so
their ramp share is a property of that harness; `concurrent_bench`
pushes 128 requests through 32 slots and ramps differently. The ratio
tells you which direction the gap runs, not its size on a different
harness. Of the three statistics the peak is the least informative, so
quote the median.

Two caveats worth knowing before quoting a floor:

- a one-second tick can land on a transition and catch a single token,
  so the **low** is a sampling-boundary artifact; the **p10** is the
  trustworthy floor.
- a tick can report 32 running requests and still emit no tokens at all,
  because the engine spent that second on a prefill chunk. Those seconds
  are excluded from the decode percentiles and counted separately (7% of
  in-band ticks on the conc=32 cell above). The run average pays for
  them; the percentiles do not. That is part of the gap.

Full per-profile data and architecture notes: `docs/models.md`.
