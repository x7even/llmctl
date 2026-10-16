#!/usr/bin/env python3
"""Compare canary_suite.py result directories. The first directory is the baseline; deltas are against it.

  python3 bench/canary_compare.py bench/results/canary-x/27b-s0 bench/results/canary-x/27b-s1 [...] [--md out.md]

Prints markdown tables (environment, speed, depth, tools, stress, quality) and a gate verdict for every
candidate. Gates (docs/rocm10-canary-plan.md section 6):
  throughput  medium-256 decode tok/s at serial, conc=8 and conc=16 no worse than -5%
  quality     hard tasks: mean tests passed no more than QUALITY_NOISE points below the baseline,
              and early stops (empty/cut) no more than baseline + 2
  tools       no fewer tool-call passes than the baseline, and at least 14 of 16
  stress      every request finished (7 of 7)
  depth       decode tok/s at every depth no worse than -10%
"""
import json
import os
import sys

THROUGHPUT_FLOOR = -5.0
DEPTH_FLOOR = -10.0
QUALITY_NOISE = 10.0  # points at 8 samples per task (15 at 4)
HARD = ["regex_engine", "mini_scheme", "json_strict", "date_math", "cron_next"]


def load(d, name):
    p = os.path.join(d, name)
    return json.load(open(p)) if os.path.exists(p) else None


def pct(new, old):
    return None if not old or new is None else (new - old) / old * 100.0


def fmt(v, nd=1):
    return "-" if v is None else f"{v:.{nd}f}"


def fmt_d(v):
    return "" if v is None else f" ({v:+.1f}%)"


