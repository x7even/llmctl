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
  • qwen3.8-27b-code

GPU VRAM:
  GPU[0]  : VRAM Total Memory (B): 34208743424
  GPU[0]  : VRAM Total Used Memory (B): 33012345678
  ...
```

---

### `llmctl list`

List the profiles in `config/models.yaml` that can run on this machine's hardware
(judged from each profile's `metadata.requires`, see `llmctl hw`). Marks currently
loaded models with `*`. If any profiles were hidden because the GPU count or host RAM
is too small, a final line says how many.

```
llmctl list            # supported profiles only
llmctl list --all      # every profile; unsupported ones are marked with the reason
```

Example output (`LLMSTACK_GPU_COUNT=2`):
```
Profiles (9)  [* = loaded]:
  qwen3.8-27b-code  (aliases: qwen3.8, 27b-3.8, qwen3.8-27b)
  qwen3.8-27b-think  (aliases: 27b-think)
  ...
  gemma4-26b-fp8  (aliases: gemma4-fp8, gemma4-fast-vllm)
3 profile(s) hidden (need more GPUs/RAM): use 'llmctl list --all' to show them
```

With `--all`:
```
  qwen3.8-flash-next  (aliases: flash-next, qwen3.8-flash)  [UNSUPPORTED: needs min_gpus 3, detected 2]
  qwen3.8-flash-next-vllm  (aliases: flash-next-vllm)  [UNSUPPORTED: needs gpus [4], detected 2]
```

If hardware detection is unavailable, `list` shows every profile exactly as before
(see "Hardware awareness and fail-open" below).

---

### `llmctl hw [--json]`

Show the detected hardware and which profiles it can run.

```
llmctl hw
LLMSTACK_GPU_COUNT=2 llmctl hw          # simulate a 2-GPU rig
llmctl hw --json                        # {hw, profiles:{name:{ok,tp_or_split,estimate,reasons,requires}}}
```

Example output (`LLMSTACK_GPU_COUNT=2`):
```
GPUs:      2 (override)
VRAM/GPU:  unknown
Host RAM:  188 GiB
Note:      GPU count overridden (LLMSTACK_GPU_COUNT / --gpu-count); simulation only

PROFILE                  OK  USES     EST         REASONS
qwen3.8-27b-code         OK  TP2
...
qwen3.8-flash-next       NO  -        (estimate)  needs min_gpus 3, detected 2
qwen3.8-flash-next-vllm  NO  -                    needs gpus [4], detected 2
gemma4-26b-q8            OK  split 2  (estimate)
```

- `USES` is what `scripts/configure` would pick: `TP<n>` (vLLM tensor-parallel size, the
  largest listed `gpus` entry that fits) or `split <n>` (llama-server `min_gpus` profiles).
- `(estimate)` means the profile's requirements were derived, not measured on this rig.
- GPU/RAM detection and the checks are `scripts/llmhw.py`; sources are `sysfs`, `amd-smi`, `rocm-smi`
  or `override`. `VRAM/GPU` is unknown for an override.
- Exit code 1 if the GPU count could not be detected (a warning explains why), else 0.
  If `scripts/llmhw.py` loads but finds no GPU count, `--json` still prints the full
  report with `ok` true for everything. If `scripts/llmhw.py` cannot be loaded (or
  detection raises), `--json` prints `{"hw": null, "profiles": {}}`, plain `hw` prints
  nothing but the `llmctl: warning: ... cannot report hardware` line on stderr, and
  both exit 1.

---

### `llmctl swap [--force] <profile>`

Load a model profile and wait until it is ready to serve requests.

```
llmctl swap qwen3.8-27b-code
llmctl swap --force gemma4-26b-a4b     # skip the hardware check
```

If the profile (or the profile an alias resolves to) declares `metadata.requires` that this
machine does not meet, the swap is **refused with exit code 2** before the router is
contacted. The message names the unmet requirement(s), the detected hardware, a warning
that the profile will probably fail to start, and the override. If the requirement is an
`estimate` (see `llmctl hw`) the message says so, since the verdict is then a best guess.
The last line appears only when the GPU count is a simulated one (`LLMSTACK_GPU_COUNT` /
`--gpu-count`):

```
llmctl: 'gemma4-vllm' (profile 'gemma4-26b-a4b') does not meet its hardware requirements:
  - needs gpus [4], detected 2
