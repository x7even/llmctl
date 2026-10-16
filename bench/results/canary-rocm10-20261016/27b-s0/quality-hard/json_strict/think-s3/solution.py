class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_CONTAINER = object()


def _match_literal(s, i, n, lit):
    ln = len(lit)
    for j in range(ln):
        if i + j >= n:
            raise JSONError("unexpected end of input", n)
        if s[i + j] != lit[j]:
            raise JSONError("invalid literal", i + j)
    return i + ln


def _parse_number(s, i, n):
    start = i
    if i < n and s[i] == '-':
        i += 1
    if i >= n:
        raise JSONError("unexpected end of input", i)
    c = s[i]
    if c == '0':
        i += 1
    elif '1' <= c <= '9':
        i += 1
        while i < n:
            c = s[i]
            if '0' <= c <= '9':
                i += 1
            else:
                break
    else:
        raise JSONError("invalid number", i)
    has_frac = False
    has_exp = False
    if i < n and s[i] == '.':
        has_frac = True
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input", i)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit after '.'", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1
    if i < n and (s[i] == 'e' or s[i] == 'E'):
        has_exp = True
        i += 1
        if i < n and (s[i] == '+' or s[i] == '-'):
            i += 1
        if i >= n:
            raise JSONError("unexpected end of input", i)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit in exponent", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1
    text = s[start:i]
    if has_frac or has_exp:
        return float(text), i
    return int(text), i


def _parse_string(s, i, n):
    # s[i] == '"'
    i += 1
    chars = []
    while True:
        if i >= n:
            raise JSONError("unterminated string", i)
        c = s[i]
        if c == '"':
            i += 1
            return ''.join(chars), i
        elif c == '\\':
            i += 1
            if i >= n:
                raise JSONError("unterminated escape", i)
            ec = s[i]
            if ec == '"':
                chars.append('"'); i += 1
            elif ec == '\\':
                chars.append('\\'); i += 1
            elif ec == '/':
                chars.append('/'); i += 1
            elif ec == 'b':
                chars.append('\b'); i += 1
            elif ec == 'f':
                chars.append('\f'); i += 1
            elif ec == 'n':
                chars.append('\n'); i += 1
            elif ec == 'r':
                chars.append('\r'); i += 1
            elif ec == 't':
                chars.append('\t'); i += 1
            elif ec == 'u':
                i += 1
                # Parse 4 hex digits
                h0 = i
                if i + 4 > n:
                    # find first missing position
                    for j in range(4):
                        if i + j >= n:
                            raise JSONError("truncated \\u escape", i + j)
                for j in range(4):
                    hc = s[i + j]
                    if not ('0' <= hc <= '9' or 'a' <= hc <= 'f' or 'A' <= hc <= 'F'):
                        raise JSONError("invalid hex digit in \\u escape", i + j)
                val = 0
                for j in range(4):
                    hc = s[i + j]
                    if '0' <= hc <= '9':
                        val = val * 16 + (ord(hc) - 48)
                    elif 'a' <= hc <= 'f':
                        val = val * 16 + (ord(hc) - 87)
                    else:
                        val = val * 16 + (ord(hc) - 55)
                i += 4
                # Surrogate pair handling
                if 0xD800 <= val <= 0xDBFF:
                    # High surrogate: check for \uXXXX low surrogate
                    if i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u':
                        lo_ok = True
                        for j in range(4):
                            hc = s[i + 2 + j]
                            if not ('0' <= hc <= '9' or 'a' <= hc <= 'f' or 'A' <= hc <= 'F'):
                                lo_ok = False
                                break
                        if lo_ok:
                            lo_val = 0
                            for j in range(4):
                                hc = s[i + 2 + j]
                                if '0' <= hc <= '9':
                                    lo_val = lo_val * 16 + (ord(hc) - 48)
                                elif 'a' <= hc <= 'f':
                                    lo_val = lo_val * 16 + (ord(hc) - 87)
                                else:
                                    lo_val = lo_val * 16 + (ord(hc) - 55)
                            if 0xDC00 <= lo_val <= 0xDFFF:
                                cp = 0x10000 + ((val - 0xD800) << 10) + (lo_val - 0xDC00)
                                chars.append(chr(cp))
                                i += 6
                                continue
                    # Unpaired high surrogate
                    chars.append(chr(val))
                else:
                    chars.append(chr(val))
            else:
                raise JSONError(f"invalid escape character", i)
        else:
            if ord(c) < 0x20:
                raise JSONError("control character in string", i)
            chars.append(c)
            i += 1


