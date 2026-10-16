"""Strict RFC 8259 JSON parser – standard library only, no json/simplejson/ast/eval/exec/compile."""

class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos

_HEX = frozenset('0123456789abcdefABCDEF')
_WS = frozenset(' \t\n\r')

def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}")
    n = len(s)
    if n == 0:
        raise JSONError("empty input", 0)
    i = 0
    while i < n and s[i] in _WS:
        i += 1
    if i >= n:
        raise JSONError("empty input", n)
    val, i = _parse_value(s, i, 0, n)
    while i < n and s[i] in _WS:
        i += 1
    if i < n:
        raise JSONError("trailing data", i)
    return val


def _parse_value(s, i, depth, n):
    while i < n and s[i] in _WS:
        i += 1
    if i >= n:
        raise JSONError("unexpected end of input", n)
    c = s[i]

    if c == '"':
        return _parse_string(s, i, n)

    if c == '[':
        if depth >= 500:
            raise JSONError("maximum nesting depth exceeded", i)
        i += 1
        arr = []
        while i < n and s[i] in _WS:
            i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if s[i] == ']':
            return arr, i + 1
        while True:
            val, i = _parse_value(s, i, depth + 1, n)
            arr.append(val)
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ']':
                return arr, i + 1
            if s[i] == ',':
                i += 1
                continue
            raise JSONError("expected ',' or ']'", i)

    if c == '{':
        if depth >= 500:
            raise JSONError("maximum nesting depth exceeded", i)
        i += 1
        obj = {}
        while i < n and s[i] in _WS:
            i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if s[i] == '}':
            return obj, i + 1
        while True:
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] != '"':
                raise JSONError("expected '\"'", i)
            key, i = _parse_string(s, i, n)
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] != ':':
                raise JSONError("expected ':'", i)
            i += 1
            val, i = _parse_value(s, i, depth + 1, n)
            obj[key] = val
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == '}':
                return obj, i + 1
            if s[i] == ',':
                i += 1
                continue
            raise JSONError("expected ',' or '}'", i)

    if c == 't':
        if s[i:i+4] == 'true':
            return True, i + 4
        for j in range(1, min(4, n - i)):
            if s[i + j] != 'true'[j]:
                raise JSONError("invalid literal", i + j)
        raise JSONError("unexpected end of input", n)

    if c == 'f':
        if s[i:i+5] == 'false':
            return False, i + 5
        for j in range(1, min(5, n - i)):
            if s[i + j] != 'false'[j]:
                raise JSONError("invalid literal", i + j)
        raise JSONError("unexpected end of input", n)

    if c == 'n':
        if s[i:i+4] == 'null':
            return None, i + 4
        for j in range(1, min(4, n - i)):
            if s[i + j] != 'null'[j]:
                raise JSONError("invalid literal", i + j)
        raise JSONError("unexpected end of input", n)

    if c == '-' or ('0' <= c <= '9'):
        return _parse_number(s, i, n)

    raise JSONError("unexpected character", i)


def _parse_number(s, i, n):
    start = i
    if s[i] == '-':
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
    if i >= n:
        raise JSONError("unexpected end of input", n)
    c = s[i]
    if c == '0':
        i += 1
    elif '1' <= c <= '9':
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1
    else:
        raise JSONError("invalid number", i)

    is_float = False

    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    if i < n and s[i] in 'eE':
        is_float = True
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    text = s[start:i]
    if is_float:
        return float(text), i
    return int(text), i


def _parse_string(s, i, n):
    # s[i] == '"'
    i += 1  # skip opening quote
    parts = []
    start = i

    while True:
        if i >= n:
            raise JSONError("unterminated string", n)
        c = s[i]

        if c == '"':
            if start < i:
                parts.append(s[start:i])
            i += 1
            break

        if c == '\\':
            if start < i:
                parts.append(s[start:i])
            i += 1
            if i >= n:
                raise JSONError("unterminated string", n)
            c2 = s[i]

            if c2 == '"':
                parts.append('"'); i += 1
            elif c2 == '\\':
                parts.append('\\'); i += 1
            elif c2 == '/':
                parts.append('/'); i += 1
            elif c2 == 'b':
                parts.append('\b'); i += 1
            elif c2 == 'f':
                parts.append('\f'); i += 1
            elif c2 == 'n':
                parts.append('\n'); i += 1
            elif c2 == 'r':
                parts.append('\r'); i += 1
            elif c2 == 't':
                parts.append('\t'); i += 1
            elif c2 == 'u':
                # exactly 4 ASCII hex digits required at i+1..i+4
                if i + 5 > n:
                    for j in range(i + 1, n):
                        if s[j] not in _HEX:
                            raise JSONError("invalid unicode escape", j)
                    raise JSONError("unterminated string", n)
                h = s[i+1:i+5]
                for j in range(4):
                    if h[j] not in _HEX:
                        raise JSONError("invalid unicode escape", i + 1 + j)
                code = int(h, 16)
                i += 5

                if 0xD800 <= code <= 0xDBFF:
                    # high surrogate – try to combine with next \uXXXX low surrogate
                    combined_ok = False
                    if (i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u'):
                        h2 = s[i+2:i+6]
                        ok = True
                        for j in range(4):
                            if h2[j] not in _HEX:
                                ok = False
                                break
                        if ok:
                            code2 = int(h2, 16)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                cp = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                parts.append(chr(cp))
                                i += 6
                                combined_ok = True
                    if not combined_ok:
                        parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError("invalid escape", i)

            start = i
            continue

        if ord(c) < 0x20:
            raise JSONError("control character in string", i)

        i += 1

    return ''.join(parts), i
