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
    stack = []  # each entry: [container, state, key]
    # array states: 'first', 'ev', 'es'
    # object states: 'first', 'ec', 'ev', 'es', 'ek'
    pending = None
    has_pending = False
    WS = ' \t\n\r'

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening quote
        chars = []
        while True:
            if pos >= n:
                raise JSONError("unexpected end of string", pos)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of string escape", pos)
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
                        for i in range(4):
                            if pos + i >= n:
                                raise JSONError("unexpected end of \\u escape", pos + i)
                        raise JSONError("unexpected end", pos)
                    code = 0
                    for i in range(4):
                        ch = s[pos + i]
                        if '0' <= ch <= '9':
                            code = code * 16 + (ord(ch) - 48)
                        elif 'a' <= ch <= 'f':
                            code = code * 16 + (ord(ch) - 87)
                        elif 'A' <= ch <= 'F':
                            code = code * 16 + (ord(ch) - 55)
                        else:
                            raise JSONError("invalid hex digit in \\u escape", pos + i)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            code2 = 0
                            valid = True
                            for i in range(4):
                                ch = s[pos + 2 + i]
                                if '0' <= ch <= '9':
                                    code2 = code2 * 16 + (ord(ch) - 48)
                                elif 'a' <= ch <= 'f':
                                    code2 = code2 * 16 + (ord(ch) - 87)
                                elif 'A' <= ch <= 'F':
                                    code2 = code2 * 16 + (ord(ch) - 55)
                                else:
                                    valid = False
                                    break
                            if valid and 0xDC00 <= code2 <= 0xDFFF:
                                cp = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(cp))
                                pos += 6
                                continue
                    chars.append(chr(code))
                else:
                    raise JSONError("invalid escape character", pos)
            elif ord(c) < 0x20:
                raise JSONError("raw control character in string", pos)
            else:
                chars.append(c)
                pos += 1

    def parse_number():
        nonlocal pos
        start = pos
        if s[pos] == '-':
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end of number", pos)
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
        is_float = False
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
            return float(text)
        return int(text)

    def parse_literal():
        nonlocal pos
        c = s[pos]
        if c == 't':
            expected = 'true'
        elif c == 'f':
            expected = 'false'
        else:
            expected = 'null'
        for i in range(len(expected)):
            if pos + i >= n or s[pos + i] != expected[i]:
                raise JSONError("invalid literal", pos + i)
        pos += len(expected)
        if c == 't':
            return True
        elif c == 'f':
            return False
        return None

    def start_value():
        nonlocal pos, pending, has_pending
        c = s[pos]
        if c == '[':
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            stack.append([[], 'first', None])
        elif c == '{':
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            stack.append([{}, 'first', None])
        elif c == '"':
            pending = parse_string()
            has_pending = True
        elif c == 't' or c == 'f' or c == 'n':
            pending = parse_literal()
            has_pending = True
        elif c == '-' or '0' <= c <= '9':
            pending = parse_number()
            has_pending = True
        else:
            raise JSONError(f"unexpected character {c!r}", pos)

    while True:
        if has_pending:
            has_pending = False
            if not stack:
                skip_ws()
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return pending
            else:
                frame = stack[-1]
                container = frame[0]
                if isinstance(container, list):
                    container.append(pending)
                    frame[1] = 'es'
                else:
                    container[frame[2]] = pending
                    frame[1] = 'es'

        if not stack:
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            start_value()
        else:
            frame = stack[-1]
            container = frame[0]
            state = frame[1]
            if isinstance(container, list):
                if state == 'first':
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == ']':
                        pos += 1
                        stack.pop()
                        pending = container
                        has_pending = True
                    else:
                        start_value()
                elif state == 'es':
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == ']':
                        pos += 1
                        stack.pop()
                        pending = container
                        has_pending = True
                    elif s[pos] == ',':
                        pos += 1
                        frame[1] = 'ev'
                    else:
                        raise JSONError(f"expected ',' or ']', got {s[pos]!r}", pos)
                else:  # 'ev'
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    start_value()
            else:
                if state == 'first':
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == '}':
                        pos += 1
                        stack.pop()
                        pending = container
                        has_pending = True
                    elif s[pos] == '"':
                        key = parse_string()
                        frame[1] = 'ec'
                        frame[2] = key
                    else:
                        raise JSONError(f"expected string key or '}}', got {s[pos]!r}", pos)
                elif state == 'ec':
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == ':':
                        pos += 1
                        frame[1] = 'ev'
                    else:
                        raise JSONError(f"expected ':', got {s[pos]!r}", pos)
                elif state == 'ev':
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    start_value()
                elif state == 'es':
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == '}':
                        pos += 1
                        stack.pop()
                        pending = container
                        has_pending = True
                    elif s[pos] == ',':
                        pos += 1
                        frame[1] = 'ek'
                    else:
                        raise JSONError(f"expected ',' or '}}', got {s[pos]!r}", pos)
                else:  # 'ek'
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == '"':
                        key = parse_string()
                        frame[1] = 'ec'
                        frame[2] = key
                    else:
                        raise JSONError(f"expected string key, got {s[pos]!r}", pos)
