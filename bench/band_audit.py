#!/usr/bin/env python3
"""Flag stored baselines that were recorded in the slow gfx1201 decode band.

A server's decode band is drawn when it spawns (docs/rdna4-decode-bands.md), and
`-e GPU_MAX_HW_QUEUES=1` -- the fix -- did not ship until 2026-10-18. Every
baseline taken before that was a stock spawn, i.e. a draw that on this hardware
landed slow every time it was checked. So part of the stored corpus records the
slow band, and figures copied out of it into docs understate the hardware by up
to ~2x at one stream.

The band has a shape, and that is what makes it identifiable after the fact: the
penalty is a fixed per-step tax, so it is largest at one stream and shrinks as
the batch widens. On the 27B that curve is 1.89x serial, 1.76x at conc=2, 1.11x
at conc=8; on the 35B MoE it is 2.87x serial and still 2.07x at conc=8. Because
the magnitude varies that much by model, the test here is not "is conc=8 under
some constant" -- that would have called the 35B's real band draw clean -- but
"does the ratio decay as the batch widens". A loss that is as large at conc=8 as
at one stream is not a per-step tax and is something else.

What the shape does NOT do is name the cause. Any fixed per-step overhead draws
the same curve, and at least one other known to this stack does: vLLM 0.31.0's
Model Runner V2 costs ~45% at one stream and nothing by conc=2-4
(docs/upgrade-plan-2026-10.md), which is why the 0.31.0 files here match. The
verdict is therefore PER-STEP, with the band as the first thing to check and
provenance as the thing that settles it.

Heuristic, not proof: the server is gone and cannot be re-probed. Treat a flag
as "do not quote this file as hardware capability until it is re-measured", and
read the file's provenance before changing any doc that cites it. Files are only
ever compared within one profile and one image pin, so a version regression
across pins is never reported.

Usage:
  python3 bench/band_audit.py                 # audit bench/baselines/
  python3 bench/band_audit.py --dir <path>
  python3 bench/band_audit.py --quiet         # only files needing attention
Exit: 0 if nothing needs attention, 1 if anything does.
"""
import argparse
import glob
import json
import os
import re
import sys

# A one-stream ratio this large is not run-to-run noise: two 0.26.0 controls run
# 8 h apart agree within 1.2% on every cell (docs/upgrade-plan-2026-10.md), so
# 1.30x is ~25x the noise floor. An earlier 1.55x let the 0.31.0
# concurrency-sweep file through at 1.52x as "ok" when its one-stream loss is
# the known Model Runner V2 regression.
SLOW_AT_ONE_STREAM = 1.30
# The conc=8 ratio must be this fraction of the one-stream ratio or less for the
# loss to count as amortising. Measured: 1.11/1.89 = 0.59 on the 27B dense,
# 2.07/2.87 = 0.72 on the 35B MoE. A uniform loss sits at ~1.0.
AMORTISATION = 0.85


def levels(path):
    """medium-256 decode tok/s by concurrency level, from one baseline file."""
    with open(path) as fh:
        doc = json.load(fh)
    out = {}
    for row in doc.get("rows", []):
        label = row.get("label", "")
        if not label.startswith("medium-256"):
            continue
        if row.get("decode_tps") is None:
            continue
        key = label.replace("medium-256", "").strip() or "serial"
        out[key] = row["decode_tps"]
    return doc.get("model"), doc.get("timestamp"), out


def comparable(name):
    """Only no-thinking baselines may be compared with each other.

    Thinking inflates tok/s because the reasoning block counts as output, so a
    thinking-on file is a different measurement, not a faster one. Skipping this
    check compared the 2026-10 no-thinking 35B sweep against
    `qwen3.6-35b-code.json` -- the 2026-05 thinking-on file that bench/CLAUDE.md
    names as the root cause of the misleading "485 tok/s" benchmark -- and
    reported a 2.2x shortfall that was entirely the thinking block.

    Gemma 4 keeps a thinking-on baseline on purpose (bench/CLAUDE.md), so an
    unmarked file is excluded rather than assumed.
    """
    return "nothink" in name or "no-thinking" in name


def pin(name):
    """The image pin a filename claims. Comparing across pins would report a
    version regression as a band draw."""
    found = re.search(r"v(\d+\.\d+\.\d+)", name)
    return found.group(1) if found else "unpinned"


