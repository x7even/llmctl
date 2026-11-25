class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []  # frames: ('a', list) or ('o', dict, key)
    state = 'value'
    result = None

    while True:
        # Skip whitespace
        while pos < n:
            c = s[pos]
            if c == ' ' or c == '\t' or c == '\n' or c == '\r':
                pos += 1
            else:
                break

        if state == 'done':
            if pos < n:
                raise JSONError(f"trailing garbage: {s[pos]!r}", pos)
            return result

        if pos >= n:
            raise JSONError("unexpected end of input", n)

        c = s[pos]

        if state == 'value':
            if c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(('a', []))
                state = 'arr_first'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(('o', {}, None))
                state = 'obj_first'
            elif c == '"':
                value, pos = _parse_string(s, pos, n)
                state, result = _place_value(value, stack)
            elif c == '-' or ('0' <= c <= '9'):
                value, pos = _parse_number(s, pos, n)
                state, result = _place_value(value, stack)
            elif c == 't':
                _check_literal(s, pos, n, 'true')
                pos += 4
                state, result = _place_value(True, stack)
            elif c == 'f':
                _check_literal(s, pos, n, 'false')
                pos += 5
                state, result = _place_value(False, stack)
            elif c == 'n':
                _check_literal(s, pos, n, 'null')
                pos += 4
                state, result = _place_value(None, stack)
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'arr_first':
            if c == ']':
                pos += 1
                value = stack.pop()[1]
                state, result = _place_value(value, stack)
            else:
                state = 'value'
                continue

        elif state == 'arr_sep':
            if c == ',':
                pos += 1
                state = 'value'
            elif c == ']':
                pos += 1
                value = stack.pop()[1]
                state, result = _place_value(value, stack)
            else:
                raise JSONError(f"expected ',' or ']', got {c!r}", pos)

        elif state == 'obj_first':
            if c == '}':
                pos += 1
                value = stack.pop()[1]
                state, result = _place_value(value, stack)
            elif c == '"':
                key, pos = _parse_string(s, pos, n)
                stack[-1] = ('o', stack[-1][1], key)
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
            if c == ',':
                pos += 1
                state = 'obj_key'
            elif c == '}':
                pos += 1
                value = stack.pop()[1]
                state, result = _place_value(value, stack)
            else:
                raise JSONError(f"expected ',' or '}}', got {c!r}", pos)

        elif state == 'obj_key':
            if c == '"':
                key, pos = _parse_string(s, pos, n)
                stack[-1] = ('o', stack[-1][1], key)
                state = 'obj_colon'
            else:
                raise JSONError(f"expected string key, got {c!r}", pos)


def _place_value(value, stack):
    if not stack:
        return 'done', value
    frame = stack[-1]
    if frame[0] == 'a':
        frame[1].append(value)
        return 'arr_sep', None
    else:
        frame[1][frame[2]] = value
        return 'obj_sep', None


def _check_literal(s, pos, n, expected):
    for i in range(len(expected)):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != expected[i]:
            raise JSONError(f"invalid literal, expected {expected!r}", pos + i)


def _parse_string(s, pos, n):
    pos += 1  # skip opening quote
    chars = []

    while pos < n:
        c = s[pos]
        if c == '"':
            pos += 1
            return ''.join(chars), pos
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
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
                code, pos = _parse_unicode_escape(s, pos, n)
                if 0xD800 <= code <= 0xDBFF:
                    if pos + 5 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                        hex_ok = True
                        for j in range(4):
                            if not _is_hex(s[pos + 2 + j]):
                                hex_ok = False
                                break
                        if hex_ok:
                            code2 = _hex4(s, pos + 2)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                code = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                pos += 5
                chars.append(chr(code))
            else:
                raise JSONError(f"invalid escape character {ec!r}", pos)
        else:
            if ord(c) < 0x20:
                raise JSONError("unescaped control character in string", pos)
            chars.append(c)
            pos += 1

    raise JSONError("unexpected end of input", n)


def _is_hex(c):
    o = ord(c)
    return (48 <= o <= 57) or (97 <= o <= 102) or (65 <= o <= 70)


def _hex4(s, pos):
    v = 0
    for i in range(4):
        o = ord(s[pos + i])
        if 48 <= o <= 57:
            d = o - 48
        elif 97 <= o <= 102:
            d = o - 87
        else:
            d = o - 55
        v = (v << 4) | d
    return v


def _parse_unicode_escape(s, pos, n):
    # pos points to 'u' in \uXXXX
    if pos + 5 > n:
        raise JSONError("unexpected end of input", n)
    for i in range(4):
        if not _is_hex(s[pos + 1 + i]):
            raise JSONError(f"invalid hex digit in \\u escape", pos + 1 + i)
    code = _hex4(s, pos + 1)
    return code, pos + 5


def _parse_number(s, pos, n):
    start = pos
    is_float = False

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
        raise JSONError(f"expected digit, got {c!r}", pos)

    if pos < n and s[pos] == '.':
        is_float = True
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError(f"expected digit after '.', got {s[pos]!r}", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    if pos < n and (s[pos] == 'e' or s[pos] == 'E'):
        is_float = True
        pos += 1
        if pos < n and (s[pos] == '+' or s[pos] == '-'):
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError(f"expected digit in exponent, got {s[pos]!r}", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if is_float:
        return float(text), pos
    else:
        return int(text), pos