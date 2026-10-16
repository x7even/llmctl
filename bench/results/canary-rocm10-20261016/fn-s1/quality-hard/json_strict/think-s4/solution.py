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
    i = 0
    stack = []
    state = 'value'
    result = None

    while True:
        if state == 'value':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(('a', [], None))
                i += 1
                state = 'array_start'
            elif c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(('o', {}, None))
                i += 1
                state = 'obj_start'
            elif c == '"':
                result, i = _parse_string(s, i, n)
                if not stack:
                    state = 'top_done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(result)
                    state = 'array_sep'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_sep'
            elif c == 't':
                result, i = _parse_lit(s, i, n, 'true', True)
                if not stack:
                    state = 'top_done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(result)
                    state = 'array_sep'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_sep'
            elif c == 'f':
                result, i = _parse_lit(s, i, n, 'false', False)
                if not stack:
                    state = 'top_done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(result)
                    state = 'array_sep'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_sep'
            elif c == 'n':
                result, i = _parse_lit(s, i, n, 'null', None)
                if not stack:
                    state = 'top_done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(result)
                    state = 'array_sep'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_sep'
            elif c == '-' or '0' <= c <= '9':
                result, i = _parse_number(s, i, n)
                if not stack:
                    state = 'top_done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(result)
                    state = 'array_sep'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_sep'
            else:
                raise JSONError("unexpected character", i)

        elif state == 'array_start':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ']':
                i += 1
                _, container, _ = stack.pop()
                result = container
                if not stack:
                    state = 'top_done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(result)
                    state = 'array_sep'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_sep'
            else:
                state = 'value'

        elif state == 'array_sep':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ',':
                i += 1
                state = 'value'
            elif s[i] == ']':
                i += 1
                _, container, _ = stack.pop()
                result = container
                if not stack:
                    state = 'top_done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(result)
                    state = 'array_sep'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_sep'
            else:
                raise JSONError("expected , or ]", i)

        elif state == 'obj_start':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == '}':
                i += 1
                _, container, _ = stack.pop()
                result = container
                if not stack:
                    state = 'top_done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(result)
                    state = 'array_sep'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_sep'
            elif s[i] == '"':
                key, i = _parse_string(s, i, n)
                stack[-1] = ('o', stack[-1][1], key)
                state = 'obj_colon'
            else:
                raise JSONError("expected string or }", i)

        elif state == 'obj_key':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == '"':
                key, i = _parse_string(s, i, n)
                stack[-1] = ('o', stack[-1][1], key)
                state = 'obj_colon'
            else:
                raise JSONError("expected string", i)

        elif state == 'obj_colon':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ':':
                i += 1
                state = 'value'
            else:
                raise JSONError("expected :", i)

        elif state == 'obj_sep':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ',':
                i += 1
                state = 'obj_key'
            elif s[i] == '}':
                i += 1
                _, container, _ = stack.pop()
                result = container
                if not stack:
                    state = 'top_done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(result)
                    state = 'array_sep'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_sep'
            else:
                raise JSONError("expected , or }", i)

        elif state == 'top_done':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                return result
            else:
                raise JSONError("trailing garbage", i)


def _parse_string(s, i, n):
    i += 1  # skip opening "
    parts = []

    while True:
        if i >= n:
            raise JSONError("unexpected end of input", n)
        c = s[i]
        if c == '"':
            i += 1
            return ''.join(parts), i
        elif c == '\\':
            i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c2 = s[i]
            if c2 == '"':
                parts.append('"')
                i += 1
            elif c2 == '\\':
                parts.append('\\')
                i += 1
            elif c2 == '/':
                parts.append('/')
                i += 1
            elif c2 == 'b':
                parts.append('\b')
                i += 1
            elif c2 == 'f':
                parts.append('\f')
                i += 1
            elif c2 == 'n':
                parts.append('\n')
                i += 1
            elif c2 == 'r':
                parts.append('\r')
                i += 1
            elif c2 == 't':
                parts.append('\t')
                i += 1
            elif c2 == 'u':
                code = 0
                for k in range(4):
                    pos = i + 1 + k
                    if pos >= n:
                        raise JSONError("unexpected end of input", n)
                    ch = s[pos]
                    if '0' <= ch <= '9':
                        code = code * 16 + (ord(ch) - 48)
                    elif 'a' <= ch <= 'f':
                        code = code * 16 + (ord(ch) - 97 + 10)
                    elif 'A' <= ch <= 'F':
                        code = code * 16 + (ord(ch) - 65 + 10)
                    else:
                        raise JSONError("invalid hex digit", pos)
                i += 5

                if 0xD800 <= code <= 0xDBFF:
                    if (i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u'):
                        code2 = 0
                        valid = True
                        for k in range(4):
                            ch = s[i + 2 + k]
                            if '0' <= ch <= '9':
                                code2 = code2 * 16 + (ord(ch) - 48)
                            elif 'a' <= ch <= 'f':
                                code2 = code2 * 16 + (ord(ch) - 97 + 10)
                            elif 'A' <= ch <= 'F':
                                code2 = code2 * 16 + (ord(ch) - 65 + 10)
                            else:
                                valid = False
                                break
                        if valid and 0xDC00 <= code2 <= 0xDFFF:
                            combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            parts.append(chr(combined))
                            i += 6
                            continue
                    parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError("invalid escape", i)
        elif ord(c) < 0x20:
            raise JSONError("control character in string", i)
        else:
            parts.append(c)
            i += 1


def _parse_number(s, i, n):
    start = i
    is_float = False

    if s[i] == '-':
        i += 1

    if i >= n:
        raise JSONError("unexpected end of input", n)

    if s[i] == '0':
        i += 1
    elif '1' <= s[i] <= '9':
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1
    else:
        raise JSONError("invalid number", i)

    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit after .", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    if i < n and s[i] in 'eE':
        is_float = True
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("expected digit in exponent", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    text = s[start:i]
    if is_float:
        return float(text), i
    else:
        return int(text), i


def _parse_lit(s, i, n, word, value):
    for k in range(len(word)):
        if i + k >= n:
            raise JSONError("unexpected end of input", n)
        if s[i + k] != word[k]:
            raise JSONError("invalid literal", i + k)
    return value, i + len(word)
