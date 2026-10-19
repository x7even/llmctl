# Complete benchmark results: prefill, decode and concurrency

Every measured cell. Output pinned at 1,024 tokens with `ignore_eos`, so
the latency columns compare speeds and not answer lengths. 4x R9700
(gfx1201), vLLM 0.26.0 except Flash-Next (nightly).

## How to read the three throughput columns

They measure different things and are not interchangeable:

- **prefill (batch)** -- the batch's prompt tokens divided by the slowest
  stream's TTFT. A whole-batch rate, not a per-stream speed. Blank for
  prewarmed rows, where the prompt is served from the prefix cache and the
  figure would measure cache reuse rather than compute.
- **decode/stream** -- what one client sees: mean per-stream decode rate.
- **decode agg** -- all streams summed, averaged over the whole decode span
  (first stream's first token to last stream's last token). At high
  concurrency that span includes the staggered ramp-in while most streams
  are still prefilling, so this reads **below** the steady-state rate a live
  sampler such as `llmpanel` reports. Neither is wrong; they answer
  different questions -- this one answers "how long will the batch take".

`ok` is completed/requested. A cell below full completion keeps its figures
only where a majority finished; the loss cause is in the saved JSON.

## `gemma4-26b-a4b`

### cold

| depth | prompt tok | conc | ok | TTFT mean s | TTFT p90 s | prefill (batch) tok/s | decode/stream tok/s | decode agg tok/s | acc/step |
|---|---|---|---|---|---|---|---|---|---|
| 4096 | 4096 | 1 | 1/1 | 0.5 | 0.5 | 7947 | 53.9 | **53.9** | 1.00 |
| 4096 | 4096 | 8 | 8/8 | 4.4 | 4.9 | 6629 | 36.6 | **256.7** | 1.00 |
| 4096 | 4096 | 32 | 32/32 | 9.8 | 16.0 | 8177 | 20.3 | **544.0** | 1.00 |
| 16384 | 16384 | 1 | 1/1 | 3.9 | 3.9 | 4203 | 43.3 | **43.3** | 1.00 |
| 16384 | 16384 | 8 | 8/8 | 18.8 | 30.8 | 4255 | 22.8 | **133.5** | 1.00 |
| 65536 | 65536 | 1 | 1/1 | 45.8 | 45.8 | 1430 | 33.0 | **33.0** | 1.00 |
| 65536 | 65536 | 4 | 4/4 | 113.9 | 182.1 | 1440 | 13.4 | **23.5** | 1.00 |

## `qwen3.6-27b-code`

### cold

| depth | prompt tok | conc | ok | TTFT mean s | TTFT p90 s | prefill (batch) tok/s | decode/stream tok/s | decode agg tok/s | acc/step |
|---|---|---|---|---|---|---|---|---|---|
| 2048 | 2047 | 32 | 32/32 | 10.8 | 14.8 | 4087 | 27.8 | **642.3** | 2.76 |
| 4096 | 4096 | 1 | 1/1 | 0.9 | 0.9 | 4473 | 61.1 | **61.1** | 2.56 |
| 4096 | 4096 | 8 | 8/8 | 7.0 | 8.9 | 3683 | 45.7 | **304.2** | 2.74 |
| 4096 | 4096 | 32 | 32/32 | 25.5 | 45.6 | 2779 | 17.5 | **368.9** | 2.75 |
| 16384 | 16387 | 1 | 1/1 | 4.0 | 4.0 | 4112 | 34.7 | **34.7** | 2.81 |
| 16384 | 16387 | 8 | 8/8 | 54.9 | 92.4 | 1419 | 16.6 | **64.5** | 2.69 |
| 16384 | 16387 | 16 | 16/16 | 147.6 | 294.4 | 880 | 7.4 | **46.8** | 2.73 |
| 16384 | 16387 | 32 | **29/32** ! | 397.4 | 1006.0 | 416 | 1.5 | **22.5** | 2.75 |
| 65536 | 65551 | 1 | 1/1 | 28.4 | 28.4 | 2307 | 12.0 | **12.0** | 2.90 |
| 65536 | 65551 | 4 | 4/4 | 202.3 | 367.7 | 713 | 5.4 | **9.4** | 2.72 |

