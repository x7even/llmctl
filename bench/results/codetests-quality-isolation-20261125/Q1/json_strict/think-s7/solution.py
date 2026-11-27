class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    i = 0
    depth = 0
    stack = []  # frames: ('a', list) or ('o', dict, key)
    result = None

    # State constants
    VALUE = 0
    A_FIRST = 1
    A_COE = 2
    A_NEXT = 3
    O_FIRST = 4
    O_COLON = 5
    O_VALUE = 6
    O_COE = 7
    O_NEXT_KEY = 8
    DONE = 9

    state = VALUE
    ws = ' \t\n\r'

    while True:
        # Skip whitespace
        while i < n and s[i] in ws:
            i += 1

        if i >= n:
            if state == DONE:
                return result
            raise JSONError("unexpected end of input", n)

        c = s[i]

        if state == VALUE or state == A_FIRST or state == A_NEXT or state == O_VALUE:
            # In A_FIRST, ']' closes an empty array
            if state == A_FIRST and c == ']':
                i += 1
                _, container = stack.pop()
                depth -= 1
                if not stack:
                    result = container
                    state = DONE
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 'a':
                        pc.append(container)
                        state = A_COE
                    else:
                        pc[pkey] = container
                        state = O_COE
                continue

            if c == '[':
                if depth >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                depth += 1
                i += 1
                stack.append(('a', []))
                state = A_FIRST
            elif c == '{':
                if depth >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                depth += 1
                i += 1
                stack.append(('o', {}, None))
                state = O_FIRST
            elif c == '"':
                val, i = _parse_string(s, i, n)
                if not stack:
                    result = val
                    state = DONE
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 'a':
                        pc.append(val)
                        state = A_COE
                    else:
                        pc[pkey] = val
                        state = O_COE
            elif c == 't':
                if i + 4 <= n and s[i + 1] == 'r' and s[i + 2] == 'u' and s[i + 3] == 'e':
                    i += 4
                    val = True
                else:
                    for k in range(1, 4):
                        if i + k >= n:
                            raise JSONError("unexpected end of input", n)
                        if s[i + k] != 'true'[k]:
                            raise JSONError("invalid literal", i + k)
                    raise JSONError("unexpected end of input", n)
                if not stack:
                    result = val
                    state = DONE
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 'a':
                        pc.append(val)
                        state = A_COE
                    else:
                        pc[pkey] = val
                        state = O_COE
            elif c == 'f':
                if (i + 5 <= n and s[i + 1] == 'a' and s[i + 2] == 'l'
                        and s[i + 3] == 's' and s[i + 4] == 'e'):
                    i += 5
                    val = False
                else:
                    for k in range(1, 5):
                        if i + k >= n:
                            raise JSONError("unexpected end of input", n)
                        if s[i + k] != 'false'[k]:
                            raise JSONError("invalid literal", i + k)
                    raise JSONError("unexpected end of input", n)
                if not stack:
                    result = val
                    state = DONE
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 'a':
                        pc.append(val)
                        state = A_COE
                    else:
                        pc[pkey] = val
                        state = O_COE
            elif c == 'n':
                if (i + 4 <= n and s[i + 1] == 'u' and s[i + 2] == 'l'
                        and s[i + 3] == 'l'):
                    i += 4
                    val = None
                else:
                    for k in range(1, 4):
                        if i + k >= n:
                            raise JSONError("unexpected end of input", n)
                        if s[i + k] != 'null'[k]:
                            raise JSONError("invalid literal", i + k)
                    raise JSONError("unexpected end of input", n)
                if not stack:
                    result = val
                    state = DONE
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 'a':
                        pc.append(val)
                        state = A_COE
                    else:
                        pc[pkey] = val
                        state = O_COE
            elif c == '-' or '0' <= c <= '9':
                val, i = _parse_number(s, i, n)
                if not stack:
                    result = val
                    state = DONE
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 'a':
                        pc.append(val)
                        state = A_COE
                    else:
                        pc[pkey] = val
                        state = O_COE
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == A_COE:
            if c == ',':
                i += 1
                state = A_NEXT
            elif c == ']':
                i += 1
                _, container = stack.pop()
                depth -= 1
                if not stack:
                    result = container
                    state = DONE
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 'a':
                        pc.append(container)
                        state = A_COE
                    else:
                        pc[pkey] = container
                        state = O_COE
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == O_FIRST:
            if c == '}':
                i += 1
                _, container, _ = stack.pop()
                depth -= 1
                if not stack:
                    result = container
                    state = DONE
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 'a':
                        pc.append(container)
                        state = A_COE
                    else:
                        pc[pkey] = container
                        state = O_COE
            elif c == '"':
                key, i = _parse_string(s, i, n)
                stack[-1] = ('o', stack[-1][1], key)
                state = O_COLON
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == O_COLON:
            if c == ':':
                i += 1
                state = O_VALUE
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == O_COE:
            if c == ',':
                i += 1
                state = O_NEXT_KEY
            elif c == '}':
                i += 1
                _, container, _ = stack.pop()
                depth -= 1
                if not stack:
                    result = container
                    state = DONE
                else:
                    pk, pc, pkey = stack[-1]
                    if pk == 'a':
                        pc.append(container)
                        state = A_COE
                    else:
                        pc[pkey] = container
                        state = O_COE
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == O_NEXT_KEY:
            if c == '"':
                key, i = _parse_string(s, i, n)
                stack[-1] = ('o', stack[-1][1], key)
                state = O_COLON
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == DONE:
            raise JSONError(f"trailing garbage: {c!r}", i)


