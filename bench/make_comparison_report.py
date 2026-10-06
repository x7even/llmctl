#!/usr/bin/env python3
"""
Build the markdown tables for the Qwen3.6-27B vs Qwen3.8-27B comparison straight from the
saved result files (no numbers are typed by hand).

  python3 bench/make_comparison_report.py --tag 20261005 > bench/results/comparison-20261005/tables.md

Inputs (written by bench/run_comparison.py):
  bench/baselines/<model>-v0.26.0-nothink-<tag>.json                     concurrent_bench
  bench/baselines/<model>-v0.26.0-concurrency-sweep-nothink-<tag>.json   concurrency_sweep
  bench/results/comparison-<tag>/snapshot-<model>-<label>.json                MTP counters
  bench/results/comparison-<tag>/codetests/<model>/                           code-test outputs
"""
import argparse, json, re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
A, B = "qwen3.6-27b-code", "qwen3.8-27b-code"
NAMES = {A: "Qwen3.6-27B", B: "Qwen3.8-27B"}
VER = "v0.26.0"
LEN_FLAG = 0.10  # flag a level when mean completion tokens differ by more than this


def load(p):
    return json.loads(Path(p).read_text())


def pct(a, b):
    return (b - a) / a * 100 if a else float("nan")


def bench_rows(model, tag):
    d = load(REPO / "bench" / "baselines" / f"{model}-{VER}-nothink-{tag}.json")
    out = {}
    for r in d["rows"]:
        if "serial" in r["label"]:
            continue  # 3-request warm-up, not part of the 32-request levels
        prompt = r["label"].split()[0]
        r = dict(r)
        r["mean_out"] = r["decode_tps"] * r["wall_s"] / r["n_requests"]  # total completion tokens / requests
        out[(prompt, r["concurrency"])] = r
    return out


def section_concurrent(tag):
    a, b = bench_rows(A, tag), bench_rows(B, tag)
    prompts = []
    for k in a:
        if k[0] not in prompts:
            prompts.append(k[0])
    L = ["## Concurrent bench (decode tok/s, 32 requests per level, `--no-thinking`)", "",
         "`out` = mean completion tokens per request. A `⚠` marks levels where the two models' mean output length "
         f"differs by more than {LEN_FLAG:.0%}: tok/s is still comparable there, latency and wall time are not.", ""]
    for p in prompts:
        L += [f"### {p}", "",
              f"| conc | {NAMES[A]} tok/s | {NAMES[B]} tok/s | Δ tok/s | {NAMES[A]} out | {NAMES[B]} out | "
              f"{NAMES[A]} p90 lat (s) | {NAMES[B]} p90 lat (s) | errors |",
              "|---|---|---|---|---|---|---|---|---|"]
        for (pp, c), ra in a.items():
            if pp != p or (pp, c) not in b:
                continue
            rb = b[(pp, c)]
            flag = " ⚠" if abs(rb["mean_out"] - ra["mean_out"]) / ra["mean_out"] > LEN_FLAG else ""
            L.append(f"| {c} | {ra['decode_tps']:.1f} | {rb['decode_tps']:.1f} | {pct(ra['decode_tps'], rb['decode_tps']):+.1f}% | "
                     f"{ra['mean_out']:.0f} | {rb['mean_out']:.0f}{flag} | {ra['latency_p90']:.1f} | {rb['latency_p90']:.1f} | "
                     f"{ra['errors']}/{rb['errors']} |")
        L.append("")
    return L


