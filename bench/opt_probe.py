#!/usr/bin/env python3
"""
Optimization probes for llmstack.

Verifies each active optimization is delivering measurable gains:

  prefix_cache   — repeated identical requests; TTFT drops on cache hit;
                   vllm:gpu_prefix_cache_hit_rate rises
  kv_efficiency  — vllm:kv_cache_usage_perc at fixed load; FP8 KV should
                   leave more headroom than BF16 for the same workload
  throughput     — decode tok/s at concurrency=N; save as baseline or
                   compare against one to flag regressions

Usage:
  bench/opt_probe.py                              # run all probes
  bench/opt_probe.py --probe prefix_cache
  bench/opt_probe.py --probe kv_efficiency
  bench/opt_probe.py --probe throughput --save-baseline bench/baseline.json
  bench/opt_probe.py --probe throughput --compare-baseline bench/baseline.json
  bench/opt_probe.py --model qwen3.6-35b-fast --no-thinking --probe all
"""

import argparse
import json
import re
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

DEFAULT_URL = "http://127.0.0.1:8080"

# ── System helpers ────────────────────────────────────────────────────────────

def vram_total_gb():
    """Total VRAM used across all GPUs (GB), or None if rocm-smi unavailable."""
    try:
        out = subprocess.check_output(
            ["rocm-smi", "--showmeminfo", "vram"],
            stderr=subprocess.DEVNULL, text=True,
        )
        total = sum(
            int(line.split(":")[-1].strip())
            for line in out.splitlines()
            if "VRAM Total Used Memory (B):" in line
        )
        return total / 1e9
    except Exception:
        return None


def get_active(base_url):
    """Returns (model_id, port) of the currently loaded model, or (None, None)."""
    try:
        r = requests.get(base_url + "/running", timeout=2)
        running = r.json().get("running", [])
        if not running:
            return None, None
        m = running[0]
        port = m.get("port", 0)
        if not port and m.get("proxy"):
            port = int(m["proxy"].rstrip("/").split(":")[-1])
        return m["id"], port
    except Exception:
        return None, None


def get_metric(port, name):
    """Read a single Prometheus gauge from the vLLM /metrics endpoint."""
    try:
        r = requests.get(f"http://127.0.0.1:{port}/metrics", timeout=2)
        m = re.search(
            rf"^{re.escape(name)}\{{[^}}]*\}}\s+([\d.eE+\-]+)",
            r.text, re.MULTILINE,
        )
        return float(m.group(1)) if m else None
    except Exception:
        return None


def warmup(base_url, model, no_thinking=False):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ready"}],
        "max_tokens": 1,
    }
    if no_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    print(f"  Warming up '{model}'…", flush=True)
    t0 = time.time()
    try:
        requests.post(base_url + "/v1/chat/completions", json=payload, timeout=300)
        print(f"  Warm-up done in {time.time()-t0:.1f}s")
    except Exception as e:
        print(f"  Warm-up failed: {e}")
        sys.exit(1)


def chat(base_url, model, system, user, max_tokens, no_thinking=False, timeout=120):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    if no_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    t0 = time.perf_counter()
    r = requests.post(base_url + "/v1/chat/completions", json=payload, timeout=timeout)
    r.raise_for_status()
    elapsed = time.perf_counter() - t0
    usage = r.json().get("usage", {})
    return elapsed, usage.get("completion_tokens", 0), usage.get("total_tokens", 0)


# ── Probe: prefix cache ───────────────────────────────────────────────────────

# Long shared system prompt that exercises the prefix cache.
# Claude Code sends a prompt roughly this size on every request.
_SHARED_PREFIX = (
    "You are a powerful agentic AI coding assistant. You have deep knowledge of "
    "software architecture, algorithms, data structures, testing, security, and "
    "performance optimisation. You always write clean, idiomatic, well-tested code. "
    "You read existing code carefully before making changes and avoid introducing "
    "regressions. When tools are available you use them; when in doubt you ask. "
) * 25  # ~650 tokens

