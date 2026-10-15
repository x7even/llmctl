class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_HEX = frozenset('0123456789abcdefABCDEF')
_WS = ' \t\n\r'


def _parse_string(s, i, n):
    """Parse a JSON string starting at s[i] == '"'. Returns (value, new_i)."""
    i += 1  # skip opening quote
    parts = []
    while True:
        if i >= n:
            raise JSONError("unexpected end of input in string", n)
        c = s[i]
        if c == '"':
            i += 1
            return ''.join(parts), i
        elif c == '\\':
            i += 1
            if i >= n:
                raise JSONError("unexpected end of input in string escape", n)
            ec = s[i]
            if ec == '"':
                parts.append('"')
                i += 1
            elif ec == '\\':
                parts.append('\\')
                i += 1
            elif ec == '/':
                parts.append('/')
                i += 1
            elif ec == 'b':
                parts.append('\b')
                i += 1
            elif ec == 'f':
                parts.append('\f')
                i += 1
            elif ec == 'n':
                parts.append('\n')
                i += 1
            elif ec == 'r':
                parts.append('\r')
                i += 1
            elif ec == 't':
                parts.append('\t')
                i += 1
            elif ec == 'u':
                i += 1
                if i + 4 > n:
                    raise JSONError("unexpected end of input in \\u escape", n)
                h = s[i:i + 4]
                for j, hc in enumerate(h):
                    if hc not in _HEX:
                        raise JSONError("invalid hex digit in \\u escape", i + j)
                code = int(h, 16)
                i += 4
                # Surrogate pair handling
                if 0xD800 <= code <= 0xDBFF:
                    if i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u':
                        h2 = s[i + 2:i + 6]
                        valid = True
                        for hc in h2:
                            if hc not in _HEX:
                                valid = False
                                break
                        if valid:
                            code2 = int(h2, 16)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                code = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                i += 6
                parts.append(chr(code))
            else:
                raise JSONError(f"invalid escape character {ec!r}", i)
        elif ord(c) < 0x20:
            raise JSONError("raw control character in string", i)
        else:
            parts.append(c)
            i += 1


