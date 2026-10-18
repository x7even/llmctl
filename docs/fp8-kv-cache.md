# `--kv-cache-dtype fp8` on the Qwen3.8 27B: measured, and not shippable

**Verdict: do not set `--kv-cache-dtype fp8` on the shipped `qwen3.8-27b-*` profiles.** It is
not a quality regression and it is not a memory problem. It is **about 6x slower at full length**,
and that is enough to cross vLLM's worker-RPC watchdog: the executor declares the workers lost,
`EngineCore` shuts down, and every request after that gets a 500 until the container is restarted.

The slowness is the finding; the dead engine is a consequence of it. Raise
`VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS` from its default 300 to 1800 and the identical request
**completes and returns the correct needle** with the engine still alive. So this is not a hang
and not a kernel that refuses — it is a working configuration that is too slow to use at
131,072 tokens.

**And there is no shallower depth at which it pays.** A matched ladder against a bf16 control arm
puts the prefill penalty at **1.85x already at 8K**, rising monotonically to 6.13x at 131K, with
decode slower at every depth as well. There is no crossover, so there is no narrower profile
worth proposing — see the ladder below.

Measured 2026-10-18 on 4x R9700 (gfx1201), `docker.io/vllm/vllm-openai-rocm:v0.26.0`,
`qwen3.8-27b-think` at TP4 — the shipped profile with `--kv-cache-dtype fp8` appended and nothing
else changed. Four cold boots: two that crashed on the default watchdog, one with the watchdog
raised that completed, and one bf16 control arm.

This matters because the flag looks like the single best lever on this box. Concurrency at depth
is the scarce resource here, and FP8 KV is the only thing on the table that offers a large
amount of it for free. It does deliver that on paper. It just cannot serve.

---

## What it buys, and it is real

Both columns are the same profile on the same box and image, with `--kv-cache-dtype fp8`
appended and **nothing else changed**:

| | bf16 KV | FP8 KV |
|---|---|---|
| `GPU KV cache size` | 1,126,917 tokens | **2,133,560 - 2,178,707 tokens** |
| `Maximum concurrency for 131,072 tokens per request` | 8.60x | **16.28x - 16.62x** |
| attention block size | 784 tokens | **1568 tokens** (exactly 2x) |
| attention backend | `TRITON_ATTN` | `TRITON_ATTN` (retained) |
| `kv_cache_dtype` in engine config | `auto` | `fp8` |
| 130,752-token request, served | **75 s** | **455 s** |

**1.89x, not 2x.** Only the 16 full-attention layers' KV cache shrinks under FP8; the 48
gated-delta-net layers' recurrent state is unaffected. Do not round this to "doubles".

The FP8 pool is quoted as a range because it is not identical boot to boot: two FP8 boots of the
same config read 2,133,560 (16.28x) and 2,178,707 (16.62x), about 2% apart. The bf16 figure
reproduced exactly across boots. Quote the pair, not a single ratio — the gain is 1.89x against
the first reading and 1.93x against the second.

The bf16 column is a control arm run back to back with the FP8 one in the same script, not a
figure carried over from an older baseline. It reproduces the stored baseline exactly
(`bench/results/depth-cold-matched-20261018/`), which is what makes the 75 s against 455 s a
clean comparison: one flag, one difference.

The boot is completely clean — 199 log lines, no `NotImplementedError`, no "not supported", no
traceback. The backend does not fall back. This is worth stating plainly because it is the trap:
nothing at startup tells you anything is wrong.

Concurrency at 131K was genuinely KV-bound before this, not seq-bound: the pool allowed 8.60
full-length requests while `--max-num-seqs` was 32. And the obvious alternative lever is worse —
raising `--max-num-seqs` above 32 is exactly what closes TRITON_ATTN's 3D split-KV decode path
(`num_seqs > seq_threshold_3D`, which snaps to 32), which is the path
`docs/rdna4-long-context.md` depends on. FP8 KV raises the ceiling without touching that gate.
So the idea was sound. The implementation is what fails.

## Where it is clean

`bench/needle_check.py`, seed 1, three needle positions per depth, against the stored baseline
`bench/results/depth-cold-matched-20261018/triton-attn-needle.json`:

| depth | bf16 | FP8 |
|---|---|---|
| 16,384 | 3/3 | **3/3** |
| 65,536 | 3/3 | **3/3** |
| 130,752 | 3/3 | **0/3 — engine dead** |

The six passing cells returned the *same needle codes* as the baseline at the same
`(depth, position)`. Retrieval quality at 16K and 65K is indistinguishable, and whatever is wrong
is not precision loss.

