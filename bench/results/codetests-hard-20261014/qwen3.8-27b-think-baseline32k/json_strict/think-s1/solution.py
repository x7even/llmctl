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
    stack = []  # each entry: [container, state, pending_key]
    result = None
    done = False
    WS = ' \t\n\r'

    def _skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def _complete(val):
        nonlocal result, done
        if not stack:
            result = val
            done = True
            return
        container, state, pkey = stack[-1]
        if isinstance(container, list):
            container.append(val)
            stack[-1][1] = 'after'
        else:
            container[pkey] = val
            stack[-1][1] = 'after'
            stack[-1][2] = None

    def _hex4(p):
        v = 0
        for i in range(4):
            c = s[p + i]
            if '0' <= c <= '9':
                d = ord(c) - 48
            elif 'a' <= c <= 'f':
                d = ord(c) - 87
            elif 'A' <= c <= 'F':
                d = ord(c) - 55
            else:
                raise JSONError(f"invalid hex digit in \\u escape", p + i)
            v = (v << 4) | d
        return v

    def _is_hex4(p):
        for i in range(4):
            c = s[p + i]
            if not ('0' <= c <= '9' or 'a' <= c <= 'f' or 'A' <= c <= 'F'):
                return False
        return True

    def _parse_string():
        nonlocal pos
        pos += 1  # skip opening quote
        parts = []
        while True:
            if pos >= n:
                raise JSONError("unterminated string", n)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(parts)
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
                        raise JSONError("truncated \\u escape", n)
                    code = _hex4(pos)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                                and _is_hex4(pos + 2)):
                            code2 = _hex4(pos + 2)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                cp = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                parts.append(chr(cp))
                                pos += 6
                                continue
                    parts.append(chr(code))
                else:
                    raise JSONError(f"invalid escape character", pos)
            elif ord(c) < 0x20:
                raise JSONError("unescaped control character in string", pos)
            else:
                parts.append(c)
                pos += 1

    def _parse_number():
        nonlocal pos
        start = pos
        if s[pos] == '-':
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input after '-'", n)
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
            raise JSONError(f"expected digit, got {c!r}", pos)

        is_float = False
        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit after '.'", pos if pos < n else n)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit in exponent", pos if pos < n else n)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        else:
            return int(text)

    def _expect(literal):
        nonlocal pos
        ln = len(literal)
        for i in range(ln):
            if pos + i >= n:
                raise JSONError("truncated literal", n)
            if s[pos + i] != literal[i]:
                raise JSONError("invalid literal", pos + i)
        pos += ln

    def _parse_value():
        """Parse a value starting at current pos. Returns the value."""
        nonlocal pos
        c = s[pos]
        if c == '"':
            return _parse_string()
        elif c == '[':
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            stack.append([[], 'first', None])
            return None  # container will be completed later
        elif c == '{':
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            stack.append([{}, 'first', None])
            return None
        elif c == 't':
            _expect('true')
            return True
        elif c == 'f':
            _expect('false')
            return False
        elif c == 'n':
            _expect('null')
            return None
        elif c == '-' or '0' <= c <= '9':
            return _parse_number()
        else:
            raise JSONError(f"unexpected character {c!r}", pos)

    # Main loop
    while True:
        _skip_ws()

        if pos >= n:
            if done:
                return result
            raise JSONError("unexpected end of input", n)

        c = s[pos]

        if done:
            raise JSONError(f"unexpected character {c!r} after top-level value", pos)

        if not stack:
            # Top level: expecting a value
            if c == '"':
                _complete(_parse_string())
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append([[], 'first', None])
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append([{}, 'first', None])
            elif c == 't':
                _expect('true')
                _complete(True)
            elif c == 'f':
                _expect('false')
                _complete(False)
            elif c == 'n':
                _expect('null')
                _complete(None)
            elif c == '-' or '0' <= c <= '9':
                _complete(_parse_number())
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        else:
            container, state, pkey = stack[-1]

            if isinstance(container, list):
                if state == 'first':
                    if c == ']':
                        pos += 1
                        val = stack.pop()[0]
                        _complete(val)
                    elif c == '"':
                        _complete(_parse_string())
                    elif c == '[':
                        if len(stack) >= 500:
                            raise JSONError("maximum nesting depth exceeded", pos)
                        pos += 1
                        stack.append([[], 'first', None])
                    elif c == '{':
                        if len(stack) >= 500:
                            raise JSONError("maximum nesting depth exceeded", pos)
                        pos += 1
                        stack.append([{}, 'first', None])
                    elif c == 't':
                        _expect('true')
                        _complete(True)
                    elif c == 'f':
                        _expect('false')
                        _complete(False)
                    elif c == 'n':
                        _expect('null')
                        _complete(None)
                    elif c == '-' or '0' <= c <= '9':
                        _complete(_parse_number())
                    else:
                        raise JSONError(f"unexpected character {c!r}", pos)
                else:  # state == 'after'
                    if c == ']':
                        pos += 1
                        val = stack.pop()[0]
                        _complete(val)
                    elif c == ',':
                        pos += 1
                        stack[-1][1] = 'first'
                    else:
                        raise JSONError(f"unexpected character {c!r}", pos)

            else:  # dict
                if state == 'first':
                    if c == '}':
                        pos += 1
                        val = stack.pop()[0]
                        _complete(val)
                    elif c == '"':
                        key = _parse_string()
                        stack[-1][1] = 'colon'
                        stack[-1][2] = key
                    else:
                        raise JSONError(f"unexpected character {c!r}", pos)
                elif state == 'colon':
                    if c == ':':
                        pos += 1
                        stack[-1][1] = 'val'
                    else:
                        raise JSONError(f"unexpected character {c!r}", pos)
                elif state == 'val':
                    if c == '"':
                        _complete(_parse_string())
                    elif c == '[':
                        if len(stack) >= 500:
                            raise JSONError("maximum nesting depth exceeded", pos)
                        pos += 1
                        stack.append([[], 'first', None])
                    elif c == '{':
                        if len(stack) >= 500:
                            raise JSONError("maximum nesting depth exceeded", pos)
                        pos += 1
                        stack.append([{}, 'first', None])
                    elif c == 't':
                        _expect('true')
                        _complete(True)
                    elif c == 'f':
                        _expect('false')
                        _complete(False)
                    elif c == 'n':
                        _expect('null')
                        _complete(None)
                    elif c == '-' or '0' <= c <= '9':
                        _complete(_parse_number())
                    else:
                        raise JSONError(f"unexpected character {c!r}", pos)
                else:  # state == 'after'
                    if c == '}':
                        pos += 1
                        val = stack.pop()[0]
                        _complete(val)
                    elif c == ',':
                        pos += 1
                        stack[-1][1] = 'first'
                    else:
                        raise JSONError(f"unexpected character {c!r}", pos)