def _parse_string(s, i, n):
    """Parse a JSON string starting at s[i] == '"'. Returns (str, new_i)."""
    i += 1  # skip opening quote
    chars = []
    hexd = '0123456789abcdefABCDEF'

    while True:
        if i >= n:
            raise JSONError("unexpected end of input", n)
        c = s[i]

        if c == '"':
            i += 1
            return ''.join(chars), i
        elif c == '\\':
            i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            e = s[i]
            if e == '"':
                chars.append('"')
                i += 1
            elif e == '\\':
                chars.append('\\')
                i += 1
            elif e == '/':
                chars.append('/')
                i += 1
            elif e == 'b':
                chars.append('\b')
                i += 1
            elif e == 'f':
                chars.append('\f')
                i += 1
            elif e == 'n':
                chars.append('\n')
                i += 1
            elif e == 'r':
                chars.append('\r')
                i += 1
            elif e == 't':
                chars.append('\t')
                i += 1
            elif e == 'u':
                i += 1
                if i + 4 > n:
                    raise JSONError("unexpected end of input", n)
                h = s[i:i + 4]
                for k in range(4):
                    if h[k] not in hexd:
                        raise JSONError("invalid unicode escape", i + k)
                code = int(h, 16)
                i += 4

                if 0xD800 <= code <= 0xDBFF:
                    # High surrogate: check for immediately following \uXXXX low surrogate
                    if (i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u'):
                        lh = s[i + 2:i + 6]
                        valid = True
                        for k in range(4):
                            if lh[k] not in hexd:
                                valid = False
                                break
                        if valid:
                            lcode = int(lh, 16)
                            if 0xDC00 <= lcode <= 0xDFFF:
                                cp = 0x10000 + ((code - 0xD800) << 10) + (lcode - 0xDC00)
                                chars.append(chr(cp))
                                i += 6
                                continue
                chars.append(chr(code))
            else:
                raise JSONError(f"invalid escape \\{e}", i)
        elif ord(c) < 0x20:
            raise JSONError("control character in string", i)
        else:
            chars.append(c)
            i += 1


def _parse_number(s, i, n):
    """Parse a JSON number starting at s[i]. Returns (int|float, new_i)."""
    start = i
    is_float = False

    # Optional minus
    if i < n and s[i] == '-':
        i += 1

    # Integer part
    if i >= n:
        raise JSONError("unexpected end of input", n)
    c = s[i]
    if c == '0':
        i += 1
    elif '1' <= c <= '9':
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1
    else:
        raise JSONError("invalid number", i)

    # Fraction
    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    # Exponent
    if i < n and s[i] in 'eE':
        is_float = True
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    text = s[start:i]
    if is_float:
        return float(text), i
    else:
        return int(text), i
