"""Strict RFC 8259 JSON parser – hand-written, standard-library-only."""


class JSONError(ValueError):
    """Raised on any JSON parse failure."""

    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


# ─── helpers ──────────────────────────────────────────────────────────────────

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_WS = frozenset(" \t\n\r")


def _parse_string(s: str, i: int, n: int) -> tuple:
    """Parse a JSON string literal starting at s[i]=='\"'.  Returns (str, new_i)."""
    i += 1  # skip opening quote
    parts: list[str] = []
    while True:
        if i >= n:
            raise JSONError("unterminated string", n)
        c = s[i]
        if c == '"':
            return "".join(parts), i + 1
        if c == "\\":
            i += 1
            if i >= n:
                raise JSONError("unterminated escape", n)
            c2 = s[i]
            if c2 == '"':
                parts.append('"'); i += 1
            elif c2 == "\\":
                parts.append("\\"); i += 1
            elif c2 == "/":
                parts.append("/"); i += 1
            elif c2 == "b":
                parts.append("\b"); i += 1
            elif c2 == "f":
                parts.append("\f"); i += 1
            elif c2 == "n":
                parts.append("\n"); i += 1
            elif c2 == "r":
                parts.append("\r"); i += 1
            elif c2 == "t":
                parts.append("\t"); i += 1
            elif c2 == "u":
                # exactly four ASCII hex digits required
                if i + 5 > n:
                    raise JSONError("truncated \\u escape", n)
                h = s[i + 1 : i + 5]
                for k, ch in enumerate(h):
                    if ch not in _HEX_DIGITS:
                        raise JSONError("invalid hex digit", i + 1 + k)
                code = int(h, 16)
                i += 5
                # surrogate-pair handling (only two *escapes* combine)
                if 0xD800 <= code <= 0xDBFF:
                    if (
                        i + 1 < n
                        and s[i] == "\\"
                        and s[i + 1] == "u"
                        and i + 6 <= n
                    ):
                        h2 = s[i + 2 : i + 6]
                        ok = True
                        for ch in h2:
                            if ch not in _HEX_DIGITS:
                                ok = False
                                break
                        if ok:
                            code2 = int(h2, 16)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                parts.append(chr(combined))
                                i += 6
                                continue
                    parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError("invalid escape", i)
        elif ord(c) < 0x20:
            raise JSONError("control character in string", i)
        else:
            parts.append(c)
            i += 1


def _parse_number(s: str, i: int, n: int) -> tuple:
    """Parse a JSON number starting at s[i].  Returns (int|float, new_i)."""
    start = i
    is_float = False

    # optional sign
    if s[i] == "-":
        i += 1
        if i >= n:
            raise JSONError("unexpected end of number", n)

    # integer part: 0 | [1-9][0-9]*
    c = s[i]
    if c == "0":
        i += 1
    elif "1" <= c <= "9":
        i += 1
        while i < n and "0" <= s[i] <= "9":
            i += 1
    else:
        raise JSONError("invalid number", i)

    # optional fraction
    if i < n and s[i] == ".":
        is_float = True
        i += 1
        if i >= n:
            raise JSONError("unexpected end in fraction", n)
        if not ("0" <= s[i] <= "9"):
            raise JSONError("invalid fraction digit", i)
        while i < n and "0" <= s[i] <= "9":
            i += 1

    # optional exponent
    if i < n and s[i] in "eE":
        is_float = True
        i += 1
        if i < n and s[i] in "+-":
            i += 1
        if i >= n:
            raise JSONError("unexpected end in exponent", n)
        if not ("0" <= s[i] <= "9"):
            raise JSONError("invalid exponent digit", i)
        while i < n and "0" <= s[i] <= "9":
            i += 1

    text = s[start:i]
    if is_float:
        return float(text), i
    return int(text), i


# ─── main entry point ────────────────────────────────────────────────────────

