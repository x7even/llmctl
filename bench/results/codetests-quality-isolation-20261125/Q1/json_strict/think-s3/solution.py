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

    # Stack frames: [kind, container, state, pending_key]
    # kind: 0=array, 1=object
    # state:
    #   array:  0=expect_value_or_end, 1=expect_comma_or_end
    #   object: 0=expect_key_or_end, 1=expect_colon, 2=expect_value, 3=expect_comma_or_end
    stack = []

    top_level_done = False
    result = None

    def skip_ws():
        nonlocal pos
        while pos < n:
            c = s[pos]
            if c == ' ' or c == '\t' or c == '\n' or c == '\r':
                pos += 1
            else:
                break

    def deliver_value(value):
        nonlocal top_level_done, result
        if not stack:
            top_level_done = True
            result = value
        else:
            frame = stack[-1]
            if frame[0] == 0:  # array
                frame[1].append(value)
                frame[2] = 1
            else:  # object
                frame[1][frame[3]] = value
                frame[2] = 3

    def _hex_val(c):
        if '0' <= c <= '9':
            return ord(c) - 48
        elif 'a' <= c <= 'f':
            return ord(c) - 87
        else:
            return ord(c) - 55

    def _is_hex(c):
        return ('0' <= c <= '9') or ('a' <= c <= 'f') or ('A' <= c <= 'F')

    def parse_string(start):
        nonlocal pos
        pos = start + 1
        chars = []
        while True:
            if pos >= n:
                raise JSONError("unexpected end of input in string", n)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of input in string escape", n)
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
                    if pos + 4 > n:
                        raise JSONError("unexpected end of input in \\u escape", n)
                    h0 = s[pos]; h1 = s[pos + 1]; h2 = s[pos + 2]; h3 = s[pos + 3]
                    if not _is_hex(h0):
                        raise JSONError("invalid hex digit in \\u escape", pos)
                    if not _is_hex(h1):
                        raise JSONError("invalid hex digit in \\u escape", pos + 1)
                    if not _is_hex(h2):
                        raise JSONError("invalid hex digit in \\u escape", pos + 2)
                    if not _is_hex(h3):
                        raise JSONError("invalid hex digit in \\u escape", pos + 3)
                    code = (_hex_val(h0) << 12) | (_hex_val(h1) << 8) | (_hex_val(h2) << 4) | _hex_val(h3)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            h0b = s[pos + 2]; h1b = s[pos + 3]
                            h2b = s[pos + 4]; h3b = s[pos + 5]
                            if _is_hex(h0b) and _is_hex(h1b) and _is_hex(h2b) and _is_hex(h3b):
                                code2 = (_hex_val(h0b) << 12) | (_hex_val(h1b) << 8) | (_hex_val(h2b) << 4) | _hex_val(h3b)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    chars.append(chr(combined))
                                    pos += 6
                                    continue
                    chars.append(chr(code))
                else:
                    raise JSONError(f"invalid escape character", pos)
            elif ord(c) < 0x20:
                raise JSONError("unescaped control character in string", pos)
            else:
                chars.append(c)
                pos += 1

    def parse_number(start):
        nonlocal pos
        pos = start
        is_float = False

        if pos < n and s[pos] == '-':
            pos += 1

        if pos >= n:
            raise JSONError("unexpected end of input in number", n)
        c = s[pos]
        if c == '0':
            pos += 1
        elif '1' <= c <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            raise JSONError("expected digit in number", pos)

        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in number", n)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit in number fraction", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and (s[pos] == 'e' or s[pos] == 'E'):
            is_float = True
            pos += 1
            if pos < n and (s[pos] == '+' or s[pos] == '-'):
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in number", n)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit in number exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        else:
            return int(text)

    def parse_literal(start, expected):
        nonlocal pos
        ln = len(expected)
        for i in range(ln):
            if start + i >= n:
                raise JSONError("unexpected end of input in literal", n)
            if s[start + i] != expected[i]:
                raise JSONError("invalid literal", start + i)
        pos = start + ln

    def try_parse_value():
        nonlocal pos
        c = s[pos]
        if c == '[':
            if len(stack) >= 500:
                raise JSONError("nesting too deep", pos)
            pos += 1
            stack.append([0, [], 0, None])
        elif c == '{':
            if len(stack) >= 500:
                raise JSONError("nesting too deep", pos)
            pos += 1
            stack.append([1, {}, 0, None])
        elif c == '"':
            val = parse_string(pos)
            deliver_value(val)
        elif c == 't':
            parse_literal(pos, 'true')
            deliver_value(True)
        elif c == 'f':
            parse_literal(pos, 'false')
            deliver_value(False)
        elif c == 'n':
            parse_literal(pos, 'null')
            deliver_value(None)
        elif c == '-' or ('0' <= c <= '9'):
            val = parse_number(pos)
            deliver_value(val)
        else:
            raise JSONError(f"unexpected character {c!r}", pos)

    # Main loop
    while True:
        skip_ws()

        if pos >= n:
            if not stack and top_level_done:
                return result
            else:
                raise JSONError("unexpected end of input", n)

        c = s[pos]

        if not stack:
            if top_level_done:
                raise JSONError("trailing garbage", pos)
            try_parse_value()
        else:
            frame = stack[-1]
            kind = frame[0]
            state = frame[2]

            if kind == 0:  # array
                if state == 0:  # expect value or ]
                    if c == ']':
                        pos += 1
                        arr = frame[1]
                        stack.pop()
                        deliver_value(arr)
                    else:
                        try_parse_value()
                elif state == 1:  # expect , or ]
                    if c == ',':
                        pos += 1
                        frame[2] = 0
                    elif c == ']':
                        pos += 1
                        arr = frame[1]
                        stack.pop()
                        deliver_value(arr)
                    else:
                        raise JSONError("expected ',' or ']'", pos)
            else:  # object
                if state == 0:  # expect " or }
                    if c == '}':
                        pos += 1
                        obj = frame[1]
                        stack.pop()
                        deliver_value(obj)
                    elif c == '"':
                        key = parse_string(pos)
                        frame[3] = key
                        frame[2] = 1
                    else:
                        raise JSONError("expected string key or '}'", pos)
                elif state == 1:  # expect :
                    if c == ':':
                        pos += 1
                        frame[2] = 2
                    else:
                        raise JSONError("expected ':'", pos)
                elif state == 2:  # expect value
                    try_parse_value()
                elif state == 3:  # expect , or }
                    if c == ',':
                        pos += 1
                        frame[2] = 0
                    elif c == '}':
                        pos += 1
                        obj = frame[1]
                        stack.pop()
                        deliver_value(obj)
                    else:
                        raise JSONError("expected ',' or '}'", pos)
