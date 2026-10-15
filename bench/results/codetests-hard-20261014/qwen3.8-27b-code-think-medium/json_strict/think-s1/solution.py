class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []  # frames: [type, result, key]; type 'a'=array, 'o'=object
    state = 'value'
    WS = ' \t\n\r'
    HEX = frozenset('0123456789abcdefABCDEF')

    while True:
        while pos < n and s[pos] in WS:
            pos += 1

        if pos >= n:
            raise JSONError("unexpected end of input", pos)

        ch = s[pos]

        # --- close containers ---
        if state == 'array_first' and ch == ']':
            pos += 1
            _, result, _ = stack.pop()
            if not stack:
                while pos < n and s[pos] in WS:
                    pos += 1
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return result
            frame = stack[-1]
            if frame[0] == 'a':
                frame[1].append(result)
                state = 'array_sep'
            else:
                frame[1][frame[2]] = result
                state = 'obj_sep'
            continue

        if state == 'array_sep' and ch == ']':
            pos += 1
            _, result, _ = stack.pop()
            if not stack:
                while pos < n and s[pos] in WS:
                    pos += 1
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return result
            frame = stack[-1]
            if frame[0] == 'a':
                frame[1].append(result)
                state = 'array_sep'
            else:
                frame[1][frame[2]] = result
                state = 'obj_sep'
            continue

        if state == 'obj_first' and ch == '}':
            pos += 1
            _, result, _ = stack.pop()
            if not stack:
                while pos < n and s[pos] in WS:
                    pos += 1
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return result
            frame = stack[-1]
            if frame[0] == 'a':
                frame[1].append(result)
                state = 'array_sep'
            else:
                frame[1][frame[2]] = result
                state = 'obj_sep'
            continue

        if state == 'obj_sep' and ch == '}':
            pos += 1
            _, result, _ = stack.pop()
            if not stack:
                while pos < n and s[pos] in WS:
                    pos += 1
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return result
            frame = stack[-1]
            if frame[0] == 'a':
                frame[1].append(result)
                state = 'array_sep'
            else:
                frame[1][frame[2]] = result
                state = 'obj_sep'
            continue

        # --- separators / punctuation ---
        if state == 'array_sep' and ch == ',':
            pos += 1
            state = 'value'
            continue

        if state == 'obj_sep' and ch == ',':
            pos += 1
            state = 'obj_key'
            continue

        if state == 'obj_colon' and ch == ':':
            pos += 1
            state = 'value'
            continue

        # --- object keys ---
        if state == 'obj_first' and ch == '"':
            key, pos = _parse_string(s, pos, n, HEX)
            stack[-1][2] = key
            state = 'obj_colon'
            continue

        if state == 'obj_key' and ch == '"':
            key, pos = _parse_string(s, pos, n, HEX)
            stack[-1][2] = key
            state = 'obj_colon'
            continue

        # --- values ---
        if state == 'value' or state == 'array_first':
            if ch == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['a', [], None])
                state = 'array_first'
                continue
            if ch == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['o', {}, None])
                state = 'obj_first'
                continue
            if ch == '"':
                value, pos = _parse_string(s, pos, n, HEX)
            elif ch == '-' or ('0' <= ch <= '9'):
                value, pos = _parse_number(s, pos, n)
            elif ch == 't':
                _check_literal(s, pos, n, 'true')
                pos += 4
                value = True
            elif ch == 'f':
                _check_literal(s, pos, n, 'false')
                pos += 5
                value = False
            elif ch == 'n':
                _check_literal(s, pos, n, 'null')
                pos += 4
                value = None
            else:
                raise JSONError(f"unexpected character {ch!r}", pos)

            # deliver
            if not stack:
                while pos < n and s[pos] in WS:
                    pos += 1
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return value
            frame = stack[-1]
            if frame[0] == 'a':
                frame[1].append(value)
                state = 'array_sep'
            else:
                frame[1][frame[2]] = value
                state = 'obj_sep'
            continue

        # --- error: unexpected character for current state ---
        if state == 'array_sep':
            raise JSONError(f"expected ',' or ']', got {ch!r}", pos)
        elif state == 'obj_first':
            raise JSONError(f"expected string key or '}}', got {ch!r}", pos)
        elif state == 'obj_colon':
            raise JSONError(f"expected ':', got {ch!r}", pos)
        elif state == 'obj_sep':
            raise JSONError(f"expected ',' or '}}', got {ch!r}", pos)
        elif state == 'obj_key':
            raise JSONError(f"expected string key, got {ch!r}", pos)
        else:
            raise JSONError(f"unexpected character {ch!r}", pos)


