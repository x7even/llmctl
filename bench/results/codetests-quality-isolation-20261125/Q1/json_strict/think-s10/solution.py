class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def _parse_string(s, pos, n):
    """Parse a JSON string starting at s[pos] (which must be '"').
    Returns (string_value, new_pos)."""
    pos += 1  # skip opening quote
    parts = []
    while True:
        if pos >= n:
            raise JSONError("unexpected end of input in string", pos)
        c = s[pos]
        if c == '"':
            pos += 1
            return ''.join(parts), pos
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in escape", pos)
            ec = s[pos]
            if ec == '"':
                parts.append('"'); pos += 1
            elif ec == '\\':
                parts.append('\\'); pos += 1
            elif ec == '/':
                parts.append('/'); pos += 1
            elif ec == 'b':
                parts.append('\b'); pos += 1
            elif ec == 'f':
                parts.append('\f'); pos += 1
            elif ec == 'n':
                parts.append('\n'); pos += 1
            elif ec == 'r':
                parts.append('\r'); pos += 1
            elif ec == 't':
                parts.append('\t'); pos += 1
            elif ec == 'u':
                pos += 1
                if pos + 4 > n:
                    raise JSONError("unexpected end of input in \\u escape", pos)
                code = 0
                for i in range(4):
                    hc = s[pos + i]
                    if '0' <= hc <= '9':
                        d = ord(hc) - 48
                    elif 'a' <= hc <= 'f':
                        d = ord(hc) - 87
                    elif 'A' <= hc <= 'F':
                        d = ord(hc) - 55
                    else:
                        raise JSONError("invalid hex digit in \\u escape", pos + i)
                    code = code * 16 + d
                pos += 4
                if 0xD800 <= code <= 0xDBFF:
                    if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                        low = 0
                        valid = True
                        for i in range(4):
                            hc = s[pos + 2 + i]
                            if '0' <= hc <= '9':
                                d = ord(hc) - 48
                            elif 'a' <= hc <= 'f':
                                d = ord(hc) - 87
                            elif 'A' <= hc <= 'F':
                                d = ord(hc) - 55
                            else:
                                valid = False
                                break
                            low = low * 16 + d
                        if valid and 0xDC00 <= low <= 0xDFFF:
                            cp = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                            parts.append(chr(cp))
                            pos += 6
                            continue
                parts.append(chr(code))
            else:
                raise JSONError("invalid escape character", pos)
        elif ord(c) < 0x20:
            raise JSONError("control character in string", pos)
        else:
            parts.append(c)
            pos += 1


def _parse_number(s, pos, n):
    """Parse a JSON number starting at s[pos].
    Returns (number_value, new_pos)."""
    start = pos
    if s[pos] == '-':
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input in number", pos)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit after '-'", pos)
    if s[pos] == '0':
        pos += 1
        if pos < n and '0' <= s[pos] <= '9':
            raise JSONError("leading zero not allowed", pos)
    else:
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    is_float = False
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
        return float(text), pos
    else:
        return int(text), pos


