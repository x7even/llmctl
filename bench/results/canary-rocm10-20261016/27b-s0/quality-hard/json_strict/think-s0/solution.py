class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")

    n = len(s)
    i = 0
    ws = ' \t\n\r'

    # Stack entries: (type, state, container, key)
    #   type: 0 = array, 1 = object
    #   state (array):  0 = expect_value_or_end, 1 = expect_sep_or_end
    #   state (object): 0 = expect_key_or_end, 1 = expect_colon,
    #                   2 = expect_value, 3 = expect_sep_or_end
    #   key: current key for object (only meaningful in state 2)
    stack = []
    pending = None
    has_pending = False

    while True:
        # Process a pending value into the current container
        if has_pending:
            if not stack:
                result = pending
                while i < n and s[i] in ws:
                    i += 1
                if i < n:
                    raise JSONError("trailing garbage", i)
                return result
            else:
                t, st, cont, key = stack[-1]
                if t == 0:
                    cont.append(pending)
                    stack[-1] = (0, 1, cont, None)
                else:
                    cont[key] = pending
                    stack[-1] = (1, 3, cont, None)
                has_pending = False

        # Skip whitespace
        while i < n and s[i] in ws:
            i += 1

        if i >= n:
            raise JSONError("unexpected end of input", i)

        c = s[i]

        if not stack:
            # Top level: must start a value
            is_cont, val, i = _start_value(s, i, n, stack)
            if not is_cont:
                pending = val
                has_pending = True
        else:
            t, st, cont, key = stack[-1]
            if t == 0:  # array
                if st == 0:  # expect value or ]
                    if c == ']':
                        i += 1
                        stack.pop()
                        pending = cont
                        has_pending = True
                    else:
                        is_cont, val, i = _start_value(s, i, n, stack)
                        if not is_cont:
                            pending = val
                            has_pending = True
                else:  # st == 1: expect , or ]
                    if c == ',':
                        i += 1
                        stack[-1] = (0, 0, cont, None)
                    elif c == ']':
                        i += 1
                        stack.pop()
                        pending = cont
                        has_pending = True
                    else:
                        raise JSONError(f"expected ',' or ']', got {c!r}", i)
            else:  # object
                if st == 0:  # expect key or }
                    if c == '}':
                        i += 1
                        stack.pop()
                        pending = cont
                        has_pending = True
                    elif c == '"':
                        key, i = _parse_string(s, i, n)
                        stack[-1] = (1, 1, cont, key)
                    else:
                        raise JSONError(f"expected string key, got {c!r}", i)
                elif st == 1:  # expect :
                    if c == ':':
                        i += 1
                        stack[-1] = (1, 2, cont, key)
                    else:
                        raise JSONError(f"expected ':', got {c!r}", i)
                elif st == 2:  # expect value
                    is_cont, val, i = _start_value(s, i, n, stack)
                    if not is_cont:
                        pending = val
                        has_pending = True
                else:  # st == 3: expect , or }
                    if c == ',':
                        i += 1
                        stack[-1] = (1, 0, cont, None)
                    elif c == '}':
                        i += 1
                        stack.pop()
                        pending = cont
                        has_pending = True
                    else:
                        raise JSONError(f"expected ',' or '}}', got {c!r}", i)


def _start_value(s, i, n, stack):
    """Start parsing a value at position i.
    Returns (is_container, value, new_i).
    If is_container is True, a new container frame was pushed onto stack.
    """
    c = s[i]
    if c == '[':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", i)
        stack.append((0, 0, [], None))
        return (True, None, i + 1)
    if c == '{':
        if len(stack) >= 500:
            raise JSONError("maximum nesting depth exceeded", i)
        stack.append((1, 0, {}, None))
        return (True, None, i + 1)
    if c == '"':
        val, new_i = _parse_string(s, i, n)
        return (False, val, new_i)
    if c == 't':
        expected = 'true'
        for j in range(4):
            if i + j >= n:
                raise JSONError("unexpected end of input", n)
            if s[i + j] != expected[j]:
                raise JSONError("invalid literal", i + j)
        return (False, True, i + 4)
    if c == 'f':
        expected = 'false'
        for j in range(5):
            if i + j >= n:
                raise JSONError("unexpected end of input", n)
            if s[i + j] != expected[j]:
                raise JSONError("invalid literal", i + j)
        return (False, False, i + 5)
    if c == 'n':
        expected = 'null'
        for j in range(4):
            if i + j >= n:
                raise JSONError("unexpected end of input", n)
            if s[i + j] != expected[j]:
                raise JSONError("invalid literal", i + j)
        return (False, None, i + 4)
    if c == '-' or '0' <= c <= '9':
        val, new_i = _parse_number(s, i, n)
        return (False, val, new_i)
    raise JSONError(f"unexpected character {c!r}", i)


def _parse_number(s, i, n):
    """Parse a JSON number starting at position i. Returns (value, new_i)."""
    start = i
    if s[i] == '-':
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
    # Integer part
    if s[i] == '0':
        i += 1
        if i < n and '0' <= s[i] <= '9':
            raise JSONError("invalid number (leading zero)", i)
    else:
        if not ('1' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1
    # Fraction part
    has_fraction = False
    if i < n and s[i] == '.':
        i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
        has_fraction = True
        while i < n and '0' <= s[i] <= '9':
            i += 1
    # Exponent part
    has_exponent = False
    if i < n and s[i] in 'eE':
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n:
            raise JSONError("unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("invalid number", i)
        has_exponent = True
        while i < n and '0' <= s[i] <= '9':
            i += 1

    text = s[start:i]
    if has_fraction or has_exponent:
        return float(text), i
    else:
        return int(text), i


def _parse_string(s, i, n):
    """Parse a JSON string starting at position i (s[i] == '"').
    Returns (string_value, new_i)."""
    i += 1  # skip opening quote
    chars = []
    while True:
        if i >= n:
            raise JSONError("unexpected end of input", n)
        c = s[i]
        if c == '"':
            i += 1
            return ''.join(chars), i
        if c == '\\':
            i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            esc = s[i]
            if esc == '"':
                chars.append('"')
                i += 1
            elif esc == '\\':
                chars.append('\\')
                i += 1
            elif esc == '/':
                chars.append('/')
                i += 1
            elif esc == 'b':
                chars.append('\b')
                i += 1
            elif esc == 'f':
                chars.append('\f')
                i += 1
            elif esc == 'n':
                chars.append('\n')
                i += 1
            elif esc == 'r':
                chars.append('\r')
                i += 1
            elif esc == 't':
                chars.append('\t')
                i += 1
            elif esc == 'u':
                i += 1
                if i + 4 > n:
                    raise JSONError("unexpected end of input", n)
                for j in range(4):
                    h = s[i + j]
                    if h not in '0123456789abcdefABCDEF':
                        raise JSONError("invalid unicode escape", i + j)
                code = int(s[i:i + 4], 16)
                i += 4
                if 0xD800 <= code <= 0xDBFF:
                    # High surrogate: check for a following \uXXXX low surrogate
                    if i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u':
                        valid = True
                        for j in range(4):
                            h = s[i + 2 + j]
                            if h not in '0123456789abcdefABCDEF':
                                valid = False
                                break
                        if valid:
                            code2 = int(s[i + 2:i + 6], 16)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(combined))
                                i += 6
                                continue
                    # Lone high surrogate
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError(f"invalid escape character {esc!r}", i)
        else:
            if ord(c) < 0x20:
                raise JSONError("control character in string", i)
            chars.append(c)
            i += 1