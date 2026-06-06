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
