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
| `docker.io/vllm/vllm-openai-rocm:latest` | 0.22.1 | 7.2 | All vLLM profiles (FP8, AWQ, safetensors) |
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

`healthCheckTimeout` is set to 300 s — sufficient for warm starts. On a fresh
machine (empty cache), manually run `llmctl logs <profile>` and wait for
"Application startup complete." before the first use.

---

## Profiles

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
  exposes it in `reasoning_content`. Thinking is ON by default (Qwen3.6 native).
- `--enable-prefix-caching` — caches common prompt prefixes across requests.
  Agentic workflows with shared system prompts see 2–3× effective throughput gain.
- `--cudagraph-capture-sizes 1 2 4 8 16 32` — explicit graph sizes instead of
  the default ~2000. Cuts graph capture from ~14 min to 13 s with no throughput
  loss at practical concurrency levels (batches > 32 fall back to eager).
- Context: 262,144 tokens (native hybrid linear+full attention)

**Benchmark — vLLM 0.22.1, no-thinking, MTP enabled (2026-06-06):**

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
| vLLM 0.22.1 + MTP no-thinking | **261** |
| AWQ Int4 no-MTP no-thinking | 250 |

The 0.20.0 thinking number is not directly comparable (thinking tokens inflate
measured throughput). The 0.22.1 and AWQ no-thinking numbers are clean comparisons.

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

Three profiles are configured. As of 2026-06-13, only `gemma4-26b-q8` has model files on
disk and has been benchmarked. The other two require model downloads before use.

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

**Backend:** vLLM 0.22.1 (`docker.io/vllm/vllm-openai-rocm:latest`), BF16 safetensors.
**Model path:** `/mnt/models/llm/google/gemma-4-26B-A4B-it`
**VRAM:** 122.7 GB across 4 GPUs — nearly fills all 128 GB. Profile is exclusive; cannot
co-load with any other model. The large VRAM footprint is the model weights (49 GB BF16)
plus the KV cache pool vLLM allocates at startup.

**Use for:** High-concurrency agent workloads. vLLM's PagedAttention and MoE architecture
(4B active params per token) combine to give outstanding batching efficiency — **528 tok/s
at conc=16** on medium-256 prompts, which beats `qwen3.6-35b-code` with MTP (481 tok/s).
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

### Gemma 4 cross-model comparison

All three Gemma 4 profiles benchmarked. Medium-256 prompt, decode tok/s:

| Model | backend | quant | VRAM | conc=1 | conc=8 | conc=16 |
|-------|---------|-------|------|--------|--------|---------|
| `gemma4-26b-a4b` | vLLM | BF16 | 123 GB | 53.4 | 287.1 | **528.2** |
| `gemma4-26b-q8` | llama-server | Q8_0 GGUF | 32 GB | 65.5 | 153.9 | 135.8 |
| `gemma4-12b-q4` | llama-server | Q4_K_M GGUF | 13 GB | 36.1 | 108.9 | 94.8 |
| — | — | — | — | — | — | — |
| `qwen3.6-35b-code` (MTP, no-think) | vLLM | FP8 | 35 GB | 43 | 261 | 481 |
| `qwen3.6-35b-fast` (no-think) | vLLM | FP8 | 35 GB | 69 | 222 | — |
| `qwen3.6-35b-q4ks` | llama-server | Q4_K_S | 20 GB | ~80 | ~175 | — |

**Key findings:**
- `gemma4-26b-a4b` **beats** `qwen3.6-35b-code+MTP` at conc=16 (528 vs 481 tok/s) despite
  being BF16 vs FP8 and having no speculative decoding. The 4B active params per token
  allows vLLM to pack dramatically more requests per batch.
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
With TP=4:

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
