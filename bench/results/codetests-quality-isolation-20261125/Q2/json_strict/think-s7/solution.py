class JSONError(ValueError):
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    i = 0

    # States:
    #   'value'            – top level, expecting a value
    #   'top_end'          – top level, expecting end of input
    #   'arr_value_or_end' – in array (after '['), expecting value or ']'
    #   'arr_value'        – in array (after ','), expecting value
    #   'arr_comma_or_end' – in array (after value), expecting ',' or ']'
    #   'obj_key_or_end'   – in object (after '{'), expecting string key or '}'
    #   'obj_key'          – in object (after ','), expecting string key
    #   'obj_colon'        – in object (after key), expecting ':'
    #   'obj_value'        – in object (after ':'), expecting value
    #   'obj_comma_or_end' – in object (after value), expecting ',' or '}'

    stack = []          # list of (container, state)
    state = 'value'
    pending_key = None
    current_value = None

    WS = ' \t\n\r'
    HEX = set('0123456789abcdefABCDEF')

    def skip_ws():
        nonlocal i
        while i < n and s[i] in WS:
            i += 1

    def parse_hex4(pos):
        """Parse exactly 4 hex digits starting at pos. Returns (code, new_pos) or raises."""
        code = 0
        for j in range(4):
            idx = pos + j
            if idx >= n:
                raise JSONError("truncated \\u escape", n)
            hc = s[idx]
            if '0' <= hc <= '9':
                code = code * 16 + (ord(hc) - 48)
            elif 'a' <= hc <= 'f':
                code = code * 16 + (ord(hc) - 87)
            elif 'A' <= hc <= 'F':
                code = code * 16 + (ord(hc) - 55)
            else:
                raise JSONError("invalid hex digit in \\u escape", idx)
        return code, pos + 4

    def parse_string():
        nonlocal i
        # i points to opening '"'
        i += 1
        chars = []
        while True:
            if i >= n:
                raise JSONError("unterminated string", i)
            c = s[i]
            if c == '"':
                i += 1
                break
            if c == '\\':
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
                    code, i = parse_hex4(i)
                    if 0xD800 <= code <= 0xDBFF:
                        # High surrogate: check for immediately following \uXXXX low surrogate
                        if (i + 5 < n and s[i] == '\\' and s[i + 1] == 'u'):
                            code2, _ = parse_hex4(i + 2)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(combined))
                                i += 6
                                continue
                        # Lone high surrogate
                        chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    raise JSONError("invalid escape character", i)
            elif ord(c) < 0x20:
                raise JSONError("raw control character in string", i)
            else:
                chars.append(c)
                i += 1
        return ''.join(chars)

    def parse_number():
        nonlocal i
        start = i
        # Optional minus
        if i < n and s[i] == '-':
            i += 1
        # Integer part
        if i >= n:
            raise JSONError("truncated number", i)
        c = s[i]
        if c == '0':
            i += 1
        elif '1' <= c <= '9':
            i += 1
            while i < n and '0' <= s[i] <= '9':
                i += 1
        else:
            raise JSONError("invalid number", i)

        has_fraction = False
        has_exponent = False

        # Fraction
        if i < n and s[i] == '.':
            i += 1
            if i >= n or not ('0' <= s[i] <= '9'):
                raise JSONError("expected digit after decimal point", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1
            has_fraction = True

        # Exponent
        if i < n and s[i] in 'eE':
            i += 1
            if i < n and s[i] in '+-':
                i += 1
            if i >= n or not ('0' <= s[i] <= '9'):
                raise JSONError("expected digit in exponent", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1
            has_exponent = True

        text = s[start:i]
        if has_fraction or has_exponent:
            return float(text)
        else:
            return int(text)

    def parse_literal(expected, value):
        nonlocal i
        ln = len(expected)
        if i + ln > n:
            raise JSONError("truncated literal", n)
        for j in range(ln):
            if s[i + j] != expected[j]:
                raise JSONError("invalid literal", i + j)
        i += ln
        return value

    def place_value(value):
        nonlocal state, pending_key, current_value
        if not stack:
            current_value = value
            state = 'top_end'
        else:
            parent, pstate = stack[-1]
            if pstate == 'arr_value_or_end' or pstate == 'arr_value':
                parent.append(value)
                stack[-1] = (parent, 'arr_comma_or_end')
                state = 'arr_comma_or_end'
            elif pstate == 'obj_value':
                parent[pending_key] = value
                pending_key = None
                stack[-1] = (parent, 'obj_comma_or_end')
                state = 'obj_comma_or_end'

    def pop_container():
        nonlocal state, pending_key, current_value
        container, _ = stack.pop()
        place_value(container)

    def push_container(container, new_state):
        nonlocal state
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", i)
        stack.append((container, new_state))
        state = new_state

    def try_parse_value():
        """Attempt to parse a value starting at position i. Returns True if a value was parsed."""
        nonlocal i, state, pending_key
        c = s[i]
        if c == '"':
            val = parse_string()
            place_value(val)
        elif c == '-' or ('0' <= c <= '9'):
            val = parse_number()
            place_value(val)
        elif c == 't':
            val = parse_literal('true', True)
            place_value(val)
        elif c == 'f':
            val = parse_literal('false', False)
            place_value(val)
        elif c == 'n':
            val = parse_literal('null', None)
            place_value(val)
        elif c == '[':
            i += 1
            push_container([], 'arr_value_or_end')
        elif c == '{':
            i += 1
            push_container({}, 'obj_key_or_end')
        else:
            return False
        return True

    # Main loop
    while True:
        skip_ws()

        if state == 'top_end':
            if i >= n:
                return current_value
            else:
                raise JSONError("trailing garbage", i)

        if i >= n:
            raise JSONError("unexpected end of input", i)

        c = s[i]

        if state == 'value':
            if not try_parse_value():
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == 'arr_value_or_end':
            if c == ']':
                i += 1
                pop_container()
            elif not try_parse_value():
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == 'arr_value':
            if not try_parse_value():
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == 'arr_comma_or_end':
            if c == ',':
                i += 1
                state = 'arr_value'
            elif c == ']':
                i += 1
                pop_container()
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == 'obj_key_or_end':
            if c == '}':
                i += 1
                pop_container()
            elif c == '"':
                pending_key = parse_string()
                state = 'obj_colon'
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == 'obj_key':
            if c == '"':
                pending_key = parse_string()
                state = 'obj_colon'
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == 'obj_colon':
            if c == ':':
                i += 1
                state = 'obj_value'
            else:
                raise JSONError(f"expected ':' but got {c!r}", i)

        elif state == 'obj_value':
            if not try_parse_value():
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == 'obj_comma_or_end':
            if c == ',':
                i += 1
                state = 'obj_key'
            elif c == '}':
                i += 1
                pop_container()
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        else:
            raise JSONError(f"internal error: unexpected state {state}", i)
