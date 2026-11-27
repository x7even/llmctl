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
    stack = []
    result = None
    top_done = False

    WS = ' \t\n\r'
    HEX = '0123456789abcdefABCDEF'

    def _skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def _parse_string():
        nonlocal pos
        # s[pos] == '"'
        pos += 1
        chars = []
        while True:
            if pos >= n:
                raise JSONError("unterminated string", pos)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unterminated escape", pos)
                ec = s[pos]
                if ec == '"':
                    chars.append('"'); pos += 1
                elif ec == '\\':
                    chars.append('\\'); pos += 1
                elif ec == '/':
                    chars.append('/'); pos += 1
                elif ec == 'b':
                    chars.append('\b'); pos += 1
                elif ec == 'f':
                    chars.append('\f'); pos += 1
                elif ec == 'n':
                    chars.append('\n'); pos += 1
                elif ec == 'r':
                    chars.append('\r'); pos += 1
                elif ec == 't':
                    chars.append('\t'); pos += 1
                elif ec == 'u':
                    pos += 1
                    if pos + 4 > n:
                        raise JSONError("truncated \\u escape", pos)
                    h = s[pos:pos + 4]
                    for i in range(4):
                        if h[i] not in HEX:
                            raise JSONError("invalid hex digit in \\u escape", pos + i)
                    code = int(h, 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            h2 = s[pos + 2:pos + 6]
                            if all(hc in HEX for hc in h2):
                                code2 = int(h2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    chars.append(chr(combined))
                                    pos += 6
                                    continue
                    chars.append(chr(code))
                else:
                    raise JSONError(f"invalid escape character", pos)
            elif ord(c) < 0x20:
                raise JSONError("raw control character in string", pos)
            else:
                chars.append(c)
                pos += 1

    def _parse_number():
        nonlocal pos
        start = pos
        is_float = False

        if pos < n and s[pos] == '-':
            pos += 1

        if pos >= n:
            raise JSONError("unexpected end of input", pos)

        c = s[pos]
        if c == '0':
            pos += 1
            if pos < n and '0' <= s[pos] <= '9':
                raise JSONError("leading zero not allowed", pos)
        elif '1' <= c <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            raise JSONError("invalid number", pos)

        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit after '.'", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        else:
            return int(text)

    def _check_literal(literal):
        nonlocal pos
        llen = len(literal)
        for i in range(llen):
            if pos + i >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos + i] != literal[i]:
                raise JSONError("invalid literal", pos + i)
        pos += llen

    def _assign(val):
        nonlocal result, top_done
        if not stack:
            result = val
            top_done = True
        else:
            frame = stack[-1]
            if frame[0] == 'a':
                frame[1].append(val)
                frame[2] = 'c'
            else:
                frame[1][frame[3]] = val
                frame[2] = 'c'

    def _close():
        nonlocal pos
        frame = stack.pop()
        pos += 1  # skip ] or }
        _assign(frame[1])

    while True:
        _skip_ws()

        if pos >= n:
            if top_done:
                return result
            raise JSONError("unexpected end of input", pos)

        c = s[pos]

        if top_done:
            raise JSONError("trailing garbage", pos)

        if not stack:
            # --- Top-level value ---
            if c == '"':
                result = _parse_string()
                top_done = True
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("nesting too deep", pos)
                stack.append(['a', [], 'f'])
                pos += 1
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("nesting too deep", pos)
                stack.append(['o', {}, 'f', None])
                pos += 1
            elif c == 't':
                _check_literal('true')
                result = True
                top_done = True
            elif c == 'f':
                _check_literal('false')
                result = False
                top_done = True
            elif c == 'n':
                _check_literal('null')
                result = None
                top_done = True
            elif c == '-' or '0' <= c <= '9':
                result = _parse_number()
                top_done = True
            else:
                raise JSONError(f"unexpected character {c!r}", pos)
            continue

        # --- Inside a container ---
        frame = stack[-1]

        if frame[0] == 'a':
            # Array
            if frame[2] == 'f':
                # Expect first element or ']'
                if c == ']':
                    _close()
                elif c == '"':
                    _assign(_parse_string())
                elif c == '[':
                    if len(stack) >= 500:
                        raise JSONError("nesting too deep", pos)
                    stack.append(['a', [], 'f'])
                    pos += 1
                elif c == '{':
                    if len(stack) >= 500:
                        raise JSONError("nesting too deep", pos)
                    stack.append(['o', {}, 'f', None])
                    pos += 1
                elif c == 't':
                    _check_literal('true')
                    _assign(True)
                elif c == 'f':
                    _check_literal('false')
                    _assign(False)
                elif c == 'n':
                    _check_literal('null')
                    _assign(None)
                elif c == '-' or '0' <= c <= '9':
                    _assign(_parse_number())
                else:
                    raise JSONError(f"unexpected character {c!r}", pos)
            elif frame[2] == 'c':
                # Expect ',' or ']'
                if c == ']':
                    _close()
                elif c == ',':
                    frame[2] = 'f'
                    pos += 1
                else:
                    raise JSONError(f"expected ',' or ']'", pos)

        else:
            # Object
            if frame[2] == 'f':
                # Expect first key or '}'
                if c == '}':
                    _close()
                elif c == '"':
                    key = _parse_string()
                    frame[3] = key
                    frame[2] = 'col'
                else:
                    raise JSONError(f"expected string key", pos)
            elif frame[2] == 'col':
                # Expect ':'
                if c == ':':
                    frame[2] = 'v'
                    pos += 1
                else:
                    raise JSONError(f"expected ':'", pos)
            elif frame[2] == 'v':
                # Expect value
                if c == '"':
                    _assign(_parse_string())
                elif c == '[':
                    if len(stack) >= 500:
                        raise JSONError("nesting too deep", pos)
                    stack.append(['a', [], 'f'])
                    pos += 1
                elif c == '{':
                    if len(stack) >= 500:
                        raise JSONError("nesting too deep", pos)
                    stack.append(['o', {}, 'f', None])
                    pos += 1
                elif c == 't':
                    _check_literal('true')
                    _assign(True)
                elif c == 'f':
                    _check_literal('false')
                    _assign(False)
                elif c == 'n':
                    _check_literal('null')
                    _assign(None)
                elif c == '-' or '0' <= c <= '9':
                    _assign(_parse_number())
                else:
                    raise JSONError(f"unexpected character {c!r}", pos)
            elif frame[2] == 'c':
                # Expect ',' or '}'
                if c == '}':
                    _close()
                elif c == ',':
                    frame[2] = 'f'
                    pos += 1
                else:
                    raise JSONError(f"expected ',' or '}'", pos)