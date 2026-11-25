class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")
    n = len(s)
    pos = 0
    while pos < n and s[pos] in ' \t\n\r':
        pos += 1
    if pos >= n:
        raise JSONError("unexpected end of input", n)
    value, pos = _parse_value(s, pos, n, 0)
    while pos < n and s[pos] in ' \t\n\r':
        pos += 1
    if pos < n:
        raise JSONError("trailing garbage", pos)
    return value


def _parse_value(s, pos, n, depth):
    while pos < n and s[pos] in ' \t\n\r':
        pos += 1
    if pos >= n:
        raise JSONError("unexpected end of input", n)
    c = s[pos]
    if c == '{':
        if depth + 1 > 500:
            raise JSONError("nesting depth limit exceeded", pos)
        pos += 1
        obj = {}
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos] == '}':
            pos += 1
            return obj, pos
        while True:
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] != '"':
                raise JSONError("expected string key", pos)
            key, pos = _parse_string(s, pos, n)
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] != ':':
                raise JSONError("expected ':'", pos)
            pos += 1
            value, pos = _parse_value(s, pos, n, depth + 1)
            obj[key] = value
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                pos += 1
                while pos < n and s[pos] in ' \t\n\r':
                    pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                if s[pos] == '}':
                    raise JSONError("trailing comma in object", pos)
            elif s[pos] == '}':
                pos += 1
                return obj, pos
            else:
                raise JSONError("expected ',' or '}'", pos)
    elif c == '[':
        if depth + 1 > 500:
            raise JSONError("nesting depth limit exceeded", pos)
        pos += 1
        arr = []
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos] == ']':
            pos += 1
            return arr, pos
        while True:
            value, pos = _parse_value(s, pos, n, depth + 1)
            arr.append(value)
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                pos += 1
                while pos < n and s[pos] in ' \t\n\r':
                    pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                if s[pos] == ']':
                    raise JSONError("trailing comma in array", pos)
            elif s[pos] == ']':
                pos += 1
                return arr, pos
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
    elif c == '-' or '0' <= c <= '9':
        return _parse_number(s, pos, n)
    else:
        raise JSONError(f"unexpected character {c!r}", pos)


def _parse_string(s, pos, n):
    pos += 1  # skip opening quote
    result = []
    while True:
        if pos >= n:
            raise JSONError("unterminated string", n)
        c = s[pos]
        if c == '"':
            pos += 1
            return ''.join(result), pos
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unterminated escape sequence", n)
            ec = s[pos]
            if ec == '"':
                result.append('"')
                pos += 1
            elif ec == '\\':
                result.append('\\')
                pos += 1
            elif ec == '/':
                result.append('/')
                pos += 1
            elif ec == 'b':
                result.append('\b')
                pos += 1
            elif ec == 'f':
                result.append('\f')
                pos += 1
            elif ec == 'n':
                result.append('\n')
                pos += 1
            elif ec == 'r':
                result.append('\r')
                pos += 1
            elif ec == 't':
                result.append('\t')
                pos += 1
            elif ec == 'u':
                pos += 1
                if pos + 4 > n:
                    raise JSONError("truncated \\u escape", n)
                v1 = _hex_val(s[pos])
                if v1 < 0:
                    raise JSONError("invalid hex digit in \\u escape", pos)
                v2 = _hex_val(s[pos + 1])
                if v2 < 0:
                    raise JSONError("invalid hex digit in \\u escape", pos + 1)
                v3 = _hex_val(s[pos + 2])
                if v3 < 0:
                    raise JSONError("invalid hex digit in \\u escape", pos + 2)
                v4 = _hex_val(s[pos + 3])
                if v4 < 0:
                    raise JSONError("invalid hex digit in \\u escape", pos + 3)
                code = v1 * 4096 + v2 * 256 + v3 * 16 + v4
                pos += 4
                if 0xD800 <= code <= 0xDBFF:
                    if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                            and _hex_val(s[pos + 2]) >= 0
                            and _hex_val(s[pos + 3]) >= 0
                            and _hex_val(s[pos + 4]) >= 0
                            and _hex_val(s[pos + 5]) >= 0):
                        code2 = (_hex_val(s[pos + 2]) * 4096
                                 + _hex_val(s[pos + 3]) * 256
                                 + _hex_val(s[pos + 4]) * 16
                                 + _hex_val(s[pos + 5]))
                        if 0xDC00 <= code2 <= 0xDFFF:
                            combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            result.append(chr(combined))
                            pos += 6
                            continue
                    result.append(chr(code))
                else:
                    result.append(chr(code))
            else:
                raise JSONError(f"invalid escape character '\\{ec}'", pos)
        elif ord(c) < 0x20:
            raise JSONError("unescaped control character in string", pos)
        else:
            result.append(c)
            pos += 1


def _parse_number(s, pos, n):
    start = pos
    if s[pos] == '-':
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
    c = s[pos]
    if c == '0':
        pos += 1
    elif '1' <= c <= '9':
        pos += 1
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    else:
        raise JSONError("expected digit", pos)
    has_fraction = False
    if pos < n and s[pos] == '.':
        has_fraction = True
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit after '.'", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    has_exponent = False
    if pos < n and s[pos] in 'eE':
        has_exponent = True
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit in exponent", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    text = s[start:pos]
    if has_fraction or has_exponent:
        return float(text), pos
    else:
        return int(text), pos


def _parse_literal(s, pos, n, expected, value):
    for i in range(len(expected)):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != expected[i]:
            raise JSONError(f"invalid literal at position {pos + i}", pos + i)
    pos += len(expected)
    return value, pos


def _hex_val(c):
    if '0' <= c <= '9':
        return ord(c) - 48
    if 'a' <= c <= 'f':
        return ord(c) - 87
    if 'A' <= c <= 'F':
        return ord(c) - 55
    return -1