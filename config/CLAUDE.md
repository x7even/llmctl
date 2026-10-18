# config/ — models.yaml editing guide

`config/models.yaml` is the single source of truth for all model profiles.
llama-swap reads it at startup — changes require `llmctl down && llmctl up` to take effect.
Do NOT rely on hot-reload; llama-swap caches the config in memory.

---

## Schema overview

```yaml
version: 2
healthCheckTimeout: 300          # seconds; 300 is for warm starts
models:
  - name: <profile-id>           # used as OpenAI "model" field
    aliases:
      - <short-name>
    ttl: 0                       # seconds before auto-unload; 0 = never
    concurrencyLimit: 16         # max parallel requests before 429
    proxy:
      - url: http://127.0.0.1:<port>
        cmdType: pod              # "pod" = rootless podman
        cmd: podman run ...       # container launch command
```

`healthCheckTimeout` applies globally (not per-model). 300 s is adequate for warm vLLM
starts (~2–3 min). For a machine with no `.vllm-cache/` yet, watch manually with
`llmctl logs <profile>` — the first compile takes ~18 min.

---

## Mandatory settings for every vLLM profile

Every vLLM profile **must** have all five of these. Omitting one of the first three will
cause an 18+ minute startup or a startup failure; omitting the fourth leaves the profile
reachable only by its full name; omitting the fifth can leave it serving at half speed with
nothing in the logs to say so.

### 1. Override the broken AMD entrypoint

```yaml
cmd: podman run --rm --entrypoint="" \
  ... \
  docker.io/vllm/vllm-openai-rocm:v0.26.0 \
  vllm serve /models/<dir> ...
```

The AMD official image (`vllm/vllm-openai-rocm`) has `ENTRYPOINT ["vllm", "serve"]`.
Without `--entrypoint=""` plus an explicit `vllm serve` prefix, the command becomes
`vllm serve serve /models/...` which fails with "unrecognized arguments".

### 2. Explicit CUDA graph sizes

```yaml
--cudagraph-capture-sizes 1 2 4 8 16 32
```

Without this, vLLM's default formula generates ~2000 batch sizes to capture.
At ~5 ms each = 10+ minutes just for graph capture, every startup.
With 6 explicit sizes = 13 s capture.

**With speculative decoding the list is not the list you get.** `adjust_cudagraph_sizes_for_spec_decode`
(`vllm/config/compilation.py`) rounds every requested size *up* to a multiple of
`num_speculative_tokens + 1`, and **drops** any result that exceeds the largest size you asked
for — which is itself what sets `max_cudagraph_capture_size`. With MTP at
`num_speculative_tokens: 2` the multiple is 3, so `1 2 4 8 16 32` becomes `{3, 6, 9, 18}`:
32 rounds to 33, 33 > 32, and it is silently dropped. Four graphs survive, the largest at
18 query-tokens = **6 sequences**. The ceiling moves too — the function ends with
`max_cudagraph_capture_size = rounded_sizes[-1]`, so it collapses from 32 to 18 — and
`cudagraph_dispatcher.dispatch` returns `CUDAGraphMode.NONE` for `num_tokens > max_size`
*before* testing the piecewise key set. So there is no piecewise fallback: above 6 concurrent
requests the step is fully eager.

**That cliff reads like a bug, and fixing it has been measured as a loss. Do not "fix" it.**
A list of multiples of 3 round-trips through the transform unchanged and does cover all 32
sequences — and it is slower. Seven interleaved arms on the 27B MTP profile, `medium-256`,
`--no-thinking`, 32 requests:

| `--cudagraph-capture-sizes` | conc=8 | conc=16 | KV tokens | graph mem |
|---|---|---|---|---|
| `1 2 4 8 16 32` (shipped, ×3) | **207.3** | **358.4** | 260,406 | 0.70 GiB |
| `3 6 12 24 48 96` (×2) | 193.4 | 334.4 | 245,015 | 0.99 GiB |
| `3 6 9 12 15 18 21 24 30 36 42 48` (×2) | 192.4 | 331.8 | 225,280 | 1.78 GiB |

Both aligned lists lose ~6–7% at exactly the concurrencies they were supposed to help, and pay
6–14% of the KV budget for it.

Graph padding is not the explanation, and could not have been: a captured graph runs at its
captured size, but with MTP the steady-state step is 8 × 3 = 24 query-tokens at conc=8 and 48 at
conc=16, and both 24 and 48 are exact members of *both* aligned lists. Neither list padded at the
points measured — the loss shows up with no padding at all. (The dense list was run to vary
padding granularity and is therefore uninformative about it; what it does show is that the loss
reproduces across two quite different lists.)

