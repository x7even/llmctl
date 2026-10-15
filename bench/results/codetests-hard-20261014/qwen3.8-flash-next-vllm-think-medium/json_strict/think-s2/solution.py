class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    i = 0
    depth = 0
    MAX_DEPTH = 500
    _HEX = frozenset('0123456789abcdefABCDEF')
    _WS = frozenset(' \t\n\r')

    stack = []
    state = 'value'
    result = None

    def skip_ws():
        nonlocal i
        while i < n and s[i] in _WS:
            i += 1

    def err(msg, pos):
        raise JSONError(msg, pos)

    def parse_string():
        nonlocal i
        i += 1  # skip opening "
        parts = []
        while True:
            if i >= n:
                err("unexpected end of input", n)
            c = s[i]
            if c == '"':
                i += 1
                return ''.join(parts)
            elif c == '\\':
                i += 1
                if i >= n:
                    err("unexpected end of input", n)
                ec = s[i]
                if ec == '"':
                    parts.append('"'); i += 1
                elif ec == '\\':
                    parts.append('\\'); i += 1
                elif ec == '/':
                    parts.append('/'); i += 1
                elif ec == 'b':
                    parts.append('\b'); i += 1
                elif ec == 'f':
                    parts.append('\f'); i += 1
                elif ec == 'n':
                    parts.append('\n'); i += 1
                elif ec == 'r':
                    parts.append('\r'); i += 1
                elif ec == 't':
                    parts.append('\t'); i += 1
                elif ec == 'u':
                    i += 1
                    remaining = n - i
                    if remaining < 4:
                        for j in range(remaining):
                            if s[i + j] not in _HEX:
                                err("invalid hex digit", i + j)
                        err("unexpected end of input", n)
                    h = s[i:i + 4]
                    for j in range(4):
                        if h[j] not in _HEX:
                            err("invalid hex digit", i + j)
                    cp = int(h, 16)
                    i += 4
                    if 0xD800 <= cp <= 0xDBFF:
                        if (i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u'):
                            h2 = s[i + 2:i + 6]
                            ok = True
                            for j in range(4):
                                if h2[j] not in _HEX:
                                    ok = False
                                    break
                            if ok:
                                cp2 = int(h2, 16)
                                if 0xDC00 <= cp2 <= 0xDFFF:
                                    combined = 0x10000 + ((cp - 0xD800) << 10) + (cp2 - 0xDC00)
                                    parts.append(chr(combined))
                                    i += 6
                                    continue
                        parts.append(chr(cp))
                    elif 0xDC00 <= cp <= 0xDFFF:
                        parts.append(chr(cp))
                    else:
                        parts.append(chr(cp))
                else:
                    err("invalid escape", i)
            elif ord(c) < 0x20:
                err("control character in string", i)
            else:
                parts.append(c)
                i += 1

    def parse_number():
        nonlocal i
        start = i
        is_float = False
        if s[i] == '-':
            i += 1
        if i >= n:
            err("unexpected end of input", n)
        if s[i] == '0':
            i += 1
        elif '1' <= s[i] <= '9':
            while i < n and '0' <= s[i] <= '9':
                i += 1
        else:
            err("invalid number", i)
        if i < n and s[i] == '.':
            is_float = True
            i += 1
            if i >= n:
                err("unexpected end of input", n)
            if not ('0' <= s[i] <= '9'):
                err("invalid number", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1
        if i < n and s[i] in 'eE':
            is_float = True
            i += 1
            if i < n and s[i] in '+-':
                i += 1
            if i >= n:
                err("unexpected end of input", n)
            if not ('0' <= s[i] <= '9'):
                err("invalid number", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1
        text = s[start:i]
        if is_float:
            return float(text)
        return int(text)

    def parse_literal(expected, val):
        nonlocal i
        for ch in expected:
            if i >= n:
                err("unexpected end of input", n)
            if s[i] != ch:
                err("invalid literal", i)
            i += 1
        return val

    def deliver(val):
        nonlocal state, result
        if not stack:
            result = val
            state = 'done'
        else:
            top = stack[-1]
            if top[0] == 'array':
                top[1].append(val)
                state = 'array_after'
            else:
                top[1][top[2]] = val
                state = 'obj_after'

    while True:
        skip_ws()

        if i >= n:
            if state == 'done':
                return result
            err("unexpected end of input", n)

        c = s[i]

        if state == 'value':
            if c == '"':
                deliver(parse_string())
            elif c == '[':
                i += 1
                depth += 1
                if depth > MAX_DEPTH:
                    err("depth limit exceeded", i - 1)
                stack.append(['array', []])
                state = 'array_first'
            elif c == '{':
                i += 1
                depth += 1
                if depth > MAX_DEPTH:
                    err("depth limit exceeded", i - 1)
                stack.append(['object', {}, None])
                state = 'obj_first'
            elif c == 't':
                deliver(parse_literal('true', True))
            elif c == 'f':
                deliver(parse_literal('false', False))
            elif c == 'n':
                deliver(parse_literal('null', None))
            elif c == '-' or '0' <= c <= '9':
                deliver(parse_number())
            else:
                err("invalid character", i)

        elif state == 'array_first':
            if c == ']':
                i += 1
                depth -= 1
                val = stack.pop()[1]
                deliver(val)
            else:
                state = 'value'
                continue

        elif state == 'array_after':
            if c == ',':
                i += 1
                state = 'value'
            elif c == ']':
                i += 1
                depth -= 1
                val = stack.pop()[1]
                deliver(val)
            else:
                err("expected , or ]", i)

        elif state == 'obj_first':
            if c == '}':
                i += 1
                depth -= 1
                val = stack.pop()[1]
                deliver(val)
            elif c == '"':
                stack[-1][2] = parse_string()
                state = 'obj_colon'
            else:
                err("expected key or }", i)

        elif state == 'obj_key':
            if c == '"':
                stack[-1][2] = parse_string()
                state = 'obj_colon'
            else:
                err("expected key", i)

        elif state == 'obj_colon':
            if c == ':':
                i += 1
                state = 'value'
            else:
                err("expected :", i)

        elif state == 'obj_after':
            if c == ',':
                i += 1
                state = 'obj_key'
            elif c == '}':
                i += 1
                depth -= 1
                val = stack.pop()[1]
                deliver(val)
            else:
                err("expected , or }", i)

        elif state == 'done':
            err("trailing garbage", i)
