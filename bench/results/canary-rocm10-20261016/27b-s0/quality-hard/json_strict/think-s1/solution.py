class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, not {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []  # [type, container, state, extra]
    # type: 0=array, 1=object
    # array states: 0=expect value or ], 1=expect , or ], 2=expect value
    # object states: 0=expect " or }, 1=expect :, 2=expect value, 3=expect , or }, 4=expect "

    current_value = None
    has_value = False

    WS = ' \t\n\r'
    HEX = '0123456789abcdefABCDEF'

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def fail(msg, p):
        raise JSONError(msg, p)

    def parse_number():
        nonlocal pos
        start = pos
        if pos < n and s[pos] == '-':
            pos += 1
        if pos >= n:
            fail("unexpected end of input", n)
        c = s[pos]
        if c == '0':
            pos += 1
        elif '1' <= c <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            fail("expected digit", pos)

        is_float = False
        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                fail("unexpected end of input", n)
            if not ('0' <= s[pos] <= '9'):
                fail("expected digit after '.'", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                fail("unexpected end of input", n)
            if not ('0' <= s[pos] <= '9'):
                fail("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        else:
            return int(text)

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening quote
        chars = []
        while True:
            if pos >= n:
                fail("unexpected end of input in string", n)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    fail("unexpected end of input in escape", n)
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
                        fail("unexpected end of input in \\u escape", n)
                    hex_str = s[pos:pos + 4]
                    for hc in hex_str:
                        if hc not in HEX:
                            fail("invalid hex digit in \\u escape", pos)
                    code = int(hex_str, 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            hex2 = s[pos + 2:pos + 6]
                            if all(hc in HEX for hc in hex2):
                                code2 = int(hex2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    chars.append(chr(combined))
                                    pos += 6
                                    continue
                    chars.append(chr(code))
                else:
                    fail(f"invalid escape character", pos)
            elif ord(c) < 0x20:
                fail("unescaped control character in string", pos)
            else:
                chars.append(c)
                pos += 1

    def match_literal(lit, value):
        nonlocal pos, current_value, has_value
        for i, ch in enumerate(lit):
            if pos + i >= n:
                fail("unexpected end of input", n)
            if s[pos + i] != ch:
                fail("invalid literal", pos + i)
        pos += len(lit)
        current_value = value
        has_value = True

    while True:
        if has_value:
            if not stack:
                skip_ws()
                if pos < n:
                    fail("trailing characters", pos)
                return current_value
            else:
                frame_type, container, state, extra = stack[-1]
                if frame_type == 0:
                    container.append(current_value)
                    stack[-1][2] = 1
                else:
                    container[extra] = current_value
                    stack[-1][2] = 3
                    stack[-1][3] = None
                has_value = False
            continue

        skip_ws()
        if pos >= n:
            fail("unexpected end of input", n)

        c = s[pos]
        need_value = False

        if not stack:
            need_value = True
        else:
            frame_type, container, state, extra = stack[-1]
            if frame_type == 0:
                if state == 0:
                    if c == ']':
                        pos += 1
                        stack.pop()
                        current_value = container
                        has_value = True
                        continue
                    need_value = True
                elif state == 1:
                    if c == ']':
                        pos += 1
                        stack.pop()
                        current_value = container
                        has_value = True
                        continue
                    elif c == ',':
                        pos += 1
                        stack[-1][2] = 2
                        continue
                    else:
                        fail(f"expected ',' or ']', got {c!r}", pos)
                elif state == 2:
                    need_value = True
            else:
                if state == 0:
                    if c == '}':
                        pos += 1
                        stack.pop()
                        current_value = container
                        has_value = True
                        continue
                    elif c == '"':
                        key = parse_string()
                        stack[-1][2] = 1
                        stack[-1][3] = key
                        continue
                    else:
                        fail(f"expected string key or '}}', got {c!r}", pos)
                elif state == 1:
                    if c == ':':
                        pos += 1
                        stack[-1][2] = 2
                        continue
                    else:
                        fail(f"expected ':', got {c!r}", pos)
                elif state == 2:
                    need_value = True
                elif state == 3:
                    if c == '}':
                        pos += 1
                        stack.pop()
                        current_value = container
                        has_value = True
                        continue
                    elif c == ',':
                        pos += 1
                        stack[-1][2] = 4
                        continue
                    else:
                        fail(f"expected ',' or '}}', got {c!r}", pos)
                elif state == 4:
                    if c == '"':
                        key = parse_string()
                        stack[-1][2] = 1
                        stack[-1][3] = key
                        continue
                    else:
                        fail(f"expected string key, got {c!r}", pos)

        if need_value:
            if c == '"':
                current_value = parse_string()
                has_value = True
            elif c == '[':
                if len(stack) >= 500:
                    fail("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append([0, [], 0, None])
            elif c == '{':
                if len(stack) >= 500:
                    fail("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append([1, {}, 0, None])
            elif c == 't':
                match_literal('true', True)
            elif c == 'f':
                match_literal('false', False)
            elif c == 'n':
                match_literal('null', None)
            elif c == '-' or '0' <= c <= '9':
                current_value = parse_number()
                has_value = True
            else:
                fail(f"unexpected character {c!r}", pos)
