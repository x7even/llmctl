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
  docker.io/vllm/vllm-openai-rocm:latest \
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

All vLLM profiles must use: `docker.io/vllm/vllm-openai-rocm:latest`

### MTP requires the draft head file

Speculative MTP (`--speculative-config '{"method":"mtp","num_speculative_tokens":2}'`)
requires `mtp.safetensors` to be bundled with the model weights. Not all checkpoints
include it. If the file is missing, vLLM logs an error and falls back to standard decode.
Qwen3.6-35B-FP8-Instruct from Qwen HF includes it; raw PT files may not.

### GGUF qwen35moe in vLLM: not supported

`ValueError: GGUF model with architecture qwen35moe is not supported yet.`
Use llama-server (Vulkan) for all GGUF files. Use vLLM for safetensors only.

---

## Template for a new vLLM profile

```yaml
  - name: <profile-id>
    aliases:
      - <short-alias>
    ttl: 0
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
            docker.io/vllm/vllm-openai-rocm:latest \
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
