# Does `GPU_MAX_HW_QUEUES=1` help Flash-Next? No.

`GPU_MAX_HW_QUEUES=1` is load-bearing on the three `qwen3.8-27b-*` profiles: it is the
difference between a 35.6 tok/s serial draw and a 67.2 one, and `config/CLAUDE.md` told the
next person to measure it on the remaining profiles rather than assume it generalises. This is
that measurement for `qwen3.8-flash-next-vllm`. It does not generalise.

## Files

| file | arm | what it is |
|---|---|---|
| `band-stock.json` | stock | `scripts/llmband --calibrate` output: step rate, `mem_busy` under load |
| `band-flagged.json` | `GPU_MAX_HW_QUEUES=1` | same |
| `bench-stock.json` | stock | `concurrent_bench.py`, `medium-256`, conc 1 and 8 |
| `bench-flagged.json` | `GPU_MAX_HW_QUEUES=1` | same |

## Controls

Same profile, same nightly image, same host, consecutive boots through llama-swap. The only
difference is one `-e` line in the profile's `cmd`, and `podman inspect` was used on each
container to confirm which env it actually received — the flagged arm reported
`GPU_MAX_HW_QUEUES=1`, the stock arm reported only `HSA_ENABLE_SDMA=0`. Benchmarks are
`medium-256`, `--no-thinking`, 16 requests per level.

**The page-cache confound was controlled, and it is the one that matters here.** A Flash-Next
container that loads while the page cache is full comes up at roughly half speed (~28 vs ~56
tok/s serial) and stays there, which looks exactly like a slow band draw
(`docs/flash-next-half-speed.md`). The profile's `cmd` runs through `scripts/llm-prestart
--need-free-gib 80`, which drops cached model files before `podman run`. MemFree was logged
immediately before each boot: 135 GiB for the stock arm, but only 1.6 GiB for the flagged arm,
whose boot therefore took 4m16s against the stock arm's 2m04s — `llm-prestart` dropping 92 GiB
of cache and re-reading ~48 GiB of weights from disk. Both arms still came up at ~54-56 tok/s
serial, nowhere near the ~28 tok/s half-speed signature, so neither hit the pathology.

## Result

| arm | serial | conc=8 | `mem_busy` | steps/s | boot |
|---|---|---|---|---|---|
| stock | **55.6** | 187.4 | 32.4% | 58.4 | 2m04s |
| `GPU_MAX_HW_QUEUES=1` | 53.5 | **197.2** | 30.6% | 54.3 | 4m16s |

Serial −3.8%, conc=8 +5.2%.

## Reading it

- **There was no band to fix.** `mem_busy` under load is the discriminator that held on the 27B,
  where the two bands separate at 26% against 46% with no overlap. Here both arms read ~31%.
  Both also landed at or above the best stored conc=8 figure for this profile (182 tok/s), so
  neither spawn was a slow draw in the first place — which is why the flag has nothing to
  recover.
- **The two deltas are noise, and they point in opposite directions.** A −3.8% serial and a
  +5.2% conc=8 from one spawn each, on a profile whose documented conc=8 spread is 150-185, is
  not a result.
- **This measures whether the flag is needed here, not whether it works here.** The distinction
  matters and it is easy to fumble. The flag's job is to convert a slow draw into a fast one;
  this profile's stock spawn was already fast, so there was nothing for it to recover and the
  pair cannot speak to its effect on a slow Flash-Next draw. What it does establish — and what
  decides the config — is that Flash-Next reaches full speed without it.
- **The cause is not established.** It is tempting to explain the absence of a band by
  architecture: Flash-Next is a 6B-active MoE whose step is dominated by expert routing and
  all-reduce, the 27B a dense GDN hybrid whose step is a long chain of small kernel launches,
  and only the latter should suffer queue contention. That is a hypothesis, not a finding, and
  there is a second difference sitting right beside it: **Flash-Next runs the nightly image,
  the 27B runs v0.26.0.** Model and image both vary, so this pair cannot attribute the
  difference to either. Separating them would need the 27B on the nightly image, or Flash-Next
  on v0.26.0 if it will run there at all.
- **The flag was reverted; Flash-Next ships stock.**

The 35B and `gemma4` profiles are still unmeasured, and after this result they should be
measured rather than assumed either way.
