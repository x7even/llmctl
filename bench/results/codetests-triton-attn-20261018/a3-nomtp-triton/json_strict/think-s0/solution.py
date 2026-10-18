class JSONError(ValueError):
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(message)


def _hex_digit(s, pos, n):
    """Return the numeric value of the hex digit at s[pos], or raise JSONError."""
    if pos >= n:
        raise JSONError("Incomplete \\u escape", pos)
    c = s[pos]
    if '0' <= c <= '9':
        return ord(c) - 48
    if 'a' <= c <= 'f':
        return ord(c) - 87
    if 'A' <= c <= 'F':
        return ord(c) - 55
    raise JSONError("Invalid hex digit in \\u escape", pos)


def _parse_string(s, pos, n):
    """Parse a JSON string starting at s[pos] (which must be '"')."""
    pos += 1  # skip opening quote
    chars = []
    while True:
        if pos >= n:
            raise JSONError("Unterminated string", pos)
        c = s[pos]
        if c == '"':
            pos += 1
            return ''.join(chars), pos
        elif c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("Unterminated escape sequence", pos)
            esc = s[pos]
            if esc == '"':
                chars.append('"')
                pos += 1
            elif esc == '\\':
                chars.append('\\')
                pos += 1
            elif esc == '/':
                chars.append('/')
                pos += 1
            elif esc == 'b':
                chars.append('\b')
                pos += 1
            elif esc == 'f':
                chars.append('\f')
                pos += 1
            elif esc == 'n':
                chars.append('\n')
                pos += 1
            elif esc == 'r':
                chars.append('\r')
                pos += 1
            elif esc == 't':
                chars.append('\t')
                pos += 1
            elif esc == 'u':
                h1 = _hex_digit(s, pos + 1, n)
                h2 = _hex_digit(s, pos + 2, n)
                h3 = _hex_digit(s, pos + 3, n)
                h4 = _hex_digit(s, pos + 4, n)
                code = (h1 << 12) | (h2 << 8) | (h3 << 4) | h4
                pos += 5
                if 0xD800 <= code <= 0xDBFF:
                    # High surrogate: check for low surrogate pair
                    if (pos + 1 < n and s[pos] == '\\' and s[pos + 1] == 'u'):
                        h5 = _hex_digit(s, pos + 2, n)
                        h6 = _hex_digit(s, pos + 3, n)
                        h7 = _hex_digit(s, pos + 4, n)
                        h8 = _hex_digit(s, pos + 5, n)
                        code2 = (h5 << 12) | (h6 << 8) | (h7 << 4) | h8
                        if 0xDC00 <= code2 <= 0xDFFF:
                            combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                            chars.append(chr(combined))
                            pos += 6
                            continue
                    chars.append(chr(code))
                else:
                    chars.append(chr(code))
            else:
                raise JSONError("Invalid escape character", pos)
        elif c < ' ':
            raise JSONError("Unescaped control character in string", pos)
        else:
            chars.append(c)
            pos += 1


