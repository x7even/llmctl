class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, not {type(s).__name__}")

    n = len(s)
    i = 0
    stack = []  # each entry: [type, state, result, key]
    current = None
    top_done = False

    while True:
        # Skip whitespace
        while i < n and s[i] in ' \t\n\r':
            i += 1

        if i >= n:
            if not top_done or stack:
                raise JSONError("unexpected end of input", i)
            return current

        c = s[i]

        if top_done:
            raise JSONError("trailing garbage", i)

        if not stack:
            # Top level: parse a single value
            if c == '{':
                stack.append(['object', 'key_or_end', {}, None])
                i += 1
            elif c == '[':
                stack.append(['array', 'value_or_end', [], None])
                i += 1
            elif c == '"':
                current, i = _parse_string(s, i)
                top_done = True
            elif c == 't':
                i = _check_literal(s, i, 'true')
                current = True
                top_done = True
            elif c == 'f':
                i = _check_literal(s, i, 'false')
                current = False
                top_done = True
            elif c == 'n':
                i = _check_literal(s, i, 'null')
                current = None
                top_done = True
            elif c == '-' or '0' <= c <= '9':
                current, i = _parse_number(s, i)
                top_done = True
            else:
                raise JSONError(f"unexpected character {c!r}", i)
        else:
            frame = stack[-1]
            ftype = frame[0]
            state = frame[1]

            if ftype == 'array':
                if state == 'value_or_end':
                    if c == ']':
                        current = frame[2]
                        stack.pop()
                        i += 1
                        if not stack:
                            top_done = True
                        else:
                            _commit(stack, current)
                    else:
                        i = _parse_value(s, i, stack)
                elif state == 'comma_or_end':
                    if c == ']':
                        current = frame[2]
                        stack.pop()
                        i += 1
                        if not stack:
                            top_done = True
                        else:
                            _commit(stack, current)
                    elif c == ',':
                        frame[1] = 'value'
                        i += 1
                    else:
                        raise JSONError(f"expected ',' or ']', got {c!r}", i)
                elif state == 'value':
                    i = _parse_value(s, i, stack)

            elif ftype == 'object':
                if state == 'key_or_end':
                    if c == '}':
                        current = frame[2]
                        stack.pop()
                        i += 1
                        if not stack:
                            top_done = True
                        else:
                            _commit(stack, current)
                    elif c == '"':
                        key, i = _parse_string(s, i)
                        frame[3] = key
                        frame[1] = 'colon'
                    else:
                        raise JSONError(f"expected string key, got {c!r}", i)
                elif state == 'colon':
                    if c == ':':
                        frame[1] = 'value'
                        i += 1
                    else:
                        raise JSONError(f"expected ':', got {c!r}", i)
                elif state == 'value':
                    i = _parse_value(s, i, stack)
                elif state == 'comma_or_end':
                    if c == '}':
                        current = frame[2]
                        stack.pop()
                        i += 1
                        if not stack:
                            top_done = True
                        else:
                            _commit(stack, current)
                    elif c == ',':
                        frame[1] = 'key'
                        i += 1
                    else:
                        raise JSONError(f"expected ',' or '}}', got {c!r}", i)
                elif state == 'key':
                    if c == '"':
                        key, i = _parse_string(s, i)
                        frame[3] = key
                        frame[1] = 'colon'
                    else:
                        raise JSONError(f"expected string key, got {c!r}", i)


def _commit(stack, value):
    frame = stack[-1]
    if frame[0] == 'array':
        frame[2].append(value)
        frame[1] = 'comma_or_end'
    else:
        frame[2][frame[3]] = value
        frame[1] = 'comma_or_end'


def _parse_value(s, i, stack):
    """Parse a value inside a container. Pushes a frame for containers,
    commits scalars. Returns new position."""
    c = s[i]
    if c == '{':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", i)
        stack.append(['object', 'key_or_end', {}, None])
        return i + 1
    if c == '[':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", i)
        stack.append(['array', 'value_or_end', [], None])
        return i + 1
    if c == '"':
        val, i = _parse_string(s, i)
        _commit(stack, val)
        return i
    if c == 't':
        i = _check_literal(s, i, 'true')
        _commit(stack, True)
        return i
    if c == 'f':
        i = _check_literal(s, i, 'false')
        _commit(stack, False)
        return i
    if c == 'n':
        i = _check_literal(s, i, 'null')
        _commit(stack, None)
        return i
    if c == '-' or '0' <= c <= '9':
        val, i = _parse_number(s, i)
        _commit(stack, val)
        return i
    raise JSONError(f"unexpected character {c!r}", i)


def _parse_string(s, i):
    """Parse a JSON string. s[i] must be '"'. Returns (str, new_i)."""
    n = len(s)
    i += 1
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
                    raise JSONError("incomplete \\u escape", n)
                code = 0
                for j in range(4):
                    h = s[i + j]
                    if '0' <= h <= '9':
                        v = ord(h) - 48
                    elif 'a' <= h <= 'f':
                        v = ord(h) - 87
                    elif 'A' <= h <= 'F':
                        v = ord(h) - 55
                    else:
                        raise JSONError("invalid hex digit in \\u escape", i + j)
                    code = (code << 4) | v
                i += 4
                if 0xD800 <= code <= 0xDBFF:
                    # High surrogate: check for immediately following low surrogate escape
                    if i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u':
                        code2 = 0
                        valid = True
                        for j in range(4):
                            h = s[i + 2 + j]
                            if '0' <= h <= '9':
                                v = ord(h) - 48
                            elif 'a' <= h <= 'f':
                                v = ord(h) - 87
                            elif 'A' <= h <= 'F':
                                v = ord(h) - 55
                            else:
                                valid = False
                                break
                            code2 = (code2 << 4) | v
                        if valid and 0xDC00 <= code2 <= 0xDFFF:
                            code = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            i += 6
                            chars.append(chr(code))
                            continue
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError(f"invalid escape character", i)
        elif ord(c) < 0x20:
            raise JSONError("unescaped control character in string", i)
        else:
            chars.append(c)
            i += 1


def _parse_number(s, i):
    """Parse a JSON number starting at position i. Returns (value, new_i)."""
    n = len(s)
    start = i
    if s[i] == '-':
        i += 1
    if i >= n:
        raise JSONError("unexpected end of input", i)
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
        raise JSONError("invalid number", i)

    is_float = False
    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n or not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit after decimal point", i)
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


def _check_literal(s, i, literal):
    """Verify that s[i:i+len(literal)] equals literal. Returns new i or raises."""
    n = len(s)
    for j in range(len(literal)):
        if i + j >= n:
            raise JSONError("unexpected end of input", n)
        if s[i + j] != literal[j]:
            raise JSONError("invalid literal", i + j)
    return i + len(literal)