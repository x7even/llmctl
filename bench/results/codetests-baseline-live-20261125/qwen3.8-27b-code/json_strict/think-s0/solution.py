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
    stack = []  # frames: [type, container, pending_key]
    state = 'value'
    result = None

    while True:
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1

        if pos >= n:
            raise JSONError("unexpected end of input", pos)

        c = s[pos]

        if state == 'value' or state == 'value_or_arr_end':
            if c == ']' and state == 'value_or_arr_end':
                pos += 1
                state, result = _after_close(stack)
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("nesting too deep", pos)
                pos += 1
                stack.append(['object', {}, None])
                state = 'key_or_obj_end'
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("nesting too deep", pos)
                pos += 1
                stack.append(['array', [], None])
                state = 'value_or_arr_end'
            elif c == '"':
                value, pos = _parse_string(s, pos, n)
                state, result = _after_value(value, stack)
            elif c == 't':
                value, pos = _parse_literal(s, pos, n, 'true')
                state, result = _after_value(value, stack)
            elif c == 'f':
                value, pos = _parse_literal(s, pos, n, 'false')
                state, result = _after_value(value, stack)
            elif c == 'n':
                value, pos = _parse_literal(s, pos, n, 'null')
                state, result = _after_value(value, stack)
            elif c == '-' or ('0' <= c <= '9'):
                value, pos = _parse_number(s, pos, n)
                state, result = _after_value(value, stack)
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'key_or_obj_end':
            if c == '}':
                pos += 1
                state, result = _after_close(stack)
            elif c == '"':
                key, pos = _parse_string(s, pos, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("expected string key or '}'", pos)

        elif state == 'obj_key':
            if c == '"':
                key, pos = _parse_string(s, pos, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("expected string key", pos)

        elif state == 'arr_sep':
            if c == ',':
                pos += 1
                state = 'value'
            elif c == ']':
                pos += 1
                state, result = _after_close(stack)
            else:
                raise JSONError("expected ',' or ']'", pos)

        elif state == 'obj_colon':
            if c == ':':
                pos += 1
                state = 'value'
            else:
                raise JSONError("expected ':'", pos)

        elif state == 'obj_sep':
            if c == ',':
                pos += 1
                state = 'obj_key'
            elif c == '}':
                pos += 1
                state, result = _after_close(stack)
            else:
                raise JSONError("expected ',' or '}'", pos)

        if state == 'done':
            break

    while pos < n and s[pos] in ' \t\n\r':
        pos += 1
    if pos < n:
        raise JSONError("trailing garbage", pos)

    return result


def _after_value(value, stack):
    if not stack:
        return 'done', value
    frame = stack[-1]
    if frame[0] == 'array':
        frame[1].append(value)
        return 'arr_sep', None
    else:
        frame[1][frame[2]] = value
        frame[2] = None
        return 'obj_sep', None


def _after_close(stack):
    frame = stack.pop()
    value = frame[1]
    if not stack:
        return 'done', value
    parent = stack[-1]
    if parent[0] == 'array':
        parent[1].append(value)
        return 'arr_sep', None
    else:
        parent[1][parent[2]] = value
        parent[2] = None
        return 'obj_sep', None


def _parse_string(s, pos, n):
    pos += 1  # skip opening quote
    chars = []
    hex_digits = '0123456789abcdefABCDEF'

    while True:
        if pos >= n:
            raise JSONError("unexpected end of input", pos)

        c = s[pos]

        if c == '"':
            pos += 1
            return ''.join(chars), pos
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            esc = s[pos]
            if esc == '"':
                chars.append('"')
                pos += 1
            elif esc == '\\':
                chars.append('\\')
                pos += 1
            elif esc == '/':
                chars.append('/')
                pos += 1
            elif esc == 'b':
                chars.append('\b')
                pos += 1
            elif esc == 'f':
                chars.append('\f')
                pos += 1
            elif esc == 'n':
                chars.append('\n')
                pos += 1
            elif esc == 'r':
                chars.append('\r')
                pos += 1
            elif esc == 't':
                chars.append('\t')
                pos += 1
            elif esc == 'u':
                pos += 1
                if pos + 4 > n:
                    raise JSONError("unexpected end of input", pos)
                hex_str = s[pos:pos + 4]
                for hc in hex_str:
                    if hc not in hex_digits:
                        raise JSONError("invalid unicode escape", pos)
                code = int(hex_str, 16)
                pos += 4

                if 0xD800 <= code <= 0xDBFF:
                    if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                            and all(hc in hex_digits for hc in s[pos + 2:pos + 6])):
                        code2 = int(s[pos + 2:pos + 6], 16)
                        if 0xDC00 <= code2 <= 0xDFFF:
                            combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            chars.append(chr(combined))
                            pos += 6
                            continue
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError(f"invalid escape character {esc!r}", pos)
        elif ord(c) < 0x20:
            raise JSONError("control character in string", pos)
        else:
            chars.append(c)
            pos += 1


def _parse_number(s, pos, n):
    start = pos

    if s[pos] == '-':
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", pos)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("invalid number", pos)

    if s[pos] == '0':
        pos += 1
    else:
        pos += 1
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    is_float = False

    if pos < n and s[pos] == '.':
        is_float = True
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", pos)
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
            raise JSONError("unexpected end of input", pos)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("invalid number", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if is_float:
        return float(text), pos
    else:
        return int(text), pos


def _parse_literal(s, pos, n, expected):
    for i in range(len(expected)):
        if pos + i >= n or s[pos + i] != expected[i]:
            if pos + i >= n:
                raise JSONError("unexpected end of input", pos + i)
            raise JSONError("invalid literal", pos + i)
    pos += len(expected)
    if expected == 'true':
        return True, pos
    elif expected == 'false':
        return False, pos
    else:
        return None, pos