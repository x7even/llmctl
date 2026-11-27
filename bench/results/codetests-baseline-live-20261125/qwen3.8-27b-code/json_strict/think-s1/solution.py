class JSONError(ValueError):
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []  # each frame: [container, state, key]
    result = None
    top_done = False
    _PUSH = object()

    def err(p, msg):
        raise JSONError(msg, p)

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1

    def use_value(val):
        nonlocal result, top_done
        if not stack:
            result = val
            top_done = True
        else:
            frame = stack[-1]
            if isinstance(frame[0], list):
                frame[0].append(val)
                frame[1] = 'comma'
            else:
                frame[0][frame[2]] = val
                frame[1] = 'comma'

    def _hex4(h, base):
        v = 0
        for i in range(4):
            ch = h[i]
            if '0' <= ch <= '9':
                v = v * 16 + (ord(ch) - 48)
            elif 'a' <= ch <= 'f':
                v = v * 16 + (ord(ch) - 87)
            elif 'A' <= ch <= 'F':
                v = v * 16 + (ord(ch) - 55)
            else:
                err(base + i, "invalid hex digit in \\u escape")
        return v

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening "
        chars = []
        while True:
            if pos >= n:
                err(n, "unterminated string")
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    err(n, "unterminated string in escape")
                esc = s[pos]
                if esc == '"':
                    chars.append('"'); pos += 1
                elif esc == '\\':
                    chars.append('\\'); pos += 1
                elif esc == '/':
                    chars.append('/'); pos += 1
                elif esc == 'b':
                    chars.append('\b'); pos += 1
                elif esc == 'f':
                    chars.append('\f'); pos += 1
                elif esc == 'n':
                    chars.append('\n'); pos += 1
                elif esc == 'r':
                    chars.append('\r'); pos += 1
                elif esc == 't':
                    chars.append('\t'); pos += 1
                elif esc == 'u':
                    pos += 1
                    if pos + 4 > n:
                        err(n, "truncated \\u escape")
                    v = _hex4(s[pos:pos + 4], pos)
                    pos += 4
                    if 0xD800 <= v <= 0xDBFF:
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            v2 = _hex4(s[pos + 2:pos + 6], pos + 2)
                            if 0xDC00 <= v2 <= 0xDFFF:
                                cp = 0x10000 + ((v - 0xD800) << 10) + (v2 - 0xDC00)
                                chars.append(chr(cp))
                                pos += 6
                                continue
                        chars.append(chr(v))
                    else:
                        chars.append(chr(v))
                else:
                    err(pos, f"invalid escape character")
            else:
                if ord(c) < 0x20:
                    err(pos, "control character in string")
                chars.append(c)
                pos += 1

    def parse_number():
        nonlocal pos
        start = pos
        if s[pos] == '-':
            pos += 1
        if pos >= n:
            err(n, "truncated number")
        c = s[pos]
        if c == '0':
            pos += 1
            if pos < n and '0' <= s[pos] <= '9':
                err(pos, "leading zero in number")
        elif '1' <= c <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            err(pos, "expected digit in number")

        is_float = False
        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                err(n, "truncated number, expected digit after '.'")
            if not ('0' <= s[pos] <= '9'):
                err(pos, "expected digit after '.'")
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                err(n, "truncated number, expected digit in exponent")
            if not ('0' <= s[pos] <= '9'):
                err(pos, "expected digit in exponent")
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def parse_literal(expected):
        nonlocal pos
        ln = len(expected)
        for i in range(ln):
            if pos + i >= n:
                err(n, "truncated literal")
            if s[pos + i] != expected[i]:
                err(pos + i, "invalid literal")
        pos += ln

    def parse_value():
        nonlocal pos
        if pos >= n:
            err(n, "unexpected end of input")
        c = s[pos]
        if c == '[':
            if len(stack) >= 500:
                err(pos, "maximum nesting depth exceeded")
            pos += 1
            stack.append([[], 'first', None])
            return _PUSH
        elif c == '{':
            if len(stack) >= 500:
                err(pos, "maximum nesting depth exceeded")
            pos += 1
            stack.append([{}, 'first', None])
            return _PUSH
        elif c == '"':
            return parse_string()
        elif c == '-' or '0' <= c <= '9':
            return parse_number()
        elif c == 't':
            parse_literal('true')
            return True
        elif c == 'f':
            parse_literal('false')
            return False
        elif c == 'n':
            parse_literal('null')
            return None
        else:
            err(pos, f"unexpected character {c!r}")

    # Main loop
    while True:
        skip_ws()

        if not stack:
            if top_done:
                if pos < n:
                    err(pos, "trailing garbage after top-level value")
                break
            else:
                val = parse_value()
                if val is not _PUSH:
                    use_value(val)
        else:
            frame = stack[-1]
            container = frame[0]
            state = frame[1]

            if isinstance(container, list):
                if state == 'first':
                    if pos >= n:
                        err(n, "unexpected end of input")
                    if s[pos] == ']':
                        pos += 1
                        val = stack.pop()[0]
                        use_value(val)
                    else:
                        val = parse_value()
                        if val is not _PUSH:
                            use_value(val)
                elif state == 'elem':
                    val = parse_value()
                    if val is not _PUSH:
                        use_value(val)
                elif state == 'comma':
                    if pos >= n:
                        err(n, "unexpected end of input")
                    c = s[pos]
                    if c == ',':
                        pos += 1
                        frame[1] = 'elem'
                    elif c == ']':
                        pos += 1
                        val = stack.pop()[0]
                        use_value(val)
                    else:
                        err(pos, "expected ',' or ']'")
            else:
                if state == 'first':
                    if pos >= n:
                        err(n, "unexpected end of input")
                    c = s[pos]
                    if c == '}':
                        pos += 1
                        val = stack.pop()[0]
                        use_value(val)
                    elif c == '"':
                        key = parse_string()
                        frame[1] = 'colon'
                        frame[2] = key
                    else:
                        err(pos, "expected string key or '}'")
                elif state == 'key':
                    if pos >= n:
                        err(n, "unexpected end of input")
                    c = s[pos]
                    if c == '"':
                        key = parse_string()
                        frame[1] = 'colon'
                        frame[2] = key
                    else:
                        err(pos, "expected string key")
                elif state == 'colon':
                    if pos >= n:
                        err(n, "unexpected end of input")
                    if s[pos] == ':':
                        pos += 1
                        frame[1] = 'value'
                    else:
                        err(pos, "expected ':'")
                elif state == 'value':
                    val = parse_value()
                    if val is not _PUSH:
                        use_value(val)
                elif state == 'comma':
                    if pos >= n:
                        err(n, "unexpected end of input")
                    c = s[pos]
                    if c == ',':
                        pos += 1
                        frame[1] = 'key'
                    elif c == '}':
                        pos += 1
                        val = stack.pop()[0]
                        use_value(val)
                    else:
                        err(pos, "expected ',' or '}'")

    return result