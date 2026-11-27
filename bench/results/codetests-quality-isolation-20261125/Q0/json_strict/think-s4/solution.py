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
    _WS = ' \t\n\r'
    _HEX = '0123456789abcdefABCDEF'

    def _skip_ws(p):
        while p < n and s[p] in _WS:
            p += 1
        return p

    def _parse_string(p):
        p += 1
        result = []
        while True:
            if p >= n:
                raise JSONError("unterminated string", n)
            c = s[p]
            if c == '"':
                p += 1
                return ''.join(result), p
            elif c == '\\':
                p += 1
                if p >= n:
                    raise JSONError("unterminated escape", n)
                ec = s[p]
                if ec == '"':
                    result.append('"'); p += 1
                elif ec == '\\':
                    result.append('\\'); p += 1
                elif ec == '/':
                    result.append('/'); p += 1
                elif ec == 'b':
                    result.append('\b'); p += 1
                elif ec == 'f':
                    result.append('\f'); p += 1
                elif ec == 'n':
                    result.append('\n'); p += 1
                elif ec == 'r':
                    result.append('\r'); p += 1
                elif ec == 't':
                    result.append('\t'); p += 1
                elif ec == 'u':
                    if p + 5 > n:
                        for i in range(p + 1, n):
                            if s[i] not in _HEX:
                                raise JSONError("invalid \\u escape", i)
                        raise JSONError("incomplete \\u escape", n)
                    hex_str = s[p + 1:p + 5]
                    for i, hc in enumerate(hex_str):
                        if hc not in _HEX:
                            raise JSONError("invalid \\u escape", p + 1 + i)
                    code = int(hex_str, 16)
                    p += 5
                    if 0xD800 <= code <= 0xDBFF:
                        if p + 6 <= n and s[p] == '\\' and s[p + 1] == 'u':
                            hex2 = s[p + 2:p + 6]
                            valid = True
                            for hc in hex2:
                                if hc not in _HEX:
                                    valid = False
                                    break
                            if valid:
                                code2 = int(hex2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    result.append(chr(combined))
                                    p += 6
                                    continue
                    result.append(chr(code))
                else:
                    raise JSONError(f"invalid escape '\\{ec}'", p)
            elif ord(c) < 0x20:
                raise JSONError("control character in string", p)
            else:
                result.append(c)
                p += 1

    def _parse_number(p):
        start = p
        is_float = False
        if s[p] == '-':
            p += 1
        if p >= n:
            raise JSONError("incomplete number", n)
        c = s[p]
        if c == '0':
            p += 1
            if p < n and '0' <= s[p] <= '9':
                raise JSONError("leading zero", p)
        elif '1' <= c <= '9':
            p += 1
            while p < n and '0' <= s[p] <= '9':
                p += 1
        else:
            raise JSONError("invalid number", p)
        if p < n and s[p] == '.':
            is_float = True
            p += 1
            if p >= n:
                raise JSONError("incomplete number", n)
            if not ('0' <= s[p] <= '9'):
                raise JSONError("expected digit after '.'", p)
            while p < n and '0' <= s[p] <= '9':
                p += 1
        if p < n and s[p] in 'eE':
            is_float = True
            p += 1
            if p < n and s[p] in '+-':
                p += 1
            if p >= n:
                raise JSONError("incomplete number", n)
            if not ('0' <= s[p] <= '9'):
                raise JSONError("expected digit in exponent", p)
            while p < n and '0' <= s[p] <= '9':
                p += 1
        text = s[start:p]
        if is_float:
            return float(text), p
        return int(text), p

    # Iterative parser with explicit stack to avoid RecursionError
    stack = []
    _SENTINEL = object()
    value = _SENTINEL

    while True:
        # Place pending value into parent container
        if value is not _SENTINEL:
            if not stack:
                break
            frame = stack[-1]
            if frame[0] == 'array':
                frame[1].append(value)
                frame[2] = 'comma_end'
            else:
                frame[1][frame[3]] = value
                frame[2] = 'comma_end'
                frame[3] = None
            value = _SENTINEL

        # Determine what to do next
        if not stack:
            mode = 'value'
        else:
            mode = stack[-1][2]

        if mode == 'value':
            pos = _skip_ws(pos)
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '"':
                value, pos = _parse_string(pos)
            elif c == '-' or '0' <= c <= '9':
                value, pos = _parse_number(pos)
            elif c == 't':
                if pos + 4 <= n and s[pos + 1] == 'r' and s[pos + 2] == 'u' and s[pos + 3] == 'e':
                    value = True
                    pos += 4
                else:
                    for i in range(4):
                        if pos + i >= n or s[pos + i] != 'true'[i]:
                            raise JSONError("invalid literal", pos + i)
                    raise JSONError("invalid literal", pos)
            elif c == 'f':
                if pos + 5 <= n and s[pos + 1] == 'a' and s[pos + 2] == 'l' and s[pos + 3] == 's' and s[pos + 4] == 'e':
                    value = False
                    pos += 5
                else:
                    for i in range(5):
                        if pos + i >= n or s[pos + i] != 'false'[i]:
                            raise JSONError("invalid literal", pos + i)
                    raise JSONError("invalid literal", pos)
            elif c == 'n':
                if pos + 4 <= n and s[pos + 1] == 'u' and s[pos + 2] == 'l' and s[pos + 3] == 'l':
                    value = None
                    pos += 4
                else:
                    for i in range(4):
                        if pos + i >= n or s[pos + i] != 'null'[i]:
                            raise JSONError("invalid literal", pos + i)
                    raise JSONError("invalid literal", pos)
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("nesting too deep", pos)
                pos += 1
                stack.append(['array', [], 'val', None])
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("nesting too deep", pos)
                pos += 1
                stack.append(['object', {}, 'key', None])
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif mode == 'comma_end':
            pos = _skip_ws(pos)
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            frame = stack[-1]
            if frame[0] == 'array':
                if c == ',':
                    pos += 1
                    frame[2] = 'val'
                elif c == ']':
                    pos += 1
                    stack.pop()
                    value = frame[1]
                else:
                    raise JSONError(f"expected ',' or ']', got {c!r}", pos)
            else:
                if c == ',':
                    pos += 1
                    frame[2] = 'key'
                elif c == '}':
                    pos += 1
                    stack.pop()
                    value = frame[1]
                else:
                    raise JSONError(f"expected ',' or '}}', got {c!r}", pos)

        elif mode == 'key':
            pos = _skip_ws(pos)
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            frame = stack[-1]
            if c == '}':
                pos += 1
                stack.pop()
                value = frame[1]
            elif c == '"':
                key, pos = _parse_string(pos)
                frame[3] = key
                frame[2] = 'colon'
            else:
                raise JSONError(f"expected string key or '}}', got {c!r}", pos)

        elif mode == 'colon':
            pos = _skip_ws(pos)
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] != ':':
                raise JSONError(f"expected ':', got {s[pos]!r}", pos)
            pos += 1
            stack[-1][2] = 'val'

    # Reject trailing garbage
    pos = _skip_ws(pos)
    if pos != n:
        raise JSONError("trailing characters", pos)

    return value