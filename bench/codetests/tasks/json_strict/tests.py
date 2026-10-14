"""Hidden tests for json_strict. Each test takes the loaded solution module `m`.

Oracles (neither is the reference solution):
  * accept/reject + parsed value: the standard library `json.loads(s, parse_constant=<raise>)`
    on a seeded corpus of generated valid documents and mutated (mostly invalid) documents.
    The only spec deviations (NaN/Infinity, depth > 500, bytes input) are kept out of the
    differential corpora and covered by hand-written cases.
  * `.pos` of errors: `viable_pos`, an independent character-level pushdown automaton defined
    below (dies at the first character that cannot continue any valid document), cross-checked
    against hand-computed positions in the tables.
"""
import ast
import json
import random
import sys


# ----------------------------------------------------------------------------- helpers

def _no_const(name):
    raise ValueError(f"constant {name}")


def oracle(s):
    """Return ('ok', value) or ('err', None) according to the stdlib."""
    try:
        return "ok", json.loads(s, parse_constant=_no_const)
    except ValueError:
        return "err", None


def same(a, b):
    """Iterative deep equality that also checks types, float sign/repr and dict key order."""
    stack = [(a, b)]
    while stack:
        x, y = stack.pop()
        if type(x) is not type(y):
            return False
        if isinstance(x, dict):
            if list(x.keys()) != list(y.keys()):
                return False
            for k in x:
                stack.append((x[k], y[k]))
        elif isinstance(x, list):
            if len(x) != len(y):
                return False
            stack.extend(zip(x, y))
        elif isinstance(x, float):
            if repr(x) != repr(y):
                return False
        elif x != y:
            return False
    return True


def viable_pos(s):
    """Independent PDA oracle. None if `s` is a valid document (depth <= 500), else the
    spec'd error position (first char that cannot continue a valid document, or len(s))."""
    st = []            # 'a' / 'o' for open containers
    state = "V"        # value expected
    lit = None         # remaining chars of a literal
    ukeep = 0
    in_key = False
    D = "0123456789"
    H = "0123456789abcdefABCDEF"
    WS = " \t\n\r"
    for i, c in enumerate(s):
        while True:  # loop for epsilon re-dispatch after a number ends
            if state in ("V", "VA"):
                if c in WS:
                    state = state
                elif c == "]" and state == "VA":
                    st.pop()
                    state = "AFTER"
                elif c == "[":
                    if len(st) >= 500:
                        return i
                    st.append("a")
                    state = "VA"
                elif c == "{":
                    if len(st) >= 500:
                        return i
                    st.append("o")
                    state = "KO"
                elif c == '"':
                    state, in_key = "S", False
                elif c == "-":
                    state = "NM"
                elif c == "0":
                    state = "N0"
                elif c in "123456789":
                    state = "NI"
                elif c in "tfn":
                    word = {"t": "true", "f": "false", "n": "null"}[c]
                    lit = word[1:]
                    state = "LIT"
                else:
                    return i
            elif state in ("KO", "K"):
                if c in WS:
                    pass
                elif c == "}" and state == "KO":
                    st.pop()
                    state = "AFTER"
                elif c == '"':
                    state, in_key = "S", True
                else:
                    return i
            elif state == "COLON":
                if c in WS:
                    pass
                elif c == ":":
                    state = "V"
                else:
                    return i
            elif state == "S":
                if c == '"':
                    state = "COLON" if in_key else "AFTER"
                elif c == "\\":
                    state = "ESC"
                elif ord(c) < 0x20:
                    return i
            elif state == "ESC":
                if c in '"\\/bfnrt':
                    state = "S"
                elif c == "u":
                    state, ukeep = "U", 4
                else:
                    return i
            elif state == "U":
                if c not in H:
                    return i
                ukeep -= 1
                if ukeep == 0:
                    state = "S"
            elif state == "LIT":
                if c != lit[0]:
                    return i
                lit = lit[1:]
                if not lit:
                    state = "AFTER"
            elif state == "NM":
                if c == "0":
                    state = "N0"
                elif c in "123456789":
                    state = "NI"
                else:
                    return i
            elif state in ("N0", "NI", "NF", "NX"):
                if state == "NI" and c in D:
                    pass
                elif state == "NF" and c in D:
                    pass
                elif state == "NX" and c in D:
                    pass
                elif c == "." and state in ("N0", "NI"):
                    state = "ND"
                elif c in "eE" and state in ("N0", "NI", "NF"):
                    state = "NE"
                else:
                    state = "AFTER"
                    continue
            elif state == "ND":
                if c in D:
                    state = "NF"
                else:
                    return i
            elif state == "NE":
                if c in "+-":
                    state = "NS"
                elif c in D:
                    state = "NX"
                else:
                    return i
            elif state == "NS":
                if c in D:
                    state = "NX"
                else:
                    return i
            elif state == "AFTER":
                if c in WS:
                    pass
                elif not st:
                    return i
                elif c == ",":
                    state = "V" if st[-1] == "a" else "K"
                elif c == "]" and st[-1] == "a":
                    st.pop()
                elif c == "}" and st[-1] == "o":
                    st.pop()
                else:
                    return i
            break
    if not st and state in ("AFTER", "N0", "NI", "NF", "NX"):
        return None
    return len(s)


