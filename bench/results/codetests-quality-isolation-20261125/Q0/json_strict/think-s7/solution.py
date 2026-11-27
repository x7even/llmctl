class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_WS = frozenset(' \t\n\r')
_MAX_DEPTH = 500


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []  # each frame: [type, container, state, pending_key]
    result = None
    done = False

    while pos < n:
        c = s[pos]

        if c in _WS:
            pos += 1
            continue

        if done:
            raise JSONError("trailing garbage", pos)

        if not stack:
            # ---- top level: expecting a value ----
            if c == '[':
                if len(stack) >= _MAX_DEPTH:
                    raise JSONError("nesting depth limit exceeded", pos)
                stack.append(['array', [], 'first_or_end', None])
                pos += 1
            elif c == '{':
                if len(stack) >= _MAX_DEPTH:
                    raise JSONError("nesting depth limit exceeded", pos)
                stack.append(['object', {}, 'first_or_end', None])
                pos += 1
            elif c == '"':
                result, pos = _parse_string(s, pos, n)
                done = True
            elif c == '-' or '0' <= c <= '9':
                result, pos = _parse_number(s, pos, n)
                done = True
            elif c == 't':
                result, pos = _parse_literal(s, pos, n, 'true')
                done = True
            elif c == 'f':
                result, pos = _parse_literal(s, pos, n, 'false')
                done = True
            elif c == 'n':
                result, pos = _parse_literal(s, pos, n, 'null')
                done = True
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        else:
            frame = stack[-1]
            ftype = frame[0]
            container = frame[1]
            state = frame[2]

            if ftype == 'array':
                if state == 'first_or_end':
                    if c == ']':
                        stack.pop()
                        pos += 1
                        if not stack:
                            result = container
                            done = True
                        else:
                            _store_in_parent(stack, container)
                    elif c == '[':
                        if len(stack) >= _MAX_DEPTH:
                            raise JSONError("nesting depth limit exceeded", pos)
                        stack.append(['array', [], 'first_or_end', None])
                        pos += 1
                    elif c == '{':
                        if len(stack) >= _MAX_DEPTH:
                            raise JSONError("nesting depth limit exceeded", pos)
                        stack.append(['object', {}, 'first_or_end', None])
                        pos += 1
                    elif c == '"':
                        value, pos = _parse_string(s, pos, n)
                        container.append(value)
                        frame[2] = 'comma_or_end'
                    elif c == '-' or '0' <= c <= '9':
                        value, pos = _parse_number(s, pos, n)
                        container.append(value)
                        frame[2] = 'comma_or_end'
                    elif c == 't':
                        value, pos = _parse_literal(s, pos, n, 'true')
                        container.append(value)
                        frame[2] = 'comma_or_end'
                    elif c == 'f':
                        value, pos = _parse_literal(s, pos, n, 'false')
                        container.append(value)
                        frame[2] = 'comma_or_end'
                    elif c == 'n':
                        value, pos = _parse_literal(s, pos, n, 'null')
                        container.append(value)
                        frame[2] = 'comma_or_end'
                    else:
                        raise JSONError(f"unexpected character {c!r}", pos)

                elif state == 'value':
                    if c == '[':
                        if len(stack) >= _MAX_DEPTH:
                            raise JSONError("nesting depth limit exceeded", pos)
                        stack.append(['array', [], 'first_or_end', None])
                        pos += 1
                    elif c == '{':
                        if len(stack) >= _MAX_DEPTH:
                            raise JSONError("nesting depth limit exceeded", pos)
                        stack.append(['object', {}, 'first_or_end', None])
                        pos += 1
                    elif c == '"':
                        value, pos = _parse_string(s, pos, n)
                        container.append(value)
                        frame[2] = 'comma_or_end'
                    elif c == '-' or '0' <= c <= '9':
                        value, pos = _parse_number(s, pos, n)
                        container.append(value)
                        frame[2] = 'comma_or_end'
                    elif c == 't':
                        value, pos = _parse_literal(s, pos, n, 'true')
                        container.append(value)
                        frame[2] = 'comma_or_end'
                    elif c == 'f':
                        value, pos = _parse_literal(s, pos, n, 'false')
                        container.append(value)
                        frame[2] = 'comma_or_end'
                    elif c == 'n':
                        value, pos = _parse_literal(s, pos, n, 'null')
                        container.append(value)
                        frame[2] = 'comma_or_end'
                    else:
                        raise JSONError(f"unexpected character {c!r}", pos)

                elif state == 'comma_or_end':
                    if c == ',':
                        frame[2] = 'value'
                        pos += 1
                    elif c == ']':
                        stack.pop()
                        pos += 1
                        if not stack:
                            result = container
                            done = True
                        else:
                            _store_in_parent(stack, container)
                    else:
                        raise JSONError(f"unexpected character {c!r}", pos)

            elif ftype == 'object':
                if state == 'first_or_end':
                    if c == '}':
                        stack.pop()
                        pos += 1
                        if not stack:
                            result = container
                            done = True
                        else:
                            _store_in_parent(stack, container)
                    elif c == '"':
                        key, pos = _parse_string(s, pos, n)
                        frame[3] = key
                        frame[2] = 'colon'
                    else:
                        raise JSONError(f"expected string key or '}}'", pos)

                elif state == 'key':
                    if c == '"':
                        key, pos = _parse_string(s, pos, n)
                        frame[3] = key
                        frame[2] = 'colon'
                    else:
                        raise JSONError(f"expected string key", pos)

                elif state == 'colon':
                    if c == ':':
                        frame[2] = 'value'
                        pos += 1
                    else:
                        raise JSONError(f"expected ':'", pos)

                elif state == 'value':
                    if c == '[':
                        if len(stack) >= _MAX_DEPTH:
                            raise JSONError("nesting depth limit exceeded", pos)
                        stack.append(['array', [], 'first_or_end', None])
                        pos += 1
                    elif c == '{':
                        if len(stack) >= _MAX_DEPTH:
                            raise JSONError("nesting depth limit exceeded", pos)
                        stack.append(['object', {}, 'first_or_end', None])
                        pos += 1
                    elif c == '"':
                        value, pos = _parse_string(s, pos, n)
                        container[frame[3]] = value
                        frame[2] = 'comma_or_end'
                    elif c == '-' or '0' <= c <= '9':
                        value, pos = _parse_number(s, pos, n)
                        container[frame[3]] = value
                        frame[2] = 'comma_or_end'
                    elif c == 't':
                        value, pos = _parse_literal(s, pos, n, 'true')
                        container[frame[3]] = value
                        frame[2] = 'comma_or_end'
                    elif c == 'f':
                        value, pos = _parse_literal(s, pos, n, 'false')
                        container[frame[3]] = value
                        frame[2] = 'comma_or_end'
                    elif c == 'n':
                        value, pos = _parse_literal(s, pos, n, 'null')
                        container[frame[3]] = value
                        frame[2] = 'comma_or_end'
                    else:
                        raise JSONError(f"unexpected character {c!r}", pos)

                elif state == 'comma_or_end':
                    if c == ',':
                        frame[2] = 'key'
                        pos += 1
                    elif c == '}':
                        stack.pop()
                        pos += 1
                        if not stack:
                            result = container
                            done = True
                        else:
                            _store_in_parent(stack, container)
                    else:
                        raise JSONError(f"unexpected character {c!r}", pos)

    if not done:
        raise JSONError("unexpected end of input", n)

    return result


