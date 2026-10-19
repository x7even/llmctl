#!/usr/bin/env python3
"""
llmstack context-depth benchmark

Answers the question concurrent_bench.py cannot: how does this stack behave at
*real* context depth, and how does depth interact with concurrency?

Why a separate tool. concurrent_bench.py is non-streaming, so its "decode tok/s"
is completion_tokens / total_wall -- prefill included. At a 256-token prompt that
is a rounding error; at 128K it is most of the wall clock, and the number stops
being a decode rate at all. This script streams, so time-to-first-token (prefill
plus queue) and the decode window are measured separately and neither
contaminates the other.

Two more things it does that matter at depth:

  * Every request gets a unique filler body, so prefix caching cannot serve a
    prefill that a real client would have had to pay for. Identical long prompts
    would report a cache hit rate, not a prefill cost. --shared-prefix opts into
    the other regime deliberately.
  * Output length is pinned with ignore_eos + min_tokens, so every cell decodes
    exactly the same number of tokens and cells are comparable. Without it a
    model that stops early at depth looks fast.

Usage:
  python3 bench/depth_bench.py --model qwen3.8-27b-code \
      --depths 1024,8192,32768,65536,131072 --concurrency 1 --gen 128 --no-thinking

  # the matrix that matters for an agent fleet
  python3 bench/depth_bench.py --model qwen3.8-27b-code \
      --depths 4096,16384,65536 --concurrency 1,4,8 --gen 128 --no-thinking \
      --save bench/results/depth-27b-$(date +%Y%m%d).json

Exit status is 0 unless a cell errored.
"""

import argparse
import json
import math
import os
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

# Prompts overshoot their requested depth by a few tokens (chat wrapper, tokeniser
# boundaries); 64 covers every overshoot measured so far.
DEPTH_MARGIN = 64

DEFAULT_URL = os.environ.get("LLMSTACK_URL", "http://127.0.0.1:8080/v1/chat/completions")

# A fixed, boring vocabulary. Common English words tokenise at close to one token
# each, which keeps the words-per-token ratio stable across depths; the calibration
# below removes whatever residual error is left.
VOCAB = (
    "the of and to in a is that it for on with as was at by an be this have from or "
    "one had not but what all were when we there can an your which their said if do "
    "will each about how up out them then she many some so these would other into has "
    "more her two like him see time could no make than first been its who now people "
    "my over know water only little work place year live me back give most very after "
    "thing our just name good sentence man think say great where help through much "
    "before line right too mean old any same tell boy follow came want show also around "
    "form three small set put end does another well large must big even such because "
    "turn here why ask went men read need land different home us move try kind hand "
    "picture again change off play spell air away animal house point page letter mother "
    "answer found study still learn should america world high every near add food between"
).split()

# Words of wrapper text around the filler body; subtracted when sizing a prompt.
WRAPPER_WORDS = 60


def filler(n_words, seed):
    """Deterministic, unique-per-seed filler text."""
    rng = random.Random(seed)
    return " ".join(rng.choice(VOCAB) for _ in range(n_words))


def seed_for(seed, run_nonce, depth, conc):
    """Base seed for one (depth, conc) cell.

    `conc` has to be in here. Without it, a cell's requests take seeds
    base+0..conc-1, so at one depth conc=1 draws base+0, conc=8 draws base+0..7
    and conc=32 draws base+0..31 -- every cell after the first re-sends prompts
    the engine has already cached. Measured on a 32K pass: the prefix-cache hit
    rate climbed from 0% to 30.5%, which flatters exactly the high-concurrency
    cells worth publishing.
    """
    return seed + depth * 1000 + conc * 1_000_003 + run_nonce * 7_000_001


def build_messages(depth_words, seed):
    body = filler(depth_words, seed)
    user = (
        "Below is a transcript fragment. Read it, then answer the question at the end.\n\n"
        "--- BEGIN FRAGMENT ---\n" + body + "\n--- END FRAGMENT ---\n\n"
        "Question: in one short paragraph, describe what kind of text the fragment is."
    )
    return [{"role": "user", "content": user}]


