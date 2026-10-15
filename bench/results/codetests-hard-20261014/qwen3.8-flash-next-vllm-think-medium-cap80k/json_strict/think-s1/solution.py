class JSONError(ValueError):
    def __init__(self, message, pos):
        super().__init__(message)
        self.pos = pos


def loads(s):
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []  # ['array', list] or ['object', dict, key]
    state = 'value'
    result = None

    while state != 'done':
        if state == 'value':
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            c = s[pos]
            if c == '{':
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos)
                stack.append(['object', {}, None])
                pos += 1
                state = 'obj_first_key'
                continue
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos)
                stack.append(['array', []])
                pos += 1
                state = 'array_start'
                continue
            elif c == '"':
                result, pos = _parse_string(s, pos, n)
            elif c == 't':
                pos = _parse_literal(s, pos, n, 'true')
                result = True
            elif c == 'f':
                pos = _parse_literal(s, pos, n, 'false')
                result = False
            elif c == 'n':
                pos = _parse_literal(s, pos, n, 'null')
                result = None
            elif c == '-' or ('0' <= c <= '9'):
                result, pos = _parse_number(s, pos, n)
            else:
                raise JSONError("Unexpected character", pos)
            # return scalar value
            if not stack:
                state = 'done'
            elif stack[-1][0] == 'array':
                stack[-1][1].append(result)
                state = 'array_comma'
            else:
                stack[-1][1][stack[-1][2]] = result
                state = 'obj_comma'

        elif state == 'array_start':
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == ']':
                pos += 1
                result = stack.pop()[1]
                if not stack:
                    state = 'done'
                elif stack[-1][0] == 'array':
                    stack[-1][1].append(result)
                    state = 'array_comma'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_comma'
            else:
                state = 'value'

        elif state == 'array_comma':
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == ',':
                pos += 1
                state = 'value'
            elif s[pos] == ']':
                pos += 1
                result = stack.pop()[1]
                if not stack:
                    state = 'done'
                elif stack[-1][0] == 'array':
                    stack[-1][1].append(result)
                    state = 'array_comma'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_comma'
            else:
                raise JSONError("Expected ',' or ']'", pos)

        elif state == 'obj_first_key':
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == '}':
                pos += 1
                result = stack.pop()[1]
                if not stack:
                    state = 'done'
                elif stack[-1][0] == 'array':
                    stack[-1][1].append(result)
                    state = 'array_comma'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_comma'
            elif s[pos] == '"':
                key, pos = _parse_string(s, pos, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("Expected '\"' or '}'", pos)

        elif state == 'obj_key':
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == '"':
                key, pos = _parse_string(s, pos, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("Expected '\"'", pos)

        elif state == 'obj_colon':
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == ':':
                pos += 1
                state = 'value'
            else:
                raise JSONError("Expected ':'", pos)

        elif state == 'obj_comma':
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == ',':
                pos += 1
                state = 'obj_key'
            elif s[pos] == '}':
                pos += 1
                result = stack.pop()[1]
                if not stack:
                    state = 'done'
                elif stack[-1][0] == 'array':
                    stack[-1][1].append(result)
                    state = 'array_comma'
                else:
                    stack[-1][1][stack[-1][2]] = result
                    state = 'obj_comma'
            else:
                raise JSONError("Expected ',' or '}'", pos)

    # trailing whitespace / garbage
    while pos < n and s[pos] in ' \t\n\r':
        pos += 1
    if pos < n:
        raise JSONError("Trailing data", pos)

    return result


def _parse_literal(s, pos, n, literal):
    for i, c in enumerate(literal):
        if pos + i >= n:
            raise JSONError("Unexpected end of input", n)
        if s[pos + i] != c:
            raise JSONError("Invalid literal", pos + i)
    return pos + len(literal)


def _parse_number(s, pos, n):
    start = pos
    is_float = False

    if pos < n and s[pos] == '-':
        pos += 1

    if pos >= n:
        raise JSONError("Unexpected end of input", pos)

    if s[pos] == '0':
        pos += 1
    elif '1' <= s[pos] <= '9':
        pos += 1
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    else:
        raise JSONError("Invalid number", pos)

    if pos < n and s[pos] == '.':
        is_float = True
        pos += 1
        if pos >= n:
            raise JSONError("Unexpected end of input", pos)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("Invalid number", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    if pos < n and (s[pos] == 'e' or s[pos] == 'E'):
        is_float = True
        pos += 1
        if pos < n and (s[pos] == '+' or s[pos] == '-'):
            pos += 1
        if pos >= n:
            raise JSONError("Unexpected end of input", pos)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("Invalid number", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if is_float:
        return float(text), pos
    else:
        return int(text), pos


def _is_hex(ch):
    return ('0' <= ch <= '9') or ('a' <= ch <= 'f') or ('A' <= ch <= 'F')


def _parse_string(s, pos, n):
    pos += 1  # skip opening "
    parts = []

    while True:
        if pos >= n:
            raise JSONError("Unexpected end of input", pos)

        c = s[pos]

        if c == '"':
            pos += 1
            return ''.join(parts), pos

        if c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            esc = s[pos]
            if esc == '"':
                parts.append('"')
                pos += 1
            elif esc == '\\':
                parts.append('\\')
                pos += 1
            elif esc == '/':
                parts.append('/')
                pos += 1
            elif esc == 'b':
                parts.append('\b')
                pos += 1
            elif esc == 'f':
                parts.append('\f')
                pos += 1
            elif esc == 'n':
                parts.append('\n')
                pos += 1
            elif esc == 'r':
                parts.append('\r')
                pos += 1
            elif esc == 't':
                parts.append('\t')
                pos += 1
            elif esc == 'u':
                pos += 1
                if pos + 4 > n:
                    raise JSONError("Unexpected end of input", n)
                for i in range(4):
                    if not _is_hex(s[pos + i]):
                        raise JSONError("Invalid unicode escape", pos + i)
                code = int(s[pos:pos + 4], 16)
                pos += 4

                if 0xD800 <= code <= 0xDBFF:
                    # high surrogate – try to combine with a following \uXXXX low surrogate
                    if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'):
                        h2 = s[pos + 2:pos + 6]
                        valid = (_is_hex(h2[0]) and _is_hex(h2[1]) and
                                 _is_hex(h2[2]) and _is_hex(h2[3]))
                        if valid:
                            code2 = int(h2, 16)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                parts.append(chr(combined))
                                pos += 6
                            else:
                                parts.append(chr(code))
                        else:
                            parts.append(chr(code))
                    else:
                        parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError("Invalid escape character", pos)

        elif ord(c) < 0x20:
            raise JSONError("Control character in string", pos)

        else:
            parts.append(c)
            pos += 1
