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

    # Skip leading whitespace
    while i < n and s[i] in ' \t\n\r':
        i += 1
    if i >= n:
        raise JSONError("Empty input", n)

    # Iterative parser with explicit stack to avoid RecursionError.
    # Stack entries: (is_object: bool, container, pending_key)
    stack = []
    depth = 0
    state = 'value'
    result = None

    while True:
        if state == 'value':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("Unexpected end of input", n)

            c = s[i]

            if c == '{':
                if depth >= 500:
                    raise JSONError("Maximum nesting depth exceeded", i)
                depth += 1
                i += 1
                stack.append((True, {}, None))
                # Expect key or }
                while i < n and s[i] in ' \t\n\r':
                    i += 1
                if i >= n:
                    raise JSONError("Unexpected end of input", n)
                if s[i] == '}':
                    i += 1
                    depth -= 1
                    result = stack.pop()[1]
                    state = 'return'
                    continue
                if s[i] != '"':
                    raise JSONError("Expected key", i)
                key, i = _parse_string(s, i, n)
                stack[-1] = (True, stack[-1][1], key)
                state = 'obj_colon'
                continue

            elif c == '[':
                if depth >= 500:
                    raise JSONError("Maximum nesting depth exceeded", i)
                depth += 1
                i += 1
                stack.append((False, [], None))
                # Expect value or ]
                while i < n and s[i] in ' \t\n\r':
                    i += 1
                if i >= n:
                    raise JSONError("Unexpected end of input", n)
                if s[i] == ']':
                    i += 1
                    depth -= 1
                    result = stack.pop()[1]
                    state = 'return'
                    continue
                state = 'value'
                continue

            elif c == '"':
                result, i = _parse_string(s, i, n)
                state = 'return'
                continue

            elif c == 't':
                j = i + 1
                while j < n and j - i < 4 and s[j] == 'true'[j - i]:
                    j += 1
                if j - i == 4:
                    result = True
                    i = j
                    state = 'return'
                elif j == n:
                    raise JSONError("Unexpected end of input", n)
                else:
                    raise JSONError("Invalid literal", j)
                continue

            elif c == 'f':
                j = i + 1
                while j < n and j - i < 5 and s[j] == 'false'[j - i]:
                    j += 1
                if j - i == 5:
                    result = False
                    i = j
                    state = 'return'
                elif j == n:
                    raise JSONError("Unexpected end of input", n)
                else:
                    raise JSONError("Invalid literal", j)
                continue

            elif c == 'n':
                j = i + 1
                while j < n and j - i < 4 and s[j] == 'null'[j - i]:
                    j += 1
                if j - i == 4:
                    result = None
                    i = j
                    state = 'return'
                elif j == n:
                    raise JSONError("Unexpected end of input", n)
                else:
                    raise JSONError("Invalid literal", j)
                continue

            elif c == '-' or ('0' <= c <= '9'):
                result, i = _parse_number(s, i, n)
                state = 'return'
                continue

            else:
                raise JSONError("Unexpected character", i)

        elif state == 'return':
            if not stack:
                state = 'done'
                continue
            is_obj, container, key = stack[-1]
            if is_obj:
                container[key] = result
                state = 'obj_comma_or_end'
            else:
                container.append(result)
                state = 'array_comma_or_end'
            continue

        elif state == 'array_comma_or_end':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] == ']':
                i += 1
                depth -= 1
                result = stack.pop()[1]
                state = 'return'
            elif s[i] == ',':
                i += 1
                state = 'value'
            else:
                raise JSONError("Expected , or ]", i)
            continue

        elif state == 'obj_colon':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] == ':':
                i += 1
                state = 'value'
            else:
                raise JSONError("Expected :", i)
            continue

        elif state == 'obj_comma_or_end':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            if s[i] == '}':
                i += 1
                depth -= 1
                result = stack.pop()[1]
                state = 'return'
            elif s[i] == ',':
                i += 1
                while i < n and s[i] in ' \t\n\r':
                    i += 1
                if i >= n:
                    raise JSONError("Unexpected end of input", n)
                if s[i] != '"':
                    raise JSONError("Expected key", i)
                key, i = _parse_string(s, i, n)
                stack[-1] = (True, stack[-1][1], key)
                state = 'obj_colon'
            else:
                raise JSONError("Expected , or }", i)
            continue

        elif state == 'done':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i < n:
                raise JSONError("Trailing garbage", i)
            return result


