#!/usr/bin/env python3
"""
llmstack concurrent benchmark
Measures: prefill throughput, decode throughput, TTFT, latency under concurrency.

Usage:
  python3 bench/concurrent_bench.py                              # defaults
  python3 bench/concurrent_bench.py --model qwen3-coder-30b-fp8
  python3 bench/concurrent_bench.py --sweep 2,4,8,12,16 --requests-per-level 16
  python3 bench/concurrent_bench.py --quick                      # fast smoke bench
  python3 bench/concurrent_bench.py --no-thinking                # disable Qwen3 thinking mode
  llmctl bench qwen3-coder-30b-fp8

Output: human-readable table + optional CSV (--csv results.csv)
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

# ── Default configuration ─────────────────────────────────────────────────────

DEFAULT_URL   = "http://127.0.0.1:8080/v1/chat/completions"
DEFAULT_MODEL = "qwen3-coder-30b-fp8"

# Prompts of different lengths to exercise prefill (short = decode-bound,
# long = prefill-bound). Each tuple: (label, prompt, expected_completion_tokens)
PROMPT_SUITE = [
    (
        "short-64",
        "You are running on a homelab AI rig with 4x AMD Radeon AI PRO R9700 GPUs "
        "(gfx1201, 32 GB each). Write 2 sentences about why local AI matters.",
        64,
    ),
    (
        "medium-256",
        "You are a senior software engineer reviewing a critical production service. "
        "Describe, in 4–6 sentences, the key checks you would perform before approving "
        "a pull request that touches database migrations, authentication middleware, "
        "and cache invalidation logic simultaneously. Be concrete and technical.",
        256,
    ),
    (
        "long-512",
        "Write a detailed technical specification (10–12 sentences) for a RESTful API "
        "endpoint that accepts a JSON payload containing: a user_id (UUID), an action "
        "(enum: read/write/delete), a resource_path (string), optional metadata (dict), "
        "and a timestamp (ISO 8601). Cover: request validation, auth model, rate limiting, "
        "idempotency, error codes, response schema, and observability requirements. "
        "Be precise — this will be handed to an implementation team.",
        512,
    ),
    (
        "xlarge-2048",
        "You are a principal engineer writing an architectural design document for a new "
        "distributed key-value store. Write a comprehensive design covering: (1) data model "
        "and storage layout, (2) consistent hashing and partition strategy across nodes, "
        "(3) replication factor and quorum reads/writes, (4) failure detection and leader "
        "election using Raft or Paxos, (5) client-side routing and retry logic, (6) "
        "compaction and garbage collection strategy, (7) monitoring and observability hooks, "
        "(8) security model including encryption at rest and in transit, (9) operational "
        "runbooks for common failure modes such as node loss, network partition, and "
        "clock skew. Be detailed and precise — this document will be reviewed by a team "
        "of senior engineers before implementation begins. Include trade-off analysis for "
        "key design decisions and explain why you chose consistency over availability or "
        "vice versa for each subsystem.",
        2048,
    ),
]

PROMPT_CHOICES = [p[0] for p in PROMPT_SUITE] + ["all"]


# ── Core request function ─────────────────────────────────────────────────────

def do_request(session: requests.Session, url: str, model: str,
               prompt: str, max_tokens: int, no_thinking: bool = False) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise, technical assistant."},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.6,
        "top_p": 0.95,
    }
    if no_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    t0 = time.perf_counter()
    resp = session.post(url, json=payload, timeout=600)
    ttft = time.perf_counter() - t0   # time-to-first-token for non-streaming
    resp.raise_for_status()
    data = resp.json()
    t1 = time.perf_counter()

    usage = data.get("usage", {})
    return {
        "wall_s":            t1 - t0,
        "ttft_s":            ttft,
        "prompt_tokens":     usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens":      usage.get("total_tokens", 0),
    }


# ── Warm-up ────────────────────────────────────────────────────────────────────

def warmup(url: str, model: str, no_thinking: bool = False) -> None:
    session = requests.Session()
    print(f"  Warming up '{model}' (first request may trigger model load)...", flush=True)
    t0 = time.time()
    try:
        r = do_request(session, url, model,
                       "Say: ready", max_tokens=5, no_thinking=no_thinking)
        print(f"  Warm-up done in {time.time()-t0:.1f}s  "
              f"(prompt={r['prompt_tokens']} tokens)")
    except Exception as e:
        print(f"  Warm-up FAILED: {e}")
        print("  Make sure llmctl up && llmctl swap <model> before running bench.")
        sys.exit(1)


# ── Single-stream baseline ────────────────────────────────────────────────────

def run_serial(url, model, prompt_label, prompt, max_tokens, n_requests, no_thinking=False):
    session = requests.Session()
    results = []
    print(f"  Serial baseline — {n_requests} requests", flush=True)
    for i in range(n_requests):
        try:
            r = do_request(session, url, model, prompt, max_tokens, no_thinking=no_thinking)
            results.append(r)
            sys.stdout.write(f"\r    {i+1}/{n_requests}")
            sys.stdout.flush()
        except Exception as e:
            print(f"\n    request {i+1} error: {e}")
    print()
    return results


# ── Concurrent sweep ──────────────────────────────────────────────────────────

def run_concurrent(url, model, prompt, max_tokens, concurrency, total_requests, no_thinking=False):
    results = []
    errors  = 0
    t_start = time.perf_counter()

    def worker(_):
        s = requests.Session()
        try:
            return do_request(s, url, model, prompt, max_tokens, no_thinking=no_thinking)
        except Exception as e:
            return {"error": str(e)}

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker, i) for i in range(total_requests)]
        done = 0
        for f in as_completed(futures):
            r = f.result()
            if "error" in r:
                errors += 1
            else:
                results.append(r)
            done += 1
            sys.stdout.write(f"\r    {done}/{total_requests}  errors={errors}")
            sys.stdout.flush()

    print()
    wall = time.perf_counter() - t_start
    return results, errors, wall


# ── Stats helpers ─────────────────────────────────────────────────────────────

def stats(values):
    if not values:
        return {}
    s = sorted(values)
    return {
        "mean":   statistics.mean(s),
        "median": statistics.median(s),
        "p90":    s[int(len(s) * 0.90)],
        "p99":    s[min(int(len(s) * 0.99), len(s)-1)],
        "min":    s[0],
        "max":    s[-1],
    }


def print_stats_row(label, values, unit="s", scale=1.0):
    if not values:
        print(f"  {label:<28}  (no data)")
        return
    s = stats(values)
    print(
        f"  {label:<28}  "
        f"mean={s['mean']*scale:.3f}{unit}  "
        f"p50={s['median']*scale:.3f}{unit}  "
        f"p90={s['p90']*scale:.3f}{unit}  "
        f"p99={s['p99']*scale:.3f}{unit}  "
        f"[{s['min']*scale:.3f}–{s['max']*scale:.3f}]"
    )


# ── Report ─────────────────────────────────────────────────────────────────────

def report_suite(label, results, errors, wall_s, concurrency):
    print(f"\n  ── {label} ─────────────────────────────────────────────")
    if not results:
        print("  No successful results.")
        return {}

    prompt_toks  = [r["prompt_tokens"]     for r in results]
    comp_toks    = [r["completion_tokens"]  for r in results]
    wall_times   = [r["wall_s"]            for r in results]

    total_prompt_toks = sum(prompt_toks)
    total_comp_toks   = sum(comp_toks)
    req_per_sec       = len(results) / wall_s if wall_s > 0 else 0
    prefill_tps       = total_prompt_toks / wall_s if wall_s > 0 else 0
    decode_tps        = total_comp_toks   / wall_s if wall_s > 0 else 0

    print(f"  Requests:  {len(results)} ok / {errors} err  in {wall_s:.1f}s  "
          f"(concurrency={concurrency})")
    print(f"  Throughput:")
    print(f"    req/s          = {req_per_sec:.2f}")
    print(f"    prefill tok/s  = {prefill_tps:.1f}   "
          f"(total prompt tokens {total_prompt_toks})")
    print(f"    decode  tok/s  = {decode_tps:.1f}   "
          f"(total completion tokens {total_comp_toks})")
    print(f"  Per-request latency:")
    print_stats_row("wall time",  wall_times)
    print_stats_row("completion tokens", comp_toks, unit="", scale=1.0)

    return {
        "label":        label,
        "concurrency":  concurrency,
        "n_requests":   len(results),
        "errors":       errors,
        "wall_s":       wall_s,
        "req_per_s":    req_per_sec,
        "prefill_tps":  prefill_tps,
        "decode_tps":   decode_tps,
        "latency_mean": statistics.mean(wall_times),
        "latency_p90":  stats(wall_times)["p90"],
        "latency_p99":  stats(wall_times)["p99"],
    }


# ── Summary table ─────────────────────────────────────────────────────────────

def print_summary(rows, model):
    if len(rows) < 2:
        return
    print(f"\n{'═'*72}")
    print(f"  SUMMARY  (model: {model})")
    print(f"{'═'*72}")
    print(f"  {'Label':<38}  {'req/s':>6}  {'prefill t/s':>11}  {'decode t/s':>10}  {'p90 lat':>8}")
    print(f"  {'─'*38}  {'─'*6}  {'─'*11}  {'─'*10}  {'─'*8}")
    for row in rows:
        print(
            f"  {row['label']:<38}  "
            f"{row['req_per_s']:>6.2f}  "
            f"{row['prefill_tps']:>11.1f}  "
            f"{row['decode_tps']:>10.1f}  "
            f"{row['latency_p90']:>8.2f}s"
        )


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url",         default=DEFAULT_URL)
    ap.add_argument("--model",       default=DEFAULT_MODEL)
    ap.add_argument("--concurrency", type=int, default=8,
                    help="parallel requests for single-level run (default: 8)")
    ap.add_argument("--sweep",       default=None,
                    help="comma-separated concurrency levels, e.g. 2,4,8,12,16")
    ap.add_argument("--requests",    type=int, default=32,
                    help="total requests per concurrency level (default: 32)")
    ap.add_argument("--requests-per-level", type=int, default=None,
                    help="override --requests when using --sweep")
    ap.add_argument("--prompt",      choices=PROMPT_CHOICES,
                    default="all",
                    help="which prompt(s) to use (default: all)")
    ap.add_argument("--quick",       action="store_true",
                    help="fast run: medium-256 only, concurrency=4, 16 requests")
    ap.add_argument("--no-thinking", action="store_true",
                    help="pass chat_template_kwargs enable_thinking=false (Qwen3 GGUF thinking models)")
    ap.add_argument("--serial-n",    type=int, default=3,
                    help="serial baseline requests per prompt (default: 3)")
    ap.add_argument("--csv",         default=None,
                    help="write summary rows to CSV file")
    args = ap.parse_args()

    if args.quick:
        args.prompt = "medium-256"
        args.sweep = None
        args.concurrency = 4
        args.requests = 16
        args.serial_n = 2

    # Build the concurrency levels list
    if args.sweep:
        try:
            concurrency_levels = [int(x.strip()) for x in args.sweep.split(",")]
        except ValueError:
            print("ERROR: --sweep must be comma-separated integers, e.g. 2,4,8,12,16")
            sys.exit(1)
        requests_per_level = args.requests_per_level or args.requests
    else:
        concurrency_levels = [args.concurrency]
        requests_per_level = args.requests

    no_thinking = getattr(args, "no_thinking", False)

    print("═" * 72)
    print(f"  llmstack concurrent benchmark")
    print(f"  model      : {args.model}")
    print(f"  url        : {args.url}")
    if args.sweep:
        print(f"  sweep      : concurrency {concurrency_levels}")
        print(f"  requests   : {requests_per_level} per level")
    else:
        print(f"  concurrency: {concurrency_levels[0]}")
        print(f"  requests   : {requests_per_level} per prompt")
    print(f"  no-thinking: {no_thinking}")
    print(f"  date       : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 72)

    warmup(args.url, args.model, no_thinking=no_thinking)

    suite = [p for p in PROMPT_SUITE
             if args.prompt == "all" or p[0] == args.prompt]

    all_rows = []

    for prompt_label, prompt, max_tokens in suite:
        print(f"\n{'─'*72}")
        print(f"  Prompt: {prompt_label}  (max_tokens={max_tokens})")
        print(f"{'─'*72}")

        # Serial baseline (always single-stream, run once per prompt)
        print(f"\n  [serial] baseline ({args.serial_n} requests):")
        serial_results = run_serial(
            args.url, args.model, prompt_label, prompt, max_tokens, args.serial_n,
            no_thinking=no_thinking
        )
        t_serial = sum(r["wall_s"] for r in serial_results)
        serial_row = report_suite(
            f"{prompt_label} serial",
            serial_results, 0, t_serial, concurrency=1
        )
        if serial_row:
            all_rows.append(serial_row)

        # Concurrency sweep
        for i, conc in enumerate(concurrency_levels):
            step = f"{i+1}/{len(concurrency_levels)}"
            print(f"\n  [{step}] concurrency={conc}  ({requests_per_level} requests):")
            conc_results, errors, wall = run_concurrent(
                args.url, args.model, prompt, max_tokens,
                conc, requests_per_level,
                no_thinking=no_thinking
            )
            conc_row = report_suite(
                f"{prompt_label} conc={conc}",
                conc_results, errors, wall, concurrency=conc
            )
            if conc_row:
                if serial_row and serial_row.get("decode_tps", 0) > 0:
                    speedup = conc_row["decode_tps"] / serial_row["decode_tps"]
                    print(f"  Speedup vs serial (decode tok/s): {speedup:.1f}×")
                all_rows.append(conc_row)

    print_summary(all_rows, args.model)

    if args.csv and all_rows:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            w.writeheader()
            w.writerows(all_rows)
        print(f"\n  Results written to {args.csv}")

    print()


if __name__ == "__main__":
    main()