def _parse_value(s, i, n, stack, c):
    if c == '{':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", i)
        stack.append([1, {}, 0, None])
        return _CONTAINER, i + 1
    elif c == '[':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", i)
        stack.append([0, [], 0, None])
        return _CONTAINER, i + 1
    elif c == '"':
        return _parse_string(s, i, n)
    elif c == '-' or ('0' <= c <= '9'):
        return _parse_number(s, i, n)
    elif c == 't':
        i = _match_literal(s, i, n, 'true')
        return True, i
    elif c == 'f':
        i = _match_literal(s, i, n, 'false')
        return False, i
    elif c == 'n':
        i = _match_literal(s, i, n, 'null')
        return None, i
    else:
        raise JSONError(f"unexpected character {c!r}", i)


def _finish(s, i, n, container, stack):
    """After popping a container. Returns final value if top-level, else None."""
    if not stack:
        while i < n and s[i] in ' \t\n\r':
            i += 1
        if i < n:
            raise JSONError("trailing garbage", i)
        return container
    pt, pc, ps, pk = stack[-1]
    if pt == 0:
        pc.append(container)
        stack[-1][2] = 1
    else:
        pc[pk] = container
        stack[-1][2] = 3
    return None


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    i = 0
    # Stack entries: [type, container, state, key]
    # type: 0=array, 1=object
    # Array states: 0=first(value or ]), 1=after_value(, or ]), 2=after_comma(value)
    # Object states: 0=first(" or }), 1=after_key(:), 2=after_colon(value),
    #               3=after_value(, or }), 4=after_comma(")
    stack = []

    while True:
        while i < n and s[i] in ' \t\n\r':
            i += 1
        if i >= n:
            raise JSONError("unexpected end of input", i)
        c = s[i]

        if not stack:
            val, i = _parse_value(s, i, n, stack, c)
            if val is not _CONTAINER:
                while i < n and s[i] in ' \t\n\r':
                    i += 1
                if i < n:
                    raise JSONError("trailing garbage", i)
                return val
        else:
            ftype, container, fstate, fkey = stack[-1]
            if ftype == 0:  # array
                if fstate == 0:
                    if c == ']':
                        stack.pop()
                        i += 1
                        r = _finish(s, i, n, container, stack)
                        if r is not None:
                            return r
                    else:
                        val, i = _parse_value(s, i, n, stack, c)
                        if val is not _CONTAINER:
                            container.append(val)
                            stack[-1][2] = 1
                elif fstate == 1:
                    if c == ']':
                        stack.pop()
                        i += 1
                        r = _finish(s, i, n, container, stack)
                        if r is not None:
                            return r
                    elif c == ',':
                        stack[-1][2] = 2
                        i += 1
                    else:
                        raise JSONError("expected ',' or ']'", i)
                else:  # fstate == 2
                    val, i = _parse_value(s, i, n, stack, c)
                    if val is not _CONTAINER:
                        container.append(val)
                        stack[-1][2] = 1
            else:  # object
                if fstate == 0:
                    if c == '}':
                        stack.pop()
                        i += 1
                        r = _finish(s, i, n, container, stack)
                        if r is not None:
                            return r
                    elif c == '"':
                        key, i = _parse_string(s, i, n)
                        stack[-1][2] = 1
                        stack[-1][3] = key
                    else:
                        raise JSONError("expected string key or '}'", i)
                elif fstate == 1:
                    if c == ':':
                        stack[-1][2] = 2
                        i += 1
                    else:
                        raise JSONError("expected ':'", i)
                elif fstate == 2:
                    val, i = _parse_value(s, i, n, stack, c)
                    if val is not _CONTAINER:
                        container[stack[-1][3]] = val
                        stack[-1][2] = 3
                elif fstate == 3:
                    if c == '}':
                        stack.pop()
                        i += 1
                        r = _finish(s, i, n, container, stack)
                        if r is not None:
                            return r
                    elif c == ',':
                        stack[-1][2] = 4
                        i += 1
                    else:
                        raise JSONError("expected ',' or '}'", i)
                else:  # fstate == 4
                    if c == '"':
                        key, i = _parse_string(s, i, n)
                        stack[-1][2] = 1
                        stack[-1][3] = key
                    else:
                        raise JSONError("expected string key", i)
