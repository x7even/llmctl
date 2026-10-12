#!/usr/bin/env python3
"""
Unit tests for scripts/configure (GPU detection, TP rounding, profile minimums).

Run:  python3 tests/test_configure.py        (also pytest-compatible)
"""
import hashlib
import importlib.machinery
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_path = str(REPO / "scripts" / "configure")
_loader = importlib.machinery.SourceFileLoader("configure", _path)
_spec = importlib.util.spec_from_loader("configure", _loader)
cfg = importlib.util.module_from_spec(_spec)
_loader.exec_module(cfg)

GIB = 1024**3

# Small fixture: one profile of each kind + a commented template tail.
FIXTURE = """\
healthCheckTimeout: 2100

models:

  # comment mentioning --tensor-parallel-size 4 must never be rewritten
  qwen3.8-27b-code:
    cmd: |
      podman run --rm
        -v __LLMSTACK_DIR__/.vllm-cache:/root/.cache/vllm
        --entrypoint=""
        docker.io/vllm/vllm-openai-rocm:v0.26.0
        vllm serve /models/x
        --tensor-parallel-size 4
        --enable-expert-parallel
        --cudagraph-capture-sizes 1 2 4 8 16 32
    cmdStop: podman stop x

  qwen3.8-flash-next-vllm:
    cmd: |
      podman run --rm
        vllm serve /models/y
        --tensor-parallel-size 4
        --enable-expert-parallel
        --cudagraph-capture-sizes 1 2 4 8
    cmdStop: podman stop y

  qwen3.8-flash-next:
    cmd: |
      llama-server
        --tensor-split 1,1,1,1
        --ctx-size 1024
    cmdStop: podman stop z

  gemma4-12b-q4:
    cmd: |
      llama-server
        --tensor-split 1,1,1,1
    cmdStop: podman stop w

  brand-new-profile:
    cmd: |
      vllm serve /models/q
        --tensor-parallel-size 4
    cmdStop: podman stop q

# ── Template ──
# models:
#   my-model:
#       --tensor-parallel-size 4
#       --tensor-split 1,1,1,1
"""


def _patched(n, text=FIXTURE):
    return cfg.patch(text, n, "/opt/llmstack")


def _block(text, name):
    _, profiles, _ = cfg.split_profiles(text)
    return "".join(dict(profiles)[name])


def _tp(text, name):
    return int(re.search(r"--tensor-parallel-size (\d+)", _block(text, name)).group(1))


def _split(text, name):
    m = re.search(r"--tensor-split ([\d,]+)", _block(text, name))
    return m.group(1) if m else None


def _status(results):
    return {r.name: r for r in results}


# ── TP rounding ─────────────────────────────────────────────────────────────

def test_choose_tp_default_set():
    expect = {1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 8: 4}
    for n, tp in expect.items():
        assert cfg.choose_tp(n) == tp, (n, cfg.choose_tp(n))


def test_choose_tp_restricted_set():
    assert cfg.choose_tp(3, (4,)) is None
    assert cfg.choose_tp(8, (4,)) == 4
    assert cfg.choose_tp(3, (2, 4)) == 2
    assert cfg.choose_tp(1, (2, 4)) is None


def test_patch_tp_rounding_for_each_gpu_count():
    # qwen3.8-27b-code: min 2, valid 1/2/4. flash-next-vllm: TP4 only.
    for n, tp27, flash_ok in [(2, 2, False), (3, 2, False), (4, 4, True), (8, 4, True)]:
        out, res = _patched(n)
        st = _status(res)
        assert _tp(out, "qwen3.8-27b-code") == tp27, n
        assert st["qwen3.8-27b-code"].status == "ok"
        assert (st["qwen3.8-flash-next-vllm"].status == "ok") == flash_ok, n
        if flash_ok:
            assert _tp(out, "qwen3.8-flash-next-vllm") == 4


