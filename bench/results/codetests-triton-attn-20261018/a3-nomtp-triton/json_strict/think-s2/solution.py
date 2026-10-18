import re


class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_WS = ' \t\n\r'
_HEX = frozenset('0123456789abcdefABCDEF')


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []  # each entry: [type, container, pending_key]
    state = 'value'
    result = None

    while True:
        # Skip whitespace
        while pos < n and s[pos] in _WS:
            pos += 1

        if state == 'value':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                stack.append(['array', [], None])
                pos += 1
                state = 'array_first'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                stack.append(['object', {}, None])
                pos += 1
                state = 'object_first'
            elif c == '"':
                value, pos = _parse_string(s, pos)
                state, result = _place(value, stack, result)
            elif c == 't' or c == 'f' or c == 'n':
                value, pos = _parse_literal(s, pos)
                state, result = _place(value, stack, result)
            elif c == '-' or ('0' <= c <= '9'):
                value, pos = _parse_number(s, pos)
                state, result = _place(value, stack, result)
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif state == 'array_first':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] == ']':
                pos += 1
                state, result = _close(stack, result)
            else:
                state = 'value'

        elif state == 'array_comma_or_end':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] == ',':
                pos += 1
                state = 'value'
            elif s[pos] == ']':
                pos += 1
                state, result = _close(stack, result)
            else:
                raise JSONError(f"expected ',' or ']', got {s[pos]!r}", pos)

        elif state == 'object_first':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] == '}':
                pos += 1
                state, result = _close(stack, result)
            elif s[pos] == '"':
                key, pos = _parse_string(s, pos)
                stack[-1][2] = key
                state = 'object_colon'
            else:
                raise JSONError(f"expected string key or '}}', got {s[pos]!r}", pos)

        elif state == 'object_colon':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] == ':':
                pos += 1
                state = 'value'
            else:
                raise JSONError(f"expected ':', got {s[pos]!r}", pos)

        elif state == 'object_comma_or_end':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] == ',':
                pos += 1
                state = 'object_next_key'
            elif s[pos] == '}':
                pos += 1
                state, result = _close(stack, result)
            else:
                raise JSONError(f"expected ',' or '}}', got {s[pos]!r}", pos)

        elif state == 'object_next_key':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] == '"':
                key, pos = _parse_string(s, pos)
                stack[-1][2] = key
                state = 'object_colon'
            else:
                raise JSONError(f"expected string key, got {s[pos]!r}", pos)

        elif state == 'done':
            if pos < n:
                raise JSONError("trailing garbage", pos)
            break

    return result


def _place(value, stack, result):
    if not stack:
        return 'done', value
    frame = stack[-1]
    if frame[0] == 'array':
        frame[1].append(value)
        return 'array_comma_or_end', result
    else:
        frame[1][frame[2]] = value
        return 'object_comma_or_end', result


def _close(stack, result):
    frame = stack.pop()
    value = frame[1]
    return _place(value, stack, result)


def _parse_string(s, pos):
    n = len(s)
    pos += 1  # skip opening quote
    chars = []

    while True:
        if pos >= n:
            raise JSONError("unexpected end of input in string", pos)

        c = s[pos]

        if c == '"':
            pos += 1
            return ''.join(chars), pos
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in string escape", pos)
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
                # Validate exactly 4 ASCII hex digits
                for i in range(4):
                    if pos + i >= n:
                        raise JSONError("unexpected end of input in \\u escape", pos + i)
                    if s[pos + i] not in _HEX:
                        raise JSONError(f"invalid hex digit in \\u escape: {s[pos+i]!r}", pos + i)
                code = int(s[pos:pos + 4], 16)
                pos += 4

                if 0xD800 <= code <= 0xDBFF:
                    # High surrogate: check for immediately following \uXXXX low surrogate
                    if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                        hex2 = s[pos + 2:pos + 6]
                        valid = True
                        for h in hex2:
                            if h not in _HEX:
                                valid = False
                                break
                        if valid:
                            code2 = int(hex2, 16)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(combined))
                                pos += 6
                                continue
                    # Unpaired high surrogate
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError(f"invalid escape character {esc!r}", pos)
        elif ord(c) < 0x20:
            raise JSONError(f"unescaped control character in string", pos)
        else:
            chars.append(c)
            pos += 1


def _parse_number(s, pos):
    n = len(s)
    start = pos

    # Optional minus
    if pos < n and s[pos] == '-':
        pos += 1

    # Integer part
    if pos >= n:
        raise JSONError("unexpected end of input", pos)

    if s[pos] == '0':
        pos += 1
        if pos < n and '0' <= s[pos] <= '9':
            raise JSONError("leading zero not allowed", pos)
    elif '1' <= s[pos] <= '9':
        pos += 1
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    else:
        raise JSONError(f"expected digit, got {s[pos]!r}", pos)

    is_float = False

    # Fraction part
    if pos < n and s[pos] == '.':
        is_float = True
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", pos)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError(f"expected digit after '.', got {s[pos]!r}", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    # Exponent part
    if pos < n and s[pos] in 'eE':
        is_float = True
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", pos)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError(f"expected digit in exponent, got {s[pos]!r}", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if is_float:
        return float(text), pos
    else:
        return int(text), pos


def _parse_literal(s, pos):
    n = len(s)
    c = s[pos]
    if c == 't':
        literal = 'true'
    elif c == 'f':
        literal = 'false'
    else:  # c == 'n'
        literal = 'null'

    ln = len(literal)
    for i in range(ln):
        if pos + i >= n or s[pos + i] != literal[i]:
            raise JSONError(f"invalid literal, expected {literal!r}", pos + i)

    pos += ln
    if c == 't':
        return True, pos
    elif c == 'f':
        return False, pos
    else:
        return None, pos
