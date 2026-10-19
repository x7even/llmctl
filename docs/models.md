# llmstack model registry — reference

All profiles are defined in `config/models.yaml` and routed by llama-swap based
on the OpenAI `model` field. This document explains each profile's purpose,
configuration rationale, and benchmark data.

---

## Hardware context

4× AMD Radeon AI PRO R9700 (gfx1201 / RDNA4), 32 GB VRAM each → 128 GB total.
No screen; GPU-only headless rig. PCIe 5.0 ×16 per slot.

---

## Backend images

| Image | vLLM | ROCm | Use when |
|---|---|---|---|
| `docker.io/vllm/vllm-openai-rocm:v0.26.0` | 0.26.0+rocm723 | 7.2.3 | All vLLM profiles (FP8, AWQ, safetensors) |
| `localhost/llmstack-llama:latest` | llama.cpp | Vulkan | GGUF models |

All vLLM profiles use `--entrypoint="" ... vllm serve` because the AMD official
image has `ENTRYPOINT ["vllm", "serve"]` — omitting the explicit `vllm serve`
prefix results in `vllm serve serve /models/...` which fails.

### vLLM cold start time

First boot per machine compiles Inductor kernels and calibrates FP8 KV cache:

| Phase | Time | Cached? |
|---|---|---|
| Inductor torch.compile (4 TP ranks) | ~14 min | Yes — `.vllm-cache/torch_compile_cache/` |
| CUDA graph capture (6 batch sizes) | ~13 s | No — re-runs each start |
| **Total first boot** | **~18–20 min** | |
| **Total subsequent boots** | **~2–3 min** | |

The compilation cache is mounted via `-v .vllm-cache:/root/.cache/vllm` and
`-v .triton-cache:/root/.triton/cache`. After the first start these directories
are populated and subsequent starts skip the Inductor compilation entirely.

`healthCheckTimeout` is set to 1200 s — sufficient for warm starts and the ~800 s FP8
KV calibration that runs on every cold start. On a fresh machine (empty cache), manually
run `llmctl logs <profile>` and wait for "Application startup complete." before the first use.

---

## Profiles

The per-profile tables below are the headline figures. Every measured cell —
prefill and decode in one row, cold and prewarmed kept apart, with the
steady-state decode distribution — is generated into
`docs/benchmark-results-full.md` by `bench/report_full_table.py`.

### Qwen3.8-27B FP8 — the default family (`qwen3.8-27b-code` / `-think` / `-fast`)

Official `Qwen/Qwen3.8-27B-FP8` (Apache 2.0, 30.9 GB including the bundled MTP head).
Dense 27B, 262 144 native context (served at 131 072), vision-capable, tool calls via the
`qwen3_xml` parser, reasoning via the `qwen3` parser. One checkpoint, three profiles:

| Profile | MTP | Thinking default | Use for |
|---|---|---|---|
| `qwen3.8-27b-code` | yes (2 draft tokens) | on, `reasoning_effort=medium` | interactive coding, Claude Code / OpenCode |
| `qwen3.8-27b-think` | no | on, `reasoning_effort=medium` | many parallel agents (no draft/verify overhead) |
| `qwen3.8-27b-fast` | yes | off (`enable_thinking=false`) | quick answers, bulk and batch work |

Per-profile defaults are set server-side with `--default-chat-template-kwargs`; any request can
override them with its own `chat_template_kwargs` (the request wins). The model's own template
default is `reasoning_effort=xhigh`, which produces very long or runaway think blocks, so the thinking
profiles default to `medium` (finishes typical code tasks in roughly 2–8k tokens).

Decode throughput, `medium-256`, `--no-thinking`, 32 requests per level, vLLM 0.26.0, MTP on:

| serial | conc=1 | conc=2 | conc=4 | conc=8 | conc=16 |
|---|---|---|---|---|---|
| 66 | 66 | 113 | 194 | 361 | 549 |

Comparison against Qwen3.6-27B: `bench/benchmark-qwen3.8-vs-3.6-27b-2026-10-05.md`
(throughput is equal; Qwen3.8 was weaker on the expression-evaluator task).

### Qwen3.6-35B — retained previous generation (`qwen3.6-35b-code`, `-128k-nomtp`, `-fast`)

Three Qwen3.6-35B-A3B FP8 MoE profiles stay in `config/models.yaml` as a reference set: MTP +
thinking (`-code`), thinking without MTP (`-128k-nomtp`), and thinking off (`-fast`). The sections
below describe them in detail.

### `qwen3.6-35b-code` — primary coding assistant

**Aliases:** `qwen3.6`, `qwen3.6-35b`, `qwen3.6-35b-fp8`

**Use for:** Claude Code, OpenCode, agentic multi-step coding, any task where
output quality matters more than raw latency.

**Key settings:**
- `--speculative-config '{"method": "mtp", "num_speculative_tokens": 2}'` — Multi-Token
  Prediction using the bundled `mtp.safetensors` draft head. Lossless: main model
  verifies every proposed token. Gains are largest at higher concurrency where
  batch decoding amortises verification cost.
- `--kv-cache-dtype fp8` — KV values stored in FP8; reduces VRAM per token,
  enabling larger effective batch sizes.
- `--enable-expert-parallel` — MoE experts distributed across GPUs for better
  utilisation with TP=4.
- `--reasoning-parser qwen3` — strips `<think>…</think>` from `content` and
  exposes it in the response's reasoning field. Thinking is ON by default (Qwen3.6 native).
  **Field name changed in vLLM 0.24.0:** responses now carry `message.reasoning`
  (streaming: `delta.reasoning`); vLLM ≤0.22.x used `message.reasoning_content`.
  Clients parsing the old field silently get nothing — check both, prefer the new name.
- `--enable-prefix-caching` — caches common prompt prefixes across requests.
  Agentic workflows with shared system prompts see 2–3× effective throughput gain.
- `--cudagraph-capture-sizes 1 2 4 8 16 32` — explicit graph sizes instead of
  the default ~2000. Cuts graph capture from ~14 min to 13 s with no throughput
  loss at practical concurrency levels (batches > 32 fall back to eager).
- Context: 262,144 tokens (native hybrid linear+full attention)

**Benchmark — vLLM 0.22.1, no-thinking, no-MTP (2026-06-06):**

> **Note:** These figures were measured *before* MTP was added to this profile. MTP has
> since been enabled via `--speculative-config`. A fresh conc=8 baseline with MTP active
> is pending. The numbers below reflect the pre-MTP FP8 baseline.

| Prompt | serial | conc=2 | conc=4 | conc=8 | conc=16 |
|--------|--------|--------|--------|--------|---------|
| short-64    | 38 | 56  | 90  | **208** | 347 |
| medium-256  | 43 | 77  | 145 | **261** | 481 |
| long-512    | 47 | 82  | 155 | **274** | 507 |
| xlarge-2048 | 43 | 81  | 155 | **335** | 651 |

Decode tok/s. p90 latency at conc=8: ~5 s (medium), ~12 s (long), ~49 s (xlarge).

**Comparison across configurations (medium-256, conc=8):**

| Config | decode tok/s |
|--------|-------------|
| vLLM 0.20.0 + MTP + thinking | 485 |
| vLLM 0.20.0 no-MTP no-thinking | 222 |
| vLLM 0.22.1 no-MTP no-thinking | **261** |
| AWQ Int4 no-MTP no-thinking | 250 |

