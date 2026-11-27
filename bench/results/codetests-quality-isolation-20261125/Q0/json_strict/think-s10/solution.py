class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")

    n = len(s)
    i = 0
    stack = []  # list of (type_str, container)
    state = 'value'
    current_key = None
    result = None

    WS = ' \t\n\r'
    HEX = frozenset('0123456789abcdefABCDEF')

    def parse_string(start):
        nonlocal i
        i = start + 1
        chars = []
        while True:
            if i >= n:
                raise JSONError("unexpected end of string", n)
            c = s[i]
            if c == '"':
                i += 1
                return ''.join(chars)
            elif c == '\\':
                i += 1
                if i >= n:
                    raise JSONError("unexpected end of string", n)
                esc = s[i]
                if esc == '"':
                    chars.append('"')
                    i += 1
                elif esc == '\\':
                    chars.append('\\')
                    i += 1
                elif esc == '/':
                    chars.append('/')
                    i += 1
                elif esc == 'b':
                    chars.append('\b')
                    i += 1
                elif esc == 'f':
                    chars.append('\f')
                    i += 1
                elif esc == 'n':
                    chars.append('\n')
                    i += 1
                elif esc == 'r':
                    chars.append('\r')
                    i += 1
                elif esc == 't':
                    chars.append('\t')
                    i += 1
                elif esc == 'u':
                    i += 1
                    if i + 4 > n:
                        raise JSONError("invalid \\u escape", n)
                    hex_str = s[i:i + 4]
                    for j in range(4):
                        if hex_str[j] not in HEX:
                            raise JSONError("invalid hex digit in \\u escape", i + j)
                    code = int(hex_str, 16)
                    i += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u':
                            hex2 = s[i + 2:i + 6]
                            valid = True
                            for hc in hex2:
                                if hc not in HEX:
                                    valid = False
                                    break
                            if valid:
                                code2 = int(hex2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    chars.append(chr(combined))
                                    i += 6
                                    continue
                    chars.append(chr(code))
                else:
                    raise JSONError(f"invalid escape '\\{esc}'", i)
            else:
                if ord(c) < 0x20:
                    raise JSONError("unescaped control character in string", i)
                chars.append(c)
                i += 1

    def parse_number(start):
        nonlocal i
        i = start
        if s[i] == '-':
            i += 1
        if i >= n:
            raise JSONError("unexpected end of number", n)
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

        has_fraction = False
        if i < n and s[i] == '.':
            has_fraction = True
            i += 1
            if i >= n or not ('0' <= s[i] <= '9'):
                raise JSONError("expected digit after '.'", i if i < n else n)
            while i < n and '0' <= s[i] <= '9':
                i += 1

        has_exponent = False
        if i < n and s[i] in 'eE':
            has_exponent = True
            i += 1
            if i < n and s[i] in '+-':
                i += 1
            if i >= n or not ('0' <= s[i] <= '9'):
                raise JSONError("expected digit in exponent", i if i < n else n)
            while i < n and '0' <= s[i] <= '9':
                i += 1

        text = s[start:i]
        if has_fraction or has_exponent:
            return float(text)
        return int(text)

    def parse_literal(start, expected):
        nonlocal i
        for j in range(len(expected)):
            if start + j >= n:
                raise JSONError("unexpected end of input", n)
            if s[start + j] != expected[j]:
                raise JSONError(f"invalid literal, expected '{expected}'", start + j)
        i = start + len(expected)

    def store_value(val):
        nonlocal result, state
        if not stack:
            result = val
            state = 'end'
        elif stack[-1][0] == 'array':
            stack[-1][1].append(val)
            state = 'array_sep'
        else:
            stack[-1][1][current_key] = val
            state = 'object_sep'

    def close_container():
        _, container = stack.pop()
        store_value(container)

    while True:
        while i < n and s[i] in WS:
            i += 1

        if state == 'end':
            if i >= n:
                return result
            raise JSONError("trailing characters after JSON value", i)

        if i >= n:
            raise JSONError("unexpected end of input", n)

        c = s[i]

        if state == 'value' or state == 'value_or_array_end':
            if state == 'value_or_array_end' and c == ']':
                i += 1
                close_container()
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(('array', []))
                i += 1
                state = 'value_or_array_end'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(('object', {}))
                i += 1
                state = 'key_or_object_end'
            elif c == '"':
                val = parse_string(i)
                store_value(val)
            elif c == 't':
                parse_literal(i, 'true')
                store_value(True)
            elif c == 'f':
                parse_literal(i, 'false')
                store_value(False)
            elif c == 'n':
                parse_literal(i, 'null')
                store_value(None)
            elif c == '-' or '0' <= c <= '9':
                val = parse_number(i)
                store_value(val)
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == 'key_or_object_end':
            if c == '}':
                i += 1
                close_container()
            elif c == '"':
                current_key = parse_string(i)
                state = 'colon'
            else:
                raise JSONError(f"expected string key or '}}'", i)

        elif state == 'key':
            if c == '"':
                current_key = parse_string(i)
                state = 'colon'
            else:
                raise JSONError(f"expected string key", i)

        elif state == 'colon':
            if c == ':':
                i += 1
                state = 'value'
            else:
                raise JSONError(f"expected ':'", i)

        elif state == 'array_sep':
            if c == ',':
                i += 1
                state = 'value'
            elif c == ']':
                i += 1
                close_container()
            else:
                raise JSONError(f"expected ',' or ']'", i)

        elif state == 'object_sep':
            if c == ',':
                i += 1
                state = 'key'
            elif c == '}':
                i += 1
                close_container()
            else:
                raise JSONError(f"expected ',' or '}}'", i)