### prewarmed

| depth | prompt tok | conc | ok | TTFT mean s | TTFT p90 s | prefill (batch) tok/s | decode/stream tok/s | decode agg tok/s | acc/step |
|---|---|---|---|---|---|---|---|---|---|
| 16384 | 16387 | 1 | 1/1 | 0.5 | 0.5 | cached | 34.7 | **34.7** | 2.81 |
| 16384 | 16387 | 8 | 8/8 | 3.2 | 3.6 | cached | 26.1 | **168.0** | 2.71 |
| 65536 | 65551 | 1 | 1/1 | 1.2 | 1.2 | cached | 12.0 | **12.0** | 2.90 |
| 65536 | 65551 | 4 | 4/4 | 4.8 | 5.9 | cached | 10.5 | **37.0** | 2.70 |

## `qwen3.6-35b-code`

### cold

| depth | prompt tok | conc | ok | TTFT mean s | TTFT p90 s | prefill (batch) tok/s | decode/stream tok/s | decode agg tok/s | acc/step |
|---|---|---|---|---|---|---|---|---|---|
| 2048 | 2047 | 8 | 8/8 | 1.1 | 1.2 | 13198 | 51.1 | **359.6** | 2.54 |
| 2048 | 2047 | 16 | 16/16 | 2.2 | 2.3 | 13935 | 50.9 | **673.3** | 2.54 |
| 2048 | 2047 | 32 | 32/32 | 4.4 | 4.5 | 13474 | 40.0 | **977.0** | 2.62 |
| 4096 | 4096 | 1 | 1/1 | 0.4 | 0.4 | 11377 | 53.8 | **53.8** | 2.53 |
| 4096 | 4096 | 8 | 8/8 | 2.6 | 3.0 | 11097 | 50.7 | **327.0** | 2.55 |
| 4096 | 4096 | 32 | 32/32 | 8.7 | 12.9 | 9724 | 30.5 | **726.5** | 2.64 |
| 16384 | 16387 | 1 | 1/1 | 1.4 | 1.4 | 11944 | 32.5 | **32.5** | 2.40 |
| 16384 | 16387 | 8 | 8/8 | 15.6 | 23.3 | 5620 | 29.7 | **155.5** | 2.52 |
| 65536 | 65551 | 1 | 1/1 | 9.7 | 9.7 | 6790 | 13.2 | **13.2** | 2.89 |
| 65536 | 65551 | 4 | 4/4 | 93.5 | 150.3 | 1745 | 9.8 | **19.8** | 2.71 |

## `qwen3.8-27b-code`

### cold

| depth | prompt tok | conc | ok | TTFT mean s | TTFT p90 s | prefill (batch) tok/s | decode/stream tok/s | decode agg tok/s | acc/step |
|---|---|---|---|---|---|---|---|---|---|
| 4096 | 4096 | 1 | 1/1 | 0.9 | 0.9 | 4482 | 62.7 | **62.7** | 2.64 |
| 4096 | 4096 | 8 | 8/8 | 7.0 | 8.7 | 3756 | 45.5 | **323.9** | 2.70 |
| 4096 | 4096 | 32 | 32/32 | 25.5 | 44.8 | 2922 | 18.0 | **369.6** | 2.71 |
| 16384 | 16387 | 1 | 1/1 | 4.0 | 4.0 | 4110 | 34.9 | **34.9** | 2.83 |
| 16384 | 16387 | 8 | 8/8 | 55.0 | 92.4 | 1418 | 16.4 | **66.3** | 2.74 |
| 16384 | 16387 | 16 | 16/16 | 147.2 | 294.0 | 881 | 7.2 | **46.9** | 2.63 |
| 16384 | 16387 | 32 | **29/32** ! | 397.4 | 1006.2 | 416 | 1.5 | **22.5** | 2.67 |
| 65536 | 65551 | 1 | 1/1 | 28.4 | 28.4 | 2310 | 11.6 | **11.6** | 2.79 |
| 65536 | 65551 | 4 | 4/4 | 202.5 | 368.0 | 713 | 5.4 | **9.6** | 2.81 |
| 129984 | 130015 | 1 | 1/1 | 90.4 | 90.4 | 1438 | 5.5 | **5.5** | 2.62 |