The 0.20.0 thinking number is not directly comparable (thinking tokens inflate
measured throughput). The 0.22.1 and AWQ no-thinking numbers are clean comparisons.
The 261 figure is the pre-MTP baseline; a fresh conc=8 run with MTP enabled is pending.

---

### `qwen3.6-35b-128k-nomtp` — the deep-context profile

**Aliases:** `35b-nomtp`

Same FP8 checkpoint as `-code`, no speculative decoding, `--max-model-len 131072`, TP4 with
expert parallelism. Carries two load-bearing flags: `-e GPU_MAX_HW_QUEUES=1` and
`--attention-backend TRITON_ATTN`. Without MTP every decode step has `query_len=1`, which is
what keeps TRITON_ATTN's 3D split-KV path open — the only kernel on gfx1201 that parallelises
over context length.

**This is the fastest deep-context profile in the stack.** Measured 2026-10-19, both arms
fast-band, one variable, `--no-thinking`, gen 128, aggregate tok/s (per-stream in brackets):

| depth × streams | ROCM_ATTN (auto) | TRITON_ATTN (shipped) | ratio |
|---|---|---|---|
| 2,048 × 1 | 59.2 | 97.1 | 1.64× |
| 2,048 × 8 | 341.3 [44.1] | 469.5 [61.5] | 1.38× |
| 16,384 × 1 | 18.4 | 91.5 | 4.97× |
| 16,384 × 8 | 106.9 [15.6] | 300.7 [50.1] | 2.81× |
| 16,384 × 8 *prewarmed* | 131.9 [16.6] | **439.8** [55.4] | 3.33× |
| 65,536 × 1 | 4.6 | 76.3 | 16.6× |
| 65,536 × 4 | 16.1 [4.8] | 108.4 [45.9] | 6.73× |
| 65,536 × 4 *prewarmed* | 20.7 [5.2] | **231.1** [58.3] | 11.2× |
| 129,984 × 1 | 2.2 | **62.4** | 28.4× |

Decay across the whole window is **1.56×** (97.1 at 2K → 62.4 at 130K) where ROCM_ATTN decays
26.9×. At 130K on one stream it serves 62.4 tok/s against `qwen3.8-27b-think`'s 33.4 — the
expected direction for 3B active parameters against 27B dense, now measured. Prefill improves
too: TTFT at 65,536 × 4 falls 55.21 s → 23.77 s (2.32×), at 16,384 × 8 11.73 → 7.72 s.

Retrieval is gated, not assumed: `bench/needle_check.py`, 3 depths (16K/64K/130K) × 5 needle
positions, **15/15**. A split-KV kernel that mis-combines its softmax segments benchmarks
perfectly while silently losing context, so this gate runs on every attention change.

**What it costs at short prompts: nothing measurable.** An earlier version of this entry said
the profile was 19% slower than `-code`'s configuration at `medium-256` conc=8 (347.9 vs
431.1). That is withdrawn: both figures were single runs at `--requests 32`, and the request
count alone moves a conc=8 reading by +4% to +32% here. Re-measured as a matched pair (fresh
spawn per arm, 3 reps, `--requests 128`, `--serial-n 8`, `--attention-backend` the single
variable), TRITON_ATTN is **faster** at every level — serial 91.5 vs 88.1, conc=8 463.9 vs
446.7, conc=32 1208.6 vs 1180.2 — with non-overlapping spreads and verified KV-pool parity.

So route to this profile on depth, not away from it on burstiness. The caveat that survives is
about quoting: the depth grid above launched exactly `conc` streams once, so it is a no-arrival
best case, and gate 4 (the 3D predicate is evaluated per *batch*) means a co-batched prefill
chunk still drops deep decoders to the 2D grid — how much that costs at depth is unmeasured.
Keep `--max-num-seqs` at 32 — above the nearest CUDA-graph capture size the 3D path closes
with nothing in the log. Full write-up: `docs/rdna4-long-context.md`.

---

### `qwen3.6-35b-fast` — low-latency general use

**Aliases:** `qwen3.6-fast`, `qwen3.6-nothin`

**Use for:** Quick lookups, chat, summarisation, tasks where TTFT matters and
extended reasoning is unnecessary overhead.

**Key differences from code profile:**
- Thinking **OFF** by default via custom template `config/templates/qwen3.6-no-think.jinja`.
  The template inverts the default condition — thinking only activates if the client
  explicitly passes `chat_template_kwargs: {"enable_thinking": true}`.
- `--gpu-memory-utilization 0.97` — no MTP draft head; reclaims headroom for KV cache.
- No MTP — removes speculative decoding overhead. At conc=1 with short tasks, MTP
  verification cost slightly hurts throughput when draft hit rate is low.

---

### `qwen3.8-flash-next-vllm` — Flash-Next for concurrent agents

**Aliases:** `flash-next-vllm`

**Use for:** the same model as `qwen3.8-flash-next` (125B MoE, 6B active) when more than
one agent is running. llama-server layer-splits across GPUs, so only one GPU works at a
time and 4 streams drop to ~8.5 tok/s each; TP4 + expert-parallel keeps all four busy.

**Setup:**
- Checkpoint: `albucino/Qwen3.8-Flash-Next-W4A16-FP8PLE` (121 GB): AutoRound INT4 (W4A16)
  transformer, FP8 per-layer-embedding (PLE) table. Not a full-FP8 model.
- Image: **nightly** `vllm-openai-rocm:nightly-8cbd5d03006c33185f402249ff2b448efd594986`
  (vLLM 0.31.1rc1.dev173). `v0.31.0` rejects the compressed-tensors PLE table.
  Move to a tagged release when one carries the same support.
- TP4 + `--enable-expert-parallel`, `VLLM_ROCM_USE_AITER=0` (Triton MoE path; no AITER
  path for `Qwen4Exp`). No EP crash with INT4 MoE, unlike the AWQ case in `config/CLAUDE.md`.
- The FP8 PLE table (47.7 GiB) is CPU-offloaded into pinned host RAM (~96 GB of host RAM is
  needed in total; workers measure 16-21 GiB of anonymous host memory each). It is pinned by
  the HIP pinned-host allocator (engine log `pinned=True`), not `mlock`, so the profile's
  `--ulimit memlock=-1:-1` is inert under rootless podman: the hard limit stays ~23.5 GiB
  (`ulimit -Hl` inside the container) with or without it, and speed and behaviour are identical
  without the flag (checked 2026-10-16). Kernel `VmLck` / `Mlocked` read 0 even though the table
  is pinned, so they cannot be used to judge pinning, and the cap is not what causes
  half-speed starts (`docs/flash-next-half-speed.md`).
- Checkpoint breakdown (116 GiB, 121 GB on disk): experts INT4 58.4 GiB, PLE FP8 47.7 GiB,
  attention BF16 5.6, embed 1.2, lm_head 1.2, vision 0.8.
- Per card (31.86 GiB): weights 18.79 GiB, CUDA graphs 0.72, KV 6.91, ~3 spare, ~124 GB peak
  across all four cards. Exclusive VRAM.
- Needs all four cards: TP3 fails (`248320 is not divisible by 3`, the vocab size) and TP2
  OOMs while loading weights (31.20 GiB allocated, 50 MiB free); see `docs/gpu-counts.md`.
