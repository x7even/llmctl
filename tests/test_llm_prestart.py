#!/usr/bin/env python3
"""
Unit tests for scripts/llm-prestart (host-RAM guard in front of the Flash-Next vLLM launch):
eviction stops at the target, --keep is skipped, it exec's the wrapped command with its
arguments intact, and it never blocks a launch (bad root, bad usage handled).

Run:  python3 tests/test_llm_prestart.py        (also pytest-compatible)
"""
import importlib.machinery
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "llm-prestart"

_loader = importlib.machinery.SourceFileLoader("llm_prestart", str(SCRIPT))
_spec = importlib.util.spec_from_loader("llm_prestart", _loader)
prestart = importlib.util.module_from_spec(_spec)
_loader.exec_module(prestart)


def _tree(root, spec):
    for rel, size in spec.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * size)


class _Free:
    """free_fn whose value rises by `step` GiB each time a file is evicted (fadvise is monkeypatched)."""

    def __init__(self, start, step):
        self.value, self.step, self.touched = start, step, []

    def __call__(self):
        return self.value

    def advise(self, fd, off, length, advice):
        self.touched.append(os.readlink(f"/proc/self/fd/{fd}"))
        self.value += self.step


def _run_evict(spec, start, step, need, keep=()):
    free = _Free(start, step)
    real = os.posix_fadvise
    os.posix_fadvise = free.advise
    try:
        with tempfile.TemporaryDirectory() as d:
            _tree(d, spec)
            files, _ = prestart.evict(d, [os.path.join(d, k) for k in keep], need, free_fn=free)
            touched = [os.path.relpath(p, d) for p in free.touched]
    finally:
        os.posix_fadvise = real
    return files, touched, free.value


def test_evict_stops_once_target_reached():
    files, touched, value = _run_evict({f"m/f{i}": 10 for i in range(10)}, start=20, step=20, need=80)
    assert files == 3 and len(touched) == 3 and value == 80


def test_evict_noop_when_already_free():
    files, touched, _ = _run_evict({"m/a": 10}, start=90, step=20, need=80)
    assert files == 0 and touched == []


def test_evict_skips_keep_dir_and_reports_shortfall_honestly():
    files, touched, value = _run_evict({"keep/a": 10, "keep/sub/b": 10, "other/c": 10}, start=0, step=5, need=80,
                                       keep=["keep"])
    assert touched == ["other/c"] and files == 1 and value == 5  # target not reachable: returns what it could do


def test_evict_keep_is_path_prefix_not_string_prefix():
    # 'keep' must not shield 'keepsake/...'
    _, touched, _ = _run_evict({"keep/a": 10, "keepsake/b": 10}, start=0, step=1, need=80, keep=["keep"])
    assert touched == ["keepsake/b"]


def test_evict_survives_unreadable_files():
    with tempfile.TemporaryDirectory() as d:
        _tree(d, {"a": 5})
        os.symlink(os.path.join(d, "missing"), os.path.join(d, "dangling"))
        files, _ = prestart.evict(d, [], 10**9, free_fn=lambda: 0.0)  # real fadvise on a real file, never reaches target
        assert files == 1


def _wrapper(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60)


def test_wrapper_execs_command_with_arguments_intact():
    r = _wrapper("--need-free-gib", "1", "--", sys.executable, "-c", "import sys; print(sys.argv[1:])", "a b", "--flag", "--")
    assert r.returncode == 0
    assert r.stdout.strip() == "['a b', '--flag', '--']"
    assert "llm-prestart: MemFree" in r.stderr and "ok" in r.stderr


def test_wrapper_propagates_exit_code():
    r = _wrapper("--", sys.executable, "-c", "raise SystemExit(7)")
    assert r.returncode == 7


def test_wrapper_never_blocks_launch_on_bad_root():
    with tempfile.TemporaryDirectory() as d:
        r = _wrapper("--need-free-gib", "100000", "--root", os.path.join(d, "does-not-exist"), "--",
                     sys.executable, "-c", "print('launched')")
    assert r.returncode == 0 and r.stdout.strip() == "launched"
    assert "still below target" in r.stderr


def test_wrapper_usage_errors():
    assert _wrapper("--need-free-gib", "1").returncode != 0           # no '--'
    assert _wrapper("--need-free-gib", "1", "--").returncode != 0     # nothing to exec


def test_flash_next_profile_uses_wrapper_in_front_of_podman():
    text = (REPO / "config" / "models.yaml").read_text()
    m = re.search(r"^  qwen3\.8-flash-next-vllm:\n(.*?)(?=^  [a-z0-9][^\n]*:\n|\Z)", text, re.S | re.M)
    cmd = re.search(r"^    cmd: \|\n((?:      .*\n|\n)+)", m.group(0), re.M).group(1)
    toks = cmd.split()
    assert toks[0].endswith("/scripts/llm-prestart")
    assert "--need-free-gib" in toks and "--" in toks
    sep = toks.index("--")
    assert toks[sep + 1:sep + 3] == ["podman", "run"]
    keep = toks[toks.index("--keep") + 1]
    assert f"/models/{keep.split('/mnt/models/llm/')[1]}" in cmd  # --keep names the model dir the profile serves


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, "-", repr(e))
    sys.exit(1 if fails else 0)
