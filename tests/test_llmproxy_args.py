#!/usr/bin/env python3
"""
Unit tests for the argument-repair logic in bin/llmproxy.

Tests the exact-once invariant: every byte of function.arguments reaches the client
exactly once — via _arg_correction_lines(), never through intermediate chunks.
"""
import importlib.util
import json
import sys
from pathlib import Path

# Load bin/llmproxy (no .py extension) as a module.
import importlib.machinery
_path = str(Path(__file__).parent.parent / "bin" / "llmproxy")
_loader = importlib.machinery.SourceFileLoader("llmproxy", _path)
_spec = importlib.util.spec_from_loader("llmproxy", _loader)
_mod = importlib.util.module_from_spec(_spec)
_loader.exec_module(_mod)

_strip_args_from_line = _mod._strip_args_from_line
_arg_correction_lines = _mod._arg_correction_lines
_repair_args = _mod._repair_args


def _sse(data: dict) -> str:
    return "data: " + json.dumps(data)


def _chunk(idx: int, args_frag: str = None, name: str = None,
           id_: str = None, type_: str = None) -> str:
    tc = {"index": idx}
    if id_ is not None:
        tc["id"] = id_
    if type_ is not None:
        tc["type"] = type_
    fn = {}
    if name is not None:
        fn["name"] = name
    if args_frag is not None:
        fn["arguments"] = args_frag
    if fn:
        tc["function"] = fn
    return _sse({"id": "cmpl-1", "object": "chat.completion.chunk",
                 "choices": [{"index": 0, "delta": {"tool_calls": [tc]}, "finish_reason": None}]})