def _check_literal(s, pos, n, expected):
    for i, c in enumerate(expected):
        if pos + i >= n or s[pos + i] != c:
            if pos + i >= n:
                raise JSONError("unexpected end of input", n)
            raise JSONError(f"invalid literal", pos + i)


def _parse_number(s, pos, n):
    start = pos
    if pos < n and s[pos] == '-':
        pos += 1

    if pos >= n:
        raise JSONError("unexpected end of input", n)

    if s[pos] == '0':
        pos += 1
        if pos < n and '0' <= s[pos] <= '9':
            raise JSONError("leading zero not allowed", pos)
    elif '1' <= s[pos] <= '9':
        pos += 1
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    else:
        raise JSONError(f"invalid number start", pos)

    has_fraction = False
    if pos < n and s[pos] == '.':
        has_fraction = True
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit after '.'", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    has_exponent = False
    if pos < n and s[pos] in 'eE':
        has_exponent = True
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("expected digit in exponent", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if has_fraction or has_exponent:
        return float(text), pos
    else:
        return int(text), pos


def _parse_string(s, pos, n, HEX):
    # s[pos] == '"'
    pos += 1
    parts = []

    while True:
        if pos >= n:
            raise JSONError("unexpected end of input in string", pos)

        ch = s[pos]

        if ch == '"':
            pos += 1
            return ''.join(parts), pos

        if ch == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in string escape", pos)
            ec = s[pos]
            if ec == '"':
                parts.append('"')
                pos += 1
            elif ec == '\\':
                parts.append('\\')
                pos += 1
            elif ec == '/':
                parts.append('/')
                pos += 1
            elif ec == 'b':
                parts.append('\b')
                pos += 1
            elif ec == 'f':
                parts.append('\f')
                pos += 1
            elif ec == 'n':
                parts.append('\n')
                pos += 1
            elif ec == 'r':
                parts.append('\r')
                pos += 1
            elif ec == 't':
                parts.append('\t')
                pos += 1
            elif ec == 'u':
                pos += 1
                if pos + 4 > n:
                    raise JSONError("unexpected end of input in \\u escape", n)
                for i in range(4):
                    if s[pos + i] not in HEX:
                        raise JSONError(f"invalid hex digit in \\u escape", pos + i)
                code = _hex4(s, pos)
                pos += 4

                if 0xD800 <= code <= 0xDBFF:
                    # possible high surrogate – check for low surrogate escape
                    if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                        h2 = pos + 2
                        if (s[h2] in HEX and s[h2 + 1] in HEX
                                and s[h2 + 2] in HEX and s[h2 + 3] in HEX):
                            code2 = _hex4(s, h2)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                parts.append(chr(combined))
                                pos += 6
                                continue
                    parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError(f"invalid escape character {ec!r}", pos)
        elif ord(ch) < 0x20:
            raise JSONError("unescaped control character in string", pos)
        else:
            parts.append(ch)
            pos += 1


def _hex4(s, pos):
    return ((ord(s[pos]) - 48 if s[pos] <= '9'
             else ord(s[pos]) - 87 if s[pos] >= 'a'
             else ord(s[pos]) - 55) * 16
            + (ord(s[pos+1]) - 48 if s[pos+1] <= '9'
               else ord(s[pos+1]) - 87 if s[pos+1] >= 'a'
               else ord(s[pos+1]) - 55) * 16
            + (ord(s[pos+2]) - 48 if s[pos+2] <= '9'
               else ord(s[pos+2]) - 87 if s[pos+2] >= 'a'
               else ord(s[pos+2]) - 55) * 16
            + (ord(s[pos+3]) - 48 if s[pos+3] <= '9'
               else ord(s[pos+3]) - 87 if s[pos+3] >= 'a'
               else ord(s[pos+3]) - 55))
