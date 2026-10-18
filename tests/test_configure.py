#!/usr/bin/env python3
"""
Unit tests for scripts/configure (TP rounding, requires read from models.yaml,
auto-managed `unlisted` marker lines). Hardware detection and parse_requires
have their own tests in tests/test_llmhw.py.

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
llmhw = cfg.llmhw

MARK = "# llmstack:auto"

# Small fixture: one profile of each kind + a commented template tail.
FIXTURE = """\
healthCheckTimeout: 2100

models:

  # comment mentioning --tensor-parallel-size 4 must never be rewritten
  qwen3.8-27b-code:
    name: "27B"
    metadata:
      requires:
        gpus: [2, 4]
        note: "measured: TP2 works"
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
    name: "flash"
    metadata:
      requires:
        gpus: [4]
        host_ram_gib: 96
        vram_total_gib: 66
        note: "TP4+EP only"
    cmd: |
      podman run --rm
        vllm serve /models/y
        --tensor-parallel-size 4
        --enable-expert-parallel
        --cudagraph-capture-sizes 1 2 4 8
    cmdStop: podman stop y

  qwen3.8-flash-next:
    name: "flash gguf"
    metadata:
      requires:
        min_gpus: 3
        estimate: true
    cmd: |
      llama-server
        --tensor-split 1,1,1,1
        --ctx-size 1024
    cmdStop: podman stop z

  gemma4-12b-q4:
    name: "small"
    metadata:
      requires:
        min_gpus: 1
    cmd: |
      llama-server
        --tensor-split 1,1,1,1
    cmdStop: podman stop w

  brand-new-profile:
    name: "no metadata"
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


def _hw(n, ram=188.0):
    return {"gpu_count": n, "vram_gib_per_gpu": [], "host_ram_gib": ram,
            "source": "test", "ignored_devices": 0}


def _patched(n, text=FIXTURE, ram=188.0):
    return cfg.patch(text, _hw(n, ram), "/opt/llmstack")


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


def _marker_lines(text, name):
    return [l for l in _block(text, name).splitlines() if MARK in l]


def _unlisted_lines(text, name):
    return [l for l in _block(text, name).splitlines() if l.startswith("    unlisted:")]


def _without_markers(block):
    return "".join(l for l in block.splitlines(keepends=True) if MARK not in l)


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
    # qwen3.8-27b-code: gpus [2,4]. flash-next-vllm: gpus [4].
    for n, tp27, flash_ok in [(2, 2, False), (3, 2, False), (4, 4, True), (8, 4, True)]:
        out, res = _patched(n)
        st = _status(res)
        assert _tp(out, "qwen3.8-27b-code") == tp27, n
        assert st["qwen3.8-27b-code"].status == "ok"
        assert (st["qwen3.8-flash-next-vllm"].status == "ok") == flash_ok, n
        if flash_ok:
            assert _tp(out, "qwen3.8-flash-next-vllm") == 4


def test_tp1_infeasible_for_27b_and_cmd_untouched():
    out, res = _patched(1)
    st = _status(res)
    assert st["qwen3.8-27b-code"].status == "infeasible"
    # No bogus TP written: block identical to the placeholder-substituted input
    # apart from the one auto-managed marker line.
    base = FIXTURE.replace("__LLMSTACK_DIR__", "/opt/llmstack")
    assert _without_markers(_block(out, "qwen3.8-27b-code")) == _block(base, "qwen3.8-27b-code")
    assert _tp(out, "qwen3.8-27b-code") == 4
    assert "--enable-expert-parallel" in _block(out, "qwen3.8-27b-code")


def test_expert_parallel_flag_never_stripped_and_reconfigure_roundtrips():
    # A profile without metadata (permissive, default TP sizes) at TP1 keeps
    # --enable-expert-parallel, so reconfiguring for a larger count loses nothing.
    text = FIXTURE.replace("  brand-new-profile:\n    name: \"no metadata\"\n    cmd: |\n      vllm serve /models/q\n",
                           "  brand-new-profile:\n    name: \"no metadata\"\n    cmd: |\n      vllm serve /models/q\n"
                           "        --enable-expert-parallel\n")
    out1, res1 = cfg.patch(text, _hw(1), "/x")
    assert _status(res1)["brand-new-profile"].status == "ok"
    assert _tp(out1, "brand-new-profile") == 1
    assert "--enable-expert-parallel" in _block(out1, "brand-new-profile")
    out4, _ = cfg.patch(out1, _hw(4), "/x")
    assert _tp(out4, "brand-new-profile") == 4
    assert "--enable-expert-parallel" in _block(out4, "brand-new-profile")


