class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    MAX_DEPTH = 500
    _WS = ' \t\n\r'
    _DIGITS = frozenset('0123456789')
    _HEX = frozenset('0123456789abcdefABCDEF')

    def err(msg, p):
        raise JSONError(msg, p)

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in _WS:
            pos += 1

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening quote
        chars = []
        while True:
            if pos >= n:
                err("unterminated string", pos)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            if c == '\\':
                pos += 1
                if pos >= n:
                    err("unterminated escape sequence", pos)
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
                        for i in range(n - pos):
                            if s[pos + i] not in _HEX:
                                err("invalid unicode escape", pos + i)
                        err("unterminated unicode escape", n)
                    hex_str = s[pos:pos + 4]
                    for i, hc in enumerate(hex_str):
                        if hc not in _HEX:
                            err("invalid unicode escape", pos + i)
                    code = int(hex_str, 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            hex2 = s[pos + 2:pos + 6]
                            if all(hc in _HEX for hc in hex2):
                                code2 = int(hex2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    code = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    pos += 6
                    chars.append(chr(code))
                else:
                    err(f"invalid escape character", pos)
            else:
                if ord(c) < 0x20:
                    err("unescaped control character in string", pos)
                chars.append(c)
                pos += 1

    def parse_number():
        nonlocal pos
        start = pos
        if s[pos] == '-':
            pos += 1
        if pos >= n:
            err("unexpected end of input", pos)
        c = s[pos]
        if c == '0':
            pos += 1
            if pos < n and s[pos] in _DIGITS:
                err("leading zero in number", pos)
        elif c in _DIGITS:
            pos += 1
            while pos < n and s[pos] in _DIGITS:
                pos += 1
        else:
            err("invalid number", pos)
        if pos < n and s[pos] == '.':
            pos += 1
            if pos >= n or s[pos] not in _DIGITS:
                err("invalid number: expected digit after '.'", pos)
            while pos < n and s[pos] in _DIGITS:
                pos += 1
        if pos < n and s[pos] in 'eE':
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n or s[pos] not in _DIGITS:
                err("invalid number: expected digit in exponent", pos)
            while pos < n and s[pos] in _DIGITS:
                pos += 1
        if pos < n and s[pos] in '0123456789.eE':
            err("invalid number: unexpected character after number", pos)
        text = s[start:pos]
        if '.' in text or 'e' in text or 'E' in text:
            return float(text)
        return int(text)

    def match_literal(literal):
        nonlocal pos
        for i, ch in enumerate(literal):
            if pos + i >= n:
                err("unexpected end of input", pos + i)
            if s[pos + i] != ch:
                err("invalid literal", pos + i)
        pos += len(literal)

    # --- Main iterative parser ---
    stack = []  # entries: [type, container]; type 0=array, 1=object
    pending_key = None
    state = 'value'
    result = None

    def handle_value(val):
        nonlocal state, pending_key, result
        if not stack:
            result = val
            state = 'end'
        else:
            typ, container = stack[-1]
            if typ == 0:
                container.append(val)
                state = 'array_sep'
            else:
                container[pending_key] = val
                pending_key = None
                state = 'obj_sep'

    def close_container():
        nonlocal result
        result = stack.pop()[1]
        handle_value(result)

    while True:
        skip_ws()

        if state == 'end':
            if pos < n:
                err("trailing characters after top-level value", pos)
            return result

        if pos >= n:
            err("unexpected end of input", pos)

        c = s[pos]

        if state == 'value' or state == 'array_first':
            if c == '[':
                if len(stack) >= MAX_DEPTH:
                    err("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append([0, []])
                state = 'array_first'
            elif c == '{':
                if len(stack) >= MAX_DEPTH:
                    err("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append([1, {}])
                state = 'obj_key_first'
            elif c == '"':
                val = parse_string()
                handle_value(val)
            elif c == 't':
                match_literal('true')
                handle_value(True)
            elif c == 'f':
                match_literal('false')
                handle_value(False)
            elif c == 'n':
                match_literal('null')
                handle_value(None)
            elif c == '-' or c in _DIGITS:
                val = parse_number()
                handle_value(val)
            elif state == 'array_first' and c == ']':
                pos += 1
                close_container()
            else:
                err(f"unexpected character {c!r}", pos)

        elif state == 'array_sep':
            if c == ',':
                pos += 1
                state = 'value'
            elif c == ']':
                pos += 1
                close_container()
            else:
                err(f"unexpected character {c!r}", pos)

        elif state == 'obj_key_first':
            if c == '}':
                pos += 1
                close_container()
            elif c == '"':
                pending_key = parse_string()
                state = 'colon'
            else:
                err(f"unexpected character {c!r}", pos)

        elif state == 'obj_key':
            if c == '"':
                pending_key = parse_string()
                state = 'colon'
            else:
                err(f"unexpected character {c!r}", pos)

        elif state == 'colon':
            if c == ':':
                pos += 1
                state = 'value'
            else:
                err(f"unexpected character {c!r}", pos)

        elif state == 'obj_sep':
            if c == ',':
                pos += 1
                state = 'obj_key'
            elif c == '}':
                pos += 1
                close_container()
            else:
                err(f"unexpected character {c!r}", pos)
