"""Dump EVERY measured cell -- prefill, decode and concurrency together -- as one
table, plus a CSV, with nothing summarised away.

Three rules this enforces, each because getting them wrong would mislead:

1. Cold and prewarmed cells are tagged and never averaged together. A prewarmed
   cell's prefill figure is prefix-cache reuse, not compute, so prefill is
   printed as "cached" there rather than as a rate.
2. `prefill_tok_s` is a WHOLE-BATCH rate: batch prompt tokens / max(ttft). It is
   not a per-stream speed and it is not comparable to decode tok/s.
3. `agg tok/s` is a run average over the decode span -- from the first stream's
   first token to the last stream's last token. At high concurrency that window
   includes the staggered ramp-in, so it reads BELOW the steady-state rate a live
   sampler shows. The two are different measurements of different things.
"""
import argparse
import csv
import glob
import json
import getpass
import os
import pathlib
import re
import socket
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--baselines", default=str(REPO / "bench" / "baselines"),
                help="directory holding depth/*.json and the legacy sweeps")
ap.add_argument("--out-dir", default=str(REPO / "docs"),
                help="where benchmark-results-full.{md,csv} are written")
A = ap.parse_args()
B = A.baselines

rows = []
seen = {}
for f in sorted(glob.glob(os.path.join(B, "depth", "*.json"))):
    try:
        d = json.loads(open(f).read())
    except Exception as e:
        print("skip (unreadable, still being written?): %s  %s"
              % (os.path.basename(f), e), file=sys.stderr)
        continue
    model = d["model"]
    warm = bool(d.get("prewarm"))
    for r in d.get("rows") or []:
        key = (model, warm, r["depth_requested"], r["concurrency"])
        if key in seen and seen[key] != os.path.basename(f):
            sys.exit("refusing: %s supplied by both %s and %s -- glob order "
                     "would decide which figure gets published"
                     % (key, seen[key], os.path.basename(f)))
        seen[key] = os.path.basename(f)
        rows.append({
            "model": model,
            "regime": "prewarmed" if warm else "cold",
            "depth": r["depth_requested"],
            "prompt_tokens": r.get("prompt_tokens"),
            "conc": r["concurrency"],
            "ok": r.get("ok"),
            "requested": r.get("requested"),
            "gen_tokens": r.get("completion_tokens"),
            "ttft_mean_s": r.get("ttft_s_mean"),
            "ttft_p90_s": r.get("ttft_s_p90"),
            "prefill_batch_tok_s": None if warm else r.get("prefill_tok_s"),
            "decode_per_stream_tok_s": r.get("per_stream_tok_s_mean"),
            "decode_agg_tok_s": r.get("agg_decode_tok_s"),
            "accepted_per_step": r.get("accepted_per_step"),
            "e2e_max_s": r.get("e2e_s_max"),
            "live": r.get("live"),
            "src": os.path.basename(f),
        })

rows.sort(key=lambda r: (r["model"], r["regime"], r["depth"], r["conc"]))

out = ["# Complete benchmark results: prefill, decode and concurrency",
       "",
       "Every measured cell. Output pinned at 1,024 tokens with `ignore_eos`, so",
       "the latency columns compare speeds and not answer lengths. 4x R9700",
       "(gfx1201), vLLM 0.26.0 except Flash-Next (nightly).",
       "",
       "## How to read the three throughput columns",
       "",
       "They measure different things and are not interchangeable:",
       "",
       "- **prefill (batch)** -- the batch's prompt tokens divided by the slowest",
       "  stream's TTFT. A whole-batch rate, not a per-stream speed. Blank for",
       "  prewarmed rows, where the prompt is served from the prefix cache and the",
       "  figure would measure cache reuse rather than compute.",
       "- **decode/stream** -- what one client sees: mean per-stream decode rate.",
       "- **decode agg** -- all streams summed, averaged over the whole decode span",
       "  (first stream's first token to last stream's last token). At high",
       "  concurrency that span includes the staggered ramp-in while most streams",
       "  are still prefilling, so this reads **below** the steady-state rate a live",
       "  sampler such as `llmpanel` reports. Neither is wrong; they answer",
       "  different questions -- this one answers \"how long will the batch take\".",
       "",
       "`ok` is completed/requested. A cell below full completion keeps its figures",
       "only where a majority finished; the loss cause is in the saved JSON.",
       ""]


