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
    stack = []  # [type, result, state, pending_key]
    # type: 0=array, 1=object
    # state: array: 0=expect_value_or_end, 1=expect_comma_or_end
    #        object: 0=expect_key_or_end, 1=expect_colon, 2=expect_value, 3=expect_comma_or_end
    # pending_key: for object, the key awaiting value; None for array

    WS = ' \t\n\r'
    HEX = frozenset('0123456789abcdefABCDEF')
    MAX_DEPTH = 500

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def err(msg, p):
        raise JSONError(msg, p)

    def parse_string():
        nonlocal pos
        chars = []
        while True:
            if pos >= n:
                err("unexpected end of input in string", n)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    err("unexpected end of input in escape", n)
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
                        err("unexpected end of input in \\u escape", n)
                    for i in range(4):
                        if s[pos + i] not in HEX:
                            err("invalid hex digit in \\u escape", pos + i)
                    code = int(s[pos:pos + 4], 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                                and s[pos + 2] in HEX and s[pos + 3] in HEX
                                and s[pos + 4] in HEX and s[pos + 5] in HEX):
                            code2 = int(s[pos + 2:pos + 6], 16)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(combined))
                                pos += 6
                                continue
                    chars.append(chr(code))
                else:
                    err("invalid escape character", pos)
            elif ord(c) < 0x20:
                err("control character in string", pos)
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
            err("unexpected end of input in number", n)

        c = s[pos]
        if c == '0':
            pos += 1
            if pos < n and '0' <= s[pos] <= '9':
                err("leading zero not allowed", pos)
        elif '1' <= c <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            err("expected digit in number", pos)

        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                err("unexpected end of input in number", n)
            if not ('0' <= s[pos] <= '9'):
                err("expected digit after decimal point", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                err("unexpected end of input in number", n)
            if not ('0' <= s[pos] <= '9'):
                err("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        else:
            return int(text)

    def parse_literal(expected):
        nonlocal pos
        ln = len(expected)
        for i in range(ln):
            if pos + i >= n or s[pos + i] != expected[i]:
                err(f"expected '{expected}'", pos + i)
        pos += ln

    def finish_top(value):
        nonlocal pos
        skip_ws()
        if pos < n:
            err("trailing garbage", pos)
        return value

    def commit_scalar(value):
        """Commit a scalar value to the current top frame. Returns final result if stack becomes empty."""
        frame = stack[-1]
        if frame[0] == 0:
            frame[1].append(value)
            frame[2] = 1
        else:
            frame[1][frame[3]] = value
            frame[2] = 3

    def pop_and_commit():
        """Pop top frame, commit its result to parent. Returns final result if stack becomes empty, else None."""
        nonlocal pos
        value = stack.pop()[1]
        if not stack:
            return finish_top(value)
        parent = stack[-1]
        if parent[0] == 0:
            parent[1].append(value)
            parent[2] = 1
        else:
            parent[1][parent[3]] = value
            parent[2] = 3
        return None

    def try_push(ftype):
        nonlocal pos
        if len(stack) + 1 > MAX_DEPTH:
            err("maximum nesting depth exceeded", pos)
        pos += 1
        if ftype == 0:
            stack.append([0, [], 0, None])
        else:
            stack.append([1, {}, 0, None])

    # Main loop
    while True:
        skip_ws()

        if pos >= n:
            err("unexpected end of input", n)

        c = s[pos]

        if not stack:
            # Top level: expect a value
            if c == '{':
                try_push(1)
            elif c == '[':
                try_push(0)
            elif c == '"':
                pos += 1
                value = parse_string()
                return finish_top(value)
            elif c == 't':
                parse_literal('true')
                return finish_top(True)
            elif c == 'f':
                parse_literal('false')
                return finish_top(False)
            elif c == 'n':
                parse_literal('null')
                return finish_top(None)
            elif c == '-' or '0' <= c <= '9':
                value = parse_number()
                return finish_top(value)
            else:
                err(f"unexpected character {c!r}", pos)
        else:
            frame = stack[-1]
            ftype = frame[0]
            state = frame[2]

            if ftype == 0:  # array
                if state == 0:  # expect value or ]
                    if c == ']':
                        pos += 1
                        r = pop_and_commit()
                        if r is not None:
                            return r
                    elif c == '{':
                        try_push(1)
                    elif c == '[':
                        try_push(0)
                    elif c == '"':
                        pos += 1
                        value = parse_string()
                        commit_scalar(value)
                    elif c == 't':
                        parse_literal('true')
                        commit_scalar(True)
                    elif c == 'f':
                        parse_literal('false')
                        commit_scalar(False)
                    elif c == 'n':
                        parse_literal('null')
                        commit_scalar(None)
                    elif c == '-' or '0' <= c <= '9':
                        value = parse_number()
                        commit_scalar(value)
                    else:
                        err(f"unexpected character {c!r}", pos)
                elif state == 1:  # expect comma or ]
                    if c == ',':
                        pos += 1
                        frame[2] = 0
                    elif c == ']':
                        pos += 1
                        r = pop_and_commit()
                        if r is not None:
                            return r
                    else:
                        err(f"unexpected character {c!r}", pos)

            elif ftype == 1:  # object
                if state == 0:  # expect key or }
                    if c == '}':
                        pos += 1
                        r = pop_and_commit()
                        if r is not None:
                            return r
                    elif c == '"':
                        pos += 1
                        key = parse_string()
                        frame[3] = key
                        frame[2] = 1
                    else:
                        err(f"unexpected character {c!r}", pos)
                elif state == 1:  # expect colon
                    if c == ':':
                        pos += 1
                        frame[2] = 2
                    else:
                        err(f"unexpected character {c!r}", pos)
                elif state == 2:  # expect value
                    if c == '{':
                        try_push(1)
                    elif c == '[':
                        try_push(0)
                    elif c == '"':
                        pos += 1
                        value = parse_string()
                        commit_scalar(value)
                    elif c == 't':
                        parse_literal('true')
                        commit_scalar(True)
                    elif c == 'f':
                        parse_literal('false')
                        commit_scalar(False)
                    elif c == 'n':
                        parse_literal('null')
                        commit_scalar(None)
                    elif c == '-' or '0' <= c <= '9':
                        value = parse_number()
                        commit_scalar(value)
                    else:
                        err(f"unexpected character {c!r}", pos)
                elif state == 3:  # expect comma or }
                    if c == ',':
                        pos += 1
                        frame[2] = 0
                    elif c == '}':
                        pos += 1
                        r = pop_and_commit()
                        if r is not None:
                            return r
                    else:
                        err(f"unexpected character {c!r}", pos)
