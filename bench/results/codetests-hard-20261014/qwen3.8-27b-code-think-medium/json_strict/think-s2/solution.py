class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    stack = []  # list of [type_str, container]
    state = 'value'
    result = None
    pending_key = None
    ws = ' \t\n\r'

    while True:
        while pos < n and s[pos] in ws:
            pos += 1

        if state == 'done':
            if pos < n:
                raise JSONError("trailing characters after top-level value", pos)
            return result

        if pos >= n:
            raise JSONError("unexpected end of input", pos)

        c = s[pos]

        if state == 'array_sep':
            if c == ',':
                pos += 1
                state = 'value'
                continue
            if c == ']':
                pos += 1
                _, arr = stack.pop()
                if not stack:
                    result = arr
                    state = 'done'
                else:
                    typ, container = stack[-1]
                    if typ == 'array':
                        container.append(arr)
                        state = 'array_sep'
                    else:
                        container[pending_key] = arr
                        state = 'obj_sep'
                continue
            raise JSONError(f"expected ',' or ']', got {c!r}", pos)

        if state == 'obj_sep':
            if c == ',':
                pos += 1
                state = 'obj_key'
                continue
            if c == '}':
                pos += 1
                _, obj = stack.pop()
                if not stack:
                    result = obj
                    state = 'done'
                else:
                    typ, container = stack[-1]
                    if typ == 'array':
                        container.append(obj)
                        state = 'array_sep'
                    else:
                        container[pending_key] = obj
                        state = 'obj_sep'
                continue
            raise JSONError(f"expected ',' or '}}', got {c!r}", pos)

        if state == 'obj_key_or_end':
            if c == '}':
                pos += 1
                _, obj = stack.pop()
                if not stack:
                    result = obj
                    state = 'done'
                else:
                    typ, container = stack[-1]
                    if typ == 'array':
                        container.append(obj)
                        state = 'array_sep'
                    else:
                        container[pending_key] = obj
                        state = 'obj_sep'
                continue
            if c == '"':
                pending_key, pos = _parse_string(s, pos, n)
                state = 'obj_colon'
                continue
            raise JSONError(f"expected string key or '}}', got {c!r}", pos)

        if state == 'obj_key':
            if c == '"':
                pending_key, pos = _parse_string(s, pos, n)
                state = 'obj_colon'
                continue
            raise JSONError(f"expected string key, got {c!r}", pos)

        if state == 'obj_colon':
            if c == ':':
                pos += 1
                state = 'value'
                continue
            raise JSONError(f"expected ':', got {c!r}", pos)

        if state == 'array_val_or_end':
            if c == ']':
                pos += 1
                _, arr = stack.pop()
                if not stack:
                    result = arr
                    state = 'done'
                else:
                    typ, container = stack[-1]
                    if typ == 'array':
                        container.append(arr)
                        state = 'array_sep'
                    else:
                        container[pending_key] = arr
                        state = 'obj_sep'
                continue
            # fall through to parse a value

        # --- Parse a value ---
        if c == '{':
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            stack.append(['object', {}])
            state = 'obj_key_or_end'

        elif c == '[':
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            stack.append(['array', []])
            state = 'array_val_or_end'

        elif c == '"':
            val, pos = _parse_string(s, pos, n)
            if not stack:
                result = val
                state = 'done'
            else:
                typ, container = stack[-1]
                if typ == 'array':
                    container.append(val)
                    state = 'array_sep'
                else:
                    container[pending_key] = val
                    state = 'obj_sep'

        elif c == 't':
            lit = 'true'
            if (pos + 4 <= n and s[pos] == 't' and s[pos + 1] == 'r'
                    and s[pos + 2] == 'u' and s[pos + 3] == 'e'):
                pos += 4
                val = True
            else:
                for i in range(4):
                    if pos + i >= n or s[pos + i] != lit[i]:
                        raise JSONError("invalid literal", pos + i)
                raise JSONError("unexpected end of input", pos)
            if not stack:
                result = val
                state = 'done'
            else:
                typ, container = stack[-1]
                if typ == 'array':
                    container.append(val)
                    state = 'array_sep'
                else:
                    container[pending_key] = val
                    state = 'obj_sep'

        elif c == 'f':
            lit = 'false'
            if (pos + 5 <= n and s[pos] == 'f' and s[pos + 1] == 'a'
                    and s[pos + 2] == 'l' and s[pos + 3] == 's'
                    and s[pos + 4] == 'e'):
                pos += 5
                val = False
            else:
                for i in range(5):
                    if pos + i >= n or s[pos + i] != lit[i]:
                        raise JSONError("invalid literal", pos + i)
                raise JSONError("unexpected end of input", pos)
            if not stack:
                result = val
                state = 'done'
            else:
                typ, container = stack[-1]
                if typ == 'array':
                    container.append(val)
                    state = 'array_sep'
                else:
                    container[pending_key] = val
                    state = 'obj_sep'

        elif c == 'n':
            lit = 'null'
            if (pos + 4 <= n and s[pos] == 'n' and s[pos + 1] == 'u'
                    and s[pos + 2] == 'l' and s[pos + 3] == 'l'):
                pos += 4
                val = None
            else:
                for i in range(4):
                    if pos + i >= n or s[pos + i] != lit[i]:
                        raise JSONError("invalid literal", pos + i)
                raise JSONError("unexpected end of input", pos)
            if not stack:
                result = val
                state = 'done'
            else:
                typ, container = stack[-1]
                if typ == 'array':
                    container.append(val)
                    state = 'array_sep'
                else:
                    container[pending_key] = val
                    state = 'obj_sep'

        elif c == '-' or '0' <= c <= '9':
            val, pos = _parse_number(s, pos, n)
            if not stack:
                result = val
                state = 'done'
            else:
                typ, container = stack[-1]
                if typ == 'array':
                    container.append(val)
                    state = 'array_sep'
                else:
                    container[pending_key] = val
                    state = 'obj_sep'

        else:
            raise JSONError(f"unexpected character {c!r}", pos)


def _parse_string(s, pos, n):
    pos += 1  # skip opening quote
    chars = []

    while True:
        if pos >= n:
            raise JSONError("unexpected end of input in string", pos)

        c = s[pos]

        if c == '"':
            pos += 1
            return ''.join(chars), pos

        if c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in string escape", pos)
            ec = s[pos]
            if ec == '"':
                chars.append('"')
                pos += 1
            elif ec == '\\':
                chars.append('\\')
                pos += 1
            elif ec == '/':
                chars.append('/')
                pos += 1
            elif ec == 'b':
                chars.append('\b')
                pos += 1
            elif ec == 'f':
                chars.append('\f')
               