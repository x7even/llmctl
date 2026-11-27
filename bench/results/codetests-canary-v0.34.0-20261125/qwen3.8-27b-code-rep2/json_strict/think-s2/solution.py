class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")
    _p = _Parser(s)
    return _p._parse()


class _Parser:
    __slots__ = ('s', 'n', 'pos', 'depth')

    _WS = ' \t\n\r'
    _HEX = frozenset('0123456789abcdefABCDEF')
    _HEX_VAL = '0123456789abcdef'

    def __init__(self, s: str):
        self.s = s
        self.n = len(s)
        self.pos = 0
        self.depth = 0

    def _err(self, msg: str, pos: int = -1):
        if pos < 0:
            pos = self.pos
        raise JSONError(msg, pos)

    def _skip_ws(self):
        s, n, pos = self.s, self.n, self.pos
        while pos < n and s[pos] in self._WS:
            pos += 1
        self.pos = pos

    def _parse(self):
        self._skip_ws()
        if self.pos >= self.n:
            self._err("unexpected end of input")
        val = self._value()
        self._skip_ws()
        if self.pos < self.n:
            self._err("trailing garbage")
        return val

    def _value(self):
        self._skip_ws()
        if self.pos >= self.n:
            self._err("unexpected end of input")
        c = self.s[self.pos]
        if c == '{':
            return self._object()
        if c == '[':
            return self._array()
        if c == '"':
            return self._string()
        if c == 't':
            return self._literal('true', True)
        if c == 'f':
            return self._literal('false', False)
        if c == 'n':
            return self._literal('null', None)
        if c == '-' or '0' <= c <= '9':
            return self._number()
        self._err(f"unexpected character {c!r}")

    def _literal(self, word: str, val):
        s, n, pos = self.s, self.n, self.pos
        for i, ch in enumerate(word):
            if pos + i >= n or s[pos + i] != ch:
                self._err("invalid literal", pos + i)
        self.pos = pos + len(word)
        return val

    def _number(self):
        s, n = self.s, self.n
        start = self.pos
        if s[self.pos] == '-':
            self.pos += 1
        if self.pos >= n:
            self._err("unexpected end of input")
        c = s[self.pos]
        if c == '0':
            self.pos += 1
            if self.pos < n and '0' <= s[self.pos] <= '9':
                self._err("leading zero not allowed", self.pos)
        elif '1' <= c <= '9':
            self.pos += 1
            while self.pos < n and '0' <= s[self.pos] <= '9':
                self.pos += 1
        else:
            self._err("invalid number", self.pos)
        is_float = False
        if self.pos < n and s[self.pos] == '.':
            is_float = True
            self.pos += 1
            if self.pos >= n:
                self._err("unexpected end of input")
            if not ('0' <= s[self.pos] <= '9'):
                self._err("expected digit after decimal point", self.pos)
            while self.pos < n and '0' <= s[self.pos] <= '9':
                self.pos += 1
        if self.pos < n and s[self.pos] in 'eE':
            is_float = True
            self.pos += 1
            if self.pos < n and s[self.pos] in '+-':
                self.pos += 1
            if self.pos >= n:
                self._err("unexpected end of input")
            if not ('0' <= s[self.pos] <= '9'):
                self._err("expected digit in exponent", self.pos)
            while self.pos < n and '0' <= s[self.pos] <= '9':
                self.pos += 1
        text = s[start:self.pos]
        if is_float:
            return float(text)
        return int(text)

    def _string(self):
        s, n = self.s, self.n
        self.pos += 1  # consume opening quote
        parts = []
        append = parts.append
        while True:
            if self.pos >= n:
                self._err("unexpected end of input")
            c = s[self.pos]
            if c == '"':
                self.pos += 1
                return ''.join(parts)
            if c == '\\':
                self.pos += 1
                if self.pos >= n:
                    self._err("unexpected end of input")
                ec = s[self.pos]
                if ec == '"':
                    append('"'); self.pos += 1
                elif ec == '\\':
                    append('\\'); self.pos += 1
                elif ec == '/':
                    append('/'); self.pos += 1
                elif ec == 'b':
                    append('\b'); self.pos += 1
                elif ec == 'f':
                    append('\f'); self.pos += 1
                elif ec == 'n':
                    append('\n'); self.pos += 1
                elif ec == 'r':
                    append('\r'); self.pos += 1
                elif ec == 't':
                    append('\t'); self.pos += 1
                elif ec == 'u':
                    self.pos += 1
                    code = self._hex4()
                    if 0xD800 <= code <= 0xDBFF:
                        # Check for immediately following \uXXXX low surrogate
                        p = self.pos
                        if (p + 5 < n and s[p] == '\\' and s[p + 1] == 'u'
                                and s[p+2] in self._HEX and s[p+3] in self._HEX
                                and s[p+4] in self._HEX and s[p+5] in self._HEX):
                            lo = (self._HEX_VAL.index(s[p+2].lower()) << 12
                                  | self._HEX_VAL.index(s[p+3].lower()) << 8
                                  | self._HEX_VAL.index(s[p+4].lower()) << 4
                                  | self._HEX_VAL.index(s[p+5].lower()))
                            if 0xDC00 <= lo <= 0xDFFF:
                                cp = 0x10000 + ((code - 0xD800) << 10) + (lo - 0xDC00)
                                append(chr(cp))
                                self.pos = p + 6
                                continue
                    append(chr(code))
                else:
                    self._err(f"invalid escape \\{ec}", self.pos)
            elif ord(c) < 0x20:
                self._err("control character in string", self.pos)
            else:
                append(c)
                self.pos += 1

    def _hex4(self) -> int:
        s, n = self.s, self.n
        code = 0
        for _ in range(4):
            if self.pos >= n:
                self._err("unexpected end of input")
            c = s[self.pos]
            if c not in self._HEX:
                self._err("invalid hex digit in \\u escape", self.pos)
            code = (code << 4) | self._HEX_VAL.index(c.lower())
            self.pos += 1
        return code

    def _object(self):
        self.depth += 1
        if self.depth > 500:
            self._err("maximum nesting depth exceeded")
        self.pos += 1  # consume '{'
        result = {}
        self._skip_ws()
        if self.pos >= self.n:
            self._err("unexpected end of input")
        if self.s[self.pos] == '}':
            self.pos += 1
            self.depth -= 1
            return result
        while True:
            self._skip_ws()
            if self.pos >= self.n:
                self._err("unexpected end of input")
            if self.s[self.pos] != '"':
                self._err("expected string key")
            key = self._string()
            self._skip_ws()
            if self.pos >= self.n:
                self._err("unexpected end of input")
            if self.s[self.pos] != ':':
                self._err("expected ':'")
            self.pos += 1
            val = self._value()
            result[key] = val
            self._skip_ws()
            if self.pos >= self.n:
                self._err("unexpected end of input")
            c = self.s[self.pos]
            if c == ',':
                self.pos += 1
                self._skip_ws()
                if self.pos >= self.n:
                    self._err("unexpected end of input")
                if self.s[self.pos] == '}':
                    self._err("trailing comma")
            elif c == '}':
                self.pos += 1
                self.depth -= 1
                return result
            else:
                self._err("expected ',' or '}'")

    def _array(self):
        self.depth += 1
        if self.depth > 500:
            self._err("maximum nesting depth exceeded")
        self.pos += 1  # consume '['
        result = []
        append = result.append
        self._skip_ws()
        if self.pos >= self.n:
            self._err("unexpected end of input")
        if self.s[self.pos] == ']':
            self.pos += 1
            self.depth -= 1
            return result
        while True:
            val = self._value()
            append(val)
            self._skip_ws()
            if self.pos >= self.n:
                self._err("unexpected end of input")
            c = self.s[self.pos]
            if c == ',':
                self.pos += 1
                self._skip_ws()
                if self.pos >= self.n:
                    self._err("unexpected end of input")
                if self.s[self.pos] == ']':
                    self._err("trailing comma")
            elif c == ']':
                self.pos += 1
                self.depth -= 1
                return result
            else:
                self._err("expected ',' or ']'")
