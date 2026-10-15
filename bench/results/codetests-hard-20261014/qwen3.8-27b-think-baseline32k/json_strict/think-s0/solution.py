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

    # Stack frames: [type, data, key]
    #   type: 0 = array, 1 = object
    #   data: list or dict
    #   key:  current key for object (None for arrays / not yet set)
    stack = []

    # States
    #   'value'            – expecting a JSON value
    #   'value_or_arr_end' – expecting a value or ']' (first slot in array)
    #   'key_or_obj_end'   – expecting '"' or '}' (first slot in object)
    #   'key'              – expecting '"' (after comma in object)
    #   'colon'            – expecting ':'
    #   'comma_or_arr_end' – expecting ',' or ']'
    #   'comma_or_obj_end' – expecting ',' or '}'
    #   'end'              – expecting EOF
    state = 'value'
    result = None

    WS = ' \t\n\r'
    DIGITS = '0123456789'
    HEX = '0123456789abcdefABCDEF'

    while True:
        # Skip whitespace
        while pos < n and s[pos] in WS:
            pos += 1

        if state == 'end':
            if pos < n:
                raise JSONError("Trailing data", pos)
            return result

        if pos >= n:
            raise JSONError("Unexpected end of input", n)

        c = s[pos]

        if state == 'value' or state == 'value_or_arr_end':
            if state == 'value_or_arr_end' and c == ']':
                pos += 1
                value = stack.pop()[1]
                if not stack:
                    result = value
                    state = 'end'
                else:
                    ptype, pdata, pkey = stack[-1]
                    if ptype == 0:
                        pdata.append(value)
                        state = 'comma_or_arr_end'
                    else:
                        pdata[pkey] = value
                        state = 'comma_or_obj_end'
                continue

            if c == '[':
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos)
                stack.append([0, [], None])
                pos += 1
                state = 'value_or_arr_end'

            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos)
                stack.append([1, {}, None])
                pos += 1
                state = 'key_or_obj_end'

            elif c == '"':
                value, pos = _parse_string(s, pos, n, HEX)
                if not stack:
                    result = value
                    state = 'end'
                else:
                    ptype, pdata, pkey = stack[-1]
                    if ptype == 0:
                        pdata.append(value)
                        state = 'comma_or_arr_end'
                    else:
                        pdata[pkey] = value
                        state = 'comma_or_obj_end'

            elif c == 't':
                if pos + 3 < n and s[pos+1] == 'r' and s[pos+2] == 'u' and s[pos+3] == 'e':
                    pos += 4
                    value = True
                elif pos + 1 >= n:
                    raise JSONError("Unexpected end of input", n)
                elif s[pos+1] != 'r':
                    raise JSONError("Invalid literal", pos + 1)
                elif pos + 2 >= n:
                    raise JSONError("Unexpected end of input", n)
                elif s[pos+2] != 'u':
                    raise JSONError("Invalid literal", pos + 2)
                else:
                    raise JSONError("Unexpected end of input", n)
                if not stack:
                    result = value
                    state = 'end'
                else:
                    ptype, pdata, pkey = stack[-1]
                    if ptype == 0:
                        pdata.append(value)
                        state = 'comma_or_arr_end'
                    else:
                        pdata[pkey] = value
                        state = 'comma_or_obj_end'

            elif c == 'f':
                if (pos + 4 < n and s[pos+1] == 'a' and s[pos+2] == 'l'
                        and s[pos+3] == 's' and s[pos+4] == 'e'):
                    pos += 5
                    value = False
                elif pos + 1 >= n:
                    raise JSONError("Unexpected end of input", n)
                elif s[pos+1] != 'a':
                    raise JSONError("Invalid literal", pos + 1)
                elif pos + 2 >= n:
                    raise JSONError("Unexpected end of input", n)
                elif s[pos+2] != 'l':
                    raise JSONError("Invalid literal", pos + 2)
                elif pos + 3 >= n:
                    raise JSONError("Unexpected end of input", n)
                elif s[pos+3] != 's':
                    raise JSONError("Invalid literal", pos + 3)
                else:
                    raise JSONError("Unexpected end of input", n)
                if not stack:
                    result = value
                    state = 'end'
                else:
                    ptype, pdata, pkey = stack[-1]
                    if ptype == 0:
                        pdata.append(value)
                        state = 'comma_or_arr_end'
                    else:
                        pdata[pkey] = value
                        state = 'comma_or_obj_end'

            elif c == 'n':
                if pos + 3 < n and s[pos+1] == 'u' and s[pos+2] == 'l' and s[pos+3] == 'l':
                    pos += 4
                    value = None
                elif pos + 1 >= n:
                    raise JSONError("Unexpected end of input", n)
                elif s[pos+1] != 'u':
                    raise JSONError("Invalid literal", pos + 1)
                elif pos + 2 >= n:
                    raise JSONError("Unexpected end of input", n)
                elif s[pos+2] != 'l':
                    raise JSONError("Invalid literal", pos + 2)
                else:
                    raise JSONError("Unexpected end of input", n)
                if not stack:
                    result = value
                    state = 'end'
                else:
                    ptype, pdata, pkey = stack[-1]
                    if ptype == 0:
                        pdata.append(value)
                        state = 'comma_or_arr_end'
                    else:
                        pdata[pkey] = value
                        state = 'comma_or_obj_end'

            elif c == '-' or c in DIGITS:
                value, pos = _parse_number(s, pos, n)
                if not stack:
                    result = value
                    state = 'end'
                else:
                    ptype, pdata, pkey = stack[-1]
                    if ptype == 0:
                        pdata.append(value)
                        state = 'comma_or_arr_end'
                    else:
                        pdata[pkey] = value
                        state = 'comma_or_obj_end'

            else:
                raise JSONError(f"Unexpected character {c!r}", pos)

        elif state == 'key_or_obj_end':
            if c == '}':
                pos += 1
                value = stack.pop()[1]
                if not stack:
                    result = value
                    state = 'end'
                else:
                    ptype, pdata, pkey = stack[-1]
                    if ptype == 0:
                        pdata.append(value)
                        state = 'comma_or_arr_end'
                    else:
                        pdata[pkey] = value
                        state = 'comma_or_obj_end'
            elif c == '"':
                key, pos = _parse_string(s, pos, n, HEX)
                stack[-1][2] = key
                state = 'colon'
            else:
                raise JSONError("Expected string key or '}'", pos)

        elif state == 'key':
            if c == '"':
                key, pos = _parse_string(s, pos, n, HEX)
                stack[-1][2] = key
                state = 'colon'
            else:
                raise JSONError("Expected string key", pos)

        elif state == 'colon':
            if c == ':':
                pos += 1
                state = 'value'
            else:
                raise JSONError("Expected ':'", pos)

        elif state == 'comma_or_arr_end':
            if c == ',':
                pos += 1
                state = 'value'
            elif c == ']':
                pos += 1
                value = stack.pop()[1]
                if not stack:
                    result = value
                    state = 'end'
                else:
                    ptype, pdata, pkey = stack[-1]
                    if ptype == 0:
                        pdata.append(value)
                        state = 'comma_or_arr_end'
                    else:
                        pdata[pkey] = value
                        state = 'comma_or_obj_end'
            else:
                raise JSONError("Expected ',' or ']'", pos)

        elif state == 'comma_or_obj_end':
            if c == ',':
                pos += 1
                state = 'key'
            elif c == '}':
                pos += 1
                value = stack.pop()[1]
                if not stack:
                    result = value
                    state = 'end'
                else:
                    ptype, pdata, pkey = stack[-1]
                    if ptype == 0:
                        pdata.append(value)
                        state = 'comma_or_arr_end'
                    else:
                        pdata[pkey] = value
                        state = 'comma_or_obj_end'
            else:
                raise JSONError("Expected ',' or '}'", pos)