- Server-side default `reasoning_effort=medium` (`--default-chat-template-kwargs`); requests
  can override. The template's own default (xhigh) runs away on this model (see 0.4.1 below).
- `--max-model-len 262144` (native). KV pool is ~535K tokens at 131K and ~551K at 262K.
- Cold start through the router: ~4.5 min first time (compile), ~2 min with warm cache.

**Results** (`--no-thinking`, decode tok/s, 4× R9700):

| Prompt | serial | conc=2 | conc=4 | conc=8 | conc=16 |
|--------|--------|--------|--------|--------|---------|
| medium-256 | 55 | 106 | 94 | 149 | **232** |
| xlarge-2048 | 23 | n/a | 89 | 201 | n/a |

(xlarge-2048 requests generate long outputs, so p90 latency is 70–90 s per request at every level.) An 88K-token
needle prompt prefills in ~27 s (~3.2K tok/s) and retrieves correctly. Tool calling
(`qwen3_coder` parser) and default thinking (terminates, ~100 tokens on a simple question) work.
Baselines: `bench/baselines/qwen3.8-flash-next-vllm-nightly-8cbd5d0-*.json`. For comparison
the GGUF profile does ~50 tok/s single-stream (with MTP) but only ~34 aggregate at 4 streams.

**`--gpu-memory-utilization` sweep** (2026-10-16, single run each, 262K context, serial decode
~57 tok/s at every value). Stress = 7 concurrent unique ~100K-token prompts (~690K tokens total):

| Utilization | KV pool (tokens) | Concurrency at 262K | Peak VRAM under stress | Stress result |
|-------------|------------------|---------------------|------------------------|---------------|
| **0.90 (shipped)** | 550,959 | 2.10x | ~32.0 / 34.2 GB | all 7 OK, 255 s |
| 0.93 | 627,926 (+14%) | 2.40x | 33.1 GB | all 7 OK, 255 s |
| 0.95 | 678,221 (+23%) | 2.59x | 33.76 GB (~0.45 GB headroom) | all 7 OK, 254 s |
| 0.97 | 729,278 (+32%) | 2.78x | ~34.0 GB (~0.2 GB headroom) | **stalled**: 3 of 7 timed out at 3600 s |

0.97 stalled with ~20% of the KV pool in use, no preemptions and no logged errors (probably
allocator thrash with almost no free VRAM; not proven). The extra pool only matters with several
100K+ contexts live at once, so 0.90 stays shipped; 0.93 is the safer step up and 0.95 works with
thin headroom. Do not go to 0.97 on this profile.

**Tuning findings (do not "fix" these back):**
- `--cudagraph-capture-sizes 1 2 4 8`, not the usual `1 2 4 8 16 32`. Larger captured sizes
  slow low-batch decode on this model (medium-256 serial / conc=8 / conc=16 decode tok/s:
  sizes ≤8 ≈ 52/148/209; ≤16 ≈ 37/122/231; ≤32 ≈ 27/128/227). Single-stream matters most
  for agents; batches above 8 run uncaptured and lose ~8% at conc=16.
- Context length (262144 native, was 131072) and `--max-num-seqs 32` have no measurable cost:
  the KV pool is ~535K tokens at 131K and ~551K at 262K, with the same speed.
- **MTP is not enabled.** The checkpoint ships an INT4 draft head (`runtime/mtp-int4-g32`);
  at 2 speculative tokens it accepts ~2.0 tokens/step (52% draft acceptance) but throughput
  was flat (serial 54.7 vs 53.2, conc=8 166 vs 162) and KV capacity fell by ~40% (the MTP-on pool was not re-measured against the ~535K baseline).

**0.4.1 measurements** (nightly-8cbd5d0, TP4+EP, 262144 context, 4× R9700):

| Metric | Result |
|--------|--------|
| Decode, serial / conc=8 / conc=16 / conc=32 (tok/s aggregate) | 55.5 / 204 / 251 / 460 (flagged spawn, 2026-10-19; see below) |
| Decode vs context depth, 1K to 258K | flat, 57 to 55 tok/s |
| Code tests, `reasoning_effort=medium` | 29-32/32 (two runs of 8 samples x 4 tasks: 29/32 with an explicit flag, 32/32 with the server-side default; sampling noise) |
| Code tests, template default (xhigh) | 4/32 at a 32K cap, 3/8 at 256K (runaway thinking) |

conc=8 was the unstable cell on this config, and `GPU_MAX_HW_QUEUES=1` raised it. Keep the
request counts apart when reading the evidence, because `--requests` alone moves this cell by up
to a third (`bench/CLAUDE.md`), and there are only six readings on the shipped config at
`--requests 128`.

**Unflagged, `n=128`:** 181.5 on one spawn, then 154.4, 140.1 and 140.5 on a second server in
that order — so the variation was not only spawn-to-spawn, that server drifted 10% down across
three consecutive sweeps, and the honest reading of the cell was 140-181 rather than a figure.
**Flagged, `n=128`:** 204.3 and 204.1 on two spawns; 204.1 is the published figure. Every
flagged reading is above every unflagged one, and the two flagged spawns agree to 0.1%, which
hints the flag steadies the cell as well as raising it — but two readings cannot establish that,
so treat it as something to re-check on the next spawn rather than a finding. Do not read a
difference between 204.3 and 204.1.

Lower-request-count readings exist and are not comparable with the above: 149, 157, 165 and 185
across earlier runs at `--requests 8-16` (including 157 in the same-config 262K A/B), and a
2026-10-18 matched pair at `n=16` reading 187.4 unflagged against 197.2 flagged. That pair is
internally valid — same count both sides — but its figures must not be mixed into the `n=128`
spans.

An earlier version of this section said conc=16 and conc=32 "reproduce across spawns to within
0.5%". **That was two spawns agreeing, and it does not hold.** Counting only `medium-256`
`n=128` cells on this profile's own config, the 2026-10-19 spawns give conc=16 **222.6 / 244.3 /
244.5 / 251.3** stock across four spawns against 249.9 / 250.6 flagged, and conc=32 **390.7 /
451.0 / 452.9 / 453.3** stock across four spawns against 459.6 / 465.9 flagged. So both are
~±7-13% cells and no two figures inside either should be read as a difference. Neither is a
flag gain: conc=16 lands inside the stock spread, and the flagged conc=32 readings clear the
stock maximum by only 1.4% and 2.8%. (An earlier version of this paragraph listed 359.1 and
441.5 in the conc=32 stock span; neither is a Flash-Next reading — they belong to other
profiles and were swept up by a numeric grep.) What *is* reproducible at those levels
is that they are insensitive to the state the server is in: the 22.6-tok/s-serial spawn below
still turned in 452.9 at conc=32, near the top of the stock range, so a slow draw costs ~60% on
one stream, ~9% at conc=16 and nothing measurable at conc=32.

**Open issue: an intermittent single-stream latency tail.** This profile's one-stream cells are
not reliably reproducible, and the failure is in the latency distribution rather than in the
rate. Five one-stream cells on one server on 2026-10-19:

| cell | n | decode tok/s | mean lat | p90 lat |
|---|---|---|---|---|
| serial | 32 | 55.48 | 2.82 s | 3.03 s |
| conc=1 | 128 | 55.38 | 2.81 s | 3.09 s |
| serial | 32 | 55.37 | 2.79 s | 3.06 s |
| conc=1 | 128 | **42.90** | 3.64 s | **5.72 s** |
| serial | 8 | **29.60** | 5.54 s | **10.21 s** |