def fmt(v, nd=1):
    return "--" if v is None else ("%.*f" % (nd, v))


for model in sorted({r["model"] for r in rows}):
    out += ["## `%s`" % model, ""]
    for regime in ("cold", "prewarmed"):
        sub = [r for r in rows if r["model"] == model and r["regime"] == regime]
        if not sub:
            continue
        out += ["### %s" % regime, "",
                "| depth | prompt tok | conc | ok | TTFT mean s | TTFT p90 s "
                "| prefill (batch) tok/s | decode/stream tok/s | decode agg tok/s "
                "| acc/step |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for r in sub:
            oks = "%d/%d" % (r["ok"], r["requested"])
            if r["ok"] != r["requested"]:
                oks = "**%s** !" % oks
            out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                r["depth"], r["prompt_tokens"], r["conc"], oks,
                fmt(r["ttft_mean_s"]), fmt(r["ttft_p90_s"]),
                "cached" if r["regime"] == "prewarmed"
                else fmt(r["prefill_batch_tok_s"], 0),
                fmt(r["decode_per_stream_tok_s"]),
                "**%s**" % fmt(r["decode_agg_tok_s"]),
                fmt(r["accepted_per_step"], 2)))
        out.append("")

live_rows = [r for r in rows if r.get("live")
             and ((r["live"].get("decode_tok_s_saturated")
                   or r["live"].get("decode_tok_s_all")))]