def fastest_at(files, model, want_pin, level):
    """Fastest stored reading for this profile and pin at one level."""
    vals = [lv[level] for name, (m, _, lv) in files.items()
            if m == model and pin(name) == want_pin and level in lv]
    return max(vals) if vals else None


def one_stream(lv):
    """conc=1 is the n=32 reading; serial is the same cell at small n."""
    return lv.get("conc=1") or lv.get("serial")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(here, "baselines"))
    ap.add_argument("--quiet", action="store_true",
                    help="print only files that need attention")
    args = ap.parse_args()

    files = {}
    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        model, timestamp, lv = levels(path)
        name = os.path.basename(path)
        if lv and model and comparable(name):
            files[name] = (model, timestamp, lv)
        elif lv and model and not args.quiet:
            print("%-54s %-10s  not marked no-thinking -- excluded"
                  % (name[:54], str(timestamp)[:10]))
    if not files:
        sys.exit("no medium-256 baselines found in %s" % args.dir)

    # The reference is the fastest one-stream reading for the same profile on the
    # same pin. Nothing can be said about a profile with only one reading.
    best = {}
    for name, (model, _, lv) in files.items():
        value = one_stream(lv)
        if value is None:
            continue
        key = (model, pin(name))
        if value > best.get(key, (0, None))[0]:
            best[key] = (value, name)

    flagged, unpaired, checked = [], [], 0
    for name in sorted(files):
        model, timestamp, lv = files[name]
        ref, refname = best.get((model, pin(name)), (None, None))
        value = one_stream(lv)

        if ref is None or value is None or refname == name:
            if refname == name:
                # A group of one has no reference. Say so, rather than letting
                # "the reference" read as a clean bill of health: the files that
                # feed the published tables are mostly in this category.
                peers = sum(1 for n, (m, _, _) in files.items()
                            if m == model and pin(n) == pin(name))
                role = ("fastest of %d on pin %s -- the reference" % (peers, pin(name))
                        if peers > 1 else
                        "ONLY reading for this profile on pin %s -- unaudited"
                        % pin(name))
                if peers == 1:
                    unpaired.append(name)
            else:
                role = "no no-thinking peer on pin %s" % pin(name)
                unpaired.append(name)
            if not args.quiet:
                print("%-54s %-10s  %s" % (name[:54], str(timestamp)[:10], role))
            continue

        checked += 1
        ratio_one = ref / value
        c8 = lv.get("conc=8")
        ratio_c8 = fastest_at(files, model, pin(name), "conc=8") / c8 if c8 else None

        if ratio_one < SLOW_AT_ONE_STREAM:
            verdict = "ok (%.2fx of fastest)" % ratio_one
        elif ratio_c8 is None:
            verdict = ("SLOW AT ONE STREAM %.2fx, no conc=8 cell to test the "
                       "curve against" % ratio_one)
            flagged.append(name)
        elif ratio_c8 <= AMORTISATION * ratio_one:
            verdict = ("PER-STEP  %.2fx one-stream -> %.2fx conc=8, amortising "
                       "-- slow band, or another fixed per-step cost"
                       % (ratio_one, ratio_c8))
            flagged.append(name)
        else:
            verdict = ("slower at every level (%.2fx one-stream, %.2fx conc=8) "
                       "-- not a per-step cost, read its provenance"
                       % (ratio_one, ratio_c8))
            flagged.append(name)

        if not args.quiet or ratio_one >= SLOW_AT_ONE_STREAM:
            print("%-54s %-10s  %s" % (name[:54], str(timestamp)[:10], verdict))

    print("\n%d file(s) had a same-profile same-pin reference to compare "
          "against; %d need attention" % (checked, len(flagged)))
    if flagged:
        print("Do not quote a flagged file as hardware capability. Re-measure "
              "with `-e GPU_MAX_HW_QUEUES=1` set on the profile.")
    if unpaired:
        # Not a failure, but it is why coverage is partial: a file whose name
        # omits the image pin cannot be paired with one that carries it, so it
        # can never be audited. bench/CLAUDE.md asks for the pin in the name.
        print("\n%d file(s) had no comparable peer, so nothing can be said "
              "about them. The usual cause is a filename without an image pin "
              "(`<profile>-v<pin>-nothink-<date>.json`):" % len(unpaired))
        for name in unpaired:
            print("  %s" % name)
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