def _finish_chunk() -> str:
    return _sse({"id": "cmpl-1", "object": "chat.completion.chunk",
                 "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})


# ── _repair_args ──────────────────────────────────────────────────────────────

def test_repair_valid_json_unchanged():
    s = '{"filePath": "/tmp/foo.py"}'
    assert _repair_args(s) == s


def test_repair_trailing_dot_brace():
    raw = '{"filePath": "/tmp/foo.py"}}.'
    repaired = _repair_args(raw)
    assert json.loads(repaired) == {"filePath": "/tmp/foo.py"}


def test_repair_trailing_whitespace_only():
    raw = '{"k": 1}   '
    # raw_decode sees no trailing garbage after stripping whitespace
    repaired = _repair_args(raw)
    assert json.loads(repaired) == {"k": 1}


def test_repair_truncated_json_returned_as_is():
    raw = '{"filePath": "/tmp/foo'  # unterminated string
    result = _repair_args(raw)
    assert result == raw  # can't repair, pass through unchanged


def test_repair_empty_string():
    assert _repair_args("") == ""


# ── _strip_args_from_line ──────────────────────────────────────────────────────

def test_strip_passthrough_non_sse():
    line = "event: ping"
    arg_buf = {}
    out, is_finish, cid = _strip_args_from_line(line, arg_buf)
    assert out == line
    assert not is_finish
    assert arg_buf == {}


def test_strip_passthrough_done():
    line = "data: [DONE]"
    arg_buf = {}
    out, is_finish, cid = _strip_args_from_line(line, arg_buf)
    assert out == line
    assert not is_finish
    assert arg_buf == {}


def test_strip_first_chunk_name_kept_args_buffered():
    """First chunk: name+id+type kept, arguments buffered, line not suppressed."""
    line = _chunk(idx=0, name="read", id_="call_abc", type_="function", args_frag='{"')
    arg_buf = {}
    out, is_finish, cid = _strip_args_from_line(line, arg_buf)
    assert out is not None, "First chunk should not be suppressed"
    assert cid == "cmpl-1"
    # arguments should be buffered, not in the emitted line
    out_data = json.loads(out[6:])
    fn = out_data["choices"][0]["delta"]["tool_calls"][0]["function"]
    assert "arguments" not in fn
    assert fn["name"] == "read"
    assert arg_buf == {0: '{"'}


def test_strip_args_only_chunk_suppressed():
    """Middle args-only chunk: no name/id/type → suppressed (returns None)."""
    line = _chunk(idx=0, args_frag='"filePath": "/tmp/x"}')
    arg_buf = {0: '{"'}
    out, is_finish, cid = _strip_args_from_line(line, arg_buf)
    assert out is None, "Args-only chunk should be suppressed"
    assert arg_buf == {0: '{"' + '"filePath": "/tmp/x"}'}


def test_strip_finish_chunk_detected():
    line = _finish_chunk()
    arg_buf = {}
    out, is_finish, cid = _strip_args_from_line(line, arg_buf)
    assert is_finish is True
    assert out is not None  # finish chunk is meaningful


def test_strip_finish_chunk_trailing_garbage():
    """Finish chunk with trailing '.' (vLLM bug) — raw_decode recovers is_finish."""
    raw_line = _finish_chunk() + "."   # simulate vLLM trailing garbage
    arg_buf = {}
    out, is_finish, cid = _strip_args_from_line(raw_line, arg_buf)
    assert is_finish is True, "is_finish must be detected even with trailing garbage"
    assert out is not None
    # re-encoded line should be clean JSON
    assert out.endswith("}") or out.endswith("}]}")  # no trailing .


def test_correction_skips_empty_args():
    """Empty accumulated args (vLLM sends arguments:'') must not produce a correction."""
    arg_buf = {0: "", 1: '{"filePath":"/tmp/x"}'}
    lines = _arg_correction_lines(arg_buf, "cmpl-x")
    assert len(lines) == 1, "Should emit correction only for non-empty args"
    data = json.loads(lines[0][6:])
    tc = data["choices"][0]["delta"]["tool_calls"][0]
    assert tc["index"] == 1  # only idx=1 emitted
    assert json.loads(tc["function"]["arguments"]) == {"filePath": "/tmp/x"}


def test_strip_no_double_emit():
    """
    Exact-once invariant: accumulate args across multiple chunks, then verify
    the concatenated result appears in correction lines exactly once.
    """
    fragments = ['{"filePath": "', '/tmp/server.py"', '}}.']
    arg_buf = {}

    # Simulate streaming: first chunk has name + first fragment
    line0 = _chunk(idx=0, name="read", id_="call_1", type_="function", args_frag=fragments[0])
    out0, _, _ = _strip_args_from_line(line0, arg_buf)
    assert out0 is not None  # first chunk kept

    # Middle chunks: args only → suppressed
    for frag in fragments[1:]:
        line_n = _chunk(idx=0, args_frag=frag)
        out_n, _, _ = _strip_args_from_line(line_n, arg_buf)
        assert out_n is None, f"Intermediate chunk should be suppressed (frag={frag!r})"

    # arg_buf should have all fragments concatenated
    expected_raw = "".join(fragments)
    assert arg_buf[0] == expected_raw

    # Correction lines should contain repaired args
    corrections = _arg_correction_lines(arg_buf, "cmpl-1")
    assert len(corrections) == 1
    corr_data = json.loads(corrections[0][6:])
    emitted_args = corr_data["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"]
    parsed = json.loads(emitted_args)
    assert parsed == {"filePath": "/tmp/server.py"}

    # Emitted args must NOT appear in out0 (the name chunk we kept)
    out0_data = json.loads(out0[6:])
    fn0 = out0_data["choices"][0]["delta"]["tool_calls"][0]["function"]
    assert "arguments" not in fn0, "Arguments leaked into name chunk"


def test_strip_multiple_tool_calls():
    """Parallel tool calls at index 0 and 1 are tracked independently."""
    arg_buf = {}
    for idx, frag in [(0, '{"path":"/a"}'), (1, '{"path":"/b"}')]:
        line = _chunk(idx=idx, name=f"read_{idx}", id_=f"call_{idx}",
                      type_="function", args_frag=frag)
        out, _, _ = _strip_args_from_line(line, arg_buf)
        assert out is not None

    corrections = _arg_correction_lines(arg_buf, "cmpl-2")
    assert len(corrections) == 2
    indices = set()
    for c in corrections:
        d = json.loads(c[6:])
        tc = d["choices"][0]["delta"]["tool_calls"][0]
        indices.add(tc["index"])
        assert json.loads(tc["function"]["arguments"])  # valid JSON
    assert indices == {0, 1}


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
