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

    ARR_FIRST = 0
    ARR_AFTER_VALUE = 1
    ARR_AFTER_COMMA = 2
    OBJ_FIRST = 3
    OBJ_AFTER_KEY = 4
    OBJ_AFTER_COLON = 5
    OBJ_AFTER_VALUE = 6
    OBJ_AFTER_COMMA = 7

    WS = ' \t\n\r'
    HEX_SET = frozenset('0123456789abcdefABCDEF')

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def parse_string():
        nonlocal pos
        pos += 1
        chars = []
        while pos < n:
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("truncated escape sequence", pos)
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
                    if pos + 4 > n:
                        raise JSONError("truncated \\u escape", pos)
                    h0 = s[pos]; h1 = s[pos+1]; h2 = s[pos+2]; h3 = s[pos+3]
                    if h0 not in HEX_SET:
                        raise JSONError("invalid hex digit in \\u escape", pos)
                    if h1 not in HEX_SET:
                        raise JSONError("invalid hex digit in \\u escape", pos + 1)
                    if h2 not in HEX_SET:
                        raise JSONError("invalid hex digit in \\u escape", pos + 2)
                    if h3 not in HEX_SET:
                        raise JSONError("invalid hex digit in \\u escape", pos + 3)
                    code = int(s[pos:pos+4], 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if pos + 6 <= n and s[pos] == '\\' and s[pos+1] == 'u':
                            h2_0 = s[pos+2]; h2_1 = s[pos+3]
                            h2_2 = s[pos+4]; h2_3 = s[pos+5]
                            if (h2_0 in HEX_SET and h2_1 in HEX_SET and
                                    h2_2 in HEX_SET and h2_3 in HEX_SET):
                                code2 = int(s[pos+2:pos+6], 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    chars.append(chr(0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)))
                                    pos += 6
                                    continue
                        chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    raise JSONError(f"invalid escape sequence \\{esc}", pos)
            elif ord(c) < 0x20:
                raise JSONError("unescaped control character in string", pos)
            else:
                chars.append(c)
                pos += 1
        raise JSONError("unterminated string", pos)

    def parse_number():
        nonlocal pos
        start = pos
        if s[pos] == '-':
            pos += 1
        if pos >= n:
            raise JSONError("truncated number", pos)
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
            return float(text)
        return int(text)

    def check_literal(lit):
        nonlocal pos
        ln = len(lit)
        for i in range(ln):
            if pos + i >= n or s[pos + i] != lit[i]:
                raise JSONError(f"invalid literal, expected '{lit}'", pos + i)
        pos += ln

    def deliver(value):
        container, state, pending_key = stack[-1]
        if isinstance(container, list):
            container.append(value)
            stack[-1][1] = ARR_AFTER_VALUE
        else:
            container[pending_key] = value
            stack[-1][1] = OBJ_AFTER_VALUE

    def parse_value():
        nonlocal pos
        c = s[pos]
        if c == '[':
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            stack.append([[], ARR_FIRST, None])
        elif c == '{':
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            stack.append([{}, OBJ_FIRST, None])
        elif c == '"':
            deliver(parse_string())
        elif c == 't':
            check_literal('true')
            deliver(True)
        elif c == 'f':
            check_literal('false')
            deliver(False)
        elif c == 'n':
            check_literal('null')
            deliver(None)
        elif c == '-' or '0' <= c <= '9':
            deliver(parse_number())
        else:
            raise JSONError(f"unexpected character {c!r}", pos)

    def pop_and_deliver():
        nonlocal pos
        val = stack.pop()[0]
        if not stack:
            skip_ws()
            if pos < n:
                raise JSONError("trailing garbage", pos)
            return val
        deliver(val)
        return None

    while True:
        if not stack:
            skip_ws()
            if pos >= n:
                raise JSONError("empty input", pos)
            c = s[pos]
            if c == '[':
                pos += 1
                stack.append([[], ARR_FIRST, None])
            elif c == '{':
                pos += 1
                stack.append([{}, OBJ_FIRST, None])
            elif c == '"':
                value = parse_string()
                skip_ws()
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return value
            elif c == 't':
                check_literal('true')
                skip_ws()
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return True
            elif c == 'f':
                check_literal('false')
                skip_ws()
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return False
            elif c == 'n':
                check_literal('null')
                skip_ws()
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return None
            elif c == '-' or '0' <= c <= '9':
                value = parse_number()
                skip_ws()
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return value
            else:
                raise JSONError(f"unexpected character {c!r}", pos)
        else:
            container, state, pending_key = stack[-1]
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]

            if state == ARR_FIRST:
                if c == ']':
                    pos += 1
                    result = pop_and_deliver()
                    if result is not None or not stack:
                        if not stack:
                            return result if result is not None else stack[-1][0] if stack else None
                        # Actually pop_and_deliver returns None if it delivered to parent
                        # Let me restructure
                else:
                    parse_value()
            elif state == ARR_AFTER_VALUE:
                if c == ',':
                    pos += 1
                    stack[-1][1] = ARR_AFTER_COMMA
                elif c == ']':
                    pos += 1
                    val = stack.pop()[0]
                    if not stack:
                        skip_ws()
                        if pos < n:
                            raise JSONError("trailing garbage", pos)
                        return val
                    deliver(val)
                else:
                    raise JSONError(f"expected ',' or ']', got {c!r}", pos)
            elif state == ARR_AFTER_COMMA:
                parse_value()
            elif state == OBJ_FIRST:
                if c == '}':
                    pos += 1
                    val = stack.pop()[0]
                    if not stack:
                        skip_ws()
                        if pos < n:
                            raise JSONError("trailing garbage", pos)
                        return val
                    deliver(val)
                elif c == '"':
                    key = parse_string()
                    stack[-1][1] = OBJ_AFTER_KEY
                    stack[-1][2] = key
                else:
                    raise JSONError(f"expected string key or '}}', got {c!r}", pos)
            elif state == OBJ_AFTER_KEY:
                if c == ':':
                    pos += 1
                    stack[-1][1] = OBJ_AFTER_COLON
                else:
                    raise JSONError(f"expected ':', got {c!r}", pos)
            elif state == OBJ_AFTER_COLON:
                parse_value()
            elif state == OBJ_AFTER_VALUE:
                if c == ',':
                    pos += 1
                    stack[-1][1] = OBJ_AFTER_COMMA
                elif c == '}':
                    pos += 1
                    val = stack.pop()[0]
                    if not stack:
                        skip_ws()
                        if pos < n:
                            raise JSONError("trailing garbage", pos)
                        return val
                    deliver(val)
                else:
                    raise JSONError(f"expected ',' or '}}', got {c!r}", pos)
            elif state == OBJ_AFTER_COMMA:
                if c == '"':
                    key = parse_string()
                    stack[-1][1] = OBJ_AFTER_KEY
                    stack[-1][2] = key
                else:
                    raise JSONError(f"expected string key, got {c!r}", pos)
