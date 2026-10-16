"""Strict RFC 8259 JSON parser – standard library only, no json/ast/eval."""

class JSONError(ValueError):
    def __init__(self, message, pos):
        super().__init__(message)
        self.pos = pos


class _Parser:
    __slots__ = ('s', 'pos')

    def __init__(self, s):
        self.s = s
        self.pos = 0

    def _skip_ws(self):
        s = self.s
        pos = self.pos
        n = len(s)
        while pos < n:
            c = s[pos]
            if c == ' ' or c == '\t' or c == '\n' or c == '\r':
                pos += 1
            else:
                break
        self.pos = pos

    def _parse_value(self, depth):
        self._skip_ws()
        if self.pos >= len(self.s):
            raise JSONError("unexpected end of input", self.pos)
        c = self.s[self.pos]

        if c == '[':
            nd = depth + 1
            if nd > 500:
                raise JSONError("maximum nesting depth exceeded", self.pos)
            self.pos += 1
            arr = []
            self._skip_ws()
            if self.pos < len(self.s) and self.s[self.pos] == ']':
                self.pos += 1
                return arr
            while True:
                arr.append(self._parse_value(nd))
                self._skip_ws()
                if self.pos >= len(self.s):
                    raise JSONError("unexpected end of input", self.pos)
                ch = self.s[self.pos]
                if ch == ']':
                    self.pos += 1
                    return arr
                if ch == ',':
                    self.pos += 1
                    continue
                raise JSONError("expected ',' or ']'", self.pos)

        if c == '{':
            nd = depth + 1
            if nd > 500:
                raise JSONError("maximum nesting depth exceeded", self.pos)
            self.pos += 1
            obj = {}
            self._skip_ws()
            if self.pos < len(self.s) and self.s[self.pos] == '}':
                self.pos += 1
                return obj
            while True:
                self._skip_ws()
                if self.pos >= len(self.s):
                    raise JSONError("unexpected end of input", self.pos)
                if self.s[self.pos] != '"':
                    raise JSONError("expected string key", self.pos)
                key = self._parse_string()
                self._skip_ws()
                if self.pos >= len(self.s):
                    raise JSONError("unexpected end of input", self.pos)
                if self.s[self.pos] != ':':
                    raise JSONError("expected ':'", self.pos)
                self.pos += 1
                obj[key] = self._parse_value(nd)
                self._skip_ws()
                if self.pos >= len(self.s):
                    raise JSONError("unexpected end of input", self.pos)
                ch = self.s[self.pos]
                if ch == '}':
                    self.pos += 1
                    return obj
                if ch == ',':
                    self.pos += 1
                    continue
                raise JSONError("expected ',' or '}'", self.pos)

        if c == '"':
            return self._parse_string()

        if c == 't':
            return self._parse_literal("true", True)
        if c == 'f':
            return self._parse_literal("false", False)
        if c == 'n':
            return self._parse_literal("null", None)

        if c == '-' or ('0' <= c <= '9'):
            return self._parse_number()

        raise JSONError("unexpected character", self.pos)

    def _parse_string(self):
        self.pos += 1  # skip opening quote
        s = self.s
        n = len(s)
        chars = []
        while True:
            if self.pos >= n:
                raise JSONError("unexpected end of input", self.pos)
            c = s[self.pos]
            if c == '"':
                self.pos += 1
                return ''.join(chars)
            if c == '\\':
                self.pos += 1
                if self.pos >= n:
                    raise JSONError("unexpected end of input", self.pos)
                e = s[self.pos]
                if e == '"':
                    chars.append('"'); self.pos += 1
                elif e == '\\':
                    chars.append('\\'); self.pos += 1
                elif e == '/':
                    chars.append('/'); self.pos += 1
                elif e == 'b':
                    chars.append('\b'); self.pos += 1
                elif e == 'f':
                    chars.append('\f'); self.pos += 1
                elif e == 'n':
                    chars.append('\n'); self.pos += 1
                elif e == 'r':
                    chars.append('\r'); self.pos += 1
                elif e == 't':
                    chars.append('\t'); self.pos += 1
                elif e == 'u':
                    self.pos += 1
                    code = self._parse_hex4()
                    if 0xD800 <= code <= 0xDBFF:
                        if (self.pos + 1 < n and s[self.pos] == '\\'
                                and s[self.pos + 1] == 'u'):
                            save = self.pos
                            self.pos += 2
                            code2 = self._try_hex4()
                            if code2 is not None and 0xDC00 <= code2 <= 0xDFFF:
                                combined = (0x10000 +
                                            ((code - 0xD800) << 10) +
                                            (code2 - 0xDC00))
                                chars.append(chr(combined))
                            else:
                                self.pos = save
                                chars.append(chr(code))
                        else:
                            chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    raise JSONError("invalid escape", self.pos)
            elif ord(c) < 0x20:
                raise JSONError("control character in string", self.pos)
            else:
                chars.append(c)
                self.pos += 1

    def _parse_hex4(self):
        s = self.s
        n = len(s)
        val = 0
        for _ in range(4):
            if self.pos >= n:
                raise JSONError("unexpected end of input", self.pos)
            c = s[self.pos]
            if '0' <= c <= '9':
                d = ord(c) - 48
            elif 'a' <= c <= 'f':
                d = ord(c) - 87
            elif 'A' <= c <= 'F':
                d = ord(c) - 55
            else:
                raise JSONError("invalid hex digit", self.pos)
            val = val * 16 + d
            self.pos += 1
        return val

    def _try_hex4(self):
        """Read 4 ASCII hex digits or return None without advancing pos."""
        s = self.s
        n = len(s)
        if self.pos + 4 > n:
            return None
        val = 0
        for i in range(4):
            c = s[self.pos + i]
            if '0' <= c <= '9':
                d = ord(c) - 48
            elif 'a' <= c <= 'f':
                d = ord(c) - 87
            elif 'A' <= c <= 'F':
                d = ord(c) - 55
            else:
                return None
            val = val * 16 + d
        self.pos += 4
        return val

    def _parse_literal(self, expected, value):
        s = self.s
        n = len(s)
        start = self.pos
        for i in range(len(expected)):
            if start + i >= n:
                raise JSONError("unexpected end of input", n)
            if s[start + i] != expected[i]:
                raise JSONError("invalid literal", start + i)
        self.pos = start + len(expected)
        return value

    def _parse_number(self):
        s = self.s
        n = len(s)
        start = self.pos

        if s[self.pos] == '-':
            self.pos += 1

        if self.pos >= n:
            raise JSONError("unexpected end of input", self.pos)

        c = s[self.pos]
        if c == '0':
            self.pos += 1
        elif '1' <= c <= '9':
            self.pos += 1
            while self.pos < n and '0' <= s[self.pos] <= '9':
                self.pos += 1
        else:
            raise JSONError("invalid number", self.pos)

        is_float = False

        if self.pos < n and s[self.pos] == '.':
            is_float = True
            self.pos += 1
            if self.pos >= n or not ('0' <= s[self.pos] <= '9'):
                raise JSONError("invalid number", self.pos)
            self.pos += 1
            while self.pos < n and '0' <= s[self.pos] <= '9':
                self.pos += 1

        if self.pos < n and (s[self.pos] == 'e' or s[self.pos] == 'E'):
            is_float = True
            self.pos += 1
            if self.pos < n and (s[self.pos] == '+' or s[self.pos] == '-'):
                self.pos += 1
            if self.pos >= n or not ('0' <= s[self.pos] <= '9'):
                raise JSONError("invalid number", self.pos)
            self.pos += 1
            while self.pos < n and '0' <= s[self.pos] <= '9':
                self.pos += 1

        text = s[start:self.pos]
        if is_float:
            return float(text)
        return int(text)


def loads(s):
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__}")
    parser = _Parser(s)
    result = parser._parse_value(0)
    parser._skip_ws()
    if parser.pos < len(s):
        raise JSONError("trailing garbage", parser.pos)
    return result
