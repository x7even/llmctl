# The MTP drafter OOM: 32 concurrent 8K prompts kill the engine

`qwen3.8-27b-code` — the default profile — dies during a cold burst of 32 concurrent
8,192-token requests. The engine does not degrade, queue or 429; all four tensor-parallel
workers raise `torch.OutOfMemoryError` within the same step and the EngineCore exits.

This is not a capacity limit. The KV pool is below 75% when it happens.

---

## What it looks like

Every one of the four workers, at `multiproc_executor.py:1007`:

```
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 638.00 MiB.
GPU 0 has a total capacity of 31.86 GiB of which 0 bytes is free.
Of the allocated memory 26.72 GiB is allocated by PyTorch, with 2.00 MiB allocated
in private pools (e.g. CUDA Graphs), and 601.12 MiB is reserved by PyTorch but
unallocated. If reserved but unallocated memory is large try setting
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True to avoid fragmentation.
```

and then, from the EngineCore at `core.py:1332`:

```
RuntimeError: Worker failed with error '<the message above>'
```

The 638 MiB **matches** the MTP drafter's concatenated `[embedding, hidden]` buffer for a
full `--max-num-batched-tokens` batch: `32768 x (2 x 5120) x 2 bytes = 640 MiB`. The
arithmetic lands 2 MiB away, which makes it the obvious candidate — but nothing here
identifies the allocation, and the next section shows batch size is not what triggers the
failure in any case.

### Three things about the failure mode that mislead

1. **The container does not die.** Only the EngineCore child exits; the APIServer at pid 1
   stays up. `podman inspect` reports the same container ID and `StartedAt` across the
   crash, and llama-swap keeps it. A survival check keyed on the container ID returns a
   false PASS — this was measured.
2. **`/health` keeps returning 200**, through a dead engine. So does `/v1/models`.
3. **The client finds out ~4.5 minutes later.** Between the worker OOM and the first
   client-visible `EngineDeadError`, the container repeats
   `No available shared memory broadcast block found in 60 seconds`. Requests issued in
   that window simply return no content.

The only reliable signal is the request outcome plus the container's own stdout. On a
systemd-managed host `journalctl --user` captures that stdout and survives the re-swap;
`podman logs` shows only the replacement container, and `llama-swap.log` holds HTTP
records only.

---

## Why it happens

`--gpu-memory-utilization 0.95` budgets the **KV pool**. Activations, workspaces and graph
pools are not in that budget; they grow lazily into whatever driver-level VRAM is left over.
Sampling `/sys/class/drm/card*/device/mem_info_vram_used` at 1 Hz across a run shows what
that leaves:

| state | free VRAM per card (MiB) |
|---|---|
| fresh spawn, model loaded, idle | 4091 / 4075 / 4075 / 4123 |
| 16 s into the first trivial `1024 x conc=1` cell | 35 / 19 / 19 / 67 |
| idle again, after sustained load | 671 / 655 / 626 / 703 |

Those three rows are measured. What follows from them is arithmetic.

PyTorch's caching allocator takes essentially all driver headroom within seconds of the
first request and never gives it back, so from that point the drafter's 638 MiB can only
come out of PyTorch's own pool. The traceback says what was in it: **0 bytes free on the
device, and 601.12 MiB reserved-but-unallocated in the cache.**

601 is less than 638. So no arrangement of that cache could have served the request —
this is **plain exhaustion**, not fragmentation. The working set simply does not fit, and
the "If reserved but unallocated memory is large try setting
`expandable_segments:True`" sentence is PyTorch's stock boilerplate on every OOM, not a
diagnosis of this one. It is worth stating plainly because that sentence is the obvious
thing to act on and it points at the wrong lever.

### A theory this replaces

The 638 MiB matching one full 32,768-token batch invites "a full batch is the trigger".
That is too simple: the replacement container that came up after the crash pushed roughly
ten full 32,768-token batches through the same drafter (the whole 32K depth pass plus part
of the 64K one) and survived every one. A full batch is necessary, not sufficient — the
batch has to be full *while* driver headroom is already gone, which is why only a fresh
spawn driven straight into a wide cold burst reproduces it.

---

## Reproduction