def _raises_pos(m, s, pos):
    try:
        v = m.loads(s)
    except m.JSONError as e:
        assert type(e.pos) is int, f"pos has type {type(e.pos).__name__} for {s[:60]!r}"
        assert e.pos == pos, f"{s[:60]!r}: pos {e.pos}, expected {pos}"
        return
    except Exception as e:
        raise AssertionError(f"{s[:60]!r}: raised {type(e).__name__}: {e}, expected JSONError")
    raise AssertionError(f"{s[:60]!r}: accepted -> {str(v)[:40]!r}, expected JSONError at {pos}")


def _check_valid(m, s):
    want = json.loads(s)
    got = m.loads(s)
    assert same(got, want), f"{s[:80]!r}: got {str(got)[:60]!r}, expected {str(want)[:60]!r}"


# ----------------------------------------------------------------------------- generators

_STR_ALPHA = (
    list("abcxyzAZ09 _-") * 2
    + ['"', "\\", "/", "\n", "\t", "\r", "\b", "\f", "\x00", "\x01", "\x1f", "\x7f", "\x20",
       "\u00e9", "\u4e2d", "\u2028", "\u00a0", "\ufeff", "\U0001F600", "\U00010000", "\U0010FFFF",
       "\ud800", "\udbff", "\udc00", "\udfff", "\ud83d", "\ude00", "u", "0"]
)


def gen_str(rng, maxlen=8):
    return "".join(rng.choice(_STR_ALPHA) for _ in range(rng.randint(0, maxlen)))


def emit_str(rng, st):
    out = ['"']
    for ch in st:
        o = ord(ch)
        r = rng.random()
        if ch == '"' or ch == "\\":
            out.append("\\" + ch)
        elif o < 0x20:
            short = {8: "b", 12: "f", 10: "n", 13: "r", 9: "t"}
            if o in short and r < 0.6:
                out.append("\\" + short[o])
            else:
                out.append("\\u%04x" % o if r < 0.8 else "\\u%04X" % o)
        elif ch == "/" and r < 0.3:
            out.append("\\/")
        elif 0xD800 <= o <= 0xDFFF:
            out.append("\\u%04x" % o if r < 0.7 else ch)  # escaped or raw lone surrogate
        elif o > 0xFFFF and r < 0.5:
            o2 = o - 0x10000
            hi, lo = 0xD800 + (o2 >> 10), 0xDC00 + (o2 & 0x3FF)
            out.append(("\\u%04x\\u%04x" if r < 0.25 else "\\u%04X\\u%04X") % (hi, lo))
        elif o > 0x7E and r < 0.4:
            out.append("\\u%04x" % o)
        elif o < 0x7F and r < 0.04:
            out.append("\\u%04x" % o)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def gen_num(rng):
    r = rng.random()
    sign = "-" if rng.random() < 0.3 else ""
    if r < 0.35:
        nd = rng.choice([1, 1, 2, 3, 5, 10, 20, 40])
        digs = str(rng.randint(1, 9)) + "".join(rng.choice("0123456789") for _ in range(nd - 1))
        if rng.random() < 0.1:
            digs = "0"
        return sign + digs
    ip = rng.choice(["0", str(rng.randint(1, 9)), str(rng.randint(10, 99999)), "123456789012345678901"])
    frac = "." + "".join(rng.choice("0123456789") for _ in range(rng.randint(1, 20))) if r < 0.8 else ""
    exp = ""
    if r >= 0.5 or not frac:
        exp = rng.choice("eE") + rng.choice(["", "+", "-"]) + str(rng.choice([0, 1, 5, 10, 22, 100, 308, 309, 400, 999]))
    if not frac and not exp:
        exp = "e0"
    return sign + ip + frac + exp


def gen_tree(rng, depth):
    r = rng.random()
    if depth <= 0 or r < 0.35:
        k = rng.random()
        if k < 0.35:
            return ("num", gen_num(rng))
        if k < 0.75:
            return ("str", gen_str(rng))
        return ("lit", rng.choice(["true", "false", "null"]))
    if r < 0.67:
        return ("arr", [gen_tree(rng, depth - 1) for _ in range(rng.randint(0, 5))])
    pool = [gen_str(rng, 3) for _ in range(4)]
    return ("obj", [(rng.choice(pool) if rng.random() < 0.5 else gen_str(rng, 3), gen_tree(rng, depth - 1))
                    for _ in range(rng.randint(0, 5))])


def _ws(rng, p=0.25):
    if rng.random() < p:
        return "".join(rng.choice(" \t\n\r") for _ in range(rng.randint(1, 3)))
    return ""


