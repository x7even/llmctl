class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_WS = ' \t\n\r'
_DIGITS = '0123456789'
_HEX = '0123456789abcdefABCDEF'


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0

    while pos < n and s[pos] in _WS:
        pos += 1

    if pos >= n:
        raise JSONError("empty input", n)

    value, pos = _parse_value(s, pos, n, 0)

    while pos < n and s[pos] in _WS:
        pos += 1

    if pos < n:
        raise JSONError("trailing garbage", pos)

    return value


def _skip_ws(s, pos, n):
    while pos < n and s[pos] in _WS:
        pos += 1
    return pos


def _parse_value(s, pos, n, depth):
    if pos >= n:
        raise JSONError("unexpected end of input", pos)

    c = s[pos]

    if c == '{':
        if depth >= 500:
            raise JSONError("nesting too deep", pos)
        pos += 1
        obj = {}
        pos = _skip_ws(s, pos, n)
        if pos >= n:
            raise JSONError("unexpected end of input", pos)
        if s[pos] == '}':
            return obj, pos + 1
        while True:
            pos = _skip_ws(s, pos, n)
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] != '"':
                raise JSONError("expected string key", pos)
            key, pos = _parse_string(s, pos, n)
            pos = _skip_ws(s, pos, n)
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] != ':':
                raise JSONError("expected ':'", pos)
            pos += 1
            pos = _skip_ws(s, pos, n)
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            val, pos = _parse_value(s, pos, n, depth + 1)
            obj[key] = val
            pos = _skip_ws(s, pos, n)
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] == ',':
                pos += 1
                pos = _skip_ws(s, pos, n)
                if pos >= n:
                    raise JSONError("unexpected end of input", pos)
                if s[pos] == '}':
                    raise JSONError("trailing comma", pos)
            elif s[pos] == '}':
                return obj, pos + 1
            else:
                raise JSONError("expected ',' or '}'", pos)

    elif c == '[':
        if depth >= 500:
            raise JSONError("nesting too deep", pos)
        pos += 1
        arr = []
        pos = _skip_ws(s, pos, n)
        if pos >= n:
            raise JSONError("unexpected end of input", pos)
        if s[pos] == ']':
            return arr, pos + 1
        while True:
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            val, pos = _parse_value(s, pos, n, depth + 1)
            arr.append(val)
            pos = _skip_ws(s, pos, n)
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] == ',':
                pos += 1
                pos = _skip_ws(s, pos, n)
                if pos >= n:
                    raise JSONError("unexpected end of input", pos)
                if s[pos] == ']':
                    raise JSONError("trailing comma", pos)
            elif s[pos] == ']':
                return arr, pos + 1
            else:
                raise JSONError("expected ',' or ']'", pos)

    elif c == '"':
        return _parse_string(s, pos, n)
    elif c == 't':
        return _parse_literal(s, pos, n, 'true', True)
    elif c == 'f':
        return _parse_literal(s, pos, n, 'false', False)
    elif c == 'n':
        return _parse_literal(s, pos, n, 'null', None)
    elif c == '-' or c in _DIGITS:
        return _parse_number(s, pos, n)
    else:
        raise JSONError("unexpected character", pos)


def _parse_literal(s, pos, n, literal, value):
    for i in range(len(literal)):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != literal[i]:
            raise JSONError("invalid literal", pos + i)
    return value, pos + len(literal)


def _parse_number(s, pos, n):
    start = pos

    if s[pos] == '-':
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", pos)

    if s[pos] == '0':
        pos += 1
        if pos < n and s[pos] in _DIGITS:
            raise JSONError("leading zero not allowed", pos)
    elif s[pos] in '123456789':
        pos += 1
        while pos < n and s[pos] in _DIGITS:
            pos += 1
    else:
        raise JSONError("invalid number", pos)

    is_float = False

    if pos < n and s[pos] == '.':
        is_float = True
        pos += 1
        if pos >= n or s[pos] not in _DIGITS:
            raise JSONError("expected digit after '.'", pos)
        while pos < n and s[pos] in _DIGITS:
            pos += 1

    if pos < n and s[pos] in 'eE':
        is_float = True
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n or s[pos] not in _DIGITS:
            raise JSONError("expected digit in exponent", pos)
        while pos < n and s[pos] in _DIGITS:
            pos += 1

    text = s[start:pos]
    if is_float:
        return float(text), pos
    else:
        return int(text), pos


def _parse_string(s, pos, n):
    pos += 1  # skip opening quote
    chars = []

    while True:
        if pos >= n:
            raise JSONError("unterminated string", pos)

        c = s[pos]

        if c == '"':
            pos += 1
            return ''.join(chars), pos

        if c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unterminated escape", pos)
            esc = s[pos]
            if esc == '"':
                chars.append('"')
                pos += 1
            elif esc == '\\':
                chars.append('\\')
                pos += 1
            elif esc == '/':
                chars.append('/')
                pos += 1
            elif esc == 'b':
                chars.append('\b')
                pos += 1
            elif esc == 'f':
                chars.append('\f')
                pos += 1
            elif esc == 'n':
                chars.append('\n')
                pos += 1
            elif esc == 'r':
                chars.append('\r')
                pos += 1
            elif esc == 't':
                chars.append('\t')
                pos += 1
            elif esc == 'u':
                pos += 1
                if pos + 4 > n:
                    raise JSONError("unexpected end of input", n)
                for i in range(4):
                    if s[pos + i] not in _HEX:
                        raise JSONError("invalid hex digit in \\u escape", pos + i)
                code = _hex4(s, pos)
                pos += 4

                if 0xD800 <= code <= 0xDBFF:
                    if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                            and all(s[pos + 2 + i] in _HEX for i in range(4))):
                        code2 = _hex4(s, pos + 2)
                        if 0xDC00 <= code2 <= 0xDFFF:
                            combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            chars.append(chr(combined))
                            pos += 6
                            continue
                    chars.append(chr(code))
                elif 0xDC00 <= code <= 0xDFFF:
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError("invalid escape", pos)
        elif ord(c) < 0x20:
            raise JSONError("unescaped control character in string", pos)
        else:
            chars.append(c)
            pos += 1


def _hex4(s, pos):
    val = 0
    for i in range(4):
        c = s[pos + i]
        if '0' <= c <= '9':
            val = val * 16 + (ord(c) - 48)
        elif 'a' <= c <= 'f':
            val = val * 16 + (ord(c) - 87)
        elif 'A' <= c <= 'F':
            val = val * 16 + (ord(c) - 55)
        else:
            raise JSONError("invalid hex digit", pos + i)
    return val