def _parse_string(s, pos, n, HEX):
    """Parse a JSON string starting at s[pos] == '"'. Returns (value, new_pos)."""
    pos += 1  # skip opening quote
    parts = []

    while pos < n:
        c = s[pos]
        if c == '"':
            pos += 1
            return ''.join(parts), pos
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input in string escape", n)
            esc = s[pos]
            if esc == '"':
                parts.append('"')
                pos += 1
            elif esc == '\\':
                parts.append('\\')
                pos += 1
            elif esc == '/':
                parts.append('/')
                pos += 1
            elif esc == 'b':
                parts.append('\b')
                pos += 1
            elif esc == 'f':
                parts.append('\f')
                pos += 1
            elif esc == 'n':
                parts.append('\n')
                pos += 1
            elif esc == 'r':
                parts.append('\r')
                pos += 1
            elif esc == 't':
                parts.append('\t')
                pos += 1
            elif esc == 'u':
                # Need exactly 4 hex digits at positions pos+1 .. pos+4
                if pos + 4 >= n:
                    raise JSONError("Unexpected end of input in \\u escape", n)
                h1 = s[pos+1]
                h2 = s[pos+2]
                h3 = s[pos+3]
                h4 = s[pos+4]
                if h1 not in HEX:
                    raise JSONError("Invalid hex digit in \\u escape", pos + 1)
                if h2 not in HEX:
                    raise JSONError("Invalid hex digit in \\u escape", pos + 2)
                if h3 not in HEX:
                    raise JSONError("Invalid hex digit in \\u escape", pos + 3)
                if h4 not in HEX:
                    raise JSONError("Invalid hex digit in \\u escape", pos + 4)
                code = int(s[pos+1:pos+5], 16)
                pos += 5

                # Surrogate pair: high surrogate immediately followed by \uXXXX low surrogate
                if 0xD800 <= code <= 0xDBFF:
                    if (pos + 5 < n and s[pos] == '\\' and s[pos+1] == 'u'
                            and s[pos+2] in HEX and s[pos+3] in HEX
                            and s[pos+4] in HEX and s[pos+5] in HEX):
                        code2 = int(s[pos+2:pos+6], 16)
                        if 0xDC00 <= code2 <= 0xDFFF:
                            combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            parts.append(chr(combined))
                            pos += 6
                            continue
                    # Lone high surrogate
                    parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError(f"Invalid escape character", pos)
        elif ord(c) < 0x20:
            raise JSONError("Unescaped control character in string", pos)
        else:
            parts.append(c)
            pos += 1

    raise JSONError("Unexpected end of input in string", n)