def test_column0_comment_between_profiles_does_not_truncate_parsing():
    text = FIXTURE.replace("\n  qwen3.8-flash-next-vllm:", "\n# stray column-0 comment\n  qwen3.8-flash-next-vllm:", 1)
    assert "# stray column-0 comment" in text
    _, profiles, _ = cfg.split_profiles(text)
    _, base_profiles, _ = cfg.split_profiles(FIXTURE)
    assert [n for n, _ in profiles] == [n for n, _ in base_profiles]
    out, res = cfg.patch(text, _hw(4), "/x")
    assert len(res) == len(base_profiles) >= 3
    assert "# stray column-0 comment" in out
    assert _status(res)["qwen3.8-flash-next-vllm"].requires["gpus"] == [4]


def test_idle_card_warning_when_tp_below_n():
    for n in (3, 5, 6, 7, 8):
        _, res = _patched(n)
        s = cfg.format_summary(_hw(n), res)
        assert "idle" in s, n
    _, res = _patched(4)
    ok4 = [r for r in res if r.status == "ok" and r.kind == "vllm" and r.tp == 4]
    assert "idle" not in cfg.format_summary(_hw(4), ok4)
    _, res2 = _patched(2)
    assert "idle" not in cfg.format_summary(_hw(2), res2)


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
    # flash-next GGUF needs min_gpus 3 -> OK at 3 with a 3-way split (no TP rounding).
    assert _status(res3)["qwen3.8-flash-next"].status == "ok"
    assert _split(out3, "qwen3.8-flash-next") == "1,1,1"


def test_gguf_n1_keeps_reversible_flag():
    out, res = _patched(1)
    assert _split(out, "gemma4-12b-q4") == "1"
    back, _ = cfg.patch(out, _hw(4), "/opt/llmstack")
    assert _split(back, "gemma4-12b-q4") == "1,1,1,1"


# ── Requires come from models.yaml ──────────────────────────────────────────

def test_requires_read_from_yaml_not_code():
    assert not hasattr(cfg, "PROFILE_REQUIREMENTS")
    # Same profile name, different metadata -> different verdict.
    text = FIXTURE.replace("gpus: [2, 4]\n        note: \"measured: TP2 works\"", "gpus: [4]")
    _, res = _patched(2, text)
    assert _status(res)["qwen3.8-27b-code"].status == "infeasible"
    _, res = _patched(2)
    assert _status(res)["qwen3.8-27b-code"].status == "ok"


def test_minimums_reporting():
    _, res = _patched(2)
    st = _status(res)
    assert st["qwen3.8-flash-next"].status == "infeasible"       # GGUF min_gpus 3
    assert st["qwen3.8-flash-next-vllm"].status == "infeasible"  # gpus [4]
    assert st["gemma4-12b-q4"].status == "ok"
    s = cfg.format_summary(_hw(2), res)
    assert "SKIP qwen3.8-flash-next " in s
    assert "needs min_gpus 3, detected 2" in s
    assert "needs gpus [4], detected 2" in s
    assert "llmstack:auto" in s
    assert "(estimate)" in s


def test_unknown_profile_permissive_and_flagged():
    out, res = _patched(1)
    st = _status(res)
    assert st["brand-new-profile"].status == "ok" and st["brand-new-profile"].tp == 1
    assert _marker_lines(out, "brand-new-profile") == []
    s = cfg.format_summary(_hw(1), res)
    assert "brand-new-profile has no metadata.requires block" in s


