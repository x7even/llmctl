#!/usr/bin/env python3
"""
Code-generation tests: ask a served model to implement each task in tasks/*/prompt.md,
extract the code, and grade it against the hidden tests in tasks/*/tests.py.

  # prove the hidden tests are correct (reference solutions must score 100%)
  python3 bench/codetests/run_codetests.py validate

  # generate + grade
  python3 bench/codetests/run_codetests.py run \
      --url http://127.0.0.1:8081/v1/chat/completions --model qwen3.8-27b-code \
      --samples 4 --modes think,nothink --out bench/codetests/results/qwen3.8-27b-code

  # re-grade previously saved solutions without calling a model
  python3 bench/codetests/run_codetests.py regrade --out bench/codetests/results/qwen3.8-27b-code

Each sample's raw API response, extracted solution and per-test results are saved so every
score can be audited. Tests run in a subprocess with a hard timeout and a 10 s per-test alarm.
"""
import argparse, json, os, re, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
TASKS_DIR = HERE / "tasks"
TEMPERATURE = 0.6
TOP_P = 0.95
MAX_TOKENS = 24000
REASONING_EFFORT = None  # think mode only; Qwen3.8 template default is xhigh

WORKER = r'''
import importlib.util, json, signal, sys, traceback
sol_path, tests_path = sys.argv[1], sys.argv[2]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

class Timeout(Exception):
    pass

def on_alarm(*_):
    raise Timeout("test timed out (10s)")

signal.signal(signal.SIGALRM, on_alarm)
tests = load("hidden_tests", tests_path)
try:
    signal.alarm(10)
    sol = load("solution", sol_path)
    signal.alarm(0)
except BaseException as e:
    print(json.dumps({"fatal": f"import failed: {type(e).__name__}: {e}"}), flush=True)
    sys.exit(0)

for t in tests.TESTS:
    name = t.__name__
    try:
        signal.alarm(10)
        t(sol)
        signal.alarm(0)
        print(json.dumps({"test": name, "ok": True}), flush=True)
    except BaseException as e:
        signal.alarm(0)
        msg = f"{type(e).__name__}: {e}"[:300]
        print(json.dumps({"test": name, "ok": False, "err": msg}), flush=True)
'''


def task_names():
    return sorted(p.name for p in TASKS_DIR.iterdir() if (p / "prompt.md").exists())


def test_names(task):
    src = (TASKS_DIR / task / "tests.py").read_text()
    m = re.search(r"^TESTS\s*=\s*\[(.*?)\]", src, re.S | re.M)
    return [n.strip() for n in m.group(1).split(",") if n.strip()]


def grade(task, solution_path, timeout=120):
    """Run hidden tests against a solution file. Returns dict with per-test results."""
    names = test_names(task)
    with tempfile.TemporaryDirectory() as td:
        try:
            p = subprocess.run(
                [sys.executable, "-c", WORKER, str(solution_path), str(TASKS_DIR / task / "tests.py")],
                capture_output=True, text=True, timeout=timeout, cwd=td,
            )
            out, stderr = p.stdout, p.stderr
            timed_out = False
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr, timed_out = "", True
    results, fatal = {}, None
    for line in out.splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        if "fatal" in d:
            fatal = d["fatal"]
        elif "test" in d:
            results[d["test"]] = d
    for n in names:
        results.setdefault(n, {"test": n, "ok": False, "err": fatal or ("harness timeout" if timed_out else "not run (process died)")})
    passed = sum(1 for n in names if results[n]["ok"])
    return {"passed": passed, "total": len(names), "fatal": fatal, "timed_out": timed_out,
            "stderr_tail": stderr[-500:], "tests": [results[n] for n in names]}


FENCE = re.compile(r"```[ \t]*(?:python|py|python3)?[ \t]*\n(.*?)```", re.S | re.I)