def one_request(url, model, messages, gen, timeout, no_thinking, headers):
    """Stream one completion. Returns a dict of timings, or {'error': ...}."""
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": gen,
        "min_tokens": gen,        # vLLM extra: forbid stopping early
        "ignore_eos": True,       # vLLM extra: decode exactly `gen` tokens
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if no_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    t_send = time.perf_counter()
    t_first = None
    t_last = None
    chunks = 0
    usage = None
    try:
        r = requests.post(url, json=payload, timeout=timeout, stream=True, headers=headers)
        if r.status_code != 200:
            return {"error": "HTTP %d: %s" % (r.status_code, r.text[:300])}
        for raw in r.iter_lines():
            if not raw or not raw.startswith(b"data: "):
                continue
            data = raw[6:]
            if data == b"[DONE]":
                break
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            if obj.get("usage"):
                usage = obj["usage"]
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if delta.get("content") or delta.get("reasoning_content"):
                now = time.perf_counter()
                if t_first is None:
                    t_first = now
                t_last = now
                chunks += 1
    except Exception as exc:                                   # noqa: BLE001
        return {"error": "%s: %s" % (type(exc).__name__, exc)}

    if t_first is None:
        return {"error": "no content tokens received"}

    comp = (usage or {}).get("completion_tokens") or 0
    prompt_toks = (usage or {}).get("prompt_tokens") or 0
    decode_window = max(t_last - t_first, 1e-9)
    # The first token comes out of prefill, not out of the decode loop it starts;
    # charging it to the decode window would inflate short runs.
    decode_toks = max(comp - 1, 0)
    return {
        "ttft_s": t_first - t_send,
        "decode_window_s": decode_window,
        "wall_s": t_last - t_send,
        "t_first": t_first,
        "t_last": t_last,
        "prompt_tokens": prompt_toks,
        "completion_tokens": comp,
        "decode_tokens": decode_toks,
        "chunks": chunks,
        "tok_s": decode_toks / decode_window,
        "steps_s": max(chunks - 1, 0) / decode_window,
        "accepted_per_step": decode_toks / max(chunks - 1, 1),
    }


def calibrate(url, model, timeout, no_thinking, headers, probe_words=4000):
    """Measure words-per-token for the filler, so --depths land where asked."""
    msgs = build_messages(probe_words, seed=0)
    res = one_request(url, model, msgs, gen=1, timeout=timeout,
                      no_thinking=no_thinking, headers=headers)
    if "error" in res or not res.get("prompt_tokens"):
        return None
    return (probe_words + WRAPPER_WORDS) / res["prompt_tokens"], res["prompt_tokens"]


def server_max_model_len(url, model, headers, timeout):
    """Ask the server what it will actually accept. None if it won't say."""
    models_url = url.split("/v1/")[0] + "/v1/models"
    try:
        data = requests.get(models_url, headers=headers, timeout=timeout).json()
    except Exception:
        return None
    for entry in data.get("data", []):
        if entry.get("id") == model:
            return entry.get("max_model_len")
    return None



def pct(sorted_vals, q):
    """Nearest-rank percentile, no interpolation.

    Deliberately not statistics.quantiles(): these samples are 1 to 32 requests
    wide, and interpolating between four observations reports precision the
    measurement does not have. Nearest-rank always returns a value that was
    actually observed.
    """
    if not sorted_vals:
        return None
    # floor(x + 0.5), not round(): Python's round() is banker's rounding, so
    # round(4.5) is 4 and the p50 of an even-length sample would silently pick the
    # lower-middle value. Round-half-up is the conventional nearest-rank rule and
    # does not depend on that surprise.
    i = int(math.floor(q * (len(sorted_vals) - 1) + 0.5))
    return sorted_vals[min(max(i, 0), len(sorted_vals) - 1)]