def emit(rng, node, ws=True):
    w = (lambda: _ws(rng)) if ws else (lambda: "")
    kind, v = node
    if kind in ("num", "lit"):
        return v
    if kind == "str":
        return emit_str(rng, v)
    if kind == "arr":
        return "[" + w() + ",".join(w() + emit(rng, x, ws) + w() for x in v) + "]"
    return "{" + w() + ",".join(w() + emit_str(rng, k) + w() + ":" + w() + emit(rng, x, ws) + w() for k, x in v) + "}"


def gen_doc(rng, depth=4):
    return w_wrap(rng, emit(rng, gen_tree(rng, depth)))


def w_wrap(rng, text):
    return _ws(rng, 0.2) + text + _ws(rng, 0.2)


# ----------------------------------------------------------------------------- tests

def test_basic_values(m):
    L = m.loads
    assert L("null") is None and L("true") is True and L("false") is False
    assert type(L("true")) is bool and type(L("false")) is bool
    assert same(L("0"), 0) and same(L("-17"), -17) and same(L("2.5"), 2.5)
    assert same(L('"hi"'), "hi") and same(L('""'), "")
    assert same(L("[]"), []) and same(L("{}"), {})
    assert same(L(" \t\r\n [ 1 , 2 ,3 ] \n"), [1, 2, 3])
    doc = '{"a": [1, 2.5, "x", null, true, false, {"b": []}], "c": {}, "": 0, "d e": "f"}'
    assert same(L(doc), json.loads(doc))
    assert list(L('{"z":1,"a":2,"m":3}')) == ["z", "a", "m"]
    assert same(L('[[],[[]],{},{"a":{}}]'), [[], [[]], {}, {"a": {}}])
    assert same(L('  "\\"quoted\\""  '), '"quoted"')
    assert same(L("[1,[2,[3,[4]]]]"), [1, [2, [3, [4]]]])
    assert same(L('{"a":{"b":{"c":[{"d":null}]}}}'), {"a": {"b": {"c": [{"d": None}]}}})


def test_number_values(m):
    L = m.loads
    cases = [
        "0", "-0", "1", "-1", "9", "10", "123456789", "-123456789012345678901234567890",
        "0.0", "-0.0", "0.5", "-0.5", "1.0", "10.25", "3.141592653589793238462643383279",
        "1e5", "1E5", "1e+5", "1E-2", "1e-2", "0e0", "0E0", "-0e0", "0.0e0", "1.5E+3", "12.5e-1",
        "1e400", "-1e400", "1e-400", "-1e-400", "1e308", "1.7976931348623157e308", "1.7976931348623159e308",
        "5e-324", "2.2250738585072014e-308", "0.1", "0.30000000000000004", "123456789012345678.5",
        "9007199254740993", "9007199254740993.0", "0.00000000000000000000000000000000000001",
        "1" + "0" * 400, "-" + "9" * 1000, "1" + "0" * 400 + ".5", "3" + "0" * 3999,
        "100000000000000000000e-20", "4.9406564584124654e-324", "0.000001", "1e0", "1e00", "1e007",
    ]
    for c in cases:
        _check_valid(m, c)
    # explicit type / sign checks (not through the oracle)
    for t, ty in (("1e5", float), ("1E-2", float), ("1.0", float), ("-0", int), ("0", int),
                  ("123", int), ("0e0", float), ("-0.0", float)):
        assert type(L(t)) is ty, (t, type(L(t)))
    import math
    assert math.copysign(1.0, L("-0.0")) == -1.0
    assert L("-0") == 0 and math.copysign(1.0, float(L("-0"))) == 1.0
    assert L("1e400") == float("inf") and L("-1e400") == float("-inf") and L("1e-400") == 0.0
    big = "7" * 3000
    assert L(big) == int(big) and type(L(big)) is int
    assert L("[" + ",".join(["-0", "-0.0", "1E2"]) + "]") == [0, -0.0, 100.0]
    # numbers inside containers and as object values, adjacent to delimiters and whitespace
    assert same(L('{"a":-1.5e2,"b":[0,-0,0.5]}'), {"a": -150.0, "b": [0, 0, 0.5]})
    assert same(L("[1,2]"), [1, 2]) and same(L("[1\n,\t2 ]"), [1, 2])


