# bench/ — benchmarking methodology

---

## Scripts

| Script | Purpose |
|--------|---------|
| `concurrent_bench.py` | Main benchmark: sweep concurrency levels, collect tok/s, TTFT, VRAM |
| `depth_bench.py` | Context-depth × concurrency matrix: streams, so prefill (TTFT) and decode are measured separately |
| `needle_check.py` | Long-context **retrieval** check: can the model still see the context it is decoding over |
| `opt_probe.py` | Targeted probe for optimization impact (before/after comparison) |
| `band_audit.py` | Checks `baselines/` for files recorded in the slow decode band (exit 1 if any) |
| `codetests/run_codetests.py` | Code-correctness suite: model writes code, hidden tests grade it (`validate` / `run` / `regrade`) |

### Depth matters, and `concurrent_bench.py` cannot see it

`concurrent_bench.py` is non-streaming, so its "decode tok/s" is `completion_tokens /
total_wall` — prefill included. At a 256-token prompt that is a rounding error; at 128K it is
most of the wall clock and the number stops being a decode rate at all. `medium-256` numbers
therefore say nothing about how the stack behaves at agent-fleet context depths, where the
spread between profiles reached **24×** (see `docs/rdna4-long-context.md`). Use
`depth_bench.py` for anything depth-related.

Three rules for `depth_bench.py`, all learned by getting them wrong:

- **Pass `--max-model-len` when going through llama-swap.** The router reports
  `max_model_len: null` for every profile, so the automatic clamp is inert and deep cells fail
  with an HTTP 400 instead of being clamped.
- **Use `--prewarm` for steady-state decode.** Without it, deep concurrent cells measure
  prefill contention, not decode: each stream pays a full unique prefill and chunked prefill
  interleaves those tokens into everyone else's decode steps. Cold 65K × conc=4 measured 181 s
  TTFT against 13.7 s of serial end-to-end. Both regimes are real; the header line says which
  one ran, and an unlabelled number between them is worthless.
- **A default cell has no arrivals, and that is a best case for some kernels.** Without
  `--requests`, the harness launches exactly `conc` streams once and waits: nothing enters
  mid-run. Real fleets arrive continuously, and that can matter to the kernel, not just to
  the queue: TRITON_ATTN picks its 3D split-KV path per *batch*, so one newcomer's prefill
  chunk drops every co-batched decoder to the 2D grid (`docs/rdna4-long-context.md`, gate
  4). Pass `--requests N` (N > conc) to measure the churn regime, and say which regime a
  figure came from — a no-arrival depth number is a kernel ceiling, not a fleet throughput.
  **Depth under churn is still unmeasured here**, so the 1.4-28x figures in
  `docs/rdna4-long-context.md` are ceilings and must not be quoted as fleet numbers.

### Never compare two runs at different `--requests`

A conc=8 reading moves by up to a third with the request count alone, no config change
involved. Measured 2026-10-19, same profile and same flag either side:

| profile | n=32 | n=128 | shift |
|---------|------|-------|-------|
| `qwen3.6-35b-code` | 250.1 | 298.4 | +19% |
| `qwen3.6-35b-128k-nomtp` | 347.9 | 458.3 | +32% |
| `gemma4-26b-a4b` | 522.1 | 543.3 | +4% |

32 requests through 8 slots is a ~12 s run, and ramp-up and drain are most of it. That is
large enough to invent a result: a 19% "cost" was attributed to TRITON_ATTN on this very
profile from one n=32 run per arm. Re-run matched — one fresh spawn per arm, 3 bench reps
against each live server, `--requests 128`, `--serial-n 8`, the backend flag the only variable
— the sign flips and TRITON wins every level:

| cell | ROCM_ATTN (3 reps) | TRITON_ATTN (3 reps) | T/R |
|---|---|---|---|
| serial (n=8) | 87.9 / 88.1 / 88.3 | 91.5 / 91.5 / 91.6 | +3.9% |
| conc=8 (n=128) | 445.5 / 446.7 / 446.7 | 464.1 / 463.9 / 461.3 | +3.9% |
| conc=32 (n=128) | 1180.2 / 1187.3 / 1174.1 | 1208.6 / 1226.1 / 1203.5 | +2.4% |

Note the spreads: against one live server, reps land within 0.6% at conc=8 and 1.9% at
conc=32. Run-to-run noise was never the problem — the request count was. So fix the count
before comparing anything, prefer n=128 for any number that will be published, and run more
than one rep so the spread is visible rather than assumed.

