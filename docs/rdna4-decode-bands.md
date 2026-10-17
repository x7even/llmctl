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
local two-band measurement.** Locally we have one side of the split at a time: a cold 27B
container measured 76–87 tok/s single-stream across four prompt shapes, while the same profile in
a container that had been up ~5.5 h measured 46% lower on the harness prompt; and a Flash-Next
speed stage ran slow at its first block, fast through `medium-256`, then slow from `long-512`
onward and never recovered — a flip inside one stage, which rules out a payload-size explanation.

So: the *existence* of two rates is local and solid, the *classifier threshold* is adopted from
upstream and still wants local validation. Until a run is classified by `mem_busy` and by tok/s
in both bands on this stack, treat a `slow` verdict as "probably, restart and re-measure" rather
than as proof. `llmband --json` prints the counters it used so a verdict can be audited after
the fact.

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
5. Benchmark results are only comparable within a band. A regression measured against a
   long-lived container is not evidence of a regression — re-measure on a cold spawn first.

Point 5 is the expensive lesson: a day of "the host move broke both production profiles" was
band noise, and the band check is what would have caught it in two minutes.