def test_real_config_profiles_all_have_requires_and_known_values():
    text = (REPO / "config" / "models.yaml").read_text()
    _, profiles, _ = cfg.split_profiles(text)
    names = [n for n, _ in profiles]
    assert len(names) == 12, names
    req = llmhw.parse_requires(text)
    missing = [n for n in names if n not in req]
    assert not missing, f"profiles without metadata.requires: {missing}"
    for n, lines in profiles:
        assert cfg.block_kind(lines) in ("vllm", "gguf"), n
    for k in ("qwen3.8-27b-code", "qwen3.8-27b-think", "qwen3.8-27b-fast"):
        assert req[k]["gpus"] == [2, 4] and not req[k].get("estimate")
    assert req["qwen3.8-flash-next-vllm"]["gpus"] == [4]
    assert req["qwen3.8-flash-next-vllm"]["host_ram_gib"] == 96
    assert req["qwen3.8-flash-next"]["min_gpus"] == 2 and not req["qwen3.8-flash-next"].get("estimate")
    assert req["gemma4-26b-a4b"]["gpus"] == [4] and not req["gemma4-26b-a4b"].get("estimate")
    assert req["gemma4-26b-fp8"]["gpus"] == [2, 4] and not req["gemma4-26b-fp8"].get("estimate")
    assert req["qwen3.8-flash-next-vllm"]["vram_total_gib"] == 75
    assert not req["qwen3.8-flash-next-vllm"].get("estimate")
    assert req["gemma4-26b-q8"]["min_gpus"] == 1 and req["gemma4-12b-q4"]["min_gpus"] == 1
    for k in ("qwen3.6-35b-code", "qwen3.6-35b-128k-nomtp", "qwen3.6-35b-fast"):
        assert req[k]["gpus"] == [2, 4] and not req[k].get("estimate")


# ── Host RAM ────────────────────────────────────────────────────────────────

def test_host_ram_makes_profile_unsupported_with_reason():
    out, res = _patched(4, ram=188.0)
    assert _status(res)["qwen3.8-flash-next-vllm"].status == "ok"
    out, res = _patched(4, ram=94.0)                     # a 96 GB box reports ~94 GiB
    assert _status(res)["qwen3.8-flash-next-vllm"].status == "ok"
    out, res = _patched(4, ram=64.0)
    r = _status(res)["qwen3.8-flash-next-vllm"]
    assert r.status == "infeasible" and "64 GiB" in r.reason and "96" in r.reason
    assert len(_marker_lines(out, "qwen3.8-flash-next-vllm")) == 1


def test_host_ram_unreadable_warns_but_stays_supported():
    out, res = _patched(4, ram=None)
    r = _status(res)["qwen3.8-flash-next-vllm"]
    assert r.status == "ok" and r.warnings
    assert "could not read MemTotal" in cfg.format_summary(_hw(4, None), res)
    assert _marker_lines(out, "qwen3.8-flash-next-vllm") == []


# ── Auto-managed unlisted marker ────────────────────────────────────────────

def test_marker_added_on_unsupported_with_reason_text():
    out, _ = _patched(2)
    assert _marker_lines(out, "qwen3.8-flash-next-vllm") == [
        f"    unlisted: true  {MARK} - needs gpus [4], detected 2"]
    assert _marker_lines(out, "qwen3.8-flash-next") == [
        f"    unlisted: true  {MARK} - needs min_gpus 3, detected 2"]
    assert _marker_lines(out, "qwen3.8-27b-code") == []
    assert _marker_lines(out, "gemma4-12b-q4") == []
    # directly among the profile's own keys, just before cmd:
    blk = _block(out, "qwen3.8-flash-next-vllm").splitlines()
    i = next(k for k, l in enumerate(blk) if MARK in l)
    assert blk[i + 1].startswith("    cmd:")


def test_marker_removed_when_profile_becomes_supported():
    out2, _ = _patched(2)
    assert _marker_lines(out2, "qwen3.8-flash-next-vllm")
    out4, _ = cfg.patch(out2, _hw(4), "/opt/llmstack")
    assert MARK not in out4
    assert out4 == _patched(4)[0]                        # back to the fresh 4-GPU result


def test_marker_reason_refreshed_when_count_changes():
    out2, _ = _patched(2)
    out1, _ = cfg.patch(out2, _hw(1), "/opt/llmstack")
    assert _marker_lines(out1, "qwen3.8-flash-next-vllm") == [
        f"    unlisted: true  {MARK} - needs gpus [4], detected 1"]
    assert len(_unlisted_lines(out1, "qwen3.8-flash-next-vllm")) == 1


