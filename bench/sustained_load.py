#!/usr/bin/env python3
"""Sustained-load staged concurrency test (closed loop, long generations).

For each concurrency level N, keep N streaming requests in flight for --duration
seconds. Every request asks for ~--max-tokens tokens (min_tokens == max_tokens, so
every request really generates that many; this is a load test, not a quality test).

Throughput is taken from vLLM's own generation-token counter (/metrics on the
backend), sampled every --sample seconds, so it is exact and unaffected by how
many tokens a streamed chunk carries (MTP). GPU power and temperature are read
from amdgpu hwmon sysfs at the same cadence. Everything is flushed to disk as it
is produced so a crash or power loss still leaves the data up to that point.

Usage:
  python3 bench/sustained_load.py --model qwen3.8-27b-code --levels 4,8,12,16 \
      --duration 330 --out bench/results/sustained-<date>
"""
import argparse, csv, glob, http.client, json, os, re, sys, threading, time, urllib.request
from urllib.parse import urlparse

TOPICS = [
    "the history and engineering of undersea telegraph and fibre-optic cables",
    "how a modern relational database engine executes a query, from parser to disk",
    "the design of a distributed consensus protocol such as Raft, with worked examples",
    "the physics and engineering of grid-scale battery storage",
    "building a compiler for a small statically typed language, front to back",
    "the economics and logistics of container shipping",
    "how operating system schedulers and virtual memory work, with code sketches",
    "the biochemistry of photosynthesis and its engineering for crop yield",
    "network protocols from Ethernet frames up to TLS and HTTP/3",
    "the architecture of a large-scale web search engine",
    "a field guide to numerical methods for differential equations",
    "the design and operation of a hydroelectric power station",
    "how GPUs execute matrix multiplication, from tiling to tensor cores",
    "the history of cryptography from classical ciphers to post-quantum schemes",
    "city-scale water supply and sewage engineering",
    "the principles of structural engineering for tall buildings",
]


_VOCAB = (
    "river stone market engine signal garden winter copper window letter harbor ledger "
    "forest bridge candle pattern thunder valley compass ribbon lantern meadow anchor "
    "quartz saddle timber velvet whisper yellow zephyr amber basalt cobalt dagger ember "
    "fjord glacier hollow ivory jasper kernel lagoon mosaic nectar orchid prism quiver "
    "raven summit tundra umber vortex willow xenon yarrow zenith arrow beacon cinder "
    "dune echo flint grove haven island jungle knoll lotus marble nomad oasis pebble "
    "quarry reef shadow tower utopia voyage wharf yonder zealot atlas bronze cedar delta"
).split()


def long_prompt(i, words):
    """Unique filler text (different from the first token on) so prefix caching cannot help."""
    import random
    rng = random.Random(i * 7919 + 13)
    body = " ".join(rng.choice(_VOCAB) + rng.choice(["", "", ",", "."]) for _ in range(words))
    return ("Below is a long passage of unrelated words. Read it, then answer the question at the end.\n\n"
            + body + "\n\nQuestion: in two sentences, describe what kind of text this is.")


def prompt_for(i):
    t = TOPICS[i % len(TOPICS)]
    return (
        f"Write an extremely long, thorough, book-length technical reference on {t}. "
        "Organise it into many numbered chapters with sections and sub-sections, give worked "
        "examples, tables, and numbered lists, and keep going in depth. Do not summarise or "
        "conclude early; continue writing new material until you are stopped. "
        f"(Variant {i}.)"
    )


def pct(vals, p):
    if not vals:
        return None
    v = sorted(vals)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))]


