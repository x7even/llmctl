class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def _parse_number(s, i, n):
    start = i
    if s[i] == '-':
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if s[i] < '0' or s[i] > '9':
            raise JSONError("expected digit after '-'", i)

    if s[i] == '0':
        i += 1
        if i < n and '0' <= s[i] <= '9':
            raise JSONError("leading zero not allowed", i)
    else:
        while i < n and '0' <= s[i] <= '9':
            i += 1

    has_frac = False
    has_exp = False

    if i < n and s[i] == '.':
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if s[i] < '0' or s[i] > '9':
            raise JSONError("expected digit after '.'", i)
        has_frac = True
        while i < n and '0' <= s[i] <= '9':
            i += 1

    if i < n and (s[i] == 'e' or s[i] == 'E'):
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if s[i] == '+' or s[i] == '-':
            i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
        if i >= n or s[i] < '0' or s[i] > '9':
            raise JSONError("expected digit in exponent", i)
        has_exp = True
        while i < n and '0' <= s[i] <= '9':
            i += 1

    text = s[start:i]
    if has_frac or has_exp:
        return float(text), i
    else:
        return int(text), i


def _parse_string(s, i, n):
    # s[i] == '"'
    i += 1
    chars = []
    hex_set = frozenset('0123456789abcdefABCDEF')

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
                    raise JSONError("unexpected end of input", n)
                code = 0
                for k in range(4):
                    ch = s[i + k]
                    if ch not in hex_set:
                        raise JSONError("invalid hex digit in \\u escape", i + k)
                    if '0' <= ch <= '9':
                        d = ord(ch) - 48
                    elif 'a' <= ch <= 'f':
                        d = ord(ch) - 87
                    else:
                        d = ord(ch) - 55
                    code = code * 16 + d
                i += 4

                if 0xD800 <= code <= 0xDBFF:
                    # High surrogate: check for \uXXXX low surrogate
                    if i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u':
                        code2 = 0
                        valid = True
                        for k in range(4):
                            ch = s[i + 2 + k]
                            if ch not in hex_set:
                                valid = False
                                break
                            if '0' <= ch <= '9':
                                d = ord(ch) - 48
                            elif 'a' <= ch <= 'f':
                                d = ord(ch) - 87
                            else:
                                d = ord(ch) - 55
                            code2 = code2 * 16 + d
                        if valid and 0xDC00 <= code2 <= 0xDFFF:
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
            raise JSONError("control character in string", i)

        else:
            chars.append(c)
            i += 1


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    i = 0
    MAX_DEPTH = 500
    depth = 0

    # Stack frames: [type, container, pending_key]
    # type: 0 = array, 1 = object
    stack = []

    # States
    VALUE = 0
    KEY = 1
    COLON = 2
    END = 3
    ARR_FIRST = 4
    ARR_SEP = 5
    OBJ_FIRST = 6
    OBJ_SEP = 7

    state = VALUE
    result = None
    ws = ' \t\n\r'

    while True:
        # Skip whitespace
        while i < n and s[i] in ws:
            i += 1

        if i >= n:
            if state == END:
                return result
            raise JSONError("unexpected end of input", n)

        c = s[i]

        if state == VALUE or state == ARR_FIRST:
            if state == ARR_FIRST and c == ']':
                i += 1
                depth -= 1
                frame = stack.pop()
                val = frame[1]
                if stack:
                    pf = stack[-1]
                    if pf[0] == 0:
                        pf[1].append(val)
                        state = ARR_SEP
                    else:
                        pf[1][pf[2]] = val
                        state = OBJ_SEP
                else:
                    result = val
                    state = END
                continue

            if c == 'n':
                if i + 4 <= n and s[i+1] == 'u' and s[i+2] == 'l' and s[i+3] == 'l':
                    i += 4
                    val = None
                else:
                    tgt = 'null'
                    for j in range(1, 4):
                        if i + j >= n:
                            raise JSONError("unexpected end of input", n)
                        if s[i + j] != tgt[j]:
                            raise JSONError("invalid literal", i + j)
                    raise JSONError("invalid literal", i + 1)
            elif c == 't':
                if i + 4 <= n and s[i+1] == 'r' and s[i+2] == 'u' and s[i+3] == 'e':
                    i += 4
                    val = True
                else:
                    tgt = 'true'
                    for j in range(1, 4):
                        if i + j >= n:
                            raise JSONError("unexpected end of input", n)
                        if s[i + j] != tgt[j]:
                            raise JSONError("invalid literal", i + j)
                    raise JSONError("invalid literal", i + 1)
            elif c == 'f':
                if i + 5 <= n and s[i+1] == 'a' and s[i+2] == 'l' and s[i+3] == 's' and s[i+4] == 'e':
                    i += 5
                    val = False
                else:
                    tgt = 'false'
                    for j in range(1, 5):
                        if i + j >= n:
                            raise JSONError("unexpected end of input", n)
                        if s[i + j] != tgt[j]:
                            raise JSONError("invalid literal", i + j)
                    raise JSONError("invalid literal", i + 1)
            elif c == '"':
                val, i = _parse_string(s, i, n)
            elif c == '[':
                if depth >= MAX_DEPTH:
                    raise JSONError("maximum nesting depth exceeded", i)
                i += 1
                depth += 1
                stack.append([0, [], None])
                state = ARR_FIRST
                continue
            elif c == '{':
                if depth >= MAX_DEPTH:
                    raise JSONError("maximum nesting depth exceeded", i)
                i += 1
                depth += 1
                stack.append([1, {}, None])
                state = OBJ_FIRST
                continue
            elif c == '-' or ('0' <= c <= '9'):
                val, i = _parse_number(s, i, n)
            else:
                raise JSONError("unexpected character", i)

            # Value parsed, update state based on parent
            if stack:
                pf = stack[-1]
                if pf[0] == 0:
                    pf[1].append(val)
                    state = ARR_SEP
                else:
                    pf[1][pf[2]] = val
                    state = OBJ_SEP
            else:
                result = val
                state = END

        elif state == KEY or state == OBJ_FIRST:
            if state == OBJ_FIRST and c == '}':
                i += 1
                depth -= 1
                frame = stack.pop()
                val = frame[1]
                if stack:
                    pf = stack[-1]
                    if pf[0] == 0:
                        pf[1].append(val)
                        state = ARR_SEP
                    else:
                        pf[1][pf[2]] = val
                        state = OBJ_SEP
                else:
                    result = val
                    state = END
                continue

            if c != '"':
                raise JSONError("expected string key", i)
            key, i = _parse_string(s, i, n)
            stack[-1][2] = key
            state = COLON

        elif state == COLON:
            if c != ':':
                raise JSONError("expected ':'", i)
            i += 1
            state = VALUE

        elif state == ARR_SEP:
            if c == ',':
                i += 1
                state = VALUE
            elif c == ']':
                i += 1
                depth -= 1
                frame = stack.pop()
                val = frame[1]
                if stack:
                    pf = stack[-1]
                    if pf[0] == 0:
                        pf[1].append(val)
                        state = ARR_SEP
                    else:
                        pf[1][pf[2]] = val
                        state = OBJ_SEP
                else:
                    result = val
                    state = END
            else:
                raise JSONError("expected ',' or ']'", i)

        elif state == OBJ_SEP:
            if c == ',':
                i += 1
                state = KEY
            elif c == '}':
                i += 1
                depth -= 1
                frame = stack.pop()
                val = frame[1]
                if stack:
                    pf = stack[-1]
                    if pf[0] == 0:
                        pf[1].append(val)
                        state = ARR_SEP
                    else:
                        pf[1][pf[2]] = val
                        state = OBJ_SEP
                else:
                    result = val
                    state = END
            else:
                raise JSONError("expected ',' or '}'", i)

        elif state == END:
            raise JSONError("trailing characters", i)
