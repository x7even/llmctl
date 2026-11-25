class JSONError(ValueError):
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")
    _p = _Parser(s)
    return _p.parse()


class _Parser:
    __slots__ = ('s', 'pos', 'depth')

    def __init__(self, s: str):
        self.s = s
        self.pos = 0
        self.depth = 0

    def parse(self):
        self._skip_ws()
        n = len(self.s)
        if self.pos >= n:
            raise JSONError("unexpected end of input", self.pos)
        c = self.s[self.pos]
        if c == '{':
            value = self._parse_object()
        elif c == '[':
            value = self._parse_array()
        elif c == '"':
            value = self._parse_string()
        elif c == 't':
            value = self._parse_literal('true', True)
        elif c == 'f':
            value = self._parse_literal('false', False)
        elif c == 'n':
            value = self._parse_literal('null', None)
        elif c == '-' or c >= '0' and c <= '9':
            value = self._parse_number()
        else:
            raise JSONError(f"unexpected character {c!r}", self.pos)
        self._skip_ws()
        if self.pos < len(self.s):
            raise JSONError("trailing garbage", self.pos)
        return value

    def _skip_ws(self):
        s = self.s
        pos = self.pos
        n = len(s)
        while pos < n and s[pos] in ' \t\n\r':
            pos += 1
        self.pos = pos

    def _parse_literal(self, expected, value):
        s = self.s
        n = len(s)
        pos = self.pos
        for i in range(len(expected)):
            if pos + i >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos + i] != expected[i]:
                raise JSONError(f"invalid literal", pos + i)
        self.pos = pos + len(expected)
        return value

    def _parse_number(self):
        s = self.s
        n = len(s)
        start = self.pos
        pos = self.pos

        if pos < n and s[pos] == '-':
            pos += 1

        if pos >= n:
            raise JSONError("unexpected end of input", n)
        c = s[pos]
        if c == '0':
            pos += 1
            if pos < n and s[pos] >= '0' and s[pos] <= '9':
                raise JSONError("leading zero not allowed", pos)
        elif c >= '1' and c <= '9':
            pos += 1
            while pos < n and s[pos] >= '0' and s[pos] <= '9':
                pos += 1
        else:
            raise JSONError(f"expected digit, got {c!r}", pos)

        is_float = False
        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if not (s[pos] >= '0' and s[pos] <= '9'):
                raise JSONError(f"expected digit after '.', got {s[pos]!r}", pos)
            while pos < n and s[pos] >= '0' and s[pos] <= '9':
                pos += 1

        if pos < n and s[pos] in 'eE':
            is_float = True
            pos += 1
            if pos < n and s[pos] in '+-':
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if not (s[pos] >= '0' and s[pos] <= '9'):
                raise JSONError(f"expected digit in exponent, got {s[pos]!r}", pos)
            while pos < n and s[pos] >= '0' and s[pos] <= '9':
                pos += 1

        self.pos = pos
        text = s[start:pos]
        if is_float:
            return float(text)
        return int(text)

    def _parse_string(self):
        s = self.s
        n = len(s)
        pos = self.pos + 1
        result = []
        while True:
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]
            if c == '"':
                pos += 1
                self.pos = pos
                return ''.join(result)
            elif c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                ec = s[pos]
                if ec == '"':
                    result.append('"')
                    pos += 1
                elif ec == '\\':
                    result.append('\\')
                    pos += 1
                elif ec == '/':
                    result.append('/')
                    pos += 1
                elif ec == 'b':
                    result.append('\b')
                    pos += 1
                elif ec == 'f':
                    result.append('\f')
                    pos += 1
                elif ec == 'n':
                    result.append('\n')
                    pos += 1
                elif ec == 'r':
                    result.append('\r')
                    pos += 1
                elif ec == 't':
                    result.append('\t')
                    pos += 1
                elif ec == 'u':
                    pos += 1
                    for i in range(4):
                        if pos + i >= n:
                            raise JSONError("unexpected end of input", n)
                        hc = s[pos + i]
                        if not (hc in '0123456789abcdefABCDEF'):
                            raise JSONError(f"invalid hex digit {hc!r}", pos + i)
                    code = int(s[pos:pos + 4], 16)
                    pos += 4
                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 6 <= n and
                                s[pos] == '\\' and s[pos + 1] == 'u'):
                            h2 = s[pos + 2:pos + 6]
                            valid = True
                            for hc in h2:
                                if hc not in '0123456789abcdefABCDEF':
                                    valid = False
                                    break
                            if valid:
                                code2 = int(h2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                    result.append(chr(combined))
                                    pos += 6
                                    continue
                    result.append(chr(code))
                else:
                    raise JSONError(f"invalid escape \\{ec}", pos)
            elif ord(c) < 0x20:
                raise JSONError(f"unescaped control character in string", pos)
            else:
                result.append(c)
                pos += 1

    def _parse_array(self):
        self.depth += 1
        if self.depth > 500:
            raise JSONError("maximum nesting depth exceeded", self.pos)
        s = self.s
        n = len(s)
        self.pos += 1
        result = []
        self._skip_ws()
        if self.pos >= n:
            raise JSONError("unexpected end of input", n)
        if s[self.pos] == ']':
            self.pos += 1
            self.depth -= 1
            return result
        while True:
            self._skip_ws()
            pos = self.pos
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]
            if c == '{':
                value = self._parse_object()
            elif c == '[':
                value = self._parse_array()
            elif c == '"':
                value = self._parse_string()
            elif c == 't':
                value = self._parse_literal('true', True)
            elif c == 'f':
                value = self._parse_literal('false', False)
            elif c == 'n':
                value = self._parse_literal('null', None)
            elif c == '-' or c >= '0' and c <= '9':
                value = self._parse_number()
            else:
                raise JSONError(f"unexpected character {c!r}", pos)
            result.append(value)
            self._skip_ws()
            pos = self.pos
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                self.pos = pos + 1
                self._skip_ws()
                pos = self.pos
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                if s[pos] == ']':
                    raise JSONError("trailing comma", pos)
            elif s[pos] == ']':
                self.pos = pos + 1
                self.depth -= 1
                return result
            else:
                raise JSONError(f"expected ',' or ']', got {s[pos]!r}", pos)

    def _parse_object(self):
        self.depth += 1
        if self.depth > 500:
            raise JSONError("maximum nesting depth exceeded", self.pos)
        s = self.s
        n = len(s)
        self.pos += 1
        result = {}
        self._skip_ws()
        if self.pos >= n:
            raise JSONError("unexpected end of input", n)
        if s[self.pos] == '}':
            self.pos += 1
            self.depth -= 1
            return result
        while True:
            self._skip_ws()
            pos = self.pos
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] != '"':
                raise JSONError(f"expected string key, got {s[pos]!r}", pos)
            key = self._parse_string()
            self._skip_ws()
            pos = self.pos
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] != ':':
                raise JSONError(f"expected ':', got {s[pos]!r}", pos)
            self.pos = pos + 1
            self._skip_ws()
            pos = self.pos
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]
            if c == '{':
                value = self._parse_object()
            elif c == '[':
                value = self._parse_array()
            elif c == '"':
                value = self._parse_string()
            elif c == 't':
                value = self._parse_literal('true', True)
            elif c == 'f':
                value = self._parse_literal('false', False)
            elif c == 'n':
                value = self._parse_literal('null', None)
            elif c == '-' or c >= '0' and c <= '9':
                value = self._parse_number()
            else:
                raise JSONError(f"unexpected character {c!r}", pos)
            result[key] = value
            self._skip_ws()
            pos = self.pos
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ',':
                self.pos = pos + 1
                self._skip_ws()
                pos = self.pos
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                if s[pos] == '}':
                    raise JSONError("trailing comma", pos)
            elif s[pos] == '}':
                self.pos = pos + 1
                self.depth -= 1
                return result
            else:
                raise JSONError(f"expected ',' or '}}', got {s[pos]!r}", pos)
