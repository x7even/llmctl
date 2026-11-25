"""Strict RFC 8259 JSON parser (hand-written, no json/ast/eval)."""


class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_WS = ' \t\n\r'
_HEX = frozenset('0123456789abcdefABCDEF')
_CONTAINER = object()  # sentinel


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []  # frames: [type, container, state, key]
    # type: 'a' | 'o'
    # array states:  0=expect_val_or_close, 1=expect_comma_or_close, 2=expect_val_after_comma
    # object states: 0=expect_key_or_close, 1=expect_colon, 2=expect_value,
    #                3=expect_comma_or_close, 4=expect_key_after_comma
    result = None

    while True:
        while pos < n and s[pos] in _WS:
            pos += 1

        if pos >= n:
            raise JSONError("unexpected end of input", pos)

        c = s[pos]

        if not stack:
            # ---- top level: expect a value ----
            if c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                stack.append(['o', {}, 0, None])
                pos += 1
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                stack.append(['a', [], 0, None])
                pos += 1
            elif c == '"':
                result, pos = _parse_string(s, pos, n)
                break
            elif c == 't':
                result, pos = _parse_literal(s, pos, n, 'true', True)
                break
            elif c == 'f':
                result, pos = _parse_literal(s, pos, n, 'false', False)
                break
            elif c == 'n':
                result, pos = _parse_literal(s, pos, n, 'null', None)
                break
            elif c == '-' or '0' <= c <= '9':
                result, pos = _parse_number(s, pos, n)
                break
            else:
                raise JSONError(f"unexpected character {c!r}", pos)
        else:
            ftype, container, state, key = stack[-1]

            if ftype == 'a':
                if state == 0:  # expect value or ]
                    if c == ']':
                        pos += 1
                        stack.pop()
                        result = container
                        if not stack:
                            break
                        _complete_in_parent(stack, result)
                    else:
                        val, pos = _try_parse_value(s, pos, n, stack)
                        if val is _CONTAINER:
                            continue
                        container.append(val)
                        stack[-1][2] = 1
                elif state == 1:  # expect comma or ]
                    if c == ',':
                        pos += 1
                        stack[-1][2] = 2
                    elif c == ']':
                        pos += 1
                        stack.pop()
                        result = container
                        if not stack:
                            break
                        _complete_in_parent(stack, result)
                    else:
                        raise JSONError(f"expected ',' or ']', got {c!r}", pos)
                else:  # state == 2: expect value after comma
                    val, pos = _try_parse_value(s, pos, n, stack)
                    if val is _CONTAINER:
                        continue
                    container.append(val)
                    stack[-1][2] = 1

            elif ftype == 'o':
                if state == 0:  # expect key or }
                    if c == '}':
                        pos += 1
                        stack.pop()
                        result = container
                        if not stack:
                            break
                        _complete_in_parent(stack, result)
                    elif c == '"':
                        key, pos = _parse_string(s, pos, n)
                        stack[-1][2] = 1
                        stack[-1][3] = key
                    else:
                        raise JSONError(f"expected string key or '}}', got {c!r}", pos)
                elif state == 1:  # expect colon
                    if c == ':':
                        pos += 1
                        stack[-1][2] = 2
                    else:
                        raise JSONError(f"expected ':', got {c!r}", pos)
                elif state == 2:  # expect value
                    val, pos = _try_parse_value(s, pos, n, stack)
                    if val is _CONTAINER:
                        continue
                    container[key] = val
                    stack[-1][2] = 3
                elif state == 3:  # expect comma or }
                    if c == ',':
                        pos += 1
                        stack[-1][2] = 4
                    elif c == '}':
                        pos += 1
                        stack.pop()
                        result = container
                        if not stack:
                            break
                        _complete_in_parent(stack, result)
                    else:
                        raise JSONError(f"expected ',' or '}}', got {c!r}", pos)
                else:  # state == 4: expect key after comma
                    if c == '"':
                        key, pos = _parse_string(s, pos, n)
                        stack[-1][2] = 1
                        stack[-1][3] = key
                    else:
                        raise JSONError(f"expected string key, got {c!r}", pos)

    # trailing garbage check
    while pos < n and s[pos] in _WS:
        pos += 1
    if pos < n:
        raise JSONError("trailing garbage", pos)

    return result


def _complete_in_parent(stack, value):
    ftype, container, state, key = stack[-1]
    if ftype == 'a':
        container.append(value)
        stack[-1][2] = 1
    else:
        container[key] = value
        stack[-1][2] = 3


def _try_parse_value(s, pos, n, stack):
    c = s[pos]
    if c == '{':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", pos)
        stack.append(['o', {}, 0, None])
        return _CONTAINER, pos + 1
    if c == '[':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", pos)
        stack.append(['a', [], 0, None])
        return _CONTAINER, pos + 1
    if c == '"':
        return _parse_string(s, pos, n)
    if c == 't':
        return _parse_literal(s, pos, n, 'true', True)
    if c == 'f':
        return _parse_literal(s, pos, n, 'false', False)
    if c == 'n':
        return _parse_literal(s, pos, n, 'null', None)
    if c == '-' or '0' <= c <= '9':
        return _parse_number(s, pos, n)
    raise JSONError(f"unexpected character {c!r}", pos)


def _parse_literal(s, pos, n, expected, value):
    for i in range(len(expected)):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != expected[i]:
            raise JSONError(f"invalid literal", pos + i)
    return value, pos + len(expected)


def _parse_number(s, pos, n):
    start = pos
    is_float = False

    if pos < n and s[pos] == '-':
        pos += 1

    if pos >= n:
        raise JSONError("unexpected end in number", pos)

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
        raise JSONError(f"invalid number, expected digit, got {c!r}", pos)

    if pos < n and s[pos] == '.':
        is_float = True
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end in number (expected digit after '.')", pos)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError(f"expected digit after '.', got {s[pos]!r}", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    if pos < n and s[pos] in 'eE':
        is_float = True
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end in number (expected digit in exponent)", pos)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError(f"expected digit in exponent, got {s[pos]!r}", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if is_float:
        return float(text), pos
    return int(text), pos


def _parse_string(s, pos, n):
    # s[pos] == '"'
    pos += 1
    chars = []

    while pos < n:
        c = s[pos]

        if c == '"':
            pos += 1
            return ''.join(chars), pos

        if c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in escape", pos)
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
                hex_start = pos + 1
                if hex_start + 4 > n:
                    raise JSONError("unexpected end of input in \\u escape", n)
                for i in range(4):
                    if s[hex_start + i] not in _HEX:
                        raise JSONError(f"invalid hex digit in \\u escape", hex_start + i)
                code = int(s[hex_start:hex_start + 4], 16)
                pos = hex_start + 4 + 1  # past the 4 hex digits

                # Surrogate pair check
                if 0xD800 <= code <= 0xDBFF:
                    if pos + 4 < n and s[pos] == '\\' and s[pos + 1] == 'u':
                        h2 = pos + 2
                        if h2 + 4 <= n:
                            valid = True
                            for i in range(4):
                                if s[h2 + i] not in _HEX:
                                    valid = False
                                    break
                            if valid:
                                code2 = int(s[h2:h2 + 4], 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    chars.append(chr(combined))
                                    pos = h2 + 4 + 1
                                    continue
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError(f"invalid escape sequence \\{esc}", pos)
        elif ord(c) < 0x20:
            raise JSONError(f"unescaped control character in string", pos)
        else:
            chars.append(c)
            pos += 1

    raise JSONError("unterminated string", pos)