def test_tp1_infeasible_for_27b_and_leaves_block_untouched():
    out, res = _patched(1)
    st = _status(res)
    assert st["qwen3.8-27b-code"].status == "infeasible"
    # No bogus TP written: block identical to the placeholder-substituted input.
    base = FIXTURE.replace("__LLMSTACK_DIR__", "/opt/llmstack")
    assert _block(out, "qwen3.8-27b-code") == _block(base, "qwen3.8-27b-code")
    assert _tp(out, "qwen3.8-27b-code") == 4
    assert "--enable-expert-parallel" in _block(out, "qwen3.8-27b-code")


def test_expert_parallel_flag_never_stripped_and_reconfigure_roundtrips():
    # An unknown profile (default min 1) at TP1 keeps --enable-expert-parallel,
    # so reconfiguring the same text for a larger GPU count loses nothing.
    text = FIXTURE.replace("qwen3.8-27b-code:", "tiny-moe:")
    out1, res1 = cfg.patch(text, 1, "/x")
    assert _status(res1)["tiny-moe"].status == "ok"
    assert _tp(out1, "tiny-moe") == 1
    assert "--enable-expert-parallel" in _block(out1, "tiny-moe")
    out4, _ = cfg.patch(out1, 4, "/x")
    assert _tp(out4, "tiny-moe") == 4
    assert "--enable-expert-parallel" in _block(out4, "tiny-moe")


def test_column0_comment_between_profiles_does_not_truncate_parsing():
    text = FIXTURE.replace("\n  qwen3.8-flash-next-vllm:", "\n# stray column-0 comment\n  qwen3.8-flash-next-vllm:", 1)
    assert "# stray column-0 comment" in text
    _, profiles, _ = cfg.split_profiles(text)
    _, base_profiles, _ = cfg.split_profiles(FIXTURE)
    assert [n for n, _ in profiles] == [n for n, _ in base_profiles]
    out, res = cfg.patch(text, 4, "/x")
    assert len(res) == len(base_profiles) >= 3
    assert "# stray column-0 comment" in out


def test_idle_card_warning_when_tp_below_n():
    for n in (3, 5, 6, 7, 8):
        _, res = _patched(n)
        s = cfg.format_summary(n, "test", 0, res, [])
        assert "idle" in s, n
    _, res = _patched(4)
    assert "idle" not in cfg.format_summary(4, "test", 0, [r for r in res if r.status == "ok" and r.kind == "vllm" and r.tp == 4], [])
    _, res2 = cfg.patch(FIXTURE, 2, "/x")
    assert "idle" not in cfg.format_summary(2, "test", 0, res2, [])


def test_comments_and_template_untouched():
    out, _ = _patched(2)
    assert "# comment mentioning --tensor-parallel-size 4" in out
    assert "#       --tensor-parallel-size 4" in out
    assert "#       --tensor-split 1,1,1,1" in out


def test_placeholder_substituted():
    out, _ = _patched(4)
    assert "__LLMSTACK_DIR__" not in out
    assert "-v /opt/llmstack/.vllm-cache:/root/.cache/vllm" in out


# ── GGUF tensor-split ───────────────────────────────────────────────────────

def test_gguf_tensor_split_sized_to_real_n():
    for n in (3, 4, 8):
        out, res = _patched(n)
        assert _split(out, "gemma4-12b-q4") == ",".join(["1"] * n)
    out3, res3 = _patched(3)
    # flash-next GGUF needs 3 -> OK at 3 with a 3-way split (no TP rounding for GGUF).
    assert _status(res3)["qwen3.8-flash-next"].status == "ok"
    assert _split(out3, "qwen3.8-flash-next") == "1,1,1"


def test_gguf_n1_keeps_reversible_flag():
    out, res = _patched(1)
    assert _split(out, "gemma4-12b-q4") == "1"
    back, _ = cfg.patch(out, 4, "/opt/llmstack")
    assert _split(back, "gemma4-12b-q4") == "1,1,1,1"


# ── Minimums reporting ──────────────────────────────────────────────────────

