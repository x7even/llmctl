class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_NOTHING = object()
_WS = ' \t\n\r'
_HEX_CHARS = frozenset('0123456789abcdefABCDEF')


def _hex_val(ch):
    if '0' <= ch <= '9':
        return ord(ch) - 48
    elif 'a' <= ch <= 'f':
        return ord(ch) - 87
    elif 'A' <= ch <= 'F':
        return ord(ch) - 55
    return -1


def _parse_literal(s, pos, n, literal, value):
    ln = len(literal)
    for i in range(ln):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != literal[i]:
            raise JSONError("invalid literal", pos + i)
    return (value, pos + ln)


def _parse_number(s, pos, n):
    start = pos
    is_float = False

    if s[pos] == '-':
        pos += 1

    if pos >= n:
        raise JSONError("unexpected end of input", pos)

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
        return (float(text), pos)
    else:
        return (int(text), pos)


def _parse_string(s, pos, n):
    pos += 1  # skip opening quote
    chars = []

    while True:
        if pos >= n:
            raise JSONError("unexpected end of input in string", n)

        c = s[pos]

        if c == '"':
            pos += 1
            return (''.join(chars), pos)

        if c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in string escape", n)

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
                    raise JSONError("unexpected end of input in \\u escape", n)

                code = 0
                for i in range(4):
                    ch = s[pos + i]
                    v = _hex_val(ch)
                    if v < 0:
                        raise JSONError("invalid hex digit in \\u escape", pos + i)
                    code = code * 16 + v

                pos += 4

                if 0xD800 <= code <= 0xDBFF:
                    # High surrogate: check for immediately following \uXXXX low surrogate
                    if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                        lo_code = 0
                        valid = True
                        for i in range(4):
                            ch = s[pos + 2 + i]
                            v = _hex_val(ch)
                            if v < 0:
                                valid = False
                                break
                            lo_code = lo_code * 16 + v

                        if valid and 0xDC00 <= lo_code <= 0xDFFF:
                            combined = 0x10000 + ((code - 0xD800) << 10) + (lo_code - 0xDC00)
                            chars.append(chr(combined))
                            pos += 6
                        else:
                            chars.append(chr(code))
                    else:
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


def _parse_value(s, pos, n, stack):
    c = s[pos]

    if c == '"':
        return _parse_string(s, pos, n)
    elif c == '[':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", pos)
        pos += 1
        stack.append(['a', [], 0, None])
        return (_NOTHING, pos)
    elif c == '{':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", pos)
        pos += 1
        stack.append(['o', {}, 0, None])
        return (_NOTHING, pos)
    elif c == 't':
        return _parse_literal(s, pos, n, 'true', True)
    elif c == 'f':
        return _parse_literal(s, pos, n, 'false', False)
    elif c == 'n':
        return _parse_literal(s, pos, n, 'null', None)
    elif c == '-' or '0' <= c <= '9':
        return _parse_number(s, pos, n)
    else:
        raise JSONError(f"unexpected character {c!r}", pos)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []
    to_place = _NOTHING

    while True:
        # Place pending value into current container (or return if top-level)
        if to_place is not _NOTHING:
            if not stack:
                while pos < n and s[pos] in _WS:
                    pos += 1
                if pos != n:
                    raise JSONError("trailing characters after JSON value", pos)
                return to_place
            else:
                frame = stack[-1]
                if frame[0] == 'a':
                    frame[1].append(to_place)
                    frame[2] = 1
                else:
                    frame[1][frame[3]] = to_place
                    frame[2] = 3
                to_place = _NOTHING
                continue

        # Skip whitespace
        while pos < n and s[pos] in _WS:
            pos += 1

        if pos >= n:
            raise JSONError("unexpected end of input", pos)

        c = s[pos]

        if not stack:
            value, pos = _parse_value(s, pos, n, stack)
            to_place = value
        else:
            frame = stack[-1]
            kind = frame[0]
            state = frame[2]

            if kind == 'a':
                if state == 0:
                    if c == ']':
                        to_place = frame[1]
                        stack.pop()
                        pos += 1
                    else:
                        value, pos = _parse_value(s, pos, n, stack)
                        to_place = value
                elif state == 1:
                    if c == ']':
                        to_place = frame[1]
                        stack.pop()
                        pos += 1
                    elif c == ',':
                        pos += 1
                        frame[2] = 2
                    else:
                        raise JSONError(f"expected ',' or ']', got {c!r}", pos)
                elif state == 2:
                    value, pos = _parse_value(s, pos, n, stack)
                    to_place = value
            else:
                if state == 0:
                    if c == '}':
                        to_place = frame[1]
                        stack.pop()
                        pos += 1
                    elif c == '"':
                        key, pos = _parse_string(s, pos, n)
                        frame[3] = key
                        frame[2] = 1
                    else:
                        raise JSONError(f"expected string key or '}}', got {c!r}", pos)
                elif state == 1:
                    if c == ':':
                        pos += 1
                        frame[2] = 2
                    else:
                        raise JSONError(f"expected ':', got {c!r}", pos)
                elif state == 2:
                    value, pos = _parse_value(s, pos, n, stack)
                    to_place = value
                elif state == 3:
                    if c == '}':
                        to_place = frame[1]
                        stack.pop()
                        pos += 1
                    elif c == ',':
                        pos += 1
                        frame[2] = 4
                    else:
                        raise JSONError(f"expected ',' or '}}', got {c!r}", pos)
                elif state == 4:
                    if c == '"':
                        key, pos = _parse_string(s, pos, n)
                        frame[3] = key
                        frame[2] = 1
                    else:
                        raise JSONError(f"expected string key, got {c!r}", pos)