**Two reps per arm is the floor for any A/B.** Both arms of that test were single runs when it
first went in, which is how a 19% artifact reached three documents and a profile comment.

### Retrieval check — mandatory for any attention or kernel change

`depth_bench.py` sends filler with `ignore_eos` and never reads the reply. A split-KV decode
kernel that combines its softmax segments incorrectly loses whole stretches of context and
**still benchmarks perfectly**. Speed at depth is worthless if the model can no longer see the
depth.

```bash
python3 bench/needle_check.py --model qwen3.8-27b-think --no-thinking \
    --depths 16384,65536,131072 --positions 0.05,0.25,0.5,0.75,0.95 \
    --max-model-len 131072
```

It sweeps the needle's **position** as well as the depth, because position is the discriminator
for this bug class: vLLM's TRITON_ATTN 3D path splits the context into 16 softmax segments, so
a needle at 30% depth and one at 70% land in different segments. A uniform failure means
retrieval is broken; failures clustered at particular positions mean the segment reduction is.
Exit status is 0 only if every cell retrieved its needle. Run it against the shipped profile
as a reference and against the candidate, with the same `--seed` so the needles are identical.

---

## Code-correctness tests (`codetests/`)

Throughput numbers say nothing about whether a model still writes correct code under a new quantisation, image
or sampling setting. `codetests/` has 11 tasks, each with a prompt, a hidden test file and a reference solution.
Six are the original set (saturated: current models pass nearly all); five are harder (`regex_engine`,
`json_strict`, `cron_next`, `mini_scheme`, `date_math`).

```bash
python3 bench/codetests/run_codetests.py validate     # reference solutions must score 100%, controls 0%
python3 bench/codetests/run_codetests.py run --url http://127.0.0.1:8080/v1/chat/completions \
  --model qwen3.8-flash-next-vllm --modes think --reasoning-effort medium --samples 4 \
  --max-tokens 81920 --timeout 7200 --tasks regex_engine,mini_scheme,date_math,json_strict \
  --out bench/results/codetests-<topic>-$(date +%Y%m%d)/<profile>
```

Rules learned the hard way (details in `docs/hard-code-tasks.md`):
- Use a generation cap of 64K-96K for the hard tasks; at 32K Flash-Next truncates and the zeros measure the cap.
- 4 samples per cell is small: read differences under ~15 points as noise.
- A `finish_reason=stop` with empty content is a premature end-of-turn from the model, not a test failure; count
  it separately (the 27B does this at a rate that rises with temperature). The runner now does: the summary's
  "early stops (empty/cut)" column counts replies that were empty or ended inside an unterminated code fence,
  and each row carries `early_stop`. `regrade` fills it in for older saved runs.
- `--thinking-budget` only helps if cap minus budget still covers the answer.
- Save per-sample results (the runner does) so every score can be audited or re-graded with `regrade`.

### Quality gate for canaries (new checkpoint, image, kernel or quantisation)

Speed is not a result if output quality drops. Before a canary gets throughput numbers, a tool-call check or
a profile, run the hard code tasks (`mini_scheme`, `regex_engine`, plus `json_strict` and `date_math`) against
the current profile as a baseline and against the candidate under identical settings (same reasoning effort,
cap of at least 64K, same samples per cell, exact all-reduce where an image offers a lossy one). Stop the canary
when either holds:
- a task's mean tests passed falls by more than the noise (15 points at 4 samples, ~10 at 8), or
- more than a handful of samples end early (the "early stops" column), or run to the cap with empty content.

Before blaming the model, also run the checkpoint's own published recipe verbatim (its flags, sampling and
env). If that fails the same way, the cause is the checkpoint or the image, not our config. Precedent:
the 2026-10-15 MXFP4 Flash-Next canary was ~2x faster but scored 5-14% vs 50-54% on the two hardest tasks,
with the model's own recipe failing the same way, so it was not adopted.

### Canary checklist

1. Baseline the shipped profile on the same prompts and settings first.
2. Run the quality gate above before any throughput work.
2b. For an attention-backend, kernel or block-size change, also run `needle_check.py` against
   both arms with the same `--seed`. A split-KV kernel can be fast and wrong at the same time,
   and no throughput number will tell you.
