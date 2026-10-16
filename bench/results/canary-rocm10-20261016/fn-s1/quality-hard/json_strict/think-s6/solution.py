import re


class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


_STRING_SPECIAL = re.compile(r'["\\\x00-\x1f]')


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__}")

    n = len(s)
    i = 0
    stack = []  # list of [type, container, key]
    result = None
    state = 'value'

    def skip_ws():
        nonlocal i
        while i < n and s[i] in ' \t\n\r':
            i += 1

    def error(msg, pos):
        raise JSONError(msg, pos)

    def parse_hex4():
        nonlocal i
        code = 0
        for _ in range(4):
            if i >= n:
                error("Unexpected end of input", n)
            c = s[i]
            if '0' <= c <= '9':
                code = code * 16 + (ord(c) - 48)
            elif 'a' <= c <= 'f':
                code = code * 16 + (ord(c) - 87)
            elif 'A' <= c <= 'F':
                code = code * 16 + (ord(c) - 55)
            else:
                error("Invalid hex digit", i)
            i += 1
        return code

    def parse_string():
        nonlocal i
        i += 1  # skip opening "
        parts = []

        while True:
            m = _STRING_SPECIAL.search(s, i)
            if m is None:
                parts.append(s[i:])
                error("Unexpected end of input", n)

            j = m.start()
            if j > i:
                parts.append(s[i:j])
            i = j
            c = s[i]

            if c == '"':
                i += 1
                return ''.join(parts)
            elif c == '\\':
                i += 1
                if i >= n:
                    error("Unexpected end of input", n)
                ec = s[i]
                if ec == '"':
                    parts.append('"')
                    i += 1
                elif ec == '\\':
                    parts.append('\\')
                    i += 1
                elif ec == '/':
                    parts.append('/')
                    i += 1
                elif ec == 'b':
                    parts.append('\b')
                    i += 1
                elif ec == 'f':
                    parts.append('\f')
                    i += 1
                elif ec == 'n':
                    parts.append('\n')
                    i += 1
                elif ec == 'r':
                    parts.append('\r')
                    i += 1
                elif ec == 't':
                    parts.append('\t')
                    i += 1
                elif ec == 'u':
                    i += 1
                    code = parse_hex4()
                    if 0xD800 <= code <= 0xDBFF:
                        # High surrogate: check for immediately following low surrogate
                        if i + 1 < n and s[i] == '\\' and s[i + 1] == 'u':
                            save_i = i
                            i += 2
                            code2 = parse_hex4()
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                parts.append(chr(combined))
                            else:
                                # Not a low surrogate; emit lone high, re-parse next escape
                                i = save_i
                                parts.append(chr(code))
                                continue
                        else:
                            parts.append(chr(code))
                    else:
                        parts.append(chr(code))
                else:
                    error("Invalid escape", i)
            else:
                # Control character (U+0000..U+001F)
                error("Control character in string", i)

    def parse_number():
        nonlocal i
        num_start = i
        is_float = False

        if i < n and s[i] == '-':
            i += 1

        if i >= n:
            error("Unexpected end of input", n)
        c = s[i]
        if c == '0':
            i += 1
        elif '1' <= c <= '9':
            i += 1
            while i < n and '0' <= s[i] <= '9':
                i += 1
        else:
            error("Invalid number", i)

        if i < n and s[i] == '.':
            is_float = True
            i += 1
            if i >= n:
                error("Unexpected end of input", n)
            if not ('0' <= s[i] <= '9'):
                error("Invalid number", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1

        if i < n and s[i] in 'eE':
            is_float = True
            i += 1
            if i < n and s[i] in '+-':
                i += 1
            if i >= n:
                error("Unexpected end of input", n)
            if not ('0' <= s[i] <= '9'):
                error("Invalid number", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1

        text = s[num_start:i]
        if is_float:
            return float(text)
        return int(text)

    def parse_literal(expected, val):
        nonlocal i
        for c in expected:
            if i >= n:
                error("Unexpected end of input", n)
            if s[i] != c:
                error("Invalid literal", i)
            i += 1
        return val

    def complete_value(val):
        nonlocal state, result
        if not stack:
            result = val
            state = 'done'
        elif stack[-1][0] == 'a':
            stack[-1][1].append(val)
            state = 'array_end'
        else:
            stack[-1][1][stack[-1][2]] = val
            state = 'obj_end'

    while True:
        if state == 'value':
            skip_ws()
            if i >= n:
                error("Unexpected end of input", n)
            c = s[i]
            if c == '{':
                if len(stack) >= 500:
                    error("Maximum nesting depth exceeded", i)
                stack.append(['o', {}, None])
                i += 1
                state = 'obj_first'
            elif c == '[':
                if len(stack) >= 500:
                    error("Maximum nesting depth exceeded", i)
                stack.append(['a', [], None])
                i += 1
                state = 'array_first'
            elif c == '"':
                complete_value(parse_string())
            elif c == 't':
                complete_value(parse_literal('true', True))
            elif c == 'f':
                complete_value(parse_literal('false', False))
            elif c == 'n':
                complete_value(parse_literal('null', None))
            elif c == '-' or '0' <= c <= '9':
                complete_value(parse_number())
            else:
                error("Unexpected character", i)

        elif state == 'array_first':
            skip_ws()
            if i >= n:
                error("Unexpected end of input", n)
            if s[i] == ']':
                i += 1
                stack.pop()
                complete_value([])
            else:
                state = 'value'

        elif state == 'array_end':
            skip_ws()
            if i >= n:
                error("Unexpected end of input", n)
            if s[i] == ',':
                i += 1
                state = 'value'
            elif s[i] == ']':
                i += 1
                lst = stack.pop()[1]
                complete_value(lst)
            else:
                error("Expected ',' or ']'", i)

        elif state == 'obj_first':
            skip_ws()
            if i >= n:
                error("Unexpected end of input", n)
            if s[i] == '}':
                i += 1
                stack.pop()
                complete_value({})
            elif s[i] == '"':
                key = parse_string()
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                error("Expected '\"' or '}'", i)

        elif state == 'obj_colon':
            skip_ws()
            if i >= n:
                error("Unexpected end of input", n)
            if s[i] == ':':
                i += 1
                state = 'value'
            else:
                error("Expected ':'", i)

        elif state == 'obj_end':
            skip_ws()
            if i >= n:
                error("Unexpected end of input", n)
            if s[i] == ',':
                i += 1
                state = 'obj_key'
            elif s[i] == '}':
                i += 1
                dct = stack.pop()[1]
                complete_value(dct)
            else:
                error("Expected ',' or '}'", i)

        elif state == 'obj_key':
            skip_ws()
            if i >= n:
                error("Unexpected end of input", n)
            if s[i] == '"':
                key = parse_string()
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                error("Expected '\"'", i)

        elif state == 'done':
            skip_ws()
            if i >= n:
                return result
            error("Extra data", i)
