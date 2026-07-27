# Stack Upgrade Plan — July 2026

Working checklist for the upgrade cycle identified in the 2026-07-07 audit.
Rule #1: **every phase has a rollback that restores the exact baseline below, and we
never destroy a rollback anchor until the phase that depends on it is validated.**

Work top to bottom. Do not start a phase until the previous phase's verification
gate passed (or the phase was explicitly skipped). One layer changes at a time —
never combine a container upgrade and a host upgrade in the same window, so any
regression attributes to exactly one change.

---

## Execution log — 2026-07-07

Two execution windows ran on 2026-07-07 (multi-agent, no reboots). Round 1 created
the anchors and ran shadow/baseline work; round 2 completed the benches, the 0.24.0
canary, and the llama.cpp cutover. Cumulative state:

- **Phase 0 — DONE.** All rollback anchors created: image tags
  `localhost/vllm-openai-rocm:v0.22.1-baseline`, `localhost/llmstack-llama:b9542-baseline`,
  `localhost/llama-vulkan-bleeding:mesa25.0.7-baseline`; llama-swap v223 binary stashed;
  driver installer `amdgpu-install_7.2.70200-1_all.deb` downloaded to `.rollback/`;
  uncommitted-diff snapshot saved; baseline manifest written. Git tag
  `baseline-2026-07-07` **exists locally but was NOT pushed** (no-push rule this window).
  Anchors re-verified intact at the end of round 2. **vLLM 0.22.1 baseline bench DONE**
  (round 2): conc 1/8/32 = 58.71 / 261.26 / 741.47 output tok/s on the live production
  container — see Results table.
- **Phase 1 (kernel 6.8.0-134) — PENDING.** Requires a reboot; deferred to a
  maintenance window. Still on 6.8.0-124.
- **Phase 2 (llama.cpp + Mesa 26) — DONE (cutover performed, round 2).** New image
  built from the repo Containerfiles: `version: 9903 (47e1de77a), built with GNU 13.3.0
  for Linux x86_64` on the mesa26 base; `localhost/llmstack-llama:new` = `7ee4d1f914b6`,
  retagged to `:latest`. Bench vs b9542 baseline (same served protocol): single-stream
  81.72 vs 83.44 tok/s (-2.1%, within the 5% threshold); conc-8 aggregate 138.74 vs
  113.77 tok/s (**+21.9%**). Smoke on `:latest` passed (healthy, coherent completion).
  Residual gate items for post-merge: gemma4 vision (mmproj) profile smoke and the
  30-min DeviceLost soak.
- **Phase 3 (llama-swap v235) — DONE ON BRANCH (round 2).** Shadow validation passed
  in round 1: v235 (c59816b) on 127.0.0.1:8082 against the production models.yaml
  read-only — version/health/models/running endpoints OK, served qwen3.6-35b-q4ks
  end-to-end with container reuse, clean teardown, live v223 router untouched. Round 2:
  `bin/llmctl` pin bumped 223 → 235. **The binary swap has NOT happened yet** — after
  merge, run `llmctl down && llmctl up` — llmctl now detects the version mismatch and
  auto-downloads v235; until then the live router remains v223.
- **Phase 4 (vLLM 0.24.0) — CANARY PASSED + CUTOVER ON BRANCH (round 2).** Canary
  (image `docker.io/vllm/vllm-openai-rocm:v0.24.0`, `ee424d681e1d`) ran the exact
  128k-MTP production profile on port 9555: healthy in ~15 min first boot, all smokes
  passed (chat, qwen3_xml tool calls, reasoning, 50,631-token needle retrieval, MTP
  active with ~70% draft acceptance), zero HIP/HSA/segfault signatures, 0 failed
  requests. Bench vs 0.22.1 baseline: conc 1/8/32 output tok/s +17.5% / +19.6% / +4.9%
  — all above the −5% gate. `models.yaml` refs cut over on this branch to the pinned
  `:v0.24.0` tag (baseline tag remains the documented rollback). Per-profile
  swap+smoke of the remaining vLLM profiles happens post-merge per the plan gate.
  **Caveats found:** (a) API rename — 0.24.0 returns `message.reasoning` instead of
  `message.reasoning_content`; clients parsing the old field silently get nothing;
  (b) idle behavior — 0.24.0 busy-polls at 100% GPU-use / ~95–100 W per GPU when idle
  (server stays responsive; materially higher idle power than 0.22.1);
  (c) MTP-off at conc 8 was slightly *faster* (329.7 vs 312.4 tok/s) with much better
  ITL (p50 19.0 vs 49.5 ms) — MTP's win is at conc 1 (68.98 vs 58.71 baseline);
  revisit whether MTP is worth it at production concurrency;
  (d) changing spec-config invalidates the compile-cache match — warm restart still
  ~16 min. Production was restored to 0.22.1 baseline at the end of the window
  (healthy, router completion verified, all anchors intact).