def _store_in_parent(stack, value):
    parent = stack[-1]
    if parent[0] == 'array':
        parent[1].append(value)
        parent[2] = 'comma_or_end'
    else:
        parent[1][parent[3]] = value
        parent[2] = 'comma_or_end'


def _parse_literal(s, pos, n, expected):
    ln = len(expected)
    for i in range(ln):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != expected[i]:
            raise JSONError(f"invalid literal, expected {expected!r}", pos + i)
    val = True if expected == 'true' else (False if expected == 'false' else None)
    return val, pos + ln


def _parse_number(s, pos, n):
    start = pos

    if s[pos] == '-':
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)

    # Integer part
    if s[pos] == '0':
        pos += 1
        if pos < n and '0' <= s[pos] <= '9':
            raise JSONError("leading zero in number", pos)
    elif '1' <= s[pos] <= '9':
        pos += 1
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    else:
        raise JSONError("invalid number", pos)

    # Fraction part
    has_fraction = False
    if pos < n and s[pos] == '.':
        has_fraction = True
        pos += 1
        if pos >= n or not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit after '.'", n if pos >= n else pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    # Exponent part
    has_exponent = False
    if pos < n and s[pos] in 'eE':
        has_exponent = True
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n or not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit in exponent", n if pos >= n else pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if has_fraction or has_exponent:
        return float(text), pos
    else:
        return int(text), pos


def _parse_string(s, pos, n):
    # s[pos] == '"'
    pos += 1
    chars = []

    while True:
        if pos >= n:
            raise JSONError("unexpected end of input in string", n)

        c = s[pos]

        if c == '"':
            pos += 1
            return ''.join(chars), pos

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
                    h = s[pos + i]
                    if '0' <= h <= '9':
                        code = code * 16 + (ord(h) - 48)
                    elif 'a' <= h <= 'f':
                        code = code * 16 + (ord(h) - 87)
                    elif 'A' <= h <= 'F':
                        code = code * 16 + (ord(h) - 55)
                    else:
                        raise JSONError(f"invalid hex digit in \\u escape", pos + i)
                pos += 4

                # Surrogate pair handling
                if 0xD800 <= code <= 0xDBFF:
                    if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'):
                        code2 = 0
                        valid = True
                        for i in range(4):
                            h = s[pos + 2 + i]
                            if '0' <= h <= '9':
                                code2 = code2 * 16 + (ord(h) - 48)
                            elif 'a' <= h <= 'f':
                                code2 = code2 * 16 + (ord(h) - 87)
                            elif 'A' <= h <= 'F':
                                code2 = code2 * 16 + (ord(h) - 55)
                            else:
                                valid = False
                                break
                        if valid and 0xDC00 <= code2 <= 0xDFFF:
                            combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            chars.append(chr(combined))
                            pos += 6
                            continue
                    # Lone high surrogate
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError(f"invalid escape character \\\\{esc}", pos)

        elif ord(c) < 0x20:
            raise JSONError("unescaped control character in string", pos)

        else:
            chars.append(c)
            pos += 1
