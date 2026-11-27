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
    stack = []  # list of (type_char, container): ('a', list) or ('o', dict)
    depth = 0
    pending_key = None
    expect = 'value'
    result = None

    def skip_ws():
        nonlocal pos
        while pos < n:
            c = s[pos]
            if c == ' ' or c == '\t' or c == '\n' or c == '\r':
                pos += 1
            else:
                break

    def parse_string():
        nonlocal pos
        # pos points to opening '"'
        pos += 1
        chars = []
        while True:
            if pos >= n:
                raise JSONError("unexpected end of input in string", pos)
            c = s[pos]
            if c == '"':
                pos += 1
                break
            elif c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of input in string escape", pos)
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
                    if pos + 4 > n:
                        raise JSONError("unexpected end of input in \\u escape", pos)
                    h = s[pos:pos + 4]
                    for ch in h:
                        if not ('0' <= ch <= '9' or 'a' <= ch <= 'f' or 'A' <= ch <= 'F'):
                            raise JSONError("invalid hex digit in \\u escape", pos)
                    code = int(h, 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            h2 = s[pos + 2:pos + 6]
                            ok = True
                            for ch in h2:
                                if not ('0' <= ch <= '9' or 'a' <= ch <= 'f' or 'A' <= ch <= 'F'):
                                    ok = False
                                    break
                            if ok:
                                code2 = int(h2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    code = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    pos += 6
                    chars.append(chr(code))
                else:
                    raise JSONError(f"invalid escape character {ec!r}", pos)
            elif ord(c) < 0x20:
                raise JSONError("unescaped control character in string", pos)
            else:
                chars.append(c)
                pos += 1
        return ''.join(chars)

    def parse_literal(word, value):
        nonlocal pos
        for i, ch in enumerate(word):
            p = pos + i
            if p >= n or s[p] != ch:
                raise JSONError(f"invalid literal, expected {word!r}", p)
        pos += len(word)
        return value

    def parse_number():
        nonlocal pos
        start = pos
        is_float = False
        # Optional minus
        if s[pos] == '-':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in number", pos)
            c = s[pos]
            if c == '0':
                pos += 1
            elif '1' <= c <= '9':
                pos += 1
                while pos < n and '0' <= s[pos] <= '9':
                    pos += 1
            else:
                raise JSONError("invalid digit in number", pos)
        else:
            c = s[pos]
            if c == '0':
                pos += 1
            elif '1' <= c <= '9':
                pos += 1
                while pos < n and '0' <= s[pos] <= '9':
                    pos += 1
            else:
                raise JSONError("invalid digit in number", pos)
        # Fraction
        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit after '.'", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        # Exponent
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
            return float(text)
        else:
            return int(text)

    while True:
        if expect == 'value':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '{':
                pos += 1
                depth += 1
                if depth > 500:
                    raise JSONError("maximum nesting depth exceeded", pos - 1)
                stack.append(('o', {}))
                expect = 'key_or_end'
            elif c == '[':
                pos += 1
                depth += 1
                if depth > 500:
                    raise JSONError("maximum nesting depth exceeded", pos - 1)
                stack.append(('a', []))
                expect = 'value_or_end'
            elif c == '"':
                result = parse_string()
                expect = 'after_value'
            elif c == 't':
                result = parse_literal('true', True)
                expect = 'after_value'
            elif c == 'f':
                result = parse_literal('false', False)
                expect = 'after_value'
            elif c == 'n':
                result = parse_literal('null', None)
                expect = 'after_value'
            elif c == '-' or ('0' <= c <= '9'):
                result = parse_number()
                expect = 'after_value'
            else:
                raise JSONError(f"unexpected character {c!r}", pos)

        elif expect == 'key_or_end':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '}':
                pos += 1
                depth -= 1
                _, container = stack.pop()
                result = container
                expect = 'after_value'
            elif c == '"':
                pending_key = parse_string()
                expect = 'colon'
            else:
                raise JSONError(f"expected string key or '}}', got {c!r}", pos)

        elif expect == 'value_or_end':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == ']':
                pos += 1
                depth -= 1
                _, container = stack.pop()
                result = container
                expect = 'after_value'
            else:
                expect = 'value'
                continue

        elif expect == 'colon':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            if s[pos] != ':':
                raise JSONError(f"expected ':', got {s[pos]!r}", pos)
            pos += 1
            expect = 'value'

        elif expect == 'key':
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if c == '"':
                pending_key = parse_string()
                expect = 'colon'
            else:
                raise JSONError(f"expected string key, got {c!r}", pos)

        elif expect == 'after_value':
            if not stack:
                skip_ws()
                if pos >= n:
                    return result
                else:
                    raise JSONError("trailing garbage", pos)
            frame_type, container = stack[-1]
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            c = s[pos]
            if frame_type == 'a':
                if c == ',':
                    container.append(result)
                    pos += 1
                    expect = 'value'
                elif c == ']':
                    container.append(result)
                    pos += 1
                    depth -= 1
                    stack.pop()
                    result = container
                    # remain in 'after_value' to handle parent
                else:
                    raise JSONError(f"expected ',' or ']', got {c!r}", pos)
            else:
                if c == ',':
                    container[pending_key] = result
                    pending_key = None
                    pos += 1
                    expect = 'key'
                elif c == '}':
                    container[pending_key] = result
                    pending_key = None
                    pos += 1
                    depth -= 1
                    stack.pop()
                    result = container
                    # remain in 'after_value' to handle parent
                else:
                    raise JSONError(f"expected ',' or '}}', got {c!r}", pos)
