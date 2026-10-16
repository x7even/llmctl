# Running with fewer than 4 GPUs

The shipped `config/models.yaml` is tuned for 4x 32 GB cards (128 GB). This page says what
still works on 3, 2 or 1 GPUs, what fails and why, and how `scripts/configure` handles it.
Figures marked **measured** come from runs on 4x Radeon AI PRO R9700 (ROCm 7.2, 2026-10-12)
with only the stated number of cards enabled (the 2026-10-13 run covered every profile; no
profile in `config/models.yaml` carries `estimate: true` any more).

---

## Why TP must be 1, 2 or 4

vLLM tensor parallelism splits attention heads (and the vocabulary) across cards, so the TP
size has to divide those counts. **Measured:** TP3 fails on both Qwen3.8 vLLM models with a
divisibility assertion at startup:

| Model | Head counts | TP3 failure (captured) |
|-------|-------------|------------------------|
| Qwen3.8-27B FP8 | 24 attention, 4 KV, 16-48 linear-attention | `AssertionError: 16 is not divisible by 3` (linear-attention heads) |
| Qwen3.8-Flash-Next W4A16 | 24 attention, 2 KV | `AssertionError: 248320 is not divisible by 3` (vocab size) |

TP3 also fails for Gemma 4 and Qwen3.6-35B (`Total number of attention heads (16) must be
divisible by tensor parallel size (3)`), so TP 1, 2 and 4 are the valid sizes for every vLLM
profile here. Three cards therefore run vLLM profiles at TP2 with one card idle. With 3 cards
the options are:

- Run vLLM profiles at **TP2** and leave one card idle (works for the 27B, see below).
- Use the **GGUF / llama-server profiles**, which layer-split with `--tensor-split` and accept
  any card count (`qwen3.8-flash-next`, `gemma4-26b-q8`, `gemma4-12b-q4`).

Whenever the model fits, TP2 is not "half speed": the 27B keeps about 70% of its serial speed
and 60-76% of its concurrent throughput (below).

---

## Per-profile summary

Min GPUs is the smallest count at which the profile can run with the shipped settings.

| Profile | Backend | Min GPUs | 3 GPUs | 2 GPUs | 1 GPU |
|---------|---------|----------|--------|--------|-------|
| `qwen3.8-27b-code` / `-think` / `-fast` | vLLM | 2 | TP2, one card idle (TP3 fails) | **Works (measured)** | Fails (OOM loading weights) |
| `qwen3.8-flash-next-vllm` | vLLM TP+EP | 4 | TP3 fails | Fails (OOM loading weights) | Not run; the 4-card layout is required |
| `qwen3.8-flash-next` | llama-server (Vulkan) | 2 | **Works (measured)**, 33.2 tok/s serial | **Works (measured)**, 17.4 tok/s serial, no VRAM headroom | Does not fit (~87 GiB of shards) |
| `qwen3.6-35b-code` / `-128k-nomtp` / `-fast` | vLLM | 2 | TP2, one card idle (TP3 fails: 16 heads) | **Works (measured)**, 58.9 tok/s serial | Fails (OOM loading weights) |
| `gemma4-26b-a4b` (BF16) | vLLM | 4 | Skipped (TP3 fails: 16 heads; TP2 not supported) | Fails (weights load at 25.6 GiB/card, then the profiling run dies with an NCCL/CUDA error) | Fails (OOM) |
| `gemma4-26b-fp8` | vLLM | 2 | TP2, one card idle (TP3 fails: 16 heads) | **Works (measured)**, 56.4 tok/s serial | Fails (OOM loading weights) |
| `gemma4-26b-q8` | llama-server | 1 | Works (layer split) | Works (layer split) | **Works (measured)**, 91.7 tok/s serial, 29.3 GiB |
| `gemma4-12b-q4` | llama-server | 1 | Works (layer split) | Works (layer split) | **Works (measured)**, 61.6 tok/s serial, 11.6 GiB |

All profiles are now measured at the card counts that decide their minimum (2026-10-13,
direct `podman run` with only the stated cards visible, shipped settings). Cells without
"measured" follow from a neighbouring measurement (a GGUF layer split that fits on one card
fits on more; TP3 fails wherever the head count is 16). The Qwen3.6-35B rows were measured on
`-code` (TP2) and `-fast` (TP1, TP3); `-128k-nomtp` shares the same checkpoint and flags.

### Measured detail, 2026-10-13 run

