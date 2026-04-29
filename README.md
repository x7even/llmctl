# llmstack

OpenAI-compatible LLM serving stack for **concurrent agent use**.  
Designed for: Claude Code · OpenCode · MCP testing · agent frameworks · raw API clients.

Hardware: 4× AMD Radeon AI PRO R9700 (gfx1201, 32 GB each = 128 GB total)  
Backends: **vLLM** (FP8/safetensors, high concurrency) + **llama-server Vulkan** (GGUF models)  
Router: **llama-swap** — one OpenAI endpoint, models loaded on demand by `model` field

## Quick Start

```bash
# Install the CLI helper (one-time)
ln -sf "$(pwd)/bin/llmctl" ~/.local/bin/llmctl

# Start the router
llmctl up

# Load a model and verify
llmctl swap qwen3-coder-30b-fp8

# Point any client here
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-coder-30b-fp8","messages":[{"role":"user","content":"hello"}]}'
```

## Client configuration

| Client | Setting |
|--------|---------|
| Claude Code | `ANTHROPIC_BASE_URL=http://localhost:8080/v1` or set in `.claude/settings.json` |
| OpenCode | Point base URL to `http://localhost:8080/v1` |
| Continue.dev | `apiBase: http://localhost:8080/v1` |
| aichat / llm CLI | `--url http://localhost:8080/v1` |
| curl / scripts | `http://localhost:8080/v1/chat/completions` |

## CLI reference (`llmctl`)

```
llmctl up              start llama-swap (auto-downloads binary if missing)
llmctl down            stop llama-swap
llmctl status          running state + loaded models + GPU VRAM
llmctl list            list all profiles in config/models.yaml
llmctl swap <profile>  preload a model (waits until ready)
llmctl pick            interactive fzf or numbered menu to swap model
llmctl logs            tail llama-swap process log
llmctl logs <profile>  tail a model's container log
llmctl bench [profile] run concurrent benchmark (Phase 2)
```

## Model profiles (config/models.yaml)

| Profile | Backend | VRAM | Best for |
|---------|---------|------|---------|
| `qwen3-coder-30b-fp8` | vLLM TP=4 | ~30 GB | Code, agents, high concurrency |
| `qwen3.5-122b-a10b-q4` | llama-server Vulkan | ~73 GB | Heavyweight reasoning |
| `qwen3.5-122b-a10b-q6` | llama-server Vulkan | ~98 GB | Maximum quality, limited context |

Aliases: `coder`, `qwen3.5-122b`, `122b`, `qwen3.5-122b-q6`

## Adding a new model

**vLLM (safetensors / FP8 / AWQ):**
1. Copy the template block at the bottom of `config/models.yaml`
2. Set `name:`, local model path in `serve /models/<dir>`, `--served-model-name`, `--dtype`
3. Run `llmctl swap <new-profile>` to verify

**GGUF (llama-server):**
1. Copy the GGUF template block from `config/models.yaml`
2. Set the `-m /models/<path>.gguf` argument
3. For split GGUFs (`-00001-of-0000N`), llama.cpp auto-detects the remaining parts — point at part 1

## Architecture

```
Clients ──► llama-swap :8080 ──► vLLM container (FP8/safetensors)
                            └──► llama-server container (GGUF/Vulkan)
```

- **llama-swap** runs on the host as a background process (binary at `~/.local/bin/llama-swap`)
- Each backend is a rootless podman container with GPU device passthrough
- Models hot-swap by model name with configurable idle TTL
- Logs: `~/.local/share/llmstack/llama-swap.log`

## Smoke test

```bash
# Full test (loads both backends — slow on first run)
./tests/smoke.sh

# Skip the 73 GB GGUF model
./tests/smoke.sh --skip-gguf
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `llmctl up` hangs | Check `~/.local/share/llmstack/llama-swap.log` |
| vLLM fails to load | Verify `podman images \| grep vllm-rdna4`; check GPU with `rocm-smi` |
| GGUF model not found | Check path in `config/models.yaml` matches `/mnt/models/llm/...` |
| GPU not visible in container | Ensure user is in `video` and `render` groups: `groups` |
| Timeout on first model load | Large models take 60–180 s on cold page cache; `--max-time 600` in curl |
| `podman: no such container` | Container stopped cleanly; `--replace` will restart it on next swap |

## Phases

- **Phase 1** (current): minimal serving, two backends, llmctl, smoke test
- **Phase 2** (after benchmark approval): prefix caching tuned, MCP sidecar (mcpo), Caddy front door
- **Phase 3** (after Phase 2 approval): Prometheus metrics, Grafana dashboard, ROCm-HIP llama.cpp variant

## Files

```
config/models.yaml   model profiles (edit here to add models)
bin/llmctl           CLI helper
containers/vllm/     vLLM Containerfile (thin wrapper on existing image)
containers/llama-server/  llama-server Vulkan Containerfile
tests/smoke.sh       Phase 1 verification
bench/               benchmark scripts (Phase 2)
```