def dist(vals):
    """Full distribution of one measured quantity across a cell's streams.

    `percentiles_meaningful` is the honest caveat: below ~10 samples p10 and p90
    degenerate to min and max, so a reader can see when a tail figure is really
    just an extreme.
    """
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    return {
        "n": len(v),
        "mean": statistics.fmean(v),
        "stdev": statistics.stdev(v) if len(v) > 1 else 0.0,
        "min": v[0],
        "p10": pct(v, 0.10),
        "p50": pct(v, 0.50),
        "p90": pct(v, 0.90),
        "max": v[-1],
        "percentiles_meaningful": len(v) >= 10,
    }


class MetricsSampler:
    """Sample vLLM's own token counters while a cell runs.

    This exists to reconcile two numbers that look like they disagree and do not.
    The aggregate decode rate this script reports is a run average over the whole
    decode span, so at high concurrency it is diluted by the staggered ramp-in
    while most streams are still prefilling. A live panel instead shows
    delta(generation_tokens_total)/tick and keeps the running maximum, which is an
    instantaneous steady-state rate. Both are correct and they are not the same
    statistic; sampling here lets one run report both.

    Scrape the BACKEND port, not the router: llama-swap does not proxy /metrics.
    """

    def __init__(self, url, interval=1.0):
        self.url = url
        self.interval = interval
        self.samples = []
        self._stop = threading.Event()
        self._thread = None

    def _scrape(self):
        r = requests.get(self.url, timeout=5)
        r.raise_for_status()
        got = {}
        for line in r.text.split("\n"):
            for key in ("vllm:generation_tokens_total", "vllm:prompt_tokens_total",
                        "vllm:num_requests_running", "vllm:num_requests_waiting"):
                if line.startswith(key + "{"):
                    try:
                        got[key] = float(line.rsplit("}", 1)[1])
                    except (ValueError, IndexError):
                        pass
        return got

    def _loop(self):
        prev = None
        while not self._stop.is_set():
            t = time.monotonic()
            try:
                g = self._scrape()
            except Exception:
                self._stop.wait(self.interval)
                continue
            if prev is not None and t - prev[0] > 0.1:
                dt = t - prev[0]
                self.samples.append({
                    "dt": dt,
                    "gen_tok_s": (g.get("vllm:generation_tokens_total", 0.0)
                                  - prev[1].get("vllm:generation_tokens_total", 0.0)) / dt,
                    "prompt_tok_s": (g.get("vllm:prompt_tokens_total", 0.0)
                                     - prev[1].get("vllm:prompt_tokens_total", 0.0)) / dt,
                    "running": g.get("vllm:num_requests_running"),
                    "waiting": g.get("vllm:num_requests_waiting"),
                })
            prev = (t, g)
            self._stop.wait(max(0.0, self.interval - (time.monotonic() - t)))

    def start(self):
        self.samples = []
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval * 3)

    def summary(self):
        """Distributions of the instantaneous rates, saturated subset separated.

        The saturated subset is the samples taken while the server was within 10%
        of its high-water running-request count. Restricting to those removes the
        ramp-in and the drain, which is what makes the median a steady-state figure
        rather than an average over three different regimes.

        Returns None when nothing was sampled, so a caller stores an honest null
        rather than a distribution over an empty window.
        """
        if not self.samples:
            return None
        gen = [x["gen_tok_s"] for x in self.samples]
        runs = [x["running"] for x in self.samples if x["running"]]
        # Saturation is a HIGH-WATER band, not the modal running-count. The mode
        # is wrong in the one regime that matters most: when prompts are deep and
        # concurrency is high, the ramp-in is LONGER than the plateau, so the most
        # common running-count is a partially-filled server and a mode-based subset
        # would report the ramp as the steady state -- precisely backwards. Taking
        # everything within 10% of the high-water mark targets the plateau whether
        # it is long or short.
        hi = max(runs) if runs else None
        mode = statistics.mode(runs) if runs else None
        band = [x for x in self.samples
                if hi is not None and (x["running"] or 0) >= 0.9 * hi]
        # Zero-decode ticks are dropped from the DECODE distribution, and counted
        # separately. A tick inside the saturated band can still emit no tokens:
        # the requests are admitted and running, but the engine spent that whole
        # second on a prefill chunk. Leaving those in makes the floor and the p10
        # read 0.0 tok/s, which is not a slow decode -- it is a second that was not
        # decoding at all, and it would also disagree with
        # RingBuffer.ActiveStats() in tui/sparkline.go, which filters them. The
        # fraction is reported because it is the thing that explains the gap
        # between these percentiles and the run average: the run average pays for
        # those seconds and these percentiles do not.
        sat = [x["gen_tok_s"] for x in band if x["gen_tok_s"] > 0]
        nz = len(band) - len(sat)
        out = {
            "interval_s": self.interval,
            "n_samples": len(self.samples),
            "modal_running_requests": mode,
            "max_running_requests": hi,
            "saturation_threshold_requests": (0.9 * hi) if hi is not None else None,
            "max_waiting_requests": max((x["waiting"] or 0) for x in self.samples),
            "n_samples_in_band": len(band),
            "n_zero_decode_ticks_in_band": nz,
            "zero_decode_tick_fraction_in_band": (nz / len(band)) if band else None,
            "decode_tok_s_all": dist([x for x in gen if x > 0]),
            "decode_tok_s_saturated": dist(sat) if sat else None,
            "prefill_tok_s_nonzero": dist([x["prompt_tok_s"] for x in self.samples
                                           if x["prompt_tok_s"] > 0]),
            # The raw series, so every figure above can be re-derived later. Kept
            # because a bug in the subset rule was found AFTER a run and could not
            # be re-checked against the saved file -- only the summary had been
            # stored, so the run had to be repeated. ~50 rows per cell.
            "samples": [{"dt": round(x["dt"], 3),
                         "gen_tok_s": round(x["gen_tok_s"], 2),
                         "prompt_tok_s": round(x["prompt_tok_s"], 2),
                         "running": x["running"], "waiting": x["waiting"]}
                        for x in self.samples],
        }
        d = out["decode_tok_s_saturated"] or out["decode_tok_s_all"]
        if d and d["p50"] and d["p50"] > 0:
            # How much of a live panel's "peak" is just the maximum of a noisy
            # difference quotient rather than a higher true rate.
            out["peak_over_median"] = d["max"] / d["p50"]
        return out