def test_hand_written_unlisted_untouched_and_not_doubled():
    hand = "    unlisted: true\n"
    text = FIXTURE.replace("  qwen3.8-flash-next-vllm:\n    name: \"flash\"\n",
                           "  qwen3.8-flash-next-vllm:\n    name: \"flash\"\n" + hand)
    assert hand in text
    # unsupported + hand-unlisted: no second line, hand line kept
    out2, res = _patched(2, text)
    assert _unlisted_lines(out2, "qwen3.8-flash-next-vllm") == ["    unlisted: true"]
    assert _marker_lines(out2, "qwen3.8-flash-next-vllm") == []
    assert _status(res)["qwen3.8-flash-next-vllm"].status == "infeasible"
    # supported + hand-unlisted: hand line must survive
    out4, _ = _patched(4, text)
    assert _unlisted_lines(out4, "qwen3.8-flash-next-vllm") == ["    unlisted: true"]
    # hand line in one profile, marker in another: going back to 4 GPUs removes
    # only the marker line; the hand-written one survives.
    assert _marker_lines(out2, "qwen3.8-flash-next")
    out_b, _ = cfg.patch(out2, _hw(4), "/opt/llmstack")
    assert MARK not in out_b
    assert _unlisted_lines(out_b, "qwen3.8-flash-next-vllm") == ["    unlisted: true"]


def _with_hand(line, name="qwen3.8-flash-next-vllm"):
    head = f"  {name}:\n    name: \"flash\"\n"
    assert head in FIXTURE
    return FIXTURE.replace(head, head + line)


def test_hand_written_unlisted_false_stays_listed_with_warning():
    text = _with_hand("    unlisted: false\n")
    out, res = _patched(2, text)
    r = _status(res)["qwen3.8-flash-next-vllm"]
    assert r.status == "infeasible" and r.marker == "hand-listed"
    assert _unlisted_lines(out, "qwen3.8-flash-next-vllm") == ["    unlisted: false"]   # not touched, not doubled
    assert any("explicitly listed" in w for w in r.warnings)
    s = cfg.format_summary(_hw(2), res)
    assert "hand-listed (unlisted: false)" in s and "hand-unlisted" not in s.split("qwen3.8-flash-next-vllm")[1].splitlines()[0]
    assert "WARNING: qwen3.8-flash-next-vllm is unsupported here but explicitly listed" in s
    # a truthy hand line (with a trailing comment) is still 'hand', quoted true included
    for line in ("    unlisted: true  # mine\n", '    unlisted: "true"\n'):
        _, res = _patched(2, _with_hand(line))
        assert _status(res)["qwen3.8-flash-next-vllm"].marker == "hand"
    # supported: nothing changes
    out4, res4 = _patched(4, text)
    assert _unlisted_lines(out4, "qwen3.8-flash-next-vllm") == ["    unlisted: false"]


def test_hand_line_added_after_marker_wins_and_marker_is_dropped():
    # configure (2 GPUs), then the user adds their own unlisted: true; rerun must not leave two keys
    out2, _ = _patched(2)
    assert len(_unlisted_lines(out2, "qwen3.8-flash-next-vllm")) == 1
    head = "  qwen3.8-flash-next-vllm:\n    name: \"flash\"\n"
    for hand, kind in (("    unlisted: true\n", "hand"), ("    unlisted: false\n", "hand-listed")):
        edited = out2.replace(head, head + hand)
        assert len(_unlisted_lines(edited, "qwen3.8-flash-next-vllm")) == 2
        again, res = cfg.patch(edited, _hw(2), "/opt/llmstack")
        assert _unlisted_lines(again, "qwen3.8-flash-next-vllm") == [hand.rstrip("\n")], kind
        assert _marker_lines(again, "qwen3.8-flash-next-vllm") == []
        assert _status(res)["qwen3.8-flash-next-vllm"].marker == kind
        # the other profiles' markers are unaffected, and it is stable on a third run
        assert _marker_lines(again, "qwen3.8-flash-next")
        assert cfg.patch(again, _hw(2), "/opt/llmstack")[0] == again
    # unit level: marker + hand in one block, no cmd needed
    blk = ["  p:\n", "    unlisted: true\n", f"    unlisted: true  {MARK} - old\n", "    cmd: x\n"]
    lines, action = cfg.set_auto_unlisted(blk, "needs gpus [4], detected 2")
    assert action == "hand" and lines == ["  p:\n", "    unlisted: true\n", "    cmd: x\n"]