def test_minimums_reporting():
    _, res = _patched(2)
    st = _status(res)
    assert st["qwen3.8-flash-next"].status == "infeasible"       # GGUF needs 3
    assert st["qwen3.8-flash-next-vllm"].status == "infeasible"  # needs 4
    assert st["gemma4-12b-q4"].status == "ok"
    s = cfg.format_summary(2, "test", 0, res, [])
    assert "SKIP qwen3.8-flash-next " in s
    assert "needs 3 GPU(s), have 2" in s
    assert "needs 4 GPU(s), have 2" in s
    assert "not modified or removed" in s


def test_unknown_profile_flagged():
    _, res = _patched(4)
    s = cfg.format_summary(4, "test", 0, res, [])
    assert "brand-new-profile has no entry in PROFILE_REQUIREMENTS" in s


def test_table_covers_real_config_profiles():
    text = (REPO / "config" / "models.yaml").read_text()
    _, profiles, _ = cfg.split_profiles(text)
    names = [n for n, _ in profiles]
    assert names, "no profiles parsed from config/models.yaml"
    missing = [n for n in names if n not in cfg.PROFILE_REQUIREMENTS]
    assert not missing, f"profiles without a PROFILE_REQUIREMENTS entry: {missing}"
    for n, lines in profiles:
        assert cfg.block_kind(lines) in ("vllm", "gguf"), n


def test_known_minimums():
    R = cfg.PROFILE_REQUIREMENTS
    for k in ("qwen3.8-27b-code", "qwen3.8-27b-think", "qwen3.8-27b-fast"):
        assert R[k].min_gpus == 2 and not R[k].estimate
    assert R["qwen3.8-flash-next-vllm"].min_gpus == 4
    assert R["qwen3.8-flash-next-vllm"].valid_tp == (4,)
    assert R["qwen3.8-flash-next"].min_gpus == 3
    assert R["gemma4-26b-q8"].min_gpus == 1 and R["gemma4-12b-q4"].min_gpus == 1
    for k in ("qwen3.6-35b-code", "qwen3.6-35b-128k-nomtp", "qwen3.6-35b-fast"):
        assert R[k].min_gpus >= 2 and R[k].estimate


# ── Host RAM ────────────────────────────────────────────────────────────────

def _meminfo(gib):
    return f"MemTotal:       {int(gib * 1024 * 1024)} kB\nMemFree:        1 kB\n"


def test_host_ram_warning():
    _, res = _patched(4)
    assert cfg.parse_memtotal_gib(_meminfo(188)) == 188
    assert cfg.check_host_ram(res, _meminfo(188)) == []     # this host: no warning
    assert cfg.check_host_ram(res, _meminfo(94)) == []      # 96 GB box reports ~94 GiB
    low = cfg.check_host_ram(res, _meminfo(64))
    assert len(low) == 1 and "qwen3.8-flash-next-vllm" in low[0] and "64 GiB" in low[0]
    assert len(cfg.check_host_ram(res, "")) == 1            # unreadable -> warn
    _, res2 = _patched(2)                                   # infeasible -> GPU message wins
    assert cfg.check_host_ram(res2, _meminfo(8)) == []


# ── GPU detection ───────────────────────────────────────────────────────────

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


def test_igpu_filtered_from_fake_sysfs():
    with tempfile.TemporaryDirectory() as td:
        drm = _fake_drm(Path(td), {"card0": 32 * GIB, "card1": 32 * GIB, "card2": 32 * GIB,
                                    "card3": 512 * 1024 * 1024})
        assert cfg.count_sysfs_gpus(drm) == (3, 1)
        assert cfg.detect_gpus(drm, run=lambda a: "") == (3, 1, "sysfs")


def test_connector_entries_and_symlink_dupes_ignored():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        drm = _fake_drm(root, {"card0": 32 * GIB})
        # a second card node pointing at the same underlying device
        (drm / "card1").mkdir()
        (drm / "card1" / "device").symlink_to(root / "devices" / "pci-card0")
        assert cfg.count_sysfs_gpus(drm) == (1, 0)


def test_only_igpu_gives_zero_not_rocm_smi_fallback():
    with tempfile.TemporaryDirectory() as td:
        drm = _fake_drm(Path(td), {"card0": 2 * GIB})
        called = []
        det = cfg.detect_gpus(drm, run=lambda a: called.append(a) or "GPU[0] : x")
        assert det == (0, 1, "sysfs") and not called


