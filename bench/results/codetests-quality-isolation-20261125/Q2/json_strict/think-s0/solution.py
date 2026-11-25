class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, not {type(s).__name__}")

    n = len(s)
    i = 0
    stack = []
    current_key = None
    expect = 'value'
    result = None

    WS = ' \t\n\r'
    HEX = '0123456789abcdefABCDEF'

    def _skip_ws():
        nonlocal i
        while i < n and s[i] in WS:
            i += 1

    def _parse_string():
        nonlocal i
        i += 1
        parts = []
        while True:
            if i >= n:
                raise JSONError("unexpected end of string", n)
            c = s[i]
            if c == '"':
                i += 1
                return ''.join(parts)
            if c == '\\':
                i += 1
                if i >= n:
                    raise JSONError("unexpected end of string", n)
                e = s[i]
                if e == '"':
                    parts.append('"')
                    i += 1
                elif e == '\\':
                    parts.append('\\')
                    i += 1
                elif e == '/':
                    parts.append('/')
                    i += 1
                elif e == 'b':
                    parts.append('\b')
                    i += 1
                elif e == 'f':
                    parts.append('\f')
                    i += 1
                elif e == 'n':
                    parts.append('\n')
                    i += 1
                elif e == 'r':
                    parts.append('\r')
                    i += 1
                elif e == 't':
                    parts.append('\t')
                    i += 1
                elif e == 'u':
                    i += 1
                    if i + 4 > n:
                        raise JSONError("unexpected end of unicode escape", n)
                    h = s[i:i + 4]
                    for j in range(4):
                        if h[j] not in HEX:
                            raise JSONError("invalid hex digit in \\u escape", i + j)
                    code = int(h, 16)
                    i += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u':
                            h2 = s[i + 2:i + 6]
                            valid = True
                            for j in range(4):
                                if h2[j] not in HEX:
                                    valid = False
                                    break
                            if valid:
                                code2 = int(h2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    cp = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    parts.append(chr(cp))
                                    i += 6
                                    continue
                    parts.append(chr(code))
                else:
                    raise JSONError(f"invalid escape character", i)
            elif ord(c) < 0x20:
                raise JSONError("unescaped control character in string", i)
            else:
                parts.append(c)
                i += 1

    def _parse_number():
        nonlocal i
        start = i
        is_float = False

        if s[i] == '-':
            i += 1
        if i >= n:
            raise JSONError("unexpected end of number", n)

        c = s[i]
        if c == '0':
            i += 1
            if i < n and '0' <= s[i] <= '9':
                raise JSONError("invalid number: leading zero", i)
        elif '1' <= c <= '9':
            i += 1
            while i < n and '0' <= s[i] <= '9':
                i += 1
        else:
            raise JSONError("invalid number", i)

        if i < n and s[i] == '.':
            is_float = True
            i += 1
            if i >= n:
                raise JSONError("unexpected end of number", n)
            if not ('0' <= s[i] <= '9'):
                raise JSONError("expected digit after decimal point", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1

        if i < n and s[i] in 'eE':
            is_float = True
            i += 1
            if i < n and s[i] in '+-':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of number", n)
            if not ('0' <= s[i] <= '9'):
                raise JSONError("expected digit in exponent", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1

        text = s[start:i]
        if is_float:
            return float(text)
        return int(text)

    def _parse_literal(expected):
        nonlocal i
        ln = len(expected)
        for j in range(ln):
            if i + j >= n:
                raise JSONError("unexpected end of input", n)
            if s[i + j] != expected[j]:
                raise JSONError("invalid literal", i + j)
        i += ln
        if expected == 'true':
            return True
        elif expected == 'false':
            return False
        return None

    def _after_value():
        nonlocal expect
        if not stack:
            expect = 'done'
        elif stack[-1][0] == 'array':
            stack[-1][1].append(result)
            expect = 'array_end_or_comma'
        else:
            stack[-1][1][current_key] = result
            expect = 'obj_end_or_comma'

    while True:
        if expect == 'value':
            _skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '"':
                result = _parse_string()
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                i += 1
                stack.append(('array', []))
                expect = 'array_first'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                i += 1
                stack.append(('object', {}))
                expect = 'obj_key_or_end'
            elif c == 't':
                result = _parse_literal('true')
            elif c == 'f':
                result = _parse_literal('false')
            elif c == 'n':
                result = _parse_literal('null')
            elif c == '-' or '0' <= c <= '9':
                result = _parse_number()
            else:
                raise JSONError(f"unexpected character {c!r}", i)
            _after_value()

        elif expect == 'array_first':
            _skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ']':
                i += 1
                _, lst = stack.pop()
                result = lst
                _after_value()
            else:
                expect = 'value'

        elif expect == 'array_end_or_comma':
            _skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == ']':
                i += 1
                _, lst = stack.pop()
                result = lst
                _after_value()
            elif c == ',':
                i += 1
                expect = 'value'
            else:
                raise JSONError(f"expected ',' or ']', got {c!r}", i)

        elif expect == 'obj_key_or_end':
            _skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '}':
                i += 1
                _, dct = stack.pop()
                result = dct
                _after_value()
            elif c == '"':
                current_key = _parse_string()
                expect = 'obj_colon'
            else:
                raise JSONError(f"expected string key or '}}', got {c!r}", i)

        elif expect == 'obj_next_key':
            _skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '"':
                current_key = _parse_string()
                expect = 'obj_colon'
            else:
                raise JSONError(f"expected string key, got {c!r}", i)

        elif expect == 'obj_colon':
            _skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ':':
                i += 1
                expect = 'value'
            else:
                raise JSONError(f"expected ':', got {s[i]!r}", i)

        elif expect == 'obj_end_or_comma':
            _skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '}':
                i += 1
                _, dct = stack.pop()
                result = dct
                _after_value()
            elif c == ',':
                i += 1
                expect = 'obj_next_key'
            else:
                raise JSONError(f"expected ',' or '}}', got {c!r}", i)

        elif expect == 'done':
            _skip_ws()
            if i < n:
                raise JSONError("trailing garbage", i)
            return result
