# Running with fewer than 4 GPUs

The shipped `config/models.yaml` is tuned for 4x 32 GB cards (128 GB). This page says what
still works on 3, 2 or 1 GPUs, what fails and why, and how `scripts/configure` handles it.
Figures marked **measured** come from runs on 4x Radeon AI PRO R9700 (ROCm 7.2, 2026-10-12)
with only the stated number of cards enabled. Figures marked **estimate** are arithmetic from
checkpoint sizes, not runs.

---

## Why TP must be 1, 2 or 4

vLLM tensor parallelism splits attention heads (and the vocabulary) across cards, so the TP
size has to divide those counts. **Measured:** TP3 fails on both Qwen3.8 vLLM models with a
divisibility assertion at startup:

| Model | Head counts | TP3 failure (captured) |
|-------|-------------|------------------------|
| Qwen3.8-27B FP8 | 24 attention, 4 KV, 16-48 linear-attention | `AssertionError: 16 is not divisible by 3` (linear-attention heads) |
| Qwen3.8-Flash-Next W4A16 | 24 attention, 2 KV | `AssertionError: 248320 is not divisible by 3` (vocab size) |

TP 1, 2 and 4 are the sizes the 27B counts divide by; `scripts/configure` assumes the same
set for other vLLM profiles (not checked for the Qwen3.6 and Gemma 4 head counts). Three
cards therefore run vLLM profiles at TP2 with one card idle. With 3 cards the options are:

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
| `qwen3.8-flash-next` | llama-server (Vulkan) | 3 | Layer split (estimate, not run at 3) | Does not fit (~81 GB) | Does not fit (~81 GB) |
| `qwen3.6-35b-code` / `-128k-nomtp` / `-fast` | vLLM | 2 (estimate) | TP2 expected (estimate) | Expected to fit (estimate) | Does not fit (35 GB checkpoint) |
| `gemma4-26b-a4b` (BF16) | vLLM | 4 (estimate: only benchmarked at TP4, a conservative cap rather than a measured failure; `scripts/configure` skips it below 4) | Skipped | Skipped | Skipped (49 GB checkpoint) |
| `gemma4-26b-fp8` | vLLM | 2 (estimate) | TP2 (estimate) | TP2 (estimate) | Skipped (~26 GB weights + KV) |
| `gemma4-26b-q8` | llama-server | 1 (estimate) | Untested | Untested | Untested; 27 GB GGUF + mmproj + KV may not fit one 32 GB card |
| `gemma4-12b-q4` | llama-server | 1 (estimate) | Untested | Untested | Untested; 7 GB GGUF should fit |

Only the Qwen3.8-27B and Flash-Next vLLM rows are measured. Rows marked estimate or untested
are derived from checkpoint size per card, not from runs at the reduced GPU count; TP validity
for the Qwen3.6 and Gemma 4 head counts was not checked.

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
pinned host RAM, which also needs the container to run with `--ulimit memlock=-1:-1`.

- **TP2 fails:** `torch.OutOfMemoryError` while loading weights (31.20 GiB allocated, 50 MiB
  free). The 4-card layout at about 19 GiB/GPU is required.
- **TP3 fails:** `AssertionError: 248320 is not divisible by 3` (vocab size).
- **Host RAM:** about 96 GB. The pinned PLE table is 47.7 GiB (about 12 GiB per rank); the
  rest is process and page-cache headroom while the 116 GiB checkpoint loads. Treat 96 GB as
  the working requirement, not a hard-measured minimum.
- Exclusive VRAM: unload every other model first.

### Flash-Next on llama-server (GGUF)

`qwen3.8-flash-next` totals about 81 GB across the cards, so it needs at least three 32 GB
cards (the GGUF is 90 GB on disk). `--tensor-split` layer-splits on any count of 3 or more.
Caveat: the shards are about 87 GiB plus a 2.6 GiB MTP draft, and three cards offer 95.6 GiB
before KV cache, so the `min_gpus: 3` figure is an unmeasured estimate. If it runs out of
memory on three cards, raise `min_gpus` to 4 in the profile.
Only one GPU is active at a time, so throughput does not scale with concurrency.

---

## How `scripts/configure` handles GPU counts

`scripts/configure` rewrites the GPU-dependent settings in `config/models.yaml` after cloning.
Its behaviour for fewer than four cards:

- **Detection:** it reads each GPU's VRAM size from sysfs (`mem_info_vram_total`) and counts
  devices with at least 8 GiB, so an integrated GPU does not inflate the count. `rocm-smi` is
  only a fallback when sysfs exposes no VRAM information. Override with `--gpu-count N`.
- **Valid-TP rounding:** vLLM `--tensor-parallel-size` is set to the largest valid size (1, 2 or
  4) that does not exceed the GPU count. Three cards give TP2, not TP3. It warns when it
  rounds down, because one card then sits idle for vLLM profiles.
- **llama-server:** `--tensor-split` is written for the actual count (`1` for a single card),
  since GGUF layer splits work with any number of cards.
- **Requirements are declared in the profile:** each profile in `config/models.yaml` carries a
  `metadata.requires` block (`gpus: [2, 4]` for vLLM, `min_gpus: 3` for llama-server, optional
  `host_ram_gib`, `estimate`, `note`), and `scripts/configure` reads them from there. The table
  above is the human-readable view of those declarations; the schema is in
  `config/CLAUDE.md` ("Profile requirements"). Add the block to every new profile.
- **Minimum-GPU handling:** profiles that cannot run at the detected count (for example
  `qwen3.8-flash-next-vllm` and `gemma4-26b-a4b` below four cards, `qwen3.8-flash-next` below
  three) are reported as `SKIP` with the reason and their `cmd` is left unchanged. They are
  hidden from `/v1/models` by an auto-managed `unlisted: true  # llmstack:auto` line that
  configure removes again once the profile becomes supported; a hand-written `unlisted:` line
  (`true` or `false`) is never touched and always wins, so a profile never ends up with two. `llmctl list` / `pick` / `swap` apply the same `scripts/llmhw.py` verdict: they hide these profiles, and `llmctl swap` refuses them with exit 2 unless `--force` (they will probably fail to start). That verdict comes only from `metadata.requires`; a hand-written `unlisted: true` or `false` does not change it.
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

- 3 cards: run `qwen3.8-27b-code` at TP2 (one card idle), or `qwen3.8-flash-next` (GGUF) for
  the larger model. Load one at a time.
- 2 cards: Qwen3.8-27B at TP2 is the default choice; expect about 70% of the 4-card serial
  speed and a 255K-token KV pool.
- 1 card: GGUF profiles only. `gemma4-12b-q4` should fit; `gemma4-26b-q8` is untested and may
  not fit with mmproj and KV (lower `--parallel`/`--ctx-size` if it OOMs).
- Always check `llmctl logs <profile>` the first time; a wrong TP size shows up as the server
  exiting during startup.
