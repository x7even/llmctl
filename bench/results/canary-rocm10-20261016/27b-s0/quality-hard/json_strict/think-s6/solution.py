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
    stack = []  # [type, container, state, key]

    _HEX = frozenset('0123456789abcdefABCDEF')

    def skip_ws():
        nonlocal pos
        while pos < n:
            c = s[pos]
            if c == ' ' or c == '\t' or c == '\n' or c == '\r':
                pos += 1
            else:
                break

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening "
        parts = []
        while True:
            # Fast path: consume run of plain characters
            start = pos
            while pos < n:
                c = s[pos]
                if c == '"' or c == '\\' or c < ' ':
                    break
                pos += 1
            if pos > start:
                parts.append(s[start:pos])

            if pos >= n:
                raise JSONError("unexpected end of input in string", pos)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(parts)
            if c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of input in string escape", pos)
                esc = s[pos]
                if esc == '"':
                    parts.append('"')
                    pos += 1
                elif esc == '\\':
                    parts.append('\\')
                    pos += 1
                elif esc == '/':
                    parts.append('/')
                    pos += 1
                elif esc == 'b':
                    parts.append('\b')
                    pos += 1
                elif esc == 'f':
                    parts.append('\f')
                    pos += 1
                elif esc == 'n':
                    parts.append('\n')
                    pos += 1
                elif esc == 'r':
                    parts.append('\r')
                    pos += 1
                elif esc == 't':
                    parts.append('\t')
                    pos += 1
                elif esc == 'u':
                    for i in range(4):
                        idx = pos + 1 + i
                        if idx >= n:
                            raise JSONError("unexpected end of input in \\u escape", idx)
                        if s[idx] not in _HEX:
                            raise JSONError("invalid hex digit in \\u escape", idx)
                    code = int(s[pos + 1:pos + 5], 16)
                    pos += 5
                    if 0xD800 <= code <= 0xDBFF:
                        # High surrogate: check for immediately following low surrogate escape
                        if pos + 5 < n and s[pos] == '\\' and s[pos + 1] == 'u':
                            ok = True
                            for i in range(4):
                                if s[pos + 2 + i] not in _HEX:
                                    ok = False
                                    break
                            if ok:
                                code2 = int(s[pos + 2:pos + 6], 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    cp = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    parts.append(chr(cp))
                                    pos += 6
                                    continue
                    parts.append(chr(code))
                else:
                    raise JSONError(f"invalid escape character", pos)
            else:
                # c < ' ' i.e. control character
                raise JSONError("control character in string", pos)

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
            raise JSONError("invalid number", pos)

        has_frac = False
        if pos < n and s[pos] == '.':
            has_frac = True
            pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit after '.'", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        has_exp = False
        if pos < n and (s[pos] == 'e' or s[pos] == 'E'):
            has_exp = True
            pos += 1
            if pos < n and (s[pos] == '+' or s[pos] == '-'):
                pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if has_frac or has_exp:
            return float(text)
        return int(text)

    def parse_scalar():
        nonlocal pos
        c = s[pos]
        if c == '"':
            return parse_string()
        if c == 't':
            for i in range(4):
                idx = pos + i
                if idx >= n:
                    raise JSONError("unexpected end of input", idx)
                if s[idx] != 'true'[i]:
                    raise JSONError("invalid literal", idx)
            pos += 4
            return True
        if c == 'f':
            for i in range(5):
                idx = pos + i
                if idx >= n:
                    raise JSONError("unexpected end of input", idx)
                if s[idx] != 'false'[i]:
                    raise JSONError("invalid literal", idx)
            pos += 5
            return False
        if c == 'n':
            for i in range(4):
                idx = pos + i
                if idx >= n:
                    raise JSONError("unexpected end of input", idx)
                if s[idx] != 'null'[i]:
                    raise JSONError("invalid literal", idx)
            pos += 4
            return None
        return parse_number()

    def place_value(val):
        """Place a completed value in context. Returns True if top-level (done)."""
        nonlocal pos
        if not stack:
            skip_ws()
            if pos < n:
                raise JSONError("trailing characters", pos)
            return True
        entry = stack[-1]
        if entry[0] == 'array':
            entry[1].append(val)
            entry[2] = 'comma'
        else:
            entry[1][entry[3]] = val
            entry[2] = 'comma'
        return False

    # Main iterative loop
    while True:
        skip_ws()
        if pos >= n:
            raise JSONError("unexpected end of input", pos)

        c = s[pos]

        if not stack:
            # Top level: expect a value
            if c == '[':
                if len(stack) >= 500:
                    raise JSONError("depth limit exceeded", pos)
                stack.append(['array', [], 'value', None])
                pos += 1
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("depth limit exceeded", pos)
                stack.append(['object', {}, 'key', None])
                pos += 1
            else:
                val = parse_scalar()
                if place_value(val):
                    return val
        else:
            entry = stack[-1]
            etype = entry[0]
            state = entry[2]

            if etype == 'array':
                if state == 'value':
                    if c == ']':
                        arr = entry[1]
                        stack.pop()
                        pos += 1
                        if place_value(arr):
                            return arr
                    elif c == '[':
                        if len(stack) >= 500:
                            raise JSONError("depth limit exceeded", pos)
                        stack.append(['array', [], 'value', None])
                        pos += 1
                    elif c == '{':
                        if len(stack) >= 500:
                            raise JSONError("depth limit exceeded", pos)
                        stack.append(['object', {}, 'key', None])
                        pos += 1
                    else:
                        val = parse_scalar()
                        entry[1].append(val)
                        entry[2] = 'comma'
                else:  # comma
                    if c == ',':
                        pos += 1
                        entry[2] = 'value'
                    elif c == ']':
                        arr = entry[1]
                        stack.pop()
                        pos += 1
                        if place_value(arr):
                            return arr
                    else:
                        raise JSONError(f"expected ',' or ']', got {c!r}", pos)
            else:  # object
                if state == 'key':
                    if c == '}':
                        obj = entry[1]
                        stack.pop()
                        pos += 1
                        if place_value(obj):
                            return obj
                    elif c == '"':
                        key = parse_string()
                        entry[2] = 'colon'
                        entry[3] = key
                    else:
                        raise JSONError(f"expected string key or '}}', got {c!r}", pos)
                elif state == 'colon':
                    if c == ':':
                        pos += 1
                        entry[2] = 'value'
                    else:
                        raise JSONError(f"expected ':', got {c!r}", pos)
                elif state == 'value':
                    if c == '[':
                        if len(stack) >= 500:
                            raise JSONError("depth limit exceeded", pos)
                        stack.append(['array', [], 'value', None])
                        pos += 1
                    elif c == '{':
                        if len(stack) >= 500:
                            raise JSONError("depth limit exceeded", pos)
                        stack.append(['object', {}, 'key', None])
                        pos += 1
                    else:
                        val = parse_scalar()
                        entry[1][entry[3]] = val
                        entry[2] = 'comma'
                else:  # comma
                    if c == ',':
                        pos += 1
                        entry[2] = 'key'
                    elif c == '}':
                        obj = entry[1]
                        stack.pop()
                        pos += 1
                        if place_value(obj):
                            return obj
                    else:
                        raise JSONError(f"expected ',' or '}}', got {c!r}", pos)
