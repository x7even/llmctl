class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, not {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []
    pending = None
    has_pending = False
    _CONTAINER = object()

    WS = ' \t\n\r'
    DIGITS = '0123456789'
    HEX = '0123456789abcdefABCDEF'

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def parse_string():
        nonlocal pos
        # s[pos] == '"'
        pos += 1
        chars = []
        while True:
            if pos >= n:
                raise JSONError("Unterminated string", n)
            ch = s[pos]
            if ch == '"':
                pos += 1
                return ''.join(chars)
            if ch == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("Unterminated escape sequence", n)
                esc = s[pos]
                if esc == '"':
                    chars.append('"')
                    pos += 1
                elif esc == '\\':
                    chars.append('\\')
                    pos += 1
                elif esc == '/':
                    chars.append('/')
                    pos += 1
                elif esc == 'b':
                    chars.append('\b')
                    pos += 1
                elif esc == 'f':
                    chars.append('\f')
                    pos += 1
                elif esc == 'n':
                    chars.append('\n')
                    pos += 1
                elif esc == 'r':
                    chars.append('\r')
                    pos += 1
                elif esc == 't':
                    chars.append('\t')
                    pos += 1
                elif esc == 'u':
                    pos += 1
                    if pos + 4 > n:
                        raise JSONError("Incomplete \\u escape", n)
                    for i in range(4):
                        if s[pos + i] not in HEX:
                            raise JSONError("Invalid hex digit in \\u escape", pos + i)
                    code = int(s[pos:pos + 4], 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                                and all(c in HEX for c in s[pos + 2:pos + 6])):
                            code2 = int(s[pos + 2:pos + 6], 16)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(combined))
                                pos += 6
                                continue
                        chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    raise JSONError(f"Invalid escape character '\\{esc}'", pos)
            else:
                if ord(ch) < 0x20:
                    raise JSONError("Unescaped control character in string", pos)
                chars.append(ch)
                pos += 1

    def parse_number():
        nonlocal pos
        start = pos
        is_float = False

        if s[pos] == '-':
            pos += 1

        if pos >= n:
            raise JSONError("Unexpected end of number", n)

        ch = s[pos]
        if ch == '0':
            pos += 1
            if pos < n and s[pos] in DIGITS:
                raise JSONError("Leading zero in number", pos)
        elif ch in '123456789':
            pos += 1
            while pos < n and s[pos] in DIGITS:
                pos += 1
        else:
            raise JSONError("Invalid number", pos)

        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of number", n)
            if s[pos] not in DIGITS:
                raise JSONError("Expected digit after '.'", pos)
            while pos < n and s[pos] in DIGITS:
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of number", n)
            if s[pos] not in DIGITS:
                raise JSONError("Expected digit in exponent", pos)
            while pos < n and s[pos] in DIGITS:
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def parse_value():
        nonlocal pos
        ch = s[pos]

        if ch == 't':
            expected = 'true'
            if s[pos:pos + 4] == expected:
                pos += 4
                return True
            for i in range(4):
                if pos + i >= n or s[pos + i] != expected[i]:
                    raise JSONError("Invalid literal", pos + i)
            raise JSONError("Invalid literal", pos)
        elif ch == 'f':
            expected = 'false'
            if s[pos:pos + 5] == expected:
                pos += 5
                return False
            for i in range(5):
                if pos + i >= n or s[pos + i] != expected[i]:
                    raise JSONError("Invalid literal", pos + i)
            raise JSONError("Invalid literal", pos)
        elif ch == 'n':
            expected = 'null'
            if s[pos:pos + 4] == expected:
                pos += 4
                return None
            for i in range(4):
                if pos + i >= n or s[pos + i] != expected[i]:
                    raise JSONError("Invalid literal", pos + i)
            raise JSONError("Invalid literal", pos)
        elif ch == '"':
            return parse_string()
        elif ch == '[':
            if len(stack) >= 500:
                raise JSONError("Maximum nesting depth exceeded", pos)
            stack.append(['array', [], 'first', None])
            pos += 1
            return _CONTAINER
        elif ch == '{':
            if len(stack) >= 500:
                raise JSONError("Maximum nesting depth exceeded", pos)
            stack.append(['object', {}, 'first', None])
            pos += 1
            return _CONTAINER
        elif ch == '-' or ch in DIGITS:
            return parse_number()
        else:
            raise JSONError(f"Unexpected character {ch!r}", pos)

    # Main loop
    while True:
        # Deliver pending value
        if has_pending:
            if not stack:
                skip_ws()
                if pos < n:
                    raise JSONError("Trailing data", pos)
                return pending
            frame = stack[-1]
            if frame[0] == 'array':
                frame[1].append(pending)
                frame[2] = 'comma_or_end'
            else:
                frame[1][frame[3]] = pending
                frame[2] = 'comma_or_end'
            has_pending = False
            pending = None

        skip_ws()

        if pos >= n:
            raise JSONError("Unexpected end of input", n)

        ch = s[pos]

        if not stack:
            val = parse_value()
            if val is _CONTAINER:
                continue
            pending = val
            has_pending = True
        else:
            frame = stack[-1]
            ftype = frame[0]
            state = frame[2]

            if ftype == 'array':
                if state == 'first':
                    if ch == ']':
                        pos += 1
                        pending = frame[1]
                        has_pending = True
                        stack.pop()
                    else:
                        val = parse_value()
                        if val is _CONTAINER:
                            continue
                        pending = val
                        has_pending = True
                elif state == 'value':
                    if ch == ']':
                        raise JSONError("Trailing comma in array", pos)
                    val = parse_value()
                    if val is _CONTAINER:
                        continue
                    pending = val
                    has_pending = True
                elif state == 'comma_or_end':
                    if ch == ',':
                        pos += 1
                        frame[2] = 'value'
                    elif ch == ']':
                        pos += 1
                        pending = frame[1]
                        has_pending = True
                        stack.pop()
                    else:
                        raise JSONError(f"Expected ',' or ']', got {ch!r}", pos)
            else:
                if state == 'first':
                    if ch == '}':
                        pos += 1
                        pending = frame[1]
                        has_pending = True
                        stack.pop()
                    elif ch == '"':
                        key = parse_string()
                        frame[3] = key
                        frame[2] = 'colon'
                    else:
                        raise JSONError(f"Expected string key or '}}', got {ch!r}", pos)
                elif state == 'key':
                    if ch == '"':
                        key = parse_string()
                        frame[3] = key
                        frame[2] = 'colon'
                    elif ch == '}':
                        raise JSONError("Trailing comma in object", pos)
                    else:
                        raise JSONError(f"Expected string key, got {ch!r}", pos)
                elif state == 'colon':
                    if ch == ':':
                        pos += 1
                        frame[2] = 'value'
                    else:
                        raise JSONError(f"Expected ':', got {ch!r}", pos)
                elif state == 'value':
                    val = parse_value()
                    if val is _CONTAINER:
                        continue
                    pending = val
                    has_pending = True
                elif state == 'comma_or_end':
                    if ch == ',':
                        pos += 1
                        frame[2] = 'key'
                    elif ch == '}':
                        pos += 1
                        pending = frame[1]
                        has_pending = True
                        stack.pop()
                    else:
                        raise JSONError(f"Expected ',' or '}}', got {ch!r}", pos)