A **fresh spawn** is required. A pass on a container that has already been under load
proves nothing — the allocator's pool is in a different state and the crash does not
reproduce. The measured recipe:

```bash
llmctl unload && sleep 5 && llmctl swap qwen3.8-27b-code
# wait for /health 200, then, cold:
python3 bench/depth_bench.py --model qwen3.8-27b-code --max-model-len 131072 \
  --depths 1024,8192 --concurrency 1,8,32 --gen 128 --no-thinking \
  --timeout 600 --run-nonce <a value not used before>
```

`--run-nonce` matters: prompts are a pure function of the seed, so a re-run without a
fresh nonce re-sends text the engine still has cached and never drives a cold prefill.

Stock reproduced **2 of 2** fresh spawns. The failing cell is `8192 x conc=32`: 11 of 32
requests returned "no content tokens received", `agg_decode_tok_s` 0.0.

Judge an arm by **both** of:

- `ok == N` on every cell of the saved JSON, and
- a `journalctl --user` window over the run with no `OutOfMemory` / `EngineDeadError`.

Not by the container ID, and not by `/health`.

---

## Pricing the candidates before benchmarking them

A repro arm costs ~20 minutes; a spawn and one `grep 'GPU KV cache size'` costs ~3. Since
the remedy has to be judged on KV pool as much as on survival, every candidate was priced
by its KV line first. Fresh spawn each, same image, nothing else varied:

| `PYTORCH_ALLOC_CONF` | `--max-num-batched-tokens` | `--gpu-memory-utilization` | KV pool | max conc @131K | vs stock |
|---|---|---|---|---|---|
| — | 32768 | 0.95 | 1,009,850 | 7.70x | — |
| `expandable_segments:True` | 32768 | 0.95 | 785,687 | 5.99x | **-22.2%** |
| `expandable_segments:True` | 32768 | 0.97 | 822,923 | 6.28x | -18.5% |
| `expandable_segments:True` | 16384 | 0.95 | 947,293 | 7.23x | -6.2% |
| — | **16384** | 0.95 | **1,079,109** | **8.23x** | **+6.9%** |

Two things fall out of this.

**Raising `--gpu-memory-utilization` cannot buy the allocator flag's cost back.** 0.01 is
about 326 MiB per card on a 31.86 GiB card and the gap is ~2 GB per card, so 0.95 -> 0.97
recovers about a third of it (and the config guide caps the knob at 0.97 anyway). Measured:
-22.2% becomes -18.5%.

**Halving `--max-num-batched-tokens` is the better lever on KV pool.** It halves the very
buffer whose allocation fails — 16384 x (2 x 5120) x 2 B = 320 MiB instead of 640 — and
the profiling run's own peak shrinks with it, so vLLM hands *more* to the KV pool, not
less: +7-9%, and admission at the full 131K window goes from 7.70x to ~8.3x concurrent
requests.

**It is still a trade, on prefill.** A smaller chunk means a wide cold burst takes longer
to admit, and that cost is not hypothetical or confined to deep prompts — it already shows
at 8K. See the arm below. Intermediate values (24576, i.e. a 480 MiB buffer) were not
tested.

## The allocator flag, and why it is not the remedy

PyTorch's own error message names one: `expandable_segments:True`. It makes the allocator
grow a single virtual segment per size class instead of carving fixed blocks, which is
what would remove a "601 MiB free, none of it contiguous" failure.

**It works — and it costs 22% of the KV pool, which lands on exactly the axis that matters
here.** The table above prices it: 1,009,850 -> 785,687 tokens, 7.70x -> 5.99x concurrent
requests at the full 131K window. Idle free VRAM per card rises from ~4,090 to ~6,070 MiB,
i.e. roughly 2 GB per card that vLLM's profiling pass now declines to hand over.

That cost also means a clean pass at 785K tokens does not by itself credit the flag — the
same run has ~2 GB per card more headroom, which is a gpu-util cut in disguise. See the
arm below.

A `medium-256` throughput sweep cannot price any of this: ~500-token requests never
approach the pool. The cost is concurrent deep requests, and only a depth sweep sees it.

It is kept documented rather than shipped, because it remains the right lever if a future
model's drafter buffer cannot be shrunk by batch size. To set it, add the container env var:

