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
    stack = []  # each entry: [type, container, key]
    result = None
    expect = 'value'

    while True:
        # Skip whitespace
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1

        if expect == 'value':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['array', [], None])
                expect = 'array_first'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['object', {}, None])
                expect = 'object_first'
            elif c == '"':
                pos, result = _parse_string(s, pos, n)
                expect = 'after_value'
            elif c == '-' or ('0' <= c <= '9'):
                pos, result = _parse_number(s, pos, n)
                expect = 'after_value'
            elif c == 't':
                pos = _parse_literal(s, pos, n, 'true')
                result = True
                expect = 'after_value'
            elif c == 'f':
                pos = _parse_literal(s, pos, n, 'false')
                result = False
                expect = 'after_value'
            elif c == 'n':
                pos = _parse_literal(s, pos, n, 'null')
                result = None
                expect = 'after_value'
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif expect == 'array_first':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] == ']':
                pos += 1
                _, arr, _ = stack.pop()
                result = arr
                expect = 'after_value'
            else:
                expect = 'value'

        elif expect == 'object_first':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '}':
                pos += 1
                _, obj, _ = stack.pop()
                result = obj
                expect = 'after_value'
            elif c == '"':
                pos, key = _parse_string(s, pos, n)
                stack[-1][2] = key
                expect = 'colon'
            else:
                raise JSONError(f"expected string key or '}}'", pos)

        elif expect == 'colon':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] != ':':
                raise JSONError("expected ':'", pos)
            pos += 1
            expect = 'value'

        elif expect == 'array_sep':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == ']':
                pos += 1
                _, arr, _ = stack.pop()
                result = arr
                expect = 'after_value'
            elif c == ',':
                pos += 1
                expect = 'value'
            else:
                raise JSONError(f"expected ',' or ']', got {c!r}", pos)

        elif expect == 'object_sep':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '}':
                pos += 1
                _, obj, _ = stack.pop()
                result = obj
                expect = 'after_value'
            elif c == ',':
                pos += 1
                expect = 'key'
            else:
                raise JSONError(f"expected ',' or '}}', got {c!r}", pos)

        elif expect == 'key':
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] != '"':
                raise JSONError(f"expected string key, got {s[pos]!r}", pos)
            pos, key = _parse_string(s, pos, n)
            stack[-1][2] = key
            expect = 'colon'

        elif expect == 'after_value':
            if not stack:
                expect = 'top_end'
            else:
                if stack[-1][0] == 'array':
                    stack[-1][1].append(result)
                    expect = 'array_sep'
                else:
                    key = stack[-1][2]
                    stack[-1][1][key] = result
                    expect = 'object_sep'

        elif expect == 'top_end':
            if pos >= n:
                return result
            else:
                raise JSONError(f"trailing garbage: {s[pos]!r}", pos)


def _parse_literal(s, pos, n, target):
    tlen = len(target)
    for i in range(tlen):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != target[i]:
            raise JSONError(f"invalid literal", pos + i)
    return pos + tlen


def _parse_number(s, pos, n):
    start = pos

    # Optional minus
    if pos < n and s[pos] == '-':
        pos += 1

    # Integer part
    if pos >= n:
        raise JSONError("unexpected end of input in number", pos)
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
        raise JSONError("expected digit in number", pos)

    # Fraction part
    has_fraction = False
    if pos < n and s[pos] == '.':
        has_fraction = True
        pos += 1
        if pos >= n or not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit after '.'", pos)
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
            raise JSONError("expected digit in exponent", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    num_str = s[start:pos]
    if has_fraction or has_exponent:
        return pos, float(num_str)
    else:
        return pos, int(num_str)


def _parse_string(s, pos, n):
    # s[pos] == '"'
    pos += 1  # skip opening quote
    chars = []

    while True:
        if pos >= n:
            raise JSONError("unexpected end of input in string", n)
        c = s[pos]
        if c == '"':
            pos += 1
            return pos, ''.join(chars)
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in string escape", n)
            ec = s[pos]
            if ec == '"':
                chars.append('"')
                pos += 1
            elif ec == '\\':
                chars.append('\\')
                pos += 1
            elif ec == '/':
                chars.append('/')
                pos += 1
            elif ec == 'b':
                chars.append('\b')
                pos += 1
            elif ec == 'f':
                chars.append('\f')
                pos += 1
            elif ec == 'n':
                chars.append('\n')
                pos += 1
            elif ec == 'r':
                chars.append('\r')
                pos += 1
            elif ec == 't':
                chars.append('\t')
                pos += 1
            elif ec == 'u':
                pos += 1
                if pos + 4 > n:
                    raise JSONError("unexpected end of input in \\u escape", n)
                h0 = s[pos]
                h1 = s[pos + 1]
                h2 = s[pos + 2]
                h3 = s[pos + 3]
                if not _is_hex(h0):
                    raise JSONError("invalid hex digit in \\u escape", pos)
                if not _is_hex(h1):
                    raise JSONError("invalid hex digit in \\u escape", pos + 1)
                if not _is_hex(h2):
                    raise JSONError("invalid hex digit in \\u escape", pos + 2)
                if not _is_hex(h3):
                    raise JSONError("invalid hex digit in \\u escape", pos + 3)
                code = int(h0 + h1 + h2 + h3, 16)
                pos += 4

                if 0xD800 <= code <= 0xDBFF:
                    # High surrogate: check for immediately following \uXXXX low surrogate
                    if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                            and _is_hex(s[pos + 2]) and _is_hex(s[pos + 3])
                            and _is_hex(s[pos + 4]) and _is_hex(s[pos + 5])):
                        code2 = int(s[pos + 2:pos + 6], 16)
                        if 0xDC00 <= code2 <= 0xDFFF:
                            cp = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            chars.append(chr(cp))
                            pos += 6
                            continue
                    # Unpaired high surrogate
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError(f"invalid escape character {ec!r}", pos)
        elif ord(c) < 0x20:
            raise JSONError("raw control character in string", pos)
        else:
            chars.append(c)
            pos += 1


def _is_hex(c):
    return ('0' <= c <= '9') or ('a' <= c <= 'f') or ('A' <= c <= 'F')