Detected: 2 GPUs (override), 188 GiB host RAM
This profile will probably fail to start (out of memory or an invalid tensor-parallel size).
Run 'llmctl hw' to see what fits, or 'llmctl swap --force gemma4-26b-a4b' to try anyway (a failed start can leave the router waiting on a slow health check).
LLMSTACK_GPU_COUNT / --gpu-count only simulate a different rig; unset them to use the real hardware.
```

`--force` skips the refusal and runs the swap, adding a warning on stderr
(`warning: --force: '<profile>' does not meet its requirements (<reasons>); expect the
start to fail`). Expect it to fail: the container can run out of memory or reject the
tensor-parallel size, and a failed start can leave the router waiting on a slow health
check. A profile with no `requires` block, a name that is
not in `config/models.yaml` (the router decides), or a failed hardware detection are all
allowed.

- Sends a warm-up chat completion request (max_tokens=1) which causes
  llama-swap to start the backend container
- Blocks until the container is healthy and responds (up to 5 min timeout — adequate for warm starts)
- **First boot** on a new machine: vLLM compiles Inductor kernels (~14 min) then captures
  CUDA graphs (~13 s). Total ~18–20 min. Run `llmctl logs <profile>` to watch progress and
  wait for "Application startup complete." Subsequent starts use the cached compilation
  (`.vllm-cache/`) and take ~2–3 min.
- GGUF cold start: ~5 s (35B) or 90–180 s (122B, first disk read)

**Aliases work:** `llmctl swap qwen3.8` is equivalent to
`llmctl swap qwen3.8-27b-code` if `qwen3.8` is listed as an alias.

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

### `llmctl pick [--all]`

Interactive model picker. Uses `fzf` if installed, falls back to a numbered
list. Like `llmctl list`, it offers only profiles this hardware can run; `--all`
includes the rest, tagged `[unsupported on this hardware]`. Picking a tagged profile is
always refused with the `swap` message (the picker cannot pass `--force`); to load one
anyway run `llmctl swap --force <id>`.

```
llmctl pick
llmctl pick --all
```

With `fzf`:
```
Load model ›  qwen3.8-27b-code
              qwen3.8-27b-think
              ...
```

Without `fzf`:
```
Available profiles:
   1) qwen3.8-27b-code
   2) qwen3.8-27b-think
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
llmctl logs qwen3.8-27b-code
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
llmctl bench qwen3.8-27b-code
```

Wraps `bench/concurrent_bench.py`. Prints aggregate tok/s, TTFT, and per-GPU VRAM.
A profile this hardware cannot run is refused with the same exit-2 message as `swap`
(the router would otherwise load it by name); `llmctl bench --force <profile>` skips that check.
Used to establish throughput baselines and detect regressions after config changes.

For a full sweep across all prompt sizes and concurrency levels:
```bash
python3 bench/concurrent_bench.py \
  --model qwen3.8-27b-code \
  --sweep 1,2,4,8,16 \
  --prompt all \
  --no-thinking \
  --save bench/baselines/qwen3.8-27b-code-$(date +%Y%m%d).json
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

## Hardware awareness and fail-open

`llmctl hw`, `list`, `pick` and `swap` use `scripts/llmhw.py` (the same module as
`scripts/configure`) to detect GPUs / host RAM and to evaluate each profile's
`metadata.requires` (schema: `config/CLAUDE.md`). The module is located relative to the real
path of `llmctl`, so symlinks and other working directories are fine.

| Control | Effect |
|---------|--------|
| `LLMSTACK_GPU_COUNT=N` | Treat the machine as having N GPUs (source `override`). For simulating smaller rigs and testing; it does not change what is really installed, so a swap that passes the check can still fail at container start. |
| `--gpu-count N` | Same, as a global flag in any position (`llmctl --gpu-count 2 list`); wins over the env var. |
| `llmctl swap --force` | Skip the swap refusal. The profile will probably fail to start. |

**Fail open:** hardware checks never block or crash llmctl. If `scripts/llmhw.py` cannot be
loaded, detection raises, or no GPU count can be detected, `list`, `pick` and `swap` behave
exactly as before this feature (all profiles shown, any swap allowed) and print one short
`llmctl: warning: ...` line on stderr. An unusable `LLMSTACK_GPU_COUNT` value is warned
about and ignored. `llmctl hw` has nothing to show without detection and exits 1.

`scripts/configure` hides unsupported profiles from `/v1/models` with an `unlisted: true
# llmstack:auto` line; `llmctl list` / `pick` / `swap` apply the same `llmhw` verdict
(hidden from the lists, refused by `swap` without `--force`). The llmctl verdict comes
only from `metadata.requires`: a hand-written `unlisted: true` or `false` does not change
it.

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
| `up` hangs past 10 s | Check `llama-swap.log`; confirm GPUs are free (`amd-smi list`) |
| `swap` times out | First vLLM boot takes 18–20 min; run `llmctl logs <profile>` and wait manually. Subsequent starts are ~2–3 min. |
| `swap` exits 2 "does not meet its hardware requirements" | The profile's `metadata.requires` is not met (`llmctl hw` shows why). Unset `LLMSTACK_GPU_COUNT` if you set it for a simulation; use `--force` only to knowingly override |
| A profile is missing from `list` | Hidden for this hardware; `llmctl list --all` shows it with the reason |
| `swap` returns no response | `llmctl logs <profile>` to see backend errors |
| Port 8080 already in use | Another process is on 8080; `lsof -i :8080` to identify |
| `unload` no-ops silently | Nothing was loaded; llama-swap returns OK regardless |
| `llmproxy` fails to start | Check that `bin/llmproxy` exists and Python 3 is available |
| Container not found in `logs` | Profile uses a fixed container name (e.g. 122B GGUF); check `podman ps` |