```yaml
        -e PYTORCH_ALLOC_CONF=expandable_segments:True
```

**The variable is honoured by the pinned image, and that was checked rather than assumed.**
There is no runtime getter for allocator settings in this build (`_get_allocator_settings`
is absent; `get_allocator_backend()` returns `"native"` either way), so it was confirmed by
a negative test: launching with `-e PYTORCH_ALLOC_CONF=expandable_segments:NotABool` and
GPUs attached raises

```
ValueError: Expected 'True' or 'False' at index 2 in ConfigTokenizer but got 'NotABool'
```

It is therefore parsed, not silently dropped. This check is worth doing for any env-var
knob on this stack — an invalid `--attention-backend` on the same image silently falls back
to auto-selection instead of erroring.

The image's torch is 2.11.0+gitd0c8b1f, which carries all three spellings
(`PYTORCH_CUDA_ALLOC_CONF`, `PYTORCH_ALLOC_CONF`, `PYTORCH_HIP_ALLOC_CONF`). The
vendor-neutral `PYTORCH_ALLOC_CONF` is the one set here.

### What one fresh-spawn arm showed, and what it does not establish

The whole `1024,8192 x {1,8,32}` cold sequence on a fresh spawn with the flag: every cell
clean, `ok` equal to the request count on all six, and a clean journal window. Stock failed
the same sequence on 2 of 2 fresh spawns, 11 of 32 requests lost at `8192 x conc=32`.

So the flag does prevent the crash. **But the free-VRAM trace says why is still open:**

| | idle free | minimum free under the full sequence |
|---|---|---|
| stock | ~4,090 MiB/card | **19 MiB/card** (reached within 16 s of the first request) |
| `expandable_segments:True` | ~6,070 MiB/card | **4,415 MiB/card** |

Headroom never got tight in the flagged arm, so this arm cannot separate two explanations:

1. the allocator no longer fragments, which is the mechanism the flag is for; or
2. there was simply 2 GB more per card to begin with, because the pool is 22% smaller —
   i.e. a `--gpu-memory-utilization` cut in disguise, which stock would also survive.

Note what the two rows do show independently of that: the flagged run's *peak transient*
demand was only ~1,650 MiB per card, while stock's allocator had taken ~4,070 MiB and held
it. Stock is not short of memory; it is hoarding and then failing to find a contiguous
block inside what it hoarded. That is consistent with lazy physical commit under expandable
segments, and it is the reason the flag is a candidate at all — but it is one pair of runs.

Separating (1) from (2) needs a stock control with `--gpu-memory-utilization` lowered until
its KV line also reads ~785K tokens. Until that control runs, do not state a mechanism
here.

Throughput at the cell that used to die was unchanged: `8192 x conc=32` read 28.5
aggregate tok/s with TTFT mean 74.7 s, against 28.4 / 74.4 s measured on a surviving stock
container at the same cell. The flag is not buying stability with decode speed.

---

## The leading candidate: `--max-num-batched-tokens 16384`

One fresh spawn, stock allocator, batched tokens halved. The whole
`1024,8192 x {1,8,32}` cold sequence: every cell `ok` equal to its request
count, clean journal window. The same sequence killed stock on 2 of 2 fresh
spawns.

It also survived with *less* idle headroom than stock — 2,997 against 4,091 MiB
per card, because more VRAM went to the KV pool — so this is not a
`--gpu-memory-utilization` cut in disguise. What changed is the size of the
working set, and with it the size of the request: 320 MiB instead of 640.

Note what this arm does **not** show. Its minimum free VRAM under load was
676 MiB per card, against 19 on stock, so it never approached the boundary at
all — there is no moment in it where a 320 MiB request succeeded somewhere a
640 MiB one would have failed. Both this fix and the allocator flag worked by
keeping headroom away from zero, by different routes. Neither arm isolates
*why* 638 MiB was unavailable beyond the arithmetic already given above.

| | KV pool | conc @131K | idle free | min free under load | `8192 x 32` | agg tok/s @ `8192 x 32` |
|---|---|---|---|---|---|---|
| stock, 32768 | 1,009,850 | 7.70x | ~4,090 MiB | **19 MiB** | **11 of 32 lost** | — (28.4 on a warmed container) |
| `expandable_segments`, 32768 | 785,687 | 5.99x | ~6,070 MiB | 4,415 MiB | ok | 28.5 |
| stock, **16384** | **1,097,728** | **8.38x** | ~2,990 MiB | 676 MiB | ok | **17.6** |