| Profile | Cards | Result | Serial tok/s | VRAM per card (GiB) | KV pool |
|---------|-------|--------|--------------|---------------------|---------|
| `gemma4-26b-q8` | 1 | OK, load 15 s | 91.7 | 29.3 | - |
| `qwen3.8-flash-next` | 3 | OK, load 25 s | 33.2 | 24.5 / 22.8 / 26.2 | - |
| `qwen3.8-flash-next` | 2 | OK, load 15 s | 17.4 | 31.7 / 31.3 | - |
| `gemma4-26b-a4b` | 2 | EXIT: NCCL unhandled CUDA error in the profiling run | - | weights 25.6 | - |
| `gemma4-26b-a4b` | 3 | EXIT: 16 attention heads not divisible by 3 | - | - | - |
| `gemma4-26b-a4b` | 1 | EXIT: `torch.OutOfMemoryError` | - | 31.45 allocated | - |
| `gemma4-26b-fp8` | 2 | OK, load 215 s | 56.4 | 27.8 / 27.8 | 284,518 tokens |
| `gemma4-26b-fp8` | 3 | EXIT: 16 attention heads not divisible by 3 | - | - | - |
| `gemma4-26b-fp8` | 1 | EXIT: `torch.OutOfMemoryError` | - | 29.77 allocated | - |
| `qwen3.6-35b-code` | 2 | OK, load 210 s | 58.9 | 27.4 / 27.4 | 483,510 tokens |
| `qwen3.6-35b-fast` | 3 | EXIT: 16 attention heads not divisible by 3 | - | - | - |
| `qwen3.6-35b-fast` | 1 | EXIT: `torch.OutOfMemoryError` | - | 31.09 allocated | - |

The Gemma BF16 TP2 failure is at the shipped settings only (`--max-num-seqs`,
`--gpu-memory-utilization`); a TP2 run with those lowered was not tried, so `[4]` is the
supported set, not a proof that no TP2 configuration exists. The 2-card Flash-Next GGUF run
uses 31.7 GiB of 31.86 per card, so it works but leaves no room to raise `--ctx-size` or
`--parallel`, and its serial speed is roughly half the 3-card figure.

### Qwen3.8-27B at TP2 (measured)

`qwen3.8-27b-code` with `--tensor-parallel-size 2`, 131072 max-model-len, MTP on:

| | serial | conc=8 | conc=16 | KV pool | Code tests |
|---|---|---|---|---|---|
| TP2 | 46.6 | 219 | 418 | 255K tokens | 11/16 |
| TP4 (reference) | 66 | 361 | 549 | - | - |

Decode tok/s, `medium-256`, `--no-thinking`. 131072 context fits at TP2. The 11/16 code-test
result is the TP2 run only, so it is not a like-for-like comparison with a TP4 score here.

TP1 fails: `torch.OutOfMemoryError` while loading weights (29.78 GiB allocated of 31.86 GiB),
so there is no room for KV cache or CUDA graphs. TP3 fails with `AssertionError: 16 is not
divisible by 3` (the 16 linear-attention heads).

### Flash-Next on vLLM (measured: needs all four cards)

Per card at TP4+EP (31.86 GiB): weights 18.79, graphs 0.72, KV 6.91, about 3 spare. The
checkpoint is 116 GiB; the 47.7 GiB FP8 per-layer-embedding (PLE) table is offloaded to
pinned host RAM (via the HIP pinned-host allocator; `--ulimit memlock=-1:-1` in the profile is
inert under rootless podman, see `docs/models.md`).

- **TP2 fails:** `torch.OutOfMemoryError` while loading weights (31.20 GiB allocated, 50 MiB
  free). The 4-card layout at about 19 GiB/GPU is required.
- **TP3 fails:** `AssertionError: 248320 is not divisible by 3` (vocab size).
- **Host RAM:** about 96 GB. The pinned PLE table is 47.7 GiB (about 12 GiB per rank); the
  rest is process and page-cache headroom while the 116 GiB checkpoint loads. Treat 96 GB as
  the working requirement, not a hard-measured minimum.
- Exclusive VRAM: unload every other model first.

### Context length: what vLLM auto-fit picks (measured 2026-10-15)

`--max-model-len -1` makes vLLM choose the largest context that fits the KV memory it actually has. With the
shipped profiles on this rig (auto-fit message in the container log):

| profile | cards | auto-fit max_model_len | KV pool (tokens) | load / serial tok/s |
|---|---|---|---|---|
| qwen3.8-flash-next-vllm | 4 (TP4+EP) | 262,144 (native) | 550,959 | 125 s / 56.6 |
| qwen3.8-27b-code | 4 (TP4) | 262,144 (native) | 1,057,057 | 165 s / 68.7 |
| qwen3.8-27b-code | 2 (TP2) | 262,144 (native) | 264,457 | 220 s / 33.4 |

The native context fits on every valid TP size, so the 27B's shipped 131,072 is a decode-speed policy, not a
memory limit. At TP2, 262,144 leaves room for one full-length request in the pool; 131,072 allows two. Where a
profile should follow the hardware rather than a fixed number, `-1` is the right setting; see
`docs/hard-code-tasks.md` section 5.

### Flash-Next on llama-server (GGUF)

