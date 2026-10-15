class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


_HEX = frozenset('0123456789abcdefABCDEF')
_WS = frozenset(' \t\n\r')


def _parse_string(s, i, n):
    i += 1
    parts = []
    while True:
        if i >= n:
            raise JSONError("Unexpected end of input in string", n)
        c = s[i]
        if c == '"':
            return ''.join(parts), i + 1
        if c == '\\':
            i += 1
            if i >= n:
                raise JSONError("Unexpected end of input in string", n)
            c = s[i]
            if c == '"':
                parts.append('"'); i += 1
            elif c == '\\':
                parts.append('\\'); i += 1
            elif c == '/':
                parts.append('/'); i += 1
            elif c == 'b':
                parts.append('\b'); i += 1
            elif c == 'f':
                parts.append('\f'); i += 1
            elif c == 'n':
                parts.append('\n'); i += 1
            elif c == 'r':
                parts.append('\r'); i += 1
            elif c == 't':
                parts.append('\t'); i += 1
            elif c == 'u':
                i += 1
                if i + 4 > n:
                    for j in range(i, n):
                        if s[j] not in _HEX:
                            raise JSONError("Invalid hex digit", j)
                    raise JSONError("Unexpected end of input in string", n)
                for j in range(i, i + 4):
                    if s[j] not in _HEX:
                        raise JSONError("Invalid hex digit", j)
                code = (int(s[i], 16) << 12 | int(s[i + 1], 16) << 8 |
                        int(s[i + 2], 16) << 4 | int(s[i + 3], 16))
                i += 4
                if 0xD800 <= code <= 0xDBFF:
                    combined = False
                    if i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u':
                        hs = i + 2
                        ok = True
                        for j in range(hs, hs + 4):
                            if s[j] not in _HEX:
                                ok = False
                                break
                        if ok:
                            code2 = (int(s[hs], 16) << 12 | int(s[hs + 1], 16) << 8 |
                                     int(s[hs + 2], 16) << 4 | int(s[hs + 3], 16))
                            if 0xDC00 <= code2 <= 0xDFFF:
                                cp = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                parts.append(chr(cp))
                                i = hs + 4
                                combined = True
                    if not combined:
                        parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError("Invalid escape", i)
        elif ord(c) < 0x20:
            raise JSONError("Control character in string", i)
        else:
            parts.append(c)
            i += 1


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError("Expected str, got " + type(s).__name__)

    n = len(s)
    i = 0
    while i < n and s[i] in _WS:
        i += 1
    if i >= n:
        raise JSONError("Empty input", n)

    stack = []
    pending_key = None
    result = None
    depth = 0
    state = 'val'

    while True:
        while i < n and s[i] in _WS:
            i += 1

        if state == 'val':
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            c = s[i]
            if c == '[':
                depth += 1
                if depth > 500:
                    raise JSONError("Maximum depth exceeded", i)
                stack.append(('a', []))
                i += 1
                state = 'arr_first'
            elif c == '{':
                depth += 1
                if depth > 500:
                    raise JSONError("Maximum depth exceeded", i)
                stack.append(('o', {}))
                i += 1
                state = 'obj_first'
            elif c == '"':
                val, i = _parse_string(s, i, n)
                if not stack:
                    result = val; state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val); state = 'arr_sep'
                else:
                    stack[-1][1][pending_key] = val; state = 'obj_sep'
            elif c == 't':
                for j in range(4):
                    if i + j >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i + j] != 'true'[j]:
                        raise JSONError("Invalid literal", i + j)
                i += 4
                if not stack:
                    result = True; state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(True); state = 'arr_sep'
                else:
                    stack[-1][1][pending_key] = True; state = 'obj_sep'
            elif c == 'f':
                for j in range(5):
                    if i + j >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i + j] != 'false'[j]:
                        raise JSONError("Invalid literal", i + j)
                i += 5
                if not stack:
                    result = False; state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(False); state = 'arr_sep'
                else:
                    stack[-1][1][pending_key] = False; state = 'obj_sep'
            elif c == 'n':
                for j in range(4):
                    if i + j >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i + j] != 'null'[j]:
                        raise JSONError("Invalid literal", i + j)
                i += 4
                if not stack:
                    result = None; state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(None); state = 'arr_sep'
                else:
                    stack[-1][1][pending_key] = None; state = 'obj_sep'
            elif c == '-' or ('0' <= c <= '9'):
                num_start = i
                if c == '-':
                    i += 1
                    if i >= n:
                        raise JSONError("Unexpected end of input", n)
                c = s[i]
                if c == '0':
                    i += 1
                elif '1' <= c <= '9':
                    i += 1
                    while i < n and '0' <= s[i] <= '9':
                        i += 1
                else:
                    raise JSONError("Invalid number", i)
                is_float = False
                if i < n and s[i] == '.':
                    is_float = True
                    i += 1
                    if i >= n or not ('0' <= s[i] <= '9'):
                        raise JSONError("Invalid number", i)
                    while i < n and '0' <= s[i] <= '9':
                        i += 1
                if i < n and (s[i] == 'e' or s[i] == 'E'):
                    is_float = True
                    i += 1
                    if i < n and (s[i] == '+' or s[i] == '-'):
                        i += 1
                    if i >= n or not ('0' <= s[i] <= '9'):
                        raise JSONError("Invalid number", i)
                    while i < n and '0' <= s[i] <= '9':
                        i += 1
                num_text = s[num_start:i]
                val = float(num_text) if is_float else int(num_text)
                if not stack:
                    result = val; state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val); state = 'arr_sep'
                else:
                    stack[-1][1][pending_key] = val; state = 'obj_sep'
            else:
                raise JSONError("Unexpected character", i)

        elif state == 'arr_first':
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] == ']':
                i += 1
                obj = stack.pop()[1]
                depth -= 1
                if not stack:
                    result = obj; state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(obj); state = 'arr_sep'
                else:
                    stack[-1][1][pending_key] = obj; state = 'obj_sep'
            else:
                state = 'val'

        elif state == 'arr_sep':
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] == ']':
                i += 1
                obj = stack.pop()[1]
                depth -= 1
                if not stack:
                    result = obj; state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(obj); state = 'arr_sep'
                else:
                    stack[-1][1][pending_key] = obj; state = 'obj_sep'
            elif s[i] == ',':
                i += 1
                state = 'val'
            else:
                raise JSONError("Expected ',' or ']'", i)

        elif state == 'obj_first':
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] == '}':
                i += 1
                obj = stack.pop()[1]
                depth -= 1
                if not stack:
                    result = obj; state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(obj); state = 'arr_sep'
                else:
                    stack[-1][1][pending_key] = obj; state = 'obj_sep'
            elif s[i] == '"':
                val, i = _parse_string(s, i, n)
                pending_key = val
                state = 'obj_colon'
            else:
                raise JSONError("Expected key or '}'", i)

        elif state == 'obj_colon':
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] == ':':
                i += 1
                state = 'val'
            else:
                raise JSONError("Expected ':'", i)

        elif state == 'obj_sep':
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] == '}':
                i += 1
                obj = stack.pop()[1]
                depth -= 1
                if not stack:
                    result = obj; state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(obj); state = 'arr_sep'
                else:
                    stack[-1][1][pending_key] = obj; state = 'obj_sep'
            elif s[i] == ',':
                i += 1
                state = 'obj_key'
            else:
                raise JSONError("Expected ',' or '}'", i)

        elif state == 'obj_key':
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] == '"':
                val, i = _parse_string(s, i, n)
                pending_key = val
                state = 'obj_colon'
            else:
                raise JSONError("Expected key", i)

        elif state == 'top_end':
            if i >= n:
                break
            raise JSONError("Trailing data", i)

    return result
