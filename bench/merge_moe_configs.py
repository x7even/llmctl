#!/usr/bin/env python3
"""Merge per-GPU partial tuning JSONs into a single config file.

Usage:
  python3 bench/merge_moe_configs.py \
    --inputs vllm-tuned-configs/E=64,...json \
             vllm-tuned-configs/gpu0/E=64,...json \
             vllm-tuned-configs/gpu1/E=64,...json \
             vllm-tuned-configs/gpu2/E=64,...json \
             vllm-tuned-configs/gpu3/E=64,...json \
    --output vllm-tuned-configs/E=64,...json
"""

import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True,
                        help="JSON files to merge (later files override earlier on key conflict)")
    parser.add_argument("--output", required=True,
                        help="Output file path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print merged result without writing")
    args = parser.parse_args()

    merged = {}
    triton_version = None
    for path in args.inputs:
        if not os.path.exists(path):
            print(f"Warning: {path} not found, skipping", file=sys.stderr)
            continue
        with open(path) as f:
            data = json.load(f)
        tv = data.pop("triton_version", None)
        if tv:
            triton_version = tv
        before = len(merged)
        merged.update(data)
        print(f"  {path}: {len(data)} batch sizes → total {len(merged)} (+{len(merged)-before})")

    if not merged:
        print("Error: no data loaded", file=sys.stderr)
        sys.exit(1)

    batch_sizes = sorted(int(k) for k in merged)
    print(f"Merged batch sizes: {batch_sizes}")

    payload = {"triton_version": triton_version, **{str(k): merged[str(k)] for k in batch_sizes}}

    if args.dry_run:
        print(json.dumps(payload, indent=4))
    else:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(payload, f, indent=4)
            f.write("\n")
        print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