def extract_code(text):
    """Pick the longest fenced code block; fall back to an unterminated fence, then raw text."""
    if not text:
        return ""
    blocks = FENCE.findall(text)
    if blocks:
        return max(blocks, key=len)
    m = re.search(r"```[ \t]*(?:python|py|python3)?[ \t]*\n(.*)$", text, re.S | re.I)
    return m.group(1) if m else text


def call_model(url, model, prompt, mode, max_tokens, timeout=3600):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
    }
    if mode == "nothink":
        body["chat_template_kwargs"] = {"enable_thinking": False}
    elif REASONING_EFFORT:
        body["chat_template_kwargs"] = {"reasoning_effort": REASONING_EFFORT}
    t0 = time.perf_counter()
    r = requests.post(url, json=body, timeout=timeout)
    r.raise_for_status()
    d = r.json()
    d["_wall_s"] = time.perf_counter() - t0
    return d


def run_sample(args, task, mode, k):
    d = Path(args.out) / task / f"{mode}-s{k}"
    d.mkdir(parents=True, exist_ok=True)
    prompt = (TASKS_DIR / task / "prompt.md").read_text()
    try:
        resp = call_model(args.url, args.model, prompt, mode, args.max_tokens, timeout=args.timeout)
    except Exception as e:
        (d / "error.txt").write_text(str(e))
        return {"task": task, "mode": mode, "sample": k, "error": str(e)}
    (d / "raw.json").write_text(json.dumps(resp, indent=1))
    msg = resp["choices"][0]["message"]
    content = msg.get("content") or ""
    code = extract_code(content)
    (d / "solution.py").write_text(code)
    return grade_saved(d, task, mode, k, resp)


def grade_saved(d, task, mode, k, resp=None):
    if resp is None:
        resp = json.loads((d / "raw.json").read_text())
    g = grade(task, d / "solution.py")
    (d / "result.json").write_text(json.dumps(g, indent=1))
    msg = resp["choices"][0]["message"]
    u = resp.get("usage", {})
    return {
        "task": task, "mode": mode, "sample": k,
        "passed": g["passed"], "total": g["total"], "full_pass": g["passed"] == g["total"],
        "fatal": g["fatal"], "finish": resp["choices"][0].get("finish_reason"),
        "completion_tokens": u.get("completion_tokens"), "wall_s": round(resp.get("_wall_s", 0), 1),
        "reasoning_chars": len(msg.get("reasoning") or msg.get("reasoning_content") or ""),
        "failed_tests": [t["test"] for t in g["tests"] if not t["ok"]],
    }


def summarize(rows, out, model):
    ok = [r for r in rows if "error" not in r]
    lines = [f"# Code test results — {model}", "", f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')}  "
             f"(temperature {TEMPERATURE}, top_p {TOP_P}, max_tokens {MAX_TOKENS}, "
             f"reasoning_effort {REASONING_EFFORT or 'template default'})", "",
             "| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |",
             "|---|---|---|---|---|---|---|---|"]
    for task in sorted({r["task"] for r in ok}):
        for mode in sorted({r["mode"] for r in ok if r["task"] == task}):
            g = [r for r in ok if r["task"] == task and r["mode"] == mode]
            n = len(g)
            frac = sum(r["passed"] / r["total"] for r in g) / n
            toks = [r["completion_tokens"] for r in g if r["completion_tokens"]]
            lines.append(
                f"| {task} | {mode} | {n} | {sum(r['full_pass'] for r in g)}/{n} | {frac * 100:.1f}% | "
                f"{(sum(toks) / len(toks)) if toks else 0:.0f} | {sum(r['finish'] == 'length' for r in g)} | "
                f"{sum(bool(r['fatal']) for r in g)} |")
    errs = [r for r in rows if "error" in r]
    if errs:
        lines += ["", f"**{len(errs)} request errors** (not counted above):"] + [f"- {r['task']}/{r['mode']}-s{r['sample']}: {r['error'][:150]}" for r in errs]
    lines += ["", "## Per-sample failures", ""]
    for r in sorted(ok, key=lambda r: (r["task"], r["mode"], r["sample"])):
        if r["failed_tests"]:
            lines.append(f"- {r['task']}/{r['mode']}-s{r['sample']} ({r['passed']}/{r['total']}): " + ", ".join(r["failed_tests"]))
    (Path(out) / "summary.md").write_text("\n".join(lines) + "\n")
    (Path(out) / "summary.json").write_text(json.dumps({"model": model, "rows": rows}, indent=1))
    print("\n".join(lines))


