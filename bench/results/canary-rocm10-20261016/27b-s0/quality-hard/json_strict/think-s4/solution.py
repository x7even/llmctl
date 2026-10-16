class JSONError(ValueError):
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(f"{message} (at position {pos})")


_HEX = frozenset('0123456789abcdefABCDEF')
_WS = frozenset(' \t\n\r')


def _parse_literal(s, i, n, expected, value):
    for j in range(len(expected)):
        if i + j >= n:
            raise JSONError("unexpected end of input", n)
        if s[i + j] != expected[j]:
            raise JSONError("invalid literal", i + j)
    return value, i + len(expected)


def _parse_number(s, i, n):
    start = i
    is_float = False

    if i < n and s[i] == '-':
        i += 1

    if i >= n:
        raise JSONError("expected digit", i)

    c = s[i]
    if c == '0':
        i += 1
        if i < n and '0' <= s[i] <= '9':
            raise JSONError("leading zero in number", i)
    elif '1' <= c <= '9':
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1
    else:
        raise JSONError("expected digit", i)

    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n or not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit after '.'", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    if i < n and s[i] in 'eE':
        is_float = True
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n or not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit in exponent", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    text = s[start:i]
    if is_float:
        return float(text), i
    else:
        return int(text), i


def _parse_string(s, i, n):
    i += 1  # skip opening quote
    chars = []

    while True:
        if i >= n:
            raise JSONError("unterminated string", i)

        c = s[i]

        if c == '"':
            i += 1
            return ''.join(chars), i
        elif c == '\\':
            i += 1
            if i >= n:
                raise JSONError("unterminated escape sequence", i)
            ec = s[i]
            if ec == '"':
                chars.append('"')
                i += 1
            elif ec == '\\':
                chars.append('\\')
                i += 1
            elif ec == '/':
                chars.append('/')
                i += 1
            elif ec == 'b':
                chars.append('\b')
                i += 1
            elif ec == 'f':
                chars.append('\f')
                i += 1
            elif ec == 'n':
                chars.append('\n')
                i += 1
            elif ec == 'r':
                chars.append('\r')
                i += 1
            elif ec == 't':
                chars.append('\t')
                i += 1
            elif ec == 'u':
                i += 1
                if i + 4 > n:
                    raise JSONError("truncated \\u escape", n)
                h1, h2, h3, h4 = s[i], s[i + 1], s[i + 2], s[i + 3]
                if h1 not in _HEX:
                    raise JSONError("invalid hex digit in \\u escape", i)
                if h2 not in _HEX:
                    raise JSONError("invalid hex digit in \\u escape", i + 1)
                if h3 not in _HEX:
                    raise JSONError("invalid hex digit in \\u escape", i + 2)
                if h4 not in _HEX:
                    raise JSONError("invalid hex digit in \\u escape", i + 3)
                code = (int(h1, 16) << 12) | (int(h2, 16) << 8) | (int(h3, 16) << 4) | int(h4, 16)
                i += 4

                if 0xD800 <= code <= 0xDBFF:
                    if (i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u'
                            and s[i + 2] in _HEX and s[i + 3] in _HEX
                            and s[i + 4] in _HEX and s[i + 5] in _HEX):
                        code2 = ((int(s[i + 2], 16) << 12) | (int(s[i + 3], 16) << 8)
                                 | (int(s[i + 4], 16) << 4) | int(s[i + 5], 16))
                        if 0xDC00 <= code2 <= 0xDFFF:
                            cp = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            chars.append(chr(cp))
                            i += 6
                            continue
                    chars.append(chr(code))
                elif 0xDC00 <= code <= 0xDFFF:
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError(f"invalid escape character", i)
        else:
            if ord(c) < 0x20:
                raise JSONError("unescaped control character in string", i)
            chars.append(c)
            i += 1


