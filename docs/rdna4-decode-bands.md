# RDNA4 (gfx1201) bimodal decode bands

On gfx1201 a vLLM server's decode throughput is **bimodal**. A server lands in one of two
stable bands when its process spawns, stays there for most of its life, and serves every
request at that band's rate. There is almost no variance inside a band, so a single
measurement tells you which band you are in — but nothing in the startup log tells you.
Clocks, temperatures, power, VRAM, graph-capture sizes and the log lines themselves are
identical in both bands.

A server that spawns into the slow band is a silent ~20% (dense) to ~50% (hybrid/MoE) loss
of throughput until it is restarted.

Upstream: ROCm/legacy-rocm-build#6347 (= ROCm/TheRock#9228). Related dispatch-path issues on
the same architecture: #6685 (= #9297, `hipStreamWaitEvent` adds ~17 µs to small kernels) and
#6689 (= #9300, grid-size dispatch cliff on full-die parts). Those two are *not* the cause of
the band split — see "Ruled out" below.

## Detecting it

```
scripts/llmband --model <profile> [--expect-tps <fast-band serial tok/s>] [--json]
```

Exit status: `0` fast band, `1` slow band, `2` undecided. Undecided includes every error path:
a false "restart the server" is worse than no answer.

The primary signal is **`mem_busy_percent`**, read from
`/sys/class/drm/card*/device/mem_busy_percent` while a single-stream decode runs. During
decode `gpu_busy_percent` reads ~100 in *both* bands — the GPUs look equally busy — while
`mem_busy_percent` sits far lower in the slow band. Reported centres:

| Band | `gpu_busy_percent` | `mem_busy_percent` |
|---|---|---|
| fast | ~100 | 62–67% |
| slow | ~100 | 24–27% |

Because the two clusters are far apart and do not move with the model, `mem_busy_percent` is an
**absolute** classifier: it needs no per-profile baseline, which is what makes it usable on a
freshly started server before you know what that server's fast rate should be. The threshold is
set at 45%, the midpoint of a wide gap.

Measured tok/s is only a cross-check, enabled by `--expect-tps`. It is the weaker signal because
absolute tok/s on these profiles depends on the prompt and (with speculative decoding) on the
acceptance rate, so a baseline measured on a different payload is not comparable. When the two
signals disagree the answer is `undecided`, not a guess.

Reported band ratios, fast:slow:

| Model class | Ratio |
|---|---|
| dense | 1.21–1.28 |
| MoE | 1.73 |
| gated-delta-net hybrid | 2.00–2.2 |

### Provenance of the numbers

**The band centres and ratios in the two tables above are from the upstream report, not from a
local two-band measurement.**

The clean local observation is a Flash-Next speed stage whose four blocks ran, in chronological
order, slow → fast → slow → slow, and never recovered. Because the slow blocks sit on both sides
of the fast one, no property of the payload orders that sequence: something changed underneath a
single server process, mid-run. That is the band behaviour, from one harness against one process.

What is **not** yet local is the `mem_busy` threshold. No run on this stack has yet been
classified by `mem_busy` and by tok/s in both bands, so 45% is adopted rather than verified.
Until it is, read a `slow` verdict as "restart and re-measure", not as proof. `llmband --json`
prints the counters behind every verdict so it can be audited afterwards.

Comparing tok/s across runs is also harder than it looks. With speculative decoding the rate
depends on the prompt and on the acceptance rate, so two numbers taken from different payloads
are not evidence of a band difference however far apart they are. Only same-payload comparisons
count, which is the whole reason `mem_busy` is the primary signal here.

## Ruled out as the mechanism

| Candidate | How it was excluded |
|---|---|
| Kernel-dispatch latency | Measured on-box at 2.0–2.6 µs/launch; a decode-shaped step is 1.34 ms eager. The band gap is tens of ms/step — three orders of magnitude off. No dispatch-related env knob moves it. |
| Clocks / power / thermals | Identical in both bands. `THROTTLE_STATUS` on this driver is not trustworthy and was not relied on. |
| PCIe link state | Gen5 x16 on every card in both bands, read from `/sys/bus/pci/devices/<bdf>/current_link_speed` (amd-smi's PCIe fields are idle-time artifacts). |
| Host CPU contention | A full-machine busy-loop load changed serial decode by <1%. |
| vLLM config | Startup logs of a slow and a fast spawn are line-for-line identical apart from timings. |

A secondary finding from the same investigation, unrelated to the bands: there is an idle-wake
ladder on this architecture — a kernel launch costs ~22 µs warm but 389–493 µs after ~10 ms of
idle, with GFXOFF enabled. That penalty is per-wake, so it affects trickle traffic, not
sustained decode.

## Relationship to the Flash-Next half-speed starts

`docs/flash-next-half-speed.md` documents half-speed Flash-Next starts and attributes them to a
full page cache at load time delaying the pinned per-layer-embedding table, with a prestart
wrapper as the guard. That explanation is supported by its own measurements (an 8-load series
where the one slow load was the one that started at 22 GiB `MemFree`).

These two write-ups may describe the same phenomenon through different proxies, and that is
**not yet settled**:

- Both produce a fixed-at-spawn, persists-for-process-life speed split.
- The half-speed doc's own table lists 28.3/28.5 tok/s at 20 GiB `MemFree` and 22.4 at 50 GiB,
  which is a split that low `MemFree` alone does not order correctly.
- The band story cannot explain why the prestart wrapper, which only frees page cache, reliably
  fixed it.

The honest reading is that low `MemFree` may raise the probability of drawing the slow band
rather than causing the slowdown directly. Deciding between them needs N≥5 cold spawns per arm
with each spawn classified by `mem_busy` *and* measured at serial and at concurrency, which is
the experiment to run next. Until then keep the prestart wrapper — it is cheap and it is
empirically effective — and use `llmband` as the post-start check that the wrapper worked.

## Operational guidance

1. After any cold start of a throughput-critical profile, run `scripts/llmband --model <profile>`.
2. On `slow`, restart the model (`llmctl swap` re-executes the profile's `cmd`, including any
   prestart wrapper) and check again. A restart draws a new band; it is not a repair.
3. On `undecided`, read the printed counters before acting. The common causes are a sampling
   window that missed the decode and an unreachable server.
4. Never compare tok/s across different prompts or acceptance rates when deciding a band. Use
   `mem_busy`, or compare against a baseline measured with the identical payload.
5. Benchmark results are only comparable within a band, so classify the band before believing a
   regression. A number from a long-lived container and a number from a cold spawn are not
   directly comparable, and re-measuring cold is the cheapest way to tell the two apart.