def section_sweep(tag):
    a = {r["concurrency"]: r for r in load(REPO / "bench/baselines" / f"{A}-{VER}-concurrency-sweep-nothink-{tag}.json")["rows"]}
    b = {r["concurrency"]: r for r in load(REPO / "bench/baselines" / f"{B}-{VER}-concurrency-sweep-nothink-{tag}.json")["rows"]}
    L = ["## Wide concurrency sweep (1000-token code prompt, 1000-token outputs)", "",
         "The profile caps `--max-num-seqs` at 32, so levels above 32 queue.", "",
         f"| conc | requests | {NAMES[A]} aggregate tok/s | {NAMES[B]} aggregate tok/s | Δ | "
         f"{NAMES[A]} per-agent | {NAMES[B]} per-agent | {NAMES[A]} mean out | {NAMES[B]} mean out | errors |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for c in sorted(a):
        if c not in b:
            continue
        ra, rb = a[c], b[c]
        flag = " ⚠" if abs(rb["mean_completion"] - ra["mean_completion"]) / ra["mean_completion"] > LEN_FLAG else ""
        L.append(f"| {c} | {ra['n_requests']} | {ra['aggregate_tps']:.1f} | {rb['aggregate_tps']:.1f} | "
                 f"{pct(ra['aggregate_tps'], rb['aggregate_tps']):+.1f}% | {ra['per_agent_tps']:.1f} | {rb['per_agent_tps']:.1f} | "
                 f"{ra['mean_completion']:.0f} | {rb['mean_completion']:.0f}{flag} | {ra['errors']}/{rb['errors']} |")
    L.append("")
    return L


def mtp_deltas(model, out):
    steps = ["start", "after-concurrent_bench", "after-concurrency_sweep", "end"]
    snaps = []
    for s in steps:
        p = out / f"snapshot-{model}-{s}.json"
        snaps.append(load(p)["mtp"] if p.exists() else None)
    rows = []
    for i, name in enumerate(["concurrent bench", "wide sweep", "code tests"]):
        x, y = snaps[i], snaps[i + 1]
        if not x or not y or None in (x.get("drafts"), y.get("drafts")):
            rows.append((name, None))
            continue
        dd, da, dr = (y["draft_tokens"] - x["draft_tokens"], y["accepted_tokens"] - x["accepted_tokens"], y["drafts"] - x["drafts"])
        rows.append((name, (da / dd * 100 if dd else float("nan"), da / dr if dr else float("nan"), dd)))
    return rows


def section_mtp(out):
    L = ["## MTP speculative-decoding acceptance (vLLM counters, 2 draft tokens per step)", "",
         "Deltas between driver snapshots, so each row covers only that phase. Counters reset when the container restarts.", "",
         "| phase | model | draft tokens | accepted / drafted | mean accepted per step (max 2) |", "|---|---|---|---|---|"]
    for name in ["concurrent bench", "wide sweep", "code tests"]:
        for m in (A, B):
            r = dict(mtp_deltas(m, out)).get(name)
            if r:
                L.append(f"| {name} | {NAMES[m]} | {r[2]:.0f} | {r[0]:.1f}% | {r[1]:.2f} |")
            else:
                L.append(f"| {name} | {NAMES[m]} | n/a | n/a | n/a |")
    L.append("")
    return L


def section_codetests(out):
    L = ["## Code tests", "",
         "Temperature 0.6, top_p 0.95, `max_tokens` 24000, 4 samples per task and mode. A sample that is cut off at the token "
         "limit has no code to grade, so it is counted as **truncated**, not as a wrong answer.", "",
         "| task | mode | model | samples | full passes | graded samples | mean tests passed (graded only) | truncated | mean completion tok |",
         "|---|---|---|---|---|---|---|---|---|"]
    per_test = defaultdict(Counter)
    detail = []
    for m in (A, B):
        sp = out / "codetests" / m / "summary.json"
        if not sp.exists():
            continue
        rows = [r for r in load(sp)["rows"] if "error" not in r]
        for task in sorted({r["task"] for r in rows}):
            for mode in sorted({r["mode"] for r in rows if r["task"] == task}, reverse=True):
                g = [r for r in rows if r["task"] == task and r["mode"] == mode]
                graded = [r for r in g if r["finish"] != "length"]
                trunc = len(g) - len(graded)
                frac = (sum(r["passed"] / r["total"] for r in graded) / len(graded) * 100) if graded else float("nan")
                toks = [r["completion_tokens"] for r in g if r["completion_tokens"]]
                L.append(f"| {task} | {mode} | {NAMES[m]} | {len(g)} | {sum(r['full_pass'] for r in g)}/{len(g)} | {len(graded)} | "
                         f"{'n/a' if not graded else f'{frac:.1f}%'} | {trunc} | {sum(toks) / len(toks):.0f} |")
                for r in graded:
                    for t in r["failed_tests"]:
                        per_test[(m, task)][t] += 1
                for r in sorted(g, key=lambda r: r["sample"]):
                    detail.append(f"| {task} | {mode}-s{r['sample']} | {NAMES[m]} | {r['passed']}/{r['total']} | {r['finish']} | "
                                  f"{r['completion_tokens']} | {', '.join(r['failed_tests']) if r['finish'] != 'length' else '(truncated, not graded)'} |")
    L += ["", "### Which tests failed (graded samples only)", ""]
    for (m, task), c in sorted(per_test.items()):
        if c:
            L.append(f"- {NAMES[m]} / {task}: " + ", ".join(f"`{t}` ×{n}" for t, n in c.most_common()))
    L += ["", "### Every sample", "", "| task | sample | model | passed | finish | completion tok | failed tests |", "|---|---|---|---|---|---|---|"] + detail
    L.append("")
    return L


def section_conditions(tag, out):
    L = ["## Run conditions (from the driver snapshots)", ""]
    for m in (A, B):
        for lab in ("start", "end"):
            p = out / f"snapshot-{m}-{lab}.json"
            if not p.exists():
                continue
            s = load(p)
            L.append(f"- {NAMES[m]} {lab} ({s['time']}): containers = `{s['containers'].replace(chr(10), '; ')}`; "
                     f":8080 running = `{s['live_8080_running'].strip()}`")
    L.append("")
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    out = REPO / "bench" / "results" / f"comparison-{args.tag}"
    lines = []
    for sec in (lambda: section_concurrent(args.tag), lambda: section_sweep(args.tag), lambda: section_mtp(out),
                lambda: section_codetests(out), lambda: section_conditions(args.tag, out)):
        lines += sec()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