3. Run the model card's own recipe verbatim, as a config-vs-model check.
4. Long-context stress: ~7 concurrent unique ~100K-token prompts (~690K tokens total) must all finish, with
   no timeouts, under the profile's real `--gpu-memory-utilization`. This is what separates 0.95 from 0.97.
   **Record the decode rate during the run, not just that nothing timed out.** "Everything finished" is
   compatible with every request having run on the slow kernel path the whole time: `use_3d` is decided per
   batch from a batch-wide `max_query_len`, so a step carrying a prefill chunk drops the decoders beside it
   to the 2D grid (`docs/rdna4-long-context.md`, gate 4). Unique prompts mean continuous real prefill, which
   is exactly the regime a `--prewarm` matrix does not measure.
5. Keep throwaway routers and containers on a separate port and name, and leave the shipped profile untouched
   until every step passes.

---

## Harness traps

Each of these produced a wrong number or a wasted run here at least once.

### `--url` is the FULL endpoint, not a base

`DEFAULT_URL` in `depth_bench.py` and `concurrent_bench.py` is
`http://127.0.0.1:8080/v1/chat/completions`. Passing `--url http://host:8080/v1`
makes every POST a 404 and the whole sweep reports zero completions, which
looks exactly like a dead backend.

### `--run-nonce` is mandatory on a re-run

Without it a second run sends byte-identical prompts, the prefix cache answers
them, and the prefill figure measures cache reuse. A 32K cell re-run warm
reported 41,463 prompt tok/s against a true ~4,300 -- a 10x overstatement that
looks like a breakthrough. Pass a fresh `--run-nonce` for every run against a
server that has already seen traffic.

### Any prefill figure from a prewarmed cell is cache reuse

`--prewarm` populates the prefix cache on purpose, so the prefill rate in a
prewarmed row is not a compute rate and must never be published as one.
160K-267K tok/s figures are the tell. `report_full_table.py` prints `cached`
in that column rather than a number.

### `prefill_tok_s` is a whole-batch rate

It is batch prompt tokens divided by the slowest stream's TTFT. It is not a
per-stream speed and is not comparable with decode tok/s. At conc=32 it will
look enormous beside a decode figure; they are different denominators.

### llama-swap does not proxy `/metrics`

Port 8080 returns nothing for `vllm:*`. The backend's own port must be
scraped, and it is assigned dynamically (9104, 9106, ... depending on what has
been loaded since the router started). Discover it:

```bash
ps -eo args | grep -a 'vllm serve' | grep -oE -- '--port [0-9]+'
```

`depth_bench.py --metrics-url http://127.0.0.1:<port>/metrics` then samples
`vllm:generation_tokens_total` once a second and reports the distribution
alongside the run average.

### `llmctl swap <P>` is a no-op when P is already loaded

If the profile is already up and its pid 1 is alive, swap returns success
without restarting anything. A config change you just made is therefore NOT in
effect, and an A/B comparing two configs silently measures one of them twice.
`llmctl unload` first, then swap, then assert the container Id actually
changed:

```bash
before=$(podman ps --filter name=llmstack-vllm-<P> -q | head -1)
llmctl unload && llmctl swap <P>
after=$(podman ps --filter name=llmstack-vllm-<P> -q | head -1)
[ "$after" != "$before" ] || echo "swap was a no-op -- the old container is still serving"
```

After editing `config/models.yaml`, `llmctl down && llmctl up` as well: the
router reads the config at startup.

### `No available shared memory broadcast block` is not a death signature

vLLM prints it on any stall over 60 s, including a cold start and a long
prefill queue. A watchdog that treats it as a crash will kill healthy runs.
The patterns that do mean the engine is gone:

```
torch\.OutOfMemoryError|Tried to allocate|EngineDeadError|RPC call to [a-z_]+ timed out
```

### `llmband` exit 2 usually means "no baseline", not "slow"

`config/band-baselines.json` covers only a few profiles. For an uncalibrated
one the detector cannot decide and exits 2, with the reason on stdout -- read
it before concluding a spawn was slow. Calibrate with `--calibrate` against a
server you have reason to believe is fast.

### A deep, wide cell that reports nothing may be a queue, not a failure

16,384 tokens x 32 streams on a 27B produced a ~17-minute prefill backlog and
three client-side read timeouts. The server was serving the whole time. Check
`num_requests_waiting_by_reason{reason="capacity"}` -- a non-zero value means
the KV budget admits fewer streams than you asked for, so the extra streams
wait rather than run.

### Classify the band BEFORE the sweep, with `concurrent_bench` at `medium-256`

A gfx1201 server's decode band is drawn when it spawns (`docs/rdna4-decode-bands.md`), so
every absolute figure a run produces belongs to whichever band that spawn landed in. A
sweep that does not state its band is not a measurement.