def test_estimate_requires_plain_true():
    for val, expect in (("true", True), ('"false"', False), ("false", False), ('"true"', False)):
        text = FIXTURE.replace("        min_gpus: 3\n        estimate: true\n",
                               f"        min_gpus: 3\n        estimate: {val}\n")
        _, res = _patched(4, text)
        assert _status(res)["qwen3.8-flash-next"].estimate is expect, val


def test_crlf_file_keeps_crlf_and_roundtrips():
    crlf = FIXTURE.replace("\n", "\r\n")
    base = crlf.replace("__LLMSTACK_DIR__", "/opt/llmstack")
    out2, _ = _patched(2, crlf)
    assert "\n" not in out2.replace("\r\n", ""), "bare LF introduced"
    assert out2.count("\r\n") == out2.count("\n")
    assert _marker_lines(out2.replace("\r\n", "\n"), "qwen3.8-flash-next-vllm")
    assert f"{MARK} - needs gpus [4], detected 2\r\n" in out2
    # 4 -> 2 -> 4 restores the original bytes
    out4, _ = cfg.patch(out2, _hw(4), "/opt/llmstack")
    assert out4 == base
    # idempotent at 2 and a refresh at 1 also keeps CRLF
    assert cfg.patch(out2, _hw(2), "/opt/llmstack")[0] == out2
    out1, _ = cfg.patch(out2, _hw(1), "/opt/llmstack")
    assert "\n" not in out1.replace("\r\n", "") and "detected 1\r\n" in out1


def test_unsupported_cmd_blocks_byte_identical():
    base = FIXTURE.replace("__LLMSTACK_DIR__", "/opt/llmstack")
    for n in (1, 2, 3):
        out, res = _patched(n)
        for r in res:
            if r.status == "infeasible":
                assert _without_markers(_block(out, r.name)) == _block(base, r.name), (n, r.name)


def test_pure_patch_idempotent():
    for n in (1, 2, 3, 4, 8):
        once, _ = _patched(n)
        twice, _ = cfg.patch(once, _hw(n), "/opt/llmstack")
        assert once == twice, n


# ── CLI behaviour (subprocess, temp copy of the real config) ────────────────

def _sandbox():
    td = tempfile.mkdtemp(prefix="configure-test-")
    (Path(td) / "config").mkdir()
    dst = Path(td) / "config" / "models.yaml"
    src = (REPO / "config" / "models.yaml").read_text()
    # The working copy is normally *configured* (scripts/configure has written the real
    # repo root into it), so put the placeholder back to get a realistic fresh-clone input.
    # On an unconfigured checkout this replace simply finds nothing. Deriving the root from
    # REPO rather than hardcoding one machine's path is what makes it work anywhere.
    dst.write_text(src.replace(str(REPO), "__LLMSTACK_DIR__"))
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
        for n in ("1", "2", "3", "4"):
            r = _run("--config", str(conf), "--gpu-count", n, "--dry-run")
            assert r.returncode == 0, r.stderr
            assert "dry run" in r.stdout and f"GPU count: {n}" in r.stdout
            assert _sha(conf) == before
            assert not Path(str(conf) + ".bak").exists()
        r = _run("--config", str(conf), "--gpu-count", "2", "--dry-run")
        assert f"+    unlisted: true  {MARK} - needs gpus [4], detected 2" in r.stdout
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
        assert _marker_lines(first, "qwen3.8-flash-next-vllm")      # needs 4
        assert _marker_lines(first, "gemma4-26b-a4b")               # needs 4
        assert not _marker_lines(first, "qwen3.8-flash-next")       # min_gpus 3 ok
        # second run: no changes, same bytes
        r2 = _run("--config", str(conf), "--gpu-count", "3")
        assert r2.returncode == 0 and "No changes needed" in r2.stdout
        assert conf.read_text() == first
        # reconfigure back to 4: TP, split restored and every marker removed
        _run("--config", str(conf), "--gpu-count", "4")
        again = conf.read_text()
        assert _tp(again, "qwen3.8-27b-code") == 4
        assert _split(again, "gemma4-12b-q4") == "1,1,1,1"
        assert MARK not in again
        assert _run("--config", str(conf), "--gpu-count", "4").stdout.startswith("No changes needed")
    finally:
        shutil.rmtree(td)


