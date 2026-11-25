# Inkling 2 Mini on llmstack — review and plan (2026-11-25)

Status: **plan only, nothing deployed or downloaded.** This doc reviews Thinking Machines'
Inkling 2 Mini (released 2026-11-20) against this rig (4× R9700, gfx1201, Vulkan llama.cpp +
ROCm vLLM) and lays out a gated path to a `config/models.yaml` profile plus a `docs/models.md`
entry (the stack's "model card").

---

## 1. What the model is

| | |
|---|---|
| Checkpoint | `thinkingmachines/Inkling-2-Mini`, Apache 2.0, ~20.2 GB (19.5 GB weights + 636 MB DSpark/MTP head) |
| Arch | `Inkling2LoopForConditionalGeneration` / `inkling2_loop`: 24-layer decoder, sparse MoE (8 of 128 experts, no shared expert), **looped**: layers 6–17 run 3× with shared weights → 48 layer evaluations per token |
| Params | 26.4B total, 3.4B active per pass, ~5.4B effective active per token with the loop |
| Attention | Hybrid: 20 sliding-window layers (window 1024) + 4 global (layers 5, 11, 17, 23). 24 Q heads / 8 KV heads, head_dim 128. **No RoPE** — relative-position bias (`d_rel` 16, `rel_extent` 1024), short conv (`sconv_kernel_size` 4), "attention residuals" between blocks |
| Context | up to 1,048,576 (`model_max_length`) |
| Precision | Trained natively: routed experts of layers 0–19 NVFP4, layers 20–23 MXFP8 (config's `quantization_config` only says `modelopt`/`NVFP4`) |
| Input | text + image (23-layer ViT, 40–4096 px per side). Output text only |
| Reasoning | Always on. Template var `reasoning_effort`: `none` 0.0, `minimal` 0.1, `low` 0.2, `medium` 0.7, `high` 0.9 (**default**), `xhigh`/`max` 0.99, or a number. Model card: minimum effort "does not fully disable reasoning" |
| Tools | Own format: `<|content_invoke_tool_json|>{"name":…,"args":{…}}<|end_message|>`; thinking in `<|content_thinking|>`. Parsers: vLLM `inkling`, SGLang `inkling2`, llama.cpp chat parser (#32381, #32833, merged) |
| Sampling | temperature 1.0, top-p 1.0, top-k 0 (off), min-p 0 (generation_config + Unsloth) |
| Spec decode | DSpark drafter (3-layer, 8-token block). vLLM default recipe uses it; llama.cpp #32218 merged 2026-11-24 |

**Benchmarks worth noting for this stack** (model card, vs our current default Qwen3.8-27B):
DeepSWE 48.2% (Qwen3.8-27B 42.2%), Terminal Bench 2.1 71.6% (73.0%), SWE-bench Verified
79.2%, MCP Atlas 82.7%, BrowseComp 79.0%, GPQA-D 86.6%, LongBench v2 66.9%, MRCR v2 8-needle
256–512K 46.4%. Weak spots it states itself: MultiChallenge 50.0%, ComplexConstraints 33.4%
(both behind Qwen3.8-27B), confident hallucination (AA-Omniscience −8.6), weaker non-English.

**Card caveats that matter for agent fleets:**
- "Repetitive reasoning": can loop while debugging. TML recommends capping output tokens and
  agent turns. This is the same failure that made Flash-Next run away at `xhigh`.
- May take destructive actions (delete or overwrite files) without confirmation. Run it sandboxed.
- Compute per token is ~1.6× what "3.4B active" suggests, because of the loop.

Why it's interesting here: a ~17.6 GB 4-bit build fits on **one** R9700. That would give us a
strong agentic coder (coding scores roughly level with Qwen3.8-27B) that leaves three cards free.
No current profile can do that.

---

## 2. Engine feasibility on gfx1201

| Path | Verdict | Why |
|---|---|---|
| **vLLM** | **Blocked — watch item** | Needs vLLM ≥ 0.35 (nightly only, cu130 wheels). Recipe and blog list only NVIDIA (Blackwell, Hopper, DGX Spark). Weights are NVFP4/MXFP8 MoE. AMD's NVFP4 story is QDQ emulation on MI300/MI355, and nothing covers RDNA4. Revisit when a ROCm vLLM release names `Inkling2Loop`. |
| **SGLang** | **Blocked** | AMD support is MI350X/MI355X (gfx950) only; the cookbook says "Other ROCm GPUs refuse at launch". |
| **llama.cpp mainline, Vulkan** | **Primary path, one known gap** | Arch merged (#32217, #32694 adds `inkling2-loop.cpp`), NVFP4 loop-scale fix (#32704, ≥ b12611), FA compact bias (#32740), chat/tool parser (#32381, #32833), reasoning_effort (#32763), DSpark (#32218). **Gap:** the Vulkan port of the compact-bias FA op is an open draft, #32898. #32740 says that without it, "even when FA was on, the model effectively ran a non-FA route, materializing all the intermediate activation tensors" → enormous VRAM. Expect a slow/large fallback on Vulkan until #32898 lands. |
| llama.cpp mainline, HIP | Fallback (needs your call) | HIP shares the CUDA code, so it may already have the compact-bias FA. But HIP llama.cpp is a standing hold in this stack (upgrade-plan-2026-07). Unsloth also ships a `rocm-gfx120X` prebuilt. |
| Tensor-parallel (`-sm tensor`) | Not yet | #32751 open. Layer split (`--tensor-split`) is the only multi-card mode. |

Current image `localhost/llmstack-llama:latest` is **build 9903** — far too old (needs
≥ b12611, and ≥ the 2026-11-24 merge of #32218 for DSpark). Latest release tag today: b12719.

### KV sizing (corrected for the loop)

ggml-org's card: "Each pass keeps its own KV and convolution cache." So per token:

- Global attention evaluations: layer 5 (1) + layers 11, 17 (×3 each = 6) + layer 23 (1) = **8**
- 8 × 8 KV heads × 128 × (K+V) × 2 B = **32 KiB/token at f16** (~17 KiB at q8_0)
- SWA: 40 evaluations × 1024-token window ≈ 160 MiB per sequence, fixed

On one card (31.86 GiB): ~16.4 GiB weights + ~0.6 GiB mmproj + compute buffers → roughly
**12 GiB of KV ≈ 390K tokens f16**. That could be 2 slots × 131K or 4 × 65K. The full 1M window
does not fit on one card at f16. These are estimates: the canary reads the real
`KV self size` and compute-buffer lines from the load log and sizes `--ctx-size`/`--parallel`
from those. If the non-FA fallback is active on Vulkan, the compute buffer could eat most of
that.

---

## 3. Which weights

| Repo | File | Size | Verdict |
|---|---|---|---|
| `ggml-org/Inkling-2-Mini-GGUF` | `Inkling-2-Mini-IQ4_NL.gguf` | 17.6 GB | **Primary.** From the implementers. Experts of layers 0–19 IQ4_NL, everything else Q8_0, imatrix. KLD 0.0095 vs BF16. |
| `ggml-org/Inkling-2-Mini-GGUF` | `mmproj-Inkling-2-Mini-Q8_0.gguf` (346 MB) or BF16 (642 MB) | | Vision tower. |
| `ggml-org/Inkling-2-Mini-GGUF` | `Inkling-2-Mini-Q8_0.gguf` | 27.8 GB | Quality reference. Single card leaves ~3 GiB, so 2-card only. |
| `unsloth/Inkling-2-Mini-GGUF` | `Mainline_Support/Inkling-2-Mini-UD-Q4_K_XL.gguf_file` | 17.6 GB | Alternative A/B arm. **Root-level files are Unsloth's own layout and do not load on mainline.** Use the `Mainline_Support/` copies, renamed `.gguf_file` → `.gguf`. |
| `unsloth/Inkling-2-Mini-GGUF` | `Mainline_Support/dspark-Inkling-2-Mini-Q8_0.gguf_file` | 0.50 GB | DSpark drafter for mainline (#32218 format). The root `dspark-*.gguf` is the old format and is rejected. |

### `Harsha001/Inkling-2-Mini-Uncensored-ROCmFPX` — reviewed, not recommended

Pros: AMD-targeted weight formats (ROCmFP4 experts, 8-bit ROCmFPX elsewhere), 15.5/21.6/26.9 GB
files, the author is active, and the fork now carries the Inkling chat parser.

Against, for this stack:
1. **It is the abliterated model.** AtomicChat's rank-1 refusal-direction removal is merged in
   (the earlier censored files survive only in commit history). The model card already warns
   about unconfirmed destructive actions. Stripping refusals from an agent that holds shell
   access compounds that risk.
2. **Vulkan and ROCm are untested by its own README:** "Only the CPU path has been checked …
   Vulkan and ROCm have not been tried yet."
3. Needs a single-maintainer fork (`HarshaVardhan3002/ROCmFPX`, branch `inkling2-mini`). Its
   files don't load upstream, and upstream files don't load in it. That's the Flash-Next
   `qwen4exp` situation again, but without an upstream merge to converge on.
4. Text only: no vision tower, no drafter.
5. Its stated quality cost is not better than stock: 4-bit KLD 0.0119 vs ggml-org IQ4_NL 0.0095
   (different references, so only indicative).

Worth revisiting only as a speed experiment — ROCmFP4 kernels vs stock IQ4_NL on RDNA4 —
and only if the fork publishes a censored build and Vulkan numbers.

---

## 4. Plan (gated phases)

### Phase 0 — prerequisites (no GPU)
- Download to `/mnt/models/llm/ggml-org/Inkling-2-Mini-GGUF/`: IQ4_NL + mmproj Q8_0 (~18 GB),
  and `unsloth/.../Mainline_Support/dspark-Inkling-2-Mini-Q8_0.gguf_file` renamed (~0.5 GB).
  1 TB free on `/mnt/models`.
- New `containers/llama-server-inkling/Containerfile`, a copy of the `llama-server-qwen4exp`
  pattern: mainline `ggml-org/llama.cpp`, `ARG LLAMA_REF` pinned to the b12719 commit, Vulkan,
  same Mesa 26 runtime base. Tag `localhost/llmstack-llama-inkling:b12719`.
  **Do not rebuild `:latest`.** That would also swap the binary under both gemma4 GGUF profiles.

### Phase 1 — Vulkan canary (single card)
Run by hand on GPU 0, router untouched:
```
llama-server -m …/Inkling-2-Mini-IQ4_NL.gguf --mmproj …/mmproj-Inkling-2-Mini-Q8_0.gguf
  -ngl 999 --device Vulkan0 --ctx-size 65536 --parallel 1 --jinja
  --temp 1.0 --top-p 1.0 --top-k 0 --min-p 0.0
  --chat-template-kwargs '{"reasoning_effort":"medium"}'
```
Record from the log and a few requests:
1. Does it load? Note the `KV self size`, compute buffer size and VRAM used, with
   `--flash-attn on`, `off` and `auto`. Look for FA ops falling back to CPU.
   **This decides whether we wait for #32898.**
2. Correctness: `llama-perplexity` on wikitext-2 should land near ggml-org's 6.8–7.6 range, not
   ~130 (the #32704 symptom).
3. Chat: thinking returned in `reasoning_content` with no leaked `<|content_*|>` markers.
   `reasoning_effort` none/low/medium honoured.
4. Tools: one OpenAI `tools` request returns a parsed `tool_calls`, not raw JSON in `content`.
5. Vision: `~/.local/share/llmstack/vision-check/vtest.py` against the canary port.
6. Speed: `llama-bench` pp512/tg128, plus serial and conc=4 decode tok/s.

Gate: if FA on Vulkan blows up VRAM or runs on CPU, either (a) build with #32898 cherry-picked
as a second canary arm, or (b) take the HIP fallback (your decision, §5), or (c) wait for
#32898 to merge.

### Phase 2 — layout and arms
- Single card vs `--tensor-split 1,1,1,1` layer split (more KV and context, but every token hops
  cards, 3× through the loop core). Measure both at conc 1/4/8.
- KV f16 vs q8_0 (q8_0 V needs working FA).
- DSpark arm: `-md dspark… --spec-type draft-dspark --spec-draft-n-max 5 -ngld 99`. Unsloth
  measured only 1.1–1.2×, and n-max 2 was slower than no drafter. MTP-off has beaten MTP-on on
  this rig before, so DSpark ships only if it wins at conc ≥ 4.
- Reasoning effort: run `bench/` hard-code tasks (`docs/hard-code-tasks.md`) at low/medium/high
  under a fixed output cap. This is the Flash-Next runaway check.

### Phase 3 — the model card
- `config/models.yaml` profile `inkling2-mini` (aliases `inkling`, `inkling-mini`), llama-server
  stanza modelled on `gemma4-26b-q8`:
  - `metadata.requires`: `min_gpus: 1`, `estimate: true` until measured, plus a `note`
  - explicit `concurrencyLimit` (= `--parallel`)
  - `--chat-template-kwargs '{"reasoning_effort":"medium"}'` (template default is high/0.9)
  - sampling flags as above, `--mmproj`, `--jinja`
  - container name `llmstack-llama-${MODEL_ID}`, `cmdStop`
  - header comment with weights, layout, FA status and caveats
- `docs/models.md` section: purpose, architecture summary, the KV-per-pass note, measured
  table, caveats (reasoning loops, destructive actions, `none` ≠ off), client notes for dsh
  `input: [text, image]`.
- Baseline: `bench/concurrent_bench.py --model inkling2-mini --sweep 1,2,4,8 --prompt all
  --save bench/baselines/inkling2-mini.json`, then regenerate `docs/benchmark-results-full.md`.
- `llmctl down && llmctl up`, router check through :8080 (alias + vision + tools).

### Phase 4 — watch list
- llama.cpp #32898 (Vulkan FA compact bias), #32751 (`-sm tensor`), #32777 (looped-MoE fit)
- vLLM ROCm release naming `Inkling2Loop`, and NVFP4/MXFP8 MoE on gfx12
- A TML BF16/FP8 checkpoint (would open the vLLM FP8 path that the 35B/27B profiles already use)

---

## 5. Decisions needed from you

1. **Layout:** single card (leaves 3 GPUs free, ~390K tokens of KV) or 4-card layer split
   (more context, likely slower per token)? Recommendation: single card first, measure split second.
2. **Backend if Vulkan FA is broken:** wait for #32898 / cherry-pick it (stays Vulkan-only),
   or lift the HIP hold for this one profile? Recommendation: cherry-pick #32898 as a canary
   arm. Lift the HIP hold only if that fails.

Sources: thinkingmachines.ai/news/inkling-2-mini, thinkingmachines.ai/model-card/inkling-2-mini,
huggingface.co/thinkingmachines/Inkling-2-Mini (config.json, generation_config.json,
chat_template.jinja), recipes.vllm.ai/thinkingmachines/Inkling-2-Mini, SGLang cookbook,
unsloth.ai/docs/models/inkling-2-mini, ggml-org/unsloth/Harsha001 HF repos, ggml-org/llama.cpp
PRs listed above (states checked with `gh` on 2026-11-25).