`qwen3.8-flash-next` totals about 81 GB across the cards (the GGUF is 90 GB on disk).
`--tensor-split` layer-splits on any count. **Measured:** it loads and serves on **two** cards
(31.7 / 31.3 GiB used, 17.4 tok/s serial, no headroom left) and on three (24.5 / 22.8 / 26.2
GiB, 33.2 tok/s); one card cannot hold the shards, so `min_gpus: 2`. Two cards is a floor, not
a recommendation: speed halves and nothing is left for a larger `--ctx-size` or `--parallel`.
Only one GPU is active at a time, so throughput does not scale with concurrency.

---

## How `scripts/configure` handles GPU counts

`scripts/configure` rewrites the GPU-dependent settings in `config/models.yaml` after cloning.
Its behaviour for fewer than four cards:

- **Detection:** it reads each GPU's VRAM size from sysfs (`mem_info_vram_total`) and counts
  devices with at least 8 GiB, so an integrated GPU does not inflate the count. `amd-smi` (then `rocm-smi`) is
  only a fallback when sysfs exposes no VRAM information. Override with `--gpu-count N`.
- **Valid-TP rounding:** vLLM `--tensor-parallel-size` is set to the largest valid size (1, 2 or
  4) that does not exceed the GPU count. Three cards give TP2, not TP3. It warns when it
  rounds down, because one card then sits idle for vLLM profiles.
- **llama-server:** `--tensor-split` is written for the actual count (`1` for a single card),
  since GGUF layer splits work with any number of cards.
- **Requirements are declared in the profile:** each profile in `config/models.yaml` carries a
  `metadata.requires` block (`gpus: [2, 4]` for vLLM, `min_gpus: 2` for llama-server, optional
  `host_ram_gib`, `estimate`, `note`), and `scripts/configure` reads them from there. The table
  above is the human-readable view of those declarations; the schema is in
  `config/CLAUDE.md` ("Profile requirements"). Add the block to every new profile.
- **Minimum-GPU handling:** profiles that cannot run at the detected count (for example
  `qwen3.8-flash-next-vllm` and `gemma4-26b-a4b` below four cards, `qwen3.8-flash-next` below
  two) are reported as `SKIP` with the reason and their `cmd` is left unchanged. They are
  hidden from `/v1/models` by an auto-managed `unlisted: true  # llmstack:auto` line that
  configure removes again once the profile becomes supported; a hand-written `unlisted:` line
  (`true` or `false`) is never touched and always wins, so a profile never ends up with two. `llmctl list` / `pick` / `swap` apply the same `scripts/llmhw.py` verdict: they hide these profiles, and `llmctl swap` refuses them with exit 2 unless `--force` (they will probably fail to start). That verdict comes only from `metadata.requires`; a hand-written `unlisted: true` or `false` does not change it. `llmpanel` applies the same verdict in its Models panel: it lists only runnable profiles, `a` shows the others greyed with the reason (a compact `4 GPU`; the Config panel has the full `needs 4 GPUs, have 2`), and it will not swap an unsupported profile (use `llmctl swap --force`). `llmpanel --gpu-count N` or `LLMSTACK_GPU_COUNT=N` previews another rig.
- **`--dry-run`:** prints the resulting config and the warnings without writing anything. Use
  it first to see what a count would produce.

```bash
scripts/configure --dry-run                 # preview using the detected count
scripts/configure --gpu-count 2 --dry-run   # preview a 2-GPU layout
scripts/configure --gpu-count 3             # 3 cards: vLLM profiles at TP2, GGUF split 3 ways
```

After changing the config restart the router: `llmctl down && llmctl up`.

---

## Practical advice

- 3 cards: run `qwen3.8-27b-code` at TP2 (one card idle), or `qwen3.8-flash-next` (GGUF,
  33 tok/s serial) for the larger model. Load one at a time.
- 2 cards: Qwen3.8-27B at TP2 is the default choice; expect about 70% of the 4-card serial
  speed and a 255K-token KV pool. `gemma4-26b-fp8` and `qwen3.6-35b-*` also run at TP2;
  `qwen3.8-flash-next` (GGUF) fits but with no spare VRAM and 17 tok/s serial.
- 1 card: GGUF profiles only. `gemma4-12b-q4` (11.6 GiB) and `gemma4-26b-q8` (29.3 GiB with
  mmproj and KV, 91.7 tok/s) both run with the shipped settings.
- Always check `llmctl logs <profile>` the first time; a wrong TP size shows up as the server
  exiting during startup.
- Multi-GPU host check: the kernel needs `CONFIG_HSA_AMD_P2P=y` (`zcat /proc/config.gz | grep HSA_AMD_P2P`).
  Without it RCCL falls back to host-staged transfers and collective latency is far higher. Most distro
  kernels except Arch's omit it; this build host has it enabled.
