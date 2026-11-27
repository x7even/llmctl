class JSONError(ValueError):
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_HEX_CHARS = frozenset('0123456789abcdefABCDEF')


def _hex_val(ch):
    o = ord(ch)
    if 48 <= o <= 57:
        return o - 48
    elif 97 <= o <= 102:
        return o - 87
    else:
        return o - 55


def _parse_hex4(s, pos, n):
    if pos + 4 > n:
        raise JSONError("unexpected end of input", n)
    v = 0
    for j in range(4):
        ch = s[pos + j]
        if ch not in _HEX_CHARS:
            raise JSONError("invalid hex digit in \\u escape", pos + j)
        v = v * 16 + _hex_val(ch)
    return v, pos + 4


def _parse_string(s, pos, n):
    parts = []
    while True:
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        c = s[pos]
        if c == '"':
            pos += 1
            return ''.join(parts), pos
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
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
                pos += 1
                code, pos = _parse_hex4(s, pos, n)
                if 0xD800 <= code <= 0xDBFF:
                    if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                        hex_ok = True
                        for j in range(4):
                            if s[pos + 2 + j] not in _HEX_CHARS:
                                hex_ok = False
                                break
                        if hex_ok:
                            code2 = 0
                            for j in range(4):
                                code2 = code2 * 16 + _hex_val(s[pos + 2 + j])
                            if 0xDC00 <= code2 <= 0xDFFF:
                                cp = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                parts.append(chr(cp))
                                pos += 10
                                continue
                    parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError("invalid escape", pos)
        elif ord(c) < 0x20:
            raise JSONError("control character in string", pos)
        else:
            parts.append(c)
            pos += 1


def _parse_number(s, pos, n):
    start = pos
    if s[pos] == '-':
        pos += 1
    if pos >= n:
        raise JSONError("unexpected end of input", n)
    c = s[pos]
    if c == '0':
        pos += 1
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
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("invalid number", pos)
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
            raise JSONError("invalid number", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if is_float:
        return float(text), pos
    else:
        return int(text), pos


def _parse_literal(s, pos, n, expected, value):
    for j in range(len(expected)):
        if pos + j < n:
            if s[pos + j] != expected[j]:
                raise JSONError("invalid literal", pos + j)
        else:
            raise JSONError("unexpected end of input", n)
    return value, pos + len(expected)


def _next_state(stack):
    if not stack:
        return 'end'
    if stack[-1][0] == 'a':
        return 'arr_sep'
    return 'obj_sep'


def _store(stack, value):
    if not stack:
        return
    frame = stack[-1]
    if frame[0] == 'a':
        frame[1].append(value)
    else:
        frame[1][frame[2]] = value
        frame[2] = None


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, not {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []
    state = 'value'
    result = None

    while True:
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1

        if state == 'end':
            if pos < n:
                raise JSONError("trailing characters", pos)
            return result

        if pos >= n:
            raise JSONError("unexpected end of input", pos)

        c = s[pos]

        if state == 'value' or state == 'arr_first':
            if state == 'arr_first' and c == ']':
                pos += 1
                result = stack.pop()[1]
                _store(stack, result)
                state = _next_state(stack)
                continue

            if c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['o', {}, None])
                state = 'obj_key'
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['a', [], None])
                state = 'arr_first'
            elif c == '"':
                pos += 1
                result, pos = _parse_string(s, pos, n)
                _store(stack, result)
                state = _next_state(stack)
            elif c == 't':
                result, pos = _parse_literal(s, pos, n, 'true', True)
                _store(stack, result)
                state = _next_state(stack)
            elif c == 'f':
                result, pos = _parse_literal(s, pos, n, 'false', False)
                _store(stack, result)
                state = _next_state(stack)
            elif c == 'n':
                result, pos = _parse_literal(s, pos, n, 'null', None)
                _store(stack, result)
                state = _next_state(stack)
            elif c == '-' or '0' <= c <= '9':
                result, pos = _parse_number(s, pos, n)
                _store(stack, result)
                state = _next_state(stack)
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'arr_sep':
            if c == ']':
                pos += 1
                result = stack.pop()[1]
                _store(stack, result)
                state = _next_state(stack)
            elif c == ',':
                pos += 1
                state = 'value'
            else:
                raise JSONError(f"expected ',' or ']', got {c!r}", pos)

        elif state == 'obj_key':
            if c == '}':
                pos += 1
                result = stack.pop()[1]
                _store(stack, result)
                state = _next_state(stack)
            elif c == '"':
                pos += 1
                key, pos = _parse_string(s, pos, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError(f"expected string key or '}}', got {c!r}", pos)

        elif state == 'obj_colon':
            if c == ':':
                pos += 1
                state = 'value'
            else:
                raise JSONError(f"expected ':', got {c!r}", pos)

        elif state == 'obj_sep':
            if c == '}':
                pos += 1
                result = stack.pop()[1]
                _store(stack, result)
                state = _next_state(stack)
            elif c == ',':
                pos += 1
                state = 'obj_key'
            else:
                raise JSONError(f"expected ',' or '}}', got {c!r}", pos)
