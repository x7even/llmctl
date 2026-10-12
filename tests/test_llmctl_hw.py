#!/usr/bin/env python3
"""
Tests for the hardware-aware parts of bin/llmctl: `hw`, `list [--all]`,
`swap [--force]` refusal, `pick` filtering, the LLMSTACK_GPU_COUNT / --gpu-count
overrides and fail-open behaviour when scripts/llmhw.py is unusable.

Nothing here starts a router, loads a model or touches port 8080: in-process runs
replace llmctl's _http() and _is_running(), and subprocess runs only use paths that
exit before any network call (hw, swap refusal) or run with HOME pointed at an empty
directory so no pid file exists.

Run:  python3 tests/test_llmctl_hw.py        (also pytest-compatible)
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LLMCTL = REPO / "bin" / "llmctl"
REAL_CONFIG = REPO / "config" / "models.yaml"
sys.path.insert(0, str(REPO / "scripts"))
import llmhw  # noqa: E402

FIXTURE = """\
version: 2
models:
  big:
    name: "Needs four"
    ttl: 0
    metadata:
      requires:
        gpus: [4]
        estimate: true
        note: "fixture"
    aliases:
      - bigalias
      - bigger
  mid:
    name: "Two or four"
    ttl: 0
    metadata:
      requires:
        gpus: [2, 4]
    aliases:
      - midalias
  anyone:
    name: "Any count"
    ttl: 0
    metadata:
      requires:
        min_gpus: 1
  triple:
    name: "Needs three"
    ttl: 0
    metadata:
      requires:
        min_gpus: 3
  hungry:
    name: "Needs absurd RAM"
    ttl: 0
    metadata:
      requires:
        gpus: [1, 2, 4]
        host_ram_gib: 99999
  nometa:
    name: "No requires block"
    ttl: 0
    aliases:
      - plain
