#!/usr/bin/env python3
"""Throwaway llama-swap router for canaries: one shipped profile, a different image, nothing shared.

Derives the config from config/models.yaml so every flag (cudagraph sizes, utilisation, parser, llm-prestart)
is identical to the shipped profile; only these change:
  - the vLLM image (--image)
  - the container name gets a suffix (--suffix), so the production container is never replaced or stopped
  - the vLLM and triton cache mounts point under --cache-dir (a cold, separate cache; true cold-start time)
  - the router listens on --port (default 8099) and backends start at --start-port (default 9300)

  python3 bench/canary_router.py up   --profile qwen3.8-27b-code --image docker.io/vllm/vllm-openai-rocm:nightly-rocm100-<sha> \\
      --suffix rocm100 --cache-dir ~/.claude/jobs/<job>/tmp/cache-rocm100
  python3 bench/canary_router.py down --suffix rocm100
  python3 bench/canary_router.py config --profile ... --image ...        # print the config only

Production must be unloaded first (llmctl unload): the profiles use the same GPUs.
"""
import argparse
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_RE = re.compile(r"docker\.io/vllm/vllm-openai-rocm:\S+")


def build_config(profile, image, suffix, cache_dir, start_port, keep_logs=False):
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "models.yaml")))
    m = dict(cfg["models"][profile])
    cmd, stop = m["cmd"], m.get("cmdStop", "")
    if not IMAGE_RE.search(cmd):
        sys.exit(f"{profile}: no vLLM image in cmd (only vLLM profiles are supported)")
    cmd = IMAGE_RE.sub(image, cmd)
    cmd = cmd.replace("--name llmstack-vllm-${MODEL_ID}", f"--name llmstack-vllm-${{MODEL_ID}}-{suffix}")
    stop = stop.replace("llmstack-vllm-${MODEL_ID}", f"llmstack-vllm-${{MODEL_ID}}-{suffix}")
    vllm_c, triton_c = os.path.join(cache_dir, "vllm"), os.path.join(cache_dir, "triton")
    os.makedirs(vllm_c, exist_ok=True)
    os.makedirs(triton_c, exist_ok=True)
    cmd, n1 = re.subn(r"-v \S+/\.vllm-cache:/root/\.cache/vllm", f"-v {vllm_c}:/root/.cache/vllm", cmd)
    cmd, n2 = re.subn(r"-v \S+/\.triton-cache:/root/\.triton/cache", f"-v {triton_c}:/root/.triton/cache", cmd)
    if n1 != 1 or n2 != 1:
        sys.exit(f"{profile}: expected one vllm and one triton cache mount, found {n1}/{n2}")
    if keep_logs:  # an exited container keeps its log for `podman logs` (down removes it)
        cmd = cmd.replace("podman run --replace --rm", "podman run --replace", 1)
    m.update(cmd=cmd, cmdStop=stop, aliases=[], ttl=0)
    m.pop("metadata", None)
    return {"healthCheckTimeout": cfg["healthCheckTimeout"], "startPort": start_port, "globalTTL": 0,
            "models": {profile: m}}


def pidfile(port):
    return os.path.expanduser(f"~/.local/share/llmstack/canary-router-{port}.pid")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["up", "down", "config"])
    ap.add_argument("--profile")
    ap.add_argument("--image")
    ap.add_argument("--suffix", default="canary")
    ap.add_argument("--cache-dir")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--start-port", type=int, default=9300)
    ap.add_argument("--keep-logs", action="store_true", help="drop --rm so a crashed container's log survives")
    ap.add_argument("--config-out", help="where to write the config (default: <cache-dir>/router.yaml)")
    a = ap.parse_args()

    if a.action == "down":
        try:
            pid = int(open(pidfile(a.port)).read())
            os.kill(pid, signal.SIGTERM)
            print(f"stopped router pid {pid}")
        except (OSError, ValueError):
            print("no router pid file")
        subprocess.run(["bash", "-c", f"podman ps -q --filter name=-{a.suffix}$ | xargs -r podman stop; podman ps -aq --filter name=-{a.suffix}$ | xargs -r podman rm -f"], check=False)
        return

    if not (a.profile and a.image and a.cache_dir):
        sys.exit("--profile, --image and --cache-dir are required")
    cfg = build_config(a.profile, a.image, a.suffix, os.path.expanduser(a.cache_dir), a.start_port, a.keep_logs)
    text = yaml.safe_dump(cfg, sort_keys=False, width=10_000)
    if a.action == "config":
        print(text)
        return
    path = a.config_out or os.path.join(os.path.expanduser(a.cache_dir), "router.yaml")
    open(path, "w").write(text)
    os.makedirs(os.path.dirname(pidfile(a.port)), exist_ok=True)
    log = open(os.path.join(os.path.expanduser(a.cache_dir), "router.log"), "a")
    proc = subprocess.Popen([os.path.expanduser("~/.local/bin/llama-swap"), "--config", path,
                             "--listen", f"127.0.0.1:{a.port}"],
                            stdout=log, stderr=log, start_new_session=True)
    open(pidfile(a.port), "w").write(str(proc.pid))
    for _ in range(40):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{a.port}/v1/models", timeout=2)
            print(f"router ready on :{a.port} (pid {proc.pid}), config {path}")
            return
        except OSError:
            pass
    sys.exit("router did not come up; see router.log")


if __name__ == "__main__":
    main()
