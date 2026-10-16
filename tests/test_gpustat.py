#!/usr/bin/env python3
"""
Unit tests for scripts/gpustat.py against real captured output (tests/fixtures/amd_smi_metric.json from
`amd-smi metric --mem-usage --usage --temperature --json`, tests/fixtures/rocm_smi_show.txt from
`rocm-smi --showmeminfo vram --showuse --showtemp`), with an injected runner for tool availability.

Run:  python3 tests/test_gpustat.py        (also pytest-compatible)
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import gpustat  # noqa: E402

AMD = (REPO / "tests/fixtures/amd_smi_metric.json").read_text()
ROCM = (REPO / "tests/fixtures/rocm_smi_show.txt").read_text()
MIB = 1024 * 1024


def _runner(amd=None, rocm=None):
    """amd/rocm: text to return, or None when that tool is not installed."""
    def run(argv):
        text = {"amd-smi": amd, "rocm-smi": rocm}[argv[0]]
        if text is None:
            raise FileNotFoundError(argv[0])
        return text
    return run


def test_parse_amd_smi_real_output():
    gpus = gpustat.parse_amd_smi(AMD)
    assert [g["index"] for g in gpus] == [0, 1, 2, 3]
    g = gpus[0]
    assert g["vram_total_b"] == 32624 * MIB          # "MB" is MiB: same figure rocm-smi prints in bytes
    assert g["vram_total_b"] == 34208743424
    assert 0 < g["vram_used_b"] < g["vram_total_b"]
    assert g["util_pct"] is not None and g["temp_c"] is not None


def test_parse_rocm_smi_real_output():
    gpus = gpustat.parse_rocm_smi(ROCM)
    assert [g["index"] for g in gpus] == [0, 1, 2, 3]
    assert all(g["vram_total_b"] == 34208743424 for g in gpus)
    assert all(g["util_pct"] is not None and g["temp_c"] is not None for g in gpus)


def test_both_tools_agree_on_sizes():
    a, r = gpustat.parse_amd_smi(AMD), gpustat.parse_rocm_smi(ROCM)
    assert [g["vram_total_b"] for g in a] == [g["vram_total_b"] for g in r]


def test_amd_smi_preferred_when_both_present():
    gpus, tool = gpustat.read_gpus(_runner(amd=AMD, rocm=ROCM))
    assert tool == "amd-smi" and len(gpus) == 4


def test_rocm_smi_fallback_when_amd_smi_missing():
    gpus, tool = gpustat.read_gpus(_runner(amd=None, rocm=ROCM))
    assert tool == "rocm-smi" and len(gpus) == 4


def test_rocm_smi_fallback_when_amd_smi_prints_garbage():
    gpus, tool = gpustat.read_gpus(_runner(amd="Traceback: not json", rocm=ROCM))
    assert tool == "rocm-smi" and len(gpus) == 4


def test_neither_tool_gives_empty_and_none():
    assert gpustat.read_gpus(_runner()) == ([], "none")
    assert gpustat.vram_used_total_b(_runner()) is None


def test_na_fields_do_not_crash():
    data = json.loads(AMD)
    data["gpu_data"][0]["usage"]["gfx_activity"] = "N/A"
    data["gpu_data"][1]["temperature"] = "N/A"
    data["gpu_data"][2]["mem_usage"]["used_vram"] = "N/A"
    gpus = gpustat.parse_amd_smi(json.dumps(data))
    assert gpus[0]["util_pct"] is None
    assert gpus[1]["temp_c"] is None
    assert gpus[2]["vram_used_b"] == 0
    assert len(gpus) == 4


def test_gpu_without_vram_info_is_dropped():
    data = {"gpu_data": [{"gpu": 0, "mem_usage": {"total_vram": "N/A"}}]}
    assert gpustat.parse_amd_smi(json.dumps(data)) == []


def test_vram_used_total_sums_gpus():
    gpus = gpustat.parse_amd_smi(AMD)
    assert gpustat.vram_used_total_b(_runner(amd=AMD)) == sum(g["vram_used_b"] for g in gpus)


def test_format_gpus():
    line = gpustat.format_gpus(gpustat.parse_amd_smi(AMD))[0]
    assert line.startswith("GPU[0]  VRAM ") and "/ 31.9 GiB" in line and "util " in line and line.endswith("C")


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name}: {type(e).__name__}: {e}")
    sys.exit(1 if failed else 0)