**That last column is the price, and it needs a second sample.** At `8192 x 32` the two
32768 runs both read ~28.5 agg tok/s with ~74.5 s mean TTFT (28.4 / 74.4 on a surviving
stock container, 28.5 / 74.7 with the allocator flag), where 16384 read 17.6 with 99.1 s
mean and 201.7 s p90. That is the halved prefill chunk showing up on the widest cell, and
16384 is n=1 there. A `1024 x 8` reading of 188.7 against ~350 on both 32768 arms is also
unexplained and may be a one-off; it is being re-measured.

If the prefill cost confirms, it is still the better trade: a dead EngineCore takes every
client on the stack down and answers `/health` 200 for minutes while doing it. Slower
admission on a 32-wide cold burst is a cost you can see and plan around.

The KV figure here read 1,097,728 tokens against 1,079,109 in the triage
spawn, so call it ~1.08-1.10M, +7-9% over stock, and do not quote a single
spawn's digits as exact — vLLM's profiling pass varies a little run to run.

Band was checked, because on gfx1201 an unclassified spawn is not a
measurement: `llmband` read FAST, 36.22 steps/s against a 36.18 baseline. So
the throughput figures in this section are not slow-draw artifacts.

---

## A different engine death with the same symptom

`qwen3.6-27b-code` lost 11 of 32 requests at `32768 x conc=32` with the same
client-visible signature — `no content tokens received`, `agg_decode_tok_s`
0.0, the same 11-of-32 count. It is **not** this bug. There is no
`Tried to allocate` and no `torch.OutOfMemoryError` anywhere in its journal
window. What killed it was:

```
(EngineCore) ERROR [core.py:1332] EngineCore encountered a fatal error.
(EngineCore) ERROR [core.py:1332] TimeoutError: RPC call to sample_tokens timed out.
```

preceded by roughly half an hour of
`No available shared memory broadcast block found in 60 seconds` from the same
EngineCore, and followed by `EngineDeadError` reaching the client.

So the symptom `no content tokens received` means **"the engine died"**, not
"the engine ran out of memory". Two distinct defects produce it on this
hardware, and they need different fixes:

| | `qwen3.8-27b-code` | `qwen3.6-27b-code` |
|---|---|---|
| cell | `8192 x 32` | `32768 x 32` |
| fatal error | `torch.OutOfMemoryError` in all 4 workers | `TimeoutError: RPC call to sample_tokens` |
| journal has `Tried to allocate` | yes | **no** |
| status | fix measured below | **root cause not established** |

Do not assume the batched-tokens change below helps the second one. A smaller
prefill chunk means more steps per batch, which could as easily make an RPC
timeout worse. It is unmeasured on that profile; `32768 x 32` on
`qwen3.6-27b-code` is the cell that would tell.

**Operationally: always read the container's own stdout before attributing a
lost-request cell to memory.** Both defects look identical from the client and
from `/health`.

### What the change costs on the workload the profile is actually for

The `8192 x 32` figure above is the worst cell in the grid. It is not what
`qwen3.8-27b-code` is for — that profile is the shallow-prompt, many-agent
default, and depth work belongs on `qwen3.8-27b-think`. On the README's own
harness (`medium-256`, 128 requests per level, same FAST-band container):

| | stock, 32768 | **16384** | delta |
|---|---|---|---|
| serial | 66.0 | 67.4 | +2% |
| conc=8 | 339.2 | 352.6 | +4% |
| conc=16 | 570.7 | 566.0 | -1% |
| conc=32 | 851.2 | 861.8 | +1% |

All four are inside run-to-run noise. **So the change is free on the profile's
main workload**, costs nothing on KV pool (it gains 7-9%), and the price is
confined to cold bursts deep enough to fill a prefill chunk.

That also settles the `1024 x 8` reading of 188.7 in the depth arm: at
`medium-256 conc=8` the same container reads 352.6, so the depth-arm cell was a
one-off and not a property of the config.