def test_number_errors_pos(m):
    table = [
        ("01", 1), ("-01", 2), ("[01]", 2), ("00", 1), ("-00", 2), ("0123", 1), ("[0,01]", 4),
        ("-", 1), ("-x", 1), ("[-]", 2), ("[-,1]", 2), ("- 1", 1), ("--1", 1), ("-+1", 1),
        ("1.", 2), ("1.x", 2), ("[1.]", 3), ("[1.,2]", 3), ("0.", 2), ("-0.", 3), ("1.e5", 2), ("1.E5", 2),
        ("1.5e", 4), ("1.5e+", 5), ("1.5e-", 5), ("1e", 2), ("1E", 2), ("1e+", 3), ("1e-", 3), ("[1e]", 3),
        ("1e+x", 3), ("1ex", 2), ("0e", 2), ("[1e5e]", 4), ("1e5.5", 3), ("1.5.5", 3), ("1.5e5e5", 5),
        ("+1", 0), ("+", 0), (".5", 0), ("-.5", 1), (".", 0), ("[.5]", 1), ("[+1]", 1),
        ("0x10", 1), ("0b1", 1), ("0o7", 1), ("1_0", 1), ("[1_0]", 2), ("1,000", 1), ("1 000", 2),
        ("\u0660", 0), ("1\u0660", 1), ("-\u0660", 1), ("1.\u0661", 2), ("1e\u0662", 2), ("[\u0663]", 1),
        ("\uff11", 0), ("1\u00b2", 1), ("\u00bd", 0),
        ("1e5 1", 4), ("[1e5 1]", 5), ("12a", 2), ("1a", 1), ("[1a]", 2),
        ("NaN", 0), ("-NaN", 1), ("Infinity", 0), ("-Infinity", 1), ("+Infinity", 0), ("infinity", 0),
        ("inf", 0), ("nan", 1), ("[NaN]", 1), ("[1,NaN]", 3), ('{"a":Infinity}', 5), ('{"a":-Infinity}', 6),
        ("[NaN, Infinity, -Infinity]", 1), ("Inf", 0), ("-inf", 1), ("-nan", 1),
    ]
    for s, pos in table:
        _raises_pos(m, s, pos)


def test_string_values(m):
    L = m.loads
    assert same(L(r'"\"\\\/\b\f\n\r\t"'), '"\\/\b\f\n\r\t')
    assert same(L(r'"\u0041\u00e9\u00E9\u4e2d\u4E2D"'), "A\u00e9\u00e9\u4e2d\u4e2d")
    assert same(L(r'"\u0000\u001f\u007f\u0080\uffff"'), "\x00\x1f\x7f\x80\uffff")
    assert same(L(r'"a\u0062c"'), "abc")
    # raw characters kept as they are
    raw = "\x20\x7f\u0080\u00a0\u2028\u2029\ufeff\U0001F600\U0010FFFF\u4e2d"
    assert same(L('"' + raw + '"'), raw)
    # surrogate escapes
    assert same(L(r'"\ud83d\ude00"'), "\U0001F600")
    assert same(L(r'"\uD83D\uDE00"'), "\U0001F600")
    assert same(L(r'"\ud800\udc00"'), "\U00010000")
    assert same(L(r'"\udbff\udfff"'), "\U0010FFFF")
    assert same(L(r'"\ud83d"'), "\ud83d")                       # lone high
    assert same(L(r'"\ude00"'), "\ude00")                       # lone low
    assert same(L(r'"\ude00\ud83d"'), "\ude00\ud83d")           # low then high: no pairing
    assert same(L(r'"\ud83d\ud83d\ude00"'), "\ud83d\U0001F600")  # lone high + pair
    assert same(L(r'"\ud83d\u0041"'), "\ud83dA")
    assert same(L(r'"\ud83dx\ude00"'), "\ud83dx\ude00")
    assert same(L(r'"\ud83d \ude00"'), "\ud83d \ude00")
    assert same(L(r'"\ud83d\\ude00"'), "\ud83d\\ude00")         # second backslash escaped
    assert same(L(r'"\ud83d\n"'), "\ud83d\n")
    assert same(L(r'"\ud83d\ud83d"'), "\ud83d\ud83d")
    assert same(L(r'"\ude00\ude00"'), "\ude00\ude00")
    assert same(L(r'"\ud83d\ude00\ude00"'), "\U0001F600\ude00")
    assert same(L(r'"\ud83d\ude00\ud83d\ude01"'), "\U0001F600\U0001F601")
    # raw surrogate characters in the input str never combine
    assert same(L('"\ud83d\\ude00"'), "\ud83d\ude00")
    assert L('"\ud83d\\ude00"') == "\ud83d\ude00" and len(L('"\ud83d\\ude00"')) == 2
    assert len(L(r'"\ud83d\ude00"')) == 1
    assert same(L('"\ud800"'), "\ud800")
    assert same(L('"\\ud83d\ude00"'), "\ud83d\ude00") and len(L('"\\ud83d\ude00"')) == 2
    # keys use the same decoding
    d = L(r'{"\u0061":1,"a":2,"\ud83d\ude00":3,"\ud83d":4,"\/":5}')
    assert same(d, {"a": 2, "\U0001F600": 3, "\ud83d": 4, "/": 5})
    # long string with mixed content
    s = ("ab\\n\\\"" * 50 + "\u00e9" * 20 + "\\u00e9" * 20)
    _check_valid(m, '"' + s + '"')


