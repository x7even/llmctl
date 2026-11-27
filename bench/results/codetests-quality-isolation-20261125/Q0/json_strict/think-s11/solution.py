class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")
    return _Parser(s).parse()


class _Parser:
    __slots__ = ('s', 'n')

    def __init__(self, s):
        self.s = s
        self.n = len(s)

    def parse(self):
        pos = self._skip_ws(0)
        if pos >= self.n:
            raise JSONError("empty input", pos)
        value, pos = self._parse_value(pos, 0)
        pos = self._skip_ws(pos)
        if pos < self.n:
            raise JSONError("trailing garbage", pos)
        return value

    def _skip_ws(self, pos):
        s = self.s
        n = self.n
        while pos < n:
            c = s[pos]
            if c == ' ' or c == '\t' or c == '\n' or c == '\r':
                pos += 1
            else:
                break
        return pos

    def _parse_value(self, pos, depth):
        s = self.s
        n = self.n
        pos = self._skip_ws(pos)
        if pos >= n:
            raise JSONError("unexpected end of input", n)
        c = s[pos]

        if c == '{':
            if depth >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            obj = {}
            pos = self._skip_ws(pos)
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == '}':
                return obj, pos + 1
            while True:
                pos = self._skip_ws(pos)
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                if s[pos] != '"':
                    raise JSONError("expected string key", pos)
                key, pos = self._parse_string(pos)
                pos = self._skip_ws(pos)
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                if s[pos] != ':':
                    raise JSONError("expected ':'", pos)
                pos += 1
                value, pos = self._parse_value(pos, depth + 1)
                obj[key] = value
                pos = self._skip_ws(pos)
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                c2 = s[pos]
                if c2 == ',':
                    pos += 1
                    pos = self._skip_ws(pos)
                    if pos >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[pos] == '}':
                        raise JSONError("trailing comma in object", pos)
                elif c2 == '}':
                    return obj, pos + 1
                else:
                    raise JSONError("expected ',' or '}'", pos)

        elif c == '[':
            if depth >= 500:
                raise JSONError("maximum nesting depth exceeded", pos)
            pos += 1
            arr = []
            pos = self._skip_ws(pos)
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ']':
                return arr, pos + 1
            while True:
                value, pos = self._parse_value(pos, depth + 1)
                arr.append(value)
                pos = self._skip_ws(pos)
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                c2 = s[pos]
                if c2 == ',':
                    pos += 1
                    pos = self._skip_ws(pos)
                    if pos >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[pos] == ']':
                        raise JSONError("trailing comma in array", pos)
                elif c2 == ']':
                    return arr, pos + 1
                else:
                    raise JSONError("expected ',' or ']'", pos)

        elif c == '"':
            return self._parse_string(pos)
        elif c == 't':
            pos = self._match_literal(pos, 'true')
            return True, pos
        elif c == 'f':
            pos = self._match_literal(pos, 'false')
            return False, pos
        elif c == 'n':
            pos = self._match_literal(pos, 'null')
            return None, pos
        elif c == '-' or '0' <= c <= '9':
            return self._parse_number(pos)
        else:
            raise JSONError(f"unexpected character {c!r}", pos)

    def _match_literal(self, pos, literal):
        s = self.s
        n = self.n
        for i in range(len(literal)):
            if pos + i >= n or s[pos + i] != literal[i]:
                raise JSONError(f"invalid literal, expected {literal!r}", pos + i)
        return pos + len(literal)

    def _parse_number(self, pos):
        s = self.s
        n = self.n
        start = pos

        if s[pos] == '-':
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)

        c = s[pos]
        if c == '0':
            pos += 1
            if pos < n and '0' <= s[pos] <= '9':
                raise JSONError("leading zero not allowed", pos)
        elif '1' <= c <= '9':
            pos += 1
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1
        else:
            raise JSONError(f"invalid digit in number", pos)

        is_float = False

        if pos < n and s[pos] == '.':
            is_float = True
            pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit after decimal point", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        if pos < n and (s[pos] == 'e' or s[pos] == 'E'):
            is_float = True
            pos += 1
            if pos < n and (s[pos] == '+' or s[pos] == '-'):
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if not ('0' <= s[pos] <= '9'):
                raise JSONError("expected digit in exponent", pos)
            while pos < n and '0' <= s[pos] <= '9':
                pos += 1

        text = s[start:pos]
        if is_float:
            return float(text), pos
        else:
            return int(text), pos

    def _parse_string(self, pos):
        s = self.s
        n = self.n
        pos += 1  # skip opening "
        chars = []

        while True:
            if pos >= n:
                raise JSONError("unterminated string", n)
            c = s[pos]
            if c == '"':
                pos += 1
                return ''.join(chars), pos
            elif c == '\\':
                pos += 1
                if pos >= n:
                    raise JSONError("unterminated escape sequence", n)
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
                        raise JSONError("truncated \\u escape", n)
                    for i in range(4):
                        hc = s[pos + i]
                        if hc not in '0123456789abcdefABCDEF':
                            raise JSONError(f"invalid hex digit in \\u escape", pos + i)
                    code = int(s[pos:pos + 4], 16)
                    pos += 4

                    if 0xD800 <= code <= 0xDBFF:
                        if (pos + 6 <= n and s[pos] == '\\' and s[pos + 1] == 'u'
                                and all(hc in '0123456789abcdefABCDEF' for hc in s[pos + 2:pos + 6])):
                            code2 = int(s[pos + 2:pos + 6], 16)
                            if 0xDC00 <= code2 <= 0xDFFF:
                                combined = 0x10000 + ((code - 0xD800) << 10) + (code2 - 0xDC00)
                                chars.append(chr(combined))
                                pos += 6
                                continue
                    chars.append(chr(code))
                else:
                    raise JSONError(f"invalid escape sequence \\{ec}", pos)
            elif ord(c) < 0x20:
                raise JSONError(f"unescaped control character in string", pos)
            else:
                chars.append(c)
                pos += 1
