class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []
    result = None
    state = 'top_value'

    WS = ' \t\n\r'
    DIGITS = '0123456789'
    HEX = '0123456789abcdefABCDEF'

    while True:
        while pos < n and s[pos] in WS:
            pos += 1

        if pos >= n:
            if state == 'top_done':
                break
            raise JSONError("Unexpected end of input", pos)

        c = s[pos]

        if state == 'top_value':
            if c == '"':
                pos, val = _parse_string(s, pos, n)
                result = val
                state = 'top_done'
            elif c == '[':
                pos += 1
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos - 1)
                stack.append(['array', []])
                state = 'arr_first'
            elif c == '{':
                pos += 1
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos - 1)
                stack.append(['object', {}, None])
                state = 'obj_first'
            elif c in '-0123456789':
                pos, val = _parse_number(s, pos, n)
                result = val
                state = 'top_done'
            elif c == 't':
                pos, val = _parse_literal(s, pos, n, 'true', True)
                result = val
                state = 'top_done'
            elif c == 'f':
                pos, val = _parse_literal(s, pos, n, 'false', False)
                result = val
                state = 'top_done'
            elif c == 'n':
                pos, val = _parse_literal(s, pos, n, 'null', None)
                result = val
                state = 'top_done'
            else:
                raise JSONError(f"Unexpected character {c!r}", pos)

        elif state == 'arr_first':
            if c == ']':
                pos += 1
                _, container = stack.pop()
                if not stack:
                    result = container
                    state = 'top_done'
                else:
                    p = stack[-1]
                    if p[0] == 'array':
                        p[1].append(container)
                        state = 'arr_sep'
                    else:
                        p[1][p[2]] = container
                        state = 'obj_sep'
            elif c == '"':
                pos, val = _parse_string(s, pos, n)
                stack[-1][1].append(val)
                state = 'arr_sep'
            elif c == '[':
                pos += 1
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos - 1)
                stack.append(['array', []])
                state = 'arr_first'
            elif c == '{':
                pos += 1
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos - 1)
                stack.append(['object', {}, None])
                state = 'obj_first'
            elif c in '-0123456789':
                pos, val = _parse_number(s, pos, n)
                stack[-1][1].append(val)
                state = 'arr_sep'
            elif c == 't':
                pos, val = _parse_literal(s, pos, n, 'true', True)
                stack[-1][1].append(val)
                state = 'arr_sep'
            elif c == 'f':
                pos, val = _parse_literal(s, pos, n, 'false', False)
                stack[-1][1].append(val)
                state = 'arr_sep'
            elif c == 'n':
                pos, val = _parse_literal(s, pos, n, 'null', None)
                stack[-1][1].append(val)
                state = 'arr_sep'
            else:
                raise JSONError(f"Unexpected character {c!r}", pos)

        elif state == 'arr_value':
            if c == '"':
                pos, val = _parse_string(s, pos, n)
                stack[-1][1].append(val)
                state = 'arr_sep'
            elif c == '[':
                pos += 1
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos - 1)
                stack.append(['array', []])
                state = 'arr_first'
            elif c == '{':
                pos += 1
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos - 1)
                stack.append(['object', {}, None])
                state = 'obj_first'
            elif c in '-0123456789':
                pos, val = _parse_number(s, pos, n)
                stack[-1][1].append(val)
                state = 'arr_sep'
            elif c == 't':
                pos, val = _parse_literal(s, pos, n, 'true', True)
                stack[-1][1].append(val)
                state = 'arr_sep'
            elif c == 'f':
                pos, val = _parse_literal(s, pos, n, 'false', False)
                stack[-1][1].append(val)
                state = 'arr_sep'
            elif c == 'n':
                pos, val = _parse_literal(s, pos, n, 'null', None)
                stack[-1][1].append(val)
                state = 'arr_sep'
            else:
                raise JSONError(f"Unexpected character {c!r}", pos)

        elif state == 'arr_sep':
            if c == ',':
                pos += 1
                state = 'arr_value'
            elif c == ']':
                pos += 1
                _, container = stack.pop()
                if not stack:
                    result = container
                    state = 'top_done'
                else:
                    p = stack[-1]
                    if p[0] == 'array':
                        p[1].append(container)
                        state = 'arr_sep'
                    else:
                        p[1][p[2]] = container
                        state = 'obj_sep'
            else:
                raise JSONError(f"Expected ',' or ']', got {c!r}", pos)

        elif state == 'obj_first':
            if c == '}':
                pos += 1
                _, container, _ = stack.pop()
                if not stack:
                    result = container
                    state = 'top_done'
                else:
                    p = stack[-1]
                    if p[0] == 'array':
                        p[1].append(container)
                        state = 'arr_sep'
                    else:
                        p[1][p[2]] = container
                        state = 'obj_sep'
            elif c == '"':
                pos, key = _parse_string(s, pos, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError(f"Expected string key or '}}', got {c!r}", pos)

        elif state == 'obj_key':
            if c == '"':
                pos, key = _parse_string(s, pos, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError(f"Expected string key, got {c!r}", pos)

        elif state == 'obj_colon':
            if c == ':':
                pos += 1
                state = 'obj_val'
            else:
                raise JSONError(f"Expected ':', got {c!r}", pos)

        elif state == 'obj_val':
            if c == '"':
                pos, val = _parse_string(s, pos, n)
                stack[-1][1][stack[-1][2]] = val
                state = 'obj_sep'
            elif c == '[':
                pos += 1
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos - 1)
                stack.append(['array', []])
                state = 'arr_first'
            elif c == '{':
                pos += 1
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos - 1)
                stack.append(['object', {}, None])
                state = 'obj_first'
            elif c in '-0123456789':
                pos, val = _parse_number(s, pos, n)
                stack[-1][1][stack[-1][2]] = val
                state = 'obj_sep'
            elif c == 't':
                pos, val = _parse_literal(s, pos, n, 'true', True)
                stack[-1][1][stack[-1][2]] = val
                state = 'obj_sep'
            elif c == 'f':
                pos, val = _parse_literal(s, pos, n, 'false', False)
                stack[-1][1][stack[-1][2]] = val
                state = 'obj_sep'
            elif c == 'n':
                pos, val = _parse_literal(s, pos, n, 'null', None)
                stack[-1][1][stack[-1][2]] = val
                state = 'obj_sep'
            else:
                raise JSONError(f"Unexpected character {c!r}", pos)

        elif state == 'obj_sep':
            if c == ',':
                pos += 1
                state = 'obj_key'
            elif c == '}':
                pos += 1
                _, container, _ = stack.pop()
                if not stack:
                    result = container
                    state = 'top_done'
                else:
                    p = stack[-1]
                    if p[0] == 'array':
                        p[1].append(container)
                        state = 'arr_sep'
                    else:
                        p[1][p[2]] = container
                        state = 'obj_sep'
            else:
                raise JSONError(f"Expected ',' or '}}', got {c!r}", pos)

        elif state == 'top_done':
            raise JSONError(f"Trailing data: {c!r}", pos)

    return result