def _parse_number(s, pos, n):
    """Parse a JSON number starting at s[pos]. Returns (value, new_pos)."""
    start = pos

    # Optional minus
    if s[pos] == '-':
        pos += 1
        if pos >= n:
            raise JSONError("Unexpected end of input in number", n)

    # Integer part
    if s[pos] == '0':
        pos += 1
        if pos < n and s[pos] in '0123456789':
            raise JSONError("Leading zero in number", pos)
    elif s[pos] in '123456789':
        pos += 1
        while pos < n and s[pos] in '0123456789':
            pos += 1
    else:
        raise JSONError("Invalid number", pos)

    has_fraction = False
    has_exponent = False

    # Fractional part
    if pos < n and s[pos] == '.':
        has_fraction = True
        pos += 1
        if pos >= n:
            raise JSONError("Unexpected end of input in number", n)
        if s[pos] not in '0123456789':
            raise JSONError("Expected digit after '.'", pos)
        while pos < n and s[pos] in '0123456789':
            pos += 1

    # Exponent part
    if pos < n and s[pos] in 'eE':
        has_exponent = True
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n:
            raise JSONError("Unexpected end of input in number", n)
        if s[pos] not in '0123456789':
            raise JSONError("Expected digit in exponent", pos)
        while pos < n and s[pos] in '0123456789':
            pos += 1

    num_str = s[start:pos]

    if has_fraction or has_exponent:
        return float(num_str), pos
    else:
        return int(num_str), pos
