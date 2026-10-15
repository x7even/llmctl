class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def _parse_string(s: str, n: int, i: int):
    """Parse a JSON string starting at s[i] == '"'. Returns (value, new_i)."""
    i += 1  # skip opening quote
    parts = []
    while True:
        if i >= n:
            raise JSONError("unexpected end of string", n)
        ch = s[i]
        if ch == '"':
            i += 1
            return ''.join(parts), i
        elif ch == '\\':
            i += 1
            if i >= n:
                raise JSONError("unexpected end of string", n)
            ch = s[i]
            if ch == '"':
                parts.append('"'); i += 1
            elif ch == '\\':
                parts.append('\\'); i += 1
            elif ch == '/':
                parts.append('/'); i += 1
            elif ch == 'b':
                parts.append('\b'); i += 1
            elif ch == 'f':
                parts.append('\f'); i += 1
            elif ch == 'n':
                parts.append('\n'); i += 1
            elif ch == 'r':
                parts.append('\r'); i += 1
            elif ch == 't':
                parts.append('\t'); i += 1
            elif ch == 'u':
                i += 1
                if i + 4 > n:
                    raise JSONError("unexpected end of string", n)
                cp = 0
                for j in range(4):
                    hc = s[i + j]
                    if '0' <= hc <= '9':
                        d = ord(hc) - 48
                    elif 'a' <= hc <= 'f':
                        d = ord(hc) - 87
                    elif 'A' <= hc <= 'F':
                        d = ord(hc) - 55
                    else:
                        raise JSONError("invalid hex digit", i + j)
                    cp = cp * 16 + d
                i += 4
                if 0xD800 <= cp <= 0xDBFF:
                    if (i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u'):
                        lo = 0
                        valid = True
                        for j in range(4):
                            hc = s[i + 2 + j]
                            if '0' <= hc <= '9':
                                d = ord(hc) - 48
                            elif 'a' <= hc <= 'f':
                                d = ord(hc) - 87
                            elif 'A' <= hc <= 'F':
                                d = ord(hc) - 55
                            else:
                                valid = False
                                break
                            lo = lo * 16 + d
                        if valid and 0xDC00 <= lo <= 0xDFFF:
                            combined = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                            parts.append(chr(combined))
                            i += 6
                            continue
                    parts.append(chr(cp))
                else:
                    parts.append(chr(cp))
            else:
                raise JSONError("invalid escape character", i)
        elif ord(ch) < 0x20:
            raise JSONError("control character in string", i)
        else:
            parts.append(ch)
            i += 1


def _parse_number(s: str, n: int, i: int):
    """Parse a JSON number starting at s[i]. Returns (value, new_i)."""
    start = i
    if s[i] == '-':
        i += 1
    if i >= n:
        raise JSONError("unexpected end of input", n)
    if s[i] == '0':
        i += 1
    elif '1' <= s[i] <= '9':
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1
    else:
        raise JSONError("expected digit", i)

    is_float = False

    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    if i < n and s[i] in 'eE':
        is_float = True
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    text = s[start:i]
    if is_float:
        return float(text), i
    return int(text), i


def _match_literal(s: str, n: int, i: int, word: str):
    """Match a literal word. Returns new_i."""
    for expected in word:
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if s[i] != expected:
            raise JSONError("unexpected character", i)
        i += 1
    return i


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}"
        )

    n = len(s)
    i = 0

    # Stack entries: [type, container, key]
    # type: 0 = array, 1 = object
    stack = []
    result = None

    # States
    _VALUE, _ARRAY_FIRST, _ARRAY_COMMA, _OBJ_START, _OBJ_COLON, _OBJ_COMMA, _OBJ_KEY, _DONE = range(8)
    state = _VALUE

    while True:
        if state == _VALUE:
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]

            if c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append([0, [], None])
                i += 1
                state = _ARRAY_FIRST

            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append([1, {}, None])
                i += 1
                state = _OBJ_START

            elif c == '"':
                val, i = _parse_string(s, n, i)
                if not stack:
                    result = val
                    state = _DONE
                else:
                    entry = stack[-1]
                    if entry[0] == 0:
                        entry[1].append(val)
                        state = _ARRAY_COMMA
                    else:
                        entry[1][entry[2]] = val
                        state = _OBJ_COMMA

            elif c == '-' or '0' <= c <= '9':
                val, i = _parse_number(s, n, i)
                if not stack:
                    result = val
                    state = _DONE
                else:
                    entry = stack[-1]
                    if entry[0] == 0:
                        entry[1].append(val)
                        state = _ARRAY_COMMA
                    else:
                        entry[1][entry[2]] = val
                        state = _OBJ_COMMA

            elif c == 't':
                i = _match_literal(s, n, i, 'true')
                val = True
                if not stack:
                    result = val
                    state = _DONE
                else:
                    entry = stack[-1]
                    if entry[0] == 0:
                        entry[1].append(val)
                        state = _ARRAY_COMMA
                    else:
                        entry[1][entry[2]] = val
                        state = _OBJ_COMMA

            elif c == 'f':
                i = _match_literal(s, n, i, 'false')
                val = False
                if not stack:
                    result = val
                    state = _DONE
                else:
                    entry = stack[-1]
                    if entry[0] == 0:
                        entry[1].append(val)
                        state = _ARRAY_COMMA
                    else:
                        entry[1][entry[2]] = val
                        state = _OBJ_COMMA

            elif c == 'n':
                i = _match_literal(s, n, i, 'null')
                val = None
                if not stack:
                    result = val
                    state = _DONE
                else:
                    entry = stack[-1]
                    if entry[0] == 0:
                        entry[1].append(val)
                        state = _ARRAY_COMMA
                    else:
                        entry[1][entry[2]] = val
                        state = _OBJ_COMMA

            else:
                raise JSONError("unexpected character", i)

        elif state == _ARRAY_FIRST:
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ']':
                i += 1
                entry = stack.pop()
                val = entry[1]
                if not stack:
                    result = val
                    state = _DONE
                else:
                    parent = stack[-1]
                    if parent[0] == 0:
                        parent[1].append(val)
                        state = _ARRAY_COMMA
                    else:
                        parent[1][parent[2]] = val
                        state = _OBJ_COMMA
            else:
                state = _VALUE

        elif state == _ARRAY_COMMA:
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == ',':
                i += 1
                state = _VALUE
            elif c == ']':
                i += 1
                entry = stack.pop()
                val = entry[1]
                if not stack:
                    result = val
                    state = _DONE
                else:
                    parent = stack[-1]
                    if parent[0] == 0:
                        parent[1].append(val)
                        state = _ARRAY_COMMA
                    else:
                        parent[1][parent[2]] = val
                        state = _OBJ_COMMA
            else:
                raise JSONError("expected , or ]", i)

        elif state == _OBJ_START:
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '}':
                i += 1
                entry = stack.pop()
                val = entry[1]
                if not stack:
                    result = val
                    state = _DONE
                else:
                    parent = stack[-1]
                    if parent[0] == 0:
                        parent[1].append(val)
                        state = _ARRAY_COMMA
                    else:
                        parent[1][parent[2]] = val
                        state = _OBJ_COMMA
            elif c == '"':
                key, i = _parse_string(s, n, i)
                stack[-1][2] = key
                state = _OBJ_COLON
            else:
                raise JSONError("expected key or }", i)

        elif state == _OBJ_COLON:
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ':':
                i += 1
                state = _VALUE
            else:
                raise JSONError("expected :", i)

        elif state == _OBJ_COMMA:
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == ',':
                i += 1
                state = _OBJ_KEY
            elif c == '}':
                i += 1
                entry = stack.pop()
                val = entry[1]
                if not stack:
                    result = val
                    state = _DONE
                else:
                    parent = stack[-1]
                    if parent[0] == 0:
                        parent[1].append(val)
                        state = _ARRAY_COMMA
                    else:
                        parent[1][parent[2]] = val
                        state = _OBJ_COMMA
            else:
                raise JSONError("expected , or }", i)

        elif state == _OBJ_KEY:
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == '"':
                key, i = _parse_string(s, n, i)
                stack[-1][2] = key
                state = _OBJ_COLON
            else:
                raise JSONError("expected key", i)

        elif state == _DONE:
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i < n:
                raise JSONError("trailing garbage", i)
            return result
