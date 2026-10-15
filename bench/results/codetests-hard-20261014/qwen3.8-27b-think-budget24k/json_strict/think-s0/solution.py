class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


# Precomputed hex value lookup (index by ord, -1 for non-hex)
_HEX_VAL = [-1] * 256
for _i in range(10):
    _HEX_VAL[ord('0') + _i] = _i
for _i in range(6):
    _HEX_VAL[ord('a') + _i] = 10 + _i
    _HEX_VAL[ord('A') + _i] = 10 + _i


def _get_hex(c):
    o = ord(c)
    if o < 256:
        return _HEX_VAL[o]
    return -1


def loads(s):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    # Stack entries: [type, container, state, key]
    #   type: 'a' (array) or 'o' (object)
    #   state for array: 'e' (expect element or ]) / 'a' (expect , or ])
    #   state for object: 'k' (expect key or }) / 'c' (expect :) / 'v' (expect value) / 'a' (expect , or })
    #   key: current key for objects
    stack = []
    result = None
    have_top = False

    def err(msg, p):
        raise JSONError(msg, p)

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening "
        chars = []
        while True:
            if pos >= n:
                err("unexpected end of input in string", pos)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    err("unexpected end of input in string escape", pos)
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
                        err("unexpected end of input in \\u escape", pos)
                    h1 = _get_hex(s[pos])
                    h2 = _get_hex(s[pos + 1])
                    h3 = _get_hex(s[pos + 2])
                    h4 = _get_hex(s[pos + 3])
                    if h1 < 0 or h2 < 0 or h3 < 0 or h4 < 0:
                        for j in range(4):
                            if _get_hex(s[pos + j]) < 0:
                                err("invalid hex digit in \\u escape", pos + j)
                        err("invalid \\u escape", pos)
                    code = (h1 << 12) | (h2 << 8) | (h3 << 4) | h4
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        # High surrogate: check for immediately following \uXXXX low surrogate
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            g1 = _get_hex(s[pos + 2])
                            g2 = _get_hex(s[pos + 3])
                            g3 = _get_hex(s[pos + 4])
                            g4 = _get_hex(s[pos + 5])
                            if g1 >= 0 and g2 >= 0 and g3 >= 0 and g4 >= 0:
                                code2 = (g1 << 12) | (g2 << 8) | (g3 << 4) | g4
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    chars.append(chr(combined))
                                    pos += 6
                                    continue
                        chars.append(chr(code))
                    elif 0xDC00 <= code <= 0xDFFF:
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
        if pos < n and s[pos] == '-':
            pos += 1
        if pos >= n:
            err("unexpected end of input in number", pos)
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
            err("invalid number start", pos)

        is_float = False
        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                err("unexpected end of input in number fraction", pos)
            if not ('0' <= s[pos] <= '9'):
                err("expected digit after '.'", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                err("unexpected end of input in number exponent", pos)
            if not ('0' <= s[pos] <= '9'):
                err("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def parse_literal(expected):
        nonlocal pos
        for i in range(1, len(expected)):
            if pos + i >= n:
                err("unexpected end of input in literal", pos + i)
            if s[pos + i] != expected[i]:
                err("invalid literal", pos + i)
        pos += len(expected)

    def handle_value(val):
        nonlocal result, have_top
        if not stack:
            result = val
            have_top = True
        else:
            parent = stack[-1]
            if parent[0] == 'a':
                parent[1].append(val)
                parent[2] = 'a'
            else:
                parent[1][parent[3]] = val
                parent[2] = 'a'

    def try_open_container():
        nonlocal pos
        c = s[pos]
        if len(stack) >= 500:
            err("maximum nesting depth exceeded", pos)
        if c == '[':
            stack.append(['a', [], 'e', None])
        else:
            stack.append(['o', {}, 'k', None])
        pos += 1

    # Main loop
    while True:
        skip_ws()

        if not stack:
            if have_top:
                if pos >= n:
                    return result
                err("trailing characters", pos)
            else:
                if pos >= n:
                    err("unexpected end of input", pos)
                c = s[pos]
                if c == '[' or c == '{':
                    try_open_container()
                elif c == '"':
                    result = parse_string()
                    have_top = True
                elif c == '-' or '0' <= c <= '9':
                    result = parse_number()
                    have_top = True
                elif c == 't':
                    parse_literal('true')
                    result = True
                    have_top = True
                elif c == 'f':
                    parse_literal('false')
                    result = False
                    have_top = True
                elif c == 'n':
                    parse_literal('null')
                    result = None
                    have_top = True
                else:
                    err("unexpected character", pos)
        else:
            top = stack[-1]
            ctype = top[0]
            container = top[1]
            state = top[2]

            if ctype == 'a':
                if state == 'e':
                    if pos >= n:
                        err("unexpected end of input", pos)
                    c = s[pos]
                    if c == ']':
                        stack.pop()
                        handle_value(container)
                        pos += 1
                    elif c == '[' or c == '{':
                        try_open_container()
                    elif c == '"':
                        container.append(parse_string())
                        top[2] = 'a'
                    elif c == '-' or '0' <= c <= '9':
                        container.append(parse_number())
                        top[2] = 'a'
                    elif c == 't':
                        parse_literal('true')
                        container.append(True)
                        top[2] = 'a'
                    elif c == 'f':
                        parse_literal('false')
                        container.append(False)
                        top[2] = 'a'
                    elif c == 'n':
                        parse_literal('null')
                        container.append(None)
                        top[2] = 'a'
                    else:
                        err("unexpected character in array", pos)
                else:  # 'a'
                    if pos >= n:
                        err("unexpected end of input", pos)
                    c = s[pos]
                    if c == ',':
                        pos += 1
                        top[2] = 'e'
                    elif c == ']':
                        stack.pop()
                        handle_value(container)
                        pos += 1
                    else:
                        err("expected ',' or ']' in array", pos)
            else:  # object
                if state == 'k':
                    if pos >= n:
                        err("unexpected end of input", pos)
                    c = s[pos]
                    if c == '}':
                        stack.pop()
                        handle_value(container)
                        pos += 1
                    elif c == '"':
                        top[3] = parse_string()
                        top[2] = 'c'
                    else:
                        err("expected string key in object", pos)
                elif state == 'c':
                    if pos >= n:
                        err("unexpected end of input", pos)
                    if s[pos] == ':':
                        pos += 1
                        top[2] = 'v'
                    else:
                        err("expected ':' in object", pos)
                elif state == 'v':
                    if pos >= n:
                        err("unexpected end of input", pos)
                    c = s[pos]
                    if c == '[' or c == '{':
                        try_open_container()
                    elif c == '"':
                        container[top[3]] = parse_string()
                        top[2] = 'a'
                    elif c == '-' or '0' <= c <= '9':
                        container[top[3]] = parse_number()
                        top[2] = 'a'
                    elif c == 't':
                        parse_literal('true')
                        container[top[3]] = True
                        top[2] = 'a'
                    elif c == 'f':
                        parse_literal('false')
                        container[top[3]] = False
                        top[2] = 'a'
                    elif c == 'n':
                        parse_literal('null')
                        container[top[3]] = None
                        top[2] = 'a'
                    else:
                        err("unexpected character in object value", pos)
                else:  # 'a'
                    if pos >= n:
                        err("unexpected end of input", pos)
                    c = s[pos]
                    if c == ',':
                        pos += 1
                        top[2] = 'k'
                    elif c == '}':
                        stack.pop()
                        handle_value(container)
                        pos += 1
                    else:
                        err("expected ',' or '}' in object", pos)
