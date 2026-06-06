# llmctl — command reference

`llmctl` is the lifecycle and model management CLI for llmstack.  
It manages llama-swap (the OpenAI-compatible router), model loading, the
llmproxy shim, and log access — all from a single script.

**Install (one-time):**
```bash
ln -sf "$(pwd)/bin/llmctl" ~/.local/bin/llmctl
```

---

## Commands

### `llmctl up`

Start llama-swap. If the binary is not present it is downloaded automatically
from the llama-swap GitHub releases.

```
llmctl up
```

- Starts llama-swap as a background process on `:8080`
- Writes PID to `~/.local/share/llmstack/llama-swap.pid`
- Appends stdout/stderr to `~/.local/share/llmstack/llama-swap.log`
- Polls `/v1/models` for up to 10 s and prints "Ready." when healthy
- No-op if already running

---

### `llmctl down`

Stop llama-swap gracefully.

```
llmctl down
```

- Sends SIGTERM to the llama-swap process
- Waits up to 20 s for the port to be released
- Removes the PID file

Does **not** stop individual backend containers — those are stopped by
llama-swap itself as part of its shutdown sequence, or after their TTL elapses.

---

### `llmctl status`

Show running state, loaded models, and a quick VRAM snapshot.

```
llmctl status
```

Example output:
```
llama-swap: RUNNING  pid=12345  port=8080
Loaded models (1):
  • qwen3.6-35b-code

GPU VRAM:
  GPU[0]  : VRAM Total Memory (B): 34208743424
  GPU[0]  : VRAM Total Used Memory (B): 33012345678
  ...
```

---

### `llmctl list`

List all profiles defined in `config/models.yaml`. Marks currently loaded
models with `*`.

```
llmctl list
```

Example output:
```
Profiles (7)  [* = loaded]:
  qwen3-coder-30b-fp8
  qwen3.6-35b-code *
  qwen3.6-35b-fast
  qwen3.6-35b-512k
  qwen3.6-35b-q4ks
  qwen3.5-122b-a10b-q4
  qwen3.5-122b-a10b-q6
```

---

### `llmctl swap <profile>`

Load a model profile and wait until it is ready to serve requests.

```
llmctl swap qwen3.6-35b-code
```

- Sends a warm-up chat completion request (max_tokens=1) which causes
  llama-swap to start the backend container
- Blocks until the container is healthy and responds (up to 5 min timeout — adequate for warm starts)
- **First boot** on a new machine: vLLM compiles Inductor kernels (~14 min) then captures
  CUDA graphs (~13 s). Total ~18–20 min. Run `llmctl logs <profile>` to watch progress and
  wait for "Application startup complete." Subsequent starts use the cached compilation
  (`.vllm-cache/`) and take ~2–3 min.
- GGUF cold start: ~5 s (35B) or 90–180 s (122B, first disk read)

**Aliases work:** `llmctl swap qwen3.6` is equivalent to
`llmctl swap qwen3.6-35b-code` if `qwen3.6` is listed as an alias.

---

### `llmctl unload`

Unload all running model backends without stopping llama-swap itself.

```
llmctl unload
```

- Calls `GET /unload` on llama-swap, which stops all backend containers
- llama-swap remains running on `:8080` and is ready for the next `swap`
- Use this to free VRAM for other workloads (LM Studio, rocm benchmarks,
  compute tasks) without a full `down`/`up` cycle

---

### `llmctl pick`

Interactive model picker. Uses `fzf` if installed, falls back to a numbered
list.

```
llmctl pick
```

With `fzf`:
```
Load model ›  qwen3.6-35b-code
              qwen3.6-35b-fast
              ...
```

Without `fzf`:
```
Available profiles:
   1) qwen3-coder-30b-fp8
   2) qwen3.6-35b-code
   ...
Select [number]:
```

After selection, calls `llmctl swap` on the chosen profile.

---

### `llmctl logs [profile]`

Tail logs.

```bash
# Tail the llama-swap process log (model routing, start/stop events)
llmctl logs

# Tail a specific model's container log (vLLM or llama-server output)
llmctl logs qwen3.6-35b-code
```

Without a profile argument, tails `~/.local/share/llmstack/llama-swap.log`
via `tail -f`.

With a profile, looks for a running podman container named:
- `llmstack-vllm-<profile>` (vLLM backends)
- `llmstack-llama-<profile>` (llama-server backends)

Tails it with `podman logs -f`.

---

### `llmctl bench [profile]`

Run the concurrent benchmark against a loaded profile.

```
llmctl bench qwen3.6-35b-code
```

Wraps `bench/concurrent_bench.py`. Prints aggregate tok/s, TTFT, and per-GPU VRAM.
Used to establish throughput baselines and detect regressions after config changes.

For a full sweep across all prompt sizes and concurrency levels:
```bash
python3 bench/concurrent_bench.py \
  --model qwen3.6-35b-code \
  --sweep 1,2,4,8,16 \
  --prompt all \
  --no-thinking \
  --save bench/baselines/qwen3.6-35b-code-$(date +%Y%m%d).json
```

---

### `llmctl proxy-up`

Start the `llmproxy` streaming shim on port 9000.

```
llmctl proxy-up
```

`llmproxy` is a workaround for a vLLM streaming bug where `function.name` is
sent as `null` in tool-call SSE chunks, breaking `@ai-sdk/openai-compatible`
clients (OpenCode). The proxy intercepts SSE streams and restores the name
from earlier chunks.

- Starts `bin/llmproxy` as a background process on `:9000`
- Proxies to llama-swap on `:8080`
- Writes PID to `~/.local/share/llmstack/llmproxy.pid`
- Appends log to `~/.local/share/llmstack/llmproxy.log`

Point OpenCode (and similar clients) at `http://localhost:9000/v1`.

See `docs/workarounds.md` for full context and removal instructions.

---

### `llmctl proxy-down`

Stop the llmproxy shim.

```
llmctl proxy-down
```

---

### `llmctl proxy-status`

Show llmproxy state.

```
llmctl proxy-status
```

Example output:
```
llmproxy: RUNNING  pid=23456  port=9000 → :8080
```

---

## State files

| File | Purpose |
|------|---------|
| `~/.local/share/llmstack/llama-swap.pid` | llama-swap process ID |
| `~/.local/share/llmstack/llama-swap.log` | llama-swap stdout/stderr |
| `~/.local/share/llmstack/llmproxy.pid` | llmproxy process ID |
| `~/.local/share/llmstack/llmproxy.log` | llmproxy stdout/stderr |
| `~/.local/bin/llama-swap` | llama-swap binary (auto-downloaded) |

---

## Troubleshooting

| Symptom | Action |
|---------|--------|
| `up` hangs past 10 s | Check `llama-swap.log`; confirm GPUs are free (`rocm-smi`) |
| `swap` times out | First vLLM boot takes 18–20 min; run `llmctl logs <profile>` and wait manually. Subsequent starts are ~2–3 min. |
| `swap` returns no response | `llmctl logs <profile>` to see backend errors |
| Port 8080 already in use | Another process is on 8080; `lsof -i :8080` to identify |
| `unload` no-ops silently | Nothing was loaded; llama-swap returns OK regardless |
| `llmproxy` fails to start | Check that `bin/llmproxy` exists and Python 3 is available |
| Container not found in `logs` | Profile uses a fixed container name (e.g. 122B GGUF); check `podman ps` |
