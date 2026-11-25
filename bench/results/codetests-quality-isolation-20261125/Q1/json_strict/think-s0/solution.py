"""Strict RFC 8259 JSON parser (hand-written, no json/ast/eval)."""


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

    # Stack entries: [type, container, state, pending_key]
    #   type: 'array' | 'object'
    #   state for array: 'arr_need_value' | 'arr_need_comma_or_end'
    #   state for object: 'obj_need_key' | 'obj_need_colon' | 'obj_need_value' | 'obj_need_comma_or_end'
    stack: list = []

    pending_value = None
    has_pending = False

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1

    def parse_string() -> str:
        nonlocal pos
        pos += 1  # skip opening quote
        parts: list = []
        start = pos

        while True:
            if pos >= n:
                raise JSONError("unexpected end of input in string", pos)

            c = s[pos]

            if c == '"':
                if start < pos:
                    parts.append(s[start:pos])
                pos += 1
                return ''.join(parts)

            if c == '\\':
                if start < pos:
                    parts.append(s[start:pos])
                pos += 1  # now at escape char
                if pos >= n:
                    raise JSONError("unexpected end of input in escape", pos)
                ec = s[pos]
                if ec == '"':
                    parts.append('"')
                    pos += 1
                elif ec == '\\':
                    parts.append('\\')
                    pos += 1
                elif ec == '/':
                    parts.append('/')
                    pos += 1
                elif ec == 'b':
                    parts.append('\b')
                    pos += 1
                elif ec == 'f':
                    parts.append('\f')
                    pos += 1
                elif ec == 'n':
                    parts.append('\n')
                    pos += 1
                elif ec == 'r':
                    parts.append('\r')
                    pos += 1
                elif ec == 't':
                    parts.append('\t')
                    pos += 1
                elif ec == 'u':
                    pos += 1
                    if pos + 4 > n:
                        raise JSONError("truncated \\u escape", pos)
                    hex_str = s[pos:pos + 4]
                    for i in range(4):
                        hc = hex_str[i]
                        if not ((hc >= '0' and hc <= '9') or
                                (hc >= 'a' and hc <= 'f') or
                                (hc >= 'A' and hc <= 'F')):
                            raise JSONError("invalid hex digit in \\u escape", pos + i)
                    code = int(hex_str, 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        # High surrogate: check for low surrogate pair
                        if pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u':
                            hex2 = s[pos + 2:pos + 6]
                            valid = True
                            for i in range(4):
                                hc = hex2[i]
                                if not ((hc >= '0' and hc <= '9') or
                                        (hc >= 'a' and hc <= 'f') or
                                        (hc >= 'A' and hc <= 'F')):
                                    valid = False
                                    break
                            if valid:
                                code2 = int(hex2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    parts.append(chr(combined))
                                    pos += 6
                                    start = pos
                                    continue
                        # Unpaired high surrogate
                        parts.append(chr(code))
                    elif 0xDC00 <= code <= 0xDFFF:
                        parts.append(chr(code))
                    else:
                        parts.append(chr(code))
                else:
                    raise JSONError(f"invalid escape character '\\{ec}'", pos)
                start = pos
            elif ord(c) < 0x20:
                raise JSONError("unescaped control character in string", pos)
            else:
                pos += 1

    def parse_number():
        nonlocal pos
        start = pos

        if s[pos] == '-':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input in number", pos)

        if s[pos] == '0':
            pos += 1
            if pos < n and '0' <= s[pos] <= '9':
                raise JSONError("leading zero in number", pos)
        elif '1' <= s[pos] <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            raise JSONError("expected digit in number", pos)

        has_fraction = False
        if pos < n and s[pos] == '.':
            has_fraction = True
            pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit after decimal point", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        has_exponent = False
        if pos < n and s[pos] in 'eE':
            has_exponent = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n or not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        num_str = s[start:pos]
        if not has_fraction and not has_exponent:
            return int(num_str)
        else:
            return float(num_str)

    def parse_value():
        """Parse a value at current pos. Returns (value, is_container_start)."""
        nonlocal pos
        c = s[pos]

        if c == '[':
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            stack.append(['array', [], 'arr_need_value', None])
            return (None, True)

        if c == '{':
            if len(stack) >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            stack.append(['object', {}, 'obj_need_key', None])
            return (None, True)

        if c == '"':
            return (parse_string(), False)

        if c == 't':
            if pos + 4 <= n and s[pos] == 't' and s[pos + 1] == 'r' and s[pos + 2] == 'u' and s[pos + 3] == 'e':
                pos += 4
                return (True, False)
            for i, ch in enumerate('true'):
                if pos + i >= n or s[pos + i] != ch:
                    raise JSONError("invalid literal", pos + i)
            # unreachable

        if c == 'f':
            if pos + 5 <= n and s[pos] == 'f' and s[pos + 1] == 'a' and s[pos + 2] == 'l' and s[pos + 3] == 's' and s[pos + 4] == 'e':
                pos += 5
                return (False, False)
            for i, ch in enumerate('false'):
                if pos + i >= n or s[pos + i] != ch:
                    raise JSONError("invalid literal", pos + i)
            # unreachable

        if c == 'n':
            if pos + 4 <= n and s[pos] == 'n' and s[pos + 1] == 'u' and s[pos + 2] == 'l' and s[pos + 3] == 'l':
                pos += 4
                return (None, False)
            for i, ch in enumerate('null'):
                if pos + i >= n or s[pos + i] != ch:
                    raise JSONError("invalid literal", pos + i)
            # unreachable

        if c == '-' or ('0' <= c <= '9'):
            return (parse_number(), False)

        raise JSONError(f"unexpected character {c!r}", pos)

    # Main loop
    while True:
        if has_pending:
            if not stack:
                result = pending_value
                has_pending = False
                skip_ws()
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return result
            else:
                entry = stack[-1]
                if entry[0] == 'array':
                    entry[1].append(pending_value)
                    entry[2] = 'arr_need_comma_or_end'
                else:
                    entry[1][entry[3]] = pending_value
                    entry[2] = 'obj_need_comma_or_end'
                has_pending = False
                continue

        if not stack:
            # Top level: expect a value
            skip_ws()
            if pos >= n:
                raise JSONError("unexpected end of input", pos)
            v, is_container = parse_value()
            if is_container:
                continue
            else:
                skip_ws()
                if pos < n:
                    raise JSONError("trailing garbage", pos)
                return v
        else:
            entry = stack[-1]
            ctype = entry[0]
            state = entry[2]

            if ctype == 'array':
                if state == 'arr_need_value':
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == ']':
                        pos += 1
                        stack.pop()
                        pending_value = entry[1]
                        has_pending = True
                    else:
                        v, is_container = parse_value()
                        if is_container:
                            continue
                        else:
                            entry[1].append(v)
                            entry[2] = 'arr_need_comma_or_end'
                else:  # arr_need_comma_or_end
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    c = s[pos]
                    if c == ',':
                        pos += 1
                        entry[2] = 'arr_need_value'
                    elif c == ']':
                        pos += 1
                        stack.pop()
                        pending_value = entry[1]
                        has_pending = True
                    else:
                        raise JSONError(f"expected ',' or ']', got {c!r}", pos)

            else:  # object
                if state == 'obj_need_key':
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    c = s[pos]
                    if c == '}':
                        pos += 1
                        stack.pop()
                        pending_value = entry[1]
                        has_pending = True
                    elif c == '"':
                        key = parse_string()
                        entry[3] = key
                        entry[2] = 'obj_need_colon'
                    else:
                        raise JSONError(f"expected string key or '}}', got {c!r}", pos)
                elif state == 'obj_need_colon':
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == ':':
                        pos += 1
                        entry[2] = 'obj_need_value'
                    else:
                        raise JSONError(f"expected ':', got {s[pos]!r}", pos)
                elif state == 'obj_need_value':
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    v, is_container = parse_value()
                    if is_container:
                        continue
                    else:
                        entry[1][entry[3]] = v
                        entry[2] = 'obj_need_comma_or_end'
                else:  # obj_need_comma_or_end
                    skip_ws()
                    if pos >= n:
                        raise JSONError("unexpected end of input", pos)
                    c = s[pos]
                    if c == ',':
                        pos += 1
                        entry[2] = 'obj_need_key'
                    elif c == '}':
                        pos += 1
                        stack.pop()
                        pending_value = entry[1]
                        has_pending = True
                    else:
                        raise JSONError(f"expected ',' or '}}', got {c!r}", pos)