def _parse_literal(s, pos, n, expected):
    """Parse a literal starting at s[pos]. Returns new_pos."""
    for i in range(1, len(expected)):
        if pos + i >= n:
            raise JSONError("unexpected end of input in literal", n)
        if s[pos + i] != expected[i]:
            raise JSONError("invalid literal", pos + i)
    return pos + len(expected)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")

    n = len(s)
    pos = 0
    # Stack frames: [is_array, container, state, key]
    #   is_array: bool
    #   container: list or dict
    #   state: array: 0=expect_value, 1=expect_comma_or_end
    #          object: 0=expect_key_or_end, 1=expect_colon, 2=expect_value, 3=expect_comma_or_end
    #   key: str or None
    stack = []
    top_result = None
    top_done = False

    while True:
        # Skip whitespace
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1

        if pos >= n:
            if top_done:
                return top_result
            raise JSONError("unexpected end of input", pos)

        c = s[pos]

        # Determine what we expect
        if not stack:
            if top_done:
                raise JSONError("trailing characters", pos)
            expect_value = True
            expect_comma_or_end = False
            expect_key_or_end = False
            expect_colon = False
        else:
            frame = stack[-1]
            if frame[0]:
                expect_value = frame[2] == 0
                expect_comma_or_end = frame[2] == 1
                expect_key_or_end = False
                expect_colon = False
            else:
                expect_value = frame[2] == 2
                expect_comma_or_end = frame[2] == 3
                expect_key_or_end = frame[2] == 0
                expect_colon = frame[2] == 1

        if expect_value:
            if c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                stack.append([True, [], 0, None])
                pos += 1
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                stack.append([False, {}, 0, None])
                pos += 1
            elif c == '"':
                val, pos = _parse_string(s, pos, n)
                if not stack:
                    top_result = val
                    top_done = True
                else:
                    frame = stack[-1]
                    if frame[0]:
                        frame[1].append(val)
                        frame[2] = 1
                    else:
                        frame[1][frame[3]] = val
                        frame[2] = 3
            elif c == 't':
                pos = _parse_literal(s, pos, n, 'true')
                if not stack:
                    top_result = True
                    top_done = True
                else:
                    frame = stack[-1]
                    if frame[0]:
                        frame[1].append(True)
                        frame[2] = 1
                    else:
                        frame[1][frame[3]] = True
                        frame[2] = 3
            elif c == 'f':
                pos = _parse_literal(s, pos, n, 'false')
                if not stack:
                    top_result = False
                    top_done = True
                else:
                    frame = stack[-1]
                    if frame[0]:
                        frame[1].append(False)
                        frame[2] = 1
                    else:
                        frame[1][frame[3]] = False
                        frame[2] = 3
            elif c == 'n':
                pos = _parse_literal(s, pos, n, 'null')
                if not stack:
                    top_result = None
                    top_done = True
                else:
                    frame = stack[-1]
                    if frame[0]:
                        frame[1].append(None)
                        frame[2] = 1
                    else:
                        frame[1][frame[3]] = None
                        frame[2] = 3
            elif c == '-' or '0' <= c <= '9':
                val, pos = _parse_number(s, pos, n)
                if not stack:
                    top_result = val
                    top_done = True
                else:
                    frame = stack[-1]
                    if frame[0]:
                        frame[1].append(val)
                        frame[2] = 1
                    else:
                        frame[1][frame[3]] = val
                        frame[2] = 3
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif expect_comma_or_end:
            if c == ',':
                pos += 1
                stack[-1][2] = 0
            elif c == ']' and stack[-1][0]:
                val = stack[-1][1]
                stack.pop()
                pos += 1
                if not stack:
                    top_result = val
                    top_done = True
                else:
                    frame = stack[-1]
                    if frame[0]:
                        frame[1].append(val)
                        frame[2] = 1
                    else:
                        frame[1][frame[3]] = val
                        frame[2] = 3
            elif c == '}' and not stack[-1][0]:
                val = stack[-1][1]
                stack.pop()
                pos += 1
                if not stack:
                    top_result = val
                    top_done = True
                else:
                    frame = stack[-1]
                    if frame[0]:
                        frame[1].append(val)
                        frame[2] = 1
                    else:
                        frame[1][frame[3]] = val
                        frame[2] = 3
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif expect_key_or_end:
            if c == '"':
                key, pos = _parse_string(s, pos, n)
                stack[-1][3] = key
                stack[-1][2] = 1  # expect colon
            elif c == '}':
                val = stack[-1][1]
                stack.pop()
                pos += 1
                if not stack:
                    top_result = val
                    top_done = True
                else:
                    frame = stack[-1]
                    if frame[0]:
                        frame[1].append(val)
                        frame[2] = 1
                    else:
                        frame[1][frame[3]] = val
                        frame[2] = 3
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif expect_colon:
            if c == ':':
                pos += 1
                stack[-1][2] = 2  # expect value
            else:
                raise JSONError(f"unexpected character {c!r}", pos)
