class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_WS = ' \t\n\r'
_CONTAINER = object()


def _hex_val(c):
    o = ord(c)
    if 48 <= o <= 57:
        return o - 48
    if 97 <= o <= 102:
        return o - 87
    if 65 <= o <= 70:
        return o - 55
    return -1


def _parse_u4(s, pos, n):
    if pos + 4 > n:
        raise JSONError("truncated \\u escape", pos)
    v = 0
    for i in range(4):
        h = _hex_val(s[pos + i])
        if h < 0:
            raise JSONError("invalid hex digit in \\u escape", pos + i)
        v = (v << 4) | h
    return v, pos + 4


def _parse_string(s, pos, n):
    pos += 1
    chars = []
    while True:
        if pos >= n:
            raise JSONError("unterminated string", pos)
        c = s[pos]
        if c == '"':
            pos += 1
            return ''.join(chars), pos
        if c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unterminated escape sequence", pos)
            ec = s[pos]
            if ec == '"':
                chars.append('"'); pos += 1
            elif ec == '\\':
                chars.append('\\'); pos += 1
            elif ec == '/':
                chars.append('/'); pos += 1
            elif ec == 'b':
                chars.append('\b'); pos += 1
            elif ec == 'f':
                chars.append('\f'); pos += 1
            elif ec == 'n':
                chars.append('\n'); pos += 1
            elif ec == 'r':
                chars.append('\r'); pos += 1
            elif ec == 't':
                chars.append('\t'); pos += 1
            elif ec == 'u':
                pos += 1
                code, pos = _parse_u4(s, pos, n)
                if 0xD800 <= code <= 0xDBFF:
                    if pos + 1 < n and s[pos] == '\\' and s[pos + 1] == 'u':
                        try:
                            code2, new_pos = _parse_u4(s, pos + 2, n)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(combined))
                                pos = new_pos
                                continue
                        except JSONError:
                            pass
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError("invalid escape character", pos)
        elif ord(c) < 0x20:
            raise JSONError("control character in string", pos)
        else:
            chars.append(c)
            pos += 1


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
        return float(text), pos
    else:
        return int(text), pos


def _parse_value(s, pos, n, stack):
    c = s[pos]
    if c == 't':
        for i, ch in enumerate('true'):
            if pos + i >= n or s[pos + i] != ch:
                raise JSONError("invalid literal", min(pos + i, n))
        return True, pos + 4
    if c == 'f':
        for i, ch in enumerate('false'):
            if pos + i >= n or s[pos + i] != ch:
                raise JSONError("invalid literal", min(pos + i, n))
        return False, pos + 5
    if c == 'n':
        for i, ch in enumerate('null'):
            if pos + i >= n or s[pos + i] != ch:
                raise JSONError("invalid literal", min(pos + i, n))
        return None, pos + 4
    if c == '"':
        return _parse_string(s, pos, n)
    if c == '-' or '0' <= c <= '9':
        return _parse_number(s, pos, n)
    if c == '[':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", pos)
        stack.append([0, [], 0, None])
        return _CONTAINER, pos + 1
    if c == '{':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", pos)
        stack.append([1, {}, 0, None])
        return _CONTAINER, pos + 1
    raise JSONError("unexpected character", pos)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")
    n = len(s)
    pos = 0
    stack = []
    has_pending = False
    pending = None

    while True:
        if has_pending:
            has_pending = False
            if not stack:
                while pos < n and s[pos] in _WS:
                    pos += 1
                if pos < n:
                    raise JSONError("trailing data", pos)
                return pending
            frame = stack[-1]
            if frame[0] == 0:
                frame[1].append(pending)
                frame[2] = 1
            else:
                frame[1][frame[3]] = pending
                frame[2] = 3
            continue

        while pos < n and s[pos] in _WS:
            pos += 1

        if pos >= n:
            raise JSONError("unexpected end of input", pos)

        c = s[pos]

        if not stack:
            value, pos = _parse_value(s, pos, n, stack)
            if value is not _CONTAINER:
                pending = value
                has_pending = True
        else:
            frame = stack[-1]
            if frame[0] == 0:
                if frame[2] == 0:
                    if c == ']':
                        pos += 1
                        pending = stack.pop()[1]
                        has_pending = True
                    else:
                        value, pos = _parse_value(s, pos, n, stack)
                        if value is not _CONTAINER:
                            pending = value
                            has_pending = True
                elif frame[2] == 1:
                    if c == ',':
                        pos += 1
                        frame[2] = 2
                    elif c == ']':
                        pos += 1
                        pending = stack.pop()[1]
                        has_pending = True
                    else:
                        raise JSONError("expected ',' or ']'", pos)
                else:
                    value, pos = _parse_value(s, pos, n, stack)
                    if value is not _CONTAINER:
                        pending = value
                        has_pending = True
            else:
                if frame[2] == 0:
                    if c == '}':
                        pos += 1
                        pending = stack.pop()[1]
                        has_pending = True
                    elif c == '"':
                        key, pos = _parse_string(s, pos, n)
                        frame[3] = key
                        frame[2] = 1
                    else:
                        raise JSONError("expected string key or '}'", pos)
                elif frame[2] == 1:
                    if c == ':':
                        pos += 1
                        frame[2] = 2
                    else:
                        raise JSONError("expected ':'", pos)
                elif frame[2] == 2:
                    value, pos = _parse_value(s, pos, n, stack)
                    if value is not _CONTAINER:
                        pending = value
                        has_pending = True
                elif frame[2] == 3:
                    if c == ',':
                        pos += 1
                        frame[2] = 4
                    elif c == '}':
                        pos += 1
                        pending = stack.pop()[1]
                        has_pending = True
                    else:
                        raise JSONError("expected ',' or '}'", pos)
                else:
                    if c == '"':
                        key, pos = _parse_string(s, pos, n)
                        frame[3] = key
                        frame[2] = 1
                    else:
                        raise JSONError("expected string key", pos)