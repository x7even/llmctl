import re


class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_STR_SPECIAL = re.compile('["\\\\\x00-\x1f]')


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}"
        )

    n = len(s)
    i = 0
    stack = []  # each entry: [type_char, container, current_key]
    result = None
    state = 'value'

    while True:
        if state == 'value':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", i)
            c = s[i]
            if c == '"':
                val, i = _parse_string(s, i, n)
                if not stack:
                    result = val
                    state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'array_after'
                else:
                    stack[-1][1][stack[-1][2]] = val
                    state = 'obj_after'
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(['a', [], None])
                i += 1
                state = 'array_first'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(['o', {}, None])
                i += 1
                state = 'obj_first'
            elif c == 't':
                for j, ec in enumerate('true'):
                    if i + j >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + j] != ec:
                        raise JSONError("invalid literal", i + j)
                i += 4
                val = True
                if not stack:
                    result = val
                    state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'array_after'
                else:
                    stack[-1][1][stack[-1][2]] = val
                    state = 'obj_after'
            elif c == 'f':
                for j, ec in enumerate('false'):
                    if i + j >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + j] != ec:
                        raise JSONError("invalid literal", i + j)
                i += 5
                val = False
                if not stack:
                    result = val
                    state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'array_after'
                else:
                    stack[-1][1][stack[-1][2]] = val
                    state = 'obj_after'
            elif c == 'n':
                for j, ec in enumerate('null'):
                    if i + j >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[i + j] != ec:
                        raise JSONError("invalid literal", i + j)
                i += 4
                val = None
                if not stack:
                    result = val
                    state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'array_after'
                else:
                    stack[-1][1][stack[-1][2]] = val
                    state = 'obj_after'
            elif c == '-' or ('0' <= c <= '9'):
                val, i = _parse_number(s, i, n)
                if not stack:
                    result = val
                    state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'array_after'
                else:
                    stack[-1][1][stack[-1][2]] = val
                    state = 'obj_after'
            else:
                raise JSONError("unexpected character", i)

        elif state == 'array_first':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", i)
            if s[i] == ']':
                i += 1
                val = stack.pop()[1]
                if not stack:
                    result = val
                    state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'array_after'
                else:
                    stack[-1][1][stack[-1][2]] = val
                    state = 'obj_after'
            elif (s[i] == '"' or s[i] == '[' or s[i] == '{'
                  or s[i] in 'tfn-' or '0' <= s[i] <= '9'):
                state = 'value'
            else:
                raise JSONError("unexpected character", i)

        elif state == 'array_after':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", i)
            if s[i] == ',':
                i += 1
                state = 'value'
            elif s[i] == ']':
                i += 1
                val = stack.pop()[1]
                if not stack:
                    result = val
                    state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'array_after'
                else:
                    stack[-1][1][stack[-1][2]] = val
                    state = 'obj_after'
            else:
                raise JSONError("unexpected character", i)

        elif state == 'obj_first':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", i)
            if s[i] == '}':
                i += 1
                val = stack.pop()[1]
                if not stack:
                    result = val
                    state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'array_after'
                else:
                    stack[-1][1][stack[-1][2]] = val
                    state = 'obj_after'
            elif s[i] == '"':
                key, i = _parse_string(s, i, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("expected string key", i)

        elif state == 'obj_colon':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", i)
            if s[i] == ':':
                i += 1
                state = 'value'
            else:
                raise JSONError("expected colon", i)

        elif state == 'obj_after':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", i)
            if s[i] == ',':
                i += 1
                state = 'obj_key'
            elif s[i] == '}':
                i += 1
                val = stack.pop()[1]
                if not stack:
                    result = val
                    state = 'top_end'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'array_after'
                else:
                    stack[-1][1][stack[-1][2]] = val
                    state = 'obj_after'
            else:
                raise JSONError("unexpected character", i)

        elif state == 'obj_key':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", i)
            if s[i] == '"':
                key, i = _parse_string(s, i, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("expected string key", i)

        elif state == 'top_end':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                return result
            raise JSONError("trailing data", i)


def _parse_string(s, i, n):
    i += 1  # skip opening '"'
    parts = []
    while True:
        if i >= n:
            raise JSONError("unterminated string", i)
        m = _STR_SPECIAL.search(s, i)
        if m is None:
            raise JSONError("unterminated string", n)
        j = m.start()
        c = s[j]
        if c == '"':
            if j > i:
                parts.append(s[i:j])
            i = j + 1
            break
        elif c == '\\':
            if j > i:
                parts.append(s[i:j])
            i = j + 1  # skip backslash
            if i >= n:
                raise JSONError("unexpected end of input", i)
            esc = s[i]
            if esc == '"':
                parts.append('"')
                i += 1
            elif esc == '\\':
                parts.append('\\')
                i += 1
            elif esc == '/':
                parts.append('/')
                i += 1
            elif esc == 'b':
                parts.append('\b')
                i += 1
            elif esc == 'f':
                parts.append('\f')
                i += 1
            elif esc == 'n':
                parts.append('\n')
                i += 1
            elif esc == 'r':
                parts.append('\r')
                i += 1
            elif esc == 't':
                parts.append('\t')
                i += 1
            elif esc == 'u':
                i += 1
                cp = 0
                for k in range(4):
                    if i >= n:
                        raise JSONError("unexpected end of input", i)
                    ch = s[i]
                    if '0' <= ch <= '9':
                        cp = cp * 16 + ord(ch) - 48
                    elif 'a' <= ch <= 'f':
                        cp = cp * 16 + ord(ch) - 87
                    elif 'A' <= ch <= 'F':
                        cp = cp * 16 + ord(ch) - 55
                    else:
                        raise JSONError("invalid hex digit", i)
                    i += 1
                if 0xD800 <= cp <= 0xDBFF:
                    # try to combine with a following \uDC00-\uDFFF
                    if (i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u'):
                        lo = 0
                        ok = True
                        for k in range(4):
                            ch2 = s[i + 2 + k]
                            if '0' <= ch2 <= '9':
                                lo = lo * 16 + ord(ch2) - 48
                            elif 'a' <= ch2 <= 'f':
                                lo = lo * 16 + ord(ch2) - 87
                            elif 'A' <= ch2 <= 'F':
                                lo = lo * 16 + ord(ch2) - 55
                            else:
                                ok = False
                                break
                        if ok and 0xDC00 <= lo <= 0xDFFF:
                            combined = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                            parts.append(chr(combined))
                            i += 6
                            continue
                    parts.append(chr(cp))
                else:
                    parts.append(chr(cp))
            else:
                raise JSONError("invalid escape", i)
        else:
            # raw control character (U+0000 .. U+001F)
            raise JSONError("control character in string", j)
    return ''.join(parts), i


def _parse_number(s, i, n):
    start = i
    if s[i] == '-':
        i += 1
    if i >= n:
        raise JSONError("unexpected end of input", i)
    c = s[i]
    if c == '0':
        i += 1
    elif '1' <= c <= '9':
        while i < n and '0' <= s[i] <= '9':
            i += 1
    else:
        raise JSONError("invalid number", i)

    is_float = False
    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n or not ('0' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    if i < n and s[i] in 'eE':
        is_float = True
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n or not ('0' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    text = s[start:i]
    if is_float:
        return float(text), i
    else:
        return int(text), i
