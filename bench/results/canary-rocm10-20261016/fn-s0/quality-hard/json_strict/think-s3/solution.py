class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")

    n = len(s)
    pos = 0

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
                raise JSONError("Unterminated string", n)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            if c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("Unterminated string", n)
                e = s[pos]
                if e == '"':
                    chars.append('"'); pos += 1
                elif e == '\\':
                    chars.append('\\'); pos += 1
                elif e == '/':
                    chars.append('/'); pos += 1
                elif e == 'b':
                    chars.append('\b'); pos += 1
                elif e == 'f':
                    chars.append('\f'); pos += 1
                elif e == 'n':
                    chars.append('\n'); pos += 1
                elif e == 'r':
                    chars.append('\r'); pos += 1
                elif e == 't':
                    chars.append('\t'); pos += 1
                elif e == 'u':
                    pos += 1
                    if pos + 4 > n:
                        raise JSONError("Invalid \\u escape", n)
                    for i in range(4):
                        if s[pos + i] not in '0123456789abcdefABCDEF':
                            raise JSONError("Invalid \\u escape", pos + i)
                    code = int(s[pos:pos + 4], 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'):
                            h2 = s[pos + 2:pos + 6]
                            ok = True
                            for ch in h2:
                                if ch not in '0123456789abcdefABCDEF':
                                    ok = False
                                    break
                            if ok:
                                code2 = int(h2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    chars.append(chr(combined))
                                    pos += 6
                                    continue
                        chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    raise JSONError("Invalid escape", pos)
            elif ord(c) < 0x20:
                raise JSONError("Control character in string", pos)
            else:
                chars.append(c)
                pos += 1

    def parse_number():
        nonlocal pos
        start = pos
        is_float = False

        if pos < n and s[pos] == '-':
            pos += 1

        if pos >= n:
            raise JSONError("Unexpected end", n)

        if s[pos] == '0':
            pos += 1
        elif '1' <= s[pos] <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            raise JSONError("Invalid number", pos)

        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                raise JSONError("Unexpected end", n)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("Invalid number", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end", n)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("Invalid number", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def parse_literal(expected, val):
        nonlocal pos
        for ch in expected:
            if pos >= n:
                raise JSONError("Unexpected end", n)
            if s[pos] != ch:
                raise JSONError("Invalid literal", pos)
            pos += 1
        return val

    # --- iterative parser with explicit stack ---
    # stack entries: ['a', list] or ['o', dict, pending_key]
    stack = []
    result = None

    def assign(val):
        nonlocal result
        if not stack:
            result = val
            return 'done'
        top = stack[-1]
        if top[0] == 'a':
            top[1].append(val)
            return 'array_sep'
        else:
            top[1][top[2]] = val
            return 'obj_sep'

    state = 'value'

    while True:
        if state == 'done':
            break

        if state == 'value':
            skip_ws()
            if pos >= n:
                raise JSONError("Unexpected end", n)
            c = s[pos]
            if c == '{':
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['o', {}, None])
                state = 'obj_first'
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['a', []])
                state = 'array_first'
            elif c == '"':
                state = assign(parse_string())
            elif c == 't':
                state = assign(parse_literal("true", True))
            elif c == 'f':
                state = assign(parse_literal("false", False))
            elif c == 'n':
                state = assign(parse_literal("null", None))
            elif c == '-' or ('0' <= c <= '9'):
                state = assign(parse_number())
            else:
                raise JSONError("Unexpected character", pos)

        elif state == 'array_first':
            skip_ws()
            if pos >= n:
                raise JSONError("Unexpected end", n)
            if s[pos] == ']':
                pos += 1
                val = stack.pop()[1]
                state = assign(val)
            else:
                state = 'value'

        elif state == 'array_sep':
            skip_ws()
            if pos >= n:
                raise JSONError("Unexpected end", n)
            if s[pos] == ']':
                pos += 1
                val = stack.pop()[1]
                state = assign(val)
            elif s[pos] == ',':
                pos += 1
                state = 'value'
            else:
                raise JSONError("Expected , or ]", pos)

        elif state == 'obj_first':
            skip_ws()
            if pos >= n:
                raise JSONError("Unexpected end", n)
            if s[pos] == '}':
                pos += 1
                val = stack.pop()[1]
                state = assign(val)
            elif s[pos] == '"':
                stack[-1][2] = parse_string()
                state = 'obj_colon'
            else:
                raise JSONError('Expected " or }', pos)

        elif state == 'obj_key':
            skip_ws()
            if pos >= n:
                raise JSONError("Unexpected end", n)
            if s[pos] == '"':
                stack[-1][2] = parse_string()
                state = 'obj_colon'
            else:
                raise JSONError('Expected "', pos)

        elif state == 'obj_colon':
            skip_ws()
            if pos >= n:
                raise JSONError("Unexpected end", n)
            if s[pos] == ':':
                pos += 1
                state = 'value'
            else:
                raise JSONError("Expected :", pos)

        elif state == 'obj_sep':
            skip_ws()
            if pos >= n:
                raise JSONError("Unexpected end", n)
            if s[pos] == '}':
                pos += 1
                val = stack.pop()[1]
                state = assign(val)
            elif s[pos] == ',':
                pos += 1
                state = 'obj_key'
            else:
                raise JSONError("Expected , or }", pos)

    skip_ws()
    if pos < n:
        raise JSONError("Extra data", pos)

    return result