def test_string_errors_pos(m):
    # every raw control character below U+0020 is rejected, in values and in keys
    for o in range(0x20):
        c = chr(o)
        _raises_pos(m, '"a' + c + 'b"', 2)
        _raises_pos(m, '["x' + c + '"]', 3)
        _raises_pos(m, '{"k' + c + '":1}', 3)
    assert m.loads('"\x7f"') == "\x7f" and m.loads('"\x20"') == " "
    table = [
        ('"abc', 4), ('"', 1), ('"a\\', 3), ('"\\', 2), ('["a', 3), ('{"a', 3), ('{"a"', 4), ('{"a":"b', 7),
        ('"\\x"', 2), ('"\\a"', 2), ('"\\\'"', 2), ('"\\0"', 2), ('"\\U0041"', 2), ('"\\x41"', 2),
        ('"\\ "', 2), ('"\\\n"', 2), ('"\\\u00e9"', 2), ('"ab\\q"', 4), ('["\\v"]', 3), ('"\\B"', 2), ('"\\N"', 2),
        ('"\\u"', 3), ('"\\u1"', 4), ('"\\u12', 5), ('"\\u123', 6), ('"\\u123"', 6), ('"\\u12G4"', 5),
        ('"\\uZZZZ"', 3), ('"\\u+123"', 3), ('"\\u 123"', 3), ('"\\u1_23"', 4), ('"\\u0x12"', 4),
        ('"\\u-123"', 3), ('"\\u12 4"', 5), ('"\\u\u0660\u0660\u0660\u0660"', 3), ('"\\u00\u0660\u0660"', 5),
        ('"\\u00e\u00e9"', 6), ('"\\u\uff11\uff11\uff11\uff11"', 3), ('"\\u12"', 5), ('"\\u"', 3),
        ('"\\ud83d\\u12"', 11), ('"\\ud83d\\uZZZZ"', 9), ('"\\ud83d\\x"', 8), ('"\\ud83d\\u12G4"', 11),
        ('"\\ude00\\q"', 8), ("'a'", 0), ("a", 0), ('"a" "b"', 4), ('"a"b', 3), ('"a"x"', 3),
        ('{"a":"b"c}', 8), ('{a:1}', 1), ("{'a':1}", 1), ('{"a":1,b:2}', 7), ('{"a":1,"b"}', 10), ('{"a"::1}', 5),
        ('{"a":1 "b":2}', 7), ('{1:2}', 1), ('{"a":}', 5), ('{"a"}', 4), ('{"a",1}', 4), ('{null:1}', 1), ('{[]:1}', 1),
        ('{"a":1,,}', 7), ('{,}', 1), ('{"a":1,}', 7), ('{"a":1}}', 7), ('{"a":[1}', 7), ('["a":1]', 4),
    ]
    for s, pos in table:
        _raises_pos(m, s, pos)


def test_structure_whitespace_trailing_pos(m):
    L = m.loads
    # allowed whitespace everywhere
    assert same(L(" \t\n\r1\r\n\t "), 1)
    assert same(L(" \n{ \"a\" \t: \r [ 1 , \n 2 ] , \"b\" : { } } \n"), {"a": [1, 2], "b": {}})
    for bad in ("\x0b", "\x0c", "\xa0", "\u2003", "\u2028", "\u2029", "\u3000", "\u0085", "\u200b", "\x1c", "\x1f", "\x00"):
        _raises_pos(m, bad + "1", 0)
        _raises_pos(m, "1" + bad, 1)
        _raises_pos(m, "[1," + bad + "2]", 3)
        _raises_pos(m, "[1" + bad + "]", 2)
        _raises_pos(m, '{"a"' + bad + ':1}', 4)
        _raises_pos(m, '{"a":' + bad + '1}', 5)
        _raises_pos(m, " " + bad, 1)
    _raises_pos(m, "\ufeff", 0)
    _raises_pos(m, "\ufeff[]", 0)
    _raises_pos(m, "\ufeff{}", 0)
    _raises_pos(m, "  \ufeff1", 2)
    _raises_pos(m, "1\ufeff", 1)
    _raises_pos(m, "[]\ufeff", 2)
    table = [
        ("", 0), (" ", 1), ("   ", 3), ("\n\t\r ", 4), ("[", 1), ("{", 1), ("[ ", 2), ("{ ", 2), ("[1", 2),
        ("[1,", 3), ("[1, ", 4), ("[1, 2", 5), ('{"a":', 5), ('{"a": ', 6), ('{"a":1', 6), ('{"a":1,', 7),
        ("[1,]", 3), ("[,", 1), ("[,]", 1), ("[1,,2]", 3), ("[1 2]", 3), ("[1;2]", 2), ("[1]]", 3), ("[1] [2]", 4),
        ("1 2", 2), ("1,", 1), ("[]x", 2), ("{}x", 2), ("[] []", 3), ("{} {}", 3), ("[ 1 ] x", 6), ('"a" 1', 4),
        ("]", 0), ("}", 0), (",", 0), (":", 0), ("[}", 1), ("{]", 1), ("[1}", 2), ('{"a":1]', 6), ("[}]", 1),
        ("tru", 3), ("t", 1), ("f", 1), ("n", 1), ("nu", 2), ("nul", 3), ("fals", 4), ("trux", 3), ("True", 0),
        ("NULL", 0), ("nulll", 4), ("true1", 4), ("truefalse", 4), ("falsy", 4), ("nil", 1), ("none", 1), ("None", 0),
        ("[truex]", 5), ("[tru]", 4), ("[nul,1]", 4), ("[true false]", 6), ("[true,]", 6), ("undefined", 0),
        ("{}[]", 2), ("[]{}", 2), ('""""', 2), ("[1] //c", 4), ("/*c*/1", 0), ("# c\n1", 0), ("1 // c", 2),
        ('[1,2,3,4,5,6,7,8,9,10,', 22), ('[1,"two",[3,{"four":4}],', 24), ('{"a":[{"b":[1,2,{"c":', 21),
    ]
    for s, pos in table:
        _raises_pos(m, s, pos)
    # whitespace-heavy valid and invalid
    ws = " \t\n\r" * 50
    assert same(L(ws + "[" + ws + "1" + ws + "," + ws + "2" + ws + "]" + ws), [1, 2])
    _raises_pos(m, ws, len(ws))
    _raises_pos(m, ws + "[" + ws, len(ws) * 2 + 1)