**A depth sweep cannot classify its own band.** `depth_bench.py` is the wrong instrument for
it, for a reason that has nothing to do with the script: there is no stored reference taken
with it to compare against. Band classification is a comparison, so it has to be run on the
harness and prompt that the references use — `concurrent_bench.py --prompt medium-256`,
which is what every file in `bench/baselines/` holds.

This cost a full nine-cell grid on `qwen3.6-35b-128k-nomtp`. Run first, unclassified, it
read 26.6 tok/s at 2,048 tokens falling to 3.6 at 65,536, and that 7.4x looked like a
long-context collapse worth a large fix. A `medium-256` check afterwards read 30.7 tok/s
serial against a stored 88.3 — the spawn was in the slow band, and the whole grid was a
record of one bad draw. The matched fast spawn reads 59.2 and 4.6 in those cells.

So, in order:

```bash
# 1. the band check -- comparable with bench/baselines/ and with llmband
python3 bench/concurrent_bench.py --model <P> --prompt medium-256 --sweep 1,8 --no-thinking
# 2. only if it matches the stored figure, the thing you actually wanted
python3 bench/depth_bench.py --model <P> --depths ... --concurrency ...
```

`scripts/llmband` is the cheaper check and should be preferred — but it only covers the few
profiles in `config/band-baselines.json`, and for anything else it exits 2 (see above). For
an uncalibrated profile the `medium-256` sweep against its stored baseline is the fallback,
and it is also how to decide a spawn is fast enough to calibrate `llmband` from.

One trap inside the trap: **the band ratio is not constant across the sweep.** On the 35B
MoE it was 2.87x serial, 2.07x at conc=8, and only 1.10x at 65,536 x 4 — the penalty is a
fixed per-step tax, so it amortises with batch width and shrinks against the longer steps a
deep context produces. A band check at one cell does not transfer to another, and a slow-band
ratio must never be quoted as a speedup for a fix measured in the fast band.

### Part of the stored corpus was recorded in the slow band — audit before quoting

`-e GPU_MAX_HW_QUEUES=1` shipped on 2026-10-18. Every baseline taken before that was a stock
spawn, so some of `baselines/` records the slow band, and a figure copied out of one of those
files into a doc or a README understates the hardware by up to ~2x at one stream. This is the
answer to "why do the published numbers look slower than what the GPUs actually do".

```bash
python3 bench/band_audit.py          # exit 1 if any file needs attention
python3 bench/band_audit.py --quiet  # just those files
```

Two confirmed, both arms of the 2026-10-05 Qwen3.8-vs-3.6 comparison:

| file | one-stream | conc=8 |
|---|---|---|
| `qwen3.6-27b-code-v0.26.0-nothink-20261005.json` | 1.92x down | 1.11x down |
| `qwen3.8-27b-code-v0.26.0-nothink-20261005.json` | 1.90x down | 1.17x down |
| the 27B band curve, for comparison | 1.89x | 1.11x |

Because *both* arms were slow, that comparison's relative verdict ("throughput equal") still
holds — but every absolute number in it is a slow-band figure.

Three things the audit cannot do, so do not over-read it:

- **The curve does not name the cause.** Any fixed per-step overhead is largest at one stream
  and amortises with batch width. vLLM 0.31.0's Model Runner V2 draws the same shape (~45% at
  one stream, nothing by conc=2-4), which is why the 0.31.0 files are flagged too — there the
  cause is known and is not the band (`docs/upgrade-plan-2026-10.md`). A flag means "read the
  provenance", not "this was the band".
- **It needs a comparable peer**, which means the same profile, the same image pin and
  no-thinking on both sides. Thinking inflates tok/s, so a thinking-on file is a different
  measurement: comparing this October's no-thinking 35B sweep against `qwen3.6-35b-code.json`
  (2026-05, thinking on) manufactured a 2.2x shortfall that was entirely the thinking block.
  **Put the image pin in every baseline filename** or the file can never be audited.
- **It cannot clear a profile with only one reading.** Those are listed as `unaudited`, and
  that is the honest state, not a pass.

#### Provenance for the 2026-10-19 matched set

The seven `*-peak-nothink-matched-20261019.json` files are the published `medium-256` table in
`README.md` and the root `CLAUDE.md`. Each is one fresh spawn on the shipped config, classified
with `scripts/llmband` before it was benchmarked, 128 requests per level. Six come back as their
profile's reference on their pin. Two notes:

- **`qwen3.6-35b-128k-nomtp` reads `unaudited`** -- it is the first `medium-256` baseline for
  that profile on this pin, so the audit has no peer and correctly says nothing. Its
  91.8 serial / 457.0 conc=8 land within 1% of the TRITON arm of the attention-backend matched
  pair, which is the closest thing to a peer that exists.
- **`qwen3.8-flash-next-vllm` carries a `PER-STEP` flag that is *not* the band.** Its
  one-stream cell is defective: that profile has an intermittent multi-minute single-stream
  latency tail (`docs/models.md`), and this cell caught one -- 29.6 tok/s at a p90 of 10.21 s,
  against 55.4 at a p90 of ~3.0 s from three clean cells on the same server. `llmband`
  classified that server **fast** throughout, so the flag is reading the tail, not a slow draw.
  The published serial figure for this profile comes from the two
  `*-serial-recheck-rep{1,2}-nothink-20261019.json` files, not from the matched file. Its
  conc=8/16/32 cells are sound and are the published ones.

  Do not read `rep2`'s `ok (1.29x of fastest)` as a clean bill of health. `one_stream()` prefers
  a `conc=1` cell over a `serial` one, and `rep2`'s `conc=1` cell is the contaminated 42.90
  reading — it clears only because 1.29 happens to fall under the 1.30 threshold. `rep2`'s
  *serial* cell is clean at 55.37. The audit has no notion of a spoiled cell, so on this profile
  check the p90/mean latency ratio as well: clean one-stream cells here read 1.08-1.10 and
  contaminated ones 1.57-1.84, while the six other profiles in the matched set read 1.09-1.27.

### Report a distribution, not a peak

`llmpanel` reports the maximum of one-second difference quotients; the
benchmark reports a run average over the whole decode span. On the same cell
those differ by up to 1.44x, and neither is wrong. Quote the saturated median
for "what the hardware sustains", the run average for "how long the batch
takes", and the p10 for the floor -- the `low` is a sampling-boundary artifact
and a single tick can catch one token. Both surfaces use nearest-rank,
round-half-up, no interpolation, so their figures are comparable. See the
README's "Reading a live `llmpanel` peak" section and
`docs/benchmark-results-full.md`.

---

## Standard invocation

### Full sweep (save as baseline)

```bash
python3 bench/concurrent_bench.py \
  --model qwen3.8-27b-code \
  --url http://127.0.0.1:8080/v1/chat/completions \
  --sweep 1,2,4,8,16 \
  --prompt all \
  --no-thinking \
  --requests 16 \
  --save bench/baselines/qwen3.8-27b-code-v0.26.0-nothink.json
```

### Quick sanity check

```bash
python3 bench/concurrent_bench.py \
  --model qwen3.8-27b-code \
  --no-thinking
```

### Compare two baselines

```bash
python3 bench/concurrent_bench.py \
  --compare bench/baselines/old.json bench/baselines/new.json
```

---

## Rules for clean comparisons

### Always use `--no-thinking`

Thinking models generate many reasoning tokens that inflate tok/s numbers.
Without `--no-thinking`, Qwen3.6 emits a `<think>...</think>` block before
the actual answer. This:
- Inflates "output tokens" counted toward tok/s
- Makes the number useless for comparing models/configs against each other
- Was the root cause of the misleading v0.20.0 "485 tok/s" benchmark (thinking ON)

**For Qwen3 and other models where thinking is explicitly suppressible:**
every baseline file in `bench/baselines/` must be no-thinking.
The filename should include `-nothink` or `-no-thinking` if there is any ambiguity.

**Gemma 4 IT dual-baseline convention:**

Gemma 4 IT activates thinking by default, but `chat_template_kwargs: {enable_thinking: false}`
is confirmed effective at suppressing `<think>` output (spot-checked 2026-06-18 on all
three Gemma 4 profiles — responses to "What is 2+2?" were direct answers with no think
block, 0 errors across all prompt sizes).

However, no-thinking does NOT improve throughput for Gemma 4 models — measured differences
are within session-to-session noise (~0–6%). This means the original thinking-on baselines
remain the best representation of real-world default behaviour.

For Gemma 4 models, keep **both** baselines:

- **thinking-on baseline** (date only): reflects default real-world behaviour; the numbers
  used in comparison tables and the README.
  Example: `gemma4-26b-q8-20260613.json`