def loads(s: str):
    """Parse a JSON document from *s* and return the corresponding Python object."""
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}"
        )

    n = len(s)
    i = 0

    # skip leading whitespace
    while i < n and s[i] in _WS:
        i += 1
    if i >= n:
        raise JSONError("empty input", n)

    # ── iterative (non-recursive) parser with explicit stack ──────────────
    # stack entries: (kind, container, pending_key)
    #   kind 'a' -> array (list)
    #   kind 'o' -> object (dict), pending_key is the current key or None
    stack: list[tuple] = []
    depth = 0
    result = None

    # state machine states:
    #   'value'       – expecting a JSON value
    #   'key'         – expecting a string key (inside object)
    #   'colon'       – expecting ':' (inside object)
    #   'comma_a'     – expecting ',' or ']' (inside array)
    #   'comma_o'     – expecting ',' or '}' (inside object)
    #   'done'        – top-level value fully parsed
    state = "value"

    val = None          # last parsed value awaiting delivery
    has_val = False     # True when *val* needs to be delivered

    while True:
        # ── deliver a completed value to its parent ───────────────────────
        if has_val:
            has_val = False
            if not stack:
                result = val
                state = "done"
            else:
                kind, cont, pk = stack[-1]
                if kind == "a":
                    cont.append(val)
                    state = "comma_a"
                else:
                    cont[pk] = val
                    state = "comma_o"
            continue

        if state == "done":
            break

        # ── expecting a value ──────────────────────────────────────────────
        if state == "value":
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)

            c = s[i]

            if c == '"':
                val, i = _parse_string(s, i, n)
                has_val = True

            elif c == "[":
                if depth >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(("a", [], None))
                depth += 1
                i += 1
                # check for empty array
                while i < n and s[i] in _WS:
                    i += 1
                if i >= n:
                    raise JSONError("unexpected end of input", n)
                if s[i] == "]":
                    i += 1
                    depth -= 1
                    val = stack.pop()[1]
                    has_val = True
                # else: state stays 'value' → next iteration parses first element

            elif c == "{":
                if depth >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(("o", {}, None))
                depth += 1
                i += 1
                # check for empty object
                while i < n and s[i] in _WS:
                    i += 1
                if i >= n:
                    raise JSONError("unexpected end of input", n)
                if s[i] == "}":
                    i += 1
                    depth -= 1
                    val = stack.pop()[1]
                    has_val = True
                else:
                    state = "key"

            elif c == "t":
                for j, ch in enumerate("true"):
                    if i + j >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + j] != ch:
                        raise JSONError("invalid literal", i + j)
                i += 4
                val = True
                has_val = True

            elif c == "f":
                for j, ch in enumerate("false"):
                    if i + j >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + j] != ch:
                        raise JSONError("invalid literal", i + j)
                i += 5
                val = False
                has_val = True

            elif c == "n":
                for j, ch in enumerate("null"):
                    if i + j >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + j] != ch:
                        raise JSONError("invalid literal", i + j)
                i += 4
                val = None
                has_val = True

            elif c == "-" or ("0" <= c <= "9"):
                val, i = _parse_number(s, i, n)
                has_val = True

            else:
                raise JSONError("unexpected character", i)

        # ── expecting a key (inside object) ────────────────────────────────
        elif state == "key":
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] != '"':
                raise JSONError("expected string key", i)
            key, i = _parse_string(s, i, n)
            stack[-1] = ("o", stack[-1][1], key)
            state = "colon"

        # ── expecting ':' ──────────────────────────────────────────────────
        elif state == "colon":
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] != ":":
                raise JSONError("expected colon", i)
            i += 1
            state = "value"

        # ── expecting ',' or ']' ───────────────────────────────────────────
        elif state == "comma_a":
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == "]":
                i += 1
                depth -= 1
                val = stack.pop()[1]
                has_val = True
            elif s[i] == ",":
                i += 1
                state = "value"
            else:
                raise JSONError("expected ',' or ']'", i)

        # ── expecting ',' or '}' ───────────────────────────────────────────
        elif state == "comma_o":
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == "}":
                i += 1
                depth -= 1
                val = stack.pop()[1]
                has_val = True
            elif s[i] == ",":
                i += 1
                state = "key"
            else:
                raise JSONError("expected ',' or '}'", i)

    # ── trailing-garbage check ─────────────────────────────────────────────
    while i < n and s[i] in _WS:
        i += 1
    if i < n:
        raise JSONError("trailing garbage", i)

    return result
