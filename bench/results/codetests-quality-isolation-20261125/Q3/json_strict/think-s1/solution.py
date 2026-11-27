class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    i = 0
    _WS = ' \t\n\r'
    _HEX = '0123456789abcdefABCDEF'

    def skip_ws():
        nonlocal i
        while i < n and s[i] in _WS:
            i += 1

    def _hex4(pos):
        val = 0
        for j in range(4):
            c = s[pos + j]
            if '0' <= c <= '9':
                val = val * 16 + (ord(c) - 48)
            elif 'a' <= c <= 'f':
                val = val * 16 + (ord(c) - 87)
            elif 'A' <= c <= 'F':
                val = val * 16 + (ord(c) - 55)
            else:
                raise JSONError("invalid hex digit in \\u escape", pos + j)
        return val

    def parse_string():
        nonlocal i
        i += 1  # consume opening "
        chars = []
        while True:
            if i >= n:
                raise JSONError("unterminated string", n)
            c = s[i]
            if c == '"':
                i += 1
                return ''.join(chars)
            if c == '\\':
                i += 1
                if i >= n:
                    raise JSONError("unterminated escape sequence", n)
                ec = s[i]
                if ec == '"':
                    chars.append('"')
                    i += 1
                elif ec == '\\':
                    chars.append('\\')
                    i += 1
                elif ec == '/':
                    chars.append('/')
                    i += 1
                elif ec == 'b':
                    chars.append('\b')
                    i += 1
                elif ec == 'f':
                    chars.append('\f')
                    i += 1
                elif ec == 'n':
                    chars.append('\n')
                    i += 1
                elif ec == 'r':
                    chars.append('\r')
                    i += 1
                elif ec == 't':
                    chars.append('\t')
                    i += 1
                elif ec == 'u':
                    i += 1
                    if i + 4 > n:
                        raise JSONError("truncated \\u escape", n)
                    code = _hex4(i)
                    i += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if (i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u'
                                and s[i + 2] in _HEX and s[i + 3] in _HEX
                                and s[i + 4] in _HEX and s[i + 5] in _HEX):
                            code2 = _hex4(i + 2)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                code = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                i += 6
                                chars.append(chr(code))
                                continue
                    chars.append(chr(code))
                else:
                    raise JSONError("invalid escape character", i)
            elif ord(c) < 0x20:
                raise JSONError("raw control character in string", i)
            else:
                chars.append(c)
                i += 1

    def parse_number():
        nonlocal i
        start = i
        if s[i] == '-':
            i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if s[i] == '0':
            i += 1
        elif '1' <= s[i] <= '9':
            i += 1
            while i < n and '0' <= s[i] <= '9':
                i += 1
        else:
            raise JSONError("invalid digit in number", i)
        is_float = False
        if i < n and s[i] == '.':
            is_float = True
            i += 1
            if i >= n or not ('0' <= s[i] <= '9'):
                raise JSONError("expected digit after decimal point", i if i < n else n)
            while i < n and '0' <= s[i] <= '9':
                i += 1
        if i < n and (s[i] == 'e' or s[i] == 'E'):
            is_float = True
            i += 1
            if i < n and (s[i] == '+' or s[i] == '-'):
                i += 1
            if i >= n or not ('0' <= s[i] <= '9'):
                raise JSONError("expected digit in exponent", i if i < n else n)
            while i < n and '0' <= s[i] <= '9':
                i += 1
        text = s[start:i]
        if is_float:
            return float(text)
        return int(text)

    def parse_literal(expected, value):
        nonlocal i
        for j in range(len(expected)):
            if i + j >= n:
                raise JSONError("unexpected end of input", n)
            if s[i + j] != expected[j]:
                raise JSONError("invalid literal", i + j)
        i += len(expected)
        return value

    def parse_scalar():
        nonlocal i
        c = s[i]
        if c == '"':
            return parse_string()
        elif c == 't':
            return parse_literal('true', True)
        elif c == 'f':
            return parse_literal('false', False)
        elif c == 'n':
            return parse_literal('null', None)
        elif c == '-' or '0' <= c <= '9':
            return parse_number()
        else:
            raise JSONError(f"unexpected character {c!r}", i)

    def parse_object(depth):
        nonlocal i
        i += 1  # consume '{'
        skip_ws()
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if s[i] == '}':
            i += 1
            return {}
        d = {}
        while True:
            skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] != '"':
                raise JSONError("expected string key", i)
            key = parse_string()
            skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] != ':':
                raise JSONError("expected ':'", i)
            i += 1
            skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '{':
                if depth + 1 > 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                val = parse_object(depth + 1)
            elif c == '[':
                if depth + 1 > 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                val = parse_array(depth + 1)
            else:
                val = parse_scalar()
            d[key] = val
            skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ',':
                i += 1
            elif s[i] == '}':
                i += 1
                return d
            else:
                raise JSONError("expected ',' or '}'", i)

    def parse_array(depth):
        nonlocal i
        i += 1  # consume '['
        skip_ws()
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if s[i] == ']':
            i += 1
            return []
        arr = []
        while True:
            skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '{':
                if depth + 1 > 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                val = parse_object(depth + 1)
            elif c == '[':
                if depth + 1 > 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                val = parse_array(depth + 1)
            else:
                val = parse_scalar()
            arr.append(val)
            skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ',':
                i += 1
            elif s[i] == ']':
                i += 1
                return arr
            else:
                raise JSONError("expected ',' or ']'", i)

    # Top-level dispatch
    skip_ws()
    if i >= n:
        raise JSONError("unexpected end of input", n)
    c = s[i]
    if c == '{':
        result = parse_object(1)
    elif c == '[':
        result = parse_array(1)
    else:
        result = parse_scalar()

    skip_ws()
    if i < n:
        raise JSONError("trailing garbage", i)
    return result