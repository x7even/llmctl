#!/usr/bin/env python3
"""
Back-to-back benchmark of several profiles through ONE llama-swap instance, under identical
conditions (same vLLM image, same scripts/flags), plus code tests.

For each profile, in order:
  1. record running containers and MTP counters; load the model; verify no-thinking works
  2. snapshot MTP counters
  3. bench/concurrent_bench.py   (sweep 1,2,4,8,16 x all prompt sizes, --no-thinking, 32 req/level)
  4. bench/concurrency_sweep.py  (wide sweep 1..64, 1000-token code prompt)
  5. bench/codetests/run_codetests.py  (2 graded tasks, think + nothink)
  6. snapshot MTP counters + GPU state again

  python3 bench/run_comparison.py --tag 20261005 --models qwen3.8-27b-code,qwen3.6-27b-code
  python3 bench/run_comparison.py --quick ...     # dry run: tiny settings, same code path

Progress: <out>/status.json and <out>/driver.log.  Re-running skips steps whose output exists.
"""
import argparse, json, re, subprocess, sys, time, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8081"
URL = BASE + "/v1/chat/completions"
VLLM_VER = "v0.26.0"


def sh(cmd, check=False):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return (p.stdout + p.stderr).strip()


def http_json(url, body=None, timeout=60):
    req = urllib.request.Request(url, json.dumps(body).encode() if body else None, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


class Driver:
    def __init__(self, out, quick):
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.quick = quick
        self.t0 = time.time()
        self.log_f = open(self.out / "driver.log", "a")

    def log(self, msg):
        line = f"[{time.strftime('%H:%M:%S')} +{(time.time() - self.t0) / 60:5.1f}m] {msg}"
        print(line, flush=True)
        self.log_f.write(line + "\n")
        self.log_f.flush()

    def status(self, **kw):
        (self.out / "status.json").write_text(json.dumps({"updated": time.strftime("%H:%M:%S"), **kw}, indent=1))

    def snapshot(self, label, model):
        """Containers, live router contents, MTP counters."""
        snap = {"label": label, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "containers": sh("podman ps --format '{{.Names}} {{.Status}}'"),
                "live_8080_running": sh("curl -s -m 3 localhost:8080/running | head -c 300"),
                "mtp": self.mtp()}
        (self.out / f"snapshot-{model}-{label}.json").write_text(json.dumps(snap, indent=1))
        self.log(f"snapshot {label}: containers=[{snap['containers'].replace(chr(10), '; ')}] mtp={snap['mtp']}")
        return snap

    def mtp(self):
        try:
            proxy = http_json(BASE + "/running")["running"][0]["proxy"]
            text = urllib.request.urlopen(proxy + "/metrics", timeout=10).read().decode()
        except Exception as e:
            return {"error": str(e)}
        def val(name):
            m = re.search(rf"^vllm:{name}\{{[^}}]*\}}\s+([0-9.e+]+)", text, re.M)
            return float(m.group(1)) if m else None
        d, a, dr = val("spec_decode_num_draft_tokens_total"), val("spec_decode_num_accepted_tokens_total"), val("spec_decode_num_drafts_total")
        return {"draft_tokens": d, "accepted_tokens": a, "drafts": dr}

    def load(self, model):
        self.log(f"loading {model} (llama-swap swaps containers; cold start ~3 min)")
        t = time.time()
        http_json(URL, {"model": model, "max_tokens": 5, "messages": [{"role": "user", "content": "Say: ready"}]}, timeout=2400)
        self.log(f"{model} ready after {time.time() - t:.0f}s")

    def check_thinking(self, model):
        r = {}
        for label, kw in (("default", {}), ("enable_thinking=false", {"chat_template_kwargs": {"enable_thinking": False}})):
            m = http_json(URL, {"model": model, "max_tokens": 300, "temperature": 0.6, "messages":
                                [{"role": "user", "content": "Write a Python function to reverse a linked list."}], **kw},
                          timeout=600)["choices"][0]["message"]
            r[label] = {"reasoning_chars": len(m.get("reasoning") or ""), "content_chars": len(m.get("content") or "")}
        self.log(f"thinking check: {r}")
        if r["enable_thinking=false"]["reasoning_chars"] != 0:
            raise SystemExit(f"{model}: enable_thinking=false did NOT suppress reasoning - benchmark would be invalid")
        (self.out / f"thinking-check-{model}.json").write_text(json.dumps(r, indent=1))

    def run(self, name, cmd, marker):
        """Run a step unless its marker output already exists; stream to a per-step log."""
        if Path(marker).exists():
            self.log(f"SKIP {name} (exists: {marker})")
            return
        self.log(f"START {name}: {cmd}")
        self.status(step=name)
        t = time.time()
        with open(self.out / f"{name}.log", "w") as f:
            p = subprocess.run(cmd, shell=True, stdout=f, stderr=subprocess.STDOUT, cwd=REPO)
        self.log(f"END   {name}: rc={p.returncode} in {(time.time() - t) / 60:.1f}m")
        if p.returncode != 0:
            self.log(f"!! {name} failed - see {self.out / (name + '.log')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    ap.add_argument("--tag", required=True, help="date tag used in baseline filenames, e.g. 20261005")
    ap.add_argument("--out", default=None)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    out = args.out or str(REPO / "bench" / "results" / (f"dryrun-{args.tag}" if args.quick else f"comparison-{args.tag}"))
    d = Driver(out, args.quick)
    bdir = Path(out) / "baselines" if args.quick else REPO / "bench" / "baselines"
    bdir.mkdir(parents=True, exist_ok=True)
    d.log(f"output dir {out}; quick={args.quick}")

    for model in args.models.split(","):
        stem = f"{model}-{VLLM_VER}-nothink-{args.tag}"
        d.status(model=model, step="load")
        d.snapshot("pre-load", model)
        d.load(model)
        d.check_thinking(model)
        d.snapshot("start", model)

        if args.quick:
            cb = "--sweep 1,2 --prompt short-64 --requests 4 --serial-n 1"
            cs = "--levels 1,4 --requests 4 --max-tokens 100"
            ct = "--samples 1 --modes nothink --max-tokens 4000"
        else:
            cb = "--sweep 1,2,4,8,16 --prompt all --requests 32"
            cs = ""
            ct = "--samples 4 --modes think,nothink"

        d.run(f"{model}-concurrent_bench",
              f"python3 bench/concurrent_bench.py --url {URL} --model {model} --no-thinking {cb} "
              f"--save {bdir}/{stem}.json --csv {bdir}/{stem}.csv", f"{bdir}/{stem}.json")
        d.snapshot("after-concurrent_bench", model)
        d.run(f"{model}-concurrency_sweep",
              f"python3 bench/concurrency_sweep.py --url {URL} --model {model} {cs} "
              f"--save {bdir}/{stem.replace('-nothink', '-concurrency-sweep-nothink')}.json",
              f"{bdir}/{stem.replace('-nothink', '-concurrency-sweep-nothink')}.json")
        d.snapshot("after-concurrency_sweep", model)
        res = Path(out) / "codetests" / model
        d.run(f"{model}-codetests",
              f"python3 bench/codetests/run_codetests.py run --url {URL} --model {model} {ct} --out {res}",
              str(res / "summary.json"))
        d.snapshot("end", model)
        d.log(f"=== {model} complete ===")

    d.status(step="ALL DONE")
    d.log("ALL DONE")


if __name__ == "__main__":
    main()
