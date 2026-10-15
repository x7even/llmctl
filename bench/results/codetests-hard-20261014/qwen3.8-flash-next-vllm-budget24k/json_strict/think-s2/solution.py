import re


class JSONError(ValueError):
    def __init__(self, message, pos):
        super().__init__(message)
        self.pos = pos


_STR_SPECIAL = re.compile(r'["\\\x00-\x1f]')


def loads(s):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0

    def err(msg, p):
        raise JSONError(msg, p)

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening "
        parts = []
        while True:
            m = _STR_SPECIAL.search(s, pos)
            if m is None:
                err("unterminated string", n)
            parts.append(s[pos:m.start()])
            pos = m.start()
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(parts)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    err("unexpected end", n)
                e = s[pos]
                if e == '"':
                    parts.append('"')
                    pos += 1
                elif e == '\\':
                    parts.append('\\')
                    pos += 1
                elif e == '/':
                    parts.append('/')
                    pos += 1
                elif e == 'b':
                    parts.append('\b')
                    pos += 1
                elif e == 'f':
                    parts.append('\f')
                    pos += 1
                elif e == 'n':
                    parts.append('\n')
                    pos += 1
                elif e == 'r':
                    parts.append('\r')
                    pos += 1
                elif e == 't':
                    parts.append('\t')
                    pos += 1
                elif e == 'u':
                    pos += 1
                    if pos + 4 > n:
                        err("unexpected end", n)
                    for i in range(4):
                        ch = s[pos + i]
                        if not (('0' <= ch <= '9') or ('a' <= ch <= 'f') or ('A' <= ch <= 'F')):
                            err("invalid hex", pos + i)
                    code = int(s[pos:pos + 4], 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'):
                            valid = True
                            for i in range(4):
                                ch = s[pos + 2 + i]
                                if not (('0' <= ch <= '9') or ('a' <= ch <= 'f') or ('A' <= ch <= 'F')):
                                    valid = False
                                    break
                            if valid:
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
                    err("invalid escape", pos)
            else:
                err("control character in string", pos)

    def parse_number():
        nonlocal pos
        start = pos
        is_float = False

        if s[pos] == '-':
            pos += 1

        if pos >= n:
            err("unexpected end", n)

        c = s[pos]
        if c == '0':
            pos += 1
            if pos < n and '0' <= s[pos] <= '9':
                err("leading zeros", pos)
        elif '1' <= c <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            err("expected digit", pos)

        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                err("expected digit after decimal", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                err("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    # Iterative parser with explicit stack
    # Stack entries: ['A', list] or ['O', dict, key]
    stack = []
    result = None
    value = None

    # States:
    # -1 DELIVER, 0 VALUE, 1 ARRAY_FIRST, 2 ARRAY_SEP, 3 ARRAY_NEXT,
    #  4 OBJ_FIRST, 5 OBJ_COLON, 6 OBJ_VAL, 7 OBJ_SEP, 8 OBJ_NEXT, 9 DONE
    state = 0

    while True:
        if state == -1:  # DELIVER
            if not stack:
                result = value
                state = 9
            elif stack[-1][0] == 'A':
                stack[-1][1].append(value)
                state = 2
            else:
                stack[-1][1][stack[-1][2]] = value
                state = 7

        elif state == 0:  # VALUE
            skip_ws()
            if pos >= n:
                err("unexpected end of input", pos)
            c = s[pos]
            if c == '[':
                if len(stack) >= 500:
                    err("depth exceeded", pos)
                pos += 1
                stack.append(['A', []])
                state = 1
            elif c == '{':
                if len(stack) >= 500:
                    err("depth exceeded", pos)
                pos += 1
                stack.append(['O', {}, None])
                state = 4
            elif c == '"':
                value = parse_string()
                state = -1
            elif c == 't':
                if pos + 4 > n:
                    err("unexpected end", n)
                if s[pos:pos + 4] != 'true':
                    for i in range(1, 4):
                        if s[pos + i] != 'true'[i]:
                            err("invalid literal", pos + i)
                pos += 4
                value = True
                state = -1
            elif c == 'f':
                if pos + 5 > n:
                    err("unexpected end", n)
                if s[pos:pos + 5] != 'false':
                    for i in range(1, 5):
                        if s[pos + i] != 'false'[i]:
                            err("invalid literal", pos + i)
                pos += 5
                value = False
                state = -1
            elif c == 'n':
                if pos + 4 > n:
                    err("unexpected end", n)
                if s[pos:pos + 4] != 'null':
                    for i in range(1, 4):
                        if s[pos + i] != 'null'[i]:
                            err("invalid literal", pos + i)
                pos += 4
                value = None
                state = -1
            elif c == '-' or ('0' <= c <= '9'):
                value = parse_number()
                state = -1
            else:
                err("unexpected character", pos)

        elif state == 1:  # ARRAY_FIRST
            skip_ws()
            if pos >= n:
                err("unexpected end", pos)
            if s[pos] == ']':
                pos += 1
                value = stack[-1][1]
                stack.pop()
                state = -1
            else:
                state = 0

        elif state == 2:  # ARRAY_SEP
            skip_ws()
            if pos >= n:
                err("unexpected end", pos)
            if s[pos] == ']':
                pos += 1
                value = stack[-1][1]
                stack.pop()
                state = -1
            elif s[pos] == ',':
                pos += 1
                state = 3
            else:
                err("expected , or ]", pos)

        elif state == 3:  # ARRAY_NEXT
            state = 0

        elif state == 4:  # OBJ_FIRST
            skip_ws()
            if pos >= n:
                err("unexpected end", pos)
            if s[pos] == '}':
                pos += 1
                value = stack[-1][1]
                stack.pop()
                state = -1
            elif s[pos] == '"':
                key = parse_string()
                stack[-1][2] = key
                state = 5
            else:
                err("expected \" or }", pos)

        elif state == 5:  # OBJ_COLON
            skip_ws()
            if pos >= n:
                err("unexpected end", pos)
            if s[pos] == ':':
                pos += 1
                state = 6
            else:
                err("expected :", pos)

        elif state == 6:  # OBJ_VAL
            state = 0

        elif state == 7:  # OBJ_SEP
            skip_ws()
            if pos >= n:
                err("unexpected end", pos)
            if s[pos] == '}':
                pos += 1
                value = stack[-1][1]
                stack.pop()
                state = -1
            elif s[pos] == ',':
                pos += 1
                state = 8
            else:
                err("expected , or }", pos)

        elif state == 8:  # OBJ_NEXT
            skip_ws()
            if pos >= n:
                err("unexpected end", pos)
            if s[pos] == '"':
                key = parse_string()
                stack[-1][2] = key
                state = 5
            else:
                err("expected \"", pos)

        elif state == 9:  # DONE
            skip_ws()
            if pos < n:
                err("trailing garbage", pos)
            return result
