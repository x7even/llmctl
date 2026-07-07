# Stack Upgrade Plan — July 2026

Working checklist for the upgrade cycle identified in the 2026-07-07 audit.
Rule #1: **every phase has a rollback that restores the exact baseline below, and we
never destroy a rollback anchor until the phase that depends on it is validated.**

Work top to bottom. Do not start a phase until the previous phase's verification
gate passed (or the phase was explicitly skipped). One layer changes at a time —
never combine a container upgrade and a host upgrade in the same window, so any
regression attributes to exactly one change.

---

## Baseline manifest (state as of 2026-07-07 — the "way we are now")

Everything needed to recognize and restore today's stack:

| Layer | Baseline value |
|---|---|
| Booted kernel | `6.8.0-124-generic` (6.8.0-134 installed, not booted; amdgpu DKMS built for both) |
| amdgpu-dkms | `1:6.16.6.30200000-2238411.24.04` (driver release 30.20.0) |
| amdgpu-install | `30.20.0.0.30200000-2238411.24.04` |
| rocm-core (host) | `7.2.0.70200-43~24.04` |
| vLLM image | `docker.io/vllm/vllm-openai-rocm:latest` → **vLLM 0.22.1**, local image ID `7b70baed00f0`, registry digest `sha256:368b2992c776ad653e40e9e00d38aa51cf1e9a16558b05d07c42818abd9ec031` |
| llama.cpp image | `localhost/llmstack-llama:latest` → build **b9542** (commit `6b80c74`), image ID `eecb234037d4` |
| llama runtime base | `localhost/llama-vulkan-bleeding:latest`, image ID `0c6690b0e921`, Mesa RADV **25.0.7** |
| llama-swap | **v223** (`29d3d9ba`, built 2026-06-04), binary at `~/.local/bin/llama-swap`, pinned in `bin/llmctl` |
| llmstack repo | HEAD `80b593f` + uncommitted changes to `config/models.yaml`, `tui/data.go` |
| Live profile | `qwen3.6-35b-128k` (TP=4, MTP, 131072 ctx) on the 0.22.1 image |

**CRITICAL — moving-tag trap:** `vllm-openai-rocm:latest` on Docker Hub now points to
v0.24.0. Our local `:latest` is still the 0.22.1 image. Any `podman pull ...:latest`
(including an accidental one) replaces it. Phase 0 pins it under a stable local tag
**before anything else happens**.

---

## Phase 0 — Rollback anchors (run first, zero risk, no service impact)

- [ ] Pin the current vLLM image under an immutable local tag:
  ```bash
  podman tag docker.io/vllm/vllm-openai-rocm:latest localhost/vllm-openai-rocm:v0.22.1-baseline
  ```
- [ ] Pin the current llama.cpp image and its Mesa runtime base:
  ```bash
  podman tag localhost/llmstack-llama:latest localhost/llmstack-llama:b9542-baseline
  podman tag localhost/llama-vulkan-bleeding:latest localhost/llama-vulkan-bleeding:mesa25.0.7-baseline
  ```
- [ ] Stash the llama-swap v223 binary:
  ```bash
  mkdir -p ~/ai/llmstack/.rollback
  cp ~/.local/bin/llama-swap ~/ai/llmstack/.rollback/llama-swap-v223
  ```
- [ ] Stash the **current** driver installer (so host rollback never depends on AMD
  keeping old URLs). Verify exact filename in the directory listing first:
  ```bash
  # 30.20 / ROCm 7.2.0-era installer — confirm filename at repo.radeon.com/amdgpu-install/7.2/ubuntu/noble/
  wget -P ~/ai/llmstack/.rollback https://repo.radeon.com/amdgpu-install/7.2/ubuntu/noble/amdgpu-install_7.2.70200-1_all.deb
  ```
- [ ] Snapshot the repo state (commit + tag = the git rollback anchor):
  ```bash
  cd ~/ai/llmstack
  git add -A && git commit -m "snapshot: pre-upgrade baseline (audit 2026-07-07)"
  git tag baseline-2026-07-07
  git push origin master --tags
  ```