- **no-thinking baseline** (-nothink suffix): clean apples-to-apples comparison against
  Qwen3 and other no-thinking models.
  Example: `gemma4-26b-q8-nothink-20260618.json`

When comparing Gemma 4 against other models, use the no-thinking baseline for fairness.
When reporting Gemma 4 headline numbers in user-facing docs, the thinking-on baseline is
appropriate since that is what users get by default.

### Do NOT cap `max_tokens` at 256

Setting `--max-tokens 256` causes thinking models to hit the limit mid-think
and truncate, returning zero actual content tokens. The metric looks the same
(256 tokens output) but the quality is garbage and the number is meaningless.
Let the model generate freely.

### Use `--requests 16` minimum per concurrency level

Fewer requests means the measurement is noisy. 16 requests at each concurrency
level gives stable statistics. 32 is better for publication-quality comparisons.

### Note what's different in the filename

```
qwen3.8-27b-code-v0.26.0-nothink.json     ← good
qwen3.8-27b-code.json                      ← ambiguous
```

The image pin is not optional. `band_audit.py` only compares files within one profile *and*
one pin — comparing across pins would report a version regression as a slow-band draw — so a
baseline whose name omits the pin can never be audited. Six files committed on 2026-10-19 had
to be renamed for exactly this reason, and the rename is what revealed that the 2026-10-05
`qwen3.6-27b-code` baseline was a slow-band record. Flash-Next's pin is its nightly SHA
(`-nightly-8cbd5d0-`).

---

## Prompt sizes

| Key | Prompt length | Typical use |
|-----|--------------|-------------|
| `short-64` | ~64 tokens | Quick command/question |
| `medium-256` | ~256 tokens | Normal coding task |
| `long-512` | ~512 tokens | Complex function/class |
| `xlarge-2048` | ~2048 tokens | Multi-file analysis |

`--prompt all` runs all four. `--prompt medium-256` runs one.
`medium-256` is the standard comparison prompt — use it for headline numbers.

---

## Interpreting results

| Metric | What it means | Target |
|--------|-------------|--------|
| `tok/s` (decode) | Output tokens per second across all concurrent requests | Higher is better |
| TTFT | Time to first token (ms) | Lower is better; ≤2000 ms at conc=8 is good |
| P90 latency | 90th percentile request latency (s) | Depends on use case |
| conc=1 | Serial throughput — effective speed per single request | |
| conc=8 | Primary throughput metric — typical concurrent agent load | |
| conc=16 | Peak concurrent load | |

**MTP effect:** Multi-Token Prediction boosts tok/s mainly at conc ≥ 4. At conc=1,
MTP overhead can slightly reduce serial tok/s if the draft hit rate is low.

**Expected baselines for `qwen3.8-27b-code` (medium-256, vLLM 0.26.0, no-thinking, MTP, 32 req/level):**

| conc | tok/s |
|------|-------|
| 1    | 66    |
| 2    | 113   |
| 4    | 194   |
| 8    | 361   |
| 16   | 549   |

If conc=8 drops below ~300 tok/s, something is wrong — check VRAM, container
restart, or whether CUDA graph capture ran correctly.

**Important:** conc=8 and conc=16 numbers are only meaningful with `--requests 32`
(the default). Using `--requests-per-level 3` with `--sweep` never fills the
concurrency slots and shows false plateaus at conc≥4.

---

## Baseline file naming convention

```
bench/baselines/<profile-id>-<version>[-<variant>].json
```

Examples:
```
qwen3.8-27b-code-v0.26.0-nothink.json      ← main baseline
qwen3.6-35b-code-v0.22.1-nothink.json      ← previous-generation reference
qwen3.6-35b-awq-v0.20.0-nothink.json       ← archived profile, kept for history
```

Commit new baselines alongside the config or code change that motivated them.
Commit message should include the headline numbers, e.g.:
```
bench: add qwen3.8-27b-code vLLM 0.26.0 baseline (conc=8: 361 tok/s)
```

---

## When to benchmark

- After adding a new profile (establish baseline)
- After changing `--max-num-seqs`, `--gpu-memory-utilization`, or `--cudagraph-capture-sizes`
- After upgrading vLLM (compare against previous version baseline)
- After enabling/disabling MTP (the delta reveals its real contribution)
- When investigating a user-reported slowness

Do NOT benchmark during a vLLM cold start (first boot) — CUDA graph capture and FP8 KV
calibration are running concurrently and will skew results. Wait for
"Application startup complete." in the container log before starting a benchmark.
