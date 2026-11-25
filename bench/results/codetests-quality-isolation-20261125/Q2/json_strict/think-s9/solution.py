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
    stack = []  # frames: (container, state, key)
    has_pending = False
    pending = None

    WS = ' \t\n\r'
    HEX = '0123456789abcdefABCDEF'

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def err(msg, p):
        raise JSONError(msg, p)

    def parse_string():
        nonlocal pos
        # pos is at opening quote
        pos += 1
        chars = []
        while True:
            if pos >= n:
                err("Unterminated string", pos)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    err("Unterminated escape sequence", pos)
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
                        err("Truncated \\u escape", n)
                    for i in range(4):
                        if s[pos + i] not in HEX:
                            err("Invalid hex digit in \\u escape", pos + i)
                    code = int(s[pos:pos + 4], 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        # High surrogate: check for low surrogate escape
                        if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                                and all(s[pos + 2 + i] in HEX for i in range(4))):
                            code2 = int(s[pos + 2:pos + 6], 16)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(combined))
                                pos += 6
                                continue
                        chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    err(f"Invalid escape character", pos)
            elif ord(c) < 0x20:
                err("Raw control character in string", pos)
            else:
                chars.append(c)
                pos += 1

    def parse_number():
        nonlocal pos
        start = pos
        if pos < n and s[pos] == '-':
            pos += 1
        if pos >= n:
            err("Expected digit after '-'", pos)
        c = s[pos]
        if c == '0':
            pos += 1
        elif '1' <= c <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            err("Invalid number", pos)

        is_float = False

        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                err("Expected digit after '.'", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                err("Expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        else:
            return int(text)

    def parse_value_here():
        nonlocal pos, pending, has_pending
        if pos >= n:
            err("Unexpected end of input", pos)
        c = s[pos]
        if c == '[':
            pos += 1
            if len(stack) >= 500:
                err("Maximum nesting depth exceeded", pos - 1)
            stack.append(([], 'start', None))
        elif c == '{':
            pos += 1
            if len(stack) >= 500:
                err("Maximum nesting depth exceeded", pos - 1)
            stack.append(({}, 'start', None))
        elif c == '"':
            pending = parse_string()
            has_pending = True
        elif c == 't':
            literal = 'true'
            for i, ch in enumerate(literal):
                if pos + i >= n:
                    err("Unexpected end of input", n)
                if s[pos + i] != ch:
                    err("Invalid literal", pos + i)
            pos += 4
            pending = True
            has_pending = True
        elif c == 'f':
            literal = 'false'
            for i, ch in enumerate(literal):
                if pos + i >= n:
                    err("Unexpected end of input", n)
                if s[pos + i] != ch:
                    err("Invalid literal", pos + i)
            pos += 5
            pending = False
            has_pending = True
        elif c == 'n':
            literal = 'null'
            for i, ch in enumerate(literal):
                if pos + i >= n:
                    err("Unexpected end of input", n)
                if s[pos + i] != ch:
                    err("Invalid literal", pos + i)
            pos += 4
            pending = None
            has_pending = True
        elif c == '-' or ('0' <= c <= '9'):
            pending = parse_number()
            has_pending = True
        else:
            err(f"Unexpected character {c!r}", pos)

    while True:
        # Attach pending value to parent
        if has_pending:
            if not stack:
                skip_ws()
                if pos < n:
                    err("Trailing data", pos)
                return pending
            else:
                container, state, key = stack[-1]
                if isinstance(container, list):
                    container.append(pending)
                    stack[-1] = (container, 'after_elem', None)
                else:
                    container[key] = pending
                    stack[-1] = (container, 'after_value', None)
                has_pending = False

        skip_ws()

        if pos >= n:
            err("Unexpected end of input", pos)

        c = s[pos]

        if not stack:
            parse_value_here()
            continue

        container, state, key = stack[-1]

        if isinstance(container, list):
            if state == 'start':
                if c == ']':
                    pos += 1
                    pending = container
                    has_pending = True
                    stack.pop()
                else:
                    parse_value_here()
            elif state == 'after_elem':
                if c == ',':
                    pos += 1
                    stack[-1] = (container, 'after_comma', None)
                elif c == ']':
                    pos += 1
                    pending = container
                    has_pending = True
                    stack.pop()
                else:
                    err(f"Expected ',' or ']', got {c!r}", pos)
            elif state == 'after_comma':
                parse_value_here()
        else:
            if state == 'start':
                if c == '}':
                    pos += 1
                    pending = container
                    has_pending = True
                    stack.pop()
                elif c == '"':
                    key = parse_string()
                    stack[-1] = (container, 'after_key', key)
                else:
                    err(f"Expected '\"' or '}}', got {c!r}", pos)
            elif state == 'after_key':
                if c == ':':
                    pos += 1
                    stack[-1] = (container, 'after_colon', key)
                else:
                    err(f"Expected ':', got {c!r}", pos)
            elif state == 'after_colon':
                parse_value_here()
            elif state == 'after_value':
                if c == ',':
                    pos += 1
                    stack[-1] = (container, 'after_comma', None)
                elif c == '}':
                    pos += 1
                    pending = container
                    has_pending = True
                    stack.pop()
                else:
                    err(f"Expected ',' or '}}', got {c!r}", pos)
            elif state == 'after_comma':
                if c == '"':
                    key = parse_string()
                    stack[-1] = (container, 'after_key', key)
                else:
                    err(f"Expected '\"', got {c!r}", pos)