def test_duplicate_keys(m):
    L = m.loads
    d = L('{"a":1,"b":2,"a":3}')
    assert d == {"a": 3, "b": 2} and list(d.items()) == [("a", 3), ("b", 2)]
    d = L('{"b":1,"a":2,"b":3,"c":4,"a":5,"b":6}')
    assert list(d.items()) == [("b", 6), ("a", 5), ("c", 4)]
    d = L('{"a":1,"\\u0061":2,"a\\u0000":3,"a\\u0000":4}')
    assert list(d.items()) == [("a", 2), ("a\x00", 4)]
    d = L('{"x":{"k":1,"j":2,"k":3},"y":[{"q":1,"q":2}],"x":{"z":0}}')
    assert same(d, {"x": {"z": 0}, "y": [{"q": 2}]}) and list(d) == ["x", "y"]
    d = L('{"a":1,"a":{"a":[1,2]},"a":null}')
    assert same(d, {"a": None})
    d = L('{"":1,"":2}')
    assert d == {"": 2} and len(d) == 1
    d = L('{"\\ud83d\\ude00":1,"\U0001F600":2,"\\ud83d":3,"\ud83d":4}')
    assert list(d.items()) == [("\U0001F600", 2), ("\ud83d", 4)]
    assert type(d) is dict
    # "1" and 1-ish keys stay distinct strings; case sensitive
    d = L('{"A":1,"a":2,"1":3,"1.0":4,"01":5}')
    assert list(d) == ["A", "a", "1", "1.0", "01"]
    rng = random.Random(20260714)
    for _ in range(200):
        pairs = [(rng.choice("abcde"), rng.randint(0, 9)) for _ in range(rng.randint(0, 12))]
        text = "{" + ",".join(f'"{k}":{v}' for k, v in pairs) + "}"
        want = {}
        for k, v in pairs:
            want[k] = v
        got = L(text)
        assert list(got.items()) == list(want.items()), text


