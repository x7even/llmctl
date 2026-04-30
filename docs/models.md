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
| `localhost/llmstack-vllm:latest` | 0.10.2rc2 | 7.1.1 | Legacy safetensors, Qwen3-Coder |
| `docker.io/vllm/vllm-openai-rocm:latest` | 0.20.0 | 7.2 | Qwen3.6 (Qwen3_5MoeForConditionalGeneration) |
| `localhost/llmstack-llama:latest` | llama.cpp | Vulkan | GGUF models |

The `vllm-openai-rocm` image has a broken default entrypoint for the `serve`
subcommand; all its profiles use `--entrypoint="" ... vllm serve`.

---

## Profiles

### `qwen3.6-35b-code` — primary coding assistant

**Aliases:** `qwen3.6`, `qwen3.6-35b`, `qwen3.6-35b-fp8`

**Use for:** Claude Code, OpenCode, agentic multi-step coding, any task where
output quality matters more than raw latency.

**Key settings:**
- `--gpu-memory-utilization 0.92` — 8% headroom for MTP draft model overhead
- `--speculative-config '{"method": "mtp", "num_speculative_tokens": 2}'` — Multi-Token
  Prediction using the bundled `mtp.safetensors` draft head. Mathematically
  lossless: the main model verifies every proposed token; only accepted tokens
  appear in output. Disabled tokens never reach the client.
- `--reasoning-parser qwen3` — strips `<think>…</think>` from the `content`
  field and places it in `reasoning_content`. Clients that don't handle
  reasoning_content (like curl) see clean output; clients that do (e.g.
  OpenCode with thinking display) see the chain-of-thought separately.
- Thinking **ON** by default (Qwen3.6 native behaviour). Cannot be overridden
  per-request on this profile — use `qwen3.6-35b-fast` if you need it off.
- Context: 262,144 tokens (native)

**MTP benchmark results (vs baseline FP8, conc=8, medium-256 prompt):**

| Metric | Baseline FP8 | + MTP | Δ |
|---|---|---|---|
| Serial decode tok/s | 77 | 110 | +43% |
| conc=8 decode tok/s | 410 | 626 | +53% |
| conc=8 xlarge-2048 tok/s | 390 | 626 | +61% |

MTP gains are largest on long completions where the draft head can predict
repetitive or predictable tokens (code, prose continuation). Gains are smaller
on highly creative or random outputs.

---

### `qwen3.6-35b-fast` — low-latency general use

**Aliases:** `qwen3.6-fast`, `qwen3.6-nothin`

**Use for:** Quick lookups, chat, summarisation, tasks where TTFT matters and
extended reasoning is unnecessary overhead.

**Key difference from code profile:**
- Thinking **OFF** by default via a custom chat template
  (`config/templates/qwen3.6-no-think.jinja`). The template inverts the
  default condition: thinking only activates if the client explicitly passes
  `chat_template_kwargs: {"enable_thinking": true}`.
- `--gpu-memory-utilization 0.97` — no MTP; reclaims the headroom used by the
  draft model to maximise KV cache.
- No MTP — removes speculative decoding overhead at low concurrency. At
  conc=1, MTP's verification cost slightly hurts throughput for short tasks
  where the draft hit rate is low.

**Why a separate template?** vLLM does not expose a per-request `enable_thinking`
default at the server level; the only way to invert the default is to ship a
modified chat template. The template change is a one-line condition inversion:

```
# stock template (thinks by default):
{%- if enable_thinking is defined and enable_thinking is false %}

# fast template (silent by default):
{%- if enable_thinking is defined and enable_thinking is true %}
```

---

### `qwen3.6-35b-512k` — deep context / large codebase

**Aliases:** `qwen3.6-512k`, `qwen3.6-long`

**Use for:** Ingesting entire repositories, long document QA, tasks that
exceed the native 262K context window.

**Context extension mechanism — YaRN RoPE scaling:**

Qwen3.6's native max is 262,144 tokens. This profile doubles it to 524,288
via YaRN (Yet Another RoPE extensioN), which rescales the RoPE positional
embeddings with a factor of 2.0:

```
--hf-overrides '{"text_config": {"rope_scaling": {
    "type": "yarn",
    "factor": 2.0,
    "original_max_position_embeddings": 262144
}}}'
```

The env var `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1` is also required to bypass
vLLM's safety check (max_model_len > model's native limit).

**Tested:** Needle-in-a-haystack retrieval at 420,000 tokens — correct output
confirmed. Performance at the full 524K edge is expected to degrade slightly
due to YaRN interpolation artefacts, but retrieval remains correct.

**Architecture note — why Qwen3.6 handles long context well:**

Qwen3.6 is a hybrid attention MoE. Only 10 of its 40 attention layers are
full (quadratic) attention; the remaining 30 use linear attention (O(n)
complexity). This means:
- KV cache is only needed for 25% of layers, massively reducing VRAM per token
- Prefill is much cheaper than a pure-transformer of similar size
- 512K context becomes practical where it would OOM on a dense model

**Concurrency limit:** Reduced to 16 (vs 64 for shorter profiles). At 512K
context, a single sequence consumes most of the available KV cache. Running
>16 concurrent 512K sessions simultaneously would OOM.

**MTP:** Included, with 0.92 GPU utilisation to accommodate the draft head.

---

### `qwen3.6-35b-q4ks` — GGUF low-latency serial