- [ ] Save the manifest verification snapshot:
  ```bash
  { uname -r; dpkg-query -W amdgpu-dkms rocm-core amdgpu-install; \
    podman images --digests | grep -E 'vllm|llama'; \
    ~/.local/bin/llama-swap --version; } > ~/ai/llmstack/.rollback/baseline-manifest.txt
  ```

**Gate:** all tags/files exist; `git tag` shows `baseline-2026-07-07` on origin.

**Full "abort everything" from any later point** = the union of each phase's rollback
below, in reverse order of what was applied. Because every phase pins its predecessor,
this is always mechanical: retag images back to `:latest`, restore llama-swap binary,
`git checkout baseline-2026-07-07 -- config/models.yaml bin/llmctl`, boot old kernel,
reinstall stashed driver deb.

---

## Phase 1 — Kernel security update (reboot into 6.8.0-134)

Already installed; DKMS module already built. This is a reboot, not an install.

- [ ] Confirm no one is mid-job on the GPUs (`podman ps`, check llmpanel).
- [ ] `sudo reboot`
- [ ] After boot: `uname -r` → `6.8.0-134-generic`; `dkms status | grep 6.8.0-134` → installed.

**Gate:** `rocminfo | grep -c gfx1201` matches baseline,
`llmctl up` + `llmctl swap qwen3.6-35b-128k` reaches healthy, one chat completion succeeds.

**Rollback:** reboot → GRUB → *Advanced options* → select `6.8.0-124-generic`.
**Do not** run `apt autoremove` (it would delete the -124 kernel) until Phase 5 is done.

---

## Phase 2 — llama.cpp b9542 → current master, Mesa 25.0.7 → 26.x