What the two losing lists share is that they capture graphs *above* 6 sequences, so conc=8/16 run
as full-graph replays where the shipped list has already fallen through to eager — and here eager
is the faster path. The `qwen3.8-flash-next-vllm` exception below is a more extreme case of the
same effect, not an unrelated quirk.

Measured at TP2 on this hardware; a TP4 re-check is still owed, and `conc=1` was flat across all
seven arms (34.2–34.8) as the internal control, since batch 1 rounds to captured size 3 either way.

Graph memory is taken *before* the KV cache is sized, so a longer list always buys concurrency out
of the KV budget; price any change with `scripts/llmkv` rather than assuming it is free.
Non-speculative profiles are unaffected and `1 2 4 8 16 32` means what it says.

**Measured exception:** `qwen3.8-flash-next-vllm` uses `1 2 4 8` because larger captured
sizes cut its single-stream decode by 30–50% (see docs/models.md). Keep an explicit short
list either way; never omit the flag.

### 3. Persistent cache volume mounts

```yaml
-v __LLMSTACK_DIR__/.vllm-cache:/root/.cache/vllm
-v __LLMSTACK_DIR__/.triton-cache:/root/.triton/cache
```

These cache the Inductor torch.compile output (~14 min per TP rank on first boot).
Without the mounts, every restart re-compiles from scratch.
The cache dirs are gitignored but must physically exist on the host before first use:
```bash
mkdir -p .vllm-cache .triton-cache
```
They are created automatically by `llmctl up` if missing.

**Note**: llama-swap v223+ runs cmd without a shell — environment variables are NOT expanded.
Use `__LLMSTACK_DIR__` as a placeholder in cmd strings; `scripts/configure` replaces it
with the actual absolute path at setup time. Only `${MODEL_ID}` and `${PORT}` are
substituted by llama-swap itself at runtime.

### 4. `useModelName`

```yaml
    useModelName: <profile-id>     # must equal this profile's --served-model-name
```

A llama-swap key, not a vllm flag — it sits beside `aliases`, not inside `cmd`. It sets the
`model` string llama-swap sends to the backend.

Without it **every alias of the profile is a 404**, which is easy to miss because the profile
itself works. llama-swap resolves an alias to decide which backend to route to, then forwards
the client's `model` string upstream unchanged; vLLM answers only to `--served-model-name` and
rejects anything else. The error therefore comes back in vLLM's shape, from a backend that is
up and healthy:

```
{"error":{"message":"The model `qwen3.8` does not exist.","type":"NotFoundError","code":404}}
```