_USER_SHORT = "What is 1+1? Answer in one word."


def probe_prefix_cache(base_url, model, no_thinking, n=6):
    print("\n── Prefix Cache Probe ──────────────────────────────────────────────")
    _, port = get_active(base_url)
    if port is None:
        print("  SKIP: no model loaded or no metrics endpoint (llama-server?)")
        return None

    hit_before = get_metric(port, "vllm:gpu_prefix_cache_hit_rate")

    times = []
    session = requests.Session()
    print(f"  Sending {n} identical requests (prefix ~650 tokens, max_tokens=10)…")
    for i in range(n):
        try:
            elapsed, _, _ = chat(
                base_url, model, _SHARED_PREFIX, _USER_SHORT, 10, no_thinking
            )
            times.append(elapsed)
            print(f"    [{i+1}/{n}] {elapsed:.3f}s")
        except Exception as e:
            print(f"    [{i+1}/{n}] ERROR: {e}")

    hit_after = get_metric(port, "vllm:gpu_prefix_cache_hit_rate")

    if len(times) < 3:
        print("  Not enough data.")
        return None

    first   = times[0]
    warmed  = statistics.mean(times[2:])  # skip first two (cache warms over req 1–2)
    speedup = first / warmed if warmed > 0 else 0

    print(f"\n  First request:          {first:.3f}s")
    print(f"  Warm requests mean:     {warmed:.3f}s  (requests 3–{n})")
    print(f"  Speedup:                {speedup:.2f}×")
    if hit_before is not None:
        print(f"  PfxHit before:          {hit_before*100:.1f}%")
    if hit_after is not None:
        print(f"  PfxHit after:           {hit_after*100:.1f}%")

    passed = speedup >= 1.3
    print(f"\n  RESULT: {'PASS' if passed else 'FAIL'}  "
          f"(speedup {speedup:.2f}× — threshold 1.3×)")

    return {
        "first_s": first, "warmed_mean_s": warmed, "speedup": speedup,
        "hit_rate_before": hit_before, "hit_rate_after": hit_after,
        "passed": passed,
    }


# ── Probe: KV cache efficiency ────────────────────────────────────────────────

def probe_kv_efficiency(base_url, model, no_thinking, concurrency=8):
    """
    Measures vllm:kv_cache_usage_perc at a fixed concurrent load.
    Saves/compares to expose the effect of --kv-cache-dtype fp8:
    with FP8 KV the same workload uses ~50% less of the KV pool.
    Run once before adding --kv-cache-dtype fp8, save as baseline,
    then re-run after to confirm the gain.
    """
    print("\n── KV Cache Efficiency Probe ───────────────────────────────────────")
    _, port = get_active(base_url)
    if port is None:
        print("  SKIP: no metrics endpoint")
        return None

    vram_idle = vram_total_gb()
    print(f"  Idle VRAM: {vram_idle:.2f} GB" if vram_idle else "  VRAM: rocm-smi unavailable")

    prompt = (
        "Write a detailed design document for a distributed rate-limiter "
        "using a sliding window algorithm with Redis as the backing store. "
        "Cover consistency, failure modes, and client retry logic. " * 8
    )

    kv_samples   = []
    vram_samples = []
    stop         = threading.Event()

    def poll(p):
        while not stop.is_set():
            kv = get_metric(p, "vllm:kv_cache_usage_perc")
            if kv is not None:
                kv_samples.append(kv)
            v = vram_total_gb()
            if v is not None:
                vram_samples.append(v)
            time.sleep(0.5)

    poller = threading.Thread(target=poll, args=(port,), daemon=True)
    poller.start()

    errors = 0

    def do_req(_):
        nonlocal errors
        try:
            chat(base_url, model, "", prompt, 256, no_thinking, timeout=180)
        except Exception:
            errors += 1

    print(f"  Sending {concurrency} concurrent requests…")
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for f in as_completed([pool.submit(do_req, i) for i in range(concurrency)]):
            pass
    elapsed = time.perf_counter() - t0
    stop.set()

    if not kv_samples:
        print("  No KV cache metrics collected (is prefix-caching reporting this metric?).")
        return None

    kv_peak = max(kv_samples)
    kv_mean = statistics.mean(kv_samples)
    vram_peak = max(vram_samples) if vram_samples else None
    vram_delta = (vram_peak - vram_idle) if (vram_peak and vram_idle) else None

    print(f"\n  Concurrency:     {concurrency}")
    print(f"  Wall time:       {elapsed:.1f}s  (errors={errors})")
    print(f"  KV cache peak:   {kv_peak*100:.1f}%")
    print(f"  KV cache mean:   {kv_mean*100:.1f}%")
    if vram_delta is not None:
        print(f"  Peak VRAM:       {vram_peak:.2f} GB  (Δ {vram_delta:+.2f} GB vs idle)")

    print(
        "\n  To observe FP8 KV gain: save a baseline *before* adding --kv-cache-dtype fp8,\n"
        "  then compare after. Lower KV% at the same concurrency = more headroom = working."
    )

    return {
        "concurrency": concurrency,
        "kv_cache_peak_pct": kv_peak * 100,
        "kv_cache_mean_pct": kv_mean * 100,
        "vram_peak_gb": vram_peak,
        "vram_delta_gb": vram_delta,
        "errors": errors,
    }