def cmd_validate(_):
    bad = 0
    for t in task_names():
        g = grade(t, TASKS_DIR / t / "reference.py")
        status = "OK " if g["passed"] == g["total"] else "FAIL"
        print(f"{status} {t}: reference passes {g['passed']}/{g['total']}")
        for x in g["tests"]:
            if not x["ok"]:
                print(f"     - {x['test']}: {x.get('err')}")
        bad += g["passed"] != g["total"]
    # negative control: a solution that does nothing must fail
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write("pass\n")
    for t in task_names():
        g = grade(t, f.name)
        print(f"negative control {t}: empty solution passes {g['passed']}/{g['total']}")
    os.unlink(f.name)
    return bad


def cmd_run(args):
    global MAX_TOKENS, REASONING_EFFORT
    MAX_TOKENS = args.max_tokens  # recorded in summary.md; was always the 24000 default
    REASONING_EFFORT = args.reasoning_effort
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    names = [t for t in task_names() if not args.tasks or t in args.tasks.split(",")]
    jobs = [(t, m, k) for t in names for m in args.modes.split(",") for k in range(args.samples)]
    rows = []
    print(f"{len(jobs)} generations -> {out}", flush=True)
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futs = {pool.submit(run_sample, args, *j): j for j in jobs}
        for f in as_completed(futs):
            r = f.result()
            rows.append(r)
            if "error" in r:
                print(f"  {r['task']}/{r['mode']}-s{r['sample']}: ERROR {r['error'][:100]}", flush=True)
            else:
                print(f"  {r['task']}/{r['mode']}-s{r['sample']}: {r['passed']}/{r['total']} "
                      f"tok={r['completion_tokens']} finish={r['finish']} {r['wall_s']}s", flush=True)
    summarize(rows, out, args.model)


def cmd_regrade(args):
    out = Path(args.out)
    rows = []
    for d in sorted(out.glob("*/*-s*")):
        if not (d / "raw.json").exists():
            continue
        task, (mode, k) = d.parent.name, d.name.rsplit("-s", 1)
        resp = json.loads((d / "raw.json").read_text())
        (d / "solution.py").write_text(extract_code(resp["choices"][0]["message"].get("content") or ""))
        rows.append(grade_saved(d, task, mode, int(k), resp))
    prev = json.loads((out / "summary.json").read_text()) if (out / "summary.json").exists() else {}
    summarize(rows, out, prev.get("model", out.name))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    r = sub.add_parser("run")
    r.add_argument("--url", default="http://127.0.0.1:8081/v1/chat/completions")
    r.add_argument("--model", required=True)
    r.add_argument("--samples", type=int, default=4)
    r.add_argument("--modes", default="think,nothink", help="comma list of think,nothink")
    r.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    r.add_argument("--parallel", type=int, default=8)
    r.add_argument("--reasoning-effort", default=None, choices=["low", "medium", "xhigh"],
                   help="think-mode reasoning_effort chat-template kwarg (default: template default, xhigh)")
    r.add_argument("--tasks", default="", help="comma list of task names (default: all)")
    r.add_argument("--timeout", type=int, default=3600,
                   help="per-request read timeout in seconds; a 64k-token thinking sample can take over an hour")
    r.add_argument("--out", required=True)
    g = sub.add_parser("regrade")
    g.add_argument("--out", required=True)
    args = ap.parse_args()
    if getattr(args, "out", None):
        args.out = str(Path(args.out).resolve())  # grader runs in a temp cwd; a relative path would not be found
    sys.exit({"validate": cmd_validate, "run": cmd_run, "regrade": cmd_regrade}[args.cmd](args) or 0)


if __name__ == "__main__":
    main()