### prewarmed

| depth | prompt tok | conc | ok | TTFT mean s | TTFT p90 s | prefill (batch) tok/s | decode/stream tok/s | decode agg tok/s | acc/step |
|---|---|---|---|---|---|---|---|---|---|
| 16384 | 16387 | 1 | 1/1 | 0.5 | 0.5 | cached | 34.9 | **34.9** | 2.83 |
| 16384 | 16387 | 8 | 8/8 | 3.2 | 3.6 | cached | 26.3 | **178.8** | 2.71 |
| 65536 | 65551 | 1 | 1/1 | 1.2 | 1.2 | cached | 11.8 | **11.8** | 2.83 |
| 65536 | 65551 | 4 | 4/4 | 4.8 | 5.9 | cached | 10.8 | **40.6** | 2.78 |

## `qwen3.8-27b-think`

### cold

| depth | prompt tok | conc | ok | TTFT mean s | TTFT p90 s | prefill (batch) tok/s | decode/stream tok/s | decode agg tok/s | acc/step |
|---|---|---|---|---|---|---|---|---|---|
| 4096 | 4096 | 1 | 1/1 | 0.9 | 0.9 | 4504 | 46.9 | **46.9** | 1.00 |
| 4096 | 4096 | 8 | 8/8 | 6.4 | 7.2 | 4560 | 35.4 | **237.1** | 1.00 |
| 4096 | 4096 | 32 | 32/32 | 22.7 | 28.8 | 4554 | 22.3 | **476.9** | 1.00 |
| 16384 | 16387 | 1 | 1/1 | 4.1 | 4.1 | 3965 | 45.0 | **45.0** | 1.00 |
| 16384 | 16387 | 8 | 8/8 | 25.1 | 33.2 | 3945 | 27.4 | **136.1** | 1.00 |
| 16384 | 16387 | 16 | 16/16 | 45.0 | 66.6 | 3937 | 18.8 | **162.1** | 1.00 |
| 16384 | 16387 | 32 | 32/32 | 79.7 | 133.0 | 3931 | 11.3 | **180.9** | 1.00 |
| 65536 | 65551 | 1 | 1/1 | 25.4 | 25.4 | 2584 | 39.0 | **39.0** | 1.00 |
| 65536 | 65551 | 4 | 4/4 | 81.1 | 101.3 | 2590 | 23.3 | **49.3** | 1.00 |
| 129984 | 130015 | 1 | 1/1 | 73.7 | 73.7 | 1763 | 33.1 | **33.1** | 1.00 |

### prewarmed

| depth | prompt tok | conc | ok | TTFT mean s | TTFT p90 s | prefill (batch) tok/s | decode/stream tok/s | decode agg tok/s | acc/step |
|---|---|---|---|---|---|---|---|---|---|
| 16384 | 16387 | 1 | 1/1 | 0.3 | 0.3 | cached | 44.9 | **44.9** | 1.00 |
| 16384 | 16387 | 8 | 8/8 | 1.6 | 1.7 | cached | 32.8 | **251.9** | 1.00 |
| 65536 | 65551 | 1 | 1/1 | 0.4 | 0.4 | cached | 39.0 | **39.0** | 1.00 |
| 65536 | 65551 | 4 | 4/4 | 1.1 | 1.3 | cached | 32.5 | **127.1** | 1.00 |

## `qwen3.8-flash-next-vllm`

### cold

