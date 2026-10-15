class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    i = 0
    WS = ' \t\n\r'
    HEX = '0123456789abcdefABCDEF'

    # Stack entries: [type, state, container, key]
    #   type: 'array' | 'object'
    #   state: 'first' | 'value' | 'comma_or_end' | 'key' | 'colon'
    #   container: list | dict
    #   key: str | None
    stack = []
    result = None
    done = False

    def skip_ws():
        nonlocal i
        while i < n and s[i] in WS:
            i += 1

    def check_value_state():
        nonlocal i
        if not stack:
            return
        top = stack[-1]
        t, state = top[0], top[1]
        if t == 'array' and state in ('first', 'value'):
            return
        if t == 'object' and state == 'value':
            return
        raise JSONError("unexpected value", i)

    def parse_string():
        nonlocal i
        # s[i] == '"'
        i += 1
        chars = []
        while True:
            if i >= n:
                raise JSONError("unterminated string", n)
            c = s[i]
            if c == '"':
                i += 1
                return ''.join(chars), i
            elif c == '\\':
                i += 1
                if i >= n:
                    raise JSONError("unterminated string escape", n)
                ec = s[i]
                if ec == '"':
                    chars.append('"'); i += 1
                elif ec == '\\':
                    chars.append('\\'); i += 1
                elif ec == '/':
                    chars.append('/'); i += 1
                elif ec == 'b':
                    chars.append('\b'); i += 1
                elif ec == 'f':
                    chars.append('\f'); i += 1
                elif ec == 'n':
                    chars.append('\n'); i += 1
                elif ec == 'r':
                    chars.append('\r'); i += 1
                elif ec == 't':
                    chars.append('\t'); i += 1
                elif ec == 'u':
                    i += 1
                    if i + 4 > n:
                        raise JSONError("truncated \\u escape", n)
                    h = s[i:i + 4]
                    for j in range(4):
                        if h[j] not in HEX:
                            raise JSONError("invalid hex digit in \\u escape", i + j)
                    code = int(h, 16)
                    i += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u':
                            h2 = s[i + 2:i + 6]
                            if all(c2 in HEX for c2 in h2):
                                code2 = int(h2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    chars.append(chr(combined))
                                    i += 6
                                    continue
                    chars.append(chr(code))
                else:
                    raise JSONError(f"invalid escape '\\{ec}'", i)
            elif ord(c) < 0x20:
                raise JSONError("control character in string", i)
            else:
                chars.append(c)
                i += 1

    def parse_number():
        nonlocal i
        start = i
        if i < n and s[i] == '-':
            i += 1
        if i >= n:
            raise JSONError("truncated number", n)
        c = s[i]
        if c == '0':
            i += 1
            if i < n and '0' <= s[i] <= '9':
                raise JSONError("leading zero in number", i)
        elif '1' <= c <= '9':
            i += 1
            while i < n and '0' <= s[i] <= '9':
                i += 1
        else:
            raise JSONError("expected digit in number", i)

        is_float = False
        if i < n and s[i] == '.':
            is_float = True
            i += 1
            if i >= n:
                raise JSONError("truncated number", n)
            if not ('0' <= s[i] <= '9'):
                raise JSONError("expected digit after '.'", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1
        if i < n and s[i] in 'eE':
            is_float = True
            i += 1
            if i < n and s[i] in '+-':
                i += 1
            if i >= n:
                raise JSONError("truncated number", n)
            if not ('0' <= s[i] <= '9'):
                raise JSONError("expected digit in exponent", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1

        text = s[start:i]
        if is_float:
            return float(text), i
        else:
            return int(text), i

    def commit_value(val):
        nonlocal result, done
        if not stack:
            result = val
            done = True
            return
        top = stack[-1]
        t, state, container, key = top[0], top[1], top[2], top[3]
        if t == 'array':
            container.append(val)
            top[1] = 'comma_or_end'
        else:
            container[key] = val
            top[1] = 'comma_or_end'
            top[3] = None

    while not done:
        skip_ws()
        if i >= n:
            raise JSONError("unexpected end of input", n)

        c = s[i]

        if c == '{':
            if stack:
                t, state = stack[-1][0], stack[-1][1]
                if not ((t == 'array' and state in ('first', 'value')) or
                        (t == 'object' and state == 'value')):
                    raise JSONError("unexpected '{'", i)
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", i)
            stack.append(['object', 'first', {}, None])
            i += 1

        elif c == '[':
            if stack:
                t, state = stack[-1][0], stack[-1][1]
                if not ((t == 'array' and state in ('first', 'value')) or
                        (t == 'object' and state == 'value')):
                    raise JSONError("unexpected '['", i)
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", i)
            stack.append(['array', 'first', [], None])
            i += 1

        elif c == '"':
            val, i = parse_string()
            if stack:
                t, state = stack[-1][0], stack[-1][1]
                if t == 'array':
                    if state not in ('first', 'value'):
                        raise JSONError("unexpected string", i)
                    stack[-1][2].append(val)
                    stack[-1][1] = 'comma_or_end'
                else:
                    if state in ('first', 'key'):
                        stack[-1][1] = 'colon'
                        stack[-1][3] = val
                    elif state == 'value':
                        stack[-1][2][stack[-1][3]] = val
                        stack[-1][1] = 'comma_or_end'
                        stack[-1][3] = None
                    else:
                        raise JSONError("unexpected string", i)
            else:
                result = val
                done = True

        elif c == 't':
            check_value_state()
            for j in range(4):
                if i + j >= n:
                    raise JSONError("truncated literal", n)
                if s[i + j] != 'true'[j]:
                    raise JSONError("invalid literal", i + j)
            i += 4
            commit_value(True)

        elif c == 'f':
            check_value_state()
            for j in range(5):
                if i + j >= n:
                    raise JSONError("truncated literal", n)
                if s[i + j] != 'false'[j]:
                    raise JSONError("invalid literal", i + j)
            i += 5
            commit_value(False)

        elif c == 'n':
            check_value_state()
            for j in range(4):
                if i + j >= n:
                    raise JSONError("truncated literal", n)
                if s[i + j] != 'null'[j]:
                    raise JSONError("invalid literal", i + j)
            i += 4
            commit_value(None)

        elif c == '-' or ('0' <= c <= '9'):
            check_value_state()
            val, i = parse_number()
            commit_value(val)

        elif c == ']':
            if not stack:
                raise JSONError("unexpected ']", i)
            top = stack[-1]
            if top[0] != 'array':
                raise JSONError("unexpected ']', expected '}'", i)
            if top[1] not in ('first', 'comma_or_end'):
                raise JSONError("unexpected ']', expected ',' or value", i)
            val = top[2]
            stack.pop()
            i += 1
            if stack:
                commit_value(val)
            else:
                result = val
                done = True

        elif c == '}':
            if not stack:
                raise JSONError("unexpected '}'", i)
            top = stack[-1]
            if top[0] != 'object':
                raise JSONError("unexpected '}', expected ']', i)
            if top[1] not in ('first', 'comma_or_end'):
                raise JSONError("unexpected '}', expected ',' or key", i)
            val = top[2]
            stack.pop()
            i += 1
            if stack:
                commit_value(val)
            else:
                result = val
                done = True

        elif c == ',':
            if not stack:
                raise JSONError("unexpected ','", i)
            top = stack[-1]
            if top[1] != 'comma_or_end':
                raise JSONError("unexpected ','", i)
            if top[0] == 'array':
                top[1] = 'value'
            else:
                top[1] = 'key'
            i += 1

        elif c == ':':
            if not stack:
                raise JSONError("unexpected ':'", i)
            top = stack[-1]
            if top[0] != 'object' or top[1] != 'colon':
                raise JSONError("unexpected ':'", i)
            top[1] = 'value'
            i += 1

        else:
            raise JSONError(f"unexpected character {c!r}", i)

    # Check for trailing garbage
    skip_ws()
    if i < n:
        raise JSONError("trailing garbage", i)

    return result
