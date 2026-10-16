# Flash-Next half-speed starts: cause and guard

`qwen3.8-flash-next-vllm` normally decodes ~56 tok/s serial. Occasionally a start comes up at
**half speed** (28 tok/s or lower) and stays there until the model is reloaded. Seen twice on
2026-10-11 and reproduced on demand on 2026-10-14.

## Cause

The profile pins a 47.7 GiB table (the FP8 per-layer-embedding table) in host RAM. If the kernel
page cache is full of other models' weights when the container starts (low `MemFree`), that
pinned allocation is slow and the process runs at a fraction of its speed for its whole life.
A reload "fixes" it only because the first load already pushed the cache out.

Everything else was ruled out by measurement:

| Candidate | Result |
|---|---|
| PCIe link (Gen4 vs Gen5, width) | Gen5 x16 on all cards, idle and mid-decode, in slow and fast loads alike |
| Host CPU contention | 56 busy-loop processes on 64 threads: 55.8 tok/s vs 56.3 unloaded, no effect |
| `--max-model-len`, clocks, NUMA | no effect (single NUMA node) |
| vLLM config / kernels | startup logs of slow and fast loads are line-for-line identical apart from timings |

## Measurements (all: 4 cards, shipped profile, direct podman, 4 timed 256-token requests)

An unconstrained series of 8 loads: 7 fast (53-56.6 tok/s), 1 slow (28.0) - the slow one started with
22 GiB MemFree, the rest with 82-92 GiB. Its whole startup was ~2x slower (model init 8.9 s vs 2.2 s,
graph capture 13 s vs 5 s, 150 s total vs 105-120 s).

Then the page cache was deliberately filled with unrelated model files before the load:

| MemFree at container start | Serial tok/s over the 4 requests |
|---|---|
| 85-97 GiB (normal) | 56.3 / 56.4 / 56.4 / 56.4 |
| 70 GiB | 56.3 / 31.6 / 28.8 / 28.8 (starts fast, degrades) |
| 50 GiB | 22.4 / 22.4 / 22.4 / 22.4 |
| 20 GiB | 28.3 / 28.5 / 28.5 / 28.4 (twice, also 28.0 in the unconstrained series) |
| 20 GiB, then `llm-prestart --need-free-gib 75` | 56.3 / 56.4 / 56.4 / 56.4 |
| 20 GiB, through llama-swap with the shipped `cmd` | 56.3 / 56.4 / 56.3 |

## Guard: `scripts/llm-prestart`

The profile's `cmd` starts with the wrapper, which `exec`s podman:

```
<llmstack dir>/scripts/llm-prestart --need-free-gib 80 --keep <model dir> -- podman run ...
```

If `MemFree` is below `--need-free-gib` it drops the page cache of the model files under
`/mnt/models/llm` with `posix_fadvise(DONTNEED)` until the target is met (no root needed: clean
pages of any readable file can be evicted). The profile's own weights (`--keep`) are spared first and
only evicted if that is not enough. It is best effort and can never block a start: errors are logged
and the command is exec'd anyway. It lives in `cmd`, not in `llmctl`, so it protects every client
path (llmctl, llmpanel, direct requests to llama-swap); llama-swap runs `cmd` without a shell and
`exec` keeps the PID it tracks. The wrapper's one-line report goes to the process's stderr.

80 GiB is the measured edge: 85+ is fast, 70 and below is not. Cost: the evicted files are read
from disk again next time they are loaded.

## Not covered

Anything else that fills host RAM (another large process, `/dev/shm`) is not handled; the wrapper only
frees page cache. If a start is still slow, `free -g` before the load and a reload are the first checks.
If a future profile pins a lot of host RAM, put the same wrapper in front of it with its own
`--need-free-gib` (derive it from the profile's `host_ram_gib` and a measured sweep like the table above).