The three clean cells agree to 0.2% and reproduce the 55.3 measured independently on an earlier
spawn, so 55.4 is the profile's single-stream rate. The other two are the same server minutes
later or earlier, with a tail that stretches rather than a mode that shifts. The episodes do not
trend — a clean n=32 cell ran immediately before the 42.90 one, and a normal conc=8 cell
immediately after it — and `scripts/llmband` classified the server fast throughout.

That last point was once read as "so this is not the decode band". **It no longer rules the band
in or out.** On 2026-10-19 this profile was observed changing state *mid-process*, in both
directions: a stock spawn that came up slow (23.0 tok/s single-stream) served two long loads and
a full sweep at that rate and then read 56.9 on the next probe, while two other stock spawns went
the other way, 57 → 29. A server that flips mid-life can read fast at an `llmband` probe and slow
in the bench cell minutes later, and a flip *inside* a cell produces exactly the stretched-tail
shape in the table above rather than a shifted mode. So the tail and the slow-state observations
are plausibly one phenomenon. **Cause not established**, and `mem_busy` — the discriminator that
separated the 27B's bands — has still never been sampled on a slow Flash-Next spawn, which is
the single most useful missing measurement here. It matters more than a benchmarking footnote
suggests: this is the interactive profile, and a request that takes 10 s instead of 2.8 s is
visible to whoever is waiting for it. Worth a dedicated investigation, with host memory state
(this profile pins ~48 GiB of host RAM) as one thing to rule in or out. The
0.4.1 serial/conc=16 numbers come from local runs, not a saved
baseline; `bench/baselines/qwen3.8-flash-next-vllm-*.json` holds the earlier 55 / 149 / 232. Unlike the dense 27B, Flash-Next does not slow down with context depth, which makes
the 262K window usable in practice. Medium effort is the server default because xhigh
thinks without converging on this model; medium solves the code tests in 2-4K tokens.

**Qwen3.8-27B decode vs context depth** (vLLM 0.26.0, TP4, MTP), for comparison with Flash-Next:

| Context | 1K | 32K | 66K | 132K | 207K | 258K |
|---------|----|-----|-----|------|------|------|
| decode tok/s | 83 | 19.5 | 11.2 | 6.0 | 3.8 | 3.3 |

The dense 27B loses most of its decode speed by 32K tokens, so for very long contexts
Flash-Next is the better fit. (In the 262K code-test runs the 27B converged within about 40K
tokens at xhigh, while Flash-Next at xhigh ran away.)

**Hard code tasks (2026-10):** at an 81,920-token cap Flash-Next scores 91% / 66% / 54% / 50% mean tests on
date_math / json_strict / mini_scheme / regex_engine, with no truncation; at a 32K cap three of those are 0%
(truncation, not quantisation). A 200K cap gives no further gain. Full write-up, including the 27B's
empty-reply early stops: `docs/hard-code-tasks.md`.

**Not used from the checkpoint:** its `runtime/` directory is a CUDA/RTX 3090 overlay
(UVA expert offload, `humming` MoE backend); it does not apply to ROCm.

---

---

### `qwen3.6-27b-code` — dense 27B with MTP

**Aliases:** `27b-code`, `qwen3.6-27b`

**Use for:** A second dense-27B MTP profile alongside `qwen3.8-27b-code`, kept for the
checkpoint difference rather than for speed. Restored to the config on 2026-10-19 after
having been archived.

Official `Qwen/Qwen3.6-27B-FP8`. MTP (`num_speculative_tokens: 2`), 131,072 token context,
`--max-num-seqs 32`, `--max-num-batched-tokens 16384`, `GPU_MAX_HW_QUEUES=1`,
`--gpu-memory-utilization 0.95`. TP4 or TP2 only — TP1 OOMs loading weights and TP3 fails on
16 linear-attention key heads not dividing by 3.

**`--max-num-batched-tokens 16384` is load-bearing.** Without it the MTP drafter OOMs during
startup profiling on this checkpoint. It is plain memory exhaustion, not fragmentation.

**Benchmark (vLLM 0.26.0, no-thinking, MTP, `medium-256`, 2026-10-19, `--requests 128`):**

| | conc=1 | conc=8 | conc=16 | conc=32 |
|--|--------|--------|---------|---------|
| decode tok/s | 67.7 | 347.3 | 584.6 | **869.5** |
| p90 latency s | 2.94 | 4.17 | 4.99 | 6.72 |

Baseline: `bench/baselines/qwen3.6-27b-code-v0.26.0-peak-nothink-matched-20261019.json`,
a fresh spawn classified **fast** by `scripts/llmband` before it was benchmarked. The earlier
`-peak-nothink-20261019.json` reading of the same profile sits within 1-3% of every cell here,
which is this harness's same-server spread.

**It is not faster than `qwen3.8-27b-code`** — equal at shallow prompts, a few percent behind
at depth. On the `medium-256` sweep the two are indistinguishable — 0.9% to 3.2% apart depending
on the level (67.7/347.3/584.6/869.5 against 66.0/350.4/569.4/842.7) — and with one
run per arm that is no basis for calling either one ahead. At depth the 3.8 profile is slightly ahead rather
than equal — the prewarmed decode rows, which are the comparable ones, read 168.0 against 178.8
tok/s at 16,384 x 8 (-6%) and 37.0 against 40.6 at 65,536 x 4 (-9%), with the cold rows 2-3%
apart. Nothing in that spread is a reason to pick one over the other; the 2026-10-05 comparison
found Qwen3.8 weaker on `expr_eval`
(`bench/benchmark-qwen3.8-vs-3.6-27b-2026-10-05.md`), and that difference is larger than
anything in these tables.

**Depth behaviour is the dense-27B profile's weakness**, the same as `qwen3.8-27b-code`'s:
34.7 tok/s serial at 16K, 12.0 at 64K, and a cold 16,384 x 32 cell that completed only 29 of
32 requests behind a ~17-minute prefill queue. For deep prompts use `qwen3.8-27b-think`, whose
`--attention-backend TRITON_ATTN` holds 45.0 tok/s serial at 16K and 39.0 at 64K.

Steady-state distribution at 2,048 x 32 (one-second sampling of
`vllm:generation_tokens_total`): run average 642.3 tok/s, p10 873.9, median 1007.9, p90 1075.9,
peak 1104.9 — the median is 1.57x the run average, because the run average also pays for
the ramp, where the slow seconds are.
Every measured cell for this profile, prefill and decode together, is in
`docs/benchmark-results-full.md`.

---

## Archived profiles (removed from `config/models.yaml`)

The profiles below are no longer shipped in the config. They are documented here because
their benchmark data is still referenced elsewhere, and they can be restored from git history
(`git log -- config/models.yaml`). From the 32K/64K/128K group only `qwen3.6-35b-128k-nomtp`
is still in the config.

### `qwen3.6-35b-512k` — deep context / large codebase

**Aliases:** `qwen3.6-512k`, `qwen3.6-long`

**Use for:** Ingesting entire repositories, long document QA, tasks that exceed
the native 262K context window.

**Context extension — YaRN RoPE scaling:**

