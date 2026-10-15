"""Strict RFC 8259 JSON parser – hand-written, standard-library-only."""


class JSONError(ValueError):
    """Raised on any JSON parsing error."""
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0
    stack: list = []  # entries: ['a', list] or ['o', dict, pending_key]

    state = 'val'
    result = None

    while True:
        # skip whitespace: only U+0020, U+0009, U+000A, U+000D
        while pos < n:
            ch = s[pos]
            if ch == ' ' or ch == '\t' or ch == '\n' or ch == '\r':
                pos += 1
            else:
                break

        if state == 'val':
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            c = s[pos]
            if c == '{':
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos)
                stack.append(['o', {}, None])
                pos += 1
                state = 'obj_first'
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("Maximum nesting depth exceeded", pos)
                stack.append(['a', []])
                pos += 1
                state = 'arr_first'
            elif c == '"':
                val, pos = _parse_string(s, pos, n)
                result, state = _deliver(stack, val)
            elif c == '-' or ('0' <= c <= '9'):
                val, pos = _parse_number(s, pos, n)
                result, state = _deliver(stack, val)
            elif c == 't':
                pos = _match_lit(s, pos, n, 'true')
                result, state = _deliver(stack, True)
            elif c == 'f':
                pos = _match_lit(s, pos, n, 'false')
                result, state = _deliver(stack, False)
            elif c == 'n':
                pos = _match_lit(s, pos, n, 'null')
                result, state = _deliver(stack, None)
            else:
                raise JSONError(f"Unexpected character {c!r}", pos)

        elif state == 'arr_first':
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == ']':
                pos += 1
                val = stack.pop()[1]
                result, state = _deliver(stack, val)
            else:
                state = 'val'
                continue

        elif state == 'arr_sep':
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == ',':
                pos += 1
                state = 'val'
            elif s[pos] == ']':
                pos += 1
                val = stack.pop()[1]
                result, state = _deliver(stack, val)
            else:
                raise JSONError("Expected ',' or ']'", pos)

        elif state == 'obj_first':
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == '}':
                pos += 1
                val = stack.pop()[1]
                result, state = _deliver(stack, val)
            elif s[pos] == '"':
                key, pos = _parse_string(s, pos, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("Expected '\"' or '}'", pos)

        elif state == 'obj_colon':
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == ':':
                pos += 1
                state = 'val'
            else:
                raise JSONError("Expected ':'", pos)

        elif state == 'obj_sep':
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == ',':
                pos += 1
                state = 'obj_key'
            elif s[pos] == '}':
                pos += 1
                val = stack.pop()[1]
                result, state = _deliver(stack, val)
            else:
                raise JSONError("Expected ',' or '}'", pos)

        elif state == 'obj_key':
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == '"':
                key, pos = _parse_string(s, pos, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("Expected '\"'", pos)

        elif state == 'done':
            if pos < n:
                raise JSONError("Trailing garbage", pos)
            return result


# --------------- helpers (module-private) ---------------

def _deliver(stack, val):
    if not stack:
        return val, 'done'
    top = stack[-1]
    if top[0] == 'a':
        top[1].append(val)
        return None, 'arr_sep'
    else:
        top[1][top[2]] = val
        top[2] = None
        return None, 'obj_sep'


def _match_lit(s, pos, n, lit):
    for i, c in enumerate(lit):
        if pos + i >= n:
            raise JSONError("Unexpected end of input", n)
        if s[pos + i] != c:
            raise JSONError("Invalid literal", pos + i)
    return pos + len(lit)


def _parse_number(s, pos, n):
    start = pos
    is_float = False

    if s[pos] == '-':
        pos += 1

    if pos >= n:
        raise JSONError("Unexpected end of input", pos)

    c = s[pos]
    if c == '0':
        pos += 1
    elif '1' <= c <= '9':
        pos += 1
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1
    else:
        raise JSONError("Invalid number", pos)

    if pos < n and s[pos] == '.':
        is_float = True
        pos += 1
        if pos >= n or not ('0' <= s[pos] <= '9'):
            raise JSONError("Invalid number", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    if pos < n and (s[pos] == 'e' or s[pos] == 'E'):
        is_float = True
        pos += 1
        if pos < n and (s[pos] == '+' or s[pos] == '-'):
            pos += 1
        if pos >= n or not ('0' <= s[pos] <= '9'):
            raise JSONError("Invalid number", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if is_float:
        return float(text), pos
    return int(text), pos


def _parse_string(s, pos, n):
    pos += 1  # skip opening "
    parts: list = []

    while pos < n:
        c = s[pos]

        if c == '"':
            pos += 1
            return ''.join(parts), pos

        if c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", n)
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
                pos += 1  # skip 'u'
                if pos + 4 > n:
                    raise JSONError("Unexpected end of input", n)
                cp = 0
                for i in range(4):
                    h = s[pos + i]
                    if '0' <= h <= '9':
                        d = ord(h) - 48
                    elif 'a' <= h <= 'f':
                        d = ord(h) - 87
                    elif 'A' <= h <= 'F':
                        d = ord(h) - 55
                    else:
                        raise JSONError("Invalid hex digit", pos + i)
                    cp = cp * 16 + d
                pos += 4
                # surrogate pair handling
                if 0xD800 <= cp <= 0xDBFF:
                    if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'):
                        valid = True
                        lo = 0
                        for i in range(4):
                            h = s[pos + 2 + i]
                            if '0' <= h <= '9':
                                d = ord(h) - 48
                            elif 'a' <= h <= 'f':
                                d = ord(h) - 87
                            elif 'A' <= h <= 'F':
                                d = ord(h) - 55
                            else:
                                valid = False
                                break
                            lo = lo * 16 + d
                        if valid and 0xDC00 <= lo <= 0xDFFF:
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                            pos += 6
                parts.append(chr(cp))
            else:
                raise JSONError("Invalid escape", pos)
            continue

        if ord(c) < 0x20:
            raise JSONError("Control character in string", pos)

        # fast path: consume a run of ordinary characters
        end = pos + 1
        while end < n:
            ch = s[end]
            if ch == '"' or ch == '\\' or ord(ch) < 0x20:
                break
            end += 1
        parts.append(s[pos:end])
        pos = end

    raise JSONError("Unterminated string", n)
