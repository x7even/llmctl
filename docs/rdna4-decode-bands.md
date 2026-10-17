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
scripts/llmband --model <profile> --calibrate   # once, against a server believed to be fast
scripts/llmband --model <profile>               # thereafter, after any cold start
```

Exit status: `0` fast band, `1` slow band, `2` undecided. Undecided covers every error path and
the no-baseline case: a false "restart the server" is worse than no answer.

The signal is the **decode step rate**, measured as streamed SSE chunks per second and compared
against a stored per-profile baseline in `config/band-baselines.json`.

Step rate is the right quantity for two reasons. The band moves the duration of a decode step,
so step rate is what it acts on directly. And with speculative decoding one SSE chunk is one
decode step carrying however many tokens that step accepted, so token rate varies with the
acceptance rate — which itself moves with the prompt, the temperature and whether thinking is
enabled — while step rate does not. Two step rates are comparable where two token rates are not.

Reported band ratios, fast:slow:

| Model class | Ratio |
|---|---|
| dense | 1.21–1.28 |
| MoE | 1.73 |
| gated-delta-net hybrid | 2.00–2.2 |

The narrowest of those puts the slow band 17.4% below the fast one, and within-band variance is
a few percent, so the default `--tolerance 0.12` separates them with room on both sides.

### Why there is no baseline-free threshold

`mem_busy_percent` was tried as an absolute classifier and **it does not work on this rig.**

The idea was sound: during decode `gpu_busy_percent` reads ~100 in both bands, so the GPUs look
equally busy, while upstream reports `mem_busy_percent` splitting cleanly into two clusters —
24–27% slow against 62–67% fast. That would have been an absolute signal needing no baseline,
usable on a freshly started server before anyone knows what that server's rate should be.

Measured here, a healthy, continuously decoding 27B FP8 TP4+MTP server sampled **36.7–37.5%
mean** (p50 37–38, max 42, tight) — between upstream's two clusters. A 45% threshold, the
midpoint of upstream's gap, would have called that server slow and told the operator to restart
it. Upstream measured a different model and configuration, so the absolute values simply do not
transfer.

`llmband` therefore reports `mem_busy` and compares it against the baseline's own `mem_busy`,
but it only ever corroborates. It cannot call a server slow on its own, and when it contradicts
a slow step rate the verdict is downgraded to undecided rather than acted on. A disagreeing
`mem_busy` does not block a `fast` verdict, because "carry on" is the safe outcome.

The practical consequence is that **a baseline is mandatory**, and it must be recorded on this
rig, for this profile, on this image. Re-calibrate after any image, profile, driver or firmware
change, and remember that `--calibrate` records whatever band the server happened to be in — it
is a fast-band reference only if the server really was in the fast band when you ran it.

### What the local evidence actually supports

The clean local observation is a Flash-Next speed stage whose four blocks ran, in chronological
order, slow → fast → slow → slow, and never recovered. Because the slow blocks sit on both sides
of the fast one, no property of the payload orders that sequence: something changed underneath a
single server process, mid-run. That is the band behaviour, from one harness against one process.

The band *ratios* in the table above are still upstream's, not measured here. Measuring them
locally needs N cold spawns with each classified and measured at serial and at concurrency,
which is the experiment to run next.

### A regression that is *not* a band draw, and how its shape says so

A comparison of the same image and the same profile against a stored baseline (clean cold
container, nothing else on the GPUs) came out 5–15% down on three of four prompts and failed the
−5% gate on the headline one: medium-256 serial −14.9%, conc 8 −8.1%, conc 16 −10.8%. The
useful part is the fourth prompt. `xlarge-2048` is **flat** at concurrency
— +0.1% at conc 4, +1.0% at conc 8, −0.4% at conc 16 — while being 12–15% down at serial and
conc 1.

That shape rules out a band draw. A band is a whole-process property: it would take xlarge-2048
down with everything else, at every concurrency. A deficit that disappears exactly where each
step does the most compute is instead the signature of a **fixed per-step overhead increase**,
amortised away once the step is long enough to hide it. That points at the per-step collective
path rather than at anything payload-shaped, which is what promotes the TP4 all-reduce
candidate below from "leading remaining" to directly indicated — and it is also why a
single-boot A/B on any throughput lever is still uninterpretable: the two mechanisms coexist.

The practical consequence is that `llmband` cannot be used to accept or reject arms whose lever
plausibly changes serial step rate; it can only be used where the arm provably leaves batch 1
alone (the capture-size lever is one such case: batch 1 lands on captured size 3 either way).

## Ruled out as the mechanism

| Candidate | How it was excluded |
|---|---|
| Kernel-dispatch latency | Measured on-box: 2.56 µs/launch host submit, 2.77 µs back-to-back, 21.5 µs launch→completion, and a 500-dispatch decode-shaped step at 1.34 ms eager / 1.10 ms as a graph replay. At ~450–550 dispatches per token that is 3–5% of a healthy step, and graph replay saves only 0.24 ms, so neither dispatch cost nor total graph-capture failure can produce a tens-of-ms/step gap. Three different wait paths agree within 0.8 µs, so there is no host wake penalty either. Upstream measures the same floor on the same part and reports it unchanged across ROCm 7.2 / 7.14 / 10.0 (ROCm/TheRock#9241). `AMD_DIRECT_DISPATCH=0` is 13–23% *worse*, which incidentally proves direct dispatch is already on. **Scope limit:** this measures a fresh HIP context, so it says the per-launch floor is normal — not that a given long-lived vLLM process is healthy. It also does not test #9297's actual trigger, which needs several `hipStreamWaitEvent`s left pending while timing; the probe used only completed sync fences, so #9297 is untested here rather than excluded. |
| Clocks / power / thermals | Identical in both bands. `THROTTLE_STATUS` on this driver is not trustworthy and was not relied on. |
| PCIe link state | Gen5 x16 on every card in both bands, read from `/sys/bus/pci/devices/<bdf>/current_link_speed` (amd-smi's PCIe fields are idle-time artifacts). |
| Host CPU contention | A full-machine busy-loop load changed serial decode by <1%. |
| vLLM config | Startup logs of a slow and a fast spawn are line-for-line identical apart from timings. |

Still **not** excluded, and the leading remaining candidate: the TP4 collective path. On
gfx1201 every fast all-reduce backend is unavailable — QuickReduce is gfx94/gfx95 only,
CustomAllreduce disables itself above two PCIe-only GPUs, and AITER does not support this
architecture at all — so the engine falls back to `PYNCCL`, confirmed in the startup log as
`Using ['PYNCCL'] all-reduce backends ... out of potential backends: ['NCCL_SYMM_MEM',
'QUICK_REDUCE', 'FLASHINFER', 'AITER_CUSTOM', 'CUSTOM', 'SYMM_MEM', 'PYNCCL']`. Every TP4
collective therefore goes through generic RCCL over PCIe, and that path is unmeasured.

Two secondary findings from the same investigation, neither of which explains the bands:

- **An idle-wake ladder.** A kernel launch costs ~22 µs warm but 137 µs after a 1 ms host gap
  and 389 µs after 10 ms, with GFXOFF enabled in `ppfeaturemask`. It is a per-wake cost, not a
  clock ramp — 3 s of heavy GEMM immediately beforehand does not remove it. At step scale a
  20 ms host gap costs +0.75 ms. It matters for TTFT and idle-to-first-token, not for sustained
  decode.
- **Speculative decoding shrinks the captured graph set**, by an exact rule read out of the
  image's own `vllm/config/compilation.py`. `adjust_cudagraph_sizes_for_spec_decode` rounds
  every requested size *up* to a multiple of `uniform_decode_query_len =
  num_speculative_tokens + 1`, and **drops** any rounded size that exceeds
  `max_cudagraph_capture_size` — which `compilation.py` itself sets to the largest size that was
  requested. With MTP at `num_speculative_tokens: 2` the multiple is 3, so the production list
  `1 2 4 8 16 32` becomes `{3, 6, 9, 18}`: 32 rounds to 33, 33 > 32, and it is silently dropped.
  Four graphs survive, the largest at 18 query-tokens = **6 sequences**. Above 6 concurrent
  sequences every step runs eager. `3 6 12 24 48 96` round-trips unchanged and covers 32
  sequences, i.e. all of `--max-num-seqs`.

  This is not free, and the price is measured: `scripts/llmkv` on the 27B profile reads
  1,009,850 KV tokens (17.60 GiB/GPU, effective utilization 0.9368) with the production list
  against 972,613 (17.25 GiB/GPU, 0.9285) with the aligned one — **−3.7% KV budget for 0.35
  GiB/GPU more graph memory**, because graph memory is taken before the KV cache is sized. So
  the lever trades context for concurrency and has to clear that 3.7% to be worth taking.

  Note also that the startup log reports the *requested* list (`cudagraph_capture_sizes': [...]`
  in the engine config dump), never the post-rounding set, and the tqdm capture bar that does
  carry the surviving count does not reach `podman logs` on this stack. There is no log line
  that states what was actually captured, which is why this went unnoticed.

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

1. Calibrate once per profile per image: `scripts/llmband --model <profile> --calibrate`,
   against a server you have reason to believe is fast (for instance one that has just produced
   a normal benchmark result).
2. After any cold start of a throughput-critical profile, run `scripts/llmband --model <profile>`.
3. On `slow`, restart the model (`llmctl swap` re-executes the profile's `cmd`, including any
   prestart wrapper) and check again. A restart draws a new band; it is not a repair.
4. On `undecided`, read the printed counters before acting. The common causes are a sampling
   window that missed the decode and an unreachable server.
5. Never compare tok/s across different prompts or acceptance rates when deciding a band. Use
   step rate, or compare against a baseline measured with the identical payload.
6. Benchmark results are only comparable within a band, so classify the band before believing a
   regression. A number from a long-lived container and a number from a cold spawn are not
   directly comparable, and re-measuring cold is the cheapest way to tell the two apart.