```
--hf-overrides '{"text_config": {"rope_scaling": {
    "type": "yarn",
    "factor": 2.0,
    "original_max_position_embeddings": 262144
}}}'
```

Tested: needle-in-a-haystack retrieval at 420,000 tokens — correct output confirmed.

**Architecture note — why Qwen3.6 handles long context well:**

Qwen3.6 is a hybrid attention MoE: only 10 of 40 attention layers use full (quadratic)
attention; the remaining 30 use linear attention (O(n)). KV cache is needed for 25%
of layers only, making 512K context practical where it would OOM on a dense model.

**Concurrency limit:** 16. At 512K context, one sequence consumes most available KV cache.

---

### `qwen3.6-35b-32k` / `-64k` / `-128k` / `-128k-nomtp` — context-bounded variants

Clones of the code profile with `--max-model-len` bounded to 32K/64K/128K: a smaller
KV pool means faster warmup and more sequence headroom for tool-call/MCP sessions
that never approach 256K. The `-32k`/`-64k`/`-128k` variants keep MTP.

**`qwen3.6-35b-128k-nomtp` is NOT archived** — it is live in `config/models.yaml` and has its
own section above, which is the one to read. It is mentioned here only because this heading
covers the family it was cloned from. The table below is a vLLM **0.24.0** measurement from
2026-07-07 and is superseded: the profile has since gained `GPU_MAX_HW_QUEUES=1` and
`TRITON_ATTN`, which together take it from ~59 to 97.1 tok/s at 2K and from unusable to 62.4 at
130K. Kept for the MTP-vs-no-MTP comparison only, which is what it was run for:

| Profile | conc 1 tok/s | conc 8 tok/s | ITL p50 @ conc 8 |
|---|---|---|---|
| `-128k` (MTP) | **68.98** | 312.42 | 49.5 ms |
| `-128k-nomtp` | ~59 | **329.70** | **19.0 ms** |

Rule of thumb: **MTP for single-user interactive sessions; no-MTP for parallel agent
fleets** (conc ≥ 8). Switching between the two invalidates the vLLM compile-cache match —
budget ~16 min for the first swap in each direction. Full data: docs/upgrade-plan-2026-07.md.

---

### `qwen3.6-35b-awq` — AWQ Int4 quantisation

**Aliases:** `qwen3.6-awq`, `qwen3.6-q4`

**Use for:** Memory-constrained deployments; benchmarking quantisation quality/throughput
tradeoff vs FP8; loading alongside another model.

**Key settings:**
- `--quantization awq` — AWQ 4-bit weight quantisation.
- No `--enable-expert-parallel` — AWQ's MoE layers use a Triton WNA16 fallback kernel
  that is incompatible with expert parallelism (causes `IndexError: index out of bounds`).
- VRAM: ~20 GB (15 GB less than FP8) — leaves ~108 GB for KV cache and other models.

**Benchmark (vLLM 0.20.0, no-thinking, no-MTP, 2026-05-08):**

| Metric | medium-256 |
|--------|-----------|
| serial | 92 tok/s |
| conc=8 | 250 tok/s |

AWQ serial is faster than FP8 serial (92 vs 69 no-MTP) due to smaller model footprint.
At conc=8 it's slightly below FP8+MTP (250 vs 261) because FP8 benefits more from
batched execution.

