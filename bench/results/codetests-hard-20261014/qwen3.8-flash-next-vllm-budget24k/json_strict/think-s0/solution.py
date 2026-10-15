class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


_HEX = frozenset('0123456789abcdefABCDEF')
_WS = frozenset(' \t\n\r')


def _skip_ws(s, i, n):
    while i < n and s[i] in _WS:
        i += 1
    return i


def _parse_string(s, i, n):
    i += 1  # skip opening "
    chars = []
    while True:
        if i >= n:
            raise JSONError("Unterminated string", n)
        c = s[i]
        if c == '"':
            i += 1
            return ''.join(chars), i
        if c == '\\':
            i += 1
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            c2 = s[i]
            if c2 == '"':
                chars.append('"'); i += 1
            elif c2 == '\\':
                chars.append('\\'); i += 1
            elif c2 == '/':
                chars.append('/'); i += 1
            elif c2 == 'b':
                chars.append('\b'); i += 1
            elif c2 == 'f':
                chars.append('\f'); i += 1
            elif c2 == 'n':
                chars.append('\n'); i += 1
            elif c2 == 'r':
                chars.append('\r'); i += 1
            elif c2 == 't':
                chars.append('\t'); i += 1
            elif c2 == 'u':
                if i + 5 > n:
                    raise JSONError("Unexpected end of input", n)
                h1 = s[i+1]; h2 = s[i+2]; h3 = s[i+3]; h4 = s[i+4]
                if h1 not in _HEX: raise JSONError("Invalid hex digit", i+1)
                if h2 not in _HEX: raise JSONError("Invalid hex digit", i+2)
                if h3 not in _HEX: raise JSONError("Invalid hex digit", i+3)
                if h4 not in _HEX: raise JSONError("Invalid hex digit", i+4)
                code = int(h1 + h2 + h3 + h4, 16)
                i += 5
                if 0xD800 <= code <= 0xDBFF:
                    # high surrogate – look for immediately following low surrogate escape
                    if i < n and s[i] == '\\':
                        if i + 1 < n and s[i+1] == 'u':
                            if i + 6 > n:
                                raise JSONError("Unexpected end of input", n)
                            g1 = s[i+2]; g2 = s[i+3]; g3 = s[i+4]; g4 = s[i+5]
                            if g1 not in _HEX: raise JSONError("Invalid hex digit", i+2)
                            if g2 not in _HEX: raise JSONError("Invalid hex digit", i+3)
                            if g3 not in _HEX: raise JSONError("Invalid hex digit", i+4)
                            if g4 not in _HEX: raise JSONError("Invalid hex digit", i+5)
                            code2 = int(g1 + g2 + g3 + g4, 16)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(combined))
                                i += 6
                            else:
                                chars.append(chr(code))
                        else:
                            chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError("Invalid escape", i)
        elif ord(c) < 0x20:
            raise JSONError("Control character in string", i)
        else:
            chars.append(c)
            i += 1


