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
    WS = ' \t\n\r'
    HEX = frozenset('0123456789abcdefABCDEF')

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def parse_string():
        nonlocal pos
        # s[pos] == '"'
        pos += 1
        parts = []
        while pos < n:
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(parts)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of input in string escape", pos)
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
                    for i in range(4):
                        if pos + i >= n:
                            raise JSONError("unexpected end of input in \\u escape", n)
                        if s[pos + i] not in HEX:
                            raise JSONError("invalid hex digit in \\u escape", pos + i)
                    code = int(s[pos:pos + 4], 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                                and all(ch in HEX for ch in s[pos + 2:pos + 6])):
                            low = int(s[pos + 2:pos + 6], 16)
                            if 0xDC00 <= low <= 0xDFFF:
                                cp = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                                parts.append(chr(cp))
                                pos += 6
                                continue
                    parts.append(chr(code))
                else:
                    raise JSONError(f"invalid escape character '\\{ec}'", pos)
            elif c < ' ':
                raise JSONError("control character in string", pos)
            else:
                parts.append(c)
                pos += 1
        raise JSONError("unexpected end of input in string", n)

    def parse_number():
        nonlocal pos
        start = pos
        if s[pos] == '-':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in number", pos)
        c = s[pos]
        if c == '0':
            pos += 1
            if pos < n and '0' <= s[pos] <= '9':
                raise JSONError("leading zero in number", pos)
        elif '1' <= c <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            raise JSONError("expected digit in number", pos)
        is_float = False
        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in number", pos)
            if not '0' <= s[pos] <= '9':
                raise JSONError("expected digit after '.'", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in number", pos)
            if not '0' <= s[pos] <= '9':
                raise JSONError("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def check_literal(expected):
        nonlocal pos
        for i in range(len(expected)):
            if pos + i >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos + i] != expected[i]:
                raise JSONError(f"invalid literal, expected {expected!r}", pos + i)
        pos += len(expected)

    # Stack frames: [container, key]
    stack = []
    state = 'value'
    result = None

    while True:
        skip_ws()

        if state == 'value':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                arr = []
                stack.append([arr, None])
                pos += 1
                state = 'value_or_arr_end'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                obj = {}
                stack.append([obj, None])
                pos += 1
                state = 'key_or_end'
            elif c == '"':
                val = parse_string()
                if not stack:
                    result = val
                    state = 'done'
                else:
                    container, key = stack[-1]
                    if isinstance(container, list):
                        container.append(val)
                        state = 'comma_or_arr_end'
                    else:
                        container[key] = val
                        state = 'comma_or_obj_end'
            elif c == 't':
                check_literal('true')
                val = True
                if not stack:
                    result = val
                    state = 'done'
                else:
                    container, key = stack[-1]
                    if isinstance(container, list):
                        container.append(val)
                        state = 'comma_or_arr_end'
                    else:
                        container[key] = val
                        state = 'comma_or_obj_end'
            elif c == 'f':
                check_literal('false')
                val = False
                if not stack:
                    result = val
                    state = 'done'
                else:
                    container, key = stack[-1]
                    if isinstance(container, list):
                        container.append(val)
                        state = 'comma_or_arr_end'
                    else:
                        container[key] = val
                        state = 'comma_or_obj_end'
            elif c == 'n':
                check_literal('null')
                val = None
                if not stack:
                    result = val
                    state = 'done'
                else:
                    container, key = stack[-1]
                    if isinstance(container, list):
                        container.append(val)
                        state = 'comma_or_arr_end'
                    else:
                        container[key] = val
                        state = 'comma_or_obj_end'
            elif c == '-' or '0' <= c <= '9':
                val = parse_number()
                if not stack:
                    result = val
                    state = 'done'
                else:
                    container, key = stack[-1]
                    if isinstance(container, list):
                        container.append(val)
                        state = 'comma_or_arr_end'
                    else:
                        container[key] = val
                        state = 'comma_or_obj_end'
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'value_or_arr_end':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == ']':
                pos += 1
                arr, _ = stack.pop()
                if not stack:
                    result = arr
                    state = 'done'
                else:
                    container, key = stack[-1]
                    if isinstance(container, list):
                        container.append(arr)
                        state = 'comma_or_arr_end'
                    else:
                        container[key] = arr
                        state = 'comma_or_obj_end'
            else:
                state = 'value'

        elif state == 'key_or_end':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '}':
                pos += 1
                obj, _ = stack.pop()
                if not stack:
                    result = obj
                    state = 'done'
                else:
                    container, key = stack[-1]
                    if isinstance(container, list):
                        container.append(obj)
                        state = 'comma_or_arr_end'
                    else:
                        container[key] = obj
                        state = 'comma_or_obj_end'
            elif c == '"':
                key_val = parse_string()
                stack[-1][1] = key_val
                state = 'colon'
            else:
                raise JSONError(f"expected string key or '}}', got {c!r}", pos)

        elif state == 'colon':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c != ':':
                raise JSONError(f"expected ':', got {c!r}", pos)
            pos += 1
            state = 'value'

        elif state == 'comma_or_arr_end':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == ',':
                pos += 1
                state = 'value'
            elif c == ']':
                pos += 1
                arr, _ = stack.pop()
                if not stack:
                    result = arr
                    state = 'done'
                else:
                    container, key = stack[-1]
                    if isinstance(container, list):
                        container.append(arr)
                        state = 'comma_or_arr_end'
                    else:
                        container[key] = arr
                        state = 'comma_or_obj_end'
            else:
                raise JSONError(f"expected ',' or ']', got {c!r}", pos)

        elif state == 'comma_or_obj_end':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == ',':
                pos += 1
                state = 'key_or_end'
            elif c == '}':
                pos += 1
                obj, _ = stack.pop()
                if not stack:
                    result = obj
                    state = 'done'
                else:
                    container, key = stack[-1]
                    if isinstance(container, list):
                        container.append(obj)
                        state = 'comma_or_arr_end'
                    else:
                        container[key] = obj
                        state = 'comma_or_obj_end'
            else:
                raise JSONError(f"expected ',' or '}}', got {c!r}", pos)

        elif state == 'done':
            if pos >= n:
                return result
            raise JSONError("trailing garbage", pos)

    return result