def _parse_scalar(s, i, n):
    c = s[i]
    if c == '"':
        return _parse_string(s, i, n)
    elif c == 't':
        return _parse_literal(s, i, n, 'true', True)
    elif c == 'f':
        return _parse_literal(s, i, n, 'false', False)
    elif c == 'n':
        return _parse_literal(s, i, n, 'null', None)
    elif c == '-' or '0' <= c <= '9':
        return _parse_number(s, i, n)
    else:
        raise JSONError(f"unexpected character {c!r}", i)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    i = 0
    stack = []  # each frame: [type, container, state, key]
    result = None
    top_done = False

    while True:
        # Skip whitespace
        while i < n and s[i] in _WS:
            i += 1

        if i >= n:
            if top_done:
                return result
            raise JSONError("unexpected end of input", i)

        c = s[i]

        if top_done:
            raise JSONError("trailing garbage", i)

        if not stack:
            # Top level: expecting a value
            if c == '{':
                stack.append(['object', {}, 'first', None])
                i += 1
            elif c == '[':
                stack.append(['array', [], 'first', None])
                i += 1
            else:
                val, i = _parse_scalar(s, i, n)
                result = val
                top_done = True
        else:
            frame = stack[-1]
            ftype = frame[0]
            container = frame[1]
            state = frame[2]
            key = frame[3]

            if ftype == 'array':
                if state == 'first':
                    if c == ']':
                        stack.pop()
                        if not stack:
                            result = container
                            top_done = True
                        else:
                            p = stack[-1]
                            if p[0] == 'array':
                                p[1].append(container)
                                p[2] = 'after'
                            else:
                                p[1][p[3]] = container
                                p[2] = 'after'
                        i += 1
                    elif c == '{':
                        if len(stack) >= 500:
                            raise JSONError("maximum nesting depth exceeded", i)
                        stack.append(['object', {}, 'first', None])
                        i += 1
                    elif c == '[':
                        if len(stack) >= 500:
                            raise JSONError("maximum nesting depth exceeded", i)
                        stack.append(['array', [], 'first', None])
                        i += 1
                    else:
                        val, i = _parse_scalar(s, i, n)
                        container.append(val)
                        frame[2] = 'after'
                elif state == 'next':
                    if c == '{':
                        if len(stack) >= 500:
                            raise JSONError("maximum nesting depth exceeded", i)
                        stack.append(['object', {}, 'first', None])
                        i += 1
                    elif c == '[':
                        if len(stack) >= 500:
                            raise JSONError("maximum nesting depth exceeded", i)
                        stack.append(['array', [], 'first', None])
                        i += 1
                    else:
                        val, i = _parse_scalar(s, i, n)
                        container.append(val)
                        frame[2] = 'after'
                else:  # state == 'after'
                    if c == ',':
                        frame[2] = 'next'
                        i += 1
                    elif c == ']':
                        stack.pop()
                        if not stack:
                            result = container
                            top_done = True
                        else:
                            p = stack[-1]
                            if p[0] == 'array':
                                p[1].append(container)
                                p[2] = 'after'
                            else:
                                p[1][p[3]] = container
                                p[2] = 'after'
                        i += 1
                    else:
                        raise JSONError(f"expected ',' or ']]', got {c!r}", i)
            else:  # ftype == 'object'
                if state == 'first':
                    if c == '}':
                        stack.pop()
                        if not stack:
                            result = container
                            top_done = True
                        else:
                            p = stack[-1]
                            if p[0] == 'array':
                                p[1].append(container)
                                p[2] = 'after'
                            else:
                                p[1][p[3]] = container
                                p[2] = 'after'
                        i += 1
                    elif c == '"':
                        key, i = _parse_string(s, i, n)
                        frame[3] = key
                        frame[2] = 'colon'
                    else:
                        raise JSONError(f"expected '\"' or '}}', got {c!r}", i)
                elif state == 'key':
                    if c == '"':
                        key, i = _parse_string(s, i, n)
                        frame[3] = key
                        frame[2] = 'colon'
                    else:
                        raise JSONError(f"expected '\"', got {c!r}", i)
                elif state == 'colon':
                    if c == ':':
                        frame[2] = 'value'
                        i += 1
                    else:
                        raise JSONError(f"expected ':', got {c!r}", i)
                elif state == 'value':
                    if c == '{':
                        if len(stack) >= 500:
                            raise JSONError("maximum nesting depth exceeded", i)
                        stack.append(['object', {}, 'first', None])
                        i += 1
                    elif c == '[':
                        if len(stack) >= 500:
                            raise JSONError("maximum nesting depth exceeded", i)
                        stack.append(['array', [], 'first', None])
                        i += 1
                    else:
                        val, i = _parse_scalar(s, i, n)
                        container[key] = val
                        frame[2] = 'after'
                else:  # state == 'after'
                    if c == ',':
                        frame[2] = 'key'
                        i += 1
                    elif c == '}':
                        stack.pop()
                        if not stack:
                            result = container
                            top_done = True
                        else:
                            p = stack[-1]
                            if p[0] == 'array':
                                p[1].append(container)
                                p[2] = 'after'
                            else:
                                p[1][p[3]] = container
                                p[2] = 'after'
                        i += 1
                    else:
                        raise JSONError(f"expected ',' or '}}', got {c!r}", i)
