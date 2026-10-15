class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__}")

    n = len(s)
    i = 0

    def _err(msg, pos):
        raise JSONError(msg, pos)

    def _skip_ws():
        nonlocal i
        while i < n and s[i] in ' \t\n\r':
            i += 1

    def _is_hex(c):
        return ('0' <= c <= '9') or ('a' <= c <= 'f') or ('A' <= c <= 'F')

    def _hex_val(c):
        if '0' <= c <= '9':
            return ord(c) - 48
        if 'a' <= c <= 'f':
            return ord(c) - 87
        return ord(c) - 55

    def _parse_hex4():
        nonlocal i
        val = 0
        for _ in range(4):
            if i >= n:
                _err("unexpected end of input", n)
            c = s[i]
            if '0' <= c <= '9':
                val = val * 16 + (ord(c) - 48)
            elif 'a' <= c <= 'f':
                val = val * 16 + (ord(c) - 87)
            elif 'A' <= c <= 'F':
                val = val * 16 + (ord(c) - 55)
            else:
                _err("invalid hex digit", i)
            i += 1
        return val

    def _parse_string():
        nonlocal i
        i += 1  # skip opening "
        parts = None
        start = i
        while True:
            if i >= n:
                _err("unexpected end of input", n)
            c = s[i]
            if c == '"':
                if parts is not None:
                    parts.append(s[start:i])
                    return ''.join(parts)
                return s[start:i]
            elif c == '\\':
                if parts is None:
                    parts = [s[start:i]]
                else:
                    parts.append(s[start:i])
                i += 1
                if i >= n:
                    _err("unexpected end of input", n)
                esc = s[i]
                if esc == '"':
                    parts.append('"'); i += 1
                elif esc == '\\':
                    parts.append('\\'); i += 1
                elif esc == '/':
                    parts.append('/'); i += 1
                elif esc == 'b':
                    parts.append('\b'); i += 1
                elif esc == 'f':
                    parts.append('\f'); i += 1
                elif esc == 'n':
                    parts.append('\n'); i += 1
                elif esc == 'r':
                    parts.append('\r'); i += 1
                elif esc == 't':
                    parts.append('\t'); i += 1
                elif esc == 'u':
                    i += 1
                    code = _parse_hex4()
                    if 0xD800 <= code <= 0xDBFF:
                        if (i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u' and
                                _is_hex(s[i + 2]) and _is_hex(s[i + 3]) and
                                _is_hex(s[i + 4]) and _is_hex(s[i + 5])):
                            lo = (_hex_val(s[i + 2]) << 12 |
                                  _hex_val(s[i + 3]) << 8 |
                                  _hex_val(s[i + 4]) << 4 |
                                  _hex_val(s[i + 5]))
                            if 0xDC00 <= lo <= 0xDFFF:
                                i += 6
                                parts.append(chr(0x10000 + ((code - 0xD800) << 10) + (lo - 0xDC00)))
                            else:
                                parts.append(chr(code))
                        else:
                            parts.append(chr(code))
                    else:
                        parts.append(chr(code))
                    start = i
                else:
                    _err("invalid escape", i)
            elif ord(c) < 0x20:
                _err("control character in string", i)
            else:
                i += 1

    def _parse_number():
        nonlocal i
        start = i
        is_float = False

        if s[i] == '-':
            i += 1

        if i >= n:
            _err("unexpected end of input", n)
        c = s[i]
        if c == '0':
            i += 1
        elif '1' <= c <= '9':
            i += 1
            while i < n and '0' <= s[i] <= '9':
                i += 1
        else:
            _err("expected digit", i)

        if i < n and s[i] == '.':
            is_float = True
            i += 1
            if i >= n:
                _err("unexpected end of input", n)
            if not ('0' <= s[i] <= '9'):
                _err("expected digit", i)
            i += 1
            while i < n and '0' <= s[i] <= '9':
                i += 1

        if i < n and s[i] in 'eE':
            is_float = True
            i += 1
            if i < n and s[i] in '+-':
                i += 1
            if i >= n:
                _err("unexpected end of input", n)
            if not ('0' <= s[i] <= '9'):
                _err("expected digit", i)
            i += 1
            while i < n and '0' <= s[i] <= '9':
                i += 1

        text = s[start:i]
        if is_float:
            return float(text)
        return int(text)

    stack = []
    result = None
    state = 'value'

    def _deliver(val):
        nonlocal state, result
        if not stack:
            result = val
            state = 'done'
        else:
            top = stack[-1]
            if top[0] == 'array':
                top[1].append(val)
                state = 'array_comma'
            else:
                top[1][top[2]] = val
                state = 'obj_comma'

    def _match_literal(lit, val):
        nonlocal i
        for c in lit:
            if i >= n:
                _err("unexpected end of input", n)
            if s[i] != c:
                _err("invalid literal", i)
            i += 1
        _deliver(val)

    while True:
        if state == 'value':
            _skip_ws()
            if i >= n:
                _err("unexpected end of input", n)
            c = s[i]
            if c == '{':
                if len(stack) >= 500:
                    _err("depth limit exceeded", i)
                stack.append(['object', {}, None])
                i += 1
                state = 'obj_start'
            elif c == '[':
                if len(stack) >= 500:
                    _err("depth limit exceeded", i)
                stack.append(['array', [], None])
                i += 1
                state = 'array_start'
            elif c == '"':
                _deliver(_parse_string())
            elif c == 't':
                _match_literal("true", True)
            elif c == 'f':
                _match_literal("false", False)
            elif c == 'n':
                _match_literal("null", None)
            elif c == '-' or ('0' <= c <= '9'):
                _deliver(_parse_number())
            else:
                _err("unexpected character", i)

        elif state == 'array_start':
            _skip_ws()
            if i >= n:
                _err("unexpected end of input", n)
            if s[i] == ']':
                i += 1
                _deliver(stack.pop()[1])
            else:
                state = 'value'

        elif state == 'array_comma':
            _skip_ws()
            if i >= n:
                _err("unexpected end of input", n)
            if s[i] == ']':
                i += 1
                _deliver(stack.pop()[1])
            elif s[i] == ',':
                i += 1
                state = 'value'
            else:
                _err("expected ',' or ']'", i)

        elif state == 'obj_start':
            _skip_ws()
            if i >= n:
                _err("unexpected end of input", n)
            if s[i] == '}':
                i += 1
                _deliver(stack.pop()[1])
            elif s[i] == '"':
                stack[-1][2] = _parse_string()
                state = 'obj_colon'
            else:
                _err("expected '\"' or '}'", i)

        elif state == 'obj_key':
            _skip_ws()
            if i >= n:
                _err("unexpected end of input", n)
            if s[i] == '"':
                stack[-1][2] = _parse_string()
                state = 'obj_colon'
            else:
                _err("expected '\"'", i)

        elif state == 'obj_colon':
            _skip_ws()
            if i >= n:
                _err("unexpected end of input", n)
            if s[i] == ':':
                i += 1
                state = 'value'
            else:
                _err("expected ':'", i)

        elif state == 'obj_comma':
            _skip_ws()
            if i >= n:
                _err("unexpected end of input", n)
            if s[i] == '}':
                i += 1
                _deliver(stack.pop()[1])
            elif s[i] == ',':
                i += 1
                state = 'obj_key'
            else:
                _err("expected ',' or '}'", i)

        elif state == 'done':
            _skip_ws()
            if i < n:
                _err("trailing garbage", i)
            return result
