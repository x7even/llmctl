#!/usr/bin/env python3
"""
llmstack long-context retrieval check ("needle in a haystack")

Why this exists separately from depth_bench.py. depth_bench measures how *fast*
the stack decodes at depth; it sends filler text with ignore_eos and never looks
at what came back. That is exactly the blind spot that matters when an attention
backend or kernel changes: a split-KV decode kernel that combines its softmax
segments incorrectly loses information from whole stretches of the context and
still benchmarks perfectly. Speed at depth is worthless if the model can no
longer see the depth.

The test plants a unique code in a long filler body, asks for it back, and
grades on exact substring. It sweeps the needle's *position* as well as the
depth, because position is the discriminator for this bug class: vLLM's
TRITON_ATTN 3D path splits the context into NUM_PAR_SOFTMAX_SEGMENTS (16)
segments and reduces across them, so a needle at 30% depth and one at 70% land
in different segments. A uniform failure means retrieval is broken; failures
clustered at particular positions mean the segment reduction is.

Usage:
  python3 bench/needle_check.py --model qwen3.8-27b-think \
      --depths 16384,65536,131072 --positions 0.05,0.25,0.5,0.75,0.95

Exit status is 0 only if every cell retrieved its needle.
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from depth_bench import calibrate, filler, server_max_model_len

DEFAULT_URL = os.environ.get("LLMSTACK_URL",
                             "http://127.0.0.1:8080/v1/chat/completions")

# Words of non-filler text in a needle prompt: the instruction preamble, the
# question, and the needle sentence itself. Subtracted when sizing the filler so
# a cell lands on the depth it was asked for. depth_bench's WRAPPER_WORDS is not
# reused because this prompt is longer and carries the needle too.
NEEDLE_WRAPPER_WORDS = 110

# Headroom on the clamp. Larger than depth_bench's DEPTH_MARGIN for the same
# reason: measured overshoot was 65 tokens at 131K, which put the deepest cell
# exactly one token over max_model_len and cost the whole row.
NEEDLE_MARGIN = 256

# Distinct vault names keep each cell's question unambiguous even if some other
# cell's needle leaks into the context through a cache.
VAULTS = ("Aldebaran Borealis Cinnabar Dovetail Everest Fathom Gallant Harrow "
          "Icarus Juniper Kestrel Lantern Meridian Nocturne Obsidian Perihelion "
          "Quarry Riptide Solstice Tanager Umbral Vantage Windlass Xenolith "
          "Yarrow Zephyr").split()


def make_code(rng):
    """A code with no English words in it, so it cannot be guessed from context."""
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"   # no I/O, unambiguous
    return "%s%s%s-%04d-%s%s%s" % (
        rng.choice(letters), rng.choice(letters), rng.choice(letters),
        rng.randint(1000, 9999),
        rng.choice(letters), rng.choice(letters), rng.choice(letters))


def build_needle_messages(depth_words, position, seed):
    """Filler of depth_words words with one needle sentence at `position`."""
    rng = random.Random(seed)
    vault = rng.choice(VAULTS)
    code = make_code(rng)
    needle = ("The secret access code for vault %s is %s. "
              "Remember it; you will be asked for it later. " % (vault, code))

    words = filler(depth_words, seed).split()
    at = min(len(words), max(0, int(len(words) * position)))
    body = " ".join(words[:at]) + " " + needle + " " + " ".join(words[at:])

    user = (
        "Below is a long transcript fragment. Somewhere inside it is a sentence "
        "giving a secret access code for a vault. Read the whole fragment.\n\n"
        "--- BEGIN FRAGMENT ---\n" + body + "\n--- END FRAGMENT ---\n\n"
        "Question: what is the secret access code for vault %s? "
        "Reply with the code only, nothing else." % vault
    )
    return [{"role": "user", "content": user}], code, vault


def ask(url, model, messages, timeout, no_thinking, headers, max_tokens):
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": False,
    }
    if no_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    try:
        r = requests.post(url, json=payload, timeout=timeout, headers=headers)
    except Exception as exc:
        return None, None, "request failed: %s" % exc
    if r.status_code != 200:
        return None, None, "HTTP %d: %s" % (r.status_code, r.text[:200])
    obj = r.json()
    choice = (obj.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    return text, (obj.get("usage") or {}).get("prompt_tokens"), None


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--model", required=True)
    p.add_argument("--depths", default="16384,65536,131072")
    p.add_argument("--positions", default="0.05,0.25,0.5,0.75,0.95",
                   help="fraction of the way through the filler to plant the needle")
    p.add_argument("--max-model-len", type=int, default=None,
                   help="clamp depths; needed through llama-swap, which does not "
                        "report max_model_len")
    p.add_argument("--max-tokens", type=int, default=64)
    p.add_argument("--timeout", type=float, default=900)
    p.add_argument("--no-thinking", action="store_true")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--label", default="")
    p.add_argument("--save", default=None)
    args = p.parse_args()

    headers = {}
    if os.environ.get("LLMSTACK_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["LLMSTACK_API_KEY"]

    depths = sorted({int(x) for x in args.depths.split(",") if x.strip()})
    positions = [float(x) for x in args.positions.split(",") if x.strip()]

    print("model      : %s" % args.model)
    print("url        : %s" % args.url)
    if args.label:
        print("label      : %s" % args.label)

    print("calibrating words-per-token ... ", end="", flush=True)
    cal = calibrate(args.url, args.model, args.timeout, args.no_thinking, headers)
    if cal is None:
        print("FAILED -- server did not report prompt_tokens")
        return 2
    wpt, probe_tokens = cal
    print("%.3f words/token (4000-word probe = %d prompt tokens)" % (wpt, probe_tokens))

    mml = args.max_model_len or server_max_model_len(args.url, args.model,
                                                     headers, args.timeout)
    if mml:
        cap = mml - args.max_tokens - NEEDLE_MARGIN
        clamped = [min(d, cap) for d in depths]
        if clamped != depths:
            print("clamping to %d:  %s -> %s" % (cap, depths, clamped))
        depths = sorted(set(clamped))
    else:
        print("warning: max_model_len unknown; depths unclamped "
              "-- pass --max-model-len to enable the clamp")
    print()

    hdr = "%11s %10s %9s %8s  %-22s %s" % ("depth(req)", "depth(act)", "position",
                                           "result", "expected", "got")
    print(hdr)
    print("-" * len(hdr))

    rows = []
    misses = 0
    seed = args.seed
    for depth in depths:
        depth_words = max(1, int(depth * wpt) - NEEDLE_WRAPPER_WORDS)
        for pos in positions:
            seed += 1
            msgs, code, vault = build_needle_messages(depth_words, pos, seed)
            text, ptok, err = ask(args.url, args.model, msgs, args.timeout,
                                  args.no_thinking, headers, args.max_tokens)
            if err:
                print("%11d %10s %9.2f %8s  %-22s %s"
                      % (depth, "-", pos, "ERROR", code, err))
                rows.append({"depth": depth, "position": pos, "code": code,
                             "error": err, "hit": False})
                misses += 1
                continue
            hit = code in (text or "")
            if not hit:
                misses += 1
            got = " ".join((text or "").split())[:40] or "(empty)"
            print("%11d %10s %9.2f %8s  %-22s %s"
                  % (depth, ptok if ptok else "?", pos,
                     "ok" if hit else "MISS", code, got))
            rows.append({"depth": depth, "depth_actual": ptok, "position": pos,
                         "vault": vault, "code": code, "response": text,
                         "hit": hit})

    total = len(rows)
    print()
    print("retrieved %d/%d" % (total - misses, total))

    if args.save:
        with open(args.save, "w") as fh:
            json.dump({"model": args.model, "url": args.url, "label": args.label,
                       "words_per_token": wpt, "retrieved": total - misses,
                       "total": total, "rows": rows}, fh, indent=2)
        print("saved: %s" % args.save)

    return 0 if misses == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
