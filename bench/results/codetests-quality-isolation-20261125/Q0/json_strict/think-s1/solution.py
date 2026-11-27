class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = _skip_ws(s, 0, n)
    if pos >= n:
        raise JSONError("empty input", n)

    value, pos = _parse(s, pos, n, 0)
    pos = _skip_ws(s, pos, n)
    if pos < n:
        raise JSONError("trailing garbage", pos)
    return value


def _skip_ws(s, pos, n):
    while pos < n and s[pos] in ' \t\n\r':
        pos += 1
    return pos


def _parse(s, pos, n, depth):
    c = s[pos]

    if c == '{':
        if depth + 1 > 500:
            raise JSONError("maximum nesting depth exceeded", pos)
        pos += 1
        obj = {}
        pos = _skip_ws(s, pos, n)
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos] == '}':
            return obj, pos + 1

        while True:
            if s[pos] != '"':
                raise JSONError(f"expected string key, got {s[pos]!r}", pos)
            key, pos = _parse_string(s, pos, n)
            pos = _skip_ws(s, pos, n)
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] != ':':
                raise JSONError(f"expected ':', got {s[pos]!r}", pos)
            pos += 1
            pos = _skip_ws(s, pos, n)
            if pos >= n:
                raise JSONError("unexpected end of input", n)

            value, pos = _parse(s, pos, n, depth + 1)
            obj[key] = value

            pos = _skip_ws(s, pos, n)
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                pos += 1
                pos = _skip_ws(s, pos, n)
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                if s[pos] == '}':
                    raise JSONError("trailing comma in object", pos)
            elif s[pos] == '}':
                return obj, pos + 1
            else:
                raise JSONError(f"expected ',' or '}}', got {s[pos]!r}", pos)

    elif c == '[':
        if depth + 1 > 500:
            raise JSONError("maximum nesting depth exceeded", pos)
        pos += 1
        arr = []
        pos = _skip_ws(s, pos, n)
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos] == ']':
            return arr, pos + 1

        while True:
            value, pos = _parse(s, pos, n, depth + 1)
            arr.append(value)

            pos = _skip_ws(s, pos, n)
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                pos += 1
                pos = _skip_ws(s, pos, n)
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                if s[pos] == ']':
                    raise JSONError("trailing comma in array", pos)
            elif s[pos] == ']':
                return arr, pos + 1
            else:
                raise JSONError(f"expected ',' or ']', got {s[pos]!r}", pos)

    elif c == '"':
        return _parse_string(s, pos, n)

    elif c == 't':
        expected = 'true'
        for i in range(4):
            if pos + i >= n or s[pos + i] != expected[i]:
                raise JSONError("invalid literal", pos + i)
        return True, pos + 4

    elif c == 'f':
        expected = 'false'
        for i in range(5):
            if pos + i >= n or s[pos + i] != expected[i]:
                raise JSONError("invalid literal", pos + i)
        return False, pos + 5

    elif c == 'n':
        expected = 'null'
        for i in range(4):
            if pos + i >= n or s[pos + i] != expected[i]:
                raise JSONError("invalid literal", pos + i)
        return None, pos + 4

    elif c == '-' or c in '0123456789':
        return _parse_number(s, pos, n)

    else:
        raise JSONError(f"unexpected character {c!r}", pos)


def _parse_number(s, pos, n):
    start = pos

    if s[pos] == '-':
        pos += 1

    if pos >= n:
        raise JSONError("expected digit after '-'", n)
    if s[pos] not in '0123456789':
        raise JSONError(f"expected digit, got {s[pos]!r}", pos)

    if s[pos] == '0':
        pos += 1
    else:
        while pos < n and s[pos] in '0123456789':
            pos += 1

    has_fraction = False
    has_exponent = False

    if pos < n and s[pos] == '.':
        has_fraction = True
        pos += 1
        if pos >= n:
            raise JSONError("expected digit after '.'", n)
        if s[pos] not in '0123456789':
            raise JSONError(f"expected digit after '.', got {s[pos]!r}", pos)
        while pos < n and s[pos] in '0123456789':
            pos += 1

    if pos < n and s[pos] in 'eE':
        has_exponent = True
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n:
            raise JSONError("expected digit in exponent", n)
        if s[pos] not in '0123456789':
            raise JSONError(f"expected digit in exponent, got {s[pos]!r}", pos)
        while pos < n and s[pos] in '0123456789':
            pos += 1

    if pos < n:
        c = s[pos]
        if c in '0123456789.eE+-':
            raise JSONError(f"invalid number continuation {c!r}", pos)

    text = s[start:pos]
    if has_fraction or has_exponent:
        return float(text), pos
    else:
        return int(text), pos


def _parse_string(s, pos, n):
    pos += 1  # skip opening quote
    chars = []

    while True:
        if pos >= n:
            raise JSONError("unterminated string", n)
        c = s[pos]

        if c == '"':
            pos += 1
            return ''.join(chars), pos
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
                hex_chars = []
                for i in range(4):
                    if pos + i >= n:
                        raise JSONError("incomplete \\u escape", n)
                    hc = s[pos + i]
                    if hc not in '0123456789abcdefABCDEF':
                        raise JSONError(f"invalid hex digit {hc!r} in \\u escape", pos + i)
                    hex_chars.append(hc)
                code = int(''.join(hex_chars), 16)
                pos += 4

                if 0xD800 <= code <= 0xDBFF:
                    if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                        valid = True
                        for i in range(4):
                            if s[pos + 2 + i] not in '0123456789abcdefABCDEF':
                                valid = False
                                break
                        if valid:
                            code2 = int(s[pos + 2:pos + 6], 16)
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
                raise JSONError(f"invalid escape character {ec!r}", pos)
        elif ord(c) < 0x20:
            raise JSONError(f"control character U+{ord(c):04X} in string", pos)
        else:
            chars.append(c)
            pos += 1