def calibrate_words(backend, model, target_tokens):
    """Probe once to learn tokens-per-word of the filler, return the word count for target_tokens."""
    probe = 2000
    body = {"model": model, "max_tokens": 1, "stream": False,
            "messages": [{"role": "user", "content": long_prompt(999999, probe)}],
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(backend.rstrip("/") + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        used = json.loads(r.read())["usage"]["prompt_tokens"]
    overhead = 60  # template + instruction text
    tpw = (used - overhead) / probe
    words = int((target_tokens - overhead) / tpw)
    print(f"calibration: {tpw:.2f} tokens/word -> {words} words ~ {target_tokens} prompt tokens", flush=True)
    return words


def fmt(x, nd=1):
    return "n/a" if x is None else f"{x:.{nd}f}"


def get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def backend_url(router):
    """Resolve the backend (vLLM) base URL from llama-swap's /running."""
    running = get_json(router.rstrip("/") + "/running").get("running", [])
    for m in running:
        if m.get("state") == "ready":
            return m["proxy"], m["model"]
    return None, None


def metric_sum(text, name):
    tot, found = 0.0, False
    for m in re.finditer(r"^" + re.escape(name) + r"(?:\{[^}]*\})?\s+([0-9.eE+-]+)\s*$", text, re.M):
        tot += float(m.group(1)); found = True
    return tot if found else None


def read_metrics(base):
    with urllib.request.urlopen(base.rstrip("/") + "/metrics", timeout=5) as r:
        t = r.read().decode()
    return {
        "gen_tokens": metric_sum(t, "vllm:generation_tokens_total"),
        "prompt_tokens": metric_sum(t, "vllm:prompt_tokens_total"),
        "pc_hits": metric_sum(t, "vllm:prefix_cache_hits_total"),
        "pc_queries": metric_sum(t, "vllm:prefix_cache_queries_total"),
        "running": metric_sum(t, "vllm:num_requests_running"),
        "waiting": metric_sum(t, "vllm:num_requests_waiting"),
        "spec_accepted": metric_sum(t, "vllm:spec_decode_num_accepted_tokens_total"),
        "spec_draft": metric_sum(t, "vllm:spec_decode_num_draft_tokens_total"),
        "kv_usage": metric_sum(t, "vllm:kv_cache_usage_perc") if "vllm:kv_cache_usage_perc" in t else metric_sum(t, "vllm:gpu_cache_usage_perc"),
    }


def gpu_hwmons():
    out = []
    for d in sorted(glob.glob("/sys/class/drm/card[0-9]*/device")):
        try:
            if open(d + "/vendor").read().strip() != "0x1002":
                continue
        except OSError:
            continue
        hm = glob.glob(d + "/hwmon/hwmon*")
        if hm:
            out.append((os.path.basename(os.path.dirname(d)), hm[0]))
    return out


def rd(path):
    try:
        return int(open(path).read().strip())
    except (OSError, ValueError):
        return None


def read_gpus(hwmons):
    row = []
    for _, hm in hwmons:
        p = rd(hm + "/power1_average")
        if p is None:
            p = rd(hm + "/power1_input")
        t = rd(hm + "/temp2_input")  # junction
        row.append((None if p is None else p / 1e6, None if t is None else t / 1000))
    return row


class Level:
    def __init__(self, n):
        self.n = n
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.started = 0
        self.completed = []   # dicts per finished request
        self.errors = []
        self.cut = 0          # in-flight requests cancelled at level end
        self.ttft = []


def worker(wid, level, args, backend, model):
    u = urlparse(backend)
    i = wid + level.base  # base differs per level and per run, so prompts never repeat (no prefix-cache hits)
    while not level.stop.is_set():
        i += 1000  # distinct prompt per request
        text = long_prompt(i, args.prompt_words) if args.prompt_words else prompt_for(i)
        body = {
            "model": model,
            "messages": [{"role": "user", "content": text}],
            "max_tokens": args.max_tokens,
            "temperature": 0.7, "top_p": 0.8, "presence_penalty": 1.0,
            "stream": True,
            "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if not args.free_length:
            body["min_tokens"] = args.max_tokens  # force the full length (load test, not quality)
        conn = http.client.HTTPConnection(u.hostname, u.port, timeout=args.req_timeout)
        t0 = time.time(); first = None; chunks = 0; usage = None; ok = False
        with level.lock:
            level.started += 1
        try:
            conn.request("POST", "/v1/chat/completions", json.dumps(body),
                         {"Content-Type": "application/json"})
            r = conn.getresponse()
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}: {r.read()[:200]!r}")
            for line in r:
                if level.stop.is_set():
                    break
                if not line.startswith(b"data:"):
                    continue
                d = line[5:].strip()
                if d == b"[DONE]":
                    ok = True
                    break
                try:
                    j = json.loads(d)
                except ValueError:
                    continue
                if j.get("usage"):
                    usage = j["usage"]
                if j.get("choices") and j["choices"][0].get("delta", {}).get("content"):
                    if first is None:
                        first = time.time() - t0
                    chunks += 1
        except Exception as e:  # noqa
            if not level.stop.is_set():
                with level.lock:
                    level.errors.append({"t": time.time(), "err": repr(e)[:300]})
                time.sleep(2)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        with level.lock:
            if ok:
                level.completed.append({"secs": time.time() - t0, "ttft": first, "chunks": chunks,
                                        "completion_tokens": (usage or {}).get("completion_tokens")})
            elif level.stop.is_set():
                level.cut += 1


def run_level(n, args, backend, model, hwmons, samples_w, out_dir):
    lvl = Level(n)
    lvl.base = args.seed + n * 100_000_000
    threads = [threading.Thread(target=worker, args=(w, lvl, args, backend, model), daemon=True)
               for w in range(n)]
    t_start = time.time()
    m0 = read_metrics(backend)
    rows = []
    print(f"\n=== concurrency {n}: {args.duration}s window ===", flush=True)
    for th in threads:
        th.start()
    last = m0
    while time.time() - t_start < args.duration:
        time.sleep(args.sample)
        now = time.time()
        try:
            m = read_metrics(backend)
        except Exception as e:
            print(f"  metrics read failed: {e!r}", flush=True)
            with lvl.lock:
                lvl.errors.append({"t": now, "err": "metrics: " + repr(e)[:200]})
            if len(lvl.errors) > 20:
                print("  too many errors, aborting level", flush=True)
                break
            continue
        g = read_gpus(hwmons)
        dt = args.sample
        inst = (m["gen_tokens"] - last["gen_tokens"]) / dt if m["gen_tokens"] is not None else None
        last = m
        el = now - t_start
        pw = [x[0] for x in g]
        row = {"level": n, "elapsed_s": round(el, 1), "gen_tokens": m["gen_tokens"], "inst_tok_s": inst,
               "running": m["running"], "waiting": m["waiting"], "kv_usage": m["kv_usage"],
               "gpu_w": pw, "gpu_c": [x[1] for x in g], "errors": len(lvl.errors)}
        rows.append(row)
        samples_w.writerow([n, f"{el:.1f}", m["gen_tokens"], f"{inst:.1f}" if inst is not None else "",
                            m["running"], m["waiting"], m["kv_usage"]]
                           + [("" if x is None else f"{x:.0f}") for x in pw]
                           + [("" if x[1] is None else f"{x[1]:.0f}") for x in g])
        print(f"  t={el:5.0f}s  {inst if inst is not None else float('nan'):7.1f} tok/s  run={m['running']:.0f} "
              f"wait={m['waiting']:.0f} kv={m['kv_usage']}  W={['%.0f' % x if x is not None else '?' for x in pw]} "
              f"err={len(lvl.errors)}", flush=True)
    t_end = time.time()
    m1 = last
    lvl.stop.set()
    for th in threads:
        th.join(timeout=15)
    # let the server notice the disconnects and drain before the next level
    for _ in range(30):
        try:
            if (read_metrics(backend)["running"] or 0) == 0:
                break
        except Exception:
            pass
        time.sleep(2)
    dur = t_end - t_start
    toks = (m1["gen_tokens"] - m0["gen_tokens"]) if m1["gen_tokens"] is not None else None
    insts = [r["inst_tok_s"] for r in rows if r["inst_tok_s"] is not None]
    # steady state = skip the first 30 s (prefill ramp)
    steady = [r["inst_tok_s"] for r in rows if r["inst_tok_s"] is not None and r["elapsed_s"] > 30]
    mins = {}
    for r in rows:
        if r["inst_tok_s"] is not None:
            mins.setdefault(int(r["elapsed_s"] // 60), []).append(r["inst_tok_s"])
    pmax = [max([r["gpu_w"][g] for r in rows if r["gpu_w"][g] is not None] or [None]) for g in range(len(hwmons))]
    pavg = [(sum(v) / len(v)) if (v := [r["gpu_w"][g] for r in rows if r["gpu_w"][g] is not None]) else None
            for g in range(len(hwmons))]
    tmax = [max([r["gpu_c"][g] for r in rows if r["gpu_c"][g] is not None] or [None]) for g in range(len(hwmons))]
    acc = None
    if m1.get("spec_draft") and m0.get("spec_draft") is not None and m1["spec_draft"] > m0["spec_draft"]:
        acc = (m1["spec_accepted"] - m0["spec_accepted"]) / (m1["spec_draft"] - m0["spec_draft"])
    res = {
        "concurrency": n, "window_s": round(dur, 1), "tokens_generated": toks,
        "avg_tok_s": toks / dur if toks is not None else None,
        "steady_avg_tok_s": sum(steady) / len(steady) if steady else None,
        "peak_tok_s": max(insts) if insts else None,
        "per_minute_avg_tok_s": {str(k): sum(v) / len(v) for k, v in sorted(mins.items())},
        "per_stream_steady_tok_s": (sum(steady) / len(steady) / n) if steady else None,
        "spec_accept_rate": acc,
        "requests_started": lvl.started, "requests_completed": len(lvl.completed),
        "requests_cut_at_level_end": lvl.cut, "errors": len(lvl.errors), "error_samples": lvl.errors[:5],
        "prompt_tok_s": ((m1["prompt_tokens"] - m0["prompt_tokens"]) / dur) if m1.get("prompt_tokens") is not None and m0.get("prompt_tokens") is not None else None,
        "prefix_cache_hit_rate": ((m1["pc_hits"] - m0["pc_hits"]) / (m1["pc_queries"] - m0["pc_queries"])) if m1.get("pc_queries") and m1["pc_queries"] > (m0.get("pc_queries") or 0) else None,
        "req_per_s": len(lvl.completed) / dur,
        "ttft_p50_s": pct([c["ttft"] for c in lvl.completed if c["ttft"]], 50),
        "ttft_p95_s": pct([c["ttft"] for c in lvl.completed if c["ttft"]], 95),
        "latency_p50_s": pct([c["secs"] for c in lvl.completed], 50),
        "ttft_median_s": pct([c["ttft"] for c in lvl.completed if c["ttft"]], 50),
        "gpu_power_avg_w": pavg, "gpu_power_max_w": pmax, "gpu_temp_max_c": tmax,
    }
    json.dump(res, open(os.path.join(out_dir, f"level-{n:02d}.json"), "w"), indent=1)
    print(f"  -> conc {n}: avg {fmt(res['avg_tok_s'])} tok/s, steady {fmt(res['steady_avg_tok_s'])}, "
          f"per-stream {fmt(res['per_stream_steady_tok_s'])}, errors {res['errors']}", flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--router", default="http://127.0.0.1:8080")
    ap.add_argument("--model", default="qwen3.8-27b-code")
    ap.add_argument("--levels", default="4,8,12,16")
    ap.add_argument("--duration", type=int, default=330, help="seconds per level")
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--prompt-tokens", type=int, default=0,
                    help="send ~this many unique prompt tokens per request (prefill-heavy test)")
    ap.add_argument("--seed", type=int, default=int(time.time()) % 1_000_000 * 1000,
                    help="prompt seed base; default differs every run so a rerun cannot hit the prefix cache")
    ap.add_argument("--free-length", action="store_true",
                    help="do not force min_tokens==max_tokens; let the model stop on its own")
    ap.add_argument("--sample", type=float, default=5.0)
    ap.add_argument("--req-timeout", type=int, default=3600)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    backend, model = backend_url(args.router)
    if not backend:
        sys.exit("no ready model on the router; load one first (llmctl swap ...)")
    if args.model and model != args.model:
        sys.exit(f"router has {model!r} loaded, expected {args.model!r}")
    args.prompt_words = calibrate_words(backend, model, args.prompt_tokens) if args.prompt_tokens else 0
    hwmons = gpu_hwmons()
    print(f"backend={backend} model={model} gpus={[n for n, _ in hwmons]}", flush=True)
    f = open(os.path.join(args.out, "samples.csv"), "a", newline="")
    w = csv.writer(f)
    if f.tell() == 0:
        w.writerow(["level", "elapsed_s", "gen_tokens", "inst_tok_s", "running", "waiting", "kv_usage"]
                   + [f"{n}_W" for n, _ in hwmons] + [f"{n}_C" for n, _ in hwmons])

    class Flush:  # flush the CSV on every row so a power loss keeps the data
        def writerow(self, r):
            w.writerow(r); f.flush(); os.fsync(f.fileno())

    results = []
    for n in [int(x) for x in args.levels.split(",")]:
        try:
            results.append(run_level(n, args, backend, model, hwmons, Flush(), args.out))
        except Exception as e:  # noqa
            print(f"level {n} aborted: {e!r}", flush=True)
            break
    json.dump(results, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
    if args.prompt_tokens:
        print("\n| conc | prefill tok/s | decode tok/s | req/s | done | TTFT p50 s | TTFT p95 s | latency p50 s | cache hit | max W per GPU | errors |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in results:
            print(f"| {r['concurrency']} | {fmt(r['prompt_tok_s'], 0)} | {fmt(r['avg_tok_s'], 0)} | {fmt(r['req_per_s'], 2)} | "
                  f"{r['requests_completed']} | {fmt(r['ttft_p50_s'])} | {fmt(r['ttft_p95_s'])} | {fmt(r['latency_p50_s'])} | "
                  f"{fmt(r['prefix_cache_hit_rate'], 2)} | {[round(x) if x else None for x in r['gpu_power_max_w']]} | {r['errors']} |")
    print("\n| conc | avg tok/s | steady tok/s | per-stream | peak | spec accept | max W per GPU | max C | errors |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        print(f"| {r['concurrency']} | {fmt(r['avg_tok_s'], 0)} | {fmt(r['steady_avg_tok_s'], 0)} | "
              f"{fmt(r['per_stream_steady_tok_s'])} | {fmt(r['peak_tok_s'], 0)} | "
              f"{'' if r['spec_accept_rate'] is None else '%.2f' % r['spec_accept_rate']} | "
              f"{[round(x) if x else None for x in r['gpu_power_max_w']]} | {r['gpu_temp_max_c']} | {r['errors']} |")


if __name__ == "__main__":
    main()