| depth | prompt tok | conc | ok | TTFT mean s | TTFT p90 s | prefill (batch) tok/s | decode/stream tok/s | decode agg tok/s | acc/step |
|---|---|---|---|---|---|---|---|---|---|
| 4096 | 4096 | 1 | 1/1 | 1.5 | 1.5 | 2688 | 56.4 | **56.4** | 1.00 |
| 4096 | 4096 | 8 | 8/8 | 11.6 | 14.8 | 2218 | 22.4 | **145.9** | 1.00 |
| 4096 | 4096 | 32 | 32/32 | 28.2 | 47.6 | 2745 | 12.6 | **297.2** | 1.00 |
| 16384 | 16387 | 1 | 1/1 | 6.2 | 6.2 | 2652 | 55.6 | **55.6** | 1.00 |
| 16384 | 16387 | 8 | 8/8 | 30.7 | 48.0 | 2732 | 17.9 | **99.8** | 1.00 |
| 16384 | 16387 | 16 | 16/16 | 54.9 | 94.7 | 2720 | 10.6 | **108.7** | 1.00 |
| 65536 | 65551 | 1 | 1/1 | 24.5 | 24.5 | 2673 | 55.3 | **55.3** | 1.00 |
| 65536 | 65551 | 4 | 4/4 | 64.9 | 98.7 | 2658 | 13.7 | **34.4** | 1.00 |
| 131072 | 131103 | 1 | 1/1 | 49.8 | 49.8 | 2633 | 56.4 | **56.4** | 1.00 |
| 249856 | 249916 | 1 | 1/1 | 98.8 | 98.8 | 2528 | 55.5 | **55.5** | 1.00 |

### prewarmed

| depth | prompt tok | conc | ok | TTFT mean s | TTFT p90 s | prefill (batch) tok/s | decode/stream tok/s | decode agg tok/s | acc/step |
|---|---|---|---|---|---|---|---|---|---|
| 16384 | 16387 | 1 | 1/1 | 0.3 | 0.3 | cached | 56.9 | **56.9** | 1.00 |
| 16384 | 16387 | 8 | 8/8 | 2.0 | 2.2 | cached | 24.2 | **186.1** | 1.00 |
| 65536 | 65551 | 1 | 1/1 | 0.3 | 0.3 | cached | 56.7 | **56.7** | 1.00 |
| 65536 | 65551 | 4 | 4/4 | 0.8 | 1.0 | cached | 21.6 | **85.6** | 1.00 |

## Steady-state decode distributions

Cells run with the in-benchmark sampler attached to vLLM's
`/metrics`. The percentiles are over the one-second samples taken
while the server was within 10% of its high-water running-request
count -- i.e. the plateau, with ramp-in and drain excluded. Ticks
that emitted no tokens at all are excluded and counted separately:
the requests were admitted and running, but the engine spent that
whole second on a prefill chunk.

Read **median** as what the hardware sustains, **p10** as the floor
a slow second hits, and **run avg** as how long a batch of this
shape takes. The **low** is a sampling-boundary artifact -- a tick
can straddle a transition and catch a single token -- so quote the
p10, not the low. Convention: nearest-rank, round-half-up, no
interpolation, matching `RingBuffer.ActiveStats` in the TUI.

| profile | depth | conc | run avg | low | p10 | median | p90 | peak | peak/med | med/run avg | n | zero-decode ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3.6-27b-code` | 2048 | 32 | 642.3 | 16.0 | 873.9 | **1007.9** | 1075.9 | 1104.9 | 1.10 | 1.57 | 34 | 6/40 |
| `qwen3.6-35b-code` | 2048 | 8 | 359.6 | 4.0 | 339.0 | **406.0** | 457.0 | 480.0 | 1.18 | 1.13 | 19 | 0/19 |
| `qwen3.6-35b-code` | 2048 | 16 | 673.3 | 1.0 | 486.0 | **774.9** | 900.9 | 922.9 | 1.19 | 1.15 | 20 | 0/20 |
| `qwen3.6-35b-code` | 2048 | 32 | 977.0 | 1.0 | 1137.9 | **1275.9** | 1376.9 | 1404.9 | 1.10 | 1.31 | 26 | 2/28 |

`!` on the sample count means fewer than 10 samples, where "p10"
and "p90" are just the minimum and the maximum.

Where **p10 exceeds the run average** -- both conc=32 rows -- that
is not an inconsistency. The p10 is over plateau samples only; the
run average also pays for the ramp, which is where the slow seconds
are. That difference is the `med/run avg` column, and it is a
property of the shape rather than of the hardware: it is 1.31x on
the 35B at 32 streams and 1.57x on the 27B at the same shape.

