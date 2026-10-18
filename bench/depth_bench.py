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
import os
import random
import statistics
import sys
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


def run_cell(url, model, depth_words, conc, gen, timeout, no_thinking, headers,
             shared_prefix, seed_base, prewarm=False):
    """Run `conc` concurrent requests at one depth. Returns the aggregate row."""
    msgs = [
        build_messages(depth_words, seed=(seed_base if shared_prefix else seed_base + i))
        for i in range(conc)
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

    with ThreadPoolExecutor(max_workers=conc) as pool:
        futs = [
            pool.submit(one_request, url, model, m, gen, timeout, no_thinking, headers)
            for m in msgs
        ]
        results = [f.result() for f in futs]

    errors = [r["error"] for r in results if "error" in r]
    ok = [r for r in results if "error" not in r]
    if not ok:
        return {"errors": errors, "ok": 0, "requested": conc}

    # Aggregate decode rate: every decode token the server produced for this cell,
    # divided by the window in which it was decoding. First-token to last-token
    # keeps prefill out of the denominator at both ends.
    agg_window = max(max(r["t_last"] for r in ok) - min(r["t_first"] for r in ok), 1e-9)
    agg_decode_toks = sum(r["decode_tokens"] for r in ok)

    ttfts = sorted(r["ttft_s"] for r in ok)
    per_stream = [r["tok_s"] for r in ok]

    return {
        "ok": len(ok),
        "requested": conc,
        "errors": errors,
        "prompt_tokens": int(statistics.median(r["prompt_tokens"] for r in ok)),
        "completion_tokens": int(statistics.median(r["completion_tokens"] for r in ok)),
        "agg_decode_tok_s": agg_decode_toks / agg_window,
        "per_stream_tok_s_mean": statistics.fmean(per_stream),
        "per_stream_tok_s_min": min(per_stream),
        "ttft_s_mean": statistics.fmean(ttfts),
        "ttft_s_p90": ttfts[min(len(ttfts) - 1, int(0.9 * len(ttfts)))],
        "e2e_s_max": max(r["wall_s"] for r in ok),
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


def main(argv=None):
    ap = argparse.ArgumentParser(description="context-depth x concurrency benchmark")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--model", required=True)
    ap.add_argument("--depths", default="1024,8192,32768,65536,131072",
                    help="target prompt_tokens per request, comma separated")
    ap.add_argument("--concurrency", default="1",
                    help="comma separated concurrency levels")
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
                           args.shared_prefix, args.seed + depth * 1000,
                           prewarm=args.prewarm)
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
