import re


class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


_HEX = frozenset('0123456789abcdefABCDEF')
_STR_SPECIAL = re.compile(r'["\\\x00-\x1f]')


def _skip_ws(s, i):
    n = len(s)
    while i < n and s[i] in ' \t\n\r':
        i += 1
    return i


def _parse_string(s, i, n):
    i += 1  # skip opening "
    parts = []
    while True:
        m = _STR_SPECIAL.search(s, i)
        if m is None:
            raise JSONError("unterminated string", n)
        j = m.start()
        if j > i:
            parts.append(s[i:j])
        i = j
        c = s[i]
        if c == '"':
            return ''.join(parts), i + 1
        if c == '\\':
            i += 1
            if i >= n:
                raise JSONError("unterminated string", n)
            c2 = s[i]
            if c2 == '"':
                parts.append('"'); i += 1
            elif c2 == '\\':
                parts.append('\\'); i += 1
            elif c2 == '/':
                parts.append('/'); i += 1
            elif c2 == 'b':
                parts.append('\b'); i += 1
            elif c2 == 'f':
                parts.append('\f'); i += 1
            elif c2 == 'n':
                parts.append('\n'); i += 1
            elif c2 == 'r':
                parts.append('\r'); i += 1
            elif c2 == 't':
                parts.append('\t'); i += 1
            elif c2 == 'u':
                for k in range(1, 5):
                    if i + k >= n:
                        raise JSONError("unexpected end", n)
                    if s[i + k] not in _HEX:
                        raise JSONError("invalid hex digit", i + k)
                code = int(s[i + 1:i + 5], 16)
                i += 5
                if 0xD800 <= code <= 0xDBFF:
                    if (i + 6 <= n and
                            s[i] == '\\' and s[i + 1] == 'u' and
                            s[i + 2] in _HEX and s[i + 3] in _HEX and
                            s[i + 4] in _HEX and s[i + 5] in _HEX):
                        lo = int(s[i + 2:i + 6], 16)
                        if 0xDC00 <= lo <= 0xDFFF:
                            parts.append(chr(0x10000 + ((code - 0xD800) << 10) + (lo - 0xDC00)))
                            i += 6
                            continue
                    parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError("invalid escape", i)
        else:
            raise JSONError("control character in string", i)


def _parse_number(s, i, n):
    start = i
    if s[i] == '-':
        i += 1
    if i >= n:
        raise JSONError("unexpected end", n)
    if s[i] == '0':
        i += 1
    elif '1' <= s[i] <= '9':
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1
    else:
        raise JSONError("invalid number", i)
    is_float = False
    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n:
            raise JSONError("unexpected end", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1
    if i < n and s[i] in 'eE':
        is_float = True
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n:
            raise JSONError("unexpected end", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1
    text = s[start:i]
    return (float(text) if is_float else int(text)), i


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")

    n = len(s)
    i = 0
    stack = []
    depth = 0
    result = None
    state = 'VALUE'

    while True:
        if state == 'VALUE':
            i = _skip_ws(s, i)
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '"':
                result, i = _parse_string(s, i, n)
                state = 'AFTER_VALUE'
            elif c == '[':
                depth += 1
                if depth > 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(['a', []])
                i += 1
                state = 'ARRAY_FIRST'
            elif c == '{':
                depth += 1
                if depth > 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(['o', {}, None])
                i += 1
                state = 'OBJ_FIRST'
            elif c == 't':
                for k, ch in enumerate('true'):
                    if i + k >= n:
                        raise JSONError("unexpected end", n)
                    if s[i + k] != ch:
                        raise JSONError("invalid literal", i + k)
                result = True
                i += 4
                state = 'AFTER_VALUE'
            elif c == 'f':
                for k, ch in enumerate('false'):
                    if i + k >= n:
                        raise JSONError("unexpected end", n)
                    if s[i + k] != ch:
                        raise JSONError("invalid literal", i + k)
                result = False
                i += 5
                state = 'AFTER_VALUE'
            elif c == 'n':
                for k, ch in enumerate('null'):
                    if i + k >= n:
                        raise JSONError("unexpected end", n)
                    if s[i + k] != ch:
                        raise JSONError("invalid literal", i + k)
                result = None
                i += 4
                state = 'AFTER_VALUE'
            elif c == '-' or '0' <= c <= '9':
                result, i = _parse_number(s, i, n)
                state = 'AFTER_VALUE'
            else:
                raise JSONError("unexpected character", i)

        elif state == 'AFTER_VALUE':
            if not stack:
                state = 'END'
            else:
                top = stack[-1]
                if top[0] == 'a':
                    top[1].append(result)
                    state = 'ARRAY_COMMA'
                else:
                    top[1][top[2]] = result
                    state = 'OBJ_COMMA'

        elif state == 'ARRAY_FIRST':
            i = _skip_ws(s, i)
            if i >= n:
                raise JSONError("unexpected end", n)
            if s[i] == ']':
                depth -= 1
                result = stack.pop()[1]
                i += 1
                state = 'AFTER_VALUE'
            else:
                state = 'VALUE'

        elif state == 'ARRAY_COMMA':
            i = _skip_ws(s, i)
            if i >= n:
                raise JSONError("unexpected end", n)
            if s[i] == ']':
                depth -= 1
                result = stack.pop()[1]
                i += 1
                state = 'AFTER_VALUE'
            elif s[i] == ',':
                i += 1
                state = 'VALUE'
            else:
                raise JSONError("expected , or ]", i)

        elif state == 'OBJ_FIRST':
            i = _skip_ws(s, i)
            if i >= n:
                raise JSONError("unexpected end", n)
            if s[i] == '}':
                depth -= 1
                result = stack.pop()[1]
                i += 1
                state = 'AFTER_VALUE'
            elif s[i] == '"':
                key, i = _parse_string(s, i, n)
                stack[-1] = ['o', stack[-1][1], key]
                state = 'OBJ_COLON'
            else:
                raise JSONError("expected key or }", i)

        elif state == 'OBJ_KEY':
            i = _skip_ws(s, i)
            if i >= n:
                raise JSONError("unexpected end", n)
            if s[i] == '"':
                key, i = _parse_string(s, i, n)
                stack[-1] = ['o', stack[-1][1], key]
                state = 'OBJ_COLON'
            else:
                raise JSONError("expected key", i)

        elif state == 'OBJ_COLON':
            i = _skip_ws(s, i)
            if i >= n:
                raise JSONError("unexpected end", n)
            if s[i] == ':':
                i += 1
                state = 'VALUE'
            else:
                raise JSONError("expected :", i)

        elif state == 'OBJ_COMMA':
            i = _skip_ws(s, i)
            if i >= n:
                raise JSONError("unexpected end", n)
            if s[i] == '}':
                depth -= 1
                result = stack.pop()[1]
                i += 1
                state = 'AFTER_VALUE'
            elif s[i] == ',':
                i += 1
                state = 'OBJ_KEY'
            else:
                raise JSONError("expected , or }", i)

        elif state == 'END':
            i = _skip_ws(s, i)
            if i < n:
                raise JSONError("trailing data", i)
            return result