**v0.26.0 note:** this profile combines two things CLAUDE.md flags as fragile — AWQ's
Triton WNA16 MoE fallback kernel (crashes under `--enable-expert-parallel`, not used
here) — so it was tested directly rather than assumed safe. `llmctl swap qwen3.6-35b-awq`
loaded cleanly in 3m21s on v0.26.0 (`Initial profiling/warmup run took 37.17s` — AWQ has
no FP8 KV calibration step, so it's faster than the FP8 profiles), served a live
completion correctly, no `IndexError`. Light no-thinking recheck:
serial 80.2 tok/s, conc=8 272.0 tok/s (`bench/baselines/qwen3.6-35b-awq-v0.26.0-nothink.json`).
Mixed against the 0.20.0 baseline above: conc=8 is above (272.0 vs 250, +8.8%), but serial
is below (80.2 vs 92, −12.8%). This is **not** a matched-version regression check like the
other Phase 6 tables — it spans six vLLM versions (0.20.0 → 0.26.0) with unrelated changes
in between, so the delta can't be attributed to this bump specifically. What this test does
establish is the thing it was run for: the crash risk (AWQ + expert-parallel WNA16 fallback)
does not reproduce on v0.26.0, and absolute throughput is still in a usable range.

---

### `qwen3.6-27b-fp8` — dense 27B model

**Aliases:** `qwen3.6-27b`, `qwen3.6-dense`

**Use for:** Tasks requiring the highest code quality; Qwen3.6-27B scores higher on
SWE-bench (77.2) than the 35B-A3B MoE (73.4) despite having a smaller total parameter
count — because all 27B parameters are active on every forward pass.

**Architecture note:**

Unlike the 35B-A3B (3B active parameters per token), the 27B model activates all 27B
parameters per forward pass. This makes it slower but more accurate:

| | 35B-A3B MoE | 27B dense |
|---|---|---|
| Total params | 35B | 27B |
| Active params/token | 3B | 27B |
| SWE-bench | 73.4 | **77.2** |
| serial decode | 43 tok/s | 23 tok/s |
| conc=8 decode | 261 tok/s | 153 tok/s |
| VRAM (FP8) | ~35 GB | ~29 GB |

**Benchmark (vLLM 0.22.1, medium-256, 2026-05-09):**

| | serial | conc=4 | conc=8 |
|---|---|---|---|
| decode tok/s | 23 | 125 | **153** |

No MTP. For the MTP-enabled variant with higher throughput see
`qwen3.6-27b-code` under Profiles above — it is in the config, this one is not.
The ~2.5x gain at conc=8 between these two rows (153 -> 351 on the newer run) is
primarily MTP; the profiles also differ in context length and KV dtype.

---

### `qwen3.6-27b-code-f16` — dense 27B BF16 (full precision)

**Aliases:** `27b-f16`, `27b-bf16`

**Use for:** Highest-quality code generation where quantisation fidelity matters; comparing
BF16 vs FP8 output quality on the 27B dense model.

**Key differences from `qwen3.6-27b-code` (FP8):**
- Full BF16 weights — zero W8A8 quantisation error in dense attention/FFN layers.
- Higher VRAM footprint: ~54 GB weights vs ~29 GB for FP8; leaves ~74 GB for KV cache.
- MTP enabled (`--speculative-config '{"method": "mtp", "num_speculative_tokens": 2}'`).
- 131,072 token context (BF16 KV, same as FP8 code profile).
- Decode throughput approximately half of FP8 (reads 2× weight bytes per step).

**Benchmark:** not benchmarked. Expected serial ~30–35 tok/s (half the FP8 rate).

---

### `qwen3.6-27b-q4km` — dense 27B Q4_K_M GGUF

**Aliases:** `qwen3.6-27b-gguf`, `qwen3.6-27b-q4`

**Use for:** Code tasks where VRAM is at a premium; comparing quantisation quality
(FP8 vs Q4) on the dense 27B model.

**Backend:** llama-server (Vulkan). ~17 GB across 4 GPUs.

**Benchmark (llama-server, medium-256, 2026-05-09):**

| | serial | conc=4 | conc=8 |
|---|---|---|---|
| decode tok/s | 22 | 45 | **41** |

Note: throughput drops at conc=8 vs conc=4 — llama-server's Vulkan threading
model saturates around 4–6 parallel sessions for a 27B dense model.
For concurrent workloads, prefer `qwen3.6-27b-fp8`.

---

### `qwen3.6-35b-q4ks` — 35B MoE GGUF

**Aliases:** `qwen3.6-gguf`

**Use for:** Serial interactive sessions where VRAM is already occupied; GPU-free
CPU inference is not needed but VRAM headroom matters.

**Backend:** llama-server (Vulkan). UD-Q4_K_S (unsloth quant). ~20 GB.

**When to prefer over vLLM profiles:**
- Conc=1: comparable serial throughput, fast cold start (~5 s vs ~2 min)
- Memory-constrained: frees ~15 GB vs FP8

**When to prefer vLLM:**
- Concurrency ≥ 2: FP8 PagedAttention scales; llama-server plateaus at ~10 parallel sessions

---

### `qwen3-coder-30b-fp8` — legacy code model

**Aliases:** `qwen3-coder`, `coder`

**Use for:** Retained as a benchmark reference. Qwen3.6 outperforms it on both
quality and concurrency throughput.

**Benchmark (vLLM 0.22.1, medium-256, 2026-05-07):**

| | serial | conc=8 |
|---|---|---|
| decode tok/s | 39 | **158** |

---

### `qwen3.5-122b-a10b-q4` and `qwen3.5-122b-a10b-q6`

**Aliases:** `qwen3.5-122b`, `122b` / `qwen3.5-122b-q6`, `122b-q6`

**Use for:** Heavyweight single queries requiring maximum reasoning depth.
Not suitable for concurrent serving — KV cache fills all 4 GPUs.

**Backend:** llama-server Vulkan. Split GGUF across 4 GPUs via `--tensor-split 1,1,1,1`.

| Variant | Quantisation | VRAM | ctx-size | concurrencyLimit |
|---|---|---|---|---|
| q4 | Q4_K_M | ~73 GB | 32768 | 8 |
| q6 | Q6_K   | ~98 GB | 16384 | 6 |

Cold start: ~90–180 s (first disk read of 73–98 GB over NVMe).

---

## Gemma 4

Google's Gemma 4 is a vision-capable MoE model family. Gemma 4 26B-A4B has 26B total
parameters but only 4B active per forward pass (top-8 routing across small 704-dim experts),
giving MoE-class throughput at a fraction of the VRAM of a dense model. It supports
multimodal input (image + text) via a bundled SigLIP-400M vision encoder. Thinking/reasoning
mode is active by default in the IT variant.

Four profiles are configured. As of 2026-06-13, only `gemma4-26b-q8` has model files on
disk and has been benchmarked. The other three require model downloads before use.

---

### `gemma4-26b-q8` — Gemma 4 26B Q8 GGUF (primary, on disk)

**Aliases:** `gemma4`, `gemma4-26b`, `gemma4-moe`, `gemma4-vision`

**Backend:** llama-server (Vulkan). GGUF Q8_0.
**Model path:** `/mnt/models/llm/lmstudio-community/gemma-4-26B-A4B-it-GGUF/`
**VRAM:** ~28 GB across 4 GPUs (~7 GB each) at Q8_0.

**Use for:** General reasoning, instruction following, vision tasks (image QA, OCR,
diagram analysis). Strong all-round alternative to Qwen3.6 for non-code tasks where
vision input is needed. Thinking mode active by default — token counts include `<think>`
blocks; use `--no-thinking` in bench to measure decode throughput cleanly.

**Special capabilities:**
- **Vision:** Accepts image URLs or base64 via the standard OpenAI multimodal format
  (`content: [{type: "image_url", ...}]`). The llama-server image must be built with
  vision support enabled (`--mmproj` flag in the profile).
- **Thinking/reasoning mode:** The IT model activates extended reasoning by default.
  This inflates measured token counts relative to models with thinking off. Benchmark
  numbers below reflect thinking active (not suppressed).
- **MoE efficiency:** 4B active params per token. At Q8_0, decode throughput scales
  well with concurrency — long-512 throughput nearly doubles from conc=1 to conc=16,
  consistent with effective request batching on longer contexts.

**Key config notes:**
- `--tool-call-parser gemma4` — Gemma 4 uses a non-JSON wire format
  (`<|tool_call>call:func_name{...}<tool_call|>`). The dedicated `gemma4` parser is
  required; `pythonic` or `json` parsers do not handle this format.
- `--reasoning-parser` intentionally omitted for the llama-server GGUF profile. The
  vLLM profile (`gemma4-26b-a4b`) would need it, but there is a confirmed upstream bug
  (vLLM #39130): adding `--reasoning-parser gemma4` while `enable_thinking=false`
  silently disables structured output (xgrammar) for all requests.
- `--enable-expert-parallel` omitted — not validated for Gemma 4's expert architecture
  (704-dim experts, top-8 routing); tested only for DeepSeek-V3 and Qwen3 MoE.

**Benchmark — thinking active (2026-06-13):**

| Prompt | conc=1 | conc=4 | conc=8 | conc=16 |
|--------|--------|--------|--------|---------|
| short-64    |  56.8 |  90.6 | **127.5** | 129.7 |
| medium-256  |  65.5 | 117.2 | **153.9** | 135.8 |
| long-512    |  66.8 | 119.0 | **155.5** | 129.7 |
| xlarge-2048 |  67.3 | 114.8 | **150.6** | 125.0 |

Decode tok/s. Baseline saved: `bench/baselines/gemma4-26b-q8-20260613.json`.
Peak VRAM: 32.1 GB (single GPU, tensor-split across 4 × R9700).
Sweet spot: conc=8 across all prompt sizes. conc=16 shows a slight dip (llama-server
queue saturation at `--parallel 16`). Decode rate is remarkably stable across prompt
sizes at the same concurrency — characteristic of the MoE architecture where only 4B
parameters are active per token regardless of prompt length.

**Benchmark — no-thinking (2026-06-18):**

| Prompt | conc=1 | conc=4 | conc=8 | conc=16 |
|--------|--------|--------|--------|---------|
| short-64    |  51.6 |  68.4 |   85.0 | **112.6** |
| medium-256  |  63.5 |  99.1 | **126.8** | 127.5 |
| long-512    |  66.5 | 107.6 | **129.5** | 119.9 |
| xlarge-2048 |  67.4 |  62.2 |   70.2 | **119.0** |

Decode tok/s. Baseline saved: `bench/baselines/gemma4-26b-q8-nothink-20260618.json`.
Thinking suppression confirmed: `chat_template_kwargs: {enable_thinking: false}` works
correctly — direct answers, no thinking tokens in content. Numbers appear ~10–18% lower
than the thinking-on baseline at conc=4–8; this is a measurement artifact: thinking tokens
inflate the completion token count in the thinking-on run, making its measured tok/s
artificially higher. Both baseline sets are kept; see `bench/CLAUDE.md` for the
dual-baseline convention.

---

### `gemma4-12b-q4` — Gemma 4 12B Q4 GGUF

**Aliases:** `gemma4-12b`, `gemma4-small`, `gemma4-fast`

**Backend:** llama-server (Vulkan). GGUF Q4_K_M.
**Model path:** `/mnt/models/llm/lmstudio-community/gemma-4-12B-it-GGUF/`
**VRAM:** ~13.4 GB across 4 GPUs (~3.4 GB each) — lowest footprint in the stack.

**Use for:** Lightweight inference and quick tasks. Dense 12B model — slower per token
than the MoE 26B Q8 but uses less than half the VRAM, making it co-loadable alongside
heavier profiles. Also vision-capable via the bundled mmproj.

**Benchmark — thinking active (2026-06-13):**

| Prompt | conc=1 | conc=4 | conc=8 | conc=16 |
|--------|--------|--------|--------|---------|
| short-64    |  32.6 |  62.5 |  **83.7** | 78.4 |
| medium-256  |  36.1 |  81.2 | **108.9** | 94.8 |
| long-512    |  36.3 |  83.9 | **108.5** | 94.0 |
| xlarge-2048 |  35.2 |  82.4 | **107.1** | 93.6 |

Decode tok/s. Baseline saved: `bench/baselines/gemma4-12b-q4-20260613.json`.
Peak VRAM: 13.4 GB. Sweet spot: conc=8 across all prompt sizes (2.6–3.0× serial).
Throughput is remarkably flat across prompt sizes (~35 tok/s serial) — consistent with
a dense model where bandwidth cost per token is fixed by parameter count, not context.

**Benchmark — no-thinking (2026-06-18):**

| Prompt | conc=1 | conc=4 | conc=8 | conc=16 |
|--------|--------|--------|--------|---------|
| short-64    |  31.4 |  51.3 |  **63.8** | 68.3 |
| medium-256  |  35.3 |  70.3 |  **87.7** | 81.9 |
| long-512    |  35.8 |  77.9 |  **95.9** | 83.7 |
| xlarge-2048 |  35.6 |  35.2 |  **47.5** | 85.8 |

Decode tok/s. Baseline saved: `bench/baselines/gemma4-12b-q4-nothink-20260618.json`.
`chat_template_kwargs: {enable_thinking: false}` confirmed effective — spot-check
response to "What is 2+2?" was a direct answer with no `<think>` block.
Notable: no-thinking throughput is lower than the thinking-on baseline (e.g. conc=8
medium-256: 87.7 vs 108.9). This is counterintuitive but consistent with the 26B-A4B
results — for Gemma 4, `enable_thinking: false` changes only the template scaffolding;
any throughput difference is within session-to-session measurement noise.
xlarge-2048 shows no speedup at conc=4 (35.2 tok/s ≈ serial), indicating KV cache
pressure at long contexts with 4 concurrent streams; speedup recovers at conc=16.

---

### `gemma4-26b-a4b` — Gemma 4 26B vLLM BF16

**Aliases:** `gemma4-vllm`, `gemma4-concurrent`

**Backend:** vLLM 0.26.0 (`docker.io/vllm/vllm-openai-rocm:v0.26.0`), BF16 safetensors.
**Model path:** `/mnt/models/llm/google/gemma-4-26B-A4B-it`
**VRAM:** 122.7 GB across 4 GPUs — nearly fills all 128 GB. Profile is exclusive; cannot
co-load with any other model. The large VRAM footprint is the model weights (49 GB BF16)
plus the KV cache pool vLLM allocates at startup.

**v0.26.0 note:** upstream issue #49878 reports a ~40% KV-cache VRAM sizing regression
for Gemma 4 models between vLLM v0.25.1→v0.26.0 (reported on NVIDIA Blackwell running
a different Gemma 4 checkpoint with FP8 KV cache + speculative decoding). Given this
concern and that this profile already consumes 122.7/128 GB, it was tested directly as
part of the v0.24.0→v0.26.0 upgrade (2026-07-27): `llmctl swap gemma4-26b-a4b` loaded
cleanly in 3m07s, served a live completion correctly, and used ~124 GB total VRAM — in
line with the historical 122.7 GB figure, no OOM, no KV-cache blowup. The upstream
report does not reproduce on this hardware/config. A light conc=1/8/16 recheck on
medium-256 no-thinking gave 63.0/233.1/485.6 tok/s (`bench/baselines/gemma4-26b-a4b-v0.26.0-nothink.json`)
— conc=16 is close to the 0.22.1-era baseline below; conc=8 is softer, but this compares
against a baseline four vLLM versions back, not a matched 0.24.0→0.26.0 delta, so it
isn't read as a regression from this bump specifically.

**Use for:** High-concurrency agent workloads. vLLM's PagedAttention and MoE architecture
(4B active params per token) combine to give outstanding batching efficiency — on the
2026-10-19 matched sweep this is **the fastest profile on the stack at every concurrency
level**: 891 tok/s at conc=16 and 1443 at conc=32 on medium-256 prompts.

The 528 tok/s figure this section used to quote was measured before
`GPU_MAX_HW_QUEUES=1` shipped on this profile, and gemma4 is the one profile where a slow
band draw costs fleet throughput rather than just single-stream latency (it keeps 1.71× of
the flag's gain all the way to conc=8). The dated 2026-06-13 sweep below is kept as the
historical record, not as a current figure.
Use this profile when many parallel requests are hitting Gemma 4 simultaneously.

**First boot:** vLLM triggers Inductor/Triton compile on first start (~3–5 min with warm
`.vllm-cache/`). The `healthCheckTimeout` in models.yaml is set to 1200 s to cover this.
Subsequent starts: ~2–3 min.

**Key config notes:**
- `--tool-call-parser gemma4` — Gemma 4's tool-call wire format requires its own parser
- Triton attention backend is forced automatically by vLLM (heterogeneous head dims)
- No `--enable-expert-parallel` — not validated for this MoE architecture
- No `--kv-cache-dtype fp8` — BF16 weights; leave KV at default

**Benchmark — thinking active (2026-06-13):**

| Prompt | conc=1 | conc=4 | conc=8 | conc=16 | conc=32 |
|--------|--------|--------|--------|---------|---------|
| short-64    |  53.1 | 123.1 | 140.0 | 243.0 | **394.8** |
| medium-256  |  53.4 | 167.1 | 287.1 | **528.2** | 540.7 |
| long-512    |  53.5 | 170.8 | 289.8 | **476.1** | 483.1 |
| xlarge-2048 |  53.1 | 165.9 | 294.5 | **485.7** | 492.5 |

Decode tok/s. Baseline saved: `bench/baselines/gemma4-26b-a4b-20260613.json`.
Peak VRAM: 122.7 GB. Sweet spot: conc=16 for medium/long/xlarge (conc=32 adds <3%).
Scaling factor from serial to conc=16: **9.9×** on medium-256 — exceptional MoE batching.
The throughput plateau at conc=16→32 reflects the `--max-num-seqs 32` ceiling being
reached; the model is compute-bound, not queue-bound, at this level.

**Benchmark — no-thinking (2026-06-18):**

| Prompt | conc=1 | conc=4 | conc=8 | conc=16 | conc=32 |
|--------|--------|--------|--------|---------|---------|
| short-64    |  51.5 | 146.0 | 281.6 | **482.5** | 501.5 |
| medium-256  |  52.4 | 165.4 | 307.3 | **493.7** | 527.8 |
| long-512    |  52.6 | 160.9 | 283.7 | **476.1** | 470.9 |
| xlarge-2048 |  52.2 | 164.5 | 288.4 | **488.5** | 491.8 |

Decode tok/s. Baseline saved: `bench/baselines/gemma4-26b-a4b-nothink-20260618.json`.
`chat_template_kwargs: {enable_thinking: false}` confirmed effective — spot-check
response to "What is 2+2?" was a direct answer with no `<think>` block.
No-thinking throughput is effectively identical to thinking-on across all prompt sizes
(differences within ~6%, within session-to-session noise). Gemma 4 IT does not use
thinking by default in generation; `enable_thinking: false` changes template scaffolding
only and does not meaningfully alter throughput. The short-64 conc=16 thinking-on
result (243 tok/s) is anomalously low compared to no-thinking (482.5); the thinking-on
run likely generated additional reasoning tokens that changed the effective batch
dynamics at that concurrency level.

---

### `gemma4-26b-fp8` — Gemma 4 26B FP8 vLLM (long-context)

**Aliases:** `gemma4-fp8`, `gemma4-fast-vllm`

**Backend:** vLLM 0.26.0 (`docker.io/vllm/vllm-openai-rocm:v0.26.0`), FP8-Dynamic weights.
**Model path:** `/mnt/models/llm/RedHatAI/gemma-4-26B-A4B-it-FP8-Dynamic`
**VRAM:** ~26 GB FP8 weights + BF16 KV cache across 4 GPUs.

**Use for:** Long-context coding sessions and document analysis. FP8 quantisation roughly
halves weight VRAM vs BF16, leaving far more headroom for KV cache at extended context.
Max context: 262,144 tokens. Heterogeneous attention architecture (25 sliding + 5 full
attention layers) makes this efficient at long contexts.

**Key config notes:**
- `--max-model-len 262144` — full native context window.
- No `--kv-cache-dtype fp8` — BF16 KV avoids calibration; ~2× VRAM per KV token vs FP8 KV
  but is simpler and avoids accuracy questions at long contexts.
- No `--enable-expert-parallel` — not confirmed supported for this MoE architecture.
- No `--reasoning-parser` — Gemma 4 has no structured thinking mode.

**Benchmark:** not benchmarked. Model requires download to `/mnt/models/llm/RedHatAI/`.

---

### Gemma 4 cross-model comparison

Three of four Gemma 4 profiles have benchmark data. Medium-256 prompt, decode tok/s:

| Model | backend | quant | VRAM | conc=1 | conc=8 | conc=16 |
|-------|---------|-------|------|--------|--------|---------|
| `gemma4-26b-a4b` | vLLM | BF16 | 123 GB | 53.4 | 287.1 | **528.2** |
| `gemma4-26b-fp8` | vLLM | FP8 | ~26 GB | — | — | — |
| `gemma4-26b-q8` | llama-server | Q8_0 GGUF | 32 GB | 65.5 | 153.9 | 135.8 |
| `gemma4-12b-q4` | llama-server | Q4_K_M GGUF | 13 GB | 36.1 | 108.9 | 94.8 |
| — | — | — | — | — | — | — |
| `qwen3.6-35b-code` (pre-MTP baseline, no-think) | vLLM | FP8 | 35 GB | 43 | 261 | 481 |

**Superseded for the two vLLM rows.** Every figure in this table predates
`GPU_MAX_HW_QUEUES=1`. On the 2026-10-19 matched sweep `gemma4-26b-a4b` reads
129.2 / 539.9 / 890.8 at conc=1/8/16 and `qwen3.6-35b-code` reads 109.7 / 302.0 / 584.8. The
llama-server rows are unaffected by that flag and still stand. The table is left as measured
so the pre-flag record survives.
| `qwen3.6-35b-fast` (no-think, no-MTP) | vLLM | FP8 | 35 GB | 69 | 222 | — |
| `qwen3.6-35b-q4ks` | llama-server | Q4_K_S | 20 GB | ~80 | ~175 | — |

**Key findings:**
- `gemma4-26b-a4b` **beats** `qwen3.6-35b-code` (pre-MTP baseline) at conc=16 (528 vs
  481 tok/s) despite being BF16 vs FP8 and having no speculative decoding. The 4B active
  params per token allows vLLM to pack dramatically more requests per batch.
- `gemma4-26b-q8` serial (65.5) is comparable to Qwen3.6 FP8 serial (43–69) but doesn't
  scale as well with concurrency — llama-server caps at `--parallel 16` without vLLM's
  PagedAttention. Advantage: 32 GB VRAM vs 123 GB, can co-load with other models.
- `gemma4-12b-q4` is the lightest vision-capable option at 13 GB — can run alongside any
  other profile in the stack. Throughput ~109 tok/s at conc=8 is solid for its size.

---

### Vision usage — image input with `gemma4-26b-q8`

Pass images using the OpenAI multimodal `content` array format. The `image_url` type
accepts either an HTTPS URL or a base64 data URI:

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4-26b-q8",
    "max_tokens": 512,
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "image_url",
            "image_url": {
              "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png"
            }
          },
          {
            "type": "text",
            "text": "Describe what you see in this image."
          }
        ]
      }
    ]
  }'
