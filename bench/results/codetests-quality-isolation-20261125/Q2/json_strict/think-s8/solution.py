class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_WS = frozenset(' \t\n\r')
_DIGIT = frozenset('0123456789')
_HEX = frozenset('0123456789abcdefABCDEF')


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")
    n = len(s)
    pos = 0
    while pos < n and s[pos] in _WS:
        pos += 1
    if pos >= n:
        raise JSONError("empty input", n)
    value, pos = _parse_value(s, pos, 0)
    while pos < n and s[pos] in _WS:
        pos += 1
    if pos < n:
        raise JSONError("trailing garbage", pos)
    return value


def _skip_ws(s, pos):
    n = len(s)
    while pos < n and s[pos] in _WS:
        pos += 1
    return pos


def _parse_value(s, pos, depth):
    n = len(s)
    pos = _skip_ws(s, pos)
    if pos >= n:
        raise JSONError("unexpected end of input", n)
    c = s[pos]
    if c == '[':
        if depth >= 500:
            raise JSONError("maximum nesting depth exceeded", pos)
        pos += 1
        arr = []
        pos = _skip_ws(s, pos)
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos] == ']':
            return arr, pos + 1
        while True:
            val, pos = _parse_value(s, pos, depth + 1)
            arr.append(val)
            pos = _skip_ws(s, pos)
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                pos += 1
                pos = _skip_ws(s, pos)
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                if s[pos] == ']':
                    raise JSONError("trailing comma", pos)
            elif s[pos] == ']':
                return arr, pos + 1
            else:
                raise JSONError(f"expected ',' or ']', got {s[pos]!r}", pos)
    elif c == '{':
        if depth >= 500:
            raise JSONError("maximum nesting depth exceeded", pos)
        pos += 1
        obj = {}
        pos = _skip_ws(s, pos)
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos] == '}':
            return obj, pos + 1
        while True:
            if s[pos] != '"':
                raise JSONError(f"expected string key, got {s[pos]!r}", pos)
            key, pos = _parse_string(s, pos)
            pos = _skip_ws(s, pos)
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] != ':':
                raise JSONError(f"expected ':', got {s[pos]!r}", pos)
            pos += 1
            val, pos = _parse_value(s, pos, depth + 1)
            obj[key] = val
            pos = _skip_ws(s, pos)
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                pos += 1
                pos = _skip_ws(s, pos)
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                if s[pos] == '}':
                    raise JSONError("trailing comma", pos)
            elif s[pos] == '}':
                return obj, pos + 1
            else:
                raise JSONError(f"expected ',' or '}}', got {s[pos]!r}", pos)
    elif c == '"':
        return _parse_string(s, pos)
    elif c == 't':
        return _parse_true(s, pos)
    elif c == 'f':
        return _parse_false(s, pos)
    elif c == 'n':
        return _parse_null(s, pos)
    elif c == '-' or c in _DIGIT:
        return _parse_number(s, pos)
    else:
        raise JSONError(f"unexpected character {c!r}", pos)


def _parse_string(s, pos):
    n = len(s)
    pos += 1  # skip opening quote
    chars = []
    while True:
        if pos >= n:
            raise JSONError("unterminated string", n)
        c = s[pos]
        if c == '"':
            return ''.join(chars), pos + 1
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unterminated escape sequence", n)
            ec = s[pos]
            if ec == '"':
                chars.append('"')
                pos += 1
            elif ec == '\\':
                chars.append('\\')
                pos += 1
            elif ec == '/':
                chars.append('/')
                pos += 1
            elif ec == 'b':
                chars.append('\b')
                pos += 1
            elif ec == 'f':
                chars.append('\f')
                pos += 1
            elif ec == 'n':
                chars.append('\n')
                pos += 1
            elif ec == 'r':
                chars.append('\r')
                pos += 1
            elif ec == 't':
                chars.append('\t')
                pos += 1
            elif ec == 'u':
                pos += 1
                if pos + 4 > n:
                    raise JSONError("incomplete \\u escape", n)
                for i in range(4):
                    if s[pos + i] not in _HEX:
                        raise JSONError("invalid hex digit in \\u escape", pos + i)
                code = _hex4_val(s, pos)
                pos += 4
                if 0xD800 <= code <= 0xDBFF:
                    if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                            and s[pos + 2] in _HEX and s[pos + 3] in _HEX
                            and s[pos + 4] in _HEX and s[pos + 5] in _HEX):
                        code2 = _hex4_val(s, pos + 2)
                        if 0xDC00 <= code2 <= 0xDFFF:
                            combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            chars.append(chr(combined))
                            pos += 6
                            continue
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError(f"invalid escape character {ec!r}", pos)
        elif ord(c) < 0x20:
            raise JSONError("control character in string", pos)
        else:
            chars.append(c)
            pos += 1


def _hex_val(c):
    o = ord(c)
    if 48 <= o <= 57:
        return o - 48
    elif 65 <= o <= 70:
        return o - 55
    else:
        return o - 87


def _hex4_val(s, pos):
    return (_hex_val(s[pos]) << 12 |
            _hex_val(s[pos + 1]) << 8 |
            _hex_val(s[pos + 2]) << 4 |
            _hex_val(s[pos + 3]))


def _parse_number(s, pos):
    n = len(s)
    start = pos
    is_float = False

    if pos < n and s[pos] == '-':
        pos += 1

    if pos >= n or s[pos] not in _DIGIT:
        raise JSONError("expected digit", pos)

    if s[pos] == '0':
        pos += 1
        if pos < n and s[pos] in _DIGIT:
            raise JSONError("leading zero not allowed", pos)
    else:
        pos += 1
        while pos < n and s[pos] in _DIGIT:
            pos += 1

    if pos < n and s[pos] == '.':
        is_float = True
        pos += 1
        if pos >= n or s[pos] not in _DIGIT:
            raise JSONError("expected digit after '.'", pos)
        while pos < n and s[pos] in _DIGIT:
            pos += 1

    if pos < n and s[pos] in 'eE':
        is_float = True
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n or s[pos] not in _DIGIT:
            raise JSONError("expected digit in exponent", pos)
        while pos < n and s[pos] in _DIGIT:
            pos += 1

    text = s[start:pos]
    if is_float:
        return float(text), pos
    else:
        return int(text), pos


def _parse_true(s, pos):
    n = len(s)
    for i in range(1, 4):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != 'true'[i]:
            raise JSONError("invalid literal", pos + i)
    return True, pos + 4


def _parse_false(s, pos):
    n = len(s)
    for i in range(1, 5):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != 'false'[i]:
            raise JSONError("invalid literal", pos + i)
    return False, pos + 5


def _parse_null(s, pos):
    n = len(s)
    for i in range(1, 4):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != 'null'[i]:
            raise JSONError("invalid literal", pos + i)
    return None, pos + 4