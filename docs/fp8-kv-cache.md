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

- a lower `--max-model-len`, which caps how deep a single request can get
- a smaller `--max-num-batched-tokens`, which shrinks the per-chunk step independently of depth
- dropping `--enable-prefix-caching`, per vllm#13147
- ~~raising `VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS`~~ — done, see above. It converts the dead
  engine into a very slow one, which is how we know this is slowness and not a hang. It is not a
  fix: 455 s for one request is not a configuration anyone should serve from

None of these is a configuration anyone should ship without a fresh needle sweep behind it.