def test_cli_crlf_models_yaml_roundtrips_byte_for_byte():
    td, conf = _sandbox()
    try:
        lf = conf.read_bytes()
        conf.write_bytes(lf.replace(b"\n", b"\r\n"))
        assert _run("--config", str(conf), "--gpu-count", "4").returncode == 0
        four = conf.read_bytes()                      # placeholder replaced, still CRLF
        assert b"__LLMSTACK_DIR__" not in four and four.count(b"\r\n") == four.count(b"\n")
        assert _run("--config", str(conf), "--gpu-count", "2").returncode == 0
        two = conf.read_bytes()
        assert b"llmstack:auto" in two and two.count(b"\r\n") == two.count(b"\n")
        assert _run("--config", str(conf), "--gpu-count", "4").returncode == 0
        assert conf.read_bytes() == four
    finally:
        shutil.rmtree(td)


def test_one_gpu_then_four_roundtrips_to_fresh_four():
    td, conf = _sandbox()
    td2, conf2 = _sandbox()
    try:
        assert _run("--config", str(conf), "--gpu-count", "1").returncode == 0
        assert MARK in conf.read_text()
        assert _run("--config", str(conf), "--gpu-count", "4").returncode == 0
        assert _run("--config", str(conf2), "--gpu-count", "4").returncode == 0
        # (each sandbox bakes in its own absolute path; normalise before comparing)
        a = conf.read_text().replace(str(td.resolve()), "<DIR>")
        b = conf2.read_text().replace(str(td2.resolve()), "<DIR>")
        assert "<DIR>" in a and a == b
    finally:
        shutil.rmtree(td)
        shutil.rmtree(td2)


def test_bad_gpu_count_rejected():
    td, conf = _sandbox()
    try:
        r = _run("--config", str(conf), "--gpu-count", "0")
        assert r.returncode != 0
    finally:
        shutil.rmtree(td)


# ── Shipped-config hygiene ─────────────────────────────────────────────────

def test_every_vllm_profile_sets_use_model_name_to_its_served_model_name():
    """A vLLM profile without `useModelName` answers only to its full name.

    llama-swap resolves an alias to pick the backend, then forwards the client's
    `model` string upstream unchanged. vLLM validates that string against its single
    `--served-model-name` and 404s anything else, so every alias of the profile fails
    while the profile itself looks fine. Checked statically because reproducing it
    needs a live backend. llama-server/GGUF profiles are exempt — they do not
    validate the field the same way.
    """
    import yaml  # local: the rest of the suite does not need a yaml dependency

    models = yaml.safe_load((REPO / "config" / "models.yaml").read_text())["models"]
    problems = []
    for name, prof in models.items():
        cmd = prof.get("cmd", "")
        served = re.search(r"--served-model-name\s+(\S+)", cmd)
        if not served:
            continue  # llama-server / GGUF profile
        got = prof.get("useModelName")
        if got is None:
            problems.append(f"{name}: no useModelName (aliases would 404)")
        elif got != served.group(1):
            problems.append(f"{name}: useModelName={got!r} != --served-model-name={served.group(1)!r}")
    assert not problems, "; ".join(problems)


def test_shipped_config_ships_placeholders_not_a_configured_path():
    """The *committed* models.yaml must carry __LLMSTACK_DIR__, never a real path.

    `configure.patch` substitutes with a plain `str.replace` and never checks that
    anything matched, so a models.yaml committed *after* running configure silently
    ships one machine's absolute paths to everyone who clones: the bind mounts point
    at directories that do not exist, the compile cache misses, and boots go from
    ~3 minutes to ~18. This has happened once already, so it gets a guard.

    Reads HEAD rather than the working tree on purpose. A working copy is *supposed*
    to be configured — that is what `scripts/configure` is for — so asserting on the
    file on disk would fail on every correctly set-up machine. The invariant belongs
    to what gets committed. Skips rather than fails where git is unavailable (export
    tarball, vendored copy), since there is nothing to check in that case.
    """
    try:
        src = subprocess.run(["git", "-C", str(REPO), "show", "HEAD:config/models.yaml"],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return  # not a git checkout; nothing committed to inspect
    assert "__LLMSTACK_DIR__" in src, "committed models.yaml has no __LLMSTACK_DIR__ placeholder"
    leaked = [(i + 1, ln) for i, ln in enumerate(src.splitlines())
              if re.search(r"/(home|Users)/", ln)]
    assert not leaked, f"absolute user paths in committed models.yaml: {leaked}"


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