def quality(d):
    """task -> dict(n, mean_pct, full, early, truncated) from the hard and common summaries."""
    out = {}
    for sub in ("quality-hard", "quality-common"):
        s = load(d, os.path.join(sub, "summary.json"))
        for r in (s or {}).get("rows", []):
            if "passed" not in r:
                continue
            t = out.setdefault(r["task"], {"n": 0, "pct": 0.0, "full": 0, "early": 0, "trunc": 0})
            t["n"] += 1
            t["pct"] += 100.0 * r["passed"] / max(r["total"], 1)
            t["full"] += bool(r.get("full_pass"))
            t["early"] += bool(r.get("early_stop"))
            t["trunc"] += r.get("finish") == "length"
    for t in out.values():
        t["pct"] /= max(t["n"], 1)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    md_out = sys.argv[sys.argv.index("--md") + 1] if "--md" in sys.argv else None
    if md_out and md_out in args:
        args.remove(md_out)
    dirs = args
    if len(dirs) < 2:
        sys.exit(__doc__)
    names = [os.path.basename(d.rstrip("/")) for d in dirs]
    lines = []

    def emit(s=""):
        lines.append(s)

    # environment
    emit("### Environment\n")
    emit("| field | " + " | ".join(names) + " |")
    emit("|---|" + "---|" * len(dirs))
    envs = [load(d, "env.json") or {} for d in dirs]
    for k in ("label", "image", "container_rocm", "container_python", "kernel", "amdgpu_driver", "host_rocm"):
        emit(f"| {k} | " + " | ".join(str(e.get(k, "-")).replace("|", "/") for e in envs) + " |")

    # speed
    speeds = [load(d, "speed.json") for d in dirs]
    verdicts = {n: [] for n in names[1:]}
    if all(speeds):
        emit("\n### Speed: decode tok/s (all prompts, no-thinking, 32 requests per level)\n")
        emit("| cell | " + " | ".join(names) + " |")
        emit("|---|" + "---|" * len(dirs))
        keyed = [{(r["label"], r["concurrency"]): r for r in s["rows"]} for s in speeds]
        for key in keyed[0]:
            cells = []
            for i, k in enumerate(keyed):
                r = k.get(key)
                v = r["decode_tps"] if r else None
                cells.append(fmt(v) + (fmt_d(pct(v, keyed[0][key]["decode_tps"])) if i else ""))
            emit(f"| {key[0]} (c={key[1]}) | " + " | ".join(cells) + " |")
        for i, n in enumerate(names[1:], 1):
            for key, r0 in keyed[0].items():
                if key[0].startswith("medium-256") and key[1] in (1, 8, 16) and key in keyed[i]:
                    d = pct(keyed[i][key]["decode_tps"], r0["decode_tps"])
                    if d is not None and d < THROUGHPUT_FLOOR:
                        verdicts[n].append(f"throughput {key[0]} c={key[1]} {d:+.1f}% < {THROUGHPUT_FLOOR}%")

    # depth
    depths = [load(d, "depth.json") for d in dirs]
    if all(depths):
        emit("\n### Decode speed vs context depth (tok/s) and prefill (tok/s)\n")
        emit("| depth | " + " | ".join(f"{n} decode / prefill" for n in names) + " |")
        emit("|---|" + "---|" * len(dirs))
        base = {r["target"]: r for r in depths[0]["rows"]}
        for tgt, r0 in base.items():
            cells = []
            for i, dp in enumerate(depths):
                r = next((x for x in dp["rows"] if x["target"] == tgt), {})
                v = r.get("decode_tps")
                cells.append(f"{fmt(v)}{fmt_d(pct(v, r0.get('decode_tps'))) if i else ''} / {fmt(r.get('prefill_tps'), 0)}"
                             + (" ERR" if r.get("error") else ""))
                if i and v is not None and r0.get("decode_tps"):
                    d = pct(v, r0["decode_tps"])
                    if d < DEPTH_FLOOR:
                        verdicts[names[i]].append(f"depth {tgt} decode {d:+.1f}% < {DEPTH_FLOOR}%")
                elif i and r.get("error") and not r0.get("error"):
                    verdicts[names[i]].append(f"depth {tgt} errored")
            emit(f"| {tgt} | " + " | ".join(cells) + " |")

    # tools
    tools = [load(d, "tools.json") for d in dirs]
    if all(tools):
        emit("\n### Tool calls\n")
        emit("| | " + " | ".join(names) + " |\n|---|" + "---|" * len(dirs))
        emit("| passed | " + " | ".join(f"{t['passed']}/{t['total']}" for t in tools) + " |")
        for i, t in enumerate(tools[1:], 1):
            if t["passed"] < tools[0]["passed"] or t["passed"] < 14:
                verdicts[names[i]].append(f"tools {t['passed']}/{t['total']} (baseline {tools[0]['passed']})")

    # stress
    stress = [load(d, "stress.json") for d in dirs]
    if all(stress):
        emit("\n### Long-context stress (7 x ~100K concurrent)\n")
        emit("| | " + " | ".join(names) + " |\n|---|" + "---|" * len(dirs))
        emit("| finished | " + " | ".join(f"{s['ok']}/{s['n']}" for s in stress) + " |")
        emit("| wall s | " + " | ".join(fmt(s["wall_s"], 0) for s in stress) + " |")
        emit("| preemptions | " + " | ".join(str(s["preemptions"]) for s in stress) + " |")
        emit("| peak VRAM GiB (max card) | " + " | ".join(
            fmt(max(s["peak_vram_gib_per_gpu"].values(), default=None), 2) for s in stress) + " |")
        for i, s in enumerate(stress[1:], 1):
            if s["ok"] < s["n"]:
                verdicts[names[i]].append(f"stress {s['ok']}/{s['n']} finished")

    # quality
    quals = [quality(d) for d in dirs]
    if all(quals):
        emit("\n### Quality: mean tests passed % (full passes / samples, early stops, truncated)\n")
        emit("| task | " + " | ".join(names) + " |\n|---|" + "---|" * len(dirs))
        for task in sorted(set().union(*quals), key=lambda t: (t not in HARD, t)):
            cells = []
            for i, q in enumerate(quals):
                t = q.get(task)
                if not t:
                    cells.append("-")
                    continue
                dpts = t["pct"] - quals[0][task]["pct"] if i and task in quals[0] else None
                cells.append(f"{t['pct']:.0f}%{'' if dpts is None else f' ({dpts:+.0f})'} "
                             f"({t['full']}/{t['n']}, e{t['early']}, t{t['trunc']})")
                if i and dpts is not None and task in HARD and dpts < -QUALITY_NOISE:
                    verdicts[names[i]].append(f"quality {task} {dpts:+.0f} points")
            emit(f"| {task} | " + " | ".join(cells) + " |")
        hard_early = [sum(q[t]["early"] for t in HARD if t in q) for q in quals]
        emit("| hard-task early stops | " + " | ".join(str(e) for e in hard_early) + " |")
        for i, e in enumerate(hard_early[1:], 1):
            if e > hard_early[0] + 2:
                verdicts[names[i]].append(f"early stops {e} vs baseline {hard_early[0]}")

    emit("\n### Gate verdict (baseline: " + names[0] + ")\n")
    for n in names[1:]:
        emit(f"- **{n}**: " + ("PASS" if not verdicts[n] else "FAIL - " + "; ".join(verdicts[n])))
    text = "\n".join(lines)
    print(text)
    if md_out:
        open(md_out, "w").write(text + "\n")


if __name__ == "__main__":
    main()
