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
    depth = 0

    # Stack frames: [type, container, state, key]
    #   type:   'A' (array) or 'O' (object)
    #   state:  'VAL' | 'SEP' | 'KEY' | 'COLON'
    #   key:    current key for object frames (None for arrays)
    stack = []

    top_done = False
    result = None

    WS = ' \t\n\r'

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def err(msg, p):
        raise JSONError(msg, p)

    def _hex4(p):
        """Return (value, ok) for 4 hex digits at s[p:p+4]."""
        v = 0
        for i in range(4):
            c = s[p + i]
            if '0' <= c <= '9':
                v = v * 16 + (ord(c) - 48)
            elif 'a' <= c <= 'f':
                v = v * 16 + (ord(c) - 87)
            elif 'A' <= c <= 'F':
                v = v * 16 + (ord(c) - 55)
            else:
                return (0, False)
        return (v, True)

    def parse_string():
        nonlocal pos
        pos += 1  # consume opening "
        chars = []
        while True:
            if pos >= n:
                err("unterminated string", n)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    err("unterminated escape sequence", n)
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
                        err("incomplete \\u escape", n)
                    code, ok = _hex4(pos)
                    if not ok:
                        # find first bad char
                        for i in range(4):
                            hc = s[pos + i]
                            if not ('0' <= hc <= '9' or 'a' <= hc <= 'f' or 'A' <= hc <= 'F'):
                                err("invalid hex digit in \\u escape", pos + i)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        # high surrogate – try to combine with next \uXXXX low surrogate
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            code2, ok2 = _hex4(pos + 2)
                            if ok2 and 0xDC00 <= code2 <= 0xDFFF:
                                cp = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(cp))
                                pos += 6
                                continue
                        chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    err("invalid escape character", pos)
            elif ord(c) < 0x20:
                err("unescaped control character in string", pos)
            else:
                chars.append(c)
                pos += 1

    def parse_number():
        nonlocal pos
        start = pos
        is_float = False

        if s[pos] == '-':
            pos += 1

        if pos >= n:
            err("incomplete number", n)

        c = s[pos]
        if c == '0':
            pos += 1
            if pos < n and '0' <= s[pos] <= '9':
                err("leading zero in number", pos)
        elif '1' <= c <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            err("invalid number", pos)

        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                err("incomplete number", n)
            if not ('0' <= s[pos] <= '9'):
                err("expected digit after decimal point", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in ('e', 'E'):
            is_float = True
            pos += 1
            if pos < n and s[pos] in ('+', '-'):
                pos += 1
            if pos >= n:
                err("incomplete number", n)
            if not ('0' <= s[pos] <= '9'):
                err("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def parse_literal(expected, value):
        nonlocal pos
        for i in range(len(expected)):
            if pos + i >= n:
                err("unexpected end of input", n)
            if s[pos + i] != expected[i]:
                err("invalid literal", pos + i)
        pos += len(expected)
        return value

    def place_value(val):
        nonlocal result, top_done
        if not stack:
            result = val
            top_done = True
        else:
            parent = stack[-1]
            if parent[0] == 'A':
                parent[1].append(val)
                parent[2] = 'SEP'
            else:
                parent[1][parent[3]] = val
                parent[2] = 'SEP'

    def open_container(c):
        nonlocal pos, depth
        depth += 1
        if depth > 500:
            err("maximum nesting depth exceeded", pos)
        pos += 1
        if c == '{':
            stack.append(['O', {}, 'KEY', None])
        else:
            stack.append(['A', [], 'VAL', None])

    def parse_scalar_or_open():
        """Parse a value that is either a scalar or opens a new container.
        Returns the value if scalar, or None if a container was opened."""
        nonlocal pos
        c = s[pos]
        if c == '{':
            open_container('{')
            return None
        elif c == '[':
            open_container('[')
            return None
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
            err(f"unexpected character {c!r}", pos)

    while True:
        skip_ws()

        if pos >= n:
            if top_done:
                return result
            err("unexpected end of input", n)

        if top_done:
            err("trailing garbage", pos)

        c = s[pos]

        if not stack:
            # Top level: expect a value
            val = parse_scalar_or_open()
            if val is not None:
                place_value(val)
            # if val is None, a container was opened; loop continues
        else:
            frame = stack[-1]
            ftype = frame[0]
            fstate = frame[2]

            if ftype == 'A':
                if fstate == 'VAL':
                    if c == ']':
                        container = frame[1]
                        pos += 1
                        stack.pop()
                        depth -= 1
                        place_value(container)
                    else:
                        val = parse_scalar_or_open()
                        if val is not None:
                            frame[1].append(val)
                            frame[2] = 'SEP'
                elif fstate == 'SEP':
                    if c == ',':
                        pos += 1
                        frame[2] = 'VAL'
                    elif c == ']':
                        container = frame[1]
                        pos += 1
                        stack.pop()
                        depth -= 1
                        place_value(container)
                    else:
                        err(f"expected ',' or ']', got {c!r}", pos)

            elif ftype == 'O':
                if fstate == 'KEY':
                    if c == '}':
                        container = frame[1]
                        pos += 1
                        stack.pop()
                        depth -= 1
                        place_value(container)
                    elif c == '"':
                        key = parse_string()
                        frame[2] = 'COLON'
                        frame[3] = key
                    else:
                        err(f"expected string key or '}}', got {c!r}", pos)
                elif fstate == 'COLON':
                    if c == ':':
                        pos += 1
                        frame[2] = 'VAL'
                    else:
                        err(f"expected ':', got {c!r}", pos)
                elif fstate == 'VAL':
                    val = parse_scalar_or_open()
                    if val is not None:
                        frame[1][frame[3]] = val
                        frame[2] = 'SEP'
                elif fstate == 'SEP':
                    if c == ',':
                        pos += 1
                        frame[2] = 'KEY'
                    elif c == '}':
                        container = frame[1]
                        pos += 1
                        stack.pop()
                        depth -= 1
                        place_value(container)
                    else:
                        err(f"expected ',' or '}}', got {c!r}", pos)