def test_fallback_to_rocm_smi_when_no_sysfs_vram_info():
    with tempfile.TemporaryDirectory() as td:
        drm = _fake_drm(Path(td), {"card0": None})
        out = ("GPU[0]\t\t: VRAM Total Memory (B): 34208743424\n"
               "GPU[1]\t\t: VRAM Total Memory (B): 34208743424\n"
               "GPU[2]\t\t: VRAM Total Memory (B): 536870912\n")
        assert cfg.detect_gpus(drm, run=lambda a: out) == (2, 1, "rocm-smi")
        listing = "GPU[0] : Device Name: a\nGPU[0] : Device ID: b\nGPU[1] : Device Name: c\n"
        def run(argv):
            return listing if "--listdevices" in argv else ""
        assert cfg.detect_gpus(drm, run=run) == (2, 0, "rocm-smi")  # unique indices, not lines
        assert cfg.detect_gpus(Path(td) / "nope", run=lambda a: (_ for _ in ()).throw(OSError())) is None


def test_real_host_detection_if_amd_present():
    # Smoke only: must not crash, and must return a sane result or None.
    det = cfg.detect_gpus()
    assert det is None or det[0] >= 0


# ── CLI behaviour (subprocess, temp copy of the real config) ────────────────

def _sandbox():
    td = tempfile.mkdtemp(prefix="configure-test-")
    (Path(td) / "config").mkdir()
    dst = Path(td) / "config" / "models.yaml"
    src = (REPO / "config" / "models.yaml").read_text()
    dst.write_text(src.replace("/home/xin/ai/llmstack", "__LLMSTACK_DIR__"))
    return Path(td), dst


def _run(*args):
    return subprocess.run([sys.executable, str(REPO / "scripts" / "configure"), *args],
                          capture_output=True, text=True)


def _sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_dry_run_does_not_write():
    td, conf = _sandbox()
    try:
        before = _sha(conf)
        for n in ("2", "3", "4"):
            r = _run("--config", str(conf), "--gpu-count", n, "--dry-run")
            assert r.returncode == 0, r.stderr
            assert "dry run" in r.stdout and f"GPU count: {n}" in r.stdout
            assert _sha(conf) == before
            assert not Path(str(conf) + ".bak").exists()
    finally:
        shutil.rmtree(td)


def test_write_is_idempotent_and_reconfigurable():
    td, conf = _sandbox()
    try:
        r = _run("--config", str(conf), "--gpu-count", "3")
        assert r.returncode == 0, r.stderr
        assert Path(str(conf) + ".bak").exists()
        first = conf.read_text()
        assert "__LLMSTACK_DIR__" not in first
        assert _tp(first, "qwen3.8-27b-code") == 2
        assert _split(first, "gemma4-12b-q4") == "1,1,1"
        # second run: no changes, same bytes
        r2 = _run("--config", str(conf), "--gpu-count", "3")
        assert r2.returncode == 0 and "No changes needed" in r2.stdout
        assert conf.read_text() == first
        # reconfigure back to 4: TP and split restored for feasible profiles
        _run("--config", str(conf), "--gpu-count", "4")
        again = conf.read_text()
        assert _tp(again, "qwen3.8-27b-code") == 4
        assert _split(again, "gemma4-12b-q4") == "1,1,1,1"
        assert _run("--config", str(conf), "--gpu-count", "4").stdout.startswith("No changes needed")
    finally:
        shutil.rmtree(td)


def test_pure_patch_idempotent():
    for n in (1, 2, 3, 4, 8):
        once, _ = _patched(n)
        twice, _ = cfg.patch(once, n, "/opt/llmstack")
        assert once == twice, n


def test_bad_gpu_count_rejected():
    td, conf = _sandbox()
    try:
        r = _run("--config", str(conf), "--gpu-count", "0")
        assert r.returncode != 0
    finally:
        shutil.rmtree(td)


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
