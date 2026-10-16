#!/usr/bin/env python3
"""
Hardware detection and per-profile requirement checks (stdlib only).

Single implementation shared by scripts/configure and (next) bin/llmctl:

    detect(...)            -> {gpu_count, vram_gib_per_gpu, host_ram_gib, source, ...}
    parse_requires(text)   -> {profile: requires_dict} from config/models.yaml
    supports(req, hw)      -> (ok, tp_or_split, reasons)

Every profile in config/models.yaml carries

    metadata:
      requires:
        gpus: [2, 4]        # vLLM: allowed GPU counts (valid tensor-parallel sizes)
        min_gpus: 3         # llama-server: works on any count >= N (exclusive with gpus)
        host_ram_gib: 96    # optional: system RAM needed
        vram_total_gib: 66  # optional, informational
        estimate: true      # numbers not measured on this rig
        note: "short human reason"

and this module is the single reader of that block. Unknown (no block) means
permissive: the profile is assumed to fit.

GPU detection counts only discrete GPUs with >= 8 GiB of VRAM (sysfs
mem_info_vram_total), so an integrated GPU is ignored. Falls back to amd-smi (then
rocm-smi) only when sysfs exposes no VRAM information at all.

CLI:
    python3 scripts/llmhw.py [--json] [--gpu-count N]
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

GIB = 1024**3
MIN_GPU_VRAM_BYTES = 8 * GIB  # smaller devices are iGPUs / display adapters
RAM_TOLERANCE = 0.92          # a "96 GB" box reports ~94 GiB MemTotal
DEFAULT_DRM_ROOT = Path("/sys/class/drm")


# ── GPU detection (pure, injectable) ────────────────────────────────────────

def sysfs_vram_sizes(drm_root: Path = DEFAULT_DRM_ROOT) -> list[int] | None:
    """VRAM bytes of every distinct device under a DRM sysfs root.

    Returns None when no device exposes mem_info_vram_total at all, so the
    caller can fall back to another method. Connector entries (card0-DP-1)
    are ignored; devices are de-duplicated by the resolved path of their
    `device` link.
    """
    seen: set[Path] = set()
    sizes: list[int] = []
    found_any = False
    for card in sorted(Path(drm_root).glob("card*")):
        if not re.fullmatch(r"card\d+", card.name):
            continue
        dev = card / "device"
        try:
            real = dev.resolve()
            vram = int((dev / "mem_info_vram_total").read_text().strip())
        except (OSError, ValueError):
            continue
        found_any = True
        if real in seen:
            continue
        seen.add(real)
        sizes.append(vram)
    return sizes if found_any else None


def _run_cmd(argv: list[str]) -> str:
    return subprocess.check_output(argv, stderr=subprocess.DEVNULL, text=True)


def smi_vram_sizes(run=None) -> tuple[list[int | None] | None, str]:
    """(VRAM bytes per GPU, tool) via amd-smi, else rocm-smi; `run(argv) -> str` is injectable.

    scripts/gpustat.py does the amd-smi-first parsing. When neither tool reports sizes this falls back to
    `rocm-smi --listdevices` (unique GPU[n] indices, sizes unknown -> None entries). (None, "none") when
    nothing answers.
    """
    run = run or _run_cmd
    gpustat = _load_gpustat()
    if gpustat is not None:
        gpus, tool = gpustat.read_gpus(run)
        if gpus:
            return [g["vram_total_b"] for g in gpus], tool
    try:
        out = run(["rocm-smi", "--listdevices"])
    except Exception:
        return None, "none"
    idx = {int(m.group(1)) for m in re.finditer(r"^GPU\[(\d+)\]", out, re.M)}
    return ([None] * len(idx), "rocm-smi") if idx else (None, "none")


def _load_gpustat():
    """The sibling gpustat module, or None when it cannot be imported (detection then degrades, not crashes)."""
    try:
        here = str(Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        import gpustat
        return gpustat
    except Exception:
        return None


def parse_memtotal_gib(meminfo: str) -> float | None:
    m = re.search(r"^MemTotal:\s+(\d+)\s*kB", meminfo, re.M)
    return int(m.group(1)) / (1024 * 1024) if m else None


def read_meminfo() -> str:
    try:
        return Path("/proc/meminfo").read_text()
    except OSError:
        return ""


def detect(gpu_count: int | None = None, drm_root: Path = DEFAULT_DRM_ROOT,
           run=None, meminfo: str | None = None) -> dict:
    """Describe this machine.

    Returns {gpu_count, vram_gib_per_gpu, host_ram_gib, source, ignored_devices}.
      gpu_count         int, or None when nothing could be detected
      vram_gib_per_gpu  [float, ...] for the counted GPUs ([] when unknown)
      host_ram_gib      float MemTotal, or None when unreadable
      source            'override' | 'sysfs' | 'amd-smi' | 'rocm-smi' | 'none'
      ignored_devices   devices under 8 GiB VRAM that were not counted (iGPU)
    `gpu_count` overrides GPU detection (host RAM is still read). `meminfo`
    injects /proc/meminfo text for tests ("" = unreadable).
    """
    ram = parse_memtotal_gib(read_meminfo() if meminfo is None else meminfo)
    hw = {"gpu_count": None, "vram_gib_per_gpu": [], "host_ram_gib": ram,
          "source": "none", "ignored_devices": 0}
    if gpu_count is not None:
        hw.update(gpu_count=int(gpu_count), source="override")
        return hw
    sizes = sysfs_vram_sizes(drm_root)
    source = "sysfs"
    if sizes is None:
        sizes, source = smi_vram_sizes(run)
    if sizes is None:
        return hw
    big = [s for s in sizes if s is None or s >= MIN_GPU_VRAM_BYTES]
    hw.update(gpu_count=len(big), source=source,
              vram_gib_per_gpu=[round(s / GIB, 2) for s in big if s is not None],
              ignored_devices=len(sizes) - len(big))
    return hw


# ── metadata.requires parsing ───────────────────────────────────────────────

_PROFILE_RE = re.compile(r"^  ([A-Za-z0-9][\w.\-]*):\s*(?:#.*)?$")


def strip_comment(s: str) -> str:
    """Drop a trailing `# comment` (outside quotes) and surrounding space."""
    quote = None
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or s[i - 1].isspace()):
            return s[:i].rstrip()
    return s.strip()


def _scalar(s: str):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        body = s[1:-1]
        return body.replace('\\"', '"') if s[0] == '"' else body.replace("''", "'")
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if re.fullmatch(r"[+-]?\d+", s):
        return int(s)
    if re.fullmatch(r"[+-]?\d*\.\d+", s):
        return float(s)
    return s


def _value(raw: str):
    s = strip_comment(raw)
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_scalar(p) for p in inner.split(",") if p.strip()] if inner else []
    return _scalar(s)


def parse_requires(yaml_text: str) -> dict[str, dict]:
    """Read metadata.requires of each top-level profile under `models:`.

    Line-oriented (no YAML library): flow-style lists and plain/quoted scalars,
    one key per line. Comments (full-line and trailing) are tolerated, and
    commented-out template profiles are ignored. Profiles without a
    metadata.requires block are simply absent from the result.
    """
    out: dict[str, dict] = {}
    in_models = False
    profile = None
    meta_ind = req_ind = None     # indent of the open `metadata:` / `requires:` line
    for line in yaml_text.splitlines():
        if not in_models:
            in_models = bool(re.match(r"^models:\s*(?:#.*)?$", line))
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            break                                  # next top-level key
        if _PROFILE_RE.match(line):
            profile = _PROFILE_RE.match(line).group(1)
            meta_ind = req_ind = None
            continue
        if profile is None:
            continue
        text = line.strip()
        if req_ind is not None and indent > req_ind:
            m = re.match(r"([A-Za-z_][\w\-]*):(?:\s+(.*))?$", text)
            if m:
                out[profile][m.group(1)] = _value(m.group(2) or "")
            continue
        req_ind = None
        if meta_ind is not None and indent > meta_ind:
            if re.fullmatch(r"requires:\s*(?:#.*)?", text):
                req_ind = indent
                out.setdefault(profile, {})
            continue
        meta_ind = None
        if indent == 4 and re.fullmatch(r"metadata:\s*(?:#.*)?", text):
            meta_ind = indent
    return out


# ── supports() ──────────────────────────────────────────────────────────────

def _fmt_gib(x: float) -> str:
    return f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}"


def supports(requires: dict | None, hw: dict) -> tuple[bool, int | None, list[str]]:
    """Can a profile with `requires` run on `hw` (a detect() dict)?

    Returns (ok, tp_or_split, reasons):
      * `gpus: [..]`  -> largest allowed count <= gpu_count is the TP size
                         (reason if none fits)
      * `min_gpus: N` -> ok when gpu_count >= N; the split size is gpu_count
      * `host_ram_gib`-> not ok when host RAM is known and < 0.92 x need
      * no/empty requires, or unknown gpu_count/host RAM -> permissive
    tp_or_split is None when not ok, or when the profile names no GPU rule.
    `reasons` explains every failed check (empty when ok).
    """
    req = requires or {}
    n = hw.get("gpu_count")
    reasons: list[str] = []
    tp = None
    if n is not None:
        if isinstance(req.get("gpus"), list):
            fits = [g for g in req["gpus"] if isinstance(g, int) and g <= n]
            if fits:
                tp = max(fits)
            else:
                reasons.append(f"needs gpus {req['gpus']}, detected {n}")
        elif isinstance(req.get("min_gpus"), int):
            if n >= req["min_gpus"]:
                tp = n
            else:
                reasons.append(f"needs min_gpus {req['min_gpus']}, detected {n}")
    need = req.get("host_ram_gib")
    have = hw.get("host_ram_gib")
    if isinstance(need, (int, float)) and have is not None and have < RAM_TOLERANCE * need:
        reasons.append(f"needs host RAM {_fmt_gib(need)} GiB (min {_fmt_gib(RAM_TOLERANCE * need)}), "
                       f"measured {_fmt_gib(have)} GiB")
    if reasons:
        return False, None, reasons
    return True, tp, []


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Print detected GPU / host RAM hardware.")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--gpu-count", type=int, metavar="N", help="override detected GPU count")
    args = ap.parse_args(argv)
    hw = detect(args.gpu_count)
    if args.json:
        print(json.dumps(hw, indent=2))
    else:
        n = hw["gpu_count"]
        print(f"GPUs:     {n if n is not None else 'not detected'} ({hw['source']})")
        if hw["vram_gib_per_gpu"]:
            print(f"VRAM/GPU: {', '.join(_fmt_gib(v) for v in hw['vram_gib_per_gpu'])} GiB")
        if hw["ignored_devices"]:
            print(f"Ignored:  {hw['ignored_devices']} device(s) under 8 GiB VRAM")
        ram = hw["host_ram_gib"]
        print(f"Host RAM: {_fmt_gib(ram) + ' GiB' if ram is not None else 'unknown'}")
    return 0 if hw["gpu_count"] is not None else 1


if __name__ == "__main__":
    sys.exit(main())
