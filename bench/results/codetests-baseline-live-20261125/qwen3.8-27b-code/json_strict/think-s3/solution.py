class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1

    def parse_hex4(start):
        if start + 4 > n:
            raise JSONError("unexpected end of input", n)
        code = 0
        for i in range(4):
            c = s[start + i]
            if '0' <= c <= '9':
                d = ord(c) - 48
            elif 'a' <= c <= 'f':
                d = ord(c) - 97 + 10
            elif 'A' <= c <= 'F':
                d = ord(c) - 65 + 10
            else:
                raise JSONError("invalid hex digit in \\u escape", start + i)
            code = code * 16 + d
        return code, start + 4

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening quote
        parts = []
        while True:
            if pos >= n:
                raise JSONError("unexpected end of input in string", pos)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(parts)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of input in string", pos)
                ec = s[pos]
                if ec == '"':
                    parts.append('"')
                    pos += 1
                elif ec == '\\':
                    parts.append('\\')
                    pos += 1
                elif ec == '/':
                    parts.append('/')
                    pos += 1
                elif ec == 'b':
                    parts.append('\b')
                    pos += 1
                elif ec == 'f':
                    parts.append('\f')
                    pos += 1
                elif ec == 'n':
                    parts.append('\n')
                    pos += 1
                elif ec == 'r':
                    parts.append('\r')
                    pos += 1
                elif ec == 't':
                    parts.append('\t')
                    pos += 1
                elif ec == 'u':
                    pos += 1
                    code, pos = parse_hex4(pos)
                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 6 <= n and
                                s[pos] == '\\' and
                                s[pos + 1] == 'u'):
                            lo_code, lo_end = parse_hex4(pos + 2)
                            if 0xDC00 <= lo_code <= 0xDFFF:
                                cp = 0x10000 + ((code - 0xD800) << 10) + (lo_code - 0xDC00)
                                parts.append(chr(cp))
                                pos = lo_end
                            else:
                                parts.append(chr(code))
                        else:
                            parts.append(chr(code))
                    else:
                        parts.append(chr(code))
                else:
                    raise JSONError("invalid escape character", pos)
            elif ord(c) < 0x20:
                raise JSONError("unescaped control character in string", pos)
            else:
                parts.append(c)
                pos += 1

    def parse_number():
        nonlocal pos
        start = pos
        if s[pos] == '-':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
        c = s[pos]
        if c == '0':
            pos += 1
            if pos < n and '0' <= s[pos] <= '9':
                raise JSONError("leading zero in number", pos)
        elif '1' <= c <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            raise JSONError("invalid number", pos)

        has_frac = False
        has_exp = False

        if pos < n and s[pos] == '.':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit after decimal point", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
            has_frac = True

        if pos < n and s[pos] in 'eE':
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
            has_exp = True

        text = s[start:pos]
        if has_frac or has_exp:
            return float(text)
        else:
            return int(text)

    def parse_literal(expected, value):
        nonlocal pos
        for i, c in enumerate(expected):
            if pos + i >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos + i] != c:
                raise JSONError("invalid literal", pos + i)
        pos += len(expected)
        return value

    def parse_value(depth):
        nonlocal pos
        skip_ws()
        if pos >= n:
            raise JSONError("unexpected end of input", pos)

        c = s[pos]
        if c == '{':
            if depth + 1 > 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            obj = {}
            skip_ws()
            if pos < n and s[pos] == '}':
                pos += 1
                return obj
            while True:
                skip_ws()
                if pos >= n:
                    raise JSONError("unexpected end of input", pos)
                if s[pos] != '"':
                    raise JSONError("expected string key", pos)
                key = parse_string()
                skip_ws()
                if pos >= n:
                    raise JSONError("unexpected end of input", pos)
                if s[pos] != ':':
                    raise JSONError("expected colon", pos)
                pos += 1
                value = parse_value(depth + 1)
                obj[key] = value
                skip_ws()
                if pos >= n:
                    raise JSONError("unexpected end of input", pos)
                if s[pos] == ',':
                    pos += 1
                    skip_ws()
                    if pos < n and s[pos] == '}':
                        raise JSONError("trailing comma in object", pos)
                elif s[pos] == '}':
                    pos += 1
                    return obj
                else:
                    raise JSONError("expected comma or closing brace", pos)
        elif c == '[':
            if depth + 1 > 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            arr = []
            skip_ws()
            if pos < n and s[pos] == ']':
                pos += 1
                return arr
            while True:
                elem = parse_value(depth + 1)
                arr.append(elem)
                skip_ws()
                if pos >= n:
                    raise JSONError("unexpected end of input", pos)
                if s[pos] == ',':
                    pos += 1
                    skip_ws()
                    if pos < n and s[pos] == ']':
                        raise JSONError("trailing comma in array", pos)
                elif s[pos] == ']':
                    pos += 1
                    return arr
                else:
                    raise JSONError("expected comma or closing bracket", pos)
        elif c == '"':
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
            raise JSONError(f"unexpected character {c!r}", pos)

    result = parse_value(0)
    skip_ws()
    if pos != n:
        raise JSONError("trailing garbage", pos)
    return result