if live_rows:
    out += ["## Steady-state decode distributions", "",
            "Cells run with the in-benchmark sampler attached to vLLM's",
            "`/metrics`. The percentiles are over the one-second samples taken",
            "while the server was within 10% of its high-water running-request",
            "count -- i.e. the plateau, with ramp-in and drain excluded. Ticks",
            "that emitted no tokens at all are excluded and counted separately:",
            "the requests were admitted and running, but the engine spent that",
            "whole second on a prefill chunk.", "",
            "Read **median** as what the hardware sustains, **p10** as the floor",
            "a slow second hits, and **run avg** as how long a batch of this",
            "shape takes. The **low** is a sampling-boundary artifact -- a tick",
            "can straddle a transition and catch a single token -- so quote the",
            "p10, not the low. Convention: nearest-rank, round-half-up, no",
            "interpolation, matching `RingBuffer.ActiveStats` in the TUI.", "",
            "| profile | depth | conc | run avg | low | p10 | median | p90 | "
            "peak | peak/med | med/run avg | n | zero-decode ticks |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(live_rows, key=lambda r: (r["model"], r["depth"], r["conc"])):
        L = r["live"]
        d = L.get("decode_tok_s_saturated") or L.get("decode_tok_s_all")
        agg = r["decode_agg_tok_s"]
        nz = L.get("n_zero_decode_ticks_in_band")
        nb = L.get("n_samples_in_band")
        flag = "" if d.get("percentiles_meaningful") else " !"
        out.append("| `%s` | %s | %s | %s | %s | %s | **%s** | %s | %s | %s | "
                   "%s | %d%s | %s |" % (
                       r["model"], r["depth"], r["conc"], fmt(agg),
                       fmt(d["min"]), fmt(d["p10"]), fmt(d["p50"]),
                       fmt(d["p90"]), fmt(d["max"]),
                       fmt(d["max"] / d["p50"], 2) if d["p50"] else "--",
                       fmt(d["p50"] / agg, 2) if agg else "--",
                       d["n"], flag,
                       "--" if nz is None else "%d/%d" % (nz, nb)))
    out += ["",
            "`!` on the sample count means fewer than 10 samples, where \"p10\"",
            "and \"p90\" are just the minimum and the maximum.",
            "",
            "Where **p10 exceeds the run average** -- both conc=32 rows -- that",
            "is not an inconsistency. The p10 is over plateau samples only; the",
            "run average also pays for the ramp, which is where the slow seconds",
            "are. That difference is the `med/run avg` column, and it is a",
            "property of the shape rather than of the hardware: it is 1.31x on",
            "the 35B at 32 streams and 1.57x on the 27B at the same shape.",
            ""]

md = "\n".join(out)

# Nothing below spells out an identifier. Writing them into a deny list
# publishes them in the file that carries the list -- with a label attached,
# which is worse than the bare string. They are derived from the machine this
# runs on instead, which also makes the check correct in someone else's clone:
# their user and host get caught, not the ones this was written on.
#
# Extra patterns can be supplied out of band via LLMSTACK_SCRUB_PATTERNS
# (newline-separated regexes, one per line) for anything site-specific. A
# secret does not belong in a deny list in a public file.
BAD = [(r"/home/(?!alice\b)[a-z]", "absolute home path"),
       (r"\b0000:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]\b", "PCI address"),
       (r"\b\d{2}:\d{2}:\d{2}\b", "wall-clock timestamp")]
for ident, why in ((getpass.getuser(), "username"),
                   (socket.gethostname().split(".")[0], "hostname"),
                   (str(pathlib.Path.home()), "home directory")):
    if ident and len(ident) > 2:
        BAD.append((r"\b%s\b" % re.escape(ident), why))
for extra in (os.environ.get("LLMSTACK_SCRUB_PATTERNS") or "").splitlines():
    if extra.strip():
        BAD.append((extra.strip(), "site pattern"))

for pat, why in BAD:
    m = re.search(pat, md)
    if m:
        # The match itself is not echoed: printing it would put the identifier
        # on a terminal and into whatever log is capturing it.
        sys.exit("refusing to write: output contains a %s" % why)

T = A.out_dir
os.makedirs(T, exist_ok=True)
open(os.path.join(T, "benchmark-results-full.md"), "w").write(md + "\n")

cols = ["model", "regime", "depth", "prompt_tokens", "conc", "ok", "requested",
        "gen_tokens", "ttft_mean_s", "ttft_p90_s", "prefill_batch_tok_s",
        "decode_per_stream_tok_s", "decode_agg_tok_s", "accepted_per_step",
        "e2e_max_s", "sat_low_tok_s", "sat_p10_tok_s", "sat_p50_tok_s",
        "sat_p90_tok_s", "sat_peak_tok_s", "sat_n_samples",
        "sat_zero_decode_ticks", "src"]
for r in rows:
    L = r.get("live") or {}
    d = L.get("decode_tok_s_saturated") or L.get("decode_tok_s_all") or {}
    r["sat_low_tok_s"] = d.get("min")
    r["sat_p10_tok_s"] = d.get("p10")
    r["sat_p50_tok_s"] = d.get("p50")
    r["sat_p90_tok_s"] = d.get("p90")
    r["sat_peak_tok_s"] = d.get("max")
    r["sat_n_samples"] = d.get("n")
    r["sat_zero_decode_ticks"] = L.get("n_zero_decode_ticks_in_band")
with open(os.path.join(T, "benchmark-results-full.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in cols})

print("%d cells, %d profiles" % (rows.__len__(),
                                 len({r['model'] for r in rows})))
for model in sorted({r["model"] for r in rows}):
    sub = [r for r in rows if r["model"] == model]
    print("  %-26s %2d cells  peak agg %.1f" % (
        model, len(sub), max(r["decode_agg_tok_s"] or 0 for r in sub)))
