# llmstack

OpenAI-compatible LLM serving stack for **concurrent agent use**.  
Designed for: Claude Code · OpenCode · MCP testing · agent frameworks · raw API clients.

Reference hardware: 1–4× AMD Radeon AI PRO R9700 (gfx1201, 32 GB each) — `scripts/configure` auto-detects your GPU count and patches the config accordingly. See [Hardware compatibility](#hardware-compatibility) for details.  
Backends: **vLLM 0.26.0** (FP8/AWQ/safetensors, PagedAttention, high concurrency) + **llama-server Vulkan** (GGUF models)  
Router: **llama-swap** — one OpenAI endpoint, models loaded on demand by the `model` field

---

## Prerequisites

Before cloning, confirm these are in place:

- **ROCm installed** — `/dev/kfd` must exist. If `ls /dev/kfd` returns "No such file", install ROCm first: [ROCm installation guide](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/)
- **podman installed** — `which podman`. Rootless podman is assumed throughout.
- **GPU device group membership** — your user must be in the `render` (and optionally `video`) group: `groups | grep render`. If not: `sudo usermod -aG render,video $USER` then log out and back in.
- **Models on disk** — the config expects models at `/mnt/models/llm/`. Adjust the `-v` mount paths in `config/models.yaml` if yours are elsewhere.

The vLLM container image (`docker.io/vllm/vllm-openai-rocm:v0.26.0`) is large (~35 GB) and will be pulled automatically on first `llmctl swap`. Make sure you have the disk space and a reasonable connection before starting.

---

## Quick start

```bash
# 1. Clone and install tools
git clone https://github.com/x7even/llmctl.git ~/ai/llmstack
cd ~/ai/llmstack
ln -sf "$(pwd)/bin/llmctl" ~/.local/bin/llmctl

# 2. Install llmpanel TUI (pre-built binary — no Go required)
curl -fsSL https://raw.githubusercontent.com/x7even/llmctl/master/install-llmpanel.sh | bash

# 3. Configure for your machine (GPU count + absolute paths)
#    This is required — models.yaml ships with __LLMSTACK_DIR__ placeholders
#    that configure replaces with the actual repo path, and patches GPU count.
scripts/configure

# 4. Start the router
llmctl up

# 5. Load a model and wait until ready
llmctl swap qwen3.8-27b-code

# 6. Make a request
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.8-27b-code","messages":[{"role":"user","content":"Write a Python quicksort"}]}'

# 7. Open the TUI control panel (optional)
llmpanel
```

> **First-boot note:** vLLM compiles Inductor kernels and calibrates the FP8 KV cache
> on cold start — this is a one-time 18–20 min process. Compiled artifacts are cached in
> `.vllm-cache/` and `.triton-cache/`. Subsequent starts take ~2–3 min.

---

## Client configuration

| Client | Setting |
|--------|---------|
| Claude Code | `ANTHROPIC_BASE_URL=http://localhost:8080/v1` |
| OpenCode | `baseURL: http://localhost:9000/v1` (via llmproxy — see below) |
| Continue.dev | `apiBase: http://localhost:8080/v1` |
| aichat / llm CLI | `--url http://localhost:8080/v1` |
| curl / scripts | `http://localhost:8080/v1/chat/completions` |

> **OpenCode note:** OpenCode uses `@ai-sdk/openai-compatible` which has a
> strict tool-call streaming validator. Point it at `:9000` (llmproxy) rather
> than `:8080` directly. See `docs/workarounds.md`.

---

## Model profiles

| Profile | Backend | VRAM | Context | Best for |
|---------|---------|------|---------|---------|
| `qwen3.8-27b-code` | vLLM TP=4 + MTP | ~31 GB + KV | 131K | **Default.** Claude Code, OpenCode, agentic coding; thinking on (medium effort) |
| `qwen3.8-27b-think` | vLLM TP=4 + TRITON_ATTN | ~31 GB + KV | 131K | **The deep-context and agent-fleet profile.** Same weights, no MTP, `--attention-backend TRITON_ATTN` — keeps scaling with concurrency at 16K+, where the MTP default peaks at ~8 streams and then falls back |
| `qwen3.8-27b-fast` | vLLM TP=4 + MTP | ~31 GB + KV | 131K | Thinking off by default — quick answers, bulk work |
| `qwen3.8-flash-next` | llama-server Vulkan | ~81 GB | 262K (2 slots) | Qwen3.8-Flash-Next 125B (6B active), UD-IQ4_XS GGUF; single-user — throughput plateaus early, so for concurrent agents use `qwen3.8-flash-next-vllm` |
| `qwen3.8-flash-next-vllm` | vLLM TP=4 + EP (nightly image) | ~19 GB/GPU + ~48 GB pinned host RAM (~96 GB host RAM) | 262K | Same model, W4A16 INT4. Decode scales with concurrency and stays flat all the way out to its full 262K window — the one profile here whose speed barely cares how deep the prompt is. Defaults to medium reasoning effort. Exclusive VRAM; needs all 4 GPUs |
| `qwen3.6-27b-code` | vLLM TP=4 + MTP | ~31 GB + KV | 131K | Previous-generation dense 27B (FP8) — MTP + thinking; fast on short prompts |
| `qwen3.6-35b-code` | vLLM TP=4 + MTP | ~35 GB | 131K | Previous generation (MoE, 3B active) — MTP + thinking |
| `qwen3.6-35b-128k-nomtp` | vLLM TP=4 | ~35 GB | 131K | Previous generation — thinking, no MTP. Not yet measured at depth, and does not set `--attention-backend TRITON_ATTN`, so the deep-context fix in `docs/rdna4-long-context.md` is **not** applied to it |
| `qwen3.6-35b-fast` | vLLM TP=4 | ~35 GB | 262K | Previous generation — thinking disabled by default |
| `gemma4-26b-a4b` | vLLM TP=4, BF16 | ~123 GB | 128K | Highest raw aggregate throughput on short prompts; vision; exclusive VRAM |
| `gemma4-26b-fp8` | vLLM TP=4, FP8 | — | 262K | Long-context Gemma 4 agent serving |
| `gemma4-26b-q8` | llama-server Vulkan | ~32 GB | 32K | Vision-capable; co-loadable |
| `gemma4-12b-q4` | llama-server Vulkan | ~13 GB | 32K | Lightest vision option; co-loadable with any profile |

Older Qwen profiles (3.6-35B 32K/64K/512K/AWQ/GGUF, Qwen3-Coder-30B,
Qwen3.5-122B) were removed from the shipped config; their benchmark data is kept in
`docs/models.md` and the profiles can be restored from git history.

**Aliases** (short names that route to the same profile):

| Alias | Resolves to |
|-------|-------------|
| `qwen3.8`, `qwen3.8-27b`, `27b-3.8` | `qwen3.8-27b-code` |
| `27b-think` | `qwen3.8-27b-think` |
| `27b-fast`, `qwen3.8-nothink` | `qwen3.8-27b-fast` |
| `flash-next`, `qwen3.8-flash` | `qwen3.8-flash-next` |
| `flash-next-vllm` | `qwen3.8-flash-next-vllm` |
| `27b-code`, `qwen3.6-27b` | `qwen3.6-27b-code` |
| `qwen3.6`, `qwen3.6-35b`, `qwen3.6-35b-fp8` | `qwen3.6-35b-code` |
| `35b-nomtp` | `qwen3.6-35b-128k-nomtp` |
| `qwen3.6-fast`, `qwen3.6-nothin` | `qwen3.6-35b-fast` |
| `gemma4`, `gemma4-26b`, `gemma4-moe`, `gemma4-vision` | `gemma4-26b-q8` |
| `gemma4-vllm`, `gemma4-concurrent` | `gemma4-26b-a4b` |

See `docs/models.md` for benchmark data, architecture details, and tuning notes. Fewer than four GPUs: see `docs/gpu-counts.md`.

---

## Benchmarks

All figures below were measured on the same hardware (4× R9700, 128 GB total)
across a single campaign, on the pinned `v0.26.0` image (`qwen3.8-flash-next-vllm`
on its nightly pin), with **output length pinned at 1,024 tokens** and
`--no-thinking`. Pinning the output matters: without it a faster model writes
longer answers and the latency column silently compares answer lengths instead
of speeds.

### Read these three caveats first, or the numbers will mislead you

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

### Depth is the axis the old table was missing, and it dominates

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

### Per-profile depth × concurrency

#### `qwen3.8-27b-think`

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

#### `qwen3.8-27b-code`

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

#### `qwen3.8-flash-next-vllm`

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

#### `qwen3.6-27b-code`

Decode band: **fast** — llmband.

Cold — every stream pays its own prefill:

| depth | conc | ok | TTFT mean | TTFT p90 | prefill tok/s | per-stream tok/s | **aggregate tok/s** |
|---|---|---|---|---|---|---|---|
| 4,096 | 1 | 1/1 | 0.9 s | 0.9 s | 4473 | 61.1 | **61.1** |
| 4,096 | 8 | 8/8 | 7.0 s | 8.9 s | 3683 | 45.7 | **304.2** |
| 4,096 | 32 | 32/32 | 25.5 s | 45.6 s | 2779 | 17.5 | **368.9** |
| 16,384 | 1 | 1/1 | 4.0 s | 4.0 s | 4112 | 34.7 | **34.7** |
| 16,384 | 8 | 8/8 | 54.9 s | 92.4 s | 1419 | 16.6 | **64.5** |

#### `qwen3.6-35b-code`

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

#### `gemma4-26b-a4b`

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

### What happens to prefill as the batch widens

`prefill tok/s` is batch prompt tokens divided by the slowest TTFT in the cell,
so it is a whole-batch rate, not a per-stream budget. Measured, it splits cleanly
by whether the profile runs MTP, at 16,384 tokens cold:

| profile | MTP | conc=1 | conc=8 | conc=16 | conc=32 |
|---|---|---|---|---|---|
| `qwen3.8-27b-think` | no | 3965 | 3945 | 3937 | 3931 |
| `qwen3.8-27b-code` | yes | 4110 | 1418 | 881 | — |
| `qwen3.8-flash-next-vllm` | no | 2652 | 2732 | 2720 | — |
| `qwen3.6-27b-code` | yes | 4112 | 1419 | — | — |
| `qwen3.6-35b-code` | yes | 11944 | 5620 | — | — |
| `gemma4-26b-a4b` | no | 4203 | 4255 | — | — |

The non-MTP profiles hold flat as the batch widens; the MTP ones fall away. That
is the measured pattern — this table does not claim a mechanism for it.

### Short-prompt peak throughput (the legacy `medium-256` sweep)

This is the workload the previous version of this table measured, kept so the
new figures can be compared against the old. It is **not** the headline: a
256-token prompt cannot see any of the behaviour above.

| Profile | serial | conc=8 | conc=16 | conc=32 | mean latency @32 |
|---|---|---|---|---|---|
| `qwen3.8-27b-think` | 46.0 | 274.0 | 477.0 | **760.1** | 7.67 s |
| `qwen3.8-27b-code` | 64.9 | 348.8 | 576.5 | **856.5** | 6.89 s |
| `qwen3.8-flash-next-vllm` | 55.3 | 181.5 | 244.3 | **453.3** | 10.89 s |
| `qwen3.6-35b-code` | 51.3 | 291.3 | 572.0 | **950.2** | 4.76 s |
| `gemma4-26b-a4b` | 56.2 | 300.0 | 559.4 | **944.4** | 4.96 s |

Zero errors on every cell above. 128 requests per level, `--no-thinking`.

**Note how the ranking inverts.** `qwen3.8-27b-think` is the *slowest* profile
here and the *fastest* by a wide margin at depth. A single-number table cannot
express that, which is why this section leads with the depth grid.

#### Profiles this campaign did not re-measure

The two vision profiles run on llama-server (Vulkan), not vLLM, and were
left out of the sweep above. Their last figures are older and were taken
with thinking **on** and on a different vLLM-era baseline, so they are not
comparable with the tables above and are not reproduced here:

- `gemma4-26b-q8` — Q8 GGUF + mmproj, ~32 GB, the vision workhorse
- `gemma4-12b-q4` — Q4 GGUF + mmproj, ~13 GB, lightest vision option,
  co-loadable alongside any vLLM profile

Both are in `docs/models.md` with their original numbers. Gemma 4 IT turns
on extended reasoning by default; `chat_template_kwargs: {enable_thinking:
false}` does suppress `<think>` output but does not meaningfully change
their throughput (differences sit inside session noise).

### Which profile to use

| If you are | Use | Why |
|---|---|---|
| running agents on deep context (16K+), especially several at once | **`qwen3.8-27b-think`** | scales to 32 streams at 16K and holds up at 130K; the MTP default peaks at ~8 streams at depth and then falls |
| running many agents on short prompts | `qwen3.8-27b-code` | fastest at `medium-256` and at 4K; MTP wins where prompts are shallow |
| serving one or two clients at very long context | `qwen3.8-flash-next-vllm` | per-stream decode is flat (~55 tok/s) from 4K to 250K |
| after raw short-prompt aggregate | `qwen3.6-35b-code` or `gemma4-26b-a4b` | both clear 940 tok/s at conc=32 |
| doing vision work | `gemma4-26b-q8` / `gemma4-12b-q4` | the GGUF + mmproj profiles |

### Reproducing any row

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

Full per-profile data and architecture notes: `docs/models.md`.



---

## CLI reference (`llmctl`)

```
llmctl up                 start llama-swap (auto-downloads binary if missing)
llmctl down               stop llama-swap
llmctl status             running state, loaded models, GPU VRAM snapshot
llmctl list [--all]       list profiles this hardware can run [* = loaded]; --all shows every profile
llmctl hw [--json]        detected GPUs / RAM and which profiles fit (LLMSTACK_GPU_COUNT=N simulates)
llmctl swap <profile>     load a model and wait until ready (refuses unsupported ones; --force overrides, expect the start to fail)
llmctl unload             unload all backends, free VRAM (llama-swap stays up)
llmctl pick               interactive fzf / numbered picker
llmctl logs               tail the llama-swap process log
llmctl logs <profile>     tail a model's container log
llmctl bench [profile]    run concurrent benchmark
llmctl proxy-up           start llmproxy shim on :9000
llmctl proxy-down         stop llmproxy shim
llmctl proxy-status       show llmproxy state
```

Full reference: [`docs/llmctl.md`](docs/llmctl.md)

### Common workflows

```bash
# Check what's running and VRAM state
llmctl status

# Switch between models
llmctl swap qwen3.8-27b-code     # default: MTP + thinking, best single-stream latency
llmctl swap qwen3.8-27b-think    # no MTP — better for many parallel agents
llmctl swap qwen3.8-27b-fast     # thinking off
llmctl swap flash-next           # Qwen3.8-Flash-Next 125B (GGUF, single user)
llmctl swap flash-next-vllm      # Qwen3.8-Flash-Next 125B (vLLM TP4+EP, concurrent agents)
llmctl swap gemma4               # Gemma 4 26B Q8 vision (alias → gemma4-26b-q8)
llmctl swap gemma4-vllm          # Gemma 4 26B BF16 vLLM — highest concurrent tok/s

# Free VRAM without stopping the router
llmctl unload

# Benchmark the loaded model
llmctl bench qwen3.8-27b-code

# Tail model startup logs (useful during first boot)
llmctl logs qwen3.8-27b-code

# Interactive picker (requires fzf)
llmctl pick
```

---

## Terminal control panel (`llmpanel`)

`llmpanel` is a [roctop-style](https://github.com/x7even/roctop) TUI that combines monitoring and control in one
terminal window.

```bash
llmpanel [--url URL] [--interval DURATION] [--config PATH] [--log PATH] [--gpu-count N]
```

The Models panel applies the same hardware check as `llmctl`: it lists only the profiles this machine can run (from each profile's `metadata.requires`), shows the detected hardware in its header, and `a` toggles a greyed-out view of the rest with the reason. Swapping an unsupported profile is refused; use `llmctl swap --force` to try it anyway.

**Panels** (press `1`–`5` or `Tab` to focus, `f` for fullscreen):

| # | Panel | Shows |
|---|-------|-------|
| 1 | Inference | Active model, running/waiting requests, KV%, decode tok/s, TTFT, prefix hit rate |
| 2 | GPU | Per-GPU VRAM, use%, temperature — colour-coded |
| 3 | Models | Profiles this hardware can run; `▶` cursor, `●` loaded; `Enter`/`s` to swap, `u` to unload, `a` to show the rest |
| 4 | Config | Scrollable YAML for the selected profile; updates as cursor moves |
| 5 | Logs | Live tail of llama-swap log |

**Key bindings:**

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Cycle panel focus |
| `1`–`5` | Jump to panel |
| `f` / `Esc` | Toggle fullscreen |
| `↑↓` / `jk` | Navigate model list or scroll Config/Logs |
| `Enter` / `s` | Swap to selected model |
| `u` | Unload all models |
| `a` | Show / hide profiles this hardware cannot run (greyed, with the reason) |
| `p` | Cycle poll interval (500ms → 1s → 2s → 5s → 15s) |
| `r` | Reload models.yaml from disk and re-detect hardware |
| `q` / `Ctrl+C` | Quit |

Build from source: `cd tui && make install`  
Full reference: [`tui/README.md`](tui/README.md)

---

## Adding a new model

**vLLM (safetensors / FP8 / AWQ):**
1. Copy the vLLM template block at the bottom of `config/models.yaml`
2. Set `name:`, the model path in `vllm serve /models/<dir>`, `--served-model-name`, and `--dtype`
3. Include `--cudagraph-capture-sizes 1 2 4 8 16 32` and the `.vllm-cache` / `.triton-cache` volume mounts (already in the template) to keep cold starts fast
4. Adjust `--gpu-memory-utilization` and `--max-num-seqs` as needed
5. `llmctl swap <new-profile>` to load and verify
6. Press `r` in llmpanel to reload the profile list without restarting

**GGUF (llama-server):**
1. Copy the GGUF template block from `config/models.yaml`
2. Set the `-m /models/<path>.gguf` argument
3. For split GGUFs (`-00001-of-0000N`), point at part 1 — llama.cpp auto-discovers the rest

---

## Architecture

```
Clients  ──►  llmproxy :9000  ──►  llama-swap :8080  ──►  vLLM container    :910x
                (optional)              (router)       └──►  llama-server      :910x
```

- **llama-swap** runs on the host; one OpenAI endpoint, backends loaded on demand
- Each backend is a rootless podman container with GPU device passthrough
- **llmproxy** is an HTTP shim that fixes vLLM SSE tool-call streaming for `@ai-sdk` clients
- Models swap by `model` field routing; TTL-based auto-unload configurable per profile
- Compilation caches (`.vllm-cache/`, `.triton-cache/`) are mounted into vLLM containers so Inductor kernels survive restarts
- No reverse proxy in default config — clients hit `:8080` (or `:9000` via llmproxy) directly

---

## Smoke test

```bash
# Checks both backends — slow on first run (cold container pull + model load)
./tests/smoke.sh
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Container exits immediately with `invalid argument` | Run `scripts/configure` — `models.yaml` still has `__LLMSTACK_DIR__` placeholders. podman rejects them as invalid volume source paths. |
| `llmctl up` hangs | Check `~/.local/share/llmstack/llama-swap.log` |
| `llmctl swap` times out | First vLLM boot compiles Inductor kernels — up to 20 min; check `llmctl logs <profile>`. Subsequent starts are ~2–3 min (cached). |
| Log shows `exit status 125` | The container failed to start before running. Most likely cause: `/dev/kfd` doesn't exist (ROCm not installed). Run `ls /dev/kfd` — if missing, see [Prerequisites](#prerequisites). Also check `podman images` to confirm the image was pulled. |
| vLLM fails to start | `llmctl logs <profile>`; confirm image exists with `podman images` |
| GGUF model not found | Verify path in `config/models.yaml` matches `/mnt/models/llm/...` |
| GPU not visible in container | Check user is in `video` and `render` groups: `groups` |
| Tool call errors in OpenCode | Use llmproxy (`llmctl proxy-up`); see `docs/workarounds.md` |
| `Expected 'function.name' to be a string` | Same — llmproxy fixes this; point client at `:9000` |

---

## Hardware compatibility

The containers and config in this repo are built for the **AMD Radeon AI PRO R9700 (gfx1201 / RDNA4)**. **1 to 4 GPUs are supported** — `scripts/configure` auto-detects your count and patches `tensor-parallel-size` and `tensor-split` accordingly and hides profiles that cannot run on your machine. The benchmarks in this repo use 4× R9700 (128 GB total); fewer GPUs reduce throughput and limit which models fit. Here is what each backend requires if you want to adapt it to other hardware:

| Backend | Requirement | Notes |
|---------|-------------|-------|
| **vLLM** | ROCm-compatible AMD GPU | Container image is `vllm/vllm-openai-rocm` (ROCm 7.2). Other AMD cards need `HSA_OVERRIDE_GFX_VERSION` set appropriately. NVIDIA requires a CUDA build of vLLM instead. |
| **llama-server (Vulkan)** | Any Vulkan-capable GPU | Works on AMD, NVIDIA, and Intel out of the box. No code changes needed — just point the `-m` path at your GGUF. |
| **llama-swap** | None | CPU-only router; hardware-agnostic. |
| **GPU monitoring** | AMD with `rocm-smi` | `llmpanel` displays `rocm-smi unavailable` gracefully on other platforms. |

### Configuration (required after cloning)

`scripts/configure` must be run once after cloning. It does three things:

1. **Replaces `__LLMSTACK_DIR__`** — `config/models.yaml` ships with this literal placeholder in all volume mount paths. llama-swap executes container commands without a shell, so environment variables like `$HOME` aren't expanded at runtime. `configure` substitutes the placeholder with the absolute path to your repo clone.

2. **Patches GPU count** — auto-detected from sysfs VRAM size (with `rocm-smi` as fallback), or set with `--gpu-count`. What each profile needs is declared in its own `metadata: requires:` block in `config/models.yaml` (`gpus: [2, 4]` for vLLM, `min_gpus: 3` for llama-server, optional `host_ram_gib`; schema in `config/CLAUDE.md`), and `configure` reads it from there.

3. **Hides profiles this machine cannot run** — see [VRAM limits](#configuration-required-after-cloning) below.

```bash
scripts/configure                  # auto-detect GPU count, apply all fixes
scripts/configure --dry-run        # preview the result without writing
scripts/configure --gpu-count 2    # override GPU count (if rocm-smi isn't available)
```

What it adjusts in `config/models.yaml`:

| Setting | What changes |
|---------|-------------|
| `__LLMSTACK_DIR__` | Replaced with the absolute path to this repo (e.g. `/home/alice/ai/llmstack`) |
| `--tensor-parallel-size` | Set to the largest valid TP size (1, 2 or 4) not above your GPU count; TP must divide the model's head counts, so 3 GPUs gives TP2 |
| `--tensor-split` (llama-server) | Set to `1,1,...` matching GPU count (`1` for a single GPU) |
| `--enable-expert-parallel` | Never changed by `configure` |

**VRAM limits** — `qwen3.8-flash-next` (~81 GB) won't fit on fewer than 3 GPUs, and `qwen3.8-flash-next-vllm` needs all 4. The script reports profiles below their minimum GPU count (or host RAM) as `SKIP`. Their `cmd` stays untouched, but they get an auto-managed `unlisted: true  # llmstack:auto - needs gpus [4], detected 2` line, so llama-swap hides them from `/v1/models`. `llmctl list` / `pick` / `swap` apply the same `scripts/llmhw.py` verdict (hidden from the lists; `llmctl swap` refuses them with exit 2 unless `--force`, and they will probably fail to start). That verdict comes only from `metadata.requires`; a hand-written `unlisted: true` or `false` does not change it. Re-running `configure` on a machine where the profile is supported removes only those marker lines. A hand-written `unlisted:` line is never touched or duplicated. Per-profile behaviour on 3, 2 and 1 GPUs, with measured numbers: `docs/gpu-counts.md`.

---

## Files

```
bin/llmctl               CLI lifecycle manager (Python)
bin/llmpanel             Terminal control panel binary (Go, built from tui/)
bin/llmproxy             Streaming shim for @ai-sdk tool-call bug (Python)
config/models.yaml       Model profiles — edit here to add/change models
config/templates/        Custom Jinja chat templates (e.g. no-think variant)
containers/vllm/         vLLM Containerfile
containers/llama-server/ llama-server Vulkan Containerfile
tui/                     Go source for llmpanel
docs/llmctl.md           Full llmctl command reference
docs/models.md           Model benchmark data and tuning notes
docs/gpu-counts.md       Running with fewer than 4 GPUs (valid TP sizes, per-profile limits)
docs/workarounds.md      Known issues and active workarounds
tests/smoke.sh           Smoke test (both backends)
bench/                   Benchmark scripts and saved baselines
bench/baselines/         Saved benchmark JSON files (one per model/config)
.vllm-cache/             Persistent vLLM Inductor compilation cache (gitignored)
.triton-cache/           Persistent Triton kernel cache (gitignored)
```