Two changes in one image, but staged so gains are attributable and rollback is a retag.
Motivation: 352 builds behind (b9894 as of 2026-07-07); post-b9542 AMD fixes
(DeviceLost #25005/#24872, FA overflow #24909); Mesa ≥25.3 RADV compute work ≈ +13%
prefill on RDNA.

- [ ] **2a.** Rebuild the runtime base with Mesa 26.x (new tag, don't touch the old one):
  rebuild `llama-vulkan-bleeding` from `ubuntu:24.04` + a Mesa 26 source (e.g. kisak-mesa
  fresh PPA) → tag `localhost/llama-vulkan-bleeding:mesa26`. Verify inside:
  `vulkaninfo --summary` shows Mesa 26.x and RADV sees all 4 gfx1201 devices.
- [ ] **2b.** Point `containers/llama-server/Containerfile` stage-2 `FROM` at
  `localhost/llama-vulkan-bleeding:mesa26`, then rebuild (clones fresh master):
  ```bash
  podman build -t localhost/llmstack-llama:new containers/llama-server/
  podman run --rm localhost/llmstack-llama:new --version   # record build number (expect ≥ b9894)
  ```
- [ ] **2c.** Bench old vs new **before cutover** (same GGUF, same flags — see §Benchmarks):
  baseline image vs `:new`, `llama-bench` + a `--parallel 8` served pass.
- [ ] **2d.** Cut over: `podman tag localhost/llmstack-llama:new localhost/llmstack-llama:latest`,
  then `llmctl swap qwen3.6-35b-q4ks` and the gemma4 vision profile, smoke-test both.

**Gate:** bench shows no regression (expect prefill gain from Mesa 26); vision profile
(gemma4-26b-q8, exercises mmproj) works; no DeviceLost in logs after a 30-min soak.
Known non-blocker: batch≥9 MoE throughput cliff (llama.cpp #25356) exists in both old
and new builds — optional local threshold patch if concurrent GGUF traffic matters.

**Rollback:** `podman tag localhost/llmstack-llama:b9542-baseline localhost/llmstack-llama:latest`
(and stage-2 base back to `:mesa25.0.7-baseline` if rebuilding). Restart profile. Done.

---

## Phase 3 — llama-swap v223 → v235

Motivation: v233 fixes UI-induced inference slowdown; v234 rejects concurrency
overages before streaming; v230 adds `-config-dir`.

- [ ] Edit pin: `bin/llmctl` → `LLAMA_SWAP_VERSION = "235"`.
- [ ] `llmctl down && rm ~/.local/bin/llama-swap && llmctl up` (auto-downloads v235).
- [ ] `~/.local/bin/llama-swap --version` → 235.

**Gate:** router serves both a vLLM profile and a GGUF profile; model swap works;
concurrency limit still enforced (v234 changed rejection behavior — verify clients
handle the earlier rejection); TUI (`llmpanel`) still parses status.

**Rollback:** `cp ~/ai/llmstack/.rollback/llama-swap-v223 ~/.local/bin/llama-swap`,
revert the pin (`git checkout baseline-2026-07-07 -- bin/llmctl`),
`llmctl down && llmctl up`.

---

## Phase 4 — vLLM 0.22.1 → 0.24.0 (canary, then per-profile cutover)

Highest-risk phase: v0.24.0 moved Qwen/quantized MoE models to Model Runner V2 by
default, and there are open ROCm reports on MTP+cudagraph (vllm#47196) and multi-GPU
RDNA4 (vllm#40980). Canary the riskiest profile first; never rely on `:latest`.

- [ ] Pull pinned: `podman pull docker.io/vllm/vllm-openai-rocm:v0.24.0`
- [ ] **Canary** — run the 128k MTP profile's exact command from `models.yaml` but with
  image `:v0.24.0`, container name suffixed `-canary`, port 9555, while production
  keeps running. Watch first boot (Inductor recompile ~18–20 min expected — not a hang).
- [ ] Canary checks: chat completion; tool call (qwen3_xml parser); reasoning parser;
  64k+ long-context request; MTP active in logs; 30-min soak under load, watch
  `rocm-smi` for the 100%-GPU-spin deadlock signature.
- [ ] If MTP faults: retry canary without `--speculative-config` (then decide: MTP-off
  on 0.24.0 vs stay on 0.22.1 — bench both).
- [ ] Bench canary vs baseline (§Benchmarks) at concurrency 1/8/32.
- [ ] **Cutover profile-by-profile:** in `models.yaml`, change image refs from
  `docker.io/vllm/vllm-openai-rocm:latest` → `docker.io/vllm/vllm-openai-rocm:v0.24.0`.
  Order: 35b-32k → 35b-128k (MTP) → 27b variants → fp8-KV profile → AWQ → gemma4.
  Each profile: swap, smoke, next. Commit `models.yaml` after each session.
- [ ] After full cutover: fix any remaining `:latest` refs (including legacy scripts in
  `~/ai/bin` that still matter) so the moving tag can never bite again.

**Gate (per profile):** healthy endpoint, tool calls OK, tok/s within −5% of baseline
bench (or better), no HIP memory-access faults in `llmctl logs` over a working day.

**Rollback (any profile, any time):** revert that profile's image ref to
`localhost/vllm-openai-rocm:v0.22.1-baseline` in `models.yaml`, `llmctl swap` it back.
Full rollback: `git checkout baseline-2026-07-07 -- config/models.yaml` + restart.
The baseline image stays on disk — **never prune it during this campaign.**

---

## Phase 5 — Host driver 30.20 → 30.30.4 + ROCm 7.2.0 → 7.2.4

Last, after Phases 1–4 are stable, in a maintenance window. Containers ship their own
ROCm userspace; this phase mainly updates the kernel driver + host tools, so nothing
above depends on it — it can be deferred indefinitely if 1–4 already delivered.
(gfx1201 / R9700 is explicitly listed as supported in the ROCm 7.2.4 matrix.)

- [ ] Preflight: Phase 0 stashed installer exists; `dkms status` clean; models unloaded.
- [ ] ```bash
      wget https://repo.radeon.com/amdgpu-install/7.2.4/ubuntu/noble/amdgpu-install_7.2.4.70204-1_all.deb
      sudo apt install ./amdgpu-install_7.2.4.70204-1_all.deb
      sudo amdgpu-install --usecase=rocm     # driver 30.30.4 → DKMS 6.16.13 + ROCm 7.2.4
      sudo reboot
      ```
- [ ] Post-boot: `dkms status` → amdgpu 6.16.13 installed for running kernel;
  `cat /opt/rocm/.info/version` → 7.2.4; `rocminfo` sees 4× gfx1201.

**Gate:** TP=4 vLLM profile loads and serves (exercises RCCL across all 4 cards —
re-run the concurrency-8 bench once; 4×R9700 RCCL failures were reported upstream in
rccl-tests#162, so verify explicitly); llama.cpp Vulkan profile unaffected (doesn't
use ROCm); 24 h soak with no amdgpu errors in dmesg.

**Rollback:** the box boots even if ROCm userspace is unhappy (containers are
self-contained). Restore driver:
```bash
sudo amdgpu-install --uninstall
sudo apt install ~/ai/llmstack/.rollback/amdgpu-install_7.2.70200-1_all.deb
sudo amdgpu-install --usecase=rocm      # reinstalls 30.20 stream / DKMS 6.16.6
sudo reboot
```
If the new DKMS module itself fails to boot cleanly: GRUB → the -124 kernel still has
the 6.16.6 module until autoremove — which is why autoremove waits until after this gate.

---

## Post-campaign cleanup (only after everything is validated)

- [ ] `sudo apt autoremove` (drops kernel -124)
- [ ] Prune dead images (~60+ GB): `vllm-r9700-fixed` (101 GB!), old `rocm/vllm-dev` tags,
  dangling `<none>` layers — **keep all `*-baseline` tags for one more cycle**.
- [ ] Update `README.md` / Containerfile comments to reference v0.24.0.
- [ ] Commit + push; mark done: `git tag validated-2026-07 && git push --tags`.

---

## Holds (decided in the audit — revisit next cycle)

- **HWE kernel 6.17** — ROCm 7.2.4 fully supports 6.8 GA; no need.
- **podman 5.x/6.x** — direct `--device` passthrough works fine on 4.9.3.
- **llama.cpp HIP backend** — Vulkan measurably faster for our MoE mix on gfx1201,
  and HIP has an open idle-hang bug (ROCm#5706/#6298). Stay Vulkan.
- **AITER** — keep `VLLM_ROCM_USE_AITER=0`; C++/ASM kernels still broken on RDNA4.

---

## Benchmarks (before/after protocol)

Fixed for every comparison: same model file, same quant, same context length, same
TP, request shape 1024 in / 256 out, seed 42, 3 runs, report median. Bench the
**baseline first** (fill the table below) so "after" always has a "before".
Cross-engine numbers are never compared across different quants.

**vLLM** (against whichever image is on the port):
```bash
podman exec <container> vllm bench serve \
  --backend openai-chat --base-url http://127.0.0.1:<port> --model <served-name> \
  --dataset-name random --random-input-len 1024 --random-output-len 256 \
  --num-prompts 128 --max-concurrency <1|8|32> --seed 42
```
Record output tok/s, TTFT p50/p99, ITL p50/p99. Canonical model: Qwen3.6-35B-A3B-FP8,
TP=4, 131072 ctx — one pass MTP-on, one MTP-off.

**llama.cpp**:
```bash
podman run --rm --device=/dev/kfd --device=/dev/dri -v /mnt/models/llm:/models:ro \
  --entrypoint llama-bench <image> \
  -m /models/unsloth/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_S.gguf \
  -p 1024 -n 256 -b 2048 -ub 512 -ngl 999 -r 3 -o md
```
Plus a served pass at `--parallel 8` with the same shape (llama-bench alone misses the
batch≥9 MoE cliff, issue #25356). Canonical models: Qwen3.6-35B-A3B-UD-Q4_K_S and
Qwen3.5-122B-A10B-Q4_K_M.

### Results table (fill in as we go)

| Date | Phase | Engine+version | Model/quant/ctx | Conc. | tok/s | TTFT p50 | Notes |
|---|---|---|---|---|---|---|---|
| | 0 baseline | vLLM 0.22.1 | Q3.6-35B FP8 128k MTP | 1 | | | |
| | 0 baseline | vLLM 0.22.1 | Q3.6-35B FP8 128k MTP | 8 | | | |
| | 0 baseline | vLLM 0.22.1 | Q3.6-35B FP8 128k MTP | 32 | | | |
| | 0 baseline | llama.cpp b9542 | Q3.6-35B UD-Q4_K_S 32k | 1 | | | |
| | 0 baseline | llama.cpp b9542 | Q3.6-35B UD-Q4_K_S 32k | 8 | | | |