def _parse_number(s, i, n):
    start = i
    is_float = False

    if s[i] == '-':
        i += 1
        if i >= n:
            raise JSONError("Unexpected end of input", n)

    if s[i] == '0':
        i += 1
    elif '1' <= s[i] <= '9':
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1
    else:
        raise JSONError("Invalid number", i)

    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n:
            raise JSONError("Unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("Invalid number", i)
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1

    if i < n and s[i] in 'eE':
        is_float = True
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n:
            raise JSONError("Unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("Invalid number", i)
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1

    text = s[start:i]
    if is_float:
        return float(text), i
    else:
        return int(text), i


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__}")

    n = len(s)
    i = 0

    # skip leading whitespace
    i = _skip_ws(s, i, n)
    if i >= n:
        raise JSONError("Empty input", i)

    stack = []   # each entry: ['array', list] or ['object', dict, key]
    depth = 0
    result = None
    state = 'value'

    while True:
        # ---- expecting a value ----
        if state == 'value':
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            c = s[i]

            if c == '"':
                result, i = _parse_string(s, i, n)
                state = 'after_value'

            elif c == '[':
                if depth >= 500:
                    raise JSONError("Maximum nesting depth exceeded", i)
                depth += 1
                stack.append(['array', []])
                i += 1
                i = _skip_ws(s, i, n)
                if i >= n:
                    raise JSONError("Unexpected end of input", n)
                if s[i] == ']':
                    result = stack.pop()[1]
                    depth -= 1
                    i += 1
                    state = 'after_value'
                else:
                    state = 'value'

            elif c == '{':
                if depth >= 500:
                    raise JSONError("Maximum nesting depth exceeded", i)
                depth += 1
                stack.append(['object', {}, None])
                i += 1
                i = _skip_ws(s, i, n)
                if i >= n:
                    raise JSONError("Unexpected end of input", n)
                if s[i] == '}':
                    result = stack.pop()[1]
                    depth -= 1
                    i += 1
                    state = 'after_value'
                elif s[i] == '"':
                    state = 'object_key'
                else:
                    raise JSONError("Expected string key", i)

            elif c == 't':
                for j, ch in enumerate('true'):
                    if i + j >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i + j] != ch:
                        raise JSONError("Invalid literal", i + j)
                result = True
                i += 4
                state = 'after_value'

            elif c == 'f':
                for j, ch in enumerate('false'):
                    if i + j >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i + j] != ch:
                        raise JSONError("Invalid literal", i + j)
                result = False
                i += 5
                state = 'after_value'

            elif c == 'n':
                for j, ch in enumerate('null'):
                    if i + j >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i + j] != ch:
                        raise JSONError("Invalid literal", i + j)
                result = None
                i += 4
                state = 'after_value'

            elif c == '-' or '0' <= c <= '9':
                result, i = _parse_number(s, i, n)
                state = 'after_value'

            else:
                raise JSONError("Unexpected character", i)

        # ---- just finished a value, integrate into context ----
        elif state == 'after_value':
            if not stack:
                state = 'ws_after_top'
            else:
                top = stack[-1]
                if top[0] == 'array':
                    top[1].append(result)
                    state = 'array_after_value'
                else:
                    top[1][top[2]] = result
                    state = 'object_after_value'

        # ---- inside array, after an element ----
        elif state == 'array_after_value':
            i = _skip_ws(s, i, n)
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] == ',':
                i += 1
                i = _skip_ws(s, i, n)
                if i >= n:
                    raise JSONError("Unexpected end of input", n)
                state = 'value'
            elif s[i] == ']':
                i += 1
                result = stack.pop()[1]
                depth -= 1
                state = 'after_value'
            else:
                raise JSONError("Expected , or ]", i)

        # ---- inside object, after a value ----
        elif state == 'object_after_value':
            i = _skip_ws(s, i, n)
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] == ',':
                i += 1
                i = _skip_ws(s, i, n)
                if i >= n:
                    raise JSONError("Unexpected end of input", n)
                if s[i] == '"':
                    state = 'object_key'
                else:
                    raise JSONError("Expected string key", i)
            elif s[i] == '}':
                i += 1
                result = stack.pop()[1]
                depth -= 1
                state = 'after_value'
            else:
                raise JSONError("Expected , or }", i)

        # ---- expecting a string key in an object ----
        elif state == 'object_key':
            key, i = _parse_string(s, i, n)
            i = _skip_ws(s, i, n)
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] != ':':
                raise JSONError("Expected :", i)
            i += 1
            i = _skip_ws(s, i, n)
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            stack[-1][2] = key
            state = 'value'

        # ---- after top-level value, skip trailing whitespace ----
        elif state == 'ws_after_top':
            i = _skip_ws(s, i, n)
            if i >= n:
                return result
            raise JSONError("Trailing garbage", i)
