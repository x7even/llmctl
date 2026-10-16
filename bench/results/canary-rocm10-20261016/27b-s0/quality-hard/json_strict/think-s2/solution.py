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
    top_value = None
    top_done = False

    WS = ' \t\n\r'
    HEX = '0123456789abcdefABCDEF'
    ESC_MAP = {'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}

    def err(msg, p):
        raise JSONError(msg, p)

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def parse_string():
        nonlocal pos
        pos += 1
        parts = []
        start = pos
        while pos < n:
            c = s[pos]
            if c == '"':
                parts.append(s[start:pos])
                pos += 1
                return ''.join(parts)
            elif c == '\\':
                parts.append(s[start:pos])
                pos += 1
                if pos >= n:
                    err("unexpected end of input in string", n)
                esc = s[pos]
                if esc in ESC_MAP:
                    parts.append(ESC_MAP[esc])
                    pos += 1
                elif esc == 'u':
                    pos += 1
                    if pos + 4 > n:
                        err("unexpected end of input in \\u escape", n)
                    hex_str = s[pos:pos + 4]
                    for i, h in enumerate(hex_str):
                        if h not in HEX:
                            err("invalid hex digit in \\u escape", pos + i)
                    code = int(hex_str, 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            hex2 = s[pos + 2:pos + 6]
                            valid = True
                            for h in hex2:
                                if h not in HEX:
                                    valid = False
                                    break
                            if valid:
                                code2 = int(hex2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    parts.append(chr(combined))
                                    pos += 6
                                    start = pos
                                    continue
                    parts.append(chr(code))
                else:
                    err("invalid escape character", pos)
                start = pos
            elif ord(c) < 0x20:
                err("unescaped control character in string", pos)
            else:
                pos += 1
        err("unexpected end of input in string", n)

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
                err("leading zero in number", pos)
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

    def add_value(value):
        nonlocal top_value, top_done
        if not stack:
            top_value = value
            top_done = True
        else:
            frame = stack[-1]
            if frame[0]:
                frame[1].append(value)
                frame[2] = 1
            else:
                frame[1][frame[3]] = value
                frame[2] = 3

    def push_container(c):
        nonlocal pos
        if len(stack) >= 500:
            err("maximum nesting depth exceeded", pos)
        if c == '{':
            stack.append([False, {}, 0, None])
        else:
            stack.append([True, [], 0, None])
        pos += 1

    def parse_literal(lit):
        nonlocal pos
        ln = len(lit)
        for i in range(ln):
            if pos + i >= n:
                err("unexpected end of input", n)
            if s[pos + i] != lit[i]:
                err("invalid literal", pos + i)
        pos += ln

    def try_parse_value():
        nonlocal pos
        c = s[pos]
        if c == '{' or c == '[':
            push_container(c)
            return True
        elif c == '"':
            val = parse_string()
            add_value(val)
            return True
        elif c == 't':
            parse_literal('true')
            add_value(True)
            return True
        elif c == 'f':
            parse_literal('false')
            add_value(False)
            return True
        elif c == 'n':
            parse_literal('null')
            add_value(None)
            return True
        elif c == '-' or '0' <= c <= '9':
            val = parse_number()
            add_value(val)
            return True
        else:
            return False

    while True:
        skip_ws()
        if pos >= n:
            if stack:
                err("unexpected end of input", n)
            elif not top_done:
                err("unexpected end of input", n)
            else:
                return top_value

        c = s[pos]

        if not stack:
            if not top_done:
                if c == '{' or c == '[':
                    push_container(c)
                elif c == '"':
                    top_value = parse_string()
                    top_done = True
                elif c == 't':
                    parse_literal('true')
                    top_value = True
                    top_done = True
                elif c == 'f':
                    parse_literal('false')
                    top_value = False
                    top_done = True
                elif c == 'n':
                    parse_literal('null')
                    top_value = None
                    top_done = True
                elif c == '-' or '0' <= c <= '9':
                    top_value = parse_number()
                    top_done = True
                else:
                    err("unexpected character", pos)
            else:
                err("trailing garbage", pos)
        else:
            frame = stack[-1]
            is_array = frame[0]
            state = frame[2]
            if is_array:
                if state == 0:
                    if c == ']':
                        stack.pop()
                        pos += 1
                        add_value(frame[1])
                    elif try_parse_value():
                        pass
                    else:
                        err("unexpected character in array", pos)
                elif state == 1:
                    if c == ',':
                        frame[2] = 2
                        pos += 1
                    elif c == ']':
                        stack.pop()
                        pos += 1
                        add_value(frame[1])
                    else:
                        err("expected ',' or ']' in array", pos)
                else:
                    if try_parse_value():
                        pass
                    else:
                        err("unexpected character in array", pos)
            else:
                if state == 0:
                    if c == '}':
                        stack.pop()
                        pos += 1
                        add_value(frame[1])
                    elif c == '"':
                        key = parse_string()
                        frame[2] = 1
                        frame[3] = key
                    else:
                        err("expected string key or '}'", pos)
                elif state == 1:
                    if c == ':':
                        frame[2] = 2
                        pos += 1
                    else:
                        err("expected ':'", pos)
                elif state == 2:
                    if try_parse_value():
                        pass
                    else:
                        err("unexpected character in object", pos)
                elif state == 3:
                    if c == ',':
                        frame[2] = 4
                        frame[3] = None
                        pos += 1
                    elif c == '}':
                        stack.pop()
                        pos += 1
                        add_value(frame[1])
                    else:
                        err("expected ',' or '}' in object", pos)
                else:
                    if c == '"':
                        key = parse_string()
                        frame[2] = 1
                        frame[3] = key
                    else:
                        err("expected string key", pos)