"""


# ── harness ─────────────────────────────────────────────────────────────────

def _load_llmctl():
    """A fresh llmctl module (own globals) every call; the file has no .py suffix."""
    name = "llmctl_under_test"
    loader = importlib.machinery.SourceFileLoader(name, str(LLMCTL))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _fixture_file(tmp: Path) -> Path:
    p = tmp / "models.yaml"
    p.write_text(FIXTURE)
    return p


class Result:
    def __init__(self, code, out, err, http_calls):
        self.code, self.out, self.err, self.http_calls = code, out, err, http_calls


def run(args, gpus=None, config=None, tweak=None):
    """Run llmctl.main() in-process with the router unreachable.

    gpus   -> LLMSTACK_GPU_COUNT (None = variable removed)
    config -> alternative models.yaml (default: the real one)
    tweak  -> callable(mod) to patch the fresh module (e.g. simulate llmhw failures)
    """
    mod = _load_llmctl()
    calls = []

    def fake_http(*a, **k):
        calls.append(a)
        return None

    mod._http = fake_http
    mod._is_running = lambda: False
    if config is not None:
        mod.CONFIG_FILE = Path(config)
    if tweak:
        tweak(mod)
    saved_env = os.environ.get("LLMSTACK_GPU_COUNT")
    saved_argv = sys.argv
    if gpus is None:
        os.environ.pop("LLMSTACK_GPU_COUNT", None)
    else:
        os.environ["LLMSTACK_GPU_COUNT"] = str(gpus)
    sys.argv = ["llmctl", *args]
    out, err, code = io.StringIO(), io.StringIO(), 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                mod.main()
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        sys.argv = saved_argv
        if saved_env is None:
            os.environ.pop("LLMSTACK_GPU_COUNT", None)
        else:
            os.environ["LLMSTACK_GPU_COUNT"] = saved_env
    return Result(code, out.getvalue(), err.getvalue(), calls)


def sub(args, gpus=None, llmctl=None, home=None, cwd=None):
    """Run llmctl as a real subprocess (only for paths that never hit the network)."""
    env = dict(os.environ)
    env.pop("LLMSTACK_GPU_COUNT", None)
    if gpus is not None:
        env["LLMSTACK_GPU_COUNT"] = str(gpus)
    if home is not None:
        env["HOME"] = str(home)
    p = subprocess.run([sys.executable, str(llmctl or LLMCTL), *args], env=env,
                       capture_output=True, text=True, timeout=60, cwd=cwd)
    return p


def _fixture_run(args, gpus=None, tweak=None):
    with tempfile.TemporaryDirectory() as td:
        return run(args, gpus=gpus, config=_fixture_file(Path(td)), tweak=tweak)


def _break_import(mod):
    mod.llmhw, mod.LLMHW_ERROR = None, "ImportError: simulated"


def _detect_none(mod):
    class Fake:
        detect = staticmethod(lambda n=None, **k: {
            "gpu_count": None, "vram_gib_per_gpu": [], "host_ram_gib": 188.0,
            "source": "none", "ignored_devices": 0})
        parse_requires = staticmethod(llmhw.parse_requires)
        supports = staticmethod(llmhw.supports)
    mod.llmhw = Fake


def _detect_raises(mod):
    class Fake:
        @staticmethod
        def detect(n=None, **k):
            raise RuntimeError("boom")
        parse_requires = staticmethod(llmhw.parse_requires)
        supports = staticmethod(llmhw.supports)
    mod.llmhw = Fake


# ── hw: real config at 4 / 2 / 1 GPUs ───────────────────────────────────────

def _real_hw_json(n):
    p = sub(["hw", "--json"], gpus=n)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_hw_json_shape():
    data = _real_hw_json(2)
    assert set(data) == {"hw", "profiles"}
    assert data["hw"]["gpu_count"] == 2 and data["hw"]["source"] == "override"
    assert data["profiles"], "no profiles"
    for name, e in data["profiles"].items():
        assert set(e) == {"ok", "tp_or_split", "estimate", "reasons", "requires"}, name
        assert isinstance(e["ok"], bool) and isinstance(e["estimate"], bool)
        assert isinstance(e["reasons"], list)
        assert e["ok"] == (not e["reasons"])
        assert e["ok"] or e["tp_or_split"] is None


def test_hw_json_matches_llmhw_at_4_2_1():
    text = REAL_CONFIG.read_text()
    reqs = llmhw.parse_requires(text)
    for n in (4, 2, 1):
        data = _real_hw_json(n)
        for name, e in data["profiles"].items():
            ok, tp, reasons = llmhw.supports(reqs.get(name), data["hw"])
            assert (e["ok"], e["tp_or_split"], e["reasons"]) == (ok, tp, reasons), (n, name)
            assert e["requires"] == reqs.get(name)


def test_hw_known_profiles_per_count():
    p1, p2, p4 = (_real_hw_json(n)["profiles"] for n in (1, 2, 4))
    # vLLM TP profiles need >= 2 cards; llama-server min_gpus 1 profiles run anywhere.
    assert not p1["qwen3.8-27b-code"]["ok"]
    assert "detected 1" in p1["qwen3.8-27b-code"]["reasons"][0]
    assert p1["gemma4-12b-q4"]["ok"] and p1["gemma4-12b-q4"]["tp_or_split"] == 1
    assert p2["qwen3.8-27b-code"]["ok"] and p2["qwen3.8-27b-code"]["tp_or_split"] == 2
    assert not p2["qwen3.8-flash-next-vllm"]["ok"]
    assert p2["gemma4-12b-q4"]["tp_or_split"] == 2
    assert p4["qwen3.8-27b-code"]["tp_or_split"] == 4


def test_hw_text_output():
    p = sub(["hw"], gpus=2)
    assert p.returncode == 0, p.stderr
    out = p.stdout
    assert re.search(r"^GPUs:\s+2 \(override\)$", out, re.M), out
    assert re.search(r"^Host RAM:", out, re.M), out
    assert "simulation only" in out
    rows = {l.split()[0]: l for l in out.splitlines() if re.match(r"^\S+\s+(OK|NO)\s", l)}
    assert re.search(r"\bOK\s+TP2\b", rows["qwen3.8-27b-code"]), rows["qwen3.8-27b-code"]
    assert re.search(r"\bNO\s+-", rows["qwen3.8-flash-next-vllm"])
    assert "needs gpus [4], detected 2" in rows["qwen3.8-flash-next-vllm"]
    assert any("(estimate)" in l for l in rows.values())
    assert re.search(r"\bOK\s+split 2\b", rows["gemma4-12b-q4"])


def test_gpu_count_flag_and_env_precedence():
    p = sub(["--gpu-count", "1", "hw", "--json"], gpus=4)
    assert json.loads(p.stdout)["hw"]["gpu_count"] == 1       # flag beats env
    p = sub(["hw", "--gpu-count=3", "--json"])
    assert json.loads(p.stdout)["hw"]["gpu_count"] == 3
    p = sub(["--gpu-count", "x", "hw"])
    assert p.returncode == 1 and "--gpu-count" in p.stderr


def test_invalid_env_value_warns_and_is_ignored():
    r = run(["hw", "--json"], gpus="abc")
    assert "LLMSTACK_GPU_COUNT" in r.err and "ignoring" in r.err
    assert r.err.count("llmctl: warning") >= 1
    # fell back to real detection: whatever it found, it is not the bad override
    assert json.loads(r.out)["hw"]["source"] != "override"


def test_runs_through_symlink_from_other_cwd():
    with tempfile.TemporaryDirectory() as td:
        link = Path(td) / "llmctl"
        link.symlink_to(LLMCTL)
        p = sub(["hw", "--json"], gpus=2, llmctl=link, cwd=td)
        assert p.returncode == 0, p.stderr
        assert json.loads(p.stdout)["hw"]["gpu_count"] == 2
        assert "warning" not in p.stderr


# ── list ────────────────────────────────────────────────────────────────────

def _ram_known():
    return llmhw.detect(2)["host_ram_gib"] is not None


def test_list_default_hides_unsupported():
    r = _fixture_run(["list"], gpus=2)
    assert r.code == 0, r.err
    lines = r.out.splitlines()
    # 2 GPUs hides big and triple; "hungry" (99999 GiB RAM) is hidden whenever MemTotal is known
    shown, hidden = (3, 3) if _ram_known() else (4, 2)
    assert lines[0] == f"Profiles ({shown})  [* = loaded]:"
    assert "  mid  (aliases: midalias)" in lines          # existing line format, untouched
    assert "  anyone" in lines
    assert "  nometa  (aliases: plain)" in lines
    names = [l.split()[0] for l in lines[1:-1]]
    assert "big" not in names and "triple" not in names
    assert lines[-1] == (f"{hidden} profile(s) hidden (need more GPUs/RAM): "
                         "use 'llmctl list --all' to show them")


def test_list_all_marks_unsupported_with_reason():
    r = _fixture_run(["list", "--all"], gpus=2)
    lines = r.out.splitlines()
    assert lines[0] == "Profiles (6)  [* = loaded]:"
    big = next(l for l in lines if l.startswith("  big"))
    assert big == "  big  (aliases: bigalias, bigger)  [UNSUPPORTED: needs gpus [4], detected 2]"
    assert next(l for l in lines if l.startswith("  mid")) == "  mid  (aliases: midalias)"
    assert "[UNSUPPORTED: needs min_gpus 3, detected 2]" in next(
        l for l in lines if l.startswith("  triple"))
    assert not any("hidden" in l for l in lines)


def test_list_all_supported_at_4_gpus_has_no_hidden_line():
    r = _fixture_run(["list"], gpus=4)
    assert "triple" in r.out and "big" in r.out
    assert ("hungry" not in r.out) == _ram_known()
    r2 = _fixture_run(["list"], gpus=4, tweak=_break_import)
    assert "hidden" not in r2.out


def test_list_real_config_at_one_gpu():
    r = run(["list", "--all"], gpus=1)
    assert r.code == 0
    n = len([l for l in r.out.splitlines() if l.startswith("  ")])
    assert f"Profiles ({n})" in r.out
    assert "[UNSUPPORTED: needs gpus" in r.out
    d = run(["list"], gpus=1)
    assert "hidden" in d.out and d.out.count("\n") < r.out.count("\n")


def test_pick_choices_filter():
    mod = _load_llmctl()
    with tempfile.TemporaryDirectory() as td:
        mod.CONFIG_FILE = _fixture_file(Path(td))
        os.environ["LLMSTACK_GPU_COUNT"] = "1"
        try:
            ids, lines, hidden = mod._pick_choices(False)
            assert {"anyone", "nometa"} <= set(ids)
            assert not {"big", "mid", "triple"} & set(ids)
            assert hidden == 6 - len(ids)
            ids_all, lines_all, hidden_all = mod._pick_choices(True)
            assert hidden_all == 0 and len(ids_all) == 6
            assert [l.split()[0] for l in lines_all] == ids_all
            assert any("unsupported" in l for l in lines_all if l.startswith("big"))
        finally:
            os.environ.pop("LLMSTACK_GPU_COUNT", None)


# ── swap ────────────────────────────────────────────────────────────────────

def test_swap_refused_exit_2_subprocess_real_config():
    with tempfile.TemporaryDirectory() as td:
        p = sub(["swap", "qwen3.8-27b-code"], gpus=1, home=td)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "needs gpus [2, 4], detected 1" in p.stderr
    assert "Detected: 1 GPU (override)" in p.stderr
    assert "--force" in p.stderr and "LLMSTACK_GPU_COUNT" in p.stderr and "simulate" in p.stderr
    assert p.stdout == ""          # nothing printed as if a swap had started


def test_swap_alias_to_unsupported_profile_refused():
    with tempfile.TemporaryDirectory() as td:
        p = sub(["swap", "qwen3.8"], gpus=1, home=td)      # alias of qwen3.8-27b-code
    assert p.returncode == 2, p.stderr
    assert "'qwen3.8' (profile 'qwen3.8-27b-code')" in p.stderr


def test_swap_refusal_in_process_never_touches_router():
    r = _fixture_run(["swap", "bigger"], gpus=2)
    assert r.code == 2
    assert "'bigger' (profile 'big')" in r.err
    assert "needs gpus [4], detected 2" in r.err
    assert r.http_calls == []
    assert "Warming up" not in r.out


def test_swap_force_proceeds_past_check_without_router():
    r = _fixture_run(["swap", "--force", "big"], gpus=2)
    # past the hardware check -> stops at the usual "router not running" exit 1
    assert r.code == 1, (r.code, r.out, r.err)
    assert "llama-swap is not running" in r.out
    assert "--force" in r.err and "needs gpus [4], detected 2" in r.err
    assert r.http_calls == []
    r = _fixture_run(["swap", "big", "--force"], gpus=2)       # flag position is free
    assert r.code == 1 and "llama-swap is not running" in r.out


def test_swap_supported_unknown_and_no_requires_are_allowed():
    for name in ("mid", "midalias", "anyone", "nometa", "plain", "not-a-profile"):
        r = _fixture_run(["swap", name], gpus=2)
        assert r.code == 1 and "llama-swap is not running" in r.out, (name, r.out, r.err)
        assert r.err == "", (name, r.err)
    r = _fixture_run(["swap", "nometa"], gpus=1)               # no requires: any count
    assert r.code == 1 and "not running" in r.out


def test_swap_usage_without_profile():
    r = _fixture_run(["swap"], gpus=2)
    assert r.code == 1 and "Usage: llmctl swap [--force] <profile>" in r.out


def test_refusal_wording_estimate_and_override_note():
    r = _fixture_run(["swap", "big"], gpus=2)                  # override + estimate
    assert r.code == 2
    assert "does not meet its hardware requirements" in r.err
    assert "will probably fail to start" in r.err
    assert "estimate" in r.err
    assert "LLMSTACK_GPU_COUNT / --gpu-count only simulate" in r.err
    r = _fixture_run(["swap", "triple"], gpus=2)               # override, not an estimate
    assert r.code == 2 and "estimate" not in r.err


def _real_hw_low_ram(mod):
    class Fake:
        detect = staticmethod(lambda n=None, **k: {
            "gpu_count": 4, "vram_gib_per_gpu": [32.0] * 4, "host_ram_gib": 64.0,
            "source": "sysfs", "ignored_devices": 0})
        parse_requires = staticmethod(llmhw.parse_requires)
        supports = staticmethod(llmhw.supports)
    mod.llmhw = Fake


def test_refusal_omits_override_note_on_real_hardware():
    r = _fixture_run(["swap", "hungry"], gpus=None, tweak=_real_hw_low_ram)
    assert r.code == 2, (r.code, r.out, r.err)
    assert "host RAM" in r.err or "host_ram" in r.err
    assert "LLMSTACK_GPU_COUNT" not in r.err and "simulate" not in r.err


def test_force_warning_wording():
    r = _fixture_run(["swap", "--force", "big"], gpus=2)
    assert "warning: --force: 'big' does not meet its requirements (needs gpus [4], detected 2); expect the start to fail" in r.err


def test_bench_refuses_unsupported_profile_but_not_with_force():
    def tweak(mod):
        mod.BENCH_SCRIPT = Path(__file__)               # exists, never executed (see below)
        mod.subprocess = types.SimpleNamespace(run=lambda *a, **k: (_ for _ in ()).throw(AssertionError("bench ran")))
    r = _fixture_run(["bench", "big"], gpus=2, tweak=tweak)
    assert r.code == 2 and "does not meet its hardware requirements" in r.err
    ran = []

    def tweak_ok(mod):
        mod.BENCH_SCRIPT = Path(__file__)
        mod.subprocess = types.SimpleNamespace(run=lambda *a, **k: ran.append(a))
    r = _fixture_run(["bench", "--force", "big"], gpus=2, tweak=tweak_ok)
    assert r.code == 0 and len(ran) == 1
    r = _fixture_run(["bench", "mid"], gpus=2, tweak=tweak_ok)
    assert r.code == 0 and len(ran) == 2


def test_hw_without_llmhw_says_cannot_report():
    r = _fixture_run(["hw"], gpus=2, tweak=_break_import)
    assert r.code == 1 and "cannot report hardware" in r.err
    assert "all profiles allowed" not in r.err
    r = _fixture_run(["hw", "--json"], gpus=2, tweak=_break_import)
    assert r.code == 1 and json.loads(r.out) == {"hw": None, "profiles": {}}


def test_help_docstring_keeps_command_list_contiguous():
    doc = _load_llmctl().__doc__
    last_cmd = doc.index("llmctl proxy-status")
    assert doc.index("Hardware checks read") > last_cmd
    assert doc.index("llmctl logs") < doc.index("Hardware checks read")


def test_check_swap_allowed_function():
    mod = _load_llmctl()
    with tempfile.TemporaryDirectory() as td:
        mod.CONFIG_FILE = _fixture_file(Path(td))
        mod._http = lambda *a, **k: (_ for _ in ()).throw(AssertionError("router contacted"))
        os.environ["LLMSTACK_GPU_COUNT"] = "2"
        try:
            ok, entry, hw = mod.check_swap_allowed("bigalias")
            assert ok is False and entry["id"] == "big" and hw["gpu_count"] == 2
            assert mod.check_swap_allowed("mid")[0] is True
            assert mod.check_swap_allowed("zzz")[0] is True and mod.check_swap_allowed("zzz")[1] is None
        finally:
            os.environ.pop("LLMSTACK_GPU_COUNT", None)


# ── fail open ───────────────────────────────────────────────────────────────

def _assert_fails_open(tweak):
    r = _fixture_run(["list"], gpus=1, tweak=tweak)
    lines = r.out.splitlines()
    assert lines[0] == "Profiles (6)  [* = loaded]:", r.out      # nothing hidden
    assert "hidden" not in r.out
    assert r.err.count("llmctl: warning") == 1, r.err
    s = _fixture_run(["swap", "big"], gpus=1, tweak=tweak)
    assert s.code == 1 and "llama-swap is not running" in s.out, (s.code, s.out, s.err)
    assert s.err.count("llmctl: warning") == 1, s.err
    assert "cannot run" not in s.err


def test_fail_open_llmhw_import_failure():
    _assert_fails_open(_break_import)
    r = _fixture_run(["list"], gpus=1, tweak=_break_import)
    assert "llmhw.py unavailable" in r.err and "simulated" in r.err


def test_fail_open_gpu_count_not_detected():
    _assert_fails_open(_detect_none)
    r = _fixture_run(["list"], tweak=_detect_none)
    assert "GPU count not detected" in r.err


def test_fail_open_detect_raises():
    _assert_fails_open(_detect_raises)


def test_fail_open_output_identical_to_pre_hardware_format():
    broken = _fixture_run(["list"], gpus=1, tweak=_break_import)
    assert broken.out == (
        "Profiles (6)  [* = loaded]:\n"
        "  big  (aliases: bigalias, bigger)\n"
        "  mid  (aliases: midalias)\n"
        "  anyone\n"
        "  triple\n"
        "  hungry\n"
        "  nometa  (aliases: plain)\n")


def test_hw_command_without_llmhw_exits_1_with_warning():
    r = _fixture_run(["hw"], gpus=2, tweak=_break_import)
    assert r.code == 1 and "unavailable" in r.err


def test_fail_open_when_scripts_dir_is_missing_subprocess():
    """A checkout copy with no scripts/llmhw.py: llmctl still works, warns once."""
    with tempfile.TemporaryDirectory() as td:
        tree = Path(td) / "stack"
        (tree / "bin").mkdir(parents=True)
        (tree / "config").mkdir()
        shutil.copy(LLMCTL, tree / "bin" / "llmctl")
        (tree / "config" / "models.yaml").write_text(FIXTURE)
        home = Path(td) / "home"
        home.mkdir()
        p = sub(["swap", "big"], gpus=1, llmctl=tree / "bin" / "llmctl", home=home)
        assert p.returncode == 1, (p.stdout, p.stderr)       # "not running", not a refusal
        assert "llama-swap is not running" in p.stdout
        assert p.stderr.count("llmctl: warning") == 1 and "llmhw.py unavailable" in p.stderr
        assert "Traceback" not in p.stderr


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
