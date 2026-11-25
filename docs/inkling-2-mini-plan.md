# Inkling 2 Mini on llmstack — review and plan (2026-11-25)

Status: **plan only, nothing deployed or downloaded; awaiting review (§5).** Revised
2026-11-25 into two tracks: llama.cpp to get it running, then a vLLM path for agent fleets. This doc reviews Thinking Machines'
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

Why it's interesting here: the model fits on **one** R9700. That's the 20 GB official
checkpoint on vllm-redshift (§2a), or a 17.6 GB 4-bit GGUF. That would give us a strong agentic
coder (coding scores roughly level with Qwen3.8-27B) that leaves three cards free. No current
profile can do that.

---

## 2. Engine feasibility on gfx1201

| Path | Verdict | Why |
|---|---|---|
| **vllm-redshift** (third-party vLLM port, §2a) | **Starting point for the vLLM track (B)** | Built for exactly this card (R9700, gfx1201). Official NVFP4/MXFP8 weights as shipped. Author's numbers on one card: ~78 tok/s decode, 90–134 with DSpark, ~4,600 tok/s prefill, 196K ctx × 2 slots, tools + reasoning + images. Risks in §2a. |
| upstream vLLM | Blocked on this GPU — the base for Track B | Model support merged 2026-11-21 (vllm#69028, needs ≥ 0.35 nightly), NVIDIA kernels only. AMD work is an open PR for Inkling 2 Small on MI355X (#67685, block-scaled MFMA that RDNA4 lacks). No upstream work targets gfx12. |
| Radiance (standalone C++/HIP server, §2b) | Reference only | Serves Inkling on one R9700, text only, at 28.6–35.9 tok/s. Not vLLM, slower than redshift. Useful for its correctness checklist and its requantization measurements. |
| **SGLang** | **Blocked** | AMD support is MI350X/MI355X (gfx950) only; the cookbook says "Other ROCm GPUs refuse at launch". |
| **llama.cpp mainline, Vulkan** | **Track A: get it running; one known gap** | Arch merged (#32217, #32694 adds `inkling2-loop.cpp`), NVFP4 loop-scale fix (#32704, ≥ b12611), FA compact bias (#32740), chat/tool parser (#32381, #32833), reasoning_effort (#32763), DSpark (#32218). **Gap:** the Vulkan port of the compact-bias FA op is an open draft, #32898. #32740 says that without it, "even when FA was on, the model effectively ran a non-FA route, materializing all the intermediate activation tensors" → enormous VRAM. Expect a slow/large fallback on Vulkan until #32898 lands. |
| llama.cpp mainline, HIP | Fallback (needs your call) | HIP shares the CUDA code, so it may already have the compact-bias FA. But HIP llama.cpp is a standing hold in this stack (upgrade-plan-2026-07). Unsloth also ships a `rocm-gfx120X` prebuilt. |
| Tensor-parallel (`-sm tensor`) | Not yet | #32751 open. Layer split (`--tensor-split`) is the only multi-card mode. |

### 2a. `abhinand5/vllm-redshift` — reviewed, the starting point for the vLLM track

A patch series on a pinned upstream vLLM commit (`bf151b7eb1`, 2026-11-21), released per
model with semver tags (`inkling2-mini/v0.2.0` … `v0.5.1`, 2026-11-21 → 23) and a CHANGELOG
that carries numbers. How it gets around the missing hardware: Triton kernels decode NVFP4/MXFP8
experts to fp16 in registers (RDNA4 has no FP4/block-scaled matrix units). Custom Triton
attention handles the relative bias, sinks and L2 clip, with FP8 KV. A tail-only
sliding-window/conv-state manager makes two 196K requests fit. DSpark runs with an FP8 drafter
and adaptive verify. HIP graphs.

Defaults (`models/inkling2-mini/model.env`): `--max-num-seqs 2 --kv-cache-dtype fp8
--kv-cache-memory-bytes 9126805504` (416,701-token pool), `MAX_MODEL_LEN=196608`,
`--reasoning-parser inkling --tool-call-parser inkling --enable-auto-tool-choice`,
`--limit-mm-per-prompt {"image":64}`, DSpark `num_speculative_tokens: 7` (the only value it
supports). Effort per request via `chat_template_kwargs.reasoning_effort`. Its own head-to-head
on R9700 shows llama.cpp (ROCm, Q8_K_XL) at ~31 tok/s decode and 149–522 tok/s prefill. That puts
the GGUF path at roughly ⅓ the decode and 1/9–1/25 the prefill speed. For agent prompts in the
tens of K tokens, prefill is what users feel.

Risks, and how the plan handles them:
- **No LICENSE file**, so no license is granted. OK for evaluation. Ask the author to add one
  before we depend on it, and don't redistribute images built from it.
- **4 days old, one maintainer, ~1 MB of patches** (two open upstream PRs, vllm#67685 and
  #69028, ~490 KB; its own AMD backend, ~240 KB + 115 KB tests). → Build from source at a pinned
  tag rather than pulling `ghcr.io/...:inkling2-mini`. Read `core/` patches (small) in full and
  skim `model/0201`.
- **Own ROCm runtime:** the image ships pip ROCm 10.0 (TheRock) + torch 2.13 + Triton 3.8, and
  warns that a system ROCm 10.1 HIP runtime segfaults. Our host is 10.1, so never bind-mount host
  ROCm libraries into it. Kernel driver only (`/dev/kfd`, `/dev/dri`).
- **`GPU_MAX_HW_QUEUES=2`** is its RDNA4 default (`core/0101`, "37.8 → 59.9 tok/s" vs the HIP
  default of 4). Our root CLAUDE.md makes **`=1` mandatory** for every vLLM profile. The patch
  only sets 2 **when the variable is unset** (`if _ON_RDNA4 and "GPU_MAX_HW_QUEUES" not in
  os.environ`), so our `-e GPU_MAX_HW_QUEUES=1` is honoured. The canary measures 1 vs 2 as a
  plain env A/B over several spawns, the way the rule was established.
- **Single GPU only.** Its args pass all of `/dev/dri` and set `HIP_VISIBLE_DEVICES=0
  ROCR_VISIBLE_DEVICES=0`; set those to the chosen card instead.
- **Container args to translate** (`scripts/docker-args.sh`): `--device /dev/kfd --device
  /dev/dri --group-add video --security-opt seccomp=unconfined --ipc host --shm-size 8g`,
  `-e ROCPROFILER_REGISTER_ENABLED=0` (stops a 100% idle CPU spin), and **one cache volume at
  `/root/.cache`** (vLLM compile cache + Triton kernels). Its first-request Triton JIT is costly:
  65/84/68 tok/s cold vs 91/134/92 warm. llama-swap runs `--rm`, so mount a persistent host dir
  (e.g. `__LLMSTACK_DIR__/.redshift-cache`) at `/root/.cache`, not our usual
  `/root/.cache/vllm` + `/root/.triton/cache` pair, or every swap serves cold. Plus
  `--entrypoint=""` and `useModelName`.
- Every published number is one card and at most two requests. Track B (§4) measures and
  extends that.

### 2b. Radiance (`codeberg.org/StillDeadcode/radiance`) — reviewed: a reference, not the serving path

Not a vLLM fork. It is a standalone C++/HIP inference server for AMD cards (Apache-2.0, very
active, ~20 contributors, OpenAI/Anthropic/llama-server APIs, own `.rad` model containers). It
added Inkling 2 Mini on 2026-11-21 and the DSpark drafter on 2026-11-24. Naming trap: the
"Radiance" in `docs/upgrade-plan-2026-10.md` is a different project
(`magiccodingman/vllm-radiance`, a vLLM image we trialled and dropped).

Its Inkling support is **one card, text only** (`inkling2 serves one rank; run it with --tp 1`),
and it publishes no concurrent-request numbers. Measured by its authors on one R9700:

| Expert weights | Decode, 1 stream | With drafter | Prefill | Expert VRAM |
|---|---|---|---|---|
| NVFP4 as shipped (plain kernel, no WMMA) | 28.6 tok/s | slower (12.6–19.7) | 195 tok/s | ~15 GiB |
| All experts requantized to rotated int8 | 35.9 tok/s | 35.8–78.6 by prompt type | 1,355 tok/s | 23.4 GiB |

Both rows are well under vllm-redshift on the same card (~78 decode, ~4,600 prefill) with the
weights untouched. So it does not replace the vLLM path. What we take from it:

- **A correctness checklist.** `docs/ARCHITECTURES.md` §inkling2 has the exact geometry and a
  "Traps" list (relative-bias clipping, no RoPE, per-pass KV/conv state, tau on full layers only,
  SiTU's raw-gate sigmoid), validated against llama.cpp and a float32 torch golden. Any port we
  write is checked against that list.
- **The exact-arithmetic identity for NVFP4.** Twice an e2m1 magnitude is one of
  {0,1,2,3,4,6,8,12}, so NVFP4 codes expand to int8 (or to E4M3) with no loss. That is what makes
  "use a native RDNA4 matrix instruction without requantizing" possible (§2c).
- **A measured price for requantizing** (§2c).
- **Launch overhead as a lever.** It replays recorded AQL packets (~6 ns per launch vs 0.5–1.3 µs
  for `hipLaunchKernel`, ~1,600 launches per step). vLLM uses HIP graphs for the same purpose;
  worth knowing if step overhead rather than kernels turns out to be the limit.

### 2c. Should we requantize for RDNA4? — No, not as the first move

RDNA4's matrix instructions (WMMA) take fp16, bf16, fp8 (E4M3) and int8. They have no FP4 or
block-scaled form, which is why this question comes up. The evidence says the answer is kernels,
not new weights:

1. **There is nothing clean to requantize from.** Thinking Machines trained the experts natively
   in NVFP4/MXFP8 and released only that. Any new format is a second rounding on top of the
   release (Radiance says so about its own int8 build). The one FP4 microscaling requant we tried
   on this rig (MXFP4 Flash-Next) was 2× faster and failed the quality gate.
2. **The shipped 4-bit codes already run on WMMA without loss.** vllm-redshift decodes NVFP4 in
   registers and feeds the fp16 WMMA. Radiance's slow NVFP4 numbers come from its plain non-WMMA
   kernel, not from the format: its int8 requant bought 7× prefill only because the baseline
   kernel was plain. Redshift's prefill on the original weights is already ~3.4× Radiance's
   requantized figure.
3. **Decode is bound by memory bandwidth, and 4-bit is the smallest form.** Because of the loop a
   decode step re-reads the core experts three times: ~29 GB read per step when every expert is
   touched (a floor of ~50 ms at ~590 GB/s; an estimate from the config, not a measurement). An
   8-bit copy doubles those bytes. It also takes the experts from ~15 GiB to 23–30 GiB, which no
   longer fits one card with a useful KV pool.
4. **Requantizing does not shrink the porting work.** Inkling's loop, per-pass caches, relative
   attention, SiTU activation and routing don't fit stock vLLM FusedMoE in any format. Upstream's
   compressed-tensors experts PR (vllm#69141) has NVIDIA kernels only.

What stays open as a later, optional experiment (B2.4): once the experts are spread over four
cards there is VRAM to spare, and a **lossless in-memory expansion** of NVFP4 to int8/E4M3 at
load time could feed the fp8/int8 WMMA for large prefill batches. No new checkpoint, no quality
question. Only worth trying if the batched expert kernel is the measured bottleneck.

### KV sizing (corrected for the loop)

On the vLLM track, redshift's FP8 KV pool (9.13 GB = 416,701 tokens, 196K × 2) replaces
this estimate. What follows applies to llama.cpp (Track A). ggml-org's card: "Each pass keeps its own KV and convolution cache." So per token:

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
| `thinkingmachines/Inkling-2-Mini` @ `ed40e7d` | safetensors + `mtp.safetensors` | 20.2 GB | **Track B (vllm-redshift).** Official weights as shipped; the revision redshift v0.5.1 pins. |
| `ggml-org/Inkling-2-Mini-GGUF` | `Inkling-2-Mini-IQ4_NL.gguf` | 17.6 GB | **Track A (llama.cpp).** From the implementers. Experts of layers 0–19 IQ4_NL, everything else Q8_0, imatrix. KLD 0.0095 vs BF16. |
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

## 4. Plan (two tracks, gated)

Track A gets the model running and gives us reference outputs. Track B is the goal: a vLLM path
that batches well and has a large KV pool for agent fleets. Nothing in either track touches the
router or the production profiles until its last step.

**Who does what.** Fable plans, reviews each gate and takes the hard kernel/TP debugging. Opus 5.5
writes the code (Containerfiles, podman translation, balancer, bench drivers, patches, config and
doc edits). Each step below is marked **[Opus]**, **[Fable]** or **[measure]** (a bench run either
can drive).

**GPU time.** A1 and B0 need one free card. A2, B1 and B2 need all four, so the production model
is unloaded for those windows (§5.5).

### Track A — llama.cpp Vulkan: get it running

**A0. Prerequisites (no GPU).**
- **[Opus]** Download to `/mnt/models/llm/ggml-org/Inkling-2-Mini-GGUF/`: IQ4_NL + mmproj Q8_0
  (~18 GB), and `unsloth/.../Mainline_Support/dspark-Inkling-2-Mini-Q8_0.gguf_file` renamed
  (~0.5 GB).
- **[Opus]** New `containers/llama-server-inkling/Containerfile`, the `llama-server-qwen4exp`
  pattern: mainline `ggml-org/llama.cpp`, `ARG LLAMA_REF` pinned to the commit of the newest
  release tag on build day (b12720 on 2026-11-25; must be ≥ the 2026-11-24 merge of #32218),
  Vulkan, same Mesa 26 runtime base. A second build arg applies the #32898 patch, giving two tags:
  `localhost/llmstack-llama-inkling:<tag>` and `…:<tag>-fa32898`.
  **Do not rebuild `:latest`** (it is the binary under both gemma4 GGUF profiles; today it is
  build 9903, far too old for this model).

**A1. Single-card canary (one card, side port, by hand).**
```
llama-server -m …/Inkling-2-Mini-IQ4_NL.gguf --mmproj …/mmproj-Inkling-2-Mini-Q8_0.gguf
  -ngl 999 --device Vulkan0 --ctx-size 65536 --parallel 1 --jinja
  --temp 1.0 --top-p 1.0 --top-k 0 --min-p 0.0
  --chat-template-kwargs '{"reasoning_effort":"medium"}'
```
**[measure]** Record:
1. Load: `KV self size`, compute-buffer size and VRAM, with `--flash-attn on`, `off`, `auto`.
   Look for attention ops falling back to CPU. **This decides which image tag we use**: stock if
   flash attention works on Vulkan, `-fa32898` if not.
2. Correctness: `llama-perplexity` on wikitext-2 near ggml-org's 6.8–7.6, not ~130 (the #32704
   symptom).
3. Chat: thinking in `reasoning_content`, no leaked `<|content_*|>` markers; `reasoning_effort`
   none/low/medium honoured.
4. Tools: an OpenAI `tools` request returns parsed `tool_calls`.
5. Vision: `~/.local/share/llmstack/vision-check/vtest.py` against the canary port.
6. Speed: `llama-bench` pp512/tg128, plus serial and conc=4 decode.
7. **Save reference outputs**: greedy completions and top-1 tokens for a fixed prompt set. Track B
   checks every vLLM configuration against these.

**A2. Context from the other cards.** KV is ~32 KiB/token at f16 (§2), so one card holds roughly
390K tokens and the full 1M window needs ~32 GiB of KV, i.e. a second card.
**[measure]** `--tensor-split` over 2 and then 4 cards at `--ctx-size` 262144, 524288 and
1048576. Record what actually fits, and decode tok/s at 2K / 64K / 256K / deepest (every token
crosses cards, three times through the loop core). Run `bench/needle_check.py` at the deepest
size that fits.

**A3. Arms, only on the layout that A2 picks.** **[measure]**
- KV f16 vs q8_0.
- DSpark: `-md dspark… --spec-type draft-dspark --spec-draft-n-max 5 -ngld 99`. Unsloth measured
  1.1–1.2×; it ships only if it wins at conc ≥ 4.
- Reasoning effort low/medium/high on the hard-code tasks under a fixed output cap (the
  Flash-Next runaway check).

**A4. Interim profile.** **[Opus]** `inkling2-mini-gguf` in `config/models.yaml`, modelled on
`gemma4-26b-q8`: `metadata.requires`, explicit `concurrencyLimit`, medium effort default,
sampling flags, `--mmproj`, `--jinja`, `cmdStop`. Plus a `docs/models.md` section with the
measured table and the caveats (reasoning loops, destructive actions, `none` ≠ off). This makes
the model usable while Track B runs. Gate: `bench/codetests` pass rate in the Qwen3.8-27B range.

### Track B — vLLM: batching and a big KV pool

**Where things stand (checked 2026-11-25).**
- Upstream vLLM merged Inkling 2 Mini on 2026-11-21 (#69028): model, loop, DSpark, parsers.
  Kernels are NVIDIA only. It validated TP2 and TP4 there.
- Upstream's AMD work is #67685 (open): Inkling 2 *Small* on MI355X, all-MXFP8, validated at TP4,
  using an instruction RDNA4 lacks. #66943 (open) adds a peer-to-peer all-reduce for MI cards.
- vllm-redshift carries #67685 + #69028 as patches and adds the gfx1201 kernels. Its code keeps
  upstream's multi-GPU structure (experts sharded over the TP group, attention and expert outputs
  all-reduced), but its own docstring says the fused multi-GPU paths "are left out", its image
  pins `HIP_VISIBLE_DEVICES=0`, and nothing above one card or two requests has been measured.
- So the gap to an agent-fleet profile is three things: **batch shapes above 16 rows are
  untuned, multi-card has never run on this GPU, and its KV is FP8-only as far as we can tell.**

**B0. redshift as-is on one card (side port, router untouched).**
- **[Opus]** Clone at `inkling2-mini/v0.5.1`, read the `core/` patches and Dockerfile, build
  `localhost/vllm-redshift:inkling2-mini-v0.5.1` from source with podman. Download the official
  checkpoint at rev `ed40e7d` (~20.2 GB) to `/mnt/models/llm/thinkingmachines/Inkling-2-Mini/`.
  Translate `scripts/docker-args.sh` to rootless podman (§2a list; `--group-add keep-groups`,
  card chosen via `HIP_VISIBLE_DEVICES`/`ROCR_VISIBLE_DEVICES`, persistent `/root/.cache`).
- **[measure]** In this order:
  1. Load: KV pool tokens (expect ~416,701), model memory (~19.8 GiB), startup time.
  2. Function: reasoning split, effort honoured, tool call parsed, vision check.
  3. **Correctness vs Track A's reference outputs** (expect ≥ 97% top-1, redshift's own claim).
  4. Speed at its defaults vs its README (serial, conc 2, a 40K prompt, after warm-up).
  5. **Depth ladder with FP8 KV**: decode tok/s and TTFT at 2K / 16K / 64K / 131K / 190K, plus
     `needle_check`. Stock FP8 KV made attention 4–9× slower on this rig
     (`docs/fp8-kv-cache.md`); redshift's attention kernels read FP8 natively, so this may not
     repeat, but it must be shown. Also establish whether a bf16-KV mode exists at all.
  6. **Concurrency**: `--max-num-seqs` 2 / 4 / 8 / 16 at 30K-token agent-shaped prompts, DSpark
     on and off, aggregate tok/s at conc 1/2/4/8/16. Above 16 rows per step the tuned kernels
     hand over to generic paths (2 sequences with DSpark is already 16 rows).
  7. `GPU_MAX_HW_QUEUES` 1 vs 2, two fresh spawns per arm, long generations included. The value
     2 has never been measured here, and no vLLM profile has run on one card on this rig, so the
     slow-band behaviour is unknown. Calibrate `scripts/llmband` on the winner.
- **Gate:** it works, matches the reference, and step 6 gives a per-card throughput curve. That
  curve is the input to every later decision.

**B1. One replica per card (scale out with no model patch).**
Four containers, one per card, on four ports. Our llama-swap config maps a model name to one
upstream, so this needs a small balancer in front.
- **[Opus]** A sticky balancer (extend `bin/llmproxy` or a sibling script): route by a hash of
  the conversation's opening so each agent keeps hitting the replica that holds its prefix
  cache; least-loaded for new conversations; health checks. A wrapper so llama-swap starts and
  stops the four containers as one profile.
- **[measure]** Aggregate tok/s at conc 8/16/32 against the fleet bar: Flash-Next 204 / 251 /
  460, 35B-nomtp 464 at 8 and 1,209 at 32.
- Limits, known up front: four separate ~417K-token pools, not one; the largest request is still
  196K; a prefix cached on one card is no use to another.
- Expectation (inference from redshift's two-request figure, unverified): 8 concurrent requests
  is 2 per card, the regime it was tuned for.

**B2. Our patch: one engine across four cards.**
What it buys: one batch and one shared KV pool. Experts shard 32 per card, weights drop to
~5 GiB per card, leaving ~25 GiB per card for KV: an estimated ~4M-token pool at FP8, against
417K. Expert memory traffic per step also spreads over four cards.

- **B2.0 [measure] — the go/no-go, before any code.** Cross-card collective cost at Inkling's
  shapes (1 to 256 rows × 2304, bf16) over 2 and 4 cards, inside the redshift container. A step
  has ~96 collectives (2 per layer visit × 48) plus the drafter's. At ≤ ~50 µs each that is
  ≤ 5 ms per step and TP wins; at ~200 µs it eats the gain. In-house evidence it is affordable
  (an inference, not a measurement): the dense 27B already runs TP4 here over PCIe at ~15–25 ms
  per step with a comparable number of collectives.
- **B2.1 [Opus, Fable on review] — bring-up.** TP2, then TP4, on the existing code paths. Remove
  the device pin, keep the opt-in FP8 LM head off (it asserts one rank), fix what breaks in the
  conv-state sharding and the drafter's all-gather. Gate: top-1 agreement with single-card
  output and with Track A's reference; needle check; Radiance's traps list walked item by item.
- **B2.2 [Opus for sweeps, Fable for kernel design] — make large batches fast.** Retune the
  decode-attention plan for 2 KV heads per rank at 8–32 requests; sweep the batched expert
  kernel and the row-GEMV at 64–256 rows; lift the 16-token fusion limits on routing and loop
  messages; set an explicit capture-size list (`1 2 4 8 16 32`). Every tuning is accepted only
  under real serving load (the dense-FP8 lesson: an isolated sweep cost us 50%).
- **B2.3 [Fable] — only if B2.0/B2.1 show collectives dominate.** Fuse the two collectives per
  layer visit into one, or port the peer-to-peer all-reduce from #66943 to gfx1201.
- **B2.4 [measure] — optional.** The lossless in-memory int8/E4M3 expansion from §2c, if the
  batched expert kernel is the bottleneck at prefill.
- **Gate for B2 as a whole:** it beats B1 on aggregate tok/s at conc 16 and 32, or it matches B1
  and delivers the shared pool. If neither, B1 ships and B2 stops.

**B3. Ship. [Opus]**
- Profile `inkling2-mini` (aliases `inkling`, `inkling-mini`) on whichever layout won; B1 and B2
  can both ship if they serve different needs. Mandatory vLLM items, `GPU_MAX_HW_QUEUES` per the
  B0 result (documented if it is not 1), `metadata.requires`, `concurrencyLimit`,
  `--default-chat-template-kwargs '{"reasoning_effort":"medium"}'`, an output-token cap.
- Stability: 30 min of mixed agent traffic and the drafter-OOM check (32 cold 8K requests;
  `--max-num-batched-tokens` if needed, as in `docs/mtp-drafter-oom.md`).
- `docs/models.md` section, baselines under `bench/baselines/`, regenerate
  `docs/benchmark-results-full.md`, `llmctl down && llmctl up`, router check through :8080.

**B4. Keeping it maintainable.**
- redshift has **no LICENSE file** (its patch files carry Apache-2.0 headers). Before we build on
  it, ask the author to add one and offer the multi-card work back (§5.2).
- Upstream is moving under it: the `inkling2/common` refactor (#69724, #61413) will conflict with
  redshift's main patch. Pin, and rebase only at release boundaries.
- Long term the gfx1201 kernels belong upstream or in an out-of-tree plugin. Watch #67685,
  #66943, #69141, and a ROCm vLLM release that names `Inkling2Loop`.

### Watch list
- llama.cpp #32898 (Vulkan FA compact bias, open draft), #32751 (`-sm tensor`, open)
- vLLM #67685, #66943, #69141; redshift releases after v0.5.1
- Radiance: Inkling at more than one rank, or published concurrency numbers
- A TML bf16 or FP8 checkpoint, which would reopen the requantization question

---

## 5. Decisions needed from you

1. **Order of work.** A0–A1 (llama.cpp running on one card) → B0 (redshift on one card) → A2
   (context across cards) → B1 → B2. Recommendation: this order, with A4 (interim GGUF profile)
   as soon as A1–A3 pass, so the model is usable while the vLLM work runs.
2. **Base for our vLLM patch.** (a) Extend vllm-redshift, which already has the gfx1201 kernels
   but no licence; or (b) write our own port on upstream vLLM, reusing only ideas. Recommendation:
   (a), and open an issue on redshift asking for a licence and offering the multi-card work
   upstream. That issue goes out under your GitHub account, so it needs your go-ahead. If the
   author declines or is silent by the time B2.1 starts, fall back to (b).
3. **Requantization.** Recommendation: don't (§2c). Keep the shipped weights; spend the effort on
   kernels and multi-card.
4. **If Vulkan flash attention is broken in A1:** use the `-fa32898` build (stays Vulkan-only),
   or lift the hold on the HIP backend for this one profile. Recommendation: the `-fa32898`
   build.
5. **GPU windows.** Which card is free for A1/B0, and when the production model can be unloaded
   for the four-card steps (A2, B1, B2).

Sources: thinkingmachines.ai/news/inkling-2-mini, thinkingmachines.ai/model-card/inkling-2-mini,
huggingface.co/thinkingmachines/Inkling-2-Mini (config.json, generation_config.json,
chat_template.jinja), recipes.vllm.ai/thinkingmachines/Inkling-2-Mini, SGLang cookbook,
unsloth.ai/docs/models/inkling-2-mini, ggml-org/unsloth/Harsha001 HF repos, github.com/abhinand5/vllm-redshift (v0.5.1), ggml-org/llama.cpp
PRs listed above (states checked with `gh` on 2026-11-25).
