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
    stack = []  # each frame: [container, kind, key]; kind 0=array, 1=object

    state = 'value'
    result = None
    WS = ' \t\n\r'

    while True:
        if state == 'value':
            while pos < n and s[pos] in WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]
            if c == '"':
                result, pos = _parse_string(s, pos, n)
                state = 'after_value'
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append([[], 0, None])
                state = 'array_first'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append([{}, 1, None])
                state = 'obj_first'
            elif c == 't':
                pos = _parse_literal(s, pos, n, 'true')
                result = True
                state = 'after_value'
            elif c == 'f':
                pos = _parse_literal(s, pos, n, 'false')
                result = False
                state = 'after_value'
            elif c == 'n':
                pos = _parse_literal(s, pos, n, 'null')
                result = None
                state = 'after_value'
            elif c == '-' or ('0' <= c <= '9'):
                result, pos = _parse_number(s, pos, n)
                state = 'after_value'
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'after_value':
            if not stack:
                while pos < n and s[pos] in WS:
                    pos += 1
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return result
            else:
                container, kind, key = stack[-1]
                if kind == 0:
                    container.append(result)
                    state = 'array_comma'
                else:
                    container[key] = result
                    state = 'obj_comma'

        elif state == 'array_first':
            while pos < n and s[pos] in WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]
            if c == ']':
                pos += 1
                container, _, _ = stack.pop()
                result = container
                state = 'after_value'
            else:
                state = 'value'

        elif state == 'array_comma':
            while pos < n and s[pos] in WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]
            if c == ',':
                pos += 1
                state = 'value'
            elif c == ']':
                pos += 1
                container, _, _ = stack.pop()
                result = container
                state = 'after_value'
            else:
                raise JSONError(f"expected ',' or ']', got {c!r}", pos)

        elif state == 'obj_first':
            while pos < n and s[pos] in WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]
            if c == '}':
                pos += 1
                container, _, _ = stack.pop()
                result = container
                state = 'after_value'
            elif c == '"':
                key, pos = _parse_string(s, pos, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError(f"expected '\"' or '}}', got {c!r}", pos)

        elif state == 'obj_key':
            while pos < n and s[pos] in WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]
            if c != '"':
                raise JSONError(f"expected '\"', got {c!r}", pos)
            key, pos = _parse_string(s, pos, n)
            stack[-1][2] = key
            state = 'obj_colon'

        elif state == 'obj_colon':
            while pos < n and s[pos] in WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]
            if c == ':':
                pos += 1
                state = 'value'
            else:
                raise JSONError(f"expected ':', got {c!r}", pos)

        elif state == 'obj_comma':
            while pos < n and s[pos] in WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]
            if c == ',':
                pos += 1
                state = 'obj_key'
            elif c == '}':
                pos += 1
                container, _, _ = stack.pop()
                result = container
                state = 'after_value'
            else:
                raise JSONError(f"expected ',' or '}}', got {c!r}", pos)

        else:
            raise JSONError("internal parser error", pos)


def _parse_literal(s, pos, n, expected):
    for i, c in enumerate(expected):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != c:
            raise JSONError(f"invalid literal at position {pos + i}", pos + i)
    return pos + len(expected)


def _parse_number(s, pos, n):
    start = pos

    # Optional minus
    if s[pos] == '-':
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit after '-'", pos)

    # Integer part
    if s[pos] == '0':
        pos += 1
        if pos < n and '0' <= s[pos] <= '9':
            raise JSONError("leading zero not allowed", pos)
    elif '0' <= s[pos] <= '9':
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    else:
        raise JSONError("expected digit", pos)

    has_fraction = False
    has_exponent = False

    # Optional fraction
    if pos < n and s[pos] == '.':
        if pos + 1 < n and '0' <= s[pos + 1] <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
            has_fraction = True
        elif pos + 1 >= n:
            raise JSONError("unexpected end of input", n)
        else:
            raise JSONError("expected digit after '.'", pos + 1)

    # Optional exponent
    if pos < n and s[pos] in 'eE':
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit in exponent", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
        has_exponent = True

    text = s[start:pos]
    if has_fraction or has_exponent:
        value = float(text)
    else:
        value = int(text)

    return value, pos


def _parse_string(s, pos, n):
    # s[pos] == '"'
    pos += 1
    parts = []

    while True:
        if pos >= n:
            raise JSONError("unexpected end of input in string", n)

        c = s[pos]

        if c == '"':
            pos += 1
            return ''.join(parts), pos

        if c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in string escape", n)
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
                if pos + 4 > n:
                    raise JSONError("unexpected end of input in \\u escape", n)
                code = _hex4(s, pos)
                pos += 4

                # Surrogate pair handling
                if 0xD800 <= code <= 0xDBFF:
                    if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                            and _is_hex4(s, pos + 2)):
                        code2 = _hex4(s, pos + 2)
                        if 0xDC00 <= code2 <= 0xDFFF:
                            combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            parts.append(chr(combined))
                            pos += 6
                            continue
                    parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError(f"invalid escape character {ec!r}", pos)
        else:
            if ord(c) < 0x20:
                raise JSONError("raw control character in string", pos)
            parts.append(c)
            pos += 1


def _hex4(s, pos):
    """Parse exactly 4 ASCII hex digits at s[pos:pos+4]. Returns the integer value."""
    v = 0
    for i in range(4):
        c = s[pos + i]
        if '0' <= c <= '9':
            d = ord(c) - 48
        elif 'a' <= c <= 'f':
            d = ord(c) - 87
        elif 'A' <= c <= 'F':
            d = ord(c) - 55
        else:
            raise JSONError(f"invalid hex digit {c!r} in \\u escape", pos + i)
        v = (v << 4) | d
    return v


def _is_hex4(s, pos):
    """Check if s[pos:pos+4] are all valid ASCII hex digits."""
    for i in range(4):
        c = s[pos + i]
        if not ('0' <= c <= '9' or 'a' <= c <= 'f' or 'A' <= c <= 'F'):
            return False
    return True