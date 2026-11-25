class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    pos = 0

    _WS = ' \t\n\r'
    _DIGITS = frozenset('0123456789')
    _HEX = frozenset('0123456789abcdefABCDEF')
    _HEX_VAL = {
        '0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
        '8': 8, '9': 9,
        'a': 10, 'b': 11, 'c': 12, 'd': 13, 'e': 14, 'f': 15,
        'A': 10, 'B': 11, 'C': 12, 'D': 13, 'E': 14, 'F': 15,
    }

    def _err(msg, p):
        raise JSONError(msg, p)

    def _skip_ws():
        nonlocal pos
        while pos < n and s[pos] in _WS:
            pos += 1

    def _parse_number():
        nonlocal pos
        start = pos
        if s[pos] == '-':
            pos += 1
        if pos >= n:
            _err("expected digit after '-'", pos)
        if s[pos] == '0':
            pos += 1
        elif s[pos] in '123456789':
            pos += 1
            while pos < n and s[pos] in _DIGITS:
                pos += 1
        else:
            _err("expected digit", pos)

        is_float = False
        if pos < n and s[pos] == '.':
            pos += 1
            if pos >= n or s[pos] not in _DIGITS:
                _err("expected digit after '.'", pos)
            while pos < n and s[pos] in _DIGITS:
                pos += 1
            is_float = True

        if pos < n and s[pos] in 'eE':
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n or s[pos] not in _DIGITS:
                _err("expected digit in exponent", pos)
            while pos < n and s[pos] in _DIGITS:
                pos += 1
            is_float = True

        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def _parse_string():
        nonlocal pos
        pos += 1  # skip opening "
        chars = []
        while True:
            if pos >= n:
                _err("unterminated string", pos)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    _err("unterminated escape sequence", pos)
                e = s[pos]
                if e == '"':
                    chars.append('"'); pos += 1
                elif e == '\\':
                    chars.append('\\'); pos += 1
                elif e == '/':
                    chars.append('/'); pos += 1
                elif e == 'b':
                    chars.append('\b'); pos += 1
                elif e == 'f':
                    chars.append('\f'); pos += 1
                elif e == 'n':
                    chars.append('\n'); pos += 1
                elif e == 'r':
                    chars.append('\r'); pos += 1
                elif e == 't':
                    chars.append('\t'); pos += 1
                elif e == 'u':
                    pos += 1
                    if pos + 4 > n:
                        _err("truncated \\u escape", n)
                    for i in range(4):
                        if s[pos + i] not in _HEX:
                            _err("invalid hex digit in \\u escape", pos + i)
                    cp = (_HEX_VAL[s[pos]] << 12) | (_HEX_VAL[s[pos + 1]] << 8) | \
                         (_HEX_VAL[s[pos + 2]] << 4) | _HEX_VAL[s[pos + 3]]
                    pos += 4
                    if 0xD800 <= cp <= 0xDBFF:
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            valid_hex = True
                            for i in range(4):
                                if s[pos + 2 + i] not in _HEX:
                                    valid_hex = False
                                    break
                            if valid_hex:
                                cp2 = (_HEX_VAL[s[pos + 2]] << 12) | (_HEX_VAL[s[pos + 3]] << 8) | \
                                      (_HEX_VAL[s[pos + 4]] << 4) | _HEX_VAL[s[pos + 5]]
                                if 0xDC00 <= cp2 <= 0xDFFF:
                                    combined = 0x10000 + ((cp - 0xD800) << 10) + (cp2 - 0xDC00)
                                    chars.append(chr(combined))
                                    pos += 6
                                    continue
                    chars.append(chr(cp))
                else:
                    _err("invalid escape character", pos)
            elif ord(c) < 0x20:
                _err("control character in string", pos)
            else:
                chars.append(c)
                pos += 1

    def _parse_literal(expected):
        nonlocal pos
        for i in range(len(expected)):
            if pos + i >= n or s[pos + i] != expected[i]:
                _err("invalid literal", pos + i)
        pos += len(expected)

    def _parse_scalar():
        nonlocal pos
        c = s[pos]
        if c == '"':
            return _parse_string()
        elif c == '-' or c in _DIGITS:
            return _parse_number()
        elif c == 't':
            _parse_literal('true')
            return True
        elif c == 'f':
            _parse_literal('false')
            return False
        elif c == 'n':
            _parse_literal('null')
            return None
        else:
            _err(f"unexpected character {c!r}", pos)

    # Main iterative parser
    # Stack frames: [type, container, state]
    #   type: 'a' (array) or 'o' (object)
    #   Array states:  0=expect_value_or_close, 1=expect_sep, 2=expect_value_after_comma
    #   Object states: 0=expect_key_or_close,   1=expect_colon, 2=expect_value, 3=expect_sep, 4=expect_key_after_comma
    stack = []
    pending_key = None

    while True:
        _skip_ws()

        if pos >= n:
            _err("unexpected end of input", pos)

        c = s[pos]

        if not stack:
            # Top-level: must be a value
            if c == '[':
                if len(stack) >= 500:
                    _err("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['a', [], 0])
            elif c == '{':
                if len(stack) >= 500:
                    _err("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(['o', {}, 0])
            elif c == '"' or c == '-' or c in _DIGITS or c in 'tfn':
                value = _parse_scalar()
                _skip_ws()
                if pos < n:
                    _err("trailing garbage", pos)
                return value
            else:
                _err(f"unexpected character {c!r}", pos)
        else:
            frame = stack[-1]
            if frame[0] == 'a':
                state = frame[2]
                if state == 0:
                    if c == ']':
                        pos += 1
                        value = frame[1]
                        stack.pop()
                        # Commit to parent
                        if not stack:
                            _skip_ws()
                            if pos < n:
                                _err("trailing garbage", pos)
                            return value
                        else:
                            pf = stack[-1]
                            if pf[0] == 'a':
                                pf[1].append(value)
                                pf[2] = 1
                            else:
                                pf[1][pending_key] = value
                                pending_key = None
                                pf[2] = 3
                    elif c in '{[' or c == '"' or c == '-' or c in _DIGITS or c in 'tfn':
                        if c in '{[':
                            if len(stack) >= 500:
                                _err("maximum nesting depth exceeded", pos)
                            if c == '[':
                                pos += 1
                                stack.append(['a', [], 0])
                            else:
                                pos += 1
                                stack.append(['o', {}, 0])
                        else:
                            value = _parse_scalar()
                            frame[1].append(value)
                            frame[2] = 1
                    else:
                        _err(f"expected value or ']', got {c!r}", pos)
                elif state == 1:
                    if c == ',':
                        pos += 1
                        frame[2] = 2
                    elif c == ']':
                        pos += 1
                        value = frame[1]
                        stack.pop()
                        if not stack:
                            _skip_ws()
                            if pos < n:
                                _err("trailing garbage", pos)
                            return value
                        else:
                            pf = stack[-1]
                            if pf[0] == 'a':
                                pf[1].append(value)
                                pf[2] = 1
                            else:
                                pf[1][pending_key] = value
                                pending_key = None
                                pf[2] = 3
                    else:
                        _err(f"expected ',' or ']', got {c!r}", pos)
                elif state == 2:
                    if c in '{[' or c == '"' or c == '-' or c in _DIGITS or c in 'tfn':
                        if c in '{[':
                            if len(stack) >= 500:
                                _err("maximum nesting depth exceeded", pos)
                            if c == '[':
                                pos += 1
                                stack.append(['a', [], 0])
                            else:
                                pos += 1
                                stack.append(['o', {}, 0])
                        else:
                            value = _parse_scalar()
                            frame[1].append(value)
                            frame[2] = 1
                    else:
                        _err(f"expected value, got {c!r}", pos)
            else:
                # Object
                state = frame[2]
                if state == 0:
                    if c == '}':
                        pos += 1
                        value = frame[1]
                        stack.pop()
                        if not stack:
                            _skip_ws()
                            if pos < n:
                                _err("trailing garbage", pos)
                            return value
                        else:
                            pf = stack[-1]
                            if pf[0] == 'a':
                                pf[1].append(value)
                                pf[2] = 1
                            else:
                                pf[1][pending_key] = value
                                pending_key = None
                                pf[2] = 3
                    elif c == '"':
                        pending_key = _parse_string()
                        frame[2] = 1
                    else:
                        _err(f"expected string key or '}}', got {c!r}", pos)
                elif state == 1:
                    if c == ':':
                        pos += 1
                        frame[2] = 2
                    else:
                        _err(f"expected ':', got {c!r}", pos)
                elif state == 2:
                    if c in '{[' or c == '"' or c == '-' or c in _DIGITS or c in 'tfn':
                        if c in '{[':
                            if len(stack) >= 500:
                                _err("maximum nesting depth exceeded", pos)
                            if c == '[':
                                pos += 1
                                stack.append(['a', [], 0])
                            else:
                                pos += 1
                                stack.append(['o', {}, 0])
                        else:
                            value = _parse_scalar()
                            frame[1][pending_key] = value
                            pending_key = None
                            frame[2] = 3
                    else:
                        _err(f"expected value, got {c!r}", pos)
                elif state == 3:
                    if c == ',':
                        pos += 1
                        frame[2] = 4
                    elif c == '}':
                        pos += 1
                        value = frame[1]
                        stack.pop()
                        if not stack:
                            _skip_ws()
                            if pos < n:
                                _err("trailing garbage", pos)
                            return value
                        else:
                            pf = stack[-1]
                            if pf[0] == 'a':
                                pf[1].append(value)
                                pf[2] = 1
                            else:
                                pf[1][pending_key] = value
                                pending_key = None
                                pf[2] = 3
                    else:
                        _err(f"expected ',' or '}}', got {c!r}", pos)
                elif state == 4:
                    if c == '"':
                        pending_key = _parse_string()
                        frame[2] = 1
                    else:
                        _err(f"expected string key, got {c!r}", pos)