def _parse_number(s, pos, n):
    """Parse a JSON number starting at s[pos]."""
    start = pos
    if pos < n and s[pos] == '-':
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

    has_frac = False
    if pos < n and s[pos] == '.':
        has_frac = True
        pos += 1
        if pos >= n or not ('0' <= s[pos] <= '9'):
            raise JSONError("Expected digit after decimal point", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    has_exp = False
    if pos < n and s[pos] in 'eE':
        has_exp = True
        pos += 1
        if pos < n and s[pos] in '+-':
            pos += 1
        if pos >= n or not ('0' <= s[pos] <= '9'):
            raise JSONError("Expected digit in exponent", pos)
        while pos < n and '0' <= s[pos] <= '9':
            pos += 1

    text = s[start:pos]
    if has_frac or has_exp:
        return float(text), pos
    else:
        return int(text), pos


def _parse_value(s, pos, n, depth):
    """Parse a JSON value starting at s[pos]. Returns (value, new_pos)."""
    # Skip whitespace
    while pos < n and s[pos] in ' \t\n\r':
        pos += 1
    if pos >= n:
        raise JSONError("Unexpected end of input", pos)
    c = s[pos]

    if c == '[':
        new_depth = depth + 1
        if new_depth > 500:
            raise JSONError("Maximum nesting depth exceeded", pos)
        pos += 1
        arr = []
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1
        if pos >= n:
            raise JSONError("Unexpected end of input", pos)
        if s[pos] == ']':
            return arr, pos + 1
        while True:
            value, pos = _parse_value(s, pos, n, new_depth)
            arr.append(value)
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == ']':
                return arr, pos + 1
            elif s[pos] == ',':
                pos += 1
                while pos < n and s[pos] in ' \t\n\r':
                    pos += 1
                if pos >= n:
                    raise JSONError("Unexpected end of input", pos)
                if s[pos] == ']':
                    raise JSONError("Trailing comma in array", pos)
            else:
                raise JSONError("Expected ',' or ']', got unexpected character", pos)

    elif c == '{':
        new_depth = depth + 1
        if new_depth > 500:
            raise JSONError("Maximum nesting depth exceeded", pos)
        pos += 1
        obj = {}
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1
        if pos >= n:
            raise JSONError("Unexpected end of input", pos)
        if s[pos] == '}':
            return obj, pos + 1
        while True:
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] != '"':
                raise JSONError("Expected string key", pos)
            key, pos = _parse_string(s, pos, n)
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] != ':':
                raise JSONError("Expected ':' after key", pos)
            pos += 1
            value, pos = _parse_value(s, pos, n, new_depth)
            obj[key] = value
            while pos < n and s[pos] in ' \t\n\r':
                pos += 1
            if pos >= n:
                raise JSONError("Unexpected end of input", pos)
            if s[pos] == '}':
                return obj, pos + 1
            elif s[pos] == ',':
                pos += 1
                while pos < n and s[pos] in ' \t\n\r':
                    pos += 1
                if pos >= n:
                    raise JSONError("Unexpected end of input", pos)
                if s[pos] == '}':
                    raise JSONError("Trailing comma in object", pos)
            else:
                raise JSONError("Expected ',' or '}', got unexpected character", pos)

    elif c == '"':
        return _parse_string(s, pos, n)

    elif c == 't':
        if pos + 4 <= n and s[pos + 1] == 'r' and s[pos + 2] == 'u' and s[pos + 3] == 'e':
            return True, pos + 4
        for i in range(1, 4):
            if pos + i >= n or s[pos + i] != 'true'[i]:
                raise JSONError("Invalid literal", pos + i)
        raise JSONError("Invalid literal", pos + 4)

    elif c == 'f':
        if pos + 5 <= n and s[pos + 1] == 'a' and s[pos + 2] == 'l' and s[pos + 3] == 's' and s[pos + 4] == 'e':
            return False, pos + 5
        for i in range(1, 5):
            if pos + i >= n or s[pos + i] != 'false'[i]:
                raise JSONError("Invalid literal", pos + i)
        raise JSONError("Invalid literal", pos + 5)

    elif c == 'n':
        if pos + 4 <= n and s[pos + 1] == 'u' and s[pos + 2] == 'l' and s[pos + 3] == 'l':
            return None, pos + 4
        for i in range(1, 4):
            if pos + i >= n or s[pos + i] != 'null'[i]:
                raise JSONError("Invalid literal", pos + i)
        raise JSONError("Invalid literal", pos + 4)

    elif c == '-' or '0' <= c <= '9':
        return _parse_number(s, pos, n)

    else:
        raise JSONError("Unexpected character", pos)


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")
    n = len(s)
    value, pos = _parse_value(s, 0, n, 0)
    while pos < n and s[pos] in ' \t\n\r':
        pos += 1
    if pos != n:
        raise JSONError("Trailing data", pos)
    return value