Do not read more into the matching codes than they carry: position 0.5 returns `CCM-3770-ZXK` at
16,384, at 65,536 and at 130,752, so the code is seeded by cell position rather than by depth.
Matching codes confirm the two arms were asked the same questions; the retrieval result is what
confirms the answers were right.

## How it fails

A 130,752-token request. The engine log, trimmed to the sequence:

```
POST /v1/chat/completions            <- the deep request arrives
Avg prompt throughput: 6555.3 tokens/s, Running: 1 reqs
shm_broadcast.py:705] No available shared memory broadcast block found in 60 seconds.
   (x6, roughly one a minute, no scheduler progress lines in between)
dump_input.py:79] Dumping scheduler output ...
   num_computed_tokens=[94080], num_scheduled_tokens={...: 31360},
   kv_cache_usage=0.0655..., preempted_req_ids=[]
core.py:1332] EngineCore encountered a fatal error.
   TimeoutError                                    <- shm_broadcast.py:647
   The above exception was the direct cause of the following exception:
   TimeoutError: RPC call to sample_tokens timed out.   <- multiproc_executor.py:392
async_llm.py:704] EngineDeadError
POST /v1/chat/completions HTTP/1.1" 500 Internal Server Error
```

Read it from the scheduler dump outwards:

- **It dies in chunked prefill, not decode.** `num_computed_tokens=94080` with the next chunk
  at `31360`. `94080 = 3 x 31360` exactly: three prefill chunks completed, and the fourth is the
  one that did not come back.
- **The first three chunks were fast.** ~20 s for 94,080 tokens. Then no scheduler progress at
  all for the rest of the request's life.
- **The watchdog is `VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS`, default 300** (`vllm/envs.py`). The
  executor sets a deadline when it enqueues the RPC and raises
  `TimeoutError: RPC call to <method> timed out` if a worker's response does not arrive
  (`v1/executor/multiproc_executor.py:386-392`). Elapsed from last progress to fatal error:
  ~361 s. The numbers agree.
- **Once it fires, the server is finished.** `EngineCore` shuts the workers down and the API
  process reports `EngineDeadError`. It does not restart itself.
- **But the model was never stuck.** The same request on the same config with
  `VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS=1800` returned the correct needle, engine alive, zero
  `TimeoutError` lines. The watchdog is doing exactly its job; it is just being handed a step
  that legitimately takes longer than five minutes.

### The raised-watchdog arm, and the control

Same script, back to back, one flag apart:

| | 130,752-token request | outcome |
|---|---|---|
| bf16 KV | **75 s** | retrieved, engine alive |
| FP8 KV, watchdog 1800 s | **455 s** | retrieved, engine alive, 0 RPC timeouts |
| FP8 KV, watchdog 300 s (default) | — | `EngineDeadError`, 500s thereafter |

That is the whole result in three rows. **About 6x**, correct output, no recovery path at the
default watchdog. The 455 s and 75 s are the wall time of the same harness invocation on each
arm, so each includes the same fixed cost of building the prompt in Python; the engine-side gap
is therefore wider than 6x, not narrower.

During the FP8 request the engine's 10-second statistics logger printed **nothing at all for
roughly six minutes** — no scheduler progress, no throughput line — then the request returned
200. A single forward step holding the engine loop for minutes is also why this is worse than it
looks for a fleet: a step that long stalls every co-batched stream, not only the long one. The
flag's whole appeal was concurrency at depth, and a six-minute step is the opposite of that.

### It is steady state, not a one-time cost

The obvious hope was that 455 s was something that happens once — a kernel compile the two
crashed boots never survived long enough to write, or a per-process autotune. Three full-length
cells on one FP8 boot, each with a **different `--seed`** so the prompt differs and prefix caching
cannot hand a later run a free ride:

| cell | needle | time | prefix cache hit rate | result |
|---|---|---|---|---|
| seed 1 | `CCM-3770-ZXK` | **458 s** | 0.0% | retrieved |
| seed 7 | `MNE-4164-YBC` | **457 s** | 2.3% | retrieved |
| seed 23 | `NUF-4576-FGF` | **457 s** | 2.3% | retrieved |

Three distinct needles, so three genuinely different prompts; no cache help; and all three within
a second of each other and of the separate boot's 455 s. **Nothing amortises.** Every full-length
request costs this, so there is no warmup step that would make the flag shippable. The variance
being this small is itself informative — it is the signature of a fixed per-token cost in the
kernel, not of contention or scheduling luck.

Two one-time explanations are ruled out from the logs rather than by argument:

- **Nothing was compiled during the stall.** The Triton cache holds 26,865 files and **zero** were
  written during the six-minute window. (Check this with `find -L` — the cache paths in a worktree
  are symlinks into the main checkout, and a plain `find` silently reports an empty cache.)
- **The JIT monitor is identical on both arms.** vLLM's `jit_monitor` warns when a Triton kernel
  compiles during inference. It fires three times on the FP8 arm — and the bf16 control arm logs
  exactly the same count — all of them during the short calibration probe, before the deep request
  starts. Whatever the deep request is doing, it is not compiling.

### The full depth ladder: there is no shallow-depth exemption

This was the one route by which the flag could still have shipped. The 1.89-1.93x pool only
*binds* at full length — at 32K neither arm is pool-limited, because `--max-num-seqs 32` runs out
first — so if FP8 were at parity until somewhere deep, a profile capped at 65K would buy real
concurrency for nothing. The ladder closes that door. Both arms, same harness, same container
name, one flag apart, `depth_bench.py --concurrency 1 --gen 32`:

| depth | bf16 TTFT | FP8 TTFT | prefill penalty | bf16 decode | FP8 decode | decode penalty |
|---|---|---|---|---|---|---|
| 8,193 | 1.87 s | 3.46 s | **1.85x** | 46.8 tok/s | 43.6 tok/s | 1.07x |
| 16,387 | 4.10 s | 10.23 s | **2.50x** | 45.5 | 39.9 | 1.14x |
| 32,775 | 9.73 s | 33.43 s | **3.44x** | 43.4 | 34.0 | 1.28x |
| 65,551 | 25.35 s | 120.48 s | **4.75x** | 39.7 | 26.3 | 1.51x |
| 98,327 | 46.79 s | 261.05 s | **5.58x** | 36.6 | 21.5 | 1.70x |
| 131,007 | 74.28 s | 455.51 s | **6.13x** | 33.9 | 18.2 | 1.86x |

Every cell retrieved, `acc/step` 1.00 throughout, both engines alive at the end. Three readings
come out of this table:

- **The penalty never goes away.** 1.85x at the shallowest depth measured. There is no crossover
  anywhere on the curve, so no cap makes this flag worth setting.
- **It is not a constant tax — it is a change of slope.** Fit the two arms across the 16x depth
  range and bf16 prefill scales as roughly **depth^1.33** while FP8 scales as **depth^1.76**. The
  flag does not add overhead to the existing behaviour; it removes whatever sub-quadratic
  behaviour the bf16 path has. That is what losing parallelism over context length looks like,
  and it is the strongest evidence for the hypothesis below.
- **Decode pays too, not just prefill.** 1.86x slower per stream at 131K. The earlier runs
  measured prefill because a full-length needle request is nearly all prefill; the ladder
  separates them and both are worse.

The 455.51 s TTFT also reproduces the 455 s wall clock of the separate needle run almost exactly,
which independently confirms that essentially all of that time was prefill.

A free control fell out of this: the bf16 arm reads **33.9 tok/s at 131,007 tokens**, against the
**33.4** that `qwen3.8-27b-think` is documented at in `docs/rdna4-long-context.md`. The control
arm is the shipped profile, confirmed rather than assumed, which is what licenses reading the
other column as the flag's cost and nothing else.

### And it is worse under concurrency, which was the entire point

The flag's only argument was concurrency at depth. One modest fleet cell, 32,768 tokens x 4
concurrent requests, `--gen 64`:

| | mean TTFT | p90 TTFT | e2e | decode per stream |
|---|---|---|---|---|
| bf16 KV | 29.18 s | 39.19 s | 40.9 s | 19.3 tok/s |
| FP8 KV | 102.00 s | 138.75 s | 140.9 s | 11.3 tok/s |

**3.5x on TTFT, 3.5x on p90, 1.7x on per-stream decode** — at a depth and a width where the
bigger pool buys nothing, because `--max-num-seqs 32` is the binding limit there, not KV bytes.
To reach a depth where the pool does bind you have to go to full length, where the prefill
penalty is 6.13x. The trade is 1.93x nominal capacity for a 3.5-6x latency increase, which is
not a trade.

### Why the chunk is 31,360 and not 32,768 — and why that is *not* the cause

The chunk size quantizes to the attention block size, and FP8 does change the block size. This is
a hybrid GDN model, so vLLM has to make the attention page and the mamba page the same size, and
it does that by raising the attention block size until they match:

```
interface.py:905] Setting attention block size to 1568 tokens to ensure that
                  attention page size is >= mamba page size.
interface.py:929] Padding mamba page size by 0.13% to ensure that mamba page size
                  and attention page size are exactly equal.
```