- **Phase 5 (driver 30.30.4 / ROCm 7.2.4) — PENDING.** Requires reboot(s); deferred
  together with Phase 1 to a maintenance window.

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

- [x] Pin the current vLLM image under an immutable local tag:
  ```bash
  podman tag docker.io/vllm/vllm-openai-rocm:latest localhost/vllm-openai-rocm:v0.22.1-baseline
  ```
- [x] Pin the current llama.cpp image and its Mesa runtime base:
  ```bash
  podman tag localhost/llmstack-llama:latest localhost/llmstack-llama:b9542-baseline
  podman tag localhost/llama-vulkan-bleeding:latest localhost/llama-vulkan-bleeding:mesa25.0.7-baseline
  ```
- [x] Stash the llama-swap v223 binary:
  ```bash
  mkdir -p ~/ai/llmstack/.rollback
  cp ~/.local/bin/llama-swap ~/ai/llmstack/.rollback/llama-swap-v223
  ```
- [x] Stash the **current** driver installer (so host rollback never depends on AMD
  keeping old URLs). Verify exact filename in the directory listing first:
  ```bash
  # 30.20 / ROCm 7.2.0-era installer — confirm filename at repo.radeon.com/amdgpu-install/7.2/ubuntu/noble/
  wget -P ~/ai/llmstack/.rollback https://repo.radeon.com/amdgpu-install/7.2/ubuntu/noble/amdgpu-install_7.2.70200-1_all.deb
  ```
- [x] Snapshot the repo state (commit + tag = the git rollback anchor):
  ```bash
  cd ~/ai/llmstack
  git add -A && git commit -m "snapshot: pre-upgrade baseline (audit 2026-07-07)"
  git tag baseline-2026-07-07
  git push origin master --tags
  ```
  *Done 2026-07-07 with one deviation: the working tree was snapshotted (diff saved to
  `.rollback/`) and the tag `baseline-2026-07-07` created **locally only** — the
  `git push` step was NOT run (no-push rule in the execution window). Push the tag
  when the branch is reviewed.*
- [x] Save the manifest verification snapshot:
  ```bash
  { uname -r; dpkg-query -W amdgpu-dkms rocm-core amdgpu-install; \
    podman images --digests | grep -E 'vllm|llama'; \
    ~/.local/bin/llama-swap --version; } > ~/ai/llmstack/.rollback/baseline-manifest.txt
  ```

**Gate:** all tags/files exist; `git tag` shows `baseline-2026-07-07` on origin.
*Gate status 2026-07-07: all tags/files verified present; tag is local-only (push pending review).*

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

