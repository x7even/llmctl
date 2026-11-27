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
    stack = []  # each element: [kind, container, extra]
    # kind: 'array' | 'object'
    # container: list | dict
    # extra: current key (str|None) for objects, None for arrays

    state = 'value'
    result = None

    _WS = ' \t\n\r'
    _HEX = frozenset('0123456789abcdefABCDEF')

    def _err(msg, p):
        raise JSONError(msg, p)

    def _skip_ws():
        nonlocal pos
        while pos < n and s[pos] in _WS:
            pos += 1

    def _after_value():
        nonlocal state
        if not stack:
            state = 'end'
        elif stack[-1][0] == 'array':
            stack[-1][1].append(result)
            state = 'comma_or_end_array'
        else:
            d = stack[-1][1]
            key = stack[-1][2]
            d[key] = result
            stack[-1][2] = None
            state = 'comma_or_end_object'

    def _parse_string():
        nonlocal pos
        pos += 1  # skip opening quote
        chars = []
        while True:
            if pos >= n:
                _err("unexpected end of input in string", pos)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            if c == '\\':
                pos += 1
                if pos >= n:
                    _err("unexpected end of input in string escape", pos)
                ec = s[pos]
                if ec == '"':
                    chars.append('"')
                    pos += 1
                elif ec == '\\':
                    chars.append('\\')
                    pos += 1
                elif ec == '/':
                    chars.append('/')
                    pos += 1
                elif ec == 'b':
                    chars.append('\b')
                    pos += 1
                elif ec == 'f':
                    chars.append('\f')
                    pos += 1
                elif ec == 'n':
                    chars.append('\n')
                    pos += 1
                elif ec == 'r':
                    chars.append('\r')
                    pos += 1
                elif ec == 't':
                    chars.append('\t')
                    pos += 1
                elif ec == 'u':
                    pos += 1
                    hs = pos
                    if pos + 4 > n:
                        _err("truncated \\u escape", pos)
                    for i in range(4):
                        if s[pos + i] not in _HEX:
                            _err("invalid hex digit in \\u escape", pos + i)
                    code = int(s[hs:hs + 4], 16)
                    pos = hs + 4
                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                                and s[pos + 2] in _HEX and s[pos + 3] in _HEX
                                and s[pos + 4] in _HEX and s[pos + 5] in _HEX):
                            lo = int(s[pos + 2:pos + 6], 16)
                            if 0xDC00 <= lo <= 0xDFFF:
                                cp = 0x10000 + ((code - 0xD800) << 10) + (lo - 0xDC00)
                                chars.append(chr(cp))
                                pos += 6
                            else:
                                chars.append(chr(code))
                        else:
                            chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    _err("invalid escape character", pos)
            elif ord(c) < 0x20:
                _err("unescaped control character in string", pos)
            else:
                chars.append(c)
                pos += 1

    def _parse_number():
        nonlocal pos
        start = pos
        if s[pos] == '-':
            pos += 1
        if pos >= n:
            _err("unexpected end of input in number", pos)
        if s[pos] == '0':
            pos += 1
        elif '1' <= s[pos] <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            _err("invalid digit in number", pos)

        is_float = False
        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                _err("expected digit after decimal point", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                _err("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def _parse_literal(expected, value):
        nonlocal pos
        for i, ch in enumerate(expected):
            idx = pos + i
            if idx >= n:
                _err("unexpected end of input in literal", n)
            if s[idx] != ch:
                _err("invalid literal", idx)
        pos += len(expected)
        return value

    # Main iterative loop
    while True:
        _skip_ws()

        if state == 'end':
            if pos < n:
                _err("trailing characters after JSON value", pos)
            return result

        if pos >= n:
            _err("unexpected end of input", pos)

        c = s[pos]

        if state == 'value' or state == 'value_or_end_array':
            if state == 'value_or_end_array' and c == ']':
                pos += 1
                _, lst, _ = stack.pop()
                result = lst
                _after_value()
                continue

            if c == '[':
                if len(stack) >= 500:
                    _err("nesting too deep", pos)
                pos += 1
                stack.append(['array', [], None])
                state = 'value_or_end_array'
            elif c == '{':
                if len(stack) >= 500:
                    _err("nesting too deep", pos)
                pos += 1
                stack.append(['object', {}, None])
                state = 'key_or_end'
            elif c == '"':
                result = _parse_string()
                _after_value()
            elif c == 't':
                result = _parse_literal('true', True)
                _after_value()
            elif c == 'f':
                result = _parse_literal('false', False)
                _after_value()
            elif c == 'n':
                result = _parse_literal('null', None)
                _after_value()
            elif c == '-' or '0' <= c <= '9':
                result = _parse_number()
                _after_value()
            else:
                _err(f"unexpected character {c!r}", pos)

        elif state == 'key_or_end':
            if c == '}':
                pos += 1
                _, d, _ = stack.pop()
                result = d
                _after_value()
            elif c == '"':
                key = _parse_string()
                stack[-1][2] = key
                state = 'colon'
            else:
                _err("expected string key or '}'", pos)

        elif state == 'key':
            if c == '"':
                key = _parse_string()
                stack[-1][2] = key
                state = 'colon'
            else:
                _err("expected string key", pos)

        elif state == 'colon':
            if c == ':':
                pos += 1
                state = 'value'
            else:
                _err("expected ':'", pos)

        elif state == 'comma_or_end_array':
            if c == ']':
                pos += 1
                _, lst, _ = stack.pop()
                result = lst
                _after_value()
            elif c == ',':
                pos += 1
                state = 'value'
            else:
                _err("expected ',' or ']' in array", pos)

        elif state == 'comma_or_end_object':
            if c == '}':
                pos += 1
                _, d, _ = stack.pop()
                result = d
                _after_value()
            elif c == ',':
                pos += 1
                state = 'key'
            else:
                _err("expected ',' or '}' in object", pos)