FP8 halves the bytes per KV element, so the block size doubles to keep the attention page at or
above the (unchanged) mamba page. Measured on both arms, it doubles exactly: **784 -> 1568**.

It is tempting to stop there and say the coarser chunk makes a heavier forward step. **That is
backwards, and the arithmetic says so.** The prefill chunk is the largest multiple of the block
size that fits in `--max-num-batched-tokens 32768`:

| | block size | chunk |
|---|---|---|
| bf16 | 784 | 41 x 784 = **32,144** |
| FP8 | 1568 | 20 x 1568 = **31,360** |

FP8's chunk is *smaller*, by 2.4%. It does slightly **less** work per step and still takes about
six times as long. Chunk geometry is not the mechanism; the attention kernel itself is where the
time goes.

## What it is not

Each of these was checked rather than assumed, because each is what the symptom looks like:

- **Not out of memory.** `kv_cache_usage=0.0655` — 6.6% of the pool, one request in flight,
  `preempted_req_ids=[]`. The larger pool is not under any pressure. There is no
  `torch.OutOfMemoryError` and no HIP OOM anywhere in the log.
- **Not a quality regression.** 6/6 identical needle codes at 16K and 65K.
- **Not a kernel refusal.** No `NotImplementedError`, no assert, no "not supported" in either
  boot. `triton_attn.py` lists `fp8`, `fp8_e4m3` and `fp8_e5m2` among its supported cache
  dtypes.
- **Not the 3D split-KV path closing.** The `use_3d` predicate in
  `vllm/v1/attention/ops/triton_unified_attention.py` has eight disjuncts and **no dtype term**,
  and decode at 65K ran through that same path under FP8 and returned correct needles. The path
  works with FP8. (This is why the static reading in `config/CLAUDE.md` was right about the gate
  and still did not predict the failure — the gate was never the risk.)
- **Not a slow decode-band draw.** Both arms carried `GPU_MAX_HW_QUEUES=1`
  (`docs/rdna4-decode-bands.md`), and the failure is in prefill, not decode.
- **Not a hang.** With the watchdog raised the same request completes and returns the right
  needle, three times out of three, engine alive.
- **Not a one-time cost.** Three different-seed cells on one boot: 458 s, 457 s, and a separate
  boot's 455 s. No compile during the stall, no JIT difference against the control.
- **Not coarser prefill chunks.** FP8's chunk is *smaller* than bf16's — see above. This was the
  first draft's stated mechanism and it was backwards.

## Leading hypothesis: it halves the parallelism the 3D path depends on

**Labelled as a hypothesis, because nothing here instruments the kernel directly.** It is,
however, the first thing to test, it follows from something this repo already documents, and it
made a quantitative prediction that came true — see the slope result at the end of this section.

`docs/rdna4-long-context.md` establishes that on gfx1201 **nothing parallelises over context
length** unless TRITON_ATTN's 3D split-KV path is open — ROCm's custom paged-attention kernel is
disqualified by `head_dim = 256`, and the 2D fallback launches `(num_seqs, num_kv_heads)`, which
at TP4 and conc=1 is a single workgroup no matter how deep the prompt is. The whole reason
`qwen3.8-27b-think` ships `--attention-backend TRITON_ATTN` is to keep that 3D path open, and the
profile is 24x faster at 131K because of it.

FP8 doubles the attention block size, 784 -> 1568. That **halves the number of KV blocks** over
which the kernel has the option to split its work. On a path whose entire value is that it has a
segment dimension to parallelise over, and on a GPU the same document describes as starved for
work to distribute at depth, halving the splittable units is a credible way to lose a large
multiple — and it would bite hardest exactly where it is observed: deep, low-concurrency,
prefill-dominated requests.

This fits the evidence better than the alternatives. It explains why the penalty is in the
attention kernel rather than in chunk geometry, why it is steady state and amortises away over
nothing, why it scales with depth rather than appearing at 16K, and why the 2.4% *smaller* FP8
chunk does not help. It also lines up with vllm#57126 below, which reports the Triton
paged-attention path software-converting FP8 K/V: a conversion cost and a parallelism loss are
not exclusive, and both would land on the same kernel.

**The ladder's shape is the evidence.** A fixed cost — a software FP8 conversion per block, say
— would show up as a roughly constant multiplier across depth. A *parallelism* loss would not: it
would change the exponent, because the serial fraction grows with the number of blocks the kernel
can no longer split across. The ladder shows the second. Across a 16x depth range bf16 prefill
scales as about **depth^1.33** and FP8 as **depth^1.76**, and the ratio climbs monotonically from
1.85x to 6.13x rather than sitting flat. That does not prove the mechanism, but it is the
signature the mechanism predicts and it is not the signature a constant conversion cost predicts.
Both effects can be present; the slope says the parallelism term dominates.