**Aliases:** `qwen3.6-gguf`, `qwen3.6-fast` *(note: superseded by vLLM fast profile for concurrent load)*

**Use for:** Single-user interactive sessions where serial latency is the
priority and GPU VRAM is already occupied by another backend.

**Backend:** llama-server (Vulkan/RADV). GGUF UD-Q4_K_S (unsloth quant).
~20 GB across 4 GPUs — generous KV headroom.

**When to prefer over vLLM profiles:**
- Conc=1 sessions: GGUF slightly wins on raw serial tok/s (~83 vs ~77 FP8)
- Memory-constrained: GGUF uses ~15 GB less VRAM than FP8

**When to prefer vLLM profiles:**
- Any concurrent load ≥2: FP8 is 2–2.4× faster at conc=8+
- Code quality: FP8 runs full precision, no quantisation artefacts
- MTP: only available on vLLM backends

**Benchmark: GGUF vs FP8 decode tok/s (2026-04-30)**

| Prompt | GGUF conc=1 | GGUF conc=8 | GGUF conc=12 | FP8 conc=1 | FP8 conc=8 | FP8+MTP conc=8 |
|---|---|---|---|---|---|---|
| short-64    | 80  | 140 | 163 | 77  | 154 | ~200 est. |
| medium-256  | 81  | 169 | 175 | 78  | 410 | 626       |
| long-512    | 83  | 181 | 180 | 76  | 392 | ~600 est. |
| xlarge-2048 | 83  | 189 | 189 | 66  | 390 | 626       |

GGUF conc=12 shows a throughput plateau — llama-server's threading model
doesn't scale beyond ~10–12 parallel sessions. FP8 with PagedAttention
continues to scale.

---

### `qwen3-coder-30b-fp8` — legacy code model

**Aliases:** `qwen3-coder`, `coder`

**Use for:** Kept as a fallback; the original benchmark baseline. Qwen3.6
outperforms this in both quality and concurrency throughput.

**Backend:** `localhost/llmstack-vllm:latest` (vLLM 0.10.2rc2, ROCm 7.1.1).
Model: `/mnt/models/llm/Qwen3-Coder-30B-A3B-Instruct-FP8/`.

**Benchmark (2026-04-29):** Serial ~50 tok/s. conc=32 short: **827 tok/s
(16.6× speedup)** — best raw scaling observed across all models. However,
output quality is lower than Qwen3.6 on complex reasoning.

**Architecture note:** Standard dense MoE (not hybrid linear attention).
Uses `localhost/llmstack-vllm:latest` because it predates the
Qwen3_5MoeForConditionalGeneration architecture that requires vLLM 0.20.0.

---

### `qwen3.5-122b-a10b-q4` and `qwen3.5-122b-a10b-q6`

**Aliases:** `qwen3.5-122b`, `122b` / `qwen3.5-122b-q6`, `122b-q6`

**Use for:** Heavyweight single queries requiring maximum reasoning depth.
Not suited for concurrent serving — KV cache fills 4 GPUs at ~18 GB each.

**Backend:** llama-server Vulkan. Split GGUF across 4 GPUs via `--tensor-split 1,1,1,1`.

| Variant | Quantisation | VRAM | ctx-size | concurrencyLimit |
|---|---|---|---|---|
| q4 | Q4_K_M | ~73 GB | 32768 | 8 |
| q6 | Q6_K   | ~98 GB | 16384 | 6 |

Q6 is higher quality but leaves less KV headroom; context is halved to 16K
to avoid OOM at concurrency 6. Use q4 unless output quality is the bottleneck.

Cold start: ~90–180s (first disk read of 73–98 GB over NVMe).

---

## Tensor parallelism rationale

Neither Qwen3.6-35B-FP8 (31.2 GB) nor Qwen3-Coder-30B-FP8 (31.2 GB) fits
in a single 32 GB R9700. Even if it did, single-GPU throughput would be
memory-bandwidth limited. With TP=4:

- **4× aggregate HBM bandwidth:** ~12.8 TB/s effective (4× ~3.2 TB/s)
- **All-reduce cost:** ~1.5ms per token over PCIe 5.0 — small vs generation time
- **KV cache distributed:** each GPU holds 1/4 of the KV, enabling much larger
  effective batch sizes

Single-GPU serving would only win if the model fit comfortably (say, <25 GB)
and the workload was strictly serial. At conc ≥ 4, TP=4 wins decisively.

---

## FP8 kernel config note

vLLM warns at startup: `Config file not found for device_name=AMD_Radeon_R9700,dtype=fp8_w8a8`.
The R9700 (gfx1201) does not yet have a hand-tuned FP8 GEMM kernel config in
the vLLM kernel registry. vLLM falls back to MI300X defaults, which are
sub-optimal for RDNA4's memory hierarchy. Generating a custom config (via
`python -m vllm.tools.profiler`) is a future tuning opportunity that could
improve throughput by ~10–20%.

---

## Adding a new profile

See the template section at the bottom of `config/models.yaml`. Key steps:
1. Add the YAML stanza (vLLM or llama-server template as appropriate)
2. Set `concurrencyLimit` explicitly — the default of 10 causes 429s under load
3. Run `llmctl list` to verify the profile appears
4. Run `llmctl swap <profile>` to load and warm it up
5. Run `bench/concurrent_bench.py --model <profile> --quick` for a smoke benchmark
