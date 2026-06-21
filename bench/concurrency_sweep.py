#!/usr/bin/env python3
"""
Concurrency sweep benchmark: measures aggregate and per-agent tok/s across
a wide range of concurrent request counts to find peak cluster throughput
and the per-agent degradation curve.

Usage:
  python3 bench/concurrency_sweep.py
  python3 bench/concurrency_sweep.py --model qwen3.6-27b-code --save bench/baselines/27b-concurrency-sweep.json
"""
import argparse, json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

URL     = "http://127.0.0.1:8080/v1/chat/completions"
MODEL   = "qwen3.6-27b-code"
LEVELS  = [1, 2, 4, 8, 16, 24, 32, 40, 48, 56, 64]
MAX_TOKENS = 1000

# Code-generation prompt designed to elicit ~1000 tokens of actual code output.
PROMPT = (
    "Write a complete Python implementation of a binary search tree with the "
    "following methods: insert, delete, search, inorder traversal, preorder "
    "traversal, postorder traversal, height, level-order traversal (BFS), "
    "check if the tree is balanced, and find the lowest common ancestor of "
    "two nodes. Include type hints on every method. Output only the code, "
    "no explanations."
)


def do_request(session, url, model, max_tokens):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise coding assistant. Output only what is asked."},
            {"role": "user",   "content": PROMPT},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t0 = time.perf_counter()
    resp = session.post(url, json=payload, timeout=900)
    resp.raise_for_status()
    data = resp.json()
    wall = time.perf_counter() - t0
    usage = data.get("usage", {})
    return {
        "wall_s":            wall,
        "completion_tokens": usage.get("completion_tokens", 0),
        "prompt_tokens":     usage.get("prompt_tokens", 0),
    }


def warmup(url, model, max_tokens):
    s = requests.Session()
    print("  Warming up...", flush=True)
    try:
        r = do_request(s, url, model, max_tokens=10)
        print(f"  Warm-up ok (prompt={r['prompt_tokens']} tokens)")
    except Exception as e:
        print(f"  Warm-up FAILED: {e}")
        sys.exit(1)


def run_level(url, model, concurrency, n_requests, max_tokens):
    results, errors = [], 0
    t_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(do_request, requests.Session(), url, model, max_tokens)
                   for _ in range(n_requests)]
        done = 0
        for fut in as_completed(futures):
            done += 1
            sys.stdout.write(f"\r    {done}/{n_requests}  errors={errors}")
            sys.stdout.flush()
            try:
                results.append(fut.result())
            except Exception:
                errors += 1

    wall_s = time.perf_counter() - t_start
    print()

    if not results:
        return None

    total_out   = sum(r["completion_tokens"] for r in results)
    total_in    = sum(r["prompt_tokens"]     for r in results)
    req_walls   = sorted(r["wall_s"] for r in results)
    n           = len(req_walls)

    aggregate_tps   = total_out / wall_s if wall_s > 0 else 0
    per_agent_tps   = aggregate_tps / concurrency
    mean_wall       = sum(req_walls) / n
    p50             = req_walls[int(n * 0.50)]
    p90             = req_walls[min(int(n * 0.90), n - 1)]
    p99             = req_walls[min(int(n * 0.99), n - 1)]
    mean_out        = total_out / n

    return {
        "concurrency":       concurrency,
        "n_requests":        n_requests,
        "errors":            errors,
        "wall_s":            round(wall_s, 2),
        "aggregate_tps":     round(aggregate_tps, 1),
        "per_agent_tps":     round(per_agent_tps, 2),
        "mean_completion":   round(mean_out, 1),
        "mean_wall_s":       round(mean_wall, 2),
        "p50_wall_s":        round(p50, 2),
        "p90_wall_s":        round(p90, 2),
        "p99_wall_s":        round(p99, 2),
        "total_out_tokens":  total_out,
        "total_in_tokens":   total_in,
    }


def print_results(rows):
    print()
    print("=" * 82)
    print(f"  {'conc':>5}  {'aggregate':>10}  {'per-agent':>10}  {'mean out':>9}  {'mean wall':>10}  {'p90 wall':>9}")
    print(f"  {'':>5}  {'tok/s':>10}  {'tok/s':>10}  {'tokens':>9}  {'s':>10}  {'s':>9}")
    print("-" * 82)
    for r in rows:
        if r is None:
            continue
        err = f" !!{r['errors']}err" if r["errors"] else ""
        print(f"  {r['concurrency']:>5}  {r['aggregate_tps']:>10.1f}  {r['per_agent_tps']:>10.2f}"
              f"  {r['mean_completion']:>9.0f}  {r['mean_wall_s']:>10.2f}  {r['p90_wall_s']:>9.2f}{err}")
    print("=" * 82)


def main():
    ap = argparse.ArgumentParser(description="Concurrency sweep: aggregate vs per-agent tok/s")
    ap.add_argument("--url",        default=URL)
    ap.add_argument("--model",      default=MODEL)
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--levels",     default=",".join(str(x) for x in LEVELS),
                    help="comma-separated concurrency levels")
    ap.add_argument("--requests",   type=int, default=0,
                    help="requests per level (0 = auto: max(conc*2, 32))")
    ap.add_argument("--save",       metavar="FILE", help="save results JSON")
    args = ap.parse_args()

    levels = [int(x) for x in args.levels.split(",")]

    print("=" * 82)
    print(f"  concurrency sweep — {args.model}")
    print(f"  url        : {args.url}")
    print(f"  max_tokens : {args.max_tokens}")
    print(f"  levels     : {levels}")
    print(f"  date       : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 82)

    warmup(args.url, args.model, args.max_tokens)

    rows = []
    for conc in levels:
        n_req = args.requests if args.requests > 0 else max(conc * 2, 32)
        print(f"\n  ── conc={conc}  ({n_req} requests) {'─' * 40}", flush=True)
        row = run_level(args.url, args.model, conc, n_req, args.max_tokens)
        if row:
            rows.append(row)
            print(f"    aggregate={row['aggregate_tps']} tok/s  "
                  f"per-agent={row['per_agent_tps']} tok/s  "
                  f"mean-wall={row['mean_wall_s']}s  "
                  f"mean-out={row['mean_completion']:.0f} tok")

    print_results(rows)

    if args.save:
        out = {
            "model":     args.model,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "max_tokens": args.max_tokens,
            "rows": rows,
        }
        with open(args.save, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\n  Saved → {args.save}")


if __name__ == "__main__":
    main()
