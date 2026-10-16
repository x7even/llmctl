#!/usr/bin/env python3
"""GPU memory / utilisation / temperature, amd-smi first with a rocm-smi fallback.

rocm-smi is deprecated and missing from ROCm 10 installs; amd-smi replaces it. This is the one place the
repo parses either tool. Callers get the same dicts whichever tool answered:

    {"index": 0, "vram_total_b": int, "vram_used_b": int, "util_pct": float|None, "temp_c": float|None}

amd-smi reports VRAM as {"value": N, "unit": "MB"} where MB is really MiB (32624 == 34,208,743,424 B,
the same figure rocm-smi prints in bytes), so the conversion happens once here.

`run(argv) -> str` is injectable for tests. Both tools cost about 60 ms per call.
"""
from __future__ import annotations

import json
import re
import subprocess

_MIB = 1024 * 1024


def _run_cmd(argv: list[str]) -> str:
    return subprocess.check_output(argv, stderr=subprocess.DEVNULL, text=True, timeout=10)


def _num(field) -> float | None:
    """amd-smi wraps numbers as {"value": N, "unit": "..."} and uses "N/A" for missing ones."""
    if isinstance(field, dict):
        field = field.get("value")
    if isinstance(field, (int, float)):
        return float(field)
    return None


def _dict(x) -> dict:
    """amd-smi writes "N/A" in place of a whole section it cannot read."""
    return x if isinstance(x, dict) else {}


def parse_amd_smi(text: str) -> list[dict]:
    """Parse `amd-smi metric --mem-usage --usage --temperature --json`."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    rows = data.get("gpu_data", []) if isinstance(data, dict) else data
    gpus = []
    for row in rows if isinstance(rows, list) else []:
        row = _dict(row)
        mem = _dict(row.get("mem_usage"))
        total, used = _num(mem.get("total_vram")), _num(mem.get("used_vram"))
        if total is None:
            continue
        temp = _dict(row.get("temperature"))
        gpus.append({
            "index": int(row.get("gpu", len(gpus))),
            "vram_total_b": int(total * _MIB),
            "vram_used_b": int((used or 0) * _MIB),
            "util_pct": _num(_dict(row.get("usage")).get("gfx_activity")),
            "temp_c": _num(temp.get("hotspot", temp.get("edge"))),
        })
    return sorted(gpus, key=lambda g: g["index"])


_ROCM_LINE = re.compile(r"GPU\[(\d+)\]\s*:\s*(.+)")


def parse_rocm_smi(text: str) -> list[dict]:
    """Parse `rocm-smi --showmeminfo vram --showuse --showtemp` text."""
    by_idx: dict[int, dict] = {}
    for line in (text or "").splitlines():
        m = _ROCM_LINE.search(line)
        if not m:
            continue
        g = by_idx.setdefault(int(m.group(1)), {
            "index": int(m.group(1)), "vram_total_b": None, "vram_used_b": 0, "util_pct": None, "temp_c": None})
        body = m.group(2)
        val = re.search(r"([\d.]+)\s*$", body)
        if val is None:
            continue
        x = float(val.group(1))
        if "VRAM Total Memory (B):" in body:
            g["vram_total_b"] = int(x)
        elif "VRAM Total Used Memory (B):" in body:
            g["vram_used_b"] = int(x)
        elif "GPU use (%):" in body:
            g["util_pct"] = x
        elif "Temperature (Sensor junction) (C):" in body:
            g["temp_c"] = x
    return [g for _, g in sorted(by_idx.items()) if g["vram_total_b"] is not None]


def read_gpus(run=None) -> tuple[list[dict], str]:
    """Return (gpus, tool) with tool 'amd-smi', 'rocm-smi' or 'none' (then gpus is empty)."""
    run = run or _run_cmd
    try:
        gpus = parse_amd_smi(run(["amd-smi", "metric", "--mem-usage", "--usage", "--temperature", "--json"]))
        if gpus:
            return gpus, "amd-smi"
    except Exception:
        pass
    try:
        gpus = parse_rocm_smi(run(["rocm-smi", "--showmeminfo", "vram", "--showuse", "--showtemp"]))
        if gpus:
            return gpus, "rocm-smi"
    except Exception:
        pass
    return [], "none"


def vram_used_total_b(run=None) -> int | None:
    """Bytes of VRAM in use summed over all GPUs, or None when no tool answers."""
    gpus, _ = read_gpus(run)
    return sum(g["vram_used_b"] for g in gpus) if gpus else None


def format_gpus(gpus: list[dict]) -> list[str]:
    gib = 1024 ** 3
    out = []
    for g in gpus:
        util = "" if g["util_pct"] is None else f"  util {g['util_pct']:.0f}%"
        temp = "" if g["temp_c"] is None else f"  {g['temp_c']:.0f}C"
        out.append(f"GPU[{g['index']}]  VRAM {g['vram_used_b'] / gib:.1f} / {g['vram_total_b'] / gib:.1f} GiB{util}{temp}")
    return out


if __name__ == "__main__":
    found, tool = read_gpus()
    print(f"# via {tool}")
    print("\n".join(format_gpus(found)))
