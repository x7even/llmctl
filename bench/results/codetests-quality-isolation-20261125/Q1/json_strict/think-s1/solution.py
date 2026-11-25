class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")

    n = len(s)
    pos = 0
    WS = ' \t\n\r'
    HEX = '0123456789abcdefABCDEF'

    def _skip_ws():
        nonlocal pos
        while pos < n and s[pos] in WS:
            pos += 1

    def _parse_string():
        nonlocal pos
        pos += 1
        chars = []
        while True:
            if pos >= n:
                raise JSONError("unterminated string", n)
            ch = s[pos]
            if ch == '"':
                pos += 1
                return ''.join(chars)
            elif ch == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unterminated string", n)
                esc = s[pos]
                if esc == '"':
                    chars.append('"'); pos += 1
                elif esc == '\\':
                    chars.append('\\'); pos += 1
                elif esc == '/':
                    chars.append('/'); pos += 1
                elif esc == 'b':
                    chars.append('\b'); pos += 1
                elif esc == 'f':
                    chars.append('\f'); pos += 1
                elif esc == 'n':
                    chars.append('\n'); pos += 1
                elif esc == 'r':
                    chars.append('\r'); pos += 1
                elif esc == 't':
                    chars.append('\t'); pos += 1
                elif esc == 'u':
                    if pos + 4 >= n:
                        raise JSONError("unterminated unicode escape", n)
                    h1, h2, h3, h4 = s[pos+1], s[pos+2], s[pos+3], s[pos+4]
                    if h1 not in HEX:
                        raise JSONError("invalid unicode escape", pos + 1)
                    if h2 not in HEX:
                        raise JSONError("invalid unicode escape", pos + 2)
                    if h3 not in HEX:
                        raise JSONError("invalid unicode escape", pos + 3)
                    if h4 not in HEX:
                        raise JSONError("invalid unicode escape", pos + 4)
                    code = (int(h1, 16) << 12) | (int(h2, 16) << 8) | (int(h3, 16) << 4) | int(h4, 16)
                    pos += 5
                    if 0xD800 <= code <= 0xDBFF:
                        if pos + 5 <= n and s[pos] == '\\' and s[pos+1] == 'u':
                            l1, l2, l3, l4 = s[pos+2], s[pos+3], s[pos+4], s[pos+5]
                            if l1 in HEX and l2 in HEX and l3 in HEX and l4 in HEX:
                                code2 = (int(l1, 16) << 12) | (int(l2, 16) << 8) | (int(l3, 16) << 4) | int(l4, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    cp = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    chars.append(chr(cp))
                                    pos += 6
                                    continue
                    chars.append(chr(code))
                else:
                    raise JSONError("invalid escape", pos)
            elif ord(ch) < 0x20:
                raise JSONError("control character in string", pos)
            else:
                chars.append(ch)
                pos += 1

    def _parse_number():
        nonlocal pos
        start = pos
        is_float = False
        if s[pos] == '-':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
        if s[pos] == '0':
            pos += 1
        elif '1' <= s[pos] <= '9':
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            raise JSONError("invalid number", pos)
        if pos < n and s[pos] == '.':
            pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                raise JSONError("invalid number", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
            is_float = True
        if pos < n and s[pos] in 'eE':
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                raise JSONError("invalid number", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
            is_float = True
        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def _parse_literal(expected, value):
        nonlocal pos
        ln = len(expected)
        for i in range(1, ln):
            if pos + i >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos + i] != expected[i]:
                raise JSONError("invalid literal", pos + i)
        pos += ln
        return value

    # Stack frames: [type, container, state, key]
    #   type: 0=array, 1=object
    #   state:
    #     array:  0=after [ (expect val or ]), 1=after val (expect , or ]), 2=after , (expect val)
    #     object: 0=after { (expect " or }), 1=after key (expect :), 2=after : (expect val),
    #             3=after val (expect , or }), 4=after , (expect ")
    #   key: current key for object (None for array)
    stack = []
    result = None
    top_done = False

    while True:
        _skip_ws()

        if pos >= n:
            if not stack and top_done:
                return result
            raise JSONError("unexpected end of input", n)

        ch = s[pos]

        if not stack:
            # --- Top level ---
            if top_done:
                raise JSONError("trailing garbage", pos)
            if ch == '[':
                if len(stack) >= 500:
                    raise JSONError("nesting too deep", pos)
                pos += 1
                stack.append([0, [], 0, None])
            elif ch == '{':
                if len(stack) >= 500:
                    raise JSONError("nesting too deep", pos)
                pos += 1
                stack.append([1, {}, 0, None])
            elif ch == '"':
                result = _parse_string()
                top_done = True
            elif ch == 't':
                result = _parse_literal('true', True)
                top_done = True
            elif ch == 'f':
                result = _parse_literal('false', False)
                top_done = True
            elif ch == 'n':
                result = _parse_literal('null', None)
                top_done = True
            elif ch == '-' or ('0' <= ch <= '9'):
                result = _parse_number()
                top_done = True
            else:
                raise JSONError("unexpected character", pos)

        else:
            frame = stack[-1]
            ftype = frame[0]
            container = frame[1]
            state = frame[2]

            if ftype == 0:
                # --- Array ---
                if state == 0 or state == 2:
                    # Expect a value (state 0: after [, state 2: after ,)
                    if ch == ']':
                        if state == 2:
                            raise JSONError("unexpected character", pos)
                        pos += 1
                        stack.pop()
                        if not stack:
                            result = container; top_done = True
                        else:
                            parent = stack[-1]
                            if parent[0] == 0:
                                parent[1].append(container); parent[2] = 1
                            else:
                                parent[1][parent[3]] = container; parent[2] = 3
                    elif ch == '[':
                        if len(stack) >= 500:
                            raise JSONError("nesting too deep", pos)
                        pos += 1
                        stack.append([0, [], 0, None])
                    elif ch == '{':
                        if len(stack) >= 500:
                            raise JSONError("nesting too deep", pos)
                        pos += 1
                        stack.append([1, {}, 0, None])
                    elif ch == '"':
                        val = _parse_string()
                        container.append(val); frame[2] = 1
                    elif ch == 't':
                        val = _parse_literal('true', True)
                        container.append(val); frame[2] = 1
                    elif ch == 'f':
                        val = _parse_literal('false', False)
                        container.append(val); frame[2] = 1
                    elif ch == 'n':
                        val = _parse_literal('null', None)
                        container.append(val); frame[2] = 1
                    elif ch == '-' or ('0' <= ch <= '9'):
                        val = _parse_number()
                        container.append(val); frame[2] = 1
                    else:
                        raise JSONError("unexpected character", pos)
                else:
                    # state == 1: after value, expect , or ]
                    if ch == ']':
                        pos += 1
                        stack.pop()
                        if not stack:
                            result = container; top_done = True
                        else:
                            parent = stack[-1]
                            if parent[0] == 0:
                                parent[1].append(container); parent[2] = 1
                            else:
                                parent[1][parent[3]] = container; parent[2] = 3
                    elif ch == ',':
                        pos += 1
                        frame[2] = 2
                    else:
                        raise JSONError("unexpected character", pos)

            else:
                # --- Object ---
                if state == 0:
                    # After {, expect " or }
                    if ch == '}':
                        pos += 1
                        stack.pop()
                        if not stack:
                            result = container; top_done = True
                        else:
                            parent = stack[-1]
                            if parent[0] == 0:
                                parent[1].append(container); parent[2] = 1
                            else:
                                parent[1][parent[3]] = container; parent[2] = 3
                    elif ch == '"':
                        key = _parse_string()
                        frame[2] = 1; frame[3] = key
                    else:
                        raise JSONError("unexpected character", pos)
                elif state == 1:
                    # After key, expect :
                    if ch == ':':
                        pos += 1
                        frame[2] = 2
                    else:
                        raise JSONError("unexpected character", pos)
                elif state == 2:
                    # After :, expect value
                    if ch == '[':
                        if len(stack) >= 500:
                            raise JSONError("nesting too deep", pos)
                        pos += 1
                        stack.append([0, [], 0, None])
                    elif ch == '{':
                        if len(stack) >= 500:
                            raise JSONError("nesting too deep", pos)
                        pos += 1
                        stack.append([1, {}, 0, None])
                    elif ch == '"':
                        val = _parse_string()
                        container[frame[3]] = val; frame[2] = 3
                    elif ch == 't':
                        val = _parse_literal('true', True)
                        container[frame[3]] = val; frame[2] = 3
                    elif ch == 'f':
                        val = _parse_literal('false', False)
                        container[frame[3]] = val; frame[2] = 3
                    elif ch == 'n':
                        val = _parse_literal('null', None)
                        container[frame[3]] = val; frame[2] = 3
                    elif ch == '-' or ('0' <= ch <= '9'):
                        val = _parse_number()
                        container[frame[3]] = val; frame[2] = 3
                    else:
                        raise JSONError("unexpected character", pos)
                elif state == 3:
                    # After value, expect , or }
                    if ch == '}':
                        pos += 1
                        stack.pop()
                        if not stack:
                            result = container; top_done = True
                        else:
                            parent = stack[-1]
                            if parent[0] == 0:
                                parent[1].append(container); parent[2] = 1
                            else:
                                parent[1][parent[3]] = container; parent[2] = 3
                    elif ch == ',':
                        pos += 1
                        frame[2] = 4
                    else:
                        raise JSONError("unexpected character", pos)
                else:
                    # state == 4: after comma, expect "
                    if ch == '"':
                        key = _parse_string()
                        frame[2] = 1; frame[3] = key
                    else:
                        raise JSONError("unexpected character", pos)