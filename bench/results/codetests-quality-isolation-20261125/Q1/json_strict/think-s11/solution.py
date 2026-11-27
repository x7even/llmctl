class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_HEX = frozenset('0123456789abcdefABCDEF')
_WS = ' \t\n\r'


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    depth = 0
    stack = []  # [type, container, state, extra]
    top_result = None
    top_done = False

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in _WS:
            pos += 1

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening quote
        chars = []
        while True:
            if pos >= n:
                raise JSONError("unterminated string", pos)
            ch = s[pos]
            if ch == '"':
                pos += 1
                return ''.join(chars)
            elif ch == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unterminated escape sequence", pos)
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
                    hex_digits = []
                    for i in range(4):
                        idx = pos + 1 + i
                        if idx >= n:
                            raise JSONError("truncated \\u escape", n)
                        h = s[idx]
                        if h not in _HEX:
                            raise JSONError("invalid hex digit in \\u escape", idx)
                        hex_digits.append(h)
                    code = int(''.join(hex_digits), 16)
                    pos += 5
                    if 0xD800 <= code <= 0xDBFF:
                        if pos + 5 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            all_hex = True
                            for i in range(4):
                                if s[pos + 2 + i] not in _HEX:
                                    all_hex = False
                                    break
                            if all_hex:
                                code2 = int(s[pos + 2:pos + 6], 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    code = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    pos += 5
                    chars.append(chr(code))
                else:
                    raise JSONError(f"invalid escape character", pos)
            elif ord(ch) < 0x20:
                raise JSONError("control character in string", pos)
            else:
                chars.append(ch)
                pos += 1

    def parse_number():
        nonlocal pos
        start = pos
        if pos < n and s[pos] == '-':
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", pos)
        if s[pos] == '0':
            pos += 1
            if pos < n and '0' <= s[pos] <= '9':
                raise JSONError("leading zero in number", pos)
        elif '1' <= s[pos] <= '9':
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
                raise JSONError("expected digit after decimal point", pos)
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
        else:
            return int(text)

    def parse_literal(lit):
        nonlocal pos
        end = pos + len(lit)
        if end > n:
            raise JSONError("truncated literal", n)
        for i in range(len(lit)):
            if s[pos + i] != lit[i]:
                raise JSONError("invalid literal", pos + i)
        pos = end

    def parse_value():
        nonlocal pos, depth
        skip_ws()
        if pos >= n:
            raise JSONError("unexpected end of input", pos)
        ch = s[pos]
        if ch == '{':
            if depth >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            depth += 1
            stack.append(['o', {}, 'first', None])
            pos += 1
            return None, False
        elif ch == '[':
            if depth >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            depth += 1
            stack.append(['a', [], 'first', None])
            pos += 1
            return None, False
        elif ch == '"':
            return parse_string(), True
        elif ch == '-' or '0' <= ch <= '9':
            return parse_number(), True
        elif ch == 't':
            parse_literal('true')
            return True, True
        elif ch == 'f':
            parse_literal('false')
            return False, True
        elif ch == 'n':
            parse_literal('null')
            return None, True
        else:
            raise JSONError(f"unexpected character {ch!r}", pos)

    def complete_value(val):
        nonlocal top_result, top_done, depth
        if not stack:
            top_result = val
            top_done = True
        else:
            frame = stack[-1]
            if frame[0] == 'a':
                frame[1].append(val)
                frame[2] = 'sep'
            else:
                frame[1][frame[3]] = val
                frame[2] = 'sep'

    while True:
        skip_ws()

        if not stack:
            if top_done:
                if pos < n:
                    raise JSONError("trailing data", pos)
                break
            else:
                val, complete = parse_value()
                if complete:
                    complete_value(val)
        else:
            frame = stack[-1]
            ftype = frame[0]
            fstate = frame[2]

            if ftype == 'a':
                if fstate == 'first':
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == ']':
                        pos += 1
                        val = frame[1]
                        stack.pop()
                        depth -= 1
                        complete_value(val)
                    else:
                        val, complete = parse_value()
                        if complete:
                            complete_value(val)
                elif fstate == 'sep':
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == ',':
                        pos += 1
                        frame[2] = 'next'
                    elif s[pos] == ']':
                        pos += 1
                        val = frame[1]
                        stack.pop()
                        depth -= 1
                        complete_value(val)
                    else:
                        raise JSONError(f"expected ',' or ']', got {s[pos]!r}", pos)
                elif fstate == 'next':
                    val, complete = parse_value()
                    if complete:
                        complete_value(val)

            elif ftype == 'o':
                if fstate == 'first':
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == '}':
                        pos += 1
                        val = frame[1]
                        stack.pop()
                        depth -= 1
                        complete_value(val)
                    elif s[pos] == '"':
                        key = parse_string()
                        frame[3] = key
                        frame[2] = 'colon'
                    else:
                        raise JSONError(f"expected string key, got {s[pos]!r}", pos)
                elif fstate == 'colon':
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == ':':
                        pos += 1
                        frame[2] = 'value'
                    else:
                        raise JSONError(f"expected ':', got {s[pos]!r}", pos)
                elif fstate == 'value':
                    val, complete = parse_value()
                    if complete:
                        complete_value(val)
                elif fstate == 'sep':
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == ',':
                        pos += 1
                        frame[2] = 'next'
                    elif s[pos] == '}':
                        pos += 1
                        val = frame[1]
                        stack.pop()
                        depth -= 1
                        complete_value(val)
                    else:
                        raise JSONError(f"expected ',' or '}}', got {s[pos]!r}", pos)
                elif fstate == 'next':
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == '"':
                        key = parse_string()
                        frame[3] = key
                        frame[2] = 'colon'
                    else:
                        raise JSONError(f"expected string key, got {s[pos]!r}", pos)

    return top_result