def _parse_string(s, pos, n):
    pos += 1  # skip opening quote
    parts = []
    HEX = '0123456789abcdefABCDEF'
    while True:
        if pos >= n:
            raise JSONError("Unterminated string", pos)
        c = s[pos]
        if c == '"':
            pos += 1
            return pos, ''.join(parts)
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("Unterminated string escape", pos)
            esc = s[pos]
            if esc == '"':
                parts.append('"')
                pos += 1
            elif esc == '\\':
                parts.append('\\')
                pos += 1
            elif esc == '/':
                parts.append('/')
                pos += 1
            elif esc == 'b':
                parts.append('\b')
                pos += 1
            elif esc == 'f':
                parts.append('\f')
                pos += 1
            elif esc == 'n':
                parts.append('\n')
                pos += 1
            elif esc == 'r':
                parts.append('\r')
                pos += 1
            elif esc == 't':
                parts.append('\t')
                pos += 1
            elif esc == 'u':
                if pos + 5 > n:
                    raise JSONError("Incomplete \\u escape", pos + 1)
                h1 = s[pos + 1]
                h2 = s[pos + 2]
                h3 = s[pos + 3]
                h4 = s[pos + 4]
                for i, h in enumerate((h1, h2, h3, h4)):
                    if h not in HEX:
                        raise JSONError("Invalid hex digit in \\u escape", pos + 1 + i)
                code = _hex4(h1, h2, h3, h4)
                pos += 5
                if 0xD800 <= code <= 0xDBFF:
                    if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                        h5 = s[pos + 2]
                        h6 = s[pos + 3]
                        h7 = s[pos + 4]
                        h8 = s[pos + 5]
                        if (h5 in HEX and h6 in HEX and h7 in HEX and h8 in HEX):
                            code2 = _hex4(h5, h6, h7, h8)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                parts.append(chr(combined))
                                pos += 6
                                continue
                parts.append(chr(code))
            else:
                raise JSONError(f"Invalid escape character", pos)
        elif ord(c) < 0x20:
            raise JSONError("Raw control character in string", pos)
        else:
            parts.append(c)
            pos += 1


def _hex4(h1, h2, h3, h4):
    return _hv(h1) * 4096 + _hv(h2) * 256 + _hv(h3) * 16 + _hv(h4)


def _hv(c):
    o = ord(c)
    if 48 <= o <= 57:
        return o - 48
    if 65 <= o <= 70:
        return o - 55
    return o - 87


def _parse_number(s, pos, n):
    start = pos
    if pos < n and s[pos] == '-':
        pos += 1
    if pos >= n:
        raise JSONError("Expected digit after '-'", pos)
    c = s[pos]
    if c == '0':
        pos += 1
        if pos < n and '0' <= s[pos] <= '9':
            raise JSONError("Leading zero not allowed", pos)
    elif '1' <= c <= '9':
        pos += 1
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    else:
        raise JSONError(f"Expected digit, got {c!r}", pos)

    has_fraction = False
    if pos < n and s[pos] == '.':
        has_fraction = True
        pos += 1
        if pos >= n:
            raise JSONError("Expected digit after '.'", pos)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError(f"Expected digit after '.', got {s[pos]!r}", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    has_exponent = False
    if pos < n and (s[pos] == 'e' or s[pos] == 'E'):
        has_exponent = True
        pos += 1
        if pos < n and (s[pos] == '+' or s[pos] == '-'):
            pos += 1
        if pos >= n:
            raise JSONError("Expected digit in exponent", pos)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError(f"Expected digit in exponent, got {s[pos]!r}", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if has_fraction or has_exponent:
        return pos, float(text)
    else:
        return pos, int(text)


def _parse_literal(s, pos, n, expected, value):
    for i in range(len(expected)):
        if pos + i >= n or s[pos + i] != expected[i]:
            raise JSONError(f"Invalid literal, expected {expected!r}", pos + i)
    return pos + len(expected), value