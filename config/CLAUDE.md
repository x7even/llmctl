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

Every vLLM profile **must** have all three of these. Omitting any will cause an 18+ minute
startup or a startup failure.

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
With 6 explicit sizes = 13 s capture, with negligible throughput loss
(batches > 32 fall back to eager, which is rare in practice).

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
held). Rollback anchor: `localhost/vllm-openai-rocm:v0.22.1-baseline`.

### MTP requires the draft head file

Speculative MTP (`--speculative-config '{"method":"mtp","num_speculative_tokens":2}'`)
requires `mtp.safetensors` to be bundled with the model weights. Not all checkpoints
include it. If the file is missing, vLLM logs an error and falls back to standard decode.
The official Qwen3.8-27B-FP8 and Qwen3.6-35B-A3B-FP8 checkpoints include it; raw PT files may not.

### GGUF qwen35moe in vLLM: not supported

`ValueError: GGUF model with architecture qwen35moe is not supported yet.`
Use llama-server (Vulkan) for all GGUF files. Use vLLM for safetensors only.

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
- `llmpanel` does not read it yet (planned for 0.4.4); until then only `scripts/configure`
  and `llmctl` act on the declarations.
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

```yaml
  - name: <profile-id>
    aliases:
      - <short-alias>
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
| `--gpu-memory-utilization` | Fraction of VRAM reserved for KV cache | Lower if OOM; keep at 0.95–0.97 normally |
| `--kv-cache-dtype fp8` | Store KV tensors in FP8 | Leave on for all vLLM profiles; saves ~40% KV VRAM |
| `concurrencyLimit` | Queue depth before 429 | Set to `--max-num-seqs` or slightly above |
| `ttl` | Seconds before auto-unload | 0 = never; useful for infrequently used profiles |
| `--enable-prefix-caching` | Cache prompt prefixes across requests | Leave on for all profiles |
| `--enable-expert-parallel` | Distribute MoE experts across GPUs | ON for FP8/dense profiles; OFF for AWQ |
| `--speculative-config` | MTP or other speculative decoding | Only for models with bundled draft heads |
