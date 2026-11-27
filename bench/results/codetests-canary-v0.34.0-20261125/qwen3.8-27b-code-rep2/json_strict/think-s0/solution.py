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
    stack = []  # entries: [type, container, key]  type: 'a' or 'o'

    WS = ' \t\n\r'
    HEX = '0123456789abcdefABCDEF'

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening "
        chars = []
        while True:
            if pos >= n:
                raise JSONError("unexpected end of input in string", pos)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of input in string escape", pos)
                esc = s[pos]
                if esc == '"':
                    chars.append('"'); pos += 1
                elif esc == '\\':
                    chars.append('\\'); pos += 1
                elif esc == '/':
                    chars.append('/'); pos += 1
                elif esc == 'b':
                    chars.append('\b'); pos += 1
                elif esc == 'f':
                    chars.append('\f'); pos += 1
                elif esc == 'n':
                    chars.append('\n'); pos += 1
                elif esc == 'r':
                    chars.append('\r'); pos += 1
                elif esc == 't':
                    chars.append('\t'); pos += 1
                elif esc == 'u':
                    pos += 1
                    hex_start = pos
                    for _ in range(4):
                        if pos >= n:
                            raise JSONError("unexpected end of input in \\u escape", pos)
                        if s[pos] not in HEX:
                            raise JSONError("invalid hex digit in \\u escape", pos)
                        pos += 1
                    code = int(s[hex_start:pos], 16)
                    if 0xD800 <= code <= 0xDBFF:
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            h2 = s[pos + 2:pos + 6]
                            if all(ch in HEX for ch in h2):
                                code2 = int(h2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    chars.append(chr(combined))
                                    pos += 6
                                    continue
                    chars.append(chr(code))
                else:
                    raise JSONError(f"invalid escape character '\\{esc}'", pos)
            elif ord(c) < 0x20:
                raise JSONError("unescaped control character in string", pos)
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

        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in number", pos)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit after decimal point", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in number", pos)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n:
            c = s[pos]
            if '0' <= c <= '9' or c == '.' or c in 'eE' or c in '+-':
                raise JSONError("invalid character after number", pos)

        text = s[start:pos]
        if is_float:
            return float(text)
        else:
            return int(text)

    def parse_literal(expected):
        nonlocal pos
        for i, ch in enumerate(expected):
            if pos + i >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos + i] != ch:
                raise JSONError("invalid literal", pos + i)
        pos += len(expected)

    def after_value(val):
        nonlocal result
        if not stack:
            result = val
            return 'done'
        t = stack[-1][0]
        if t == 'a':
            stack[-1][1].append(val)
            return 'arr_sep'
        else:
            stack[-1][1][stack[-1][2]] = val
            return 'obj_sep'

    # Main iterative parse loop
    state = 'value'
    result = None

    while True:
        if state in ('value', 'obj_val'):
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]

            if c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['a', [], None])
                state = 'arr_first'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['o', {}, None])
                state = 'obj_first'
            elif c == '"':
                val = parse_string()
                state = after_value(val)
            elif c == 't':
                parse_literal('true')
                state = after_value(True)
            elif c == 'f':
                parse_literal('false')
                state = after_value(False)
            elif c == 'n':
                parse_literal('null')
                state = after_value(None)
            elif c == '-' or '0' <= c <= '9':
                val = parse_number()
                state = after_value(val)
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'arr_first':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] == ']':
                pos += 1
                val = stack.pop()[1]
                state = after_value(val)
            else:
                state = 'value'

        elif state == 'arr_sep':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == ',':
                pos += 1
                state = 'value'
            elif c == ']':
                pos += 1
                val = stack.pop()[1]
                state = after_value(val)
            else:
                raise JSONError(f"expected ',' or ']', got {c!r}", pos)

        elif state == 'obj_first':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '}':
                pos += 1
                val = stack.pop()[1]
                state = after_value(val)
            elif c == '"':
                key = parse_string()
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError(f"expected string key or '}}', got {c!r}", pos)

        elif state == 'obj_colon':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] == ':':
                pos += 1
                state = 'obj_val'
            else:
                raise JSONError(f"expected ':', got {s[pos]!r}", pos)

        elif state == 'obj_sep':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == ',':
                pos += 1
                state = 'obj_key'
            elif c == '}':
                pos += 1
                val = stack.pop()[1]
                state = after_value(val)
            else:
                raise JSONError(f"expected ',' or '}}', got {c!r}", pos)

        elif state == 'obj_key':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '"':
                key = parse_string()
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError(f"expected string key, got {c!r}", pos)

        elif state == 'done':
            skip_ws()
            if pos < n:
                raise JSONError("trailing garbage", pos)
            return result