def run_cell(url, model, depth_words, conc, gen, timeout, no_thinking, headers,
             shared_prefix, seed_base, prewarm=False,
             metrics_url=None, metrics_interval=1.0, requests=None):
    """Run requests at one depth through `conc` slots. Returns the aggregate row.

    `requests` defaults to `conc`, i.e. every stream starts at once and nothing
    arrives later -- the no-churn case. Setting it higher pushes that many
    requests through `conc` slots, so a new request enters whenever one
    finishes. That distinction is not cosmetic on this hardware: TRITON_ATTN's
    3D split-KV path is chosen per *batch*, and a step carrying a newcomer's
    prefill chunk drops every co-batched decoder to the 2D grid
    (docs/rdna4-long-context.md, gate 4). A no-churn cell therefore measures
    that kernel's best case. Measured on the 35B MoE at medium-256, where
    arrivals are constant, TRITON was 19% SLOWER at conc=8 than ROCM_ATTN while
    the no-churn depth grid had it 1.4-28x faster -- so quote the regime, not
    just the depth and width.
    """
    n_req = conc if requests is None else max(requests, conc)
    msgs = [
        build_messages(depth_words, seed=(seed_base if shared_prefix else seed_base + i))
        for i in range(n_req)
    ]

    # Without this, every stream in a deep cell pays a full unique prefill, and
    # chunked prefill interleaves those tokens into everyone else's decode steps.
    # The cell then measures prefill contention: at 65K x conc=4 the measured TTFT
    # was 181 s and two requests at conc=8 timed out outright. A real agent fleet
    # does not work that way -- its context grows a turn at a time and prefix
    # caching covers nearly all of it -- so prewarm populates the cache one stream
    # at a time, serially, and the measured pass then decodes from a cache hit.
    # The result is a steady-state decode rate, which is what scales (or does not)
    # with concurrency. It is not a cold-fleet figure; do not quote it as one.
    if prewarm:
        for m in msgs:
            one_request(url, model, m, 1, timeout, no_thinking, headers)

    # Sampling starts after any prewarm, so the series covers the measured pass
    # only and is not diluted by the serial cache-population requests.
    sampler = MetricsSampler(metrics_url, metrics_interval) if metrics_url else None
    if sampler:
        sampler.start()
    try:
        with ThreadPoolExecutor(max_workers=conc) as pool:
            futs = [
                pool.submit(one_request, url, model, m, gen, timeout, no_thinking,
                            headers)
                for m in msgs
            ]
            results = [f.result() for f in futs]
    finally:
        if sampler:
            sampler.stop()

    errors = [r["error"] for r in results if "error" in r]
    ok = [r for r in results if "error" not in r]
    if not ok:
        row = {"errors": errors, "ok": 0, "requested": n_req,
               "slots": conc}
        if sampler:
            # A cell that completed nothing is exactly when the live
            # series matters most: it distinguishes a server that was
            # grinding from one that produced nothing at all.
            row["live"] = sampler.summary()
        return row

    # Aggregate decode rate: every decode token the server produced for this cell,
    # divided by the window in which it was decoding. First-token to last-token
    # keeps prefill out of the denominator at both ends.
    agg_window = max(max(r["t_last"] for r in ok) - min(r["t_first"] for r in ok), 1e-9)
    agg_decode_toks = sum(r["decode_tokens"] for r in ok)

    ttfts = sorted(r["ttft_s"] for r in ok)
    per_stream = [r["tok_s"] for r in ok]

    row = {
        "ok": len(ok),
        "requested": n_req,
        "slots": conc,
        "errors": errors,
        "prompt_tokens": int(statistics.median(r["prompt_tokens"] for r in ok)),
        "completion_tokens": int(statistics.median(r["completion_tokens"] for r in ok)),
        "agg_decode_tok_s": agg_decode_toks / agg_window,
        "per_stream_tok_s_mean": statistics.fmean(per_stream),
        "per_stream_tok_s_min": min(per_stream),
        "ttft_s_mean": statistics.fmean(ttfts),
        "ttft_s_p90": pct(ttfts, 0.90),
        "e2e_s_max": max(r["wall_s"] for r in ok),
        # Full distributions. The scalars above are kept so older readers of these
        # files keep working, but these are the ones to quote: a mean decode rate
        # at conc=32 hides whether the slowest stream got a usable share.
        "dist": {
            "per_stream_tok_s": dist(per_stream),
            "ttft_s": dist(ttfts),
            "e2e_s": dist([r["wall_s"] for r in ok]),
            "decode_window_s": dist([r["decode_window_s"] for r in ok]),
            "accepted_per_step": dist([r["accepted_per_step"] for r in ok]),
        },
        # Raw vectors so any other percentile can be recomputed without re-running
        # a cell that can take a quarter of an hour.
        "samples": {
            "per_stream_tok_s": per_stream,
            "ttft_s": ttfts,
            "e2e_s": [r["wall_s"] for r in ok],
        },
        "accepted_per_step": statistics.fmean(r["accepted_per_step"] for r in ok),
        # Aggregate prefill throughput: all the prompt tokens in the batch, over the window
        # in which the batch's prefills actually finished -- which ends at the LAST TTFT, not
        # the mean one. Dividing a sum by a mean is not a rate: it silently rewards a
        # scheduler that front-loads a few streams, and inflates with concurrency even when
        # the batch took longer in total.
        "prefill_tok_s": (sum(r["prompt_tokens"] for r in ok)
                          / max(max(ttfts), 1e-9)),
        # Per-stream view of the same thing, for comparison against the serial cell.
        "prefill_tok_s_per_stream_mean": statistics.fmean(
            r["prompt_tokens"] / max(r["ttft_s"], 1e-9) for r in ok),
    }
    if sampler:
        # Instantaneous aggregate rates sampled from the server's own counters.
        # `decode_tok_s_saturated.p50` is the steady-state figure; `.max` is the
        # statistic a live panel calls "peak", and the two differ by ramp-in
        # dilution plus the upward bias of maximising a noisy difference quotient.
        row["live"] = sampler.summary()
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description="context-depth x concurrency benchmark")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--model", required=True)
    ap.add_argument("--depths", default="1024,8192,32768,65536,131072",
                    help="target prompt_tokens per request, comma separated")
    ap.add_argument("--concurrency", default="1",
                    help="comma separated concurrency levels")
    ap.add_argument("--requests", type=int, default=None,
                    help="total requests per cell, pushed through --concurrency "
                         "slots, so a new one arrives whenever one finishes. "
                         "Default: equal to the concurrency level, i.e. all "
                         "streams start together and nothing arrives later. Raise "
                         "it to measure the churn regime a real agent fleet runs "
                         "in -- arrivals inject prefill chunks into other "
                         "streams' decode steps, which closes TRITON_ATTN's 3D "
                         "split-KV path for that step (see run_cell)")
    ap.add_argument("--prewarm", action="store_true",
                    help="populate the prefix cache serially before each cell, so it "
                         "measures steady-state decode instead of prefill contention")
    ap.add_argument("--max-model-len", type=int, default=None,
                    help="context window to clamp depths against. Needed when going "
                         "through llama-swap, whose /v1/models does not report it.")
    ap.add_argument("--gen", type=int, default=128,
                    help="tokens to decode per request (pinned with ignore_eos)")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--no-thinking", action="store_true",
                    help="suppress <think> blocks; use for every comparable number")
    ap.add_argument("--shared-prefix", action="store_true",
                    help="send the SAME long prompt to every stream in a cell "
                         "(measures the prefix-cache-hit regime instead)")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--run-nonce", type=int, default=0,
                    help="shifts every prompt so a re-run against a server that "
                         "is already live is COLD again. Prompts are a pure "
                         "function of the seed, so without a fresh nonce a "
                         "second run re-sends text the engine still has cached "
                         "and the cells read far faster than they are. Measured: "
                         "a 32K cell re-run warm reported 41,463 prompt tok/s "
                         "against a true rate near 4,300.")
    ap.add_argument("--metrics-url",
                    help="vLLM /metrics on the BACKEND port (llama-swap does "
                         "not proxy it), e.g. http://127.0.0.1:9104/metrics. "
                         "Samples instantaneous aggregate throughput during "
                         "each cell and reports its distribution, which is "
                         "what a live panel shows; the row's agg_decode_tok_s "
                         "is a run average over the whole decode span and "
                         "reads lower by design.")
    ap.add_argument("--metrics-interval", type=float, default=1.0,
                    help="sampling interval in seconds (default 1.0, matching "
                         "llmpanel's default poll)")
    ap.add_argument("--save", help="write results JSON here")
    ap.add_argument("--label", default="", help="free-text tag stored in the JSON")
    args = ap.parse_args(argv)

    headers = {"Content-Type": "application/json"}
    depths = [int(x) for x in args.depths.split(",") if x.strip()]
    concs = [int(x) for x in args.concurrency.split(",") if x.strip()]

    print("model      : %s" % args.model)
    print("url        : %s" % args.url)
    print("depths     : %s" % depths)
    print("concurrency: %s" % concs)
    print("requests   : %s" % ("%d per cell (CHURN: arrivals mid-run)"
                               % args.requests if args.requests
                               else "= concurrency (no churn)"))
    print("gen        : %d tokens/request (ignore_eos)" % args.gen)
    print("prompts    : %s%s" % ("SHARED (prefix-cache regime)" if args.shared_prefix
                                 else "unique per request",
                                 ", PREWARMED (steady-state decode)" if args.prewarm
                                 else ""))
    print()

    print("calibrating words-per-token ...", end=" ", flush=True)
    cal = calibrate(args.url, args.model, args.timeout, args.no_thinking, headers)
    if cal is None:
        print("FAILED - is the model loaded?")
        return 2
    wpt, probe_toks = cal
    print("%.3f words/token (4000-word probe = %d prompt tokens)" % (wpt, probe_toks))

    # The server rejects prompt + gen > max_model_len, so a depth equal to the
    # context window can never be measured: the output has to fit too. Clamp
    # rather than let the last row come back as an HTTP 400, and say so, because
    # a silently-moved depth is worse than a missing one.
    mml = args.max_model_len or server_max_model_len(args.url, args.model,
                                                     headers, args.timeout)
    if mml:
        cap = mml - args.gen - DEPTH_MARGIN
        clamped = [min(d, cap) for d in depths]
        if clamped != depths:
            print("clamping to max_model_len %d - gen %d - %d margin = %d:  %s -> %s"
                  % (mml, args.gen, DEPTH_MARGIN, cap, depths, clamped))
        depths = sorted(set(clamped))
    else:
        print("warning: max_model_len unknown (llama-swap does not report it); "
              "depths unclamped -- pass --max-model-len to enable the clamp")
    print()

    rows = []
    # "agg t/s mix" is whole-cell tokens over the window from the first stream's
    # first token to the last stream's last token. At conc>1 that window contains
    # other streams' prefill, so it is mixed-phase cell throughput, NOT a decode
    # rate. "decode/str" is the per-stream decode rate and is the clean one.
    hdr = ("%11s %10s %5s %11s %10s %8s %9s %8s %8s"
           % ("depth(req)", "depth(act)", "conc", "agg t/s mix", "decode/str",
              "TTFT s", "TTFT p90", "e2e s", "acc/step"))
    print(hdr)
    print("-" * len(hdr))

    failed = False
    for depth in depths:
        depth_words = max(int(depth * wpt) - WRAPPER_WORDS, 16)
        for conc in concs:
            row = run_cell(args.url, args.model, depth_words, conc, args.gen,
                           args.timeout, args.no_thinking, headers,
                           args.shared_prefix,
                           seed_for(args.seed, args.run_nonce, depth, conc),
                           prewarm=args.prewarm,
                           metrics_url=args.metrics_url,
                           metrics_interval=args.metrics_interval,
                           requests=args.requests)
            row["depth_requested"] = depth
            row["concurrency"] = conc
            rows.append(row)
            if not row.get("ok"):
                failed = True
                print("%11d %10s %5d   ERROR: %s" % (depth, "-", conc, row["errors"][:1]))
                continue
            if row["errors"]:
                failed = True
            print("%11d %10d %5d %11.1f %10.1f %8.2f %9.2f %8.1f %8.2f%s"
                  % (depth, row["prompt_tokens"], conc, row["agg_decode_tok_s"],
                     row["per_stream_tok_s_mean"], row["ttft_s_mean"], row["ttft_s_p90"],
                     row["e2e_s_max"], row["accepted_per_step"],
                     ("  [%d failed]" % len(row["errors"])) if row["errors"] else ""))

    if args.save:
        out = {
            "model": args.model,
            "url": args.url,
            "label": args.label,
            "gen": args.gen,
            "no_thinking": args.no_thinking,
            # Which regime ran. --prewarm populates the prefix cache serially
            # first, so the cells measure steady-state decode; without it each
            # stream pays a full unique prefill and the cells measure the
            # mixed prefill+decode cost a real client actually pays. Both are
            # real and they differ by more than an order of magnitude in deep
            # cells, so a saved number that does not say which one ran cannot
            # be compared against anything.
            "prewarm": args.prewarm,
            "shared_prefix": args.shared_prefix,
            "requests_per_cell": args.requests,
            # Recorded so a saved file can be checked for freshness later.
            # Prompts are a pure function of these two, so two runs sharing
            # them re-send text the engine may still have cached: the second
            # run's prefill rate reads far above the hardware's real one.
            "seed": args.seed,
            "run_nonce": args.run_nonce,
            "words_per_token": wpt,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "rows": rows,
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.save)), exist_ok=True)
        with open(args.save, "w") as fh:
            json.dump(out, fh, indent=2)
        print("\nsaved: %s" % args.save)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
