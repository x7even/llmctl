"""Reference solution for json_strict: iterative strict JSON parser."""
import re

MAX_DEPTH = 500


class JSONError(ValueError):
    def __init__(self, message, pos):
        super().__init__(f"{message} at index {pos}")
        self.msg = message
        self.pos = pos


_WS = re.compile(r"[ \t\n\r]*")
_CHUNK = re.compile(r'[^"\\\x00-\x1f]*')
_NUM = re.compile(r"-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?")
_HEX = frozenset("0123456789abcdefABCDEF")
_DIGITS = frozenset("0123456789")
_SIMPLE = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
_LITERALS = {"t": ("true", True), "f": ("false", False), "n": ("null", None)}


def _hex4(s, j, n):
    """Parse 4 hex digits at s[j:j+4]; return int or raise JSONError at first bad index."""
    chunk = s[j:j + 4]
    if len(chunk) == 4 and all(ch in _HEX for ch in chunk):
        return int(chunk, 16)
    for k in range(j, j + 4):
        if k >= n:
            raise JSONError("unexpected end of input", n)
        if s[k] not in _HEX:
            raise JSONError("invalid \\u escape", k)
    raise AssertionError("unreachable")


def _string(s, i, n):
    """s[i-1] == '"'. Returns (value, index after closing quote)."""
    parts = None
    while True:
        end = _CHUNK.match(s, i).end()
        if end >= n:
            raise JSONError("unterminated string", n)
        c = s[end]
        if c == '"':
            if parts is None:
                return s[i:end], end + 1
            parts.append(s[i:end])
            return "".join(parts), end + 1
        if parts is None:
            parts = []
        parts.append(s[i:end])
        if c != "\\":
            raise JSONError("control character in string", end)
        if end + 1 >= n:
            raise JSONError("unterminated string", n)
        e = s[end + 1]
        if e in _SIMPLE:
            parts.append(_SIMPLE[e])
            i = end + 2
        elif e == "u":
            cp = _hex4(s, end + 2, n)
            i = end + 6
            if 0xD800 <= cp <= 0xDBFF and s.startswith("\\u", i):
                nxt = s[i + 2:i + 6]
                if len(nxt) == 4 and all(ch in _HEX for ch in nxt):
                    lo = int(nxt, 16)
                    if 0xDC00 <= lo <= 0xDFFF:
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                        i += 6
            parts.append(chr(cp))
        else:
            raise JSONError("invalid escape", end + 1)


def _number(s, i, n):
    """Returns (value, index after number)."""
    m = _NUM.match(s, i)
    if m is None:
        # only possible when s[i] == '-' and no valid digit follows
        raise JSONError("invalid number", n if i + 1 >= n else i + 1)
    j = m.end()
    if j < n:
        c = s[j]
        if c == "." and m.group(1) is None and m.group(2) is None:
            k = j + 1
            if k >= n:
                raise JSONError("unexpected end of input", n)
            raise JSONError("invalid number", k)  # s[k] is not a digit, else regex would match
        if c in "eE" and m.group(2) is None:
            k = j + 1
            if k < n and s[k] in "+-":
                k += 1
            if k >= n:
                raise JSONError("unexpected end of input", n)
            raise JSONError("invalid number", k)
    tok = m.group()
    if m.group(1) is None and m.group(2) is None:
        return int(tok), j
    return float(tok), j


def _literal(s, i, n):
    word, val = _LITERALS[s[i]]
    if s.startswith(word, i):
        return val, i + len(word)
    for k in range(1, len(word)):
        if i + k >= n:
            raise JSONError("unexpected end of input", n)
        if s[i + k] != word[k]:
            raise JSONError("invalid literal", i + k)
    raise AssertionError("unreachable")


def loads(s):
    if not isinstance(s, str):
        raise TypeError(f"the JSON document must be str, not {type(s).__name__}")
    n = len(s)
    ws = _WS.match
    stack = []   # open containers (list or dict)
    keys = []    # pending key for each open dict, in stack order
    i = ws(s, 0).end()
    while True:
        # ---- parse a value starting at i ----
        if i >= n:
            raise JSONError("unexpected end of input", n)
        c = s[i]
        if c == '"':
            value, i = _string(s, i + 1, n)
        elif c == "[":
            if len(stack) >= MAX_DEPTH:
                raise JSONError("nesting too deep", i)
            i = ws(s, i + 1).end()
            if i < n and s[i] == "]":
                value, i = [], i + 1
            else:
                stack.append([])
                continue
        elif c == "{":
            if len(stack) >= MAX_DEPTH:
                raise JSONError("nesting too deep", i)
            i = ws(s, i + 1).end()
            if i < n and s[i] == "}":
                value, i = {}, i + 1
            else:
                if i >= n:
                    raise JSONError("unexpected end of input", n)
                if s[i] != '"':
                    raise JSONError("expected string key", i)
                key, i = _string(s, i + 1, n)
                i = ws(s, i).end()
                if i >= n:
                    raise JSONError("unexpected end of input", n)
                if s[i] != ":":
                    raise JSONError("expected ':'", i)
                i = ws(s, i + 1).end()
                stack.append({})
                keys.append(key)
                continue
        elif c in _DIGITS or c == "-":
            value, i = _number(s, i, n)
        elif c in "tfn":
            value, i = _literal(s, i, n)
        else:
            raise JSONError("unexpected character", i)
        # ---- value complete: attach to parents / close containers ----
        while True:
            i = ws(s, i).end()
            if not stack:
                if i < n:
                    raise JSONError("extra data", i)
                return value
            top = stack[-1]
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if type(top) is list:
                top.append(value)
                if c == ",":
                    i = ws(s, i + 1).end()
                    break
                if c == "]":
                    stack.pop()
                    value = top
                    i += 1
                    continue
                raise JSONError("expected ',' or ']'", i)
            else:
                top[keys.pop()] = value
                if c == ",":
                    i = ws(s, i + 1).end()
                    if i >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i] != '"':
                        raise JSONError("expected string key", i)
                    key, i = _string(s, i + 1, n)
                    i = ws(s, i).end()
                    if i >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i] != ":":
                        raise JSONError("expected ':'", i)
                    i = ws(s, i + 1).end()
                    keys.append(key)
                    break
                if c == "}":
                    stack.pop()
                    value = top
                    i += 1
                    continue
                raise JSONError("expected ',' or '}'", i)
