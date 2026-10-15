import re


class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


_WS = ' \t\n\r'
_STR_SPECIAL_RE = re.compile(r'["\\\x00-\x1f]')


def _is_hex(c):
    return ('0' <= c <= '9') or ('a' <= c <= 'f') or ('A' <= c <= 'F')


def _hex_val(c):
    if '0' <= c <= '9':
        return ord(c) - 48
    if 'a' <= c <= 'f':
        return ord(c) - 87
    return ord(c) - 55


def _parse_string(s, pos, n):
    pos += 1  # skip opening quote
    parts = []

    while True:
        m = _STR_SPECIAL_RE.search(s, pos, n)
        if m is None:
            raise JSONError("unexpected end of string", n)

        idx = m.start()
        if idx > pos:
            parts.append(s[pos:idx])

        c = s[idx]
        pos = idx

        if c == '"':
            return ''.join(parts), pos + 1

        if c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of string", n)

            e = s[pos]
            if e == '"':
                parts.append('"'); pos += 1
            elif e == '\\':
                parts.append('\\'); pos += 1
            elif e == '/':
                parts.append('/'); pos += 1
            elif e == 'b':
                parts.append('\b'); pos += 1
            elif e == 'f':
                parts.append('\f'); pos += 1
            elif e == 'n':
                parts.append('\n'); pos += 1
            elif e == 'r':
                parts.append('\r'); pos += 1
            elif e == 't':
                parts.append('\t'); pos += 1
            elif e == 'u':
                pos += 1
                cp = 0
                for i in range(4):
                    if pos + i >= n:
                        raise JSONError("unexpected end of string", n)
                    h = s[pos + i]
                    if not _is_hex(h):
                        raise JSONError("invalid unicode escape", pos + i)
                    cp = cp * 16 + _hex_val(h)
                pos += 4

                if 0xD800 <= cp <= 0xDBFF:
                    if (pos + 5 < n and s[pos] == '\\' and s[pos + 1] == 'u'
                            and _is_hex(s[pos + 2]) and _is_hex(s[pos + 3])
                            and _is_hex(s[pos + 4]) and _is_hex(s[pos + 5])):
                        lo = 0
                        for i in range(4):
                            lo = lo * 16 + _hex_val(s[pos + 2 + i])
                        if 0xDC00 <= lo <= 0xDFFF:
                            combined = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                            parts.append(chr(combined))
                            pos += 6
                        else:
                            parts.append(chr(cp))
                    else:
                        parts.append(chr(cp))
                else:
                    parts.append(chr(cp))
            else:
                raise JSONError("invalid escape", pos)

        else:
            # control character
            raise JSONError("control character in string", pos)


def _parse_literal(s, pos, n, literal):
    for i in range(len(literal)):
        if pos + i >= n:
            raise JSONError("unexpected end of input", n)
        if s[pos + i] != literal[i]:
            raise JSONError("invalid literal", pos + i)
    return pos + len(literal)


