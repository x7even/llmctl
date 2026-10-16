class JSONError(ValueError):
    def __init__(self, message, pos):
        super().__init__(message)
        self.pos = pos


def loads(s):
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__}")
    p = _Parser(s)
    return p.parse()


class _Parser:
    __slots__ = ('s', 'pos', 'length')

    def __init__(self, s):
        self.s = s
        self.pos = 0
        self.length = len(s)

    def parse(self):
        s = self.s
        length = self.length
        pos = 0
        stack = []
        result = None
        depth = 0
        state = 'value'

        while True:
            if state == 'value':
                while pos < length and (s[pos] == ' ' or s[pos] == '\t' or s[pos] == '\n' or s[pos] == '\r'):
                    pos += 1
                if pos >= length:
                    raise JSONError("unexpected end of input", pos)
                c = s[pos]
                if c == '"':
                    self.pos = pos
                    result = self._parse_string()
                    pos = self.pos
                    state = 'after_value'
                elif c == '{':
                    if depth + 1 > 500:
                        raise JSONError("maximum nesting depth exceeded", pos)
                    depth += 1
                    pos += 1
                    stack.append(('o', {}, None))
                    state = 'object_first'
                elif c == '[':
                    if depth + 1 > 500:
                        raise JSONError("maximum nesting depth exceeded", pos)
                    depth += 1
                    pos += 1
                    stack.append(('a', [], None))
                    state = 'array_first'
                elif c == 't':
                    self.pos = pos
                    result = self._parse_literal('true', True)
                    pos = self.pos
                    state = 'after_value'
                elif c == 'f':
                    self.pos = pos
                    result = self._parse_literal('false', False)
                    pos = self.pos
                    state = 'after_value'
                elif c == 'n':
                    self.pos = pos
                    result = self._parse_literal('null', None)
                    pos = self.pos
                    state = 'after_value'
                elif c == '-' or ('0' <= c <= '9'):
                    self.pos = pos
                    result = self._parse_number()
                    pos = self.pos
                    state = 'after_value'
                else:
                    raise JSONError("unexpected character", pos)

            elif state == 'after_value':
                if not stack:
                    while pos < length and (s[pos] == ' ' or s[pos] == '\t' or s[pos] == '\n' or s[pos] == '\r'):
                        pos += 1
                    if pos < length:
                        raise JSONError("trailing garbage", pos)
                    return result
                top = stack[-1]
                if top[0] == 'a':
                    top[1].append(result)
                    state = 'array_comma'
                else:
                    top[1][top[2]] = result
                    state = 'object_comma'

            elif state == 'array_first':
                while pos < length and (s[pos] == ' ' or s[pos] == '\t' or s[pos] == '\n' or s[pos] == '\r'):
                    pos += 1
                if pos >= length:
                    raise JSONError("unexpected end of input", pos)
                if s[pos] == ']':
                    pos += 1
                    result = stack.pop()[1]
                    depth -= 1
                    state = 'after_value'
                else:
                    state = 'value'

            elif state == 'array_comma':
                while pos < length and (s[pos] == ' ' or s[pos] == '\t' or s[pos] == '\n' or s[pos] == '\r'):
                    pos += 1
                if pos >= length:
                    raise JSONError("unexpected end of input", pos)
                c = s[pos]
                if c == ',':
                    pos += 1
                    state = 'array_next'
                elif c == ']':
                    pos += 1
                    result = stack.pop()[1]
                    depth -= 1
                    state = 'after_value'
                else:
                    raise JSONError("expected ',' or ']'", pos)

            elif state == 'array_next':
                state = 'value'

            elif state == 'object_first':
                while pos < length and (s[pos] == ' ' or s[pos] == '\t' or s[pos] == '\n' or s[pos] == '\r'):
                    pos += 1
                if pos >= length:
                    raise JSONError("unexpected end of input", pos)
                c = s[pos]
                if c == '}':
                    pos += 1
                    result = stack.pop()[1]
                    depth -= 1
                    state = 'after_value'
                elif c == '"':
                    self.pos = pos
                    key = self._parse_string()
                    pos = self.pos
                    stack[-1] = ('o', stack[-1][1], key)
                    state = 'object_colon'
                else:
                    raise JSONError("expected '\"' or '}'", pos)

            elif state == 'object_colon':
                while pos < length and (s[pos] == ' ' or s[pos] == '\t' or s[pos] == '\n' or s[pos] == '\r'):
                    pos += 1
                if pos >= length:
                    raise JSONError("unexpected end of input", pos)
                if s[pos] == ':':
                    pos += 1
                    state = 'value'
                else:
                    raise JSONError("expected ':'", pos)

            elif state == 'object_comma':
                while pos < length and (s[pos] == ' ' or s[pos] == '\t' or s[pos] == '\n' or s[pos] == '\r'):
                    pos += 1
                if pos >= length:
                    raise JSONError("unexpected end of input", pos)
                c = s[pos]
                if c == ',':
                    pos += 1
                    state = 'object_next'
                elif c == '}':
                    pos += 1
                    result = stack.pop()[1]
                    depth -= 1
                    state = 'after_value'
                else:
                    raise JSONError("expected ',' or '}'", pos)

            elif state == 'object_next':
                while pos < length and (s[pos] == ' ' or s[pos] == '\t' or s[pos] == '\n' or s[pos] == '\r'):
                    pos += 1
                if pos >= length:
                    raise JSONError("unexpected end of input", pos)
                if s[pos] == '"':
                    self.pos = pos
                    key = self._parse_string()
                    pos = self.pos
                    stack[-1] = ('o', stack[-1][1], key)
                    state = 'object_colon'
                else:
                    raise JSONError("expected '\"'", pos)

    def _parse_string(self):
        s = self.s
        length = self.length
        pos = self.pos + 1
        parts = []

        while True:
            if pos >= length:
                self.pos = pos
                raise JSONError("unterminated string", pos)
            c = s[pos]
            if c == '"':
                self.pos = pos + 1
                return ''.join(parts)
            elif c == '\\':
                pos += 1
                if pos >= length:
                    self.pos = pos
                    raise JSONError("unterminated string", pos)
                esc = s[pos]
                if esc == '"':
                    parts.append('"')
                    pos += 1
                elif esc == '\\':
                    parts.append('\\')
                    pos += 1
                elif esc == '/':
                    parts.append('/')
                    pos += 1
                elif esc == 'b':
                    parts.append('\b')
                    pos += 1
                elif esc == 'f':
                    parts.append('\f')
                    pos += 1
                elif esc == 'n':
                    parts.append('\n')
                    pos += 1
                elif esc == 'r':
                    parts.append('\r')
                    pos += 1
                elif esc == 't':
                    parts.append('\t')
                    pos += 1
                elif esc == 'u':
                    pos += 1
                    if pos + 4 > length:
                        self.pos = pos
                        raise JSONError("unexpected end in \\u escape", pos)
                    code = 0
                    for i in range(4):
                        ch = s[pos + i]
                        if '0' <= ch <= '9':
                            code = code * 16 + (ord(ch) - 48)
                        elif 'a' <= ch <= 'f':
                            code = code * 16 + (ord(ch) - 87)
                        elif 'A' <= ch <= 'F':
                            code = code * 16 + (ord(ch) - 55)
                        else:
                            self.pos = pos + i
                            raise JSONError("invalid hex digit", pos + i)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 5 < length and s[pos] == '\\' and s[pos + 1] == 'u'):
                            h1 = s[pos + 2]
                            h2 = s[pos + 3]
                            h3 = s[pos + 4]
                            h4 = s[pos + 5]
                            if (self._is_hex(h1) and self._is_hex(h2) and
                                    self._is_hex(h3) and self._is_hex(h4)):
                                code2 = (self._hv(h1) << 12 | self._hv(h2) << 8 |
                                         self._hv(h3) << 4 | self._hv(h4))
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    parts.append(chr(combined))
                                    pos += 6
                                    continue
                        parts.append(chr(code))
                    else:
                        parts.append(chr(code))
                else:
                    self.pos = pos
                    raise JSONError("invalid escape", pos)
            elif ord(c) < 0x20:
                self.pos = pos
                raise JSONError("control character in string", pos)
            else:
                parts.append(c)
                pos += 1

    @staticmethod
    def _is_hex(c):
        return ('0' <= c <= '9') or ('a' <= c <= 'f') or ('A' <= c <= 'F')

    @staticmethod
    def _hv(c):
        if '0' <= c <= '9':
            return ord(c) - 48
        elif 'a' <= c <= 'f':
            return ord(c) - 87
        return ord(c) - 55

    def _parse_number(self):
        s = self.s
        length = self.length
        pos = self.pos
        start = pos
        is_float = False

        if s[pos] == '-':
            pos += 1

        if pos >= length:
            self.pos = pos
            raise JSONError("unexpected end of input", pos)

        c = s[pos]
        if c == '0':
            pos += 1
        elif '1' <= c <= '9':
            pos += 1
            while pos < length and '0' <= s[pos] <= '9':
                pos += 1
        else:
            self.pos = pos
            raise JSONError("invalid number", pos)

        if pos < length and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= length:
                self.pos = pos
                raise JSONError("unexpected end of input", pos)
            if not ('0' <= s[pos] <= '9'):
                self.pos = pos
                raise JSONError("expected digit after '.'", pos)
            while pos < length and '0' <= s[pos] <= '9':
                pos += 1

        if pos < length and (s[pos] == 'e' or s[pos] == 'E'):
            is_float = True
            pos += 1
            if pos < length and (s[pos] == '+' or s[pos] == '-'):
                pos += 1
            if pos >= length:
                self.pos = pos
                raise JSONError("unexpected end of input", pos)
            if not ('0' <= s[pos] <= '9'):
                self.pos = pos
                raise JSONError("expected digit in exponent", pos)
            while pos < length and '0' <= s[pos] <= '9':
                pos += 1

        self.pos = pos
        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def _parse_literal(self, expected, value):
        s = self.s
        length = self.length
        pos = self.pos
        elen = len(expected)

        for i in range(elen):
            if pos + i >= length:
                self.pos = pos + i
                raise JSONError("unexpected end of input", pos + i)
            if s[pos + i] != expected[i]:
                self.pos = pos + i
                raise JSONError("invalid literal", pos + i)

        self.pos = pos + elen
        return value
