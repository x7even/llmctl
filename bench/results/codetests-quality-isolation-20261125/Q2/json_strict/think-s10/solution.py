"""Strict RFC 8259 JSON parser (hand-written, no json/ast/eval)."""


class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


_WS = frozenset(' \t\n\r')
_HEX = frozenset('0123456789abcdefABCDEF')
_HEX_VAL = {}
for _i, _c in enumerate('0123456789abcdef'):
    _HEX_VAL[_c] = _i
for _i, _c in enumerate('0123456789ABCDEF'):
    _HEX_VAL[_c] = _i

_MAX_DEPTH = 500


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}"
        )

    n = len(s)
    pos = 0

    def fail(msg, p):
        raise JSONError(msg, p)

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in _WS:
            pos += 1

    def parse_string():
        nonlocal pos
        pos += 1  # skip opening quote
        chars = []
        while True:
            if pos >= n:
                fail("unexpected end of input in string", n)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    fail("unexpected end of input in string escape", n)
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
                    pos += 1
                elif ec == 'n':
                    chars.append('\n')
                    pos += 1
                elif ec == 'r':
                    chars.append('\r')
                    pos += 1
                elif ec == 't':
                    chars.append('\t')
                    pos += 1
                elif ec == 'u':
                    pos += 1
                    if pos + 4 > n:
                        fail("unexpected end of input in \\u escape", n)
                    h1 = s[pos]
                    h2 = s[pos + 1]
                    h3 = s[pos + 2]
                    h4 = s[pos + 3]
                    if h1 not in _HEX:
                        fail("invalid hex digit in \\u escape", pos)
                    if h2 not in _HEX:
                        fail("invalid hex digit in \\u escape", pos + 1)
                    if h3 not in _HEX:
                        fail("invalid hex digit in \\u escape", pos + 2)
                    if h4 not in _HEX:
                        fail("invalid hex digit in \\u escape", pos + 3)
                    code = (_HEX_VAL[h1] << 12) | (_HEX_VAL[h2] << 8) | \
                           (_HEX_VAL[h3] << 4) | _HEX_VAL[h4]
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        # High surrogate: check for a following low surrogate
                        if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                                and s[pos + 2] in _HEX and s[pos + 3] in _HEX
                                and s[pos + 4] in _HEX and s[pos + 5] in _HEX):
                            code2 = (_HEX_VAL[s[pos + 2]] << 12) | \
                                    (_HEX_VAL[s[pos + 3]] << 8) | \
                                    (_HEX_VAL[s[pos + 4]] << 4) | \
                                    _HEX_VAL[s[pos + 5]]
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(combined))
                                pos += 6
                                continue
                        chars.append(chr(code))
                    elif 0xDC00 <= code <= 0xDFFF:
                        chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    fail(f"invalid escape character {ec!r}", pos)
            elif ord(c) < 0x20:
                fail("unescaped control character in string", pos)
            else:
                chars.append(c)
                pos += 1

    def parse_number():
        nonlocal pos
        start = pos
        if s[pos] == '-':
            pos += 1
            if pos >= n:
                fail("unexpected end of input in number", n)
        if s[pos] == '0':
            pos += 1
        elif '1' <= s[pos] <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            fail("invalid digit in number", pos)

        is_float = False
        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                fail("unexpected end of input in number", n)
            if not ('0' <= s[pos] <= '9'):
                fail("expected digit after decimal point", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                fail("unexpected end of input in number", n)
            if not ('0' <= s[pos] <= '9'):
                fail("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def parse_literal(expected, value):
        nonlocal pos
        ln = len(expected)
        for i in range(ln):
            if pos + i >= n or s[pos + i] != expected[i]:
                p = pos + i if pos + i < n else n
                fail(f"invalid literal, expected {expected!r}", p)
        pos += ln
        return value

    def parse_scalar():
        nonlocal pos
        c = s[pos]
        if c == '"':
            return parse_string()
        if c == 't':
            return parse_literal('true', True)
        if c == 'f':
            return parse_literal('false', False)
        if c == 'n':
            return parse_literal('null', None)
        if c == '-' or '0' <= c <= '9':
            return parse_number()
        fail(f"unexpected character {c!r}", pos)

    # ---- iterative main loop ----
    # Stack entries: (container, state, key)
    #   Array states:  0 = expect first value or ']'
    #                 1 = expect ',' or ']'
    #                 2 = expect value (after ',')
    #   Object states: 0 = expect first key or '}'
    #                 1 = expect ':'
    #                 2 = expect value
    #                 3 = expect ',' or '}'
    stack = []
    _SENTINEL = object()
    pending = _SENTINEL  # value to assign to parent (or top-level)

    while True:
        # Assign a completed value to its parent
        if pending is not _SENTINEL:
            if not stack:
                result = pending
                pending = _SENTINEL
                skip_ws()
                if pos < n:
                    fail("trailing garbage", pos)
                return result
            else:
                container, state, key = stack[-1]
                if isinstance(container, list):
                    container.append(pending)
                    stack[-1] = (container, 1, None)
                else:
                    container[key] = pending
                    stack[-1] = (container, 3, key)
                pending = _SENTINEL

        skip_ws()

        if pos >= n:
            fail("unexpected end of input", n)

        c = s[pos]

        if not stack:
            # Top level: expect a value
            if c == '{':
                if len(stack) >= _MAX_DEPTH:
                    fail("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(({}, 0, None))
            elif c == '[':
                if len(stack) >= _MAX_DEPTH:
                    fail("maximum nesting depth exceeded", pos)
                pos += 1
                stack.append(([], 0, None))
            else:
                pending = parse_scalar()
        else:
            container, state, key = stack[-1]
            if isinstance(container, list):
                # ---- array ----
                if state == 0:
                    if c == ']':
                        pos += 1
                        stack.pop()
                        pending = container
                    elif c == '{':
                        if len(stack) >= _MAX_DEPTH:
                            fail("maximum nesting depth exceeded", pos)
                        pos += 1
                        stack.append(({}, 0, None))
                    elif c == '[':
                        if len(stack) >= _MAX_DEPTH:
                            fail("maximum nesting depth exceeded", pos)
                        pos += 1
                        stack.append(([], 0, None))
                    else:
                        pending = parse_scalar()
                elif state == 1:
                    if c == ',':
                        pos += 1
                        stack[-1] = (container, 2, None)
                    elif c == ']':
                        pos += 1
                        stack.pop()
                        pending = container
                    else:
                        fail(f"expected ',' or ']', got {c!r}", pos)
                else:  # state == 2
                    if c == '{':
                        if len(stack) >= _MAX_DEPTH:
                            fail("maximum nesting depth exceeded", pos)
                        pos += 1
                        stack.append(({}, 0, None))
                    elif c == '[':
                        if len(stack) >= _MAX_DEPTH:
                            fail("maximum nesting depth exceeded", pos)
                        pos += 1
                        stack.append(([], 0, None))
                    else:
                        pending = parse_scalar()
            else:
                # ---- object ----
                if state == 0:
                    if c == '}':
                        pos += 1
                        stack.pop()
                        pending = container
                    elif c == '"':
                        key = parse_string()
                        stack[-1] = (container, 1, key)
                    else:
                        fail(f"expected '\"' or '}}', got {c!r}", pos)
                elif state == 1:
                    if c == ':':
                        pos += 1
                        stack[-1] = (container, 2, key)
                    else:
                        fail(f"expected ':', got {c!r}", pos)
                elif state == 2:
                    if c == '{':
                        if len(stack) >= _MAX_DEPTH:
                            fail("maximum nesting depth exceeded", pos)
                        pos += 1
                        stack.append(({}, 0, None))
                    elif c == '[':
                        if len(stack) >= _MAX_DEPTH:
                            fail("maximum nesting depth exceeded", pos)
                        pos += 1
                        stack.append(([], 0, None))
                    else:
                        pending = parse_scalar()
                else:  # state == 3
                    if c == ',':
                        pos += 1
                        stack[-1] = (container, 0, None)
                    elif c == '}':
                        pos += 1
                        stack.pop()
                        pending = container
                    else:
                        fail(f"expected ',' or '}}', got {c!r}", pos)

    # Unreachable
    fail("unexpected end of input", n)