def _parse_number(s, pos, n):
    start = pos
    is_int = True

    if pos < n and s[pos] == '-':
        pos += 1

    if pos >= n:
        raise JSONError("unexpected end of input", n)

    if s[pos] == '0':
        pos += 1
        if pos < n and '0' <= s[pos] <= '9':
            raise JSONError("leading zero", pos)
    elif '1' <= s[pos] <= '9':
        pos += 1
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    else:
        raise JSONError("invalid number", pos)

    if pos < n and s[pos] == '.':
        is_int = False
        pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("invalid number", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    if pos < n and s[pos] in 'eE':
        is_int = False
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[pos] <= '9'):
            raise JSONError("invalid number", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if is_int:
        return int(text), pos
    else:
        return float(text), pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}")

    n = len(s)
    pos = 0
    depth = 0
    stack = []  # list of ('a', list) or ('o', dict)
    top_value = None
    current_key = None

    # States:
    #   top        - expect top-level value
    #   arr_val    - expect a value inside an array
    #   obj_val    - expect a value inside an object
    #   arr_end    - after value in array, expect ',' or ']'
    #   obj_end    - after value in object, expect ',' or '}'
    #   arr_first  - just after '[', expect value or ']'
    #   obj_first  - just after '{', expect '"' or '}'
    #   obj_key    - after ',' in object, expect '"'
    #   obj_colon  - after key, expect ':'
    #   done       - after top-level value, expect whitespace/EOF

    state = 'top'

    while True:
        # skip whitespace
        while pos < n and s[pos] in _WS:
            pos += 1

        if pos >= n:
            if state == 'done':
                return top_value
            raise JSONError("unexpected end of input", n)

        if state == 'done':
            raise JSONError("trailing garbage", pos)

        # --- container continuation states ---

        if state == 'arr_end':
            c = s[pos]
            if c == ']':
                pos += 1
                depth -= 1
                val = stack.pop()[1]
                if not stack:
                    top_value = val
                    state = 'done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'arr_end'
                else:
                    stack[-1][1][current_key] = val
                    state = 'obj_end'
                continue
            elif c == ',':
                pos += 1
                state = 'arr_val'
                continue
            else:
                raise JSONError("expected ',' or ']'", pos)

        if state == 'obj_end':
            c = s[pos]
            if c == '}':
                pos += 1
                depth -= 1
                val = stack.pop()[1]
                if not stack:
                    top_value = val
                    state = 'done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'arr_end'
                else:
                    stack[-1][1][current_key] = val
                    state = 'obj_end'
                continue
            elif c == ',':
                pos += 1
                state = 'obj_key'
                continue
            else:
                raise JSONError("expected ',' or '}'", pos)

        if state == 'arr_first':
            if s[pos] == ']':
                pos += 1
                depth -= 1
                val = stack.pop()[1]
                if not stack:
                    top_value = val
                    state = 'done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'arr_end'
                else:
                    stack[-1][1][current_key] = val
                    state = 'obj_end'
                continue
            else:
                state = 'arr_val'
                continue

        if state == 'obj_first':
            c = s[pos]
            if c == '}':
                pos += 1
                depth -= 1
                val = stack.pop()[1]
                if not stack:
                    top_value = val
                    state = 'done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val)
                    state = 'arr_end'
                else:
                    stack[-1][1][current_key] = val
                    state = 'obj_end'
                continue
            elif c == '"':
                current_key, pos = _parse_string(s, pos, n)
                state = 'obj_colon'
                continue
            else:
                raise JSONError("expected '\"' or '}'", pos)

        if state == 'obj_key':
            if s[pos] == '"':
                current_key, pos = _parse_string(s, pos, n)
                state = 'obj_colon'
                continue
            else:
                raise JSONError("expected '\"'", pos)

        if state == 'obj_colon':
            if s[pos] == ':':
                pos += 1
                state = 'obj_val'
                continue
            else:
                raise JSONError("expected ':'", pos)

        # --- value states: top, arr_val, obj_val ---

        c = s[pos]

        if c == '"':
            val, pos = _parse_string(s, pos, n)
        elif c == '[':
            if depth >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            depth += 1
            stack.append(('a', []))
            pos += 1
            state = 'arr_first'
            continue
        elif c == '{':
            if depth >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            depth += 1
            stack.append(('o', {}))
            pos += 1
            state = 'obj_first'
            continue
        elif c == 't':
            pos = _parse_literal(s, pos, n, 'true')
            val = True
        elif c == 'f':
            pos = _parse_literal(s, pos, n, 'false')
            val = False
        elif c == 'n':
            pos = _parse_literal(s, pos, n, 'null')
            val = None
        elif c == '-' or ('0' <= c <= '9'):
            val, pos = _parse_number(s, pos, n)
        else:
            raise JSONError("unexpected character", pos)

        # assign the parsed scalar value
        if state == 'top':
            top_value = val
            state = 'done'
        elif state == 'arr_val':
            stack[-1][1].append(val)
            state = 'arr_end'
        else:  # obj_val
            stack[-1][1][current_key] = val
            state = 'obj_end'
