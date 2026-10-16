class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}"
        )

    n = len(s)
    i = 0

    _WS = ' \t\n\r'
    _HEX = frozenset('0123456789abcdefABCDEF')

    stack = []
    result = None
    expect = 'value'

    def err(msg, pos):
        raise JSONError(msg, pos)

    def parse_string():
        nonlocal i
        i += 1
        parts = []
        start = i
        while True:
            if i >= n:
                err("unterminated string", n)
            ch = s[i]
            if ch == '"':
                parts.append(s[start:i])
                i += 1
                return ''.join(parts)
            elif ch == '\\':
                parts.append(s[start:i])
                i += 1
                if i >= n:
                    err("unterminated string", n)
                e = s[i]
                if e == '"':
                    parts.append('"'); i += 1
                elif e == '\\':
                    parts.append('\\'); i += 1
                elif e == '/':
                    parts.append('/'); i += 1
                elif e == 'b':
                    parts.append('\b'); i += 1
                elif e == 'f':
                    parts.append('\f'); i += 1
                elif e == 'n':
                    parts.append('\n'); i += 1
                elif e == 'r':
                    parts.append('\r'); i += 1
                elif e == 't':
                    parts.append('\t'); i += 1
                elif e == 'u':
                    i += 1
                    if i + 4 > n:
                        err("unterminated string", n)
                    hx = s[i:i + 4]
                    for j in range(4):
                        if hx[j] not in _HEX:
                            err("invalid \\u escape", i + j)
                    cp = int(hx, 16)
                    i += 4
                    if 0xD800 <= cp <= 0xDBFF:
                        if (i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u'):
                            hx2 = s[i + 2:i + 6]
                            ok = True
                            for j in range(4):
                                if hx2[j] not in _HEX:
                                    ok = False
                                    break
                            if ok:
                                cp2 = int(hx2, 16)
                                if 0xDC00 <= cp2 <= 0xDFFF:
                                    combined = 0x10000 + ((cp - 0xD800) << 10) + (cp2 - 0xDC00)
                                    parts.append(chr(combined))
                                    i += 6
                                    start = i
                                    continue
                        parts.append(chr(cp))
                    else:
                        parts.append(chr(cp))
                    start = i
                else:
                    err("invalid escape", i)
            elif ch < '\x20':
                err("control character in string", i)
            else:
                i += 1

    def finish_value(val):
        nonlocal expect, result
        if not stack:
            result = val
            expect = 'done'
        else:
            top = stack[-1]
            if top[0] == 'a':
                top[1].append(val)
                expect = 'array_sep'
            else:
                top[1][top[2]] = val
                expect = 'obj_sep'

    while True:
        if expect == 'value':
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                err("unexpected end of input", n)
            c = s[i]
            if c == '"':
                val = parse_string()
                finish_value(val)
            elif c == '[':
                if len(stack) + 1 > 500:
                    err("maximum nesting depth exceeded", i)
                stack.append(('a', []))
                i += 1
                expect = 'array_start'
            elif c == '{':
                if len(stack) + 1 > 500:
                    err("maximum nesting depth exceeded", i)
                stack.append(('o', {}))
                i += 1
                expect = 'obj_first_key'
            elif c == 't':
                for j, ch in enumerate('true'):
                    if i >= n:
                        err("unexpected end of input", n)
                    if s[i] != ch:
                        err("invalid literal", i)
                    i += 1
                finish_value(True)
            elif c == 'f':
                for j, ch in enumerate('false'):
                    if i >= n:
                        err("unexpected end of input", n)
                    if s[i] != ch:
                        err("invalid literal", i)
                    i += 1
                finish_value(False)
            elif c == 'n':
                for j, ch in enumerate('null'):
                    if i >= n:
                        err("unexpected end of input", n)
                    if s[i] != ch:
                        err("invalid literal", i)
                    i += 1
                finish_value(None)
            elif c == '-' or ('0' <= c <= '9'):
                start = i
                if c == '-':
                    i += 1
                    if i >= n:
                        err("unexpected end of input", n)
                if s[i] == '0':
                    i += 1
                    if i < n and '0' <= s[i] <= '9':
                        err("leading zero", i)
                elif '1' <= s[i] <= '9':
                    i += 1
                    while i < n and '0' <= s[i] <= '9':
                        i += 1
                else:
                    err("invalid number", i)
                is_float = False
                if i < n and s[i] == '.':
                    is_float = True
                    i += 1
                    if i >= n:
                        err("unexpected end of input", n)
                    if not ('0' <= s[i] <= '9'):
                        err("invalid fraction", i)
                    while i < n and '0' <= s[i] <= '9':
                        i += 1
                if i < n and (s[i] == 'e' or s[i] == 'E'):
                    is_float = True
                    i += 1
                    if i < n and (s[i] == '+' or s[i] == '-'):
                        i += 1
                    if i >= n:
                        err("unexpected end of input", n)
                    if not ('0' <= s[i] <= '9'):
                        err("invalid exponent", i)
                    while i < n and '0' <= s[i] <= '9':
                        i += 1
                text = s[start:i]
                if is_float:
                    val = float(text)
                else:
                    val = int(text)
                finish_value(val)
            else:
                err("unexpected character", i)

        elif expect == 'array_start':
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                err("unexpected end of input", n)
            if s[i] == ']':
                i += 1
                val = stack[-1][1]
                stack.pop()
                finish_value(val)
            else:
                expect = 'value'

        elif expect == 'array_sep':
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                err("unexpected end of input", n)
            c = s[i]
            if c == ',':
                i += 1
                expect = 'value'
            elif c == ']':
                i += 1
                val = stack[-1][1]
                stack.pop()
                finish_value(val)
            else:
                err("expected ',' or ']'", i)

        elif expect == 'obj_sep':
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                err("unexpected end of input", n)
            c = s[i]
            if c == ',':
                i += 1
                expect = 'obj_key'
            elif c == '}':
                i += 1
                val = stack[-1][1]
                stack.pop()
                finish_value(val)
            else:
                err("expected ',' or '}'", i)

        elif expect == 'obj_first_key':
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                err("unexpected end of input", n)
            c = s[i]
            if c == '}':
                i += 1
                val = stack[-1][1]
                stack.pop()
                finish_value(val)
            elif c == '"':
                key = parse_string()
                stack[-1] = ('o', stack[-1][1], key)
                expect = 'obj_colon'
            else:
                err("expected '\"' or '}'", i)

        elif expect == 'obj_key':
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                err("unexpected end of input", n)
            c = s[i]
            if c == '"':
                key = parse_string()
                stack[-1] = ('o', stack[-1][1], key)
                expect = 'obj_colon'
            else:
                err("expected '\"'", i)

        elif expect == 'obj_colon':
            while i < n and s[i] in _WS:
                i += 1
            if i >= n:
                err("unexpected end of input", n)
            if s[i] == ':':
                i += 1
                expect = 'value'
            else:
                err("expected ':'", i)

        elif expect == 'done':
            while i < n and s[i] in _WS:
                i += 1
            if i < n:
                err("trailing garbage", i)
            return result