```

To use a local file, encode it as base64 and substitute the `url` value:

```bash
B64=$(base64 -w 0 /path/to/image.png)
# then set "url": "data:image/png;base64,${B64}"
```

The `--mmproj` flag in the profile points to the bundled SigLIP-400M multimodal
projector. If the model loads but image requests return errors, verify the `--mmproj`
path in `config/models.yaml` matches the actual filename in the GGUF directory.

---

## FP8 kernel config note

vLLM warns at startup:

```
Using default W8A8 Block FP8 kernel config. Performance might be sub-optimal!
Config file not found for device_name=AMD_Radeon_R9700, dtype=fp8_w8a8
```

The R9700 (gfx1201 / RDNA4) does not yet have hand-tuned FP8 GEMM kernel configs in
the vLLM kernel registry. vLLM falls back to MI300X defaults. Generating a custom
config (via `python -m vllm.tools.profiler`) is a future tuning opportunity that
could improve throughput by ~10–20%.

---

## Tensor parallelism rationale

Neither Qwen3.6-35B-FP8 (~31 GB) nor Qwen3-Coder-30B-FP8 (~31 GB) fits in a single
32 GB R9700. Even if they did, single-GPU throughput would be memory-bandwidth limited.
With TP=4 (TP must be 1, 2 or 4; other sizes and smaller GPU counts are covered in
`docs/gpu-counts.md`):

- **4× aggregate HBM bandwidth** across 4 GPUs
- **All-reduce cost** ~1.5 ms per token over PCIe 5.0 — small vs generation time
- **KV cache distributed** across 4 GPUs, enabling much larger effective batch sizes

At conc ≥ 4, TP=4 wins decisively over single-GPU.

---

## Adding a new profile

See the template section at the bottom of `config/models.yaml`. Key steps:

1. Add the YAML stanza (vLLM or llama-server template)
2. Include `--cudagraph-capture-sizes 1 2 4 8 16 32` and the cache volume mounts
3. Set `concurrencyLimit` explicitly — the default causes 429s under load
4. `llmctl list` to verify the profile appears
5. `llmctl swap <profile>` to load and warm it up
6. `bench/concurrent_bench.py --model <profile> --quick --no-thinking` for a smoke benchmark
7. Save a full baseline: `bench/concurrent_bench.py --model <profile> --sweep 1,2,4,8,16 --prompt all --no-thinking --save bench/baselines/<profile>.json`
