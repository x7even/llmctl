#!/usr/bin/env python3
"""
Unit tests for scripts/llmhw.py: detect() (fake sysfs, injected rocm-smi,
override, iGPU filter), parse_requires() (fixture + the real config/models.yaml)
and supports().

Run:  python3 tests/test_llmhw.py        (also pytest-compatible)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import llmhw  # noqa: E402

GIB = 1024**3


def _meminfo(gib):
    return f"MemTotal:       {int(gib * 1024 * 1024)} kB\nMemFree:        1 kB\n"


def _fake_drm(root: Path, cards: dict, connectors=True):
    """cards: {'card0': vram_bytes | None}. None = no mem_info file."""
    for name, vram in cards.items():
        dev = root / "devices" / f"pci-{name}"
        dev.mkdir(parents=True)
        if vram is not None:
            (dev / "mem_info_vram_total").write_text(f"{vram}\n")
        c = root / "drm" / name
        c.mkdir(parents=True)
        (c / "device").symlink_to(dev)
        if connectors:
            (root / "drm" / f"{name}-DP-1").mkdir()
    return root / "drm"


def _no_rocm(argv):
    raise AssertionError(f"rocm-smi must not be called: {argv}")


def _hw(n, ram=188.0):
    return {"gpu_count": n, "vram_gib_per_gpu": [], "host_ram_gib": ram,
            "source": "test", "ignored_devices": 0}


# ── detect() ────────────────────────────────────────────────────────────────

def test_detect_fake_sysfs_four_gpus():
    with tempfile.TemporaryDirectory() as td:
        drm = _fake_drm(Path(td), {f"card{i}": 32 * GIB for i in range(4)})
        hw = llmhw.detect(drm_root=drm, run=_no_rocm, meminfo=_meminfo(188))
        assert hw["gpu_count"] == 4 and hw["source"] == "sysfs"
        assert hw["vram_gib_per_gpu"] == [32.0] * 4
        assert hw["host_ram_gib"] == 188
        assert hw["ignored_devices"] == 0


def test_igpu_filtered_from_fake_sysfs():
    with tempfile.TemporaryDirectory() as td:
        drm = _fake_drm(Path(td), {"card0": 32 * GIB, "card1": 32 * GIB, "card2": 32 * GIB,
                                    "card3": 512 * 1024 * 1024})
        hw = llmhw.detect(drm_root=drm, run=_no_rocm, meminfo="")
        assert hw["gpu_count"] == 3 and hw["ignored_devices"] == 1
        assert hw["vram_gib_per_gpu"] == [32.0] * 3
        assert hw["host_ram_gib"] is None                 # unreadable -> None


def test_connector_entries_and_symlink_dupes_ignored():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        drm = _fake_drm(root, {"card0": 32 * GIB})
        (drm / "card1").mkdir()                           # second node, same device
        (drm / "card1" / "device").symlink_to(root / "devices" / "pci-card0")
        assert llmhw.sysfs_vram_sizes(drm) == [32 * GIB]
        assert llmhw.detect(drm_root=drm, run=_no_rocm, meminfo="")["gpu_count"] == 1


def test_only_igpu_gives_zero_not_rocm_smi_fallback():
    with tempfile.TemporaryDirectory() as td:
        drm = _fake_drm(Path(td), {"card0": 2 * GIB})
        hw = llmhw.detect(drm_root=drm, run=_no_rocm, meminfo="")
        assert hw["gpu_count"] == 0 and hw["ignored_devices"] == 1 and hw["source"] == "sysfs"


def test_fallback_to_rocm_smi_when_no_sysfs_vram_info():
    with tempfile.TemporaryDirectory() as td:
        drm = _fake_drm(Path(td), {"card0": None})
        out = ("GPU[0]\t\t: VRAM Total Memory (B): 34208743424\n"
               "GPU[1]\t\t: VRAM Total Memory (B): 34208743424\n"
               "GPU[2]\t\t: VRAM Total Memory (B): 536870912\n")
        hw = llmhw.detect(drm_root=drm, run=lambda a: out, meminfo="")
        assert hw["gpu_count"] == 2 and hw["ignored_devices"] == 1 and hw["source"] == "rocm-smi"
        assert hw["vram_gib_per_gpu"] == [31.86, 31.86]
        listing = "GPU[0] : Device Name: a\nGPU[0] : Device ID: b\nGPU[1] : Device Name: c\n"

        def run(argv):
            return listing if "--listdevices" in argv else ""
        hw = llmhw.detect(drm_root=drm, run=run, meminfo="")
        assert hw["gpu_count"] == 2 and hw["vram_gib_per_gpu"] == []   # unique indices, not lines


def test_nothing_detectable_gives_none():
    def boom(argv):
        raise OSError("no rocm-smi")
    with tempfile.TemporaryDirectory() as td:
        hw = llmhw.detect(drm_root=Path(td) / "nope", run=boom, meminfo="")
        assert hw["gpu_count"] is None and hw["source"] == "none"


def test_override_wins_and_skips_gpu_probing():
    with tempfile.TemporaryDirectory() as td:
        drm = _fake_drm(Path(td), {"card0": 32 * GIB})
        hw = llmhw.detect(gpu_count=7, drm_root=drm, run=_no_rocm, meminfo=_meminfo(64))
        assert hw["gpu_count"] == 7 and hw["source"] == "override"
        assert hw["host_ram_gib"] == 64


def test_parse_memtotal():
    assert llmhw.parse_memtotal_gib(_meminfo(188)) == 188
    assert llmhw.parse_memtotal_gib("") is None


def test_real_host_detection_smoke():
    hw = llmhw.detect()
    assert set(hw) >= {"gpu_count", "vram_gib_per_gpu", "host_ram_gib", "source"}
    assert hw["gpu_count"] is None or hw["gpu_count"] >= 0


def test_cli_json_and_text():
    script = str(REPO / "scripts" / "llmhw.py")
    r = subprocess.run([sys.executable, script, "--json", "--gpu-count", "3"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["gpu_count"] == 3 and d["source"] == "override"
    r = subprocess.run([sys.executable, script, "--gpu-count", "2"], capture_output=True, text=True)
    assert r.returncode == 0 and "GPUs:     2 (override)" in r.stdout and "Host RAM:" in r.stdout


# ── parse_requires() ────────────────────────────────────────────────────────

YAML_FIXTURE = """\
healthCheckTimeout: 2100  # models: not here

