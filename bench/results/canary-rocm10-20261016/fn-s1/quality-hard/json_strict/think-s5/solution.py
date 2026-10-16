import re

class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos

_HEX_DIGITS = frozenset('0123456789abcdefABCDEF')
_WS = frozenset(' \t\n\r')
_string_special_re = re.compile(r'["\\\x00-\x1f]')


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in _WS:
            pos += 1

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening quote
        chars = []
        while True:
            m = _string_special_re.search(s, pos)
            if m is None:
                raise JSONError("unterminated string", n)
            if m.start() > pos:
                chars.append(s[pos:m.start()])
            pos = m.start()
            c = s[pos]
            if c == '"':
                pos += 1
                break
            elif c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
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
                        raise JSONError("unexpected end of input", n)
                    for i in range(4):
                        if s[pos + i] not in _HEX_DIGITS:
                            raise JSONError("invalid hex digit", pos + i)
                    code = int(s[pos:pos + 4], 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'):
                            h2 = s[pos + 2:pos + 6]
                            if all(ch in _HEX_DIGITS for ch in h2):
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
                    raise JSONError("invalid escape", pos)
            else:
                raise JSONError("control character in string", pos)
        return ''.join(chars)

    def parse_number():
        nonlocal pos
        start = pos
        is_float = False

        if pos < n and s[pos] == '-':
            pos += 1

        if pos >= n:
            raise JSONError("unexpected end of input", n)

        if s[pos] == '0':
            pos += 1
            if pos < n and '0' <= s[pos] <= '9':
                raise JSONError("leading zeros", pos)
        elif '1' <= s[pos] <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            raise JSONError("expected digit", pos)

        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit after '.'", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def parse_literal(expected, value):
        nonlocal pos
        for c in expected:
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] != c:
                raise JSONError("invalid literal", pos)
            pos += 1
        return value

    # --- main iterative parser ---
    stack = []  # each entry: [kind, container, key]
    state = 'value'
    result = None

    while True:
        if state == 'value':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]
            if c == '[':
                if len(stack) >= 500:
                    raise JSONError("depth limit exceeded", pos)
                pos += 1
                stack.append(['a', [], None])
                state = 'array_first'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("depth limit exceeded", pos)
                pos += 1
                stack.append(['o', {}, None])
                state = 'obj_first'
            elif c == '"':
                result = parse_string()
                state = 'after_value'
            elif c == 't':
                result = parse_literal('true', True)
                state = 'after_value'
            elif c == 'f':
                result = parse_literal('false', False)
                state = 'after_value'
            elif c == 'n':
                result = parse_literal('null', None)
                state = 'after_value'
            elif c == '-' or ('0' <= c <= '9'):
                result = parse_number()
                state = 'after_value'
            else:
                raise JSONError("unexpected character", pos)

        elif state == 'array_first':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ']':
                pos += 1
                result = stack.pop()[1]
                state = 'after_value'
            else:
                state = 'value'

        elif state == 'obj_first':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == '}':
                pos += 1
                result = stack.pop()[1]
                state = 'after_value'
            elif s[pos] == '"':
                key = parse_string()
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("expected key", pos)

        elif state == 'after_value':
            if not stack:
                state = 'top_after'
            else:
                top = stack[-1]
                if top[0] == 'a':
                    top[1].append(result)
                    state = 'array_comma_or_end'
                else:
                    top[1][top[2]] = result
                    state = 'obj_comma_or_end'

        elif state == 'array_comma_or_end':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                pos += 1
                state = 'value'
            elif s[pos] == ']':
                pos += 1
                result = stack.pop()[1]
                state = 'after_value'
            else:
                raise JSONError("expected , or ]", pos)

        elif state == 'obj_comma_or_end':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                pos += 1
                state = 'obj_key'
            elif s[pos] == '}':
                pos += 1
                result = stack.pop()[1]
                state = 'after_value'
            else:
                raise JSONError("expected , or }", pos)

        elif state == 'obj_key':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == '"':
                key = parse_string()
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("expected key", pos)

        elif state == 'obj_colon':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ':':
                pos += 1
                state = 'value'
            else:
                raise JSONError("expected :", pos)

        elif state == 'top_after':
            skip_ws()
            if pos < n:
                raise JSONError("trailing garbage", pos)
            return result