# ── Probe: throughput regression ──────────────────────────────────────────────

def probe_throughput(base_url, model, no_thinking, concurrency=8, n=16,
                     save_path=None, compare_path=None):
    """
    Decode tok/s at fixed concurrency.  Save once before a config change as
    baseline; compare after to confirm no regression (threshold: -5%).
    """
    print("\n── Throughput Probe ─────────────────────────────────────────────────")

    prompt = (
        "You are a senior engineer reviewing a production incident. "
        "Describe the steps you would take to diagnose and resolve a memory "
        "leak in a Go service under heavy load. Be specific and technical."
    )
    max_tokens = 256

    results = []
    errors  = 0
    t0      = time.perf_counter()

    def do_req(_):
        try:
            elapsed, comp, total = chat(
                base_url, model, "", prompt, max_tokens, no_thinking, timeout=300
            )
            return {"wall_s": elapsed, "completion_tokens": comp, "total_tokens": total}
        except Exception as e:
            return {"error": str(e)}

    print(f"  {n} requests at concurrency={concurrency}…")
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        done = 0
        for f in as_completed([pool.submit(do_req, i) for i in range(n)]):
            r = f.result()
            if "error" in r:
                errors += 1
            else:
                results.append(r)
            done += 1
            sys.stdout.write(f"\r    {done}/{n}  errors={errors}")
            sys.stdout.flush()
    print()

    wall = time.perf_counter() - t0
    if not results:
        print("  No results.")
        return None

    comp_tokens  = [r["completion_tokens"] for r in results]
    wall_times   = [r["wall_s"]            for r in results]
    decode_tps   = sum(comp_tokens) / wall
    latency_mean = statistics.mean(wall_times)
    latency_p90  = sorted(wall_times)[int(len(wall_times) * 0.9)]

    print(f"\n  Decode tok/s:    {decode_tps:.1f}")
    print(f"  Latency mean:    {latency_mean:.2f}s")
    print(f"  Latency p90:     {latency_p90:.2f}s")
    print(f"  Errors:          {errors}/{n}")

    current = {
        "model":            model,
        "concurrency":      concurrency,
        "n_requests":       n,
        "decode_tps":       decode_tps,
        "latency_mean_s":   latency_mean,
        "latency_p90_s":    latency_p90,
        "errors":           errors,
        "timestamp":        time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        Path(save_path).write_text(json.dumps(current, indent=2))
        print(f"\n  Baseline saved → {save_path}")

    passed = None
    if compare_path and Path(compare_path).exists():
        baseline = json.loads(Path(compare_path).read_text())
        ts       = baseline.get("timestamp", "?")
        print(f"\n  Comparison vs baseline ({ts}):")
        print(f"  {'Metric':<24}  {'Baseline':>10}  {'Current':>10}  {'Delta':>8}  Result")
        print(f"  {'─'*24}  {'─'*10}  {'─'*10}  {'─'*8}  ──────")

        def row(label, key, higher_better):
            old = baseline.get(key)
            new = current.get(key)
            if old is None or new is None:
                return None
            pct  = (new - old) / old * 100 if old else 0
            good = (pct >= -5) if higher_better else (pct <= 5)
            sym  = "✓ PASS" if good else "✗ FAIL"
            dir_ = "▲" if pct > 0 else "▼"
            print(f"  {label:<24}  {old:>10.2f}  {new:>10.2f}  {dir_}{abs(pct):>6.1f}%  {sym}")
            return good

        t_pass = row("decode tok/s",   "decode_tps",     higher_better=True)
        l_pass = row("latency mean s", "latency_mean_s", higher_better=False)
        row("latency p90 s",  "latency_p90_s",  higher_better=False)

        passed = (t_pass is not False) and (l_pass is not False)
        print(f"\n  Overall: {'PASS' if passed else 'FAIL'}")
        current["passed"] = passed

    return current


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--url",         default=DEFAULT_URL)
    ap.add_argument("--model",       default="qwen3.6-35b-code")
    ap.add_argument("--probe",       default="all",
                    choices=["all", "prefix_cache", "kv_efficiency", "throughput"])
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--requests",    type=int, default=16)
    ap.add_argument("--no-thinking", action="store_true")
    ap.add_argument("--save-baseline",    default=None, metavar="FILE",
                    help="save throughput/kv results as baseline JSON")
    ap.add_argument("--compare-baseline", default=None, metavar="FILE",
                    help="compare throughput results against saved baseline")
    args = ap.parse_args()

    no_thinking = args.no_thinking

    print("═" * 68)
    print(f"  llmstack optimization probes")
    print(f"  model: {args.model}   url: {args.url}")
    print(f"  date:  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 68)

    model_id, port = get_active(args.url)
    if model_id is None:
        print("ERROR: no model loaded.  Run: llmctl swap <profile>")
        sys.exit(1)
    print(f"  Active: {model_id}  port={port}\n")

    warmup(args.url, args.model, no_thinking)

    results = {}

    if args.probe in ("all", "prefix_cache"):
        results["prefix_cache"] = probe_prefix_cache(
            args.url, args.model, no_thinking
        )

    if args.probe in ("all", "kv_efficiency"):
        results["kv_efficiency"] = probe_kv_efficiency(
            args.url, args.model, no_thinking, args.concurrency
        )

    if args.probe in ("all", "throughput"):
        results["throughput"] = probe_throughput(
            args.url, args.model, no_thinking,
            concurrency=args.concurrency,
            n=args.requests,
            save_path=args.save_baseline,
            compare_path=args.compare_baseline,
        )

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "═" * 68)
    print("  SUMMARY")
    print("═" * 68)
    for name, result in results.items():
        if result is None:
            status = "SKIP"
        elif result.get("passed") is True:
            status = "PASS"
        elif result.get("passed") is False:
            status = "FAIL"
        else:
            # probe ran but no threshold (e.g. kv_efficiency without baseline)
            if name == "kv_efficiency" and result.get("kv_cache_peak_pct") is not None:
                status = f"kv_peak={result['kv_cache_peak_pct']:.1f}%  (save baseline to compare)"
            else:
                status = "OK (no threshold)"
        print(f"  {name:<16}  {status}")
    print()


if __name__ == "__main__":
    main()