def _parse_string(s, i, n):
    """Parse a JSON string starting at s[i] which must be the opening double-quote.
    Returns (decoded_string, new_position_after_closing_quote)."""
    i += 1  # skip opening "
    parts = []

    while True:
        if i >= n:
            raise JSONError("Unterminated string", n)

        c = s[i]

        if c == '"':
            i += 1
            return ''.join(parts), i

        if c == '\\':
            i += 1
            if i >= n:
                raise JSONError("Unterminated string", n)
            c = s[i]
            if c == '"':
                parts.append('"')
                i += 1
            elif c == '\\':
                parts.append('\\')
                i += 1
            elif c == '/':
                parts.append('/')
                i += 1
            elif c == 'b':
                parts.append('\b')
                i += 1
            elif c == 'f':
                parts.append('\f')
                i += 1
            elif c == 'n':
                parts.append('\n')
                i += 1
            elif c == 'r':
                parts.append('\r')
                i += 1
            elif c == 't':
                parts.append('\t')
                i += 1
            elif c == 'u':
                i += 1
                cp, i = _parse_hex4(s, i, n)
                if 0xD800 <= cp <= 0xDBFF:
                    # High surrogate: try to combine with a following \uXXXX low surrogate
                    if i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u':
                        try:
                            lo, _ = _parse_hex4(s, i + 2, n)
                            if 0xDC00 <= lo <= 0xDFFF:
                                combined = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                                parts.append(chr(combined))
                                i += 6
                                continue
                        except JSONError:
                            pass
                    parts.append(chr(cp))
                elif 0xDC00 <= cp <= 0xDFFF:
                    parts.append(chr(cp))
                else:
                    parts.append(chr(cp))
            else:
                raise JSONError("Invalid escape character", i)

        elif c < ' ':
            # Raw control character (U+0000 .. U+001F)
            raise JSONError("Control character in string", i)

        else:
            # Fast path: collect a run of normal characters
            start = i
            i += 1
            while i < n:
                c = s[i]
                if c == '"' or c == '\\' or c < ' ':
                    break
                i += 1
            parts.append(s[start:i])


def _parse_hex4(s, i, n):
    """Parse exactly 4 ASCII hex digits at position i. Returns (value, i+4)."""
    if i + 4 > n:
        raise JSONError("Incomplete unicode escape", n)
    val = 0
    for j in range(4):
        o = ord(s[i + j])
        if 48 <= o <= 57:       # 0-9
            val = (val << 4) + (o - 48)
        elif 97 <= o <= 102:    # a-f
            val = (val << 4) + (o - 87)
        elif 65 <= o <= 70:     # A-F
            val = (val << 4) + (o - 55)
        else:
            raise JSONError("Invalid hex digit", i + j)
    return val, i + 4


def _parse_number(s, i, n):
    """Parse a JSON number starting at position i. Returns (value, new_position)."""
    start = i

    # Optional minus sign
    if s[i] == '-':
        i += 1

    if i >= n:
        raise JSONError("Unexpected end of input", n)

    c = s[i]
    if c == '0':
        i += 1
    elif '1' <= c <= '9':
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1
    else:
        raise JSONError("Expected digit", i)

    is_float = False

    # Optional fraction
    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n:
            raise JSONError("Unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("Expected digit after decimal point", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    # Optional exponent
    if i < n and s[i] in 'eE':
        is_float = True
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n:
            raise JSONError("Unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("Expected digit in exponent", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1

    num_str = s[start:i]
    if is_float:
        return float(num_str), i
    else:
        return int(num_str), i