models:

  # comment before a profile
  alpha:
    name: "Alpha"
    metadata:
      requires:
        gpus: [2, 4]            # valid TP sizes
        # a full-line comment inside the block
        host_ram_gib: 96
        vram_total_gib: 66.5
        estimate: true
        note: "has a # hash and: colon"
    cmd: |
      metadata:
        requires:
          gpus: [99]
    cmdStop: x

  beta:
    metadata:
      owner: "someone"
      requires:
        min_gpus: 3
    cmd: y

  gamma:
    name: "no metadata at all"
    cmd: z

  delta:
    metadata:
      owner: "metadata but no requires"
    cmd: z

  epsilon:
    metadata:
      requires:
        gpus: []
    cmd: z

# ── Template ──
# models:
#   my-model:
#     metadata:
#       requires:
#         gpus: [8]
"""


def test_parse_requires_fixture():
    r = llmhw.parse_requires(YAML_FIXTURE)
    assert set(r) == {"alpha", "beta", "epsilon"}, set(r)
    assert r["alpha"] == {"gpus": [2, 4], "host_ram_gib": 96, "vram_total_gib": 66.5,
                          "estimate": True, "note": "has a # hash and: colon"}
    assert r["beta"] == {"min_gpus": 3}
    assert r["epsilon"] == {"gpus": []}
    assert "my-model" not in r                           # commented-out template ignored


def test_parse_requires_stops_at_next_top_level_key():
    text = YAML_FIXTURE + "\nother:\n  zeta:\n    metadata:\n      requires:\n        gpus: [1]\n"
    assert "zeta" not in llmhw.parse_requires(text)
    assert llmhw.parse_requires("no models section\n") == {}


def test_parse_requires_real_config_all_thirteen_profiles():
    text = (REPO / "config" / "models.yaml").read_text()
    req = llmhw.parse_requires(text)
    expected = {
        "qwen3.8-27b-code", "qwen3.8-27b-think", "qwen3.8-27b-fast",
        "qwen3.8-flash-next", "qwen3.8-flash-next-vllm",
        "qwen3.6-27b-code",
        "qwen3.6-35b-code", "qwen3.6-35b-128k-nomtp", "qwen3.6-35b-fast",
        "gemma4-26b-a4b", "gemma4-26b-fp8", "gemma4-26b-q8", "gemma4-12b-q4",
    }
    assert set(req) == expected, (sorted(expected - set(req)), sorted(set(req) - expected))
    assert "my-new-model" not in req and "my-gguf-model" not in req
    for name, r in req.items():
        assert ("gpus" in r) != ("min_gpus" in r), f"{name}: needs exactly one of gpus/min_gpus"
        if "gpus" in r:
            assert isinstance(r["gpus"], list) and r["gpus"] and all(isinstance(g, int) for g in r["gpus"]), name
        else:
            assert isinstance(r["min_gpus"], int), name
        if "estimate" in r:
            assert r["estimate"] is True, name
        assert set(r) <= {"gpus", "min_gpus", "host_ram_gib", "vram_total_gib", "estimate", "note"}, (name, set(r))
    assert req["qwen3.8-flash-next-vllm"]["host_ram_gib"] == 96


# ── supports() ──────────────────────────────────────────────────────────────

def test_supports_gpus_list_picks_largest_allowed_not_above_count():
    req = {"gpus": [2, 4]}
    expect = {1: (False, None), 2: (True, 2), 3: (True, 2), 4: (True, 4), 8: (True, 4)}
    for n, (ok, tp) in expect.items():
        got_ok, got_tp, reasons = llmhw.supports(req, _hw(n))
        assert (got_ok, got_tp) == (ok, tp), n
        assert bool(reasons) == (not ok), n
    _, _, reasons = llmhw.supports({"gpus": [4]}, _hw(2))
    assert reasons == ["needs gpus [4], detected 2"]
    assert llmhw.supports({"gpus": [4]}, _hw(3))[0] is False


def test_supports_min_gpus():
    assert llmhw.supports({"min_gpus": 3}, _hw(3)) == (True, 3, [])
    assert llmhw.supports({"min_gpus": 3}, _hw(4)) == (True, 4, [])
    ok, tp, reasons = llmhw.supports({"min_gpus": 3}, _hw(2))
    assert not ok and tp is None and reasons == ["needs min_gpus 3, detected 2"]
    assert llmhw.supports({"min_gpus": 1}, _hw(1))[0] is True


def test_supports_host_ram_uses_092_tolerance():
    req = {"gpus": [4], "host_ram_gib": 96}
    assert llmhw.supports(req, _hw(4, 188))[0] is True
    assert llmhw.supports(req, _hw(4, 94))[0] is True          # a 96 GB box
    assert llmhw.supports(req, _hw(4, 0.92 * 96))[0] is True   # boundary is inclusive
    ok, tp, reasons = llmhw.supports(req, _hw(4, 64))
    assert not ok and tp is None and len(reasons) == 1
    assert "64" in reasons[0] and "96" in reasons[0] and "RAM" in reasons[0]
    assert llmhw.supports(req, _hw(4, None))[0] is True        # unknown RAM -> permissive
    # both GPU and RAM failing report both reasons
    ok, _, reasons = llmhw.supports(req, _hw(2, 64))
    assert not ok and len(reasons) == 2


def test_supports_no_requires_is_permissive():
    for req in (None, {}):
        assert llmhw.supports(req, _hw(1)) == (True, None, [])
    assert llmhw.supports({"host_ram_gib": 8}, _hw(1)) == (True, None, [])   # RAM-only rule
    assert llmhw.supports({"gpus": [4]}, _hw(None))[0] is True               # GPU count unknown


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