Measured 2026-10-17 on this stack: 3 of the 4 routing names for `qwen3.8-27b-code` failed
(canonical name passed, all three aliases 404'd); with `useModelName` all 4 pass. `llmctl swap
<alias>` *appears* to work either way, because llmctl resolves the alias locally to choose the
profile — but its readiness probe asks the router for the alias, which is why a healthy model
could still print `WARNING: no response from '<alias>'`.

Keep it equal to `--served-model-name`. The llama-server/GGUF profiles do not need it
(llama-server does not validate the `model` field the same way), and they do not set it.

### 5. `-e GPU_MAX_HW_QUEUES=1` — on gfx1201, treat this as mandatory too

```yaml
        -e GPU_MAX_HW_QUEUES=1
```

A container env var, next to `-e HSA_ENABLE_SDMA=0`. Without it a gfx1201 vLLM container can
come up in a **slow decode band** and stay there for the life of the process: the same compiled
graphs and the same kernels, separated by ~15 µs of idle per launch instead of ~3 µs, serving at
roughly half speed. Nothing in the logs says so, `gpu_busy` sits at 100%, and MTP acceptance is
unchanged — so it is invisible unless you benchmark or run `scripts/llmband`.

Measured same-day on this rig, 4× R9700 TP4, `qwen3.8-27b-code`, `v0.26.0`, `medium-256`,
`--no-thinking`, `--requests 32`, varying nothing but this one variable:

| | stock | with the flag | stored baseline |
|---|---|---|---|
| draws | 5/5 slow | 3/3 fast | — |
| serial | 35.6 | **67.2** (1.89×) | 66.5 |
| conc=1 | 35.1 | 66.0 (1.88×) | 65.6 |
| conc=2 | 64.4 | 113.1 (1.76×) | 113.1 |
| conc=4 | 119.6 | 186.7 (1.56×) | 194.2 |
| conc=8 | 320.9 | **357.6** (1.11×) | 365.3 |
| conc=16 | 460.5 | **536.8** (1.17×) | 545.9 |
| `mem_busy` under load | 26% | 46% | 46% |

The penalty is a fixed per-step tax, so it **amortises with batch size** — 1.89× on one stream,
1.11× at conc=8. Do not quote "1.9×" for a saturated server. The flagged arm lands within 4% of
the stored baseline at every level, so the flag itself costs nothing measurable. It is set on the three
`qwen3.8-27b-*` profiles, and on the template at the bottom of `models.yaml`.

**It is deliberately NOT set on Flash-Next, and that is now a measurement rather than an
omission.** A matched pair on 2026-10-18 (same profile and image either side, flag confirmed in
the container with `podman inspect`, `medium-256`, `--no-thinking`, 16 requests per level):

| arm | serial | conc=8 | `mem_busy` | steps/s |
|---|---|---|---|---|
| stock | **55.6** | 187.4 | 32.4% | 58.4 |
| `GPU_MAX_HW_QUEUES=1` | 53.5 | **197.2** | 30.6% | 54.3 |

Serial −3.8%, conc=8 +5.2% — both inside this profile's own session spread, and both arms landed
at or above the best stored conc=8 figure (182), so neither was a slow draw to begin with. The
decisive column is `mem_busy`: ~31% on both arms, where the 27B's two bands separate cleanly at
26% against 46% with no overlap. There is no band to fix here, so the flag is not shipped on
this profile.

Be careful what this does and does not establish. The stock spawn was already fast, so the pair
answers "is the flag *needed* on this profile" — no — and not "does the flag work on this
model", which would need a slow stock draw to recover from and none occurred. **The cause is not
established.** Flash-Next differs from the 27B in two ways at once: it is a 6B-active MoE rather
than a dense GDN hybrid, *and* it runs the nightly image rather than v0.26.0. Either could
explain the absence of a band, and this pair cannot separate them.

**The 35B and gemma4 profiles remain unmeasured.** Measure before adding it there — the
Flash-Next result above is the reason to measure rather than assume. Give any *new* vLLM profile
the flag from the start, since the downside is bounded (a few percent on one stream) and the
upside is a silent 2×.

Two detection notes, both learned the hard way:

- **MTP acceptance is not a band signal.** Slow draws read both 2.349 and 2.246 accepted
  tokens/step; the fast draws read 2.246. Keying on acceptance calls a fast server slow.
- **`llmband` warms up before measuring, and must.** A server's first decode after startup runs
  ~12% below steady state (4/4 cold probes 31.5–31.7 steps/s, 4/4 warm probes on the same
  containers 36.2), which is the same order as its slow-band tolerance. Comparing a cold probe
  against a warm-calibrated baseline made every healthy spawn read `undecided`. Fixed in
  `scripts/llmband` (`--warmup-tokens`, default 128). If you recalibrate, the baseline and the
  checks must both be warmed the same way — which they now are by default.

Full write-up, including what was ruled out: `docs/rdna4-decode-bands.md`.

---

## Critical incompatibilities

### AWQ + expert-parallel = IndexError crash

**Never add `--enable-expert-parallel` to an AWQ profile.**

```yaml
# WRONG — will crash at startup
--quantization awq
--enable-expert-parallel    # ← REMOVE THIS for AWQ

# CORRECT
--quantization awq
# (no expert-parallel)
```

AWQ MoE layers use a Triton WNA16 kernel that is incompatible with expert parallelism.
Symptom: container starts then crashes with `IndexError: index 3 is out of bounds for
dimension 1 with size 1`. FP8 profiles can keep `--enable-expert-parallel`.

### Do not use localhost/llmstack-vllm:latest

This image (vLLM 0.10.2rc2) is broken with transformers 5.x — crashes with
`AttributeError: 'Qwen3Config' object has no attribute 'all_special_tokens_extended'`.

All vLLM profiles must use the same **pinned** tag: `docker.io/vllm/vllm-openai-rocm:v0.26.0`.
Never reference the moving `:latest` tag — it silently changes what vLLM version
production runs. Version bumps happen deliberately: canary first, then update the
pin everywhere at once (models.yaml, this file, root CLAUDE.md, scripts/) — see
docs/upgrade-plan-2026-07.md (v0.26.0) and docs/upgrade-plan-2026-10.md (v0.31.0 canary,
held). Rollback anchor: `localhost/llmstack-vllm-rollback:v0.26.0` (older anchors pruned 2026-10).

### MTP requires the draft head file

Speculative MTP (`--speculative-config '{"method":"mtp","num_speculative_tokens":2}'`)
requires `mtp.safetensors` to be bundled with the model weights. Not all checkpoints
include it. If the file is missing, vLLM logs an error and falls back to standard decode.
The official Qwen3.8-27B-FP8 and Qwen3.6-35B-A3B-FP8 checkpoints include it; raw PT files may not.

### GGUF qwen35moe in vLLM: not supported

`ValueError: GGUF model with architecture qwen35moe is not supported yet.`
Use llama-server (Vulkan) for all GGUF files. Use vLLM for safetensors only.

### Pinned host RAM: keep `scripts/llm-prestart` in front of podman

`qwen3.8-flash-next-vllm` pins ~48 GiB of host RAM; started with the page cache full it runs at half
speed for its whole life. Its `cmd` begins `__LLMSTACK_DIR__/scripts/llm-prestart --need-free-gib 80
--keep <model dir> -- podman run ...`. The path must be absolute because llama-swap runs `cmd` without
a shell, so it takes the `__LLMSTACK_DIR__` placeholder that `scripts/configure` substitutes — the same
rule as the cache mounts, not an exception to it. Do not remove it, and give any new
profile that pins a large host buffer the same wrapper. See `docs/flash-next-half-speed.md`.

### Per-profile chat-template defaults

Use `--default-chat-template-kwargs '<json>'` to set server-side template defaults
(the Qwen3.8-27B profiles use it: `{"reasoning_effort": "medium"}` for the thinking profiles,
`{"enable_thinking": false}` for `-fast`). It is merged with each request's own
`chat_template_kwargs`, and the request wins — so clients can still override per call.

---

## Profile requirements (metadata.requires)

Every profile declares what hardware it can run on, in a `metadata:` block placed directly
after `ttl:` (same position in every profile). It is the **single source of truth** for GPU
and host-RAM requirements: `scripts/configure` has no in-code table any more.

```yaml
    metadata:
      requires:
        gpus: [2, 4]          # vLLM: allowed GPU counts (valid tensor-parallel sizes)
        # min_gpus: 3         # llama-server (GGUF) instead: works on any count >= N
        host_ram_gib: 96      # optional: system RAM the profile needs
        vram_total_gib: 75    # optional, informational: approx GPU memory across all cards
        estimate: true        # present only when the numbers are not measured on this rig
        note: "short human reason"   # optional, one line
```

| Field | Meaning |
|-------|---------|
| `gpus` | Flow list of GPU counts the profile can run at. For vLLM these are valid `--tensor-parallel-size` values (head counts and vocab must divide evenly). With N cards the largest listed count <= N is used (3 cards and `[2, 4]` gives TP2, one card idle); no such count means the profile is unsupported. Mutually exclusive with `min_gpus`. |
| `min_gpus` | llama-server (GGUF) profiles: supported when the GPU count is >= N. `--tensor-split` simply follows the count, there is no divisibility rule. Mutually exclusive with `gpus`. |
| `host_ram_gib` | System RAM needed (pinned host buffers, offloaded tables). Not supported when host RAM is known and below 0.92 x this value; unknown RAM is not a failure. |
| `vram_total_gib` | Approximate GPU memory the profile holds across all cards. Informational only, never used to gate. |
| `estimate` | `true` = derived from checkpoint sizes, not run at the reduced GPU count on this rig. Drop it (and say what was measured in `note`) once someone has run the profile. Tools show estimated requirements as such. |
| `note` | One line of why: the measured failure or the size arithmetic. |

Format rules (a line-oriented regex parser, Go `yaml.v3` and llama-swap must all read the
block identically): one key per line, plain scalars and flow-style lists only, double-quote
the `note`, no anchors, no multi-line values. llama-swap v235 accepts `metadata:` (an
arbitrary map, exposed in `/v1/models` as `meta.llamaswap.requires`) but **rejects other
unknown per-model fields**, so the block must live under `metadata:`, never at profile top level.

**Rule: every new profile must declare `requires`.** A profile without one is treated as
runnable anywhere (unknown is permissive) and tools flag it. Check the values against the
profile's actual `cmd` (`--tensor-parallel-size`, `--tensor-split`, `--ulimit memlock`) and
`docs/gpu-counts.md`; if the cmd and the requirements disagree, fix one of them.

### Who uses it

- `scripts/configure` reads it: picks the TP size (largest `gpus` entry <= detected count),
  sizes `--tensor-split` for `min_gpus` profiles, and reports profiles that cannot run
  (including host-RAM shortfalls). Hardware detection and the support check live in
  `scripts/llmhw.py` (`detect()`, `supports()`, `parse_requires()`).
- `llmctl` reads it through `scripts/llmhw.py`: `llmctl hw` prints the verdict per profile,
  `llmctl list` / `pick` hide unsupported profiles (`--all` shows them), and `llmctl swap`
  refuses them with exit 2 unless `--force`. It fails open (no llmhw, no detected GPU count,
  or a profile without `requires` means allowed). `LLMSTACK_GPU_COUNT=N` / `--gpu-count N`
  simulate a different rig. See `docs/llmctl.md`.
- `llmpanel` reads it too (`tui/config.go` parses it, `tui/hw.go` is a Go port of
  `scripts/llmhw.py` kept in step by `tests/fixtures/llmhw_cases.json`). The Models panel lists
  only runnable profiles, `a` shows the rest greyed with the reason, and a swap of an
  unsupported profile is refused (the panel points at `llmctl swap --force`). It fails open
  like `llmctl`, and honours `--gpu-count` / `LLMSTACK_GPU_COUNT`. Every consumer
  (`scripts/configure`, `llmctl`, `llmpanel`) is now wired.
- llama-swap exposes it as `meta.llamaswap.requires` on `GET /v1/models`, so clients can read it.

### `unlisted: true  # llmstack:auto` lines

For each profile that cannot run at the detected (or `--gpu-count`) count, `scripts/configure`
maintains one line directly under the profile's other top-level keys:

```yaml
    unlisted: true  # llmstack:auto - needs gpus [4], detected 2
```

`unlisted: true` hides the profile from `/v1/models` only; `llmctl list` / `pick` hide it too
and `llmctl swap` refuses it (exit 2 unless `--force`) because they apply the same llmhw verdict
from `metadata.requires`. A hand-written `unlisted: true` or `false` does not change that
verdict. On a
later run where the profile becomes supported (more GPUs, `--gpu-count` raised), configure
removes **only** lines carrying the `llmstack:auto` marker. A hand-written `unlisted: true`
without the marker is never touched, and a profile that is hand-unlisted and unsupported does
not get a second line; if a marker line is already there when a hand-written `unlisted:` line
appears, configure drops the marker so the profile never has two `unlisted:` keys (a duplicate
key is invalid YAML). A hand-written `unlisted: false` also wins: the unsupported profile stays
listed and configure prints a warning. The profile's `cmd` block is not modified for
unsupported profiles, and the file's line endings (LF or CRLF) are preserved.

---

## Template for a new vLLM profile

> **This template is behind the live schema** — it still shows the `- name:` / `proxy:` /
> `cmdType: pod` form, while `config/models.yaml` now keys profiles directly under `models:`
> with `cmd: |` inline and `--group-add keep-groups`. Copy the template at the **bottom of
> `config/models.yaml`** instead; it is the one that is kept in step with the working file.
> Use the list below only as the checklist of keys a profile needs.

```yaml
  - name: <profile-id>
    aliases:
      - <short-alias>
    useModelName: <profile-id>        # == --served-model-name, or every alias 404s
    ttl: 0
    metadata:                         # required, see "Profile requirements" above
      requires:
        gpus: [2, 4]                  # valid tensor-parallel sizes for this model
        estimate: true                # remove once measured on this rig
        note: "why these counts"
    concurrencyLimit: 32
    proxy:
      - url: http://127.0.0.1:9200        # pick a free port
        cmdType: pod
        cmd: |
          podman run --rm --entrypoint="" \
            --name llmstack-vllm-<profile-id> \
            --device /dev/kfd \
            --device /dev/dri \
            --group-add video \
            --group-add render \
            --ipc host \
            --shm-size 16g \
            -p 9200:8000 \
            -v /mnt/models/llm:/models:ro \
            -v __LLMSTACK_DIR__/.vllm-cache:/root/.cache/vllm \
            -v __LLMSTACK_DIR__/.triton-cache:/root/.triton/cache \
            docker.io/vllm/vllm-openai-rocm:v0.26.0 \
            vllm serve /models/<model-dir> \
              --served-model-name <profile-id> \
              --tensor-parallel-size 4 \
              --dtype float16 \
              --kv-cache-dtype fp8 \
              --enable-expert-parallel \
              --enable-prefix-caching \
              --gpu-memory-utilization 0.95 \
              --max-num-seqs 32 \
              --cudagraph-capture-sizes 1 2 4 8 16 32 \
              --port 8000
```

After adding a profile:
1. `llmctl down && llmctl up`
2. `llmctl swap <profile-id>`
3. `llmctl logs <profile-id>` — watch for "Application startup complete."
4. Run a quick benchmark: `python3 bench/concurrent_bench.py --model <id> --no-thinking`

---

## Template for a new llama-server (GGUF) profile

```yaml
  - name: <profile-id>
    aliases:
      - <short-alias>
    ttl: 0
    metadata:                         # required, see "Profile requirements" above
      requires:
        min_gpus: 1                   # works on any count >= N (tensor-split follows the count)
        estimate: true                # remove once measured on this rig
        note: "why this minimum"
    concurrencyLimit: 8
    proxy:
      - url: http://127.0.0.1:9300        # pick a free port
        cmdType: pod
        cmd: |
          podman run --rm \
            --name llmstack-llama-<profile-id> \
            --device /dev/kfd \
            --device /dev/dri \
            --group-add video \
            --group-add render \
            -p 9300:8080 \
            -v /mnt/models/llm:/models:ro \
            localhost/llmstack-llama:latest \
            --host 0.0.0.0 --port 8080 \
            -m /models/<path>.gguf \
            -ngl 99 \
            --tensor-split 1,1,1,1 \
            -c 32768 \
            -np 8
```

For split GGUF files (`model-00001-of-00003.gguf`), point at part 1 only —
llama.cpp auto-discovers the remaining parts.

---

## Common per-profile tuning knobs

| Flag | What it does | When to change |
|------|-------------|----------------|
| `--max-num-seqs` | Max concurrent sequences in flight | Lower if OOM; raise if throughput limited and VRAM free |
| `--gpu-memory-utilization` | Fraction of VRAM reserved for KV cache | Lower if OOM; keep at 0.95–0.97 normally. Exception: `qwen3.8-flash-next-vllm` stays at 0.90 (0.97 stalls under concurrent 100K prompts; see docs/models.md) |
| `--max-num-batched-tokens` | Prefill chunk size, and the size of an MTP drafter's per-batch buffer | **16384 on MTP profiles serving Qwen3.8-27B** (`qwen3.8-27b-code`, `qwen3.8-27b-fast`); 32768 elsewhere. See below |
| `--kv-cache-dtype fp8` | Store KV tensors in FP8 | **Not a default — see below.** Only `qwen3.6-35b-fast` sets it today |
| `concurrencyLimit` | Queue depth before 429 | Set to `--max-num-seqs` or slightly above |
| `ttl` | Seconds before auto-unload | 0 = never; useful for infrequently used profiles |
| `--enable-prefix-caching` | Cache prompt prefixes across requests | Leave on for all profiles |
| `--enable-expert-parallel` | Distribute MoE experts across GPUs | ON for FP8/dense profiles; OFF for AWQ |
| `--speculative-config` | MTP or other speculative decoding | Only for models with bundled draft heads |

### `--kv-cache-dtype fp8` is not on, and "turn it on everywhere" is the wrong instruction

This row used to read "leave on for all vLLM profiles". That was never true of the config and
is the kind of instruction someone acts on in one pass across nine profiles. Reality, as of
2026-10-18: **one** of the nine vLLM profiles sets it (`qwen3.6-35b-fast`). Two of the others
carry inline comments explaining that they deliberately do not — the BF16 `gemma4` profiles,
where quantising the KV cache against BF16 weights was rejected on purpose. The remaining six,
including all three shipping Qwen3.8 profiles, simply never had it measured.

It has since been **measured on `qwen3.8-27b-think`, and the answer is do not set it.** Full
write-up: `docs/fp8-kv-cache.md`. The short version is that the prize is real and the flag
still cannot serve:

- The pool grows **1.89-1.93x** — 1,126,917 -> 2,133,560-2,178,707 tokens, lifting
  concurrency at 131K from 8.60x to 16.3-16.6x. `TRITON_ATTN` is retained, the boot is clean,
  and retrieval is correct at every depth tested. (Not 2x: only the 16 full-attention layers'
  KV shrinks, the 48 gated-delta-net layers' recurrent state is untouched.)
- **It is about 6x slower at full length.** Same script, back to back, one flag apart: a
  130,752-token request takes **75 s** on bf16 and **455 s** on FP8, both returning the right
  needle. At the default worker-RPC watchdog (`VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS`, 300 s) a
  single forward step outlives it, the executor raises `TimeoutError: RPC call to
  sample_tokens timed out`, `EngineCore` shuts down and every later request gets a 500. The
  dead engine is the watchdog's doing, not a hang — with the watchdog raised to 1800 the same
  request completes with the engine alive. Not OOM either: `kv_cache_usage` was 6.6% with one
  request in flight.

- **And there is no depth at which it pays.** The obvious next move is to cap the profile
  shallower and take the pool anyway. A matched ladder against a bf16 control says no: the
  prefill penalty is already **1.85x at 8,193 tokens** and climbs monotonically — 2.50x at 16K,
  3.44x at 32K, 4.75x at 65K, 6.13x at 131K — with per-stream decode slower at every depth too
  (1.86x at 131K). One light-load fleet cell at 32,768 x conc=4 is **3.5x worse on TTFT and
  p90** — that cell uses only ~12% of either pool, so it shows the penalty survives batching
  rather than testing the capacity claim. There is no crossover, so no cap makes this worth
  setting.

- **And the extra capacity is worth less than nothing.** Per decode step the weight path is
  paid once and attention per sequence, so step time is `c + B*d*n` and the penalty
  **multiplies by batch size** while the pool only adds slots. Fitted on the conc=1 ladder
  alone, that model reproduces the independent prewarmed matrix in `docs/rdna4-long-context.md`
  to within 1% wherever attention dominates the step (65,536 x conc=8: 144.5 predicted against
  143.4 measured), and overestimates by 23-41% on shallow cells where the weight path does. At
  each arm's **own** slot ceiling at 65,536 tokens it gives bf16 17 slots at ~180 tok/s
  aggregate against FP8's 32 slots at ~56 — twice the slots, a third of the throughput. (A
  model, validated on bf16 cells only.)

So the 1.89x is pool headroom you cannot spend, because filling it costs six times the latency.
The cost is steady state — three different-seed full-length cells on one boot came in at 455,
457 and 458 s, so nothing amortises. Keep the remaining six profiles unmeasured rather than
assuming either way — but start from "this was six times slower on the profile closest to
yours".

Two things that were checked rather than assumed before testing, both of which held up and
neither of which predicted the failure:

- **It does not close the 3D split-KV path.** The worry is obvious — the long-context fix in
  `docs/rdna4-long-context.md` depends entirely on TRITON_ATTN's 3D decode kernel, and a KV
  dtype change is exactly the sort of thing that silently drops a kernel to a fallback. It
  does not, and the place to confirm that is the `use_3d` predicate itself, not the backend's
  advertised dtype list. In the pinned v0.26.0 image,
  `vllm/v1/attention/ops/triton_unified_attention.py` decides the grid from eight disjuncts:
  five "are the softmax segment buffers allocated" checks, `max_seqlen_q > 1` (the MTP /
  prefill gate), `num_seqs > seq_threshold_3D` (the 32 ceiling) and `is_batch_invariant`.
  **No dtype term appears in it.** FP8 is handled *inside* whichever kernel runs, as the
  `USE_FP8`, `Q_IS_FP8` and `KV_QUANT_MODE` constexpr toggles. Supporting evidence from the
  backend: `triton_attn.py` lists `fp8`, `fp8_e4m3` and `fp8_e5m2` in
  `supported_kv_cache_dtypes`, and raises `NotImplementedError` for a quantized cache only on
  the **encoder** attention path, which decoder-only Qwen3.x never takes.
- **Nor is it coarser prefill chunks**, which was this section's first guess. The prefill
  chunk is the largest multiple of the attention block size that fits in
  `--max-num-batched-tokens`, and FP8 doubles that block size, 784 -> 1568 (forced by the
  hybrid model's mamba/attention page-equality constraint). So FP8's chunk is 20 x 1568 =
  31,360 against bf16's 41 x 784 = 32,144 — it does **less** work per step and still takes six
  times as long. The cost is inside the attention kernel, and it is **proportional to KV
  tokens**: fitting both arms across the depth ladder separates a linear from a quadratic term
  and gives prefill's non-attention cost as unchanged (1.03x) against its attention term at
  **9.03x**, with decode's fixed weight-path cost unchanged to 0.17% (20.868 -> 20.833 ms per
  token) against **3.96x** per KV token. Nothing that does not scale with the KV cache got
  slower. **The mechanism is open.** The candidates are a per-KV-token software FP8 conversion
  in the Triton paged-attention path (vllm#57126) and a parallelism loss from the doubled block
  size; the second cannot account for the prefill term at all, since TRITON_ATTN's 3D split-KV
  path is gated off on any step carrying a prefill chunk. Neither has been shown to predict the
  **9.03x prefill against 3.96x decode** asymmetry, which is the fact most likely to settle it —
  a conversion is amortised across a query tile in prefill, which argues prefill should be hit
  *less*, while decode touches half the bytes bf16 does and is still 4x slower, which says that
  path is not bandwidth-bound. Do not quote a mechanism here as settled.
- **The precedent that it can go wrong is image-level, not flag-level.** On the 2026-10-15
  Radiance canary, FP8 KV fell back to Triton paged attention and cost 35-46% of decode at 8K+
  with 2x TTFT. That was measured on a different image and does not transfer to v0.26.0 — but
  it is why the pairing has to be re-measured on any image bump rather than inherited.

**The gate is `needle_check.py`, not throughput.** FP8 KV reduces the precision of stored keys
and values, which degrades *retrieval* before it degrades speed, and `depth_bench.py` sends
filler with `ignore_eos` and never reads the reply — it cannot see this failure at all. Run
`bench/needle_check.py` against both arms with the same `--seed`, sweeping needle position, and
require every cell to retrieve before looking at a single tok/s figure. That gate earned its
keep here: it was the only thing issuing a full-length request, so it is what found the crash,
and a throughput-only sweep at 65K would have reported FP8 KV as a clean win.

### `--max-num-batched-tokens` on MTP profiles: 16384, not 32768

An MTP profile allocates a `[embedding, hidden]` buffer sized by
`--max-num-batched-tokens` for the drafter. On Qwen3.8-27B that is
`32768 x (2 x 5120) x 2 bytes = 640 MiB` per step. A **fresh** container driven
straight into 32 concurrent 8K-token prompts cannot find it: all four TP
workers raise `torch.OutOfMemoryError` in the same step and the EngineCore
exits, while the API server keeps answering `/health` 200 for minutes.
Reproduced on 2 of 2 fresh spawns. Full write-up and the reproduction recipe:
`docs/mtp-drafter-oom.md`.

Halving the flag halves that buffer to 320 MiB and fixes it. Measured on
`qwen3.8-27b-code`, same image, FAST band confirmed either side:

- **KV pool goes up**, not down: 1,009,850 -> ~1,085,000 tokens (+7-9%), i.e.
  7.70x -> ~8.3x concurrent requests at the full 131,072 window. The profiling
  pass needs less transient room, so more is left for KV.
- **Free on `medium-256`**: 67.4 / 352.6 / 566.0 / 861.8 tok/s at conc
  1 / 8 / 16 / 32 against a 66.0 / 339.2 / 570.7 / 851.2 stock baseline — all
  within run-to-run noise.
- **It costs cold deep-burst prefill**, which is the real trade. At
  `8192 x conc=32` cold it read 17.6 aggregate tok/s and 201.7 s p90 TTFT
  against ~28.5 and ~133 s on 32768. n=1; the engine survives either way with
  the flag set.

Applies to the two profiles serving `/models/Qwen3.8-27B-FP8` with a
speculative config. `qwen3.8-27b-think` is deliberately left at 32768: it has
no MTP drafter, so there is no buffer to shrink, and it is the long-context
profile whose whole job is deep prompts.

**Not applied to `qwen3.6-27b-code` or `qwen3.6-35b-code`**, which also run MTP.
Their drafter buffers are the same shape in principle, but neither has been
measured, and `qwen3.6-27b-code`'s own engine death at `32768 x conc=32` is a
*different* defect — `TimeoutError: RPC call to sample_tokens timed out`, with
no OOM anywhere in its log. A smaller prefill chunk means more steps per batch,
which could make an RPC timeout worse rather than better. Measure before
copying this flag across.

`--gpu-memory-utilization` is not the lever here. The step that fails is outside
that budget — it budgets the KV pool, while activations and workspaces grow
lazily into leftover driver VRAM — and 0.01 is only ~326 MiB per card on a
32 GB card.