def test_depth_limit_ok(m):
    assert sys.getrecursionlimit() == 1000, "solution changed the recursion limit"
    L = m.loads
    for d in (1, 2, 3, 100, 250, 400, 480, 495, 498, 499, 500):
        s = "[" * d + "]" * d
        _check_valid(m, s)
        s = "[" * d + "1" + "]" * d
        _check_valid(m, s)
        s = '{"a":' * d + "null" + "}" * d
        _check_valid(m, s)
        s = "[{\"k\":" * (d // 2) + ("[" if d % 2 else "") + "7" + ("]" if d % 2 else "") + "}]" * (d // 2)
        _check_valid(m, s)
    # siblings at every level, deep
    d = 500
    s = "".join('[1,"x",{},' for _ in range(d - 1)) + "[null]" + "".join(',2]' for _ in range(d - 1))
    _check_valid(m, s)
    s = "".join('{"k%d":[0],"n":' % i if i % 2 == 0 else '[true,' for i in range(d - 1)) + "[]"
    s += "".join('}' if i % 2 == 0 else ',false]' for i in reversed(range(d - 1)))
    _check_valid(m, s)
    # parse the same deep doc repeatedly (state must not leak)
    for _ in range(5):
        _check_valid(m, "[" * 500 + "]" * 500)
    # whitespace inside deep nesting
    _check_valid(m, "[ \n" * 500 + " ]" * 500)
    # many documents of moderate depth
    for d in range(1, 60):
        _check_valid(m, "[" * d + "{}" + "]" * d)
    # the result shape is right (walk down iteratively)
    v = L("[" * 500 + "]" * 500)
    n = 1
    while v:
        assert type(v) is list and len(v) == 1
        v = v[0]
        n += 1
    assert n == 500 and v == []
    assert sys.getrecursionlimit() == 1000


def test_depth_limit_exceeded(m):
    L = m.loads
    cases = [
        ("[" * 501, 500), ("[" * 501 + "]" * 501, 500), ("[" * 502, 500), ("[" * 500 + ",", 500),
        ("[" * 500 + "x", 500), ('{"a":' * 501, 2500), ('{"a":' * 501 + "1" + "}" * 501, 2500),
        ("[ " * 500 + "[", 1000), ('[{"a":' * 250 + "{", 1500), ("[" * 250 + '{"a":' * 250 + "[", 250 + 1250),
        ("[{\"a\":" * 250 + "[", 1500), ("[" * 500 + "[" + "]" * 501, 500),
        ("[" * 500 + "{}", 500),
        ("[" * 10 + "x" + "[" * 600, 10), ("[" * 505 + "x", 500), ("[" * 100000, 500),
        ("[" * 200000, 500), ("[" * 200000 + "]" * 200000, 500), ('{"a":' * 100000, 2500),
        ("[[[[" * 100000, 500), ("[" * 500 + "]" * 500 + "]", 1000), ("[" * 500 + "]" * 499, 999),
        ("[" * 500, 500), ("{" + '"a":{' * 499, 1 + 5 * 499),
    ]
    for s, pos in cases:
        _raises_pos(m, s, pos)
    # deeper-than-limit documents are rejected even though json.loads would accept them,
    # but only if they really exceed 500 levels
    ok = "[" * 500 + "]" * 500
    assert same(L(ok), json.loads(ok))
    bad = "[" * 501 + "]" * 501
    assert oracle(bad)[0] == "ok"       # stdlib accepts it; the spec deviates
    _raises_pos(m, bad, 500)
    # depth is simultaneous nesting, not total count of containers
    s = "[" + ",".join(["[]"] * 5000) + "]"
    assert same(L(s), [[]] * 5000)
    s = "[" + ",".join(["[" * 499 + "]" * 499] * 50) + "]"
    _check_valid(m, s)
    s = "[" + ",".join(["[" * 500 + "]" * 500] * 2) + "]"
    _raises_pos(m, s, 500)
    # a failure must not poison later calls
    _check_valid(m, "[" * 500 + "]" * 500)
    _check_valid(m, "[1]")


def test_error_api(m):
    E = m.JSONError
    assert isinstance(E, type) and issubclass(E, ValueError)
    e = E("boom", 7)
    assert e.pos == 7 and isinstance(e, ValueError)
    assert "boom" in str(e)
    for bad in (b"[]", b"1", bytearray(b"1"), None, 1, 1.5, [], {}, ("1",), True, object()):
        try:
            m.loads(bad)
        except TypeError:
            pass
        except Exception as ex:
            raise AssertionError(f"{type(bad).__name__}: raised {type(ex).__name__}, expected TypeError")
        else:
            raise AssertionError(f"{type(bad).__name__} accepted")
    for s in ("", "x", "[1,", "NaN", "01", "[" * 501):
        try:
            m.loads(s)
        except ValueError as ex:
            assert type(ex) is E or isinstance(ex, E), f"{s[:20]!r}: raised plain {type(ex).__name__}"
            assert type(ex.pos) is int and 0 <= ex.pos <= len(s)
        else:
            raise AssertionError(f"{s[:20]!r} accepted")
    # str subclasses are strings too
    class S(str):
        pass
    assert same(m.loads(S("[1, 2]")), [1, 2])
    # catching ValueError catches parse errors (the documented contract)
    try:
        m.loads("{")
    except ValueError as ex:
        assert ex.pos == 1


def test_no_json_module_no_eval(m):
    assert callable(m.loads) and issubclass(m.JSONError, ValueError)
    assert m.loads("[1]") == [1]
    path = getattr(m, "__file__", None)
    assert path, "module has no __file__"
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    banned_mods = {"json", "simplejson", "ast", "_json", "orjson", "ujson", "demjson", "yaml", "tomllib", "importlib"}
    banned_names = {"eval", "exec", "compile", "__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in banned_mods, f"imports {a.name}"
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned_mods, f"imports from {node.module}"
        elif isinstance(node, ast.Name) and node.id in banned_names:
            raise AssertionError(f"uses {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in ("setrecursionlimit",):
            raise AssertionError("changes recursion limit")
    assert sys.getrecursionlimit() == 1000


def test_differential_valid(m):
    rng = random.Random(0x5EED_0001)
    n_ok = 0
    for _ in range(2000):
        text = gen_doc(rng, depth=rng.choice([1, 2, 3, 4, 5]))
        verdict, want = oracle(text)
        assert verdict == "ok", f"generator produced an invalid document {text[:80]!r}"
        got = m.loads(text)
        assert same(got, want), f"{text[:120]!r}\n got  {str(got)[:100]}\n want {str(want)[:100]}"
        n_ok += 1
    assert n_ok == 2000
    # scalars at top level with surrounding whitespace
    for _ in range(300):
        t = rng.choice([("num", gen_num(rng)), ("str", gen_str(rng, 12)), ("lit", rng.choice(["true", "false", "null"]))])
        text = _ws(rng, 0.7) + emit(rng, t) + _ws(rng, 0.7)
        assert same(m.loads(text), json.loads(text)), text


_NASTY = (
    list('[]{},:"\\ \t\n\r\x0b\x0c\x00\x1f\x7f\xa0\ufeff\u2028+-.eE0123456789\u0660ntfulrsaINxX/bu_')
    + ["NaN", "Infinity", "-Infinity", "true", "false", "null", "\\u", "\\ud83d", "\\ude00", "\\x", "\\uzzzz",
       "00", "1.", "e5", ".5", "\\", '\\"', "[]", "{}", '"a":', ",", ",,", "\ud83d", "\U0001F600"]
)


def mutate(rng, s):
    for _ in range(rng.choice([1, 1, 1, 2, 3])):
        if not s:
            s = rng.choice(_NASTY)
            continue
        op = rng.random()
        k = rng.randrange(len(s) + 1)
        if op < 0.2 and k < len(s):
            s = s[:k] + s[k + 1:]
        elif op < 0.45:
            s = s[:k] + rng.choice(_NASTY) + s[k:]
        elif op < 0.65 and k < len(s):
            s = s[:k] + rng.choice(_NASTY) + s[k + 1:]
        elif op < 0.78:
            s = s[:k]
        elif op < 0.88 and k + 1 < len(s):
            s = s[:k] + s[k + 1] + s[k] + s[k + 2:]
        elif k < len(s):
            j = min(len(s), k + rng.randint(1, 6))
            s = s[:j] + s[k:j] + s[j:]
    return s


def test_differential_mutations(m):
    rng = random.Random(0x5EED_0002)
    n_ok = n_err = 0
    for _ in range(15000):
        base = gen_doc(rng, depth=rng.choice([1, 2, 3]))
        if len(base) > 90:
            continue
        text = mutate(rng, base)
        verdict, want = oracle(text)
        pos = viable_pos(text)
        assert (pos is None) == (verdict == "ok"), f"test oracle disagrees with json on {text!r}"
        if verdict == "ok":
            n_ok += 1
            got = m.loads(text)
            assert same(got, want), f"{text[:120]!r}\n got  {str(got)[:100]}\n want {str(want)[:100]}"
        else:
            n_err += 1
            _raises_pos(m, text, pos)
    assert n_ok >= 1000 and n_err >= 5000, (n_ok, n_err)
    # single-position truncations of valid documents: always cut short => pos == len or earlier garbage
    for _ in range(60):
        base = gen_doc(rng, depth=3)
        if len(base) > 80:
            continue
        for k in range(len(base)):
            text = base[:k]
            verdict, _ = oracle(text)
            pos = viable_pos(text)
            assert (pos is None) == (verdict == "ok")
            if verdict == "ok":
                assert same(m.loads(text), json.loads(text))
            else:
                _raises_pos(m, text, pos)


def test_performance_scale(m):
    rng = random.Random(0x5EED_0003)
    # a) record-like document, ~700 KB
    recs = []
    for i in range(2500):
        recs.append({
            "id": i, "name": gen_str(rng, 12), "score": rng.random() * 1000 - 500,
            "tags": [gen_str(rng, 5) for _ in range(rng.randint(0, 4))],
            "nested": {"a": [rng.randint(-10**9, 10**9) for _ in range(5)], "ok": rng.random() < 0.5, "n": None},
        })
    text = json.dumps(recs, ensure_ascii=False, separators=(" ,\n ", " : "))
    assert len(text) > 300_000
    assert same(m.loads(text), json.loads(text))
    # b) array of 100000 small numbers
    text = "[" + ",".join(str(rng.randint(-1000, 1000)) for _ in range(100_000)) + "]"
    assert same(m.loads(text), json.loads(text))
    text = "[" + ", ".join("1.5e3" if i % 3 else "true" for i in range(60_000)) + "]"
    assert same(m.loads(text), json.loads(text))
    # c) 1 MB string with lots of escapes
    body = ("x" * 20 + "\\n" + "\\u00e9" + "\\ud83d\\ude00") * 20_000 + "plain" * 100_000
    text = '"' + body + '"'
    assert len(text) > 1_000_000
    assert same(m.loads(text), json.loads(text))
    # d) very long whitespace runs and a big integer
    text = " " * 500_000 + "[1]" + "\n" * 500_000
    assert m.loads(text) == [1]
    big = "9" * 4000
    assert m.loads("[" + big + "]") == [int(big)]
    # e) error at the very end of a large document, and a huge object
    text = "[" + ",".join('{"k":%d}' % i for i in range(60_000)) + ",]"
    _raises_pos(m, text, len(text) - 1)
    text = "{" + ",".join('"key%d":"v%d"' % (i, i) for i in range(200_000)) + "}"
    got = m.loads(text)
    assert len(got) == 200_000 and got["key199999"] == "v199999" and next(iter(got)) == "key0"
    # f) 1000 repeated medium documents
    doc = '{"a":[1,2,{"b":"c\\n"}],"d":-1.5e2,"e":[true,false,null]}'
    for _ in range(3000):
        assert m.loads(doc) == {"a": [1, 2, {"b": "c\n"}], "d": -150.0, "e": [True, False, None]}
    # g) huge over-limit nesting fails fast
    _raises_pos(m, "[" * 300_000, 500)


TESTS = [
    test_basic_values, test_number_values, test_number_errors_pos, test_string_values,
    test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys,
    test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval,
    test_differential_valid, test_differential_mutations, test_performance_scale,
]
