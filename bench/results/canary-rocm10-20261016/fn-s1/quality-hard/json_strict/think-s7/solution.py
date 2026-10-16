class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}"
        )

    n = len(s)
    pos = 0
    stack = []  # each entry: ['a' or 'o', container, key_or_None]
    result = None

    _HEX = frozenset('0123456789abcdefABCDEF')

    # State constants
    _VALUE = 0
    _DELIVER = 1
    _ARR_START = 2
    _ARR_AFTER = 3
    _OBJ_START = 4
    _OBJ_AFTER_KEY = 5
    _OBJ_AFTER = 6
    _OBJ_AFTER_COMMA = 7
    _DONE = 8

    state = _VALUE

    while True:
        if state == _VALUE:
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]

            if c == '"':
                # --- parse string ---
                pos += 1
                parts = []
                while True:
                    start = pos
                    while pos < n:
                        c = s[pos]
                        if c == '"' or c == '\\' or c < ' ':
                            break
                        pos += 1
                    if pos > start:
                        parts.append(s[start:pos])
                    if pos >= n:
                        raise JSONError("unterminated string", n)
                    c = s[pos]
                    if c < ' ':
                        raise JSONError("control character in string", pos)
                    if c == '"':
                        pos += 1
                        break
                    # c == '\\'
                    pos += 1
                    if pos >= n:
                        raise JSONError("unterminated string", n)
                    esc = s[pos]
                    if esc == '"':
                        parts.append('"'); pos += 1
                    elif esc == '\\':
                        parts.append('\\'); pos += 1
                    elif esc == '/':
                        parts.append('/'); pos += 1
                    elif esc == 'b':
                        parts.append('\b'); pos += 1
                    elif esc == 'f':
                        parts.append('\f'); pos += 1
                    elif esc == 'n':
                        parts.append('\n'); pos += 1
                    elif esc == 'r':
                        parts.append('\r'); pos += 1
                    elif esc == 't':
                        parts.append('\t'); pos += 1
                    elif esc == 'u':
                        pos += 1
                        if pos + 4 > n:
                            raise JSONError("invalid unicode escape", n)
                        h0 = s[pos]; h1 = s[pos + 1]
                        h2 = s[pos + 2]; h3 = s[pos + 3]
                        if h0 not in _HEX:
                            raise JSONError("invalid unicode escape", pos)
                        if h1 not in _HEX:
                            raise JSONError("invalid unicode escape", pos + 1)
                        if h2 not in _HEX:
                            raise JSONError("invalid unicode escape", pos + 2)
                        if h3 not in _HEX:
                            raise JSONError("invalid unicode escape", pos + 3)
                        code = int(s[pos:pos + 4], 16)
                        pos += 4
                        if 0xD800 <= code <= 0xDBFF:
                            # high surrogate – look for immediately following low surrogate
                            if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                                    and s[pos + 2] in _HEX and s[pos + 3] in _HEX
                                    and s[pos + 4] in _HEX and s[pos + 5] in _HEX):
                                code2 = int(s[pos + 2:pos + 6], 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    parts.append(chr(combined))
                                    pos += 6
                                    continue
                            parts.append(chr(code))
                        else:
                            parts.append(chr(code))
                    else:
                        raise JSONError("invalid escape sequence", pos)
                result = ''.join(parts)
                state = _DELIVER

            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                stack.append(['o', {}, None])
                pos += 1
                state = _OBJ_START

            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                stack.append(['a', [], None])
                pos += 1
                state = _ARR_START

            elif c == 't':
                for i, ch in enumerate('true'):
                    if pos + i >= n:
                        raise JSONError("invalid literal", n)
                    if s[pos + i] != ch:
                        raise JSONError("invalid literal", pos + i)
                pos += 4
                result = True
                state = _DELIVER

            elif c == 'f':
                for i, ch in enumerate('false'):
                    if pos + i >= n:
                        raise JSONError("invalid literal", n)
                    if s[pos + i] != ch:
                        raise JSONError("invalid literal", pos + i)
                pos += 5
                result = False
                state = _DELIVER

            elif c == 'n':
                for i, ch in enumerate('null'):
                    if pos + i >= n:
                        raise JSONError("invalid literal", n)
                    if s[pos + i] != ch:
                        raise JSONError("invalid literal", pos + i)
                pos += 4
                result = None
                state = _DELIVER

            elif c == '-' or ('0' <= c <= '9'):
                num_start = pos
                is_float = False

                if s[pos] == '-':
                    pos += 1
                    if pos >= n:
                        raise JSONError("invalid number", n)
                    if not ('0' <= s[pos] <= '9'):
                        raise JSONError("invalid number", pos)

                if s[pos] == '0':
                    pos += 1
                elif '1' <= s[pos] <= '9':
                    pos += 1
                    while pos < n and '0' <= s[pos] <= '9':
                        pos += 1
                else:
                    raise JSONError("invalid number", pos)

                if pos < n and s[pos] == '.':
                    is_float = True
                    pos += 1
                    if pos >= n:
                        raise JSONError("invalid number", n)
                    if not ('0' <= s[pos] <= '9'):
                        raise JSONError("invalid number", pos)
                    while pos < n and '0' <= s[pos] <= '9':
                        pos += 1

                if pos < n and (s[pos] == 'e' or s[pos] == 'E'):
                    is_float = True
                    pos += 1
                    if pos < n and (s[pos] == '+' or s[pos] == '-'):
                        pos += 1
                    if pos >= n:
                        raise JSONError("invalid number", n)
                    if not ('0' <= s[pos] <= '9'):
                        raise JSONError("invalid number", pos)
                    while pos < n and '0' <= s[pos] <= '9':
                        pos += 1

                num_text = s[num_start:pos]
                if is_float:
                    result = float(num_text)
                else:
                    result = int(num_text)
                state = _DELIVER

            else:
                raise JSONError("unexpected character", pos)

        elif state == _DELIVER:
            if not stack:
                state = _DONE
            else:
                top = stack[-1]
                if top[0] == 'a':
                    top[1].append(result)
                    state = _ARR_AFTER
                else:
                    top[1][top[2]] = result
                    state = _OBJ_AFTER

        elif state == _ARR_START:
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ']':
                pos += 1
                result = stack[-1][1]
                stack.pop()
                state = _DELIVER
            else:
                state = _VALUE

        elif state == _ARR_AFTER:
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                pos += 1
                state = _VALUE
            elif s[pos] == ']':
                pos += 1
                result = stack[-1][1]
                stack.pop()
                state = _DELIVER
            else:
                raise JSONError("expected ',' or ']'", pos)

        elif state == _OBJ_START:
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == '}':
                pos += 1
                result = stack[-1][1]
                stack.pop()
                state = _DELIVER
            elif s[pos] == '"':
                # parse key string
                pos += 1
                parts = []
                while True:
                    start = pos
                    while pos < n:
                        c = s[pos]
                        if c == '"' or c == '\\' or c < ' ':
                            break
                        pos += 1
                    if pos > start:
                        parts.append(s[start:pos])
                    if pos >= n:
                        raise JSONError("unterminated string", n)
                    c = s[pos]
                    if c < ' ':
                        raise JSONError("control character in string", pos)
                    if c == '"':
                        pos += 1
                        break
                    pos += 1
                    if pos >= n:
                        raise JSONError("unterminated string", n)
                    esc = s[pos]
                    if esc == '"':
                        parts.append('"'); pos += 1
                    elif esc == '\\':
                        parts.append('\\'); pos += 1
                    elif esc == '/':
                        parts.append('/'); pos += 1
                    elif esc == 'b':
                        parts.append('\b'); pos += 1
                    elif esc == 'f':
                        parts.append('\f'); pos += 1
                    elif esc == 'n':
                        parts.append('\n'); pos += 1
                    elif esc == 'r':
                        parts.append('\r'); pos += 1
                    elif esc == 't':
                        parts.append('\t'); pos += 1
                    elif esc == 'u':
                        pos += 1
                        if pos + 4 > n:
                            raise JSONError("invalid unicode escape", n)
                        h0 = s[pos]; h1 = s[pos + 1]
                        h2 = s[pos + 2]; h3 = s[pos + 3]
                        if h0 not in _HEX:
                            raise JSONError("invalid unicode escape", pos)
                        if h1 not in _HEX:
                            raise JSONError("invalid unicode escape", pos + 1)
                        if h2 not in _HEX:
                            raise JSONError("invalid unicode escape", pos + 2)
                        if h3 not in _HEX:
                            raise JSONError("invalid unicode escape", pos + 3)
                        code = int(s[pos:pos + 4], 16)
                        pos += 4
                        if 0xD800 <= code <= 0xDBFF:
                            if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                                    and s[pos + 2] in _HEX and s[pos + 3] in _HEX
                                    and s[pos + 4] in _HEX and s[pos + 5] in _HEX):
                                code2 = int(s[pos + 2:pos + 6], 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    parts.append(chr(combined))
                                    pos += 6
                                    continue
                            parts.append(chr(code))
                        else:
                            parts.append(chr(code))
                    else:
                        raise JSONError("invalid escape sequence", pos)
                key = ''.join(parts)
                stack[-1][2] = key
                state = _OBJ_AFTER_KEY
            else:
                raise JSONError("expected '\"' or '}'", pos)

        elif state == _OBJ_AFTER_KEY:
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ':':
                pos += 1
                state = _VALUE
            else:
                raise JSONError("expected ':'", pos)

        elif state == _OBJ_AFTER:
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                pos += 1
                state = _OBJ_AFTER_COMMA
            elif s[pos] == '}':
                pos += 1
                result = stack[-1][1]
                stack.pop()
                state = _DELIVER
            else:
                raise JSONError("expected ',' or '}'", pos)

        elif state == _OBJ_AFTER_COMMA:
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == '"':
                # parse key string
                pos += 1
                parts = []
                while True:
                    start = pos
                    while pos < n:
                        c = s[pos]
                        if c == '"' or c == '\\' or c < ' ':
                            break
                        pos += 1
                    if pos > start:
                        parts.append(s[start:pos])
                    if pos >= n:
                        raise JSONError("unterminated string", n)
                    c = s[pos]
                    if c < ' ':
                        raise JSONError("control character in string", pos)
                    if c == '"':
                        pos += 1
                        break
                    pos += 1
                    if pos >= n:
                        raise JSONError("unterminated string", n)
                    esc = s[pos]
                    if esc == '"':
                        parts.append('"'); pos += 1
                    elif esc == '\\':
                        parts.append('\\'); pos += 1
                    elif esc == '/':
                        parts.append('/'); pos += 1
                    elif esc == 'b':
                        parts.append('\b'); pos += 1
                    elif esc == 'f':
                        parts.append('\f'); pos += 1
                    elif esc == 'n':
                        parts.append('\n'); pos += 1
                    elif esc == 'r':
                        parts.append('\r'); pos += 1
                    elif esc == 't':
                        parts.append('\t'); pos += 1
                    elif esc == 'u':
                        pos += 1
                        if pos + 4 > n:
                            raise JSONError("invalid unicode escape", n)
                        h0 = s[pos]; h1 = s[pos + 1]
                        h2 = s[pos + 2]; h3 = s[pos + 3]
                        if h0 not in _HEX:
                            raise JSONError("invalid unicode escape", pos)
                        if h1 not in _HEX:
                            raise JSONError("invalid unicode escape", pos + 1)
                        if h2 not in _HEX:
                            raise JSONError("invalid unicode escape", pos + 2)
                        if h3 not in _HEX:
                            raise JSONError("invalid unicode escape", pos + 3)
                        code = int(s[pos:pos + 4], 16)
                        pos += 4
                        if 0xD800 <= code <= 0xDBFF:
                            if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                                    and s[pos + 2] in _HEX and s[pos + 3] in _HEX
                                    and s[pos + 4] in _HEX and s[pos + 5] in _HEX):
                                code2 = int(s[pos + 2:pos + 6], 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    parts.append(chr(combined))
                                    pos += 6
                                    continue
                            parts.append(chr(code))
                        else:
                            parts.append(chr(code))
                    else:
                        raise JSONError("invalid escape sequence", pos)
                key = ''.join(parts)
                stack[-1][2] = key
                state = _OBJ_AFTER_KEY
            else:
                raise JSONError("expected '\"'", pos)

        elif state == _DONE:
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos < n:
                raise JSONError("trailing garbage", pos)
            return result