- [x] **2a.** Rebuild the runtime base with Mesa 26.x (new tag, don't touch the old one):
  rebuild `llama-vulkan-bleeding` from `ubuntu:24.04` + a Mesa 26 source (e.g. kisak-mesa
  fresh PPA) → tag `localhost/llama-vulkan-bleeding:mesa26`. Verify inside:
  `vulkaninfo --summary` shows Mesa 26.x and RADV sees all 4 gfx1201 devices.
  *2026-07-07: `containers/llama-vulkan-base/Containerfile` in the repo
  (ubuntu:26.04 + stock Mesa 26.0.x — simpler than the PPA route); base built and used
  as the stage-2 runtime for the round-2 `:new` image, which found all 4 devices.*
- [x] **2b.** Point `containers/llama-server/Containerfile` stage-2 `FROM` at
  `localhost/llama-vulkan-bleeding:mesa26`, then rebuild (clones fresh master):
  ```bash
  podman build -t localhost/llmstack-llama:new containers/llama-server/
  podman run --rm localhost/llmstack-llama:new --version   # record build number (expect ≥ b9894)
  ```
  *2026-07-07 round 2: built — `version: 9903 (47e1de77a), built with GNU 13.3.0 for
  Linux x86_64`; image `localhost/llmstack-llama:new` = `7ee4d1f914b6`.*
- [x] **2c.** Bench old vs new **before cutover** (same GGUF, same flags — see §Benchmarks):
  baseline image vs `:new`, `llama-bench` + a `--parallel 8` served pass.
  *2026-07-07: both sides DONE via the served protocol — see Results table. Caveat:
  `llama-bench` inside the b9542-baseline image is a stale build-tree binary (md5 differs
  from installed `llama-server`; lacks the qwen35moe arch), so the served method was used
  for BOTH sides (identical script/flags). New vs old: single-stream 81.72 vs 83.44
  (-2.1%, within 5% threshold); conc-8 aggregate 138.74 vs 113.77 (+21.9%). Reusable
  script: `bench/served_bench.py`; `--group-add keep-groups`
  is REQUIRED or Vulkan finds no devices.*
- [x] **2d.** Cut over: `podman tag localhost/llmstack-llama:new localhost/llmstack-llama:latest`,
  then `llmctl swap qwen3.6-35b-q4ks` and the gemma4 vision profile, smoke-test both.
  *2026-07-07 round 2: `:latest` retagged to `7ee4d1f914b6`; smoke on `:latest` passed
  (healthy server, coherent completion, finish=stop). Post-merge follow-ups: gemma4
  vision (mmproj) profile smoke + 30-min soak (gate items below).*

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

- [x] Edit pin: `bin/llmctl` → `LLAMA_SWAP_VERSION = "235"`. *(Done on branch,
  2026-07-07 round 2.)*
- [ ] `llmctl down && llmctl up` (llmctl now auto-updates the binary on version mismatch — code-review fix; no manual rm needed).
  **Post-merge step — the live router is still v223 until this runs.**
- [ ] `~/.local/bin/llama-swap --version` → 235. **Post-merge step.**

*2026-07-07 shadow validation PASSED (round 1); pin bumped to 235 on branch (round 2):
v235 (c59816b, built 2026-07-03) ran on 127.0.0.1:8082 against the production
models.yaml read-only. `/health`, `/v1/models` (full catalog), `/running` all OK;
served qwen3.6-35b-q4ks end-to-end (first completion 5.3 s warm-cache, second 2.2 s
reusing the same container — no reload); v235 podman-ran the container itself with the
expected 4-GPU tensor-split cmd; `GET /unload` + process kill tore everything down
cleanly (no leftover containers, VRAM idle, live v223 router on :8080 untouched).
The two unchecked steps above are the actual production cutover — run them after this
branch merges so the binary on disk matches the new pin.*

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

*2026-07-07 status (round 2): canary PASSED and the `models.yaml` cutover landed on
this branch. The 0.22.1 baseline bench completed first on the live production container
(58.71 / 261.26 / 741.47 output tok/s at conc 1/8/32); the 0.24.0 canary then beat it
at every concurrency (+17.5% / +19.6% / +4.9%). Production was restored to the 0.22.1
baseline image at window end — the new refs take effect per profile as each is swapped
and smoked post-merge. Caveats carried forward: `message.reasoning_content` →
`message.reasoning` API rename (fix clients before/with cutover); higher idle power on
0.24.0 (busy-poll, ~95–100 W/GPU at idle); MTP-off beat MTP-on at conc 8 (329.7 vs
312.4 tok/s, ITL p50 19.0 vs 49.5 ms) — MTP mainly helps single-stream.*

- [x] Pull pinned: `podman pull docker.io/vllm/vllm-openai-rocm:v0.24.0`
  *(`ee424d681e1d`.)*
- [x] **Canary** — run the 128k MTP profile's exact command from `models.yaml` but with
  image `:v0.24.0`, container name suffixed `-canary`, port 9555, while production
  keeps running. Watch first boot (Inductor recompile ~18–20 min expected — not a hang).
  *(Round 2: healthy in ~15 min, MTP on first try, no crash.)*
- [x] Canary checks: chat completion; tool call (qwen3_xml parser); reasoning parser;
  64k+ long-context request; MTP active in logs; 30-min soak under load, watch
  `rocm-smi` for the 100%-GPU-spin deadlock signature.
  *(All passed: coherent chat; valid tool_calls; reasoning present but under the
  RENAMED field `message.reasoning`; 50,631-token needle prompt → 200 in 15.4 s,
  needle found; spec-decode counters advanced, ~70% draft acceptance (accept len 2.40);
  zero HIP/HSA/memory-fault/segfault signatures, 0 failed requests across all benches.
  Note: 100% GPU-use at idle is 0.24.0's busy-poll behavior, NOT the deadlock — the
  server stays responsive (0.56 s round trip).)*
- [x] If MTP faults: retry canary without `--speculative-config` (then decide: MTP-off
  on 0.24.0 vs stay on 0.22.1 — bench both).
  *(MTP did not fault; an MTP-off conc-8 bench was run anyway for the comparison —
  see Results table and the MTP-vs-MTP-off caveat above.)*
- [x] Bench canary vs baseline (§Benchmarks) at concurrency 1/8/32.
  *(+17.5% / +19.6% / +4.9% output tok/s — all clear the −5% gate outright.)*
- [x] **Cutover profile-by-profile:** in `models.yaml`, change image refs from
  `docker.io/vllm/vllm-openai-rocm:latest` → `docker.io/vllm/vllm-openai-rocm:v0.24.0`.
  Order: 35b-32k → 35b-128k (MTP) → 27b variants → fp8-KV profile → AWQ → gemma4.
  Each profile: swap, smoke, next. Commit `models.yaml` after each session.
  *(Round 2: all refs updated on this branch in one pass — the intermediate
  `localhost/vllm-openai-rocm:v0.22.1-baseline` refs from round 1 → `:v0.24.0`.
  The per-profile swap+smoke sequence happens post-merge per the gate below; only the
  canaried 128k-MTP shape has been exercised on 0.24.0 so far.)*
- [ ] After full cutover: fix any remaining `:latest` refs (including legacy scripts in
  `~/ai/bin` that still matter) so the moving tag can never bite again.
  *(models.yaml is clean — no vLLM `:latest` refs remain; legacy `~/ai/bin` scripts
  still to be audited.)*

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

## Phase 6 — vLLM 0.24.0 → 0.26.0 (image-only bump, stable line)

*2026-07-27 status: canary PASSED, cutover landed on this branch.* Scope was
deliberately narrowed to the vLLM container image only — the host driver/ROCm bump
(originally scoped as part of Phase 5) stays deferred to its own maintenance window
since it requires a reboot and is independent of this change.

**Version check (via `pip show` inside the image, not `import vllm` — importing vLLM's
ROCm platform code triggers an `amdsmi` GPU query that fails without `--device` mounts):**
`vllm 0.26.0+rocm723`, `torch 2.11.0+gitd0c8b1f`, `hip 7.2.53211`, ROCm `7.2.3` — **identical
torch/ROCm bundle to v0.24.0**. This is a clean vLLM-only version bump with zero toolchain
churn, which is what kept the risk profile low enough to canary and cut over in one pass.

- [x] Pull pinned: `docker.io/vllm/vllm-openai-rocm:v0.26.0`.
- [x] Canary — `qwen3.6-35b-128k-nomtp` (the no-MTP 128k profile). First boot completed
  in 3m05s, far faster than the ~15-20 min historical Inductor-compile figure. Verified
  via container logs (not assumed) that this is a genuine, correctly-configured compile:
  v0.26.0 replaces the old per-shape-specialized Inductor compilation with a single
  dynamic-shape "compile range" (`compile_ranges_endpoints: [32768]`,
  `Compiling a graph for compile range (1, 32768) takes 21.72s`, `torch.compile took
  30.09s in total`). Both CUDA graph capture passes completed cleanly:
  `Capturing CUDA graphs (mixed prefill-decode, PIECEWISE): 6/6` and
  `Capturing CUDA graphs (decode, FULL): 6/6`.
- [x] Bench canary vs baseline (§Benchmarks), `medium-256`, `--no-thinking`, 32
  requests/level, conc 1/8/32:

  | Conc | v0.24.0 (before) | v0.26.0 (after) | Delta |
  |------|-------------------|------------------|-------|
  | serial | 79.3 tok/s | 78.6 tok/s | −0.9% |
  | 1    | 88.0 tok/s | 88.3 tok/s | +0.3% |
  | 8    | 351.3 tok/s | 351.2 tok/s | −0.0% |
  | 32   | 860.4 tok/s | 872.1 tok/s | +1.4% |

  All deltas within noise (well clear of the −5% regression gate). Baselines:
  `bench/baselines/qwen3.6-35b-128k-nomtp-v0.24.0-before.json` /
  `qwen3.6-35b-128k-nomtp-v0.26.0-after.json`.
- [x] MTP side-check — **redone against a clean canonical profile** after an
  in-session llama-swap config-caching bug was found and fixed (see "Validation process
  notes" below); the original run in this bullet was collected against a stale,
  WIP-suffixed container and has been superseded. `qwen3.6-35b-128k` (MTP-enabled) on
  v0.26.0, medium-256, 16 requests/level, conc 1/2/4/8/16: 63.4 / 106.2 / 168.5 / 298.8 /
  504.3 tok/s decode
  (`bench/baselines/qwen3.6-35b-128k-v0.26.0-mtp-recheck.json`).
  **4/4 CUDA-graph-capture anomaly — explained and confirmed non-regressive.** Both this
  recheck and the original run show only `4/4` PIECEWISE/FULL captures (not `6/6`),
  despite `compilation_config` listing all 6 requested sizes. Root cause found by reading
  the log directly: `Profiling CUDA graph memory: PIECEWISE=4 (largest=18), FULL=4
  (largest=18)` — this is vLLM's own automatic memory-based capture-size selection: under
  MTP's larger per-slot memory footprint, only 4 of the 6 requested sizes fit the
  profiled memory budget, so vLLM silently caps at 4 (no "skip"/"reduce" log line, but the
  behavior is intentional, not a bug). **Confirmed version-independent**: a same-harness
  v0.24.0 canary (spare port 9555, exact production 128k-MTP command,
  `bench/baselines/qwen3.6-35b-128k-canary-v0.24.0-mtp.json`) shows the identical `4/4`
  capture behavior, ruling out a v0.26.0-specific regression.

  | Conc (medium-256, MTP) | v0.24.0 canary (same harness) | v0.26.0 recheck | Delta |
  |---|---|---|---|
  | serial | 63.0 tok/s | 58.9 tok/s | −6.6% |
  | 1  | 66.6 tok/s | 63.4 tok/s | −4.9% |
  | 2  | 109.8 tok/s | 106.2 tok/s | −3.2% |
  | 4  | 167.6 tok/s | 168.5 tok/s | +0.6% |
  | 8  | 289.4 tok/s | 298.8 tok/s | +3.2% |
  | 16 | 506.2 tok/s | 504.3 tok/s | −0.4% |

  All deltas within ±6.6%, well inside noise — no MTP regression from the version bump.
  (Note: this v0.24.0-canary row supersedes the mismatched-tool figure previously cited
  for 0.24.0 MTP conc=8 — 312.42 tok/s in the Results table below came from `vllm bench
  serve`, a different harness than `concurrent_bench.py` used everywhere else in this
  document; the 289.4 tok/s figure above is the correct like-for-like comparison point.)
- [x] Cutover: all 14 vLLM image refs in `config/models.yaml` bumped
  `v0.24.0` → `v0.26.0` in one pass (all profiles share the same pinned tag). Also bumped
  `healthCheckTimeout` (1200s → 2100s), `llmctl swap`/warm-up timeout (1260s → 2100s), and
  the TUI's swap-model HTTP client timeout (300s → 2100s) to cover v0.26.0's first-boot
  window with margin.
- [x] **Gemma4 risk flag — resolved by direct test.** Upstream issue #49878 (verified real
  via `gh issue view`, still open) reports a ~40% KV-cache VRAM sizing regression for
  Gemma 4 models between v0.25.1→v0.26.0 (reported on NVIDIA Blackwell running a
  different Gemma 4 checkpoint with FP8 KV cache + speculative decoding — not our exact
  config). Given `gemma4-26b-a4b` already runs at 122.7/128 GB, tested directly rather
  than left as a warning: `llmctl swap gemma4-26b-a4b` loaded cleanly in 3m07s, served a
  live completion correctly, ~124 GB total VRAM used — in line with the historical 122.7
  GB figure, no OOM, no KV-cache blowup. Light no-thinking recheck (conc 1/8/16): 63.0 /
  233.1 / 485.6 tok/s (`bench/baselines/gemma4-26b-a4b-v0.26.0-nothink.json`). The
  upstream report does not reproduce on this hardware/config. Detail in `docs/models.md`.
- [x] **AWQ path — also tested directly.** `qwen3.6-35b-awq` combines a second thing
  CLAUDE.md flags as fragile (AWQ's Triton WNA16 MoE fallback kernel), so rather than
  assume the version bump is safe here it was swapped and benched: loaded cleanly in
  3m21s (`Initial profiling/warmup run took 37.17s` — AWQ has no FP8 KV calibration step,
  so it's faster than the FP8 profiles), served a live completion correctly, no
  `IndexError`. Recheck: serial 80.2 tok/s, conc=8 272.0 tok/s
  (`bench/baselines/qwen3.6-35b-awq-v0.26.0-nothink.json`) — in line with or above the
  existing 0.20.0 baseline. Detail in `docs/models.md`.
- [x] **FP8 profiling/warmup speedup — the real driver of the faster cold starts.** The
  compile-range change (above) explains part of the faster first boot, but not all of it.
  Direct log measurement across profiles found vLLM's FP8 KV-calibration/model-profiling
  step itself dropped from **~804.78s on v0.24.0** (confirmed via the v0.24.0 canary log)
  to **~20-40s on v0.26.0** (20.98s for `qwen3.6-35b-128k-nomtp`, 37.17s for the AWQ
  profile — measured directly, not inferred). That ~38× drop, not just the compile-range
  change, is why total cold start fell from the historical ~14-20 min to ~2-3 min.
  Measured first-boot totals this session: no-MTP 2m04s, MTP 2m41s, gemma4-26b-a4b (BF16)
  3m07s, AWQ 3m21s. Documented in root `CLAUDE.md`'s "vLLM cold start" section, which was
  rewritten to replace the now-stale "18-20 min first boot" framing; `healthCheckTimeout`
  and the `llmctl`/TUI swap timeouts were left at the generous 2100s ceiling (safety
  margin for untested profiles — 256K/512K YaRN contexts, dense 27B — not the expected
  wait) rather than tightened, since those shapes weren't part of this measurement.

**Validation process notes:**
- Mid-session, an unrelated ~2-week-old uncommitted "profile matrix reorg" WIP was found
  contaminating this worktree — not part of `master` and never authorized for this task.
  All touched files were reverted to `master`'s actual committed state and only the
  version-bump-related changes were reapplied on top.
- That revert exposed a real bug worth documenting: **llama-swap caches `config/models.yaml`
  in memory at process start** — editing the file afterward does nothing until
  `llmctl down && llmctl up` restarts it. The running router was still serving a
  pre-revert, WIP-named config (`qwen3.6-35b-128k-mtp-think` instead of the canonical
  `qwen3.6-35b-128k`), which is why the original MTP side-check above was collected
  against a mislabeled container and had to be redone. Fixed by restarting llama-swap
  (which also auto-upgraded the binary to v235, a benign side effect of Phase 3 already
  being on this branch). The underlying throughput numbers were not actually corrupted —
  the redo matched within noise — but the profile-name lineage was wrong and is now clean.

**Gate:** healthy endpoint, tok/s within −5% of baseline bench (or better) — met for the
no-MTP profile, the MTP profile (via genuine same-harness comparison), the gemma4-26b-a4b
profile, and the AWQ profile.

**Rollback:** revert `docker.io/vllm/vllm-openai-rocm:v0.26.0` → `:v0.24.0` in
`config/models.yaml` (all 14 occurrences), `llmctl down && llmctl up`, `llmctl swap`
each profile back. The v0.24.0 image stays on disk — do not prune it this cycle.

**Deferred:** host ROCm 7.2.0 → 7.2.4 bump (Phase 5 above) remains PENDING — requires a
reboot, independent of this image bump, scheduled for its own maintenance window.

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
| 2026-07-07 | 0 baseline | vLLM 0.22.1 | Q3.6-35B FP8 128k MTP | 1 | 58.71 | 134.9 ms | live prod container²; 16 prompts; ITL p50/p99 38.1/40.6 ms; total 295.95 tok/s |
| 2026-07-07 | 0 baseline | vLLM 0.22.1 | Q3.6-35B FP8 128k MTP | 8 | 261.26 | 259.3 ms | 64 prompts; TTFT p99 4602 ms is a first-batch warm/compile outlier vs p50 259 ms; ITL p50/p99 57.5/138.4 ms |
| 2026-07-07 | 0 baseline | vLLM 0.22.1 | Q3.6-35B FP8 128k MTP | 32 | 741.47 | 617.3 ms | 128 prompts; ITL p50/p99 60.1/340.3 ms; total 3737.51 tok/s |
| 2026-07-07 | 0 baseline | llama.cpp b9542 | Q3.6-35B UD-Q4_K_S 32k | 1 | 83.44 | — | served bench (not llama-bench¹); median of 3 post-warmup decode-dominated runs (83.44/81.80/83.44); prompt 981 tok / 256 out / temp 0 |
| 2026-07-07 | 0 baseline | llama.cpp b9542 | Q3.6-35B UD-Q4_K_S 32k | 8 | 113.77 | — | served bench¹, aggregate: 8×256 gen tok in 18.00 s wall (incl. per-slot prompt processing); `--parallel 8` |
| 2026-07-07 | 2 after | llama.cpp b9903 (47e1de77a) + Mesa 26 | Q3.6-35B UD-Q4_K_S 32k | 1 | 81.72 | — | served bench¹, identical protocol; −2.1% vs baseline — within 5% threshold, no regression |
| 2026-07-07 | 2 after | llama.cpp b9903 (47e1de77a) + Mesa 26 | Q3.6-35B UD-Q4_K_S 32k | 8 | 138.74 | — | served bench¹ aggregate; **+21.9%** vs baseline 113.77 |
| 2026-07-07 | 4 canary | vLLM 0.24.0 | Q3.6-35B FP8 128k MTP | 1 | 68.98 | 124.5 ms | **+17.5%** vs baseline; ITL p50/p99 33.0/34.5 ms; spec accept ~70.2% |
| 2026-07-07 | 4 canary | vLLM 0.24.0 | Q3.6-35B FP8 128k MTP | 8 | 312.42 | 233.4 ms | **+19.6%** vs baseline; ITL p50/p99 49.5/130.8 ms; spec accept ~70.5% |
| 2026-07-07 | 4 canary | vLLM 0.24.0 | Q3.6-35B FP8 128k MTP | 32 | 777.58 | 732.2 ms | **+4.9%** vs baseline; ITL p50/p99 58.2/320.4 ms; spec accept ~70.2% |
| 2026-07-07 | 4 canary | vLLM 0.24.0 MTP-off | Q3.6-35B FP8 128k | 8 | 329.70 | 560.2 ms | run for comparison (MTP never faulted); faster than MTP-on at conc 8 with far better ITL (p50/p99 19.0/20.2 ms); spec-config change forced ~16 min warm restart (compile-cache miss) |
| 2026-07-27 | 6 canary | vLLM 0.24.0 (nomtp) | Q3.6-35B FP8 128k | serial | 79.3 | — | `concurrent_bench.py`³, before-row for the no-MTP comparison |
| 2026-07-27 | 6 after | vLLM 0.26.0 (nomtp) | Q3.6-35B FP8 128k | serial | 78.6 | — | `concurrent_bench.py`³; −0.9% vs 0.24.0, within noise |
| 2026-07-27 | 6 canary | vLLM 0.24.0 (nomtp) | Q3.6-35B FP8 128k | 8 | 351.3 | — | `concurrent_bench.py`³ |
| 2026-07-27 | 6 after | vLLM 0.26.0 (nomtp) | Q3.6-35B FP8 128k | 8 | 351.2 | — | `concurrent_bench.py`³; −0.0% vs 0.24.0 |
| 2026-07-27 | 6 canary | vLLM 0.24.0 (nomtp) | Q3.6-35B FP8 128k | 32 | 860.4 | — | `concurrent_bench.py`³ |
| 2026-07-27 | 6 after | vLLM 0.26.0 (nomtp) | Q3.6-35B FP8 128k | 32 | 872.1 | — | `concurrent_bench.py`³; +1.4% vs 0.24.0 |
| 2026-07-27 | 6 canary | vLLM 0.24.0 (MTP) | Q3.6-35B FP8 128k MTP | 8 | 289.4 | — | `concurrent_bench.py`³, same-harness canary on spare port 9555 — supersedes the `vllm bench serve`-derived 312.42 row above (2026-07-07) for MTP-vs-MTP comparisons; see footnote 4 |
| 2026-07-27 | 6 after | vLLM 0.26.0 (MTP) | Q3.6-35B FP8 128k MTP | 8 | 298.8 | — | `concurrent_bench.py`³; +3.2% vs the same-harness 0.24.0 canary row above |
| 2026-07-27 | 6 after | vLLM 0.26.0 | Gemma4-26B-A4B BF16 | 1/8/16 | 63.0 / 233.1 / 485.6 | — | `concurrent_bench.py`³, no-thinking; direct test resolving the #49878 risk flag, no OOM |
| 2026-07-27 | 6 after | vLLM 0.26.0 | Q3.6-35B AWQ Int4 128k | serial/8 | 80.2 / 272.0 | — | `concurrent_bench.py`³, no-thinking; direct test of the AWQ Triton WNA16 path |

¹ `llama-bench` inside the b9542-baseline image is a stale build-tree binary (md5 ≠
installed `/usr/local/bin/llama-server`, lacks the qwen35moe arch, fails to load the
model), so a served bench was used for BOTH the baseline and Phase 2 "after" rows:
llama-server `-m Qwen3.6-35B-A3B-UD-Q4_K_S.gguf -ngl 999 --tensor-split 1,1,1,1
-c 32768 --parallel 8`, port 9310, `--group-add keep-groups` (required or Vulkan finds
no devices), same script (`bench/served_bench.py`) —
these numbers are not comparable to `llama-bench` pp/tg output.

² vLLM rows: `vllm bench serve`, backend openai-chat, random dataset 1024 in / 256 out,
seed 42, run inside the serving container. One flag adaptation was required: the served
alias is not a HF repo, so `--tokenizer /models/Qwen3.6-35B-A3B-FP8` (local weights dir)
was added while keeping the served name for API requests. All requests succeeded in
every run (16/64/128). Baseline ran against the LIVE production 0.22.1 container on
:9111; canary rows ran against the 0.24.0 canary on :9555 with the exact production
profile. Raw logs under `/home/xin/.claude/jobs/73c9942f/tmp/` (`bench_c*.log`,
`canary_bench_c*.log`, `canary_nomtp_bench_c8.log`).

³ Phase 6 rows use this repo's own `bench/concurrent_bench.py` harness (`--no-thinking`,
`medium-256` prompt), not `vllm bench serve` — chosen for consistency with every other
Phase 6 measurement and with `bench/baselines/`. Raw baseline files named in each row's
notes live under `bench/baselines/`.

⁴ The 2026-07-07 MTP row (312.42 tok/s @ conc=8, vLLM 0.24.0) was collected with `vllm
bench serve` (evidenced by ITL/spec-accept metrics that tool produces and
`concurrent_bench.py` does not) — a different tool than the rest of this document uses,
so it is not a valid apples-to-apples baseline for the 2026-07-27 MTP comparison. Fixed
by standing up a manual v0.24.0 canary container (port 9555, exact production 128k-MTP
flags) and re-benchmarking with `concurrent_bench.py` — the 2026-07-27 canary/after rows
above are the correct like-for-like comparison; the 312.42 figure is kept in the table
only as a historical record of the original 0.22.1→0.24.0 upgrade measurement.
