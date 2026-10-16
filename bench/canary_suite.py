#!/usr/bin/env python3
"""Full canary suite: speed + quality + long context for ONE served model in ONE environment.

Run the identical suite against the shipped state and the candidate state, then diff them with
canary_compare.py. Every stage writes its own JSON under --out and is skipped when that file already exists
(use --force to redo), so an interrupted run resumes where it stopped.

Stages (all by default):
  env      image / ROCm / torch / vLLM versions, kernel, amdgpu driver, GPU tool
  speed    concurrent_bench sweep 1,2,4,8,16 over all four prompt sizes, no-thinking, 32 requests per level
  depth    streamed decode speed at 1K..200K tokens of context (fixed 512-token output)
  tools    tool-call correctness, non-streaming and streaming (the vLLM null-name SSE bug shows up here)
  stress   7 concurrent unique ~100K-token prompts: all must finish; peak VRAM and preemptions recorded
  quality  code-correctness suite (bench/codetests): hard tasks x N samples + the saturated set x 2

Usage:
  python3 bench/canary_suite.py --base http://127.0.0.1:8080 --model qwen3.8-27b-code \\
      --label v0.26.0 --container llmstack-vllm-qwen3.8-27b-code --out bench/results/canary-rocm10/27b-s0

Quality runs take hours (thinking, up to 81,920 tokens per sample). Speed, depth, tools and stress take about an hour.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import gpustat  # noqa: E402

STAGES = ["env", "speed", "depth", "tools", "stress", "quality"]
HARD_TASKS = "regex_engine,mini_scheme,json_strict,date_math,cron_next"
COMMON_TASKS = "expr_eval,log_stats,retry_decorator,shopping_cart,todo_repo,ttl_cache"
NO_THINK = {"enable_thinking": False}


def sh(argv, timeout=60):
    try:
        return subprocess.check_output(argv, stderr=subprocess.STDOUT, text=True, timeout=timeout).strip()
    except Exception as e:  # missing tool, non-zero exit, timeout: record, don't abort the suite
        return f"ERROR: {type(e).__name__}: {e}"


# ── env ─────────────────────────────────────────────────────────────────────────

def stage_env(a, out):
    env = {"label": a.label, "model": a.model, "date": time.strftime("%Y-%m-%d %H:%M:%S"),
           "kernel": sh(["uname", "-r"]), "amdgpu_driver": sh(["modinfo", "-F", "version", "amdgpu"]),
           "host_rocm": sh(["cat", "/opt/rocm/.info/version"]), "amd_smi": sh(["amd-smi", "version"]).splitlines()[:1],
           "gpu_tool": gpustat.read_gpus()[1], "gpu_count": len(gpustat.read_gpus()[0])}
    try:
        models = requests.get(f"{a.base}/v1/models", timeout=10).json()
        env["served_models"] = [m.get("id") for m in models.get("data", [])]
    except Exception as e:
        env["served_models"] = f"ERROR {e}"
    if a.container:
        env["container"] = a.container
        env["image"] = sh(["podman", "inspect", "-f", "{{.ImageName}}", a.container])
        env["image_id"] = sh(["podman", "inspect", "-f", "{{.Image}}", a.container])
        # Distro-style images carry /opt/rocm/.info/version; the ROCm 10 wheel images only have the rocm-sdk pip packages.
        env["container_rocm"] = sh(["podman", "exec", a.container, "bash", "-c",
                                    "cat /opt/rocm/.info/version 2>/dev/null || "
                                    "pip list 2>/dev/null | awk '$1==\"rocm-sdk-devel\"{print $2\" (rocm-sdk wheels)\"}'"])
        env["container_python"] = sh(["podman", "exec", a.container, "python3", "-c",
                                      "import vllm, torch; print(vllm.__version__, torch.__version__, torch.version.hip)"],
                                     timeout=120)
        env["container_cmd"] = sh(["podman", "inspect", "-f", "{{.Config.Cmd}}", a.container])
    return env


# ── speed ───────────────────────────────────────────────────────────────────────

def stage_speed(a, out):
    save = os.path.join(out, "speed.json")
    cmd = [sys.executable, os.path.join(HERE, "concurrent_bench.py"), "--model", a.model,
           "--url", f"{a.base}/v1/chat/completions", "--sweep", "1,2,4,8,16", "--prompt", "all",
           "--no-thinking", "--requests", "32", "--save", save, "--csv", os.path.join(out, "speed.csv")]
    with open(os.path.join(out, "speed.log"), "w") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    return None  # concurrent_bench wrote speed.json itself


# ── depth ───────────────────────────────────────────────────────────────────────

def _filler(tag, n_lines):
    # Distinct first line per probe so prefix caching never shares prefill between depths.
    lines = [f"Dataset {tag}."]
    lines += [f"Record {i:06d}: sensor {(i * 7919) % 997} reported {(i * 104729) % 100003} units at t={i * 13 % 86400}s."
              for i in range(n_lines)]
    return "\n".join(lines)


def _stream_decode(a, n_lines, tag, out_tokens=512):
    msg = _filler(tag, n_lines) + "\n\nSummarize the records above in detail, listing as many individual records as you can."
    body = {"model": a.model, "messages": [{"role": "user", "content": msg}], "max_tokens": out_tokens,
            "min_tokens": out_tokens, "temperature": 0.6, "stream": True,
            "stream_options": {"include_usage": True}, "chat_template_kwargs": NO_THINK}
    t0, first, last, usage = time.time(), None, None, {}
    with requests.post(f"{a.base}/v1/chat/completions", json=body, stream=True, timeout=7200) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith(b"data: ") or line == b"data: [DONE]":
                continue
            ev = json.loads(line[6:])
            usage = ev.get("usage") or usage
            ch = ev.get("choices") or []
            if ch and (ch[0].get("delta") or {}).get("content"):
                now = time.time()
                first, last = first or now, now
    p, c = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    ttft = (first - t0) if first else None
    dec = (c - 1) / (last - first) if first and last and last > first else None
    return {"prompt_tokens": p, "completion_tokens": c, "ttft_s": ttft,
            "prefill_tps": (p / ttft) if ttft else None, "decode_tps": dec}


def stage_depth(a, out):
    per_line = _stream_decode(a, 200, "calib")["prompt_tokens"] / 200
    rows = []
    for d in a.depths:
        n = max(10, int((d - 60) / per_line))
        try:
            row = {"target": d, **_stream_decode(a, n, f"d{d}")}
        except Exception as e:
            row = {"target": d, "error": str(e)[:200]}
        rows.append(row)
        print(f"  depth {d}: {row}", flush=True)
    return {"rows": rows}


# ── tools ───────────────────────────────────────────────────────────────────────

WEATHER = {"type": "function", "function": {
    "name": "get_weather", "description": "Get current weather for a city",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}, "unit": {"type": "string", "enum": ["c", "f"]}},
                   "required": ["city"]}}}
ADD = {"type": "function", "function": {
    "name": "add", "description": "Add two integers",
    "parameters": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                   "required": ["a", "b"]}}}
TOOL_CASES = (
    [(f"What's the weather in {c}? Use celsius.", WEATHER, "get_weather", lambda a, c=c: a.get("city") == c)
     for c in ["Paris", "Tokyo", "Lima", "Oslo", "Cairo"]]
    + [(f"Use the add tool to add {x} and {y}.", ADD, "add",
        lambda a, x=x, y=y: a.get("a") == x and a.get("b") == y) for x, y in [(17, 25), (-4, 1000), (123456, 654321)]])


def _tool_call(a, prompt, tool, stream):
    body = {"model": a.model, "messages": [{"role": "user", "content": prompt}], "tools": [tool],
            "tool_choice": "auto", "max_tokens": 1024, "temperature": 0.0, "chat_template_kwargs": NO_THINK}
    url = f"{a.base}/v1/chat/completions"
    if not stream:
        msg = requests.post(url, json=body, timeout=600).json()["choices"][0]["message"]
        return [(t["function"]["name"], t["function"]["arguments"]) for t in msg.get("tool_calls") or []]
    body["stream"] = True
    calls = {}
    with requests.post(url, json=body, stream=True, timeout=600) as r:
        for line in r.iter_lines():
            if not line.startswith(b"data: ") or line == b"data: [DONE]":
                continue
            for ch in json.loads(line[6:]).get("choices", []):
                for tc in (ch.get("delta") or {}).get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), ["", ""])
                    fn = tc.get("function") or {}
                    slot[0] += fn.get("name") or ""
                    slot[1] += fn.get("arguments") or ""
    return [tuple(v) for _, v in sorted(calls.items())]


def stage_tools(a, out):
    rows = []
    for stream in (False, True):
        for prompt, tool, name, check in TOOL_CASES:
            ok, detail = False, ""
            try:
                calls = _tool_call(a, prompt, tool, stream)
                if calls:
                    args = json.loads(calls[0][1])
                    ok = calls[0][0] == name and check(args)
                    detail = f"{calls[0][0]} {calls[0][1][:80]}"
                else:
                    detail = "no tool call"
            except Exception as e:
                detail = f"ERROR {str(e)[:100]}"
            rows.append({"stream": stream, "prompt": prompt, "ok": ok, "detail": detail})
    return {"passed": sum(r["ok"] for r in rows), "total": len(rows), "rows": rows}


# ── stress ──────────────────────────────────────────────────────────────────────

def _metric(a, name):
    try:
        text = requests.get(f"{a.base}/upstream/{a.model}/metrics", timeout=10).text
    except Exception:
        return None
    vals = [float(ln.rsplit(" ", 1)[1]) for ln in text.splitlines() if ln.startswith(name)]
    return sum(vals) if vals else None


def _stress_prompt(i, paras):
    body = "".join(f"Ledger entry {i}-{k}: the miller of village {i * 7919 + k} sold {k * 13 % 97} sacks of grain "
                   f"to the merchant {i}x{k}, noting the river level and the weather. " for k in range(paras))
    return body + "\nQuestion: how many ledger entries are above? Answer briefly."


def stage_stress(a, out):
    url = f"{a.base}/v1/chat/completions"

    def call(i, paras, res):
        body = {"model": a.model, "messages": [{"role": "user", "content": _stress_prompt(i, paras)}],
                "max_tokens": 64, "temperature": 0.0, "chat_template_kwargs": NO_THINK}
        t0 = time.time()
        try:
            r = requests.post(url, json=body, timeout=a.stress_timeout)
            j = r.json()
            res[i] = {"s": time.time() - t0, "status": r.status_code, "prompt_tokens": (j.get("usage") or {}).get("prompt_tokens"),
                      "error": str(j.get("error") or "")[:120]}
        except Exception as e:
            res[i] = {"s": time.time() - t0, "status": "EXC", "prompt_tokens": None, "error": str(e)[:120]}

    cal = requests.post(url, json={"model": a.model, "messages": [{"role": "user", "content": _stress_prompt(999, 200)}],
                                   "max_tokens": 1, "chat_template_kwargs": NO_THINK}, timeout=600).json()
    paras = int(a.stress_tokens / (cal["usage"]["prompt_tokens"] / 200))
    peak, stop = {}, threading.Event()

    def sample():
        while not stop.is_set():
            for g in gpustat.read_gpus()[0]:
                peak[g["index"]] = max(peak.get(g["index"], 0), g["vram_used_b"])
            stop.wait(2)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    pre0 = _metric(a, "vllm:num_preemptions_total")
    res, t0 = {}, time.time()
    threads = [threading.Thread(target=call, args=(i, paras, res)) for i in range(a.stress_n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    wall = time.time() - t0
    stop.set()
    pre1 = _metric(a, "vllm:num_preemptions_total")
    ok = sum(1 for v in res.values() if v["status"] == 200)
    return {"n": a.stress_n, "ok": ok, "target_tokens": a.stress_tokens, "wall_s": wall,
            "total_prompt_tokens": sum(v["prompt_tokens"] or 0 for v in res.values()),
            "preemptions": None if pre0 is None or pre1 is None else pre1 - pre0,
            "peak_vram_gib_per_gpu": {k: round(v / 1024 ** 3, 2) for k, v in sorted(peak.items())},
            "requests": [res[i] for i in sorted(res)]}


# ── quality ─────────────────────────────────────────────────────────────────────

def stage_quality(a, out):
    runner = os.path.join(HERE, "codetests", "run_codetests.py")
    for name, tasks, samples in (("quality-hard", HARD_TASKS, a.quality_samples), ("quality-common", COMMON_TASKS, 2)):
        cmd = [sys.executable, runner, "run", "--url", f"{a.base}/v1/chat/completions", "--model", a.model,
               "--modes", "think", "--reasoning-effort", "medium", "--samples", str(samples),
               "--max-tokens", str(a.quality_max_tokens), "--timeout", "7200", "--parallel", str(a.quality_parallel),
               "--tasks", tasks, "--out", os.path.join(out, name)]
        with open(os.path.join(out, name + ".log"), "w") as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    return None


RUNNERS = {"env": stage_env, "speed": stage_speed, "depth": stage_depth, "tools": stage_tools,
           "stress": stage_stress, "quality": stage_quality}
DONE_FILE = {"env": "env.json", "speed": "speed.json", "depth": "depth.json", "tools": "tools.json",
             "stress": "stress.json", "quality": "quality-common/summary.json"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8080", help="router base URL, no /v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True, help="free text recorded in env.json, e.g. 'v0.26.0 ROCm 7.2.3'")
    ap.add_argument("--container", help="backend container name, to record image and ROCm/vLLM/torch versions")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stages", default=",".join(STAGES))
    ap.add_argument("--force", action="store_true", help="redo stages whose output already exists")
    ap.add_argument("--depths", type=lambda s: [int(x) for x in s.split(",")], default="1000,8000,32000,64000,128000,200000")
    ap.add_argument("--stress-n", type=int, default=7)
    ap.add_argument("--stress-tokens", type=int, default=100000)
    ap.add_argument("--stress-timeout", type=int, default=3600)
    ap.add_argument("--quality-samples", type=int, default=8)
    ap.add_argument("--quality-max-tokens", type=int, default=81920)
    ap.add_argument("--quality-parallel", type=int, default=8)
    a = ap.parse_args()
    if isinstance(a.depths, str):
        a.depths = [int(x) for x in a.depths.split(",")]
    os.makedirs(a.out, exist_ok=True)
    for st in a.stages.split(","):
        done = os.path.join(a.out, DONE_FILE[st])
        if os.path.exists(done) and not a.force:
            print(f"[{st}] already done, skipping", flush=True)
            continue
        print(f"[{st}] start {time.strftime('%H:%M:%S')}", flush=True)
        t0 = time.time()
        result = RUNNERS[st](a, a.out)
        if result is not None:
            with open(os.path.join(a.out, f"{st}.json"), "w") as f:
                json.dump(result, f, indent=1)
        print(f"[{st}] done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