def _parse_number(s, i, n):
    """Parse a JSON number starting at s[i]. Returns (value, new_i)."""
    start = i
    # Optional minus
    if s[i] == '-':
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input in number", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit after '-'", i)
    # Integer part
    if s[i] == '0':
        i += 1
    else:
        while i < n and '0' <= s[i] <= '9':
            i += 1
    is_float = False
    # Fraction
    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input in number", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit after '.'", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1
    # Exponent
    if i < n and s[i] in 'eE':
        is_float = True
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n:
            raise JSONError("unexpected end of input in number", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit in exponent", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1
    text = s[start:i]
    if is_float:
        return float(text), i
    else:
        return int(text), i


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    i = 0

    # Stack frames: [kind, container, key]
    # kind: 0 = array, 1 = object
    stack = []

    # States: 'value', 'key', 'colon', 'after_value', 'end'
    state = 'value'
    result = None

    while True:
        # Skip whitespace
        while i < n and s[i] in _WS:
            i += 1

        if state == 'value':
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]

            if c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                i += 1
                stack.append([1, {}, None])
                while i < n and s[i] in _WS:
                    i += 1
                if i < n and s[i] == '}':
                    i += 1
                    obj = stack.pop()[1]
                    if not stack:
                        result = obj
                        state = 'end'
                    else:
                        pk, pc, pkey = stack[-1]
                        if pk == 0:
                            pc.append(obj)
                        else:
                            pc[pkey] = obj
                        state = 'after_value'
                else:
                    state = 'key'

            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                i += 1
                stack.append([0, [], None])
                while i < n and s[i] in _WS:
                    i += 1
                if i < n and s[i] == ']':
                    i += 1
                    arr = stack.pop()[1]
                    if not stack:
                        result = arr
                        state = 'end'
                    else:
                        pk, pc, pkey = stack[-1]
                        if pk == 0:
                            pc.append(arr)
                        else:
                            pc[pkey] = arr
                        state = 'after_value'
                else:
                    state = 'value'

            elif c == '"':
                val, i = _parse_string(s, i, n)
                if not stack:
                    result = val
                    state = 'end'
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 0:
                        pc.append(val)
                    else:
                        pc[pkey] = val
                    state = 'after_value'

            elif c == '-' or ('0' <= c <= '9'):
                val, i = _parse_number(s, i, n)
                if not stack:
                    result = val
                    state = 'end'
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 0:
                        pc.append(val)
                    else:
                        pc[pkey] = val
                    state = 'after_value'

            elif c == 't':
                if i + 4 <= n and s[i + 1] == 'u' and s[i + 2] == 'r' and s[i + 3] == 'e':
                    i += 4
                    val = True
                else:
                    if i + 1 >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + 1] != 'u':
                        raise JSONError("invalid literal 'true'", i + 1)
                    if i + 2 >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + 2] != 'r':
                        raise JSONError("invalid literal 'true'", i + 2)
                    if i + 3 >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + 3] != 'e':
                        raise JSONError("invalid literal 'true'", i + 3)
                if not stack:
                    result = val
                    state = 'end'
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 0:
                        pc.append(val)
                    else:
                        pc[pkey] = val
                    state = 'after_value'

            elif c == 'f':
                if (i + 5 <= n and s[i + 1] == 'a' and s[i + 2] == 'l'
                        and s[i + 3] == 's' and s[i + 4] == 'e'):
                    i += 5
                    val = False
                else:
                    if i + 1 >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + 1] != 'a':
                        raise JSONError("invalid literal 'false'", i + 1)
                    if i + 2 >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + 2] != 'l':
                        raise JSONError("invalid literal 'false'", i + 2)
                    if i + 3 >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + 3] != 's':
                        raise JSONError("invalid literal 'false'", i + 3)
                    if i + 4 >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + 4] != 'e':
                        raise JSONError("invalid literal 'false'", i + 4)
                if not stack:
                    result = val
                    state = 'end'
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 0:
                        pc.append(val)
                    else:
                        pc[pkey] = val
                    state = 'after_value'

            elif c == 'n':
                if i + 4 <= n and s[i + 1] == 'u' and s[i + 2] == 'l' and s[i + 3] == 'l':
                    i += 4
                    val = None
                else:
                    if i + 1 >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + 1] != 'u':
                        raise JSONError("invalid literal 'null'", i + 1)
                    if i + 2 >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + 2] != 'l':
                        raise JSONError("invalid literal 'null'", i + 2)
                    if i + 3 >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + 3] != 'l':
                        raise JSONError("invalid literal 'null'", i + 3)
                if not stack:
                    result = val
                    state = 'end'
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 0:
                        pc.append(val)
                    else:
                        pc[pkey] = val
                    state = 'after_value'

            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == 'key':
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '"':
                key, i = _parse_string(s, i, n)
                stack[-1][2] = key
                state = 'colon'
            else:
                raise JSONError(f"expected string key, got {c!r}", i)

        elif state == 'colon':
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == ':':
                i += 1
                state = 'value'
            else:
                raise JSONError(f"expected ':', got {c!r}", i)

        elif state == 'after_value':
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            kind, container, key = stack[-1]
            if kind == 0:  # array
                if c == ',':
                    i += 1
                    state = 'value'
                elif c == ']':
                    i += 1
                    arr = stack.pop()[1]
                    if not stack:
                        result = arr
                        state = 'end'
                    else:
                        pk, pc, pkey = stack[-1]
                        if pk == 0:
                            pc.append(arr)
                        else:
                            pc[pkey] = arr
                        state = 'after_value'
                else:
                    raise JSONError(f"expected ',' or ']', got {c!r}", i)
            else:  # object
                if c == ',':
                    i += 1
                    state = 'key'
                elif c == '}':
                    i += 1
                    obj = stack.pop()[1]
                    if not stack:
                        result = obj
                        state = 'end'
                    else:
                        pk, pc, pkey = stack[-1]
                        if pk == 0:
                            pc.append(obj)
                        else:
                            pc[pkey] = obj
                        state = 'after_value'
                else:
                    raise JSONError(f"expected ',' or '}}', got {c!r}", i)

        elif state == 'end':
            if i >= n:
                return result
            else:
                raise JSONError(f"trailing garbage", i)

    # Unreachable