What would test it directly: the block size is forced up only by the mamba/attention
page-equality constraint on this hybrid model, so a non-hybrid FP8 model on the same backend
should not show the doubling, and should not show this penalty. Failing that, instrument the 3D
predicate and count the segments actually launched on each arm.

## A related code fact, which is *not* the cause

`triton_attn.py` does carry an up-front FP8-KV capability check, and on ROCm it never runs:

```python
if current_platform.is_cuda():            # triton_attn.py:517
    ...
    if self.kv_cache_dtype.startswith("fp8") and not (
        current_platform.has_device_capability(89)
    ):
        raise ValueError("FP8 KV cache is not supported by the Triton attention backend ...")
```

`RocmPlatform._enum = PlatformEnum.ROCM` and `is_cuda()` tests `== PlatformEnum.CUDA`, so the
whole block is skipped on ROCm and there is no ROCm-side equivalent.

Be careful what this does and does not explain. That check is about *native FP8 support*
(SM89+), and gfx1201 has native FP8 — a missing capability would have broken the 16K cells, and
those were byte-identical to the baseline. **It is not the cause of this failure.** What it does
explain is the shape of the experience: ROCm gets no up-front refusal and no warning of any
kind, so there is nothing between "the flag is accepted" and "the server dies six minutes into a
long request". That asymmetry is worth reporting upstream on its own merits.

## Upstream neighbours

None of these is this bug, but FP8 KV on Triton attention has a track record worth knowing:

- [vllm#54690](https://github.com/vllm-project/vllm/issues/54690) — `kv_cache_dtype=fp8` crashes
  startup on **hybrid GDN models**. Same model class as ours; different symptom (startup, not
  inference).
- [vllm#13147](https://github.com/vllm-project/vllm/issues/13147) — FP8 KV **plus prefix
  caching** crashes the process on RDNA3. We run `--enable-prefix-caching`, so this is a live
  confound; it has not been separated here.
- [vllm#45562](https://github.com/vllm-project/vllm/issues/45562) — FP8 KV + `TRITON_ATTN` on
  MI300X gives silently wrong output on a sparse-attention path.
- [ThePie88/vLLM-ROCm-Windows#25](https://github.com/ThePie88/vLLM-ROCm-Windows/issues/25) — FP8
  KV on the Triton backend degrades with context and collapses, on gfx1101. Reports the KV
  capacity doubling as expected, as we do.
- [vllm#57126](https://github.com/vllm-project/vllm/pull/57126) — notes the Triton paged-attention
  path must *software-convert* FP8 K/V on RDNA3, which is slower than bf16, and guards the
  automatic FP8 selection for compressed-tensors checkpoints.

That last one is the one to read first if someone picks this up: a software-converted K/V on a
path that is already parallelism-starved at depth (`docs/rdna4-long-context.md`) is exactly how
one prefill chunk ends up taking minutes.

## If you want to re-test this

The gate is `bench/needle_check.py`, not throughput. FP8 KV is capable of degrading retrieval
before it degrades speed, and `depth_bench.py` sends filler with `ignore_eos` and never reads
the reply, so it cannot see a retrieval failure at all. Run the needle sweep on both arms with
the same `--seed` and require every cell to retrieve before looking at a single tok/s figure.
Here that gate is also what caught the crash, because it was the only thing issuing a
full-length request.

Keep the container when you do it. Both of these runs used a side-port container on `:9199`
rather than the router, and the first one used `podman run --rm`, so when `EngineCore` died the
container went with it and `podman logs` had nothing left to read. Drop `--rm` (keep
`--replace`) or the trace is lost. This is the same gap `llmctl logs` has — it is
`podman logs -f`, and llama-swap retains nothing.

Not ruled out, and cheap to try if the 1.89x is wanted badly enough:

- ~~a lower `--max-model-len`, which caps how deep a single request can get~~ — ruled out by the
  ladder. The penalty is 1.85x at 8,193 tokens, so there is no depth cap that makes the flag
  worth setting; capping only limits how bad it gets
- a smaller `--max-num-batched-tokens`, which shrinks the per-chunk step independently of depth
- dropping `--enable-prefix-caching`, per vllm#13147
- ~~raising `VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS`~~ — done, see above. It converts the dead
  engine into a very slow one, which is how we know this is slowness and not a hang. It is not a
  fix: 455 s for one request is not a configuration anyone should serve from

None of these is a configuration anyone should ship without a fresh needle sweep behind it.
