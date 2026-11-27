class JSONError(ValueError):
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []  # frames: ('array', list) or ('object', dict, key)
    state = 'value'
    result = None
    top_done = False

    while True:
        # Skip whitespace
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1

        if pos >= n:
            if top_done:
                break
            raise JSONError("unexpected end of input", n)

        if top_done:
            raise JSONError("trailing garbage", pos)

        c = s[pos]

        if state == 'value' or state == 'obj_val' or state == 'arr_first':
            # Expecting a value (arr_first additionally allows ']')
            if state == 'arr_first' and c == ']':
                pos += 1
                _, arr = stack.pop()
                state = _commit(stack, arr)
                if state == 'done':
                    result = arr
                    top_done = True
            elif c == '"':
                value, pos = _parse_string(s, pos, n)
                state = _commit(stack, value)
                if state == 'done':
                    result = value
                    top_done = True
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                stack.append(('array', []))
                pos += 1
                state = 'arr_first'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                stack.append(('object', {}, None))
                pos += 1
                state = 'obj_first'
            elif c == '-' or '0' <= c <= '9':
                value, pos = _parse_number(s, pos, n)
                state = _commit(stack, value)
                if state == 'done':
                    result = value
                    top_done = True
            elif c == 't':
                pos = _match_literal(s, pos, n, 'true')
                state = _commit(stack, True)
                if state == 'done':
                    result = True
                    top_done = True
            elif c == 'f':
                pos = _match_literal(s, pos, n, 'false')
                state = _commit(stack, False)
                if state == 'done':
                    result = False
                    top_done = True
            elif c == 'n':
                pos = _match_literal(s, pos, n, 'null')
                state = _commit(stack, None)
                if state == 'done':
                    result = None
                    top_done = True
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'arr_comma':
            if c == ',':
                pos += 1
                state = 'value'
            elif c == ']':
                pos += 1
                _, arr = stack.pop()
                state = _commit(stack, arr)
                if state == 'done':
                    result = arr
                    top_done = True
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'obj_first':
            if c == '}':
                pos += 1
                _, obj, _ = stack.pop()
                state = _commit(stack, obj)
                if state == 'done':
                    result = obj
                    top_done = True
            elif c == '"':
                key, pos = _parse_string(s, pos, n)
                frame = stack[-1]
                stack[-1] = ('object', frame[1], key)
                state = 'obj_colon'
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'obj_colon':
            if c == ':':
                pos += 1
                state = 'obj_val'
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'obj_comma':
            if c == ',':
                pos += 1
                state = 'obj_key'
            elif c == '}':
                pos += 1
                _, obj, _ = stack.pop()
                state = _commit(stack, obj)
                if state == 'done':
                    result = obj
                    top_done = True
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'obj_key':
            if c == '"':
                key, pos = _parse_string(s, pos, n)
                frame = stack[-1]
                stack[-1] = ('object', frame[1], key)
                state = 'obj_colon'
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

    return result


def _commit(stack, value):
    if not stack:
        return 'done'
    top = stack[-1]
    if top[0] == 'array':
        top[1].append(value)
        return 'arr_comma'
    else:
        _, obj, key = top
        obj[key] = value
        return 'obj_comma'


def _match_literal(s, pos, n, literal):
    for i in range(len(literal)):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != literal[i]:
            raise JSONError("invalid literal", pos + i)
    return pos + len(literal)


def _parse_number(s, pos, n):
    start = pos

    # Optional minus
    if s[pos] == '-':
        pos += 1
        if pos >= n or not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit after '-'", pos)

    # Integer part
    if s[pos] == '0':
        pos += 1
        if pos < n and '0' <= s[pos] <= '9':
            raise JSONError("leading zero not allowed", pos)
    else:
        if not ('1' <= s[pos] <= '9'):
            raise JSONError("expected digit", pos)
        pos += 1
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    is_float = False

    # Fraction
    if pos < n and s[pos] == '.':
        is_float = True
        pos += 1
        if pos >= n or not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit after '.'", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    # Exponent
    if pos < n and (s[pos] == 'e' or s[pos] == 'E'):
        is_float = True
        pos += 1
        if pos < n and (s[pos] == '+' or s[pos] == '-'):
            pos += 1
        if pos >= n or not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit in exponent", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if is_float:
        return float(text), pos
    else:
        return int(text), pos


def _is_hex(c):
    return '0' <= c <= '9' or 'a' <= c <= 'f' or 'A' <= c <= 'F'


def _parse_string(s, pos, n):
    # s[pos] == '"'
    pos += 1
    parts = []

    while True:
        if pos >= n:
            raise JSONError("unterminated string", n)

        c = s[pos]

        if c == '"':
            pos += 1
            return ''.join(parts), pos
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unterminated escape sequence", n)
            ec = s[pos]
            if ec == '"':
                parts.append('"')
                pos += 1
            elif ec == '\\':
                parts.append('\\')
                pos += 1
            elif ec == '/':
                parts.append('/')
                pos += 1
            elif ec == 'b':
                parts.append('\b')
                pos += 1
            elif ec == 'f':
                parts.append('\f')
                pos += 1
            elif ec == 'n':
                parts.append('\n')
                pos += 1
            elif ec == 'r':
                parts.append('\r')
                pos += 1
            elif ec == 't':
                parts.append('\t')
                pos += 1
            elif ec == 'u':
                pos += 1
                if pos + 4 > n:
                    raise JSONError("incomplete \\u escape", n)
                h1, h2, h3, h4 = s[pos], s[pos+1], s[pos+2], s[pos+3]
                if not (_is_hex(h1) and _is_hex(h2) and _is_hex(h3) and _is_hex(h4)):
                    # Find the exact position of the bad hex digit
                    for i, hc in enumerate((h1, h2, h3, h4)):
                        if not _is_hex(hc):
                            raise JSONError("invalid hex digit in \\u escape", pos + i)
                    # Should not reach here
                    raise JSONError("invalid hex digit in \\u escape", pos)
                code = (
                    _hex_val(h1) * 4096 +
                    _hex_val(h2) * 256 +
                    _hex_val(h3) * 16 +
                    _hex_val(h4)
                )
                pos += 4

                # Check for surrogate pair
                if 0xD800 <= code <= 0xDBFF:
                    # High surrogate: check if immediately followed by \uXXXX low surrogate
                    if (pos + 6 <= n and s[pos] == '\\' and s[pos+1] == 'u'
                            and _is_hex(s[pos+2]) and _is_hex(s[pos+3])
                            and _is_hex(s[pos+4]) and _is_hex(s[pos+5])):
                        code2 = (
                            _hex_val(s[pos+2]) * 4096 +
                            _hex_val(s[pos+3]) * 256 +
                            _hex_val(s[pos+4]) * 16 +
                            _hex_val(s[pos+5])
                        )
                        if 0xDC00 <= code2 <= 0xDFFF:
                            combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            parts.append(chr(combined))
                            pos += 6
                            continue
                    # Lone high surrogate
                    parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError(f"invalid escape character {ec!r}", pos)
        elif ord(c) < 0x20:
            raise JSONError("control character in string", pos)
        else:
            parts.append(c)
            pos += 1


_HEX_TABLE = {}
for _i, _c in enumerate('0123456789abcdef'):
    _HEX_TABLE[_c] = _i
for _i, _c in enumerate('0123456789ABCDEF'):
    _HEX_TABLE[_c] = _i


def _hex_val(c):
    return _HEX_TABLE[c]