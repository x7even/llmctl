"""Strict RFC 8259 JSON parser — hand-written, standard-library only."""

__all__ = ['loads', 'JSONError']

_UNSET = object()


class JSONError(ValueError):
    """JSON parse error carrying a 0-based character position."""

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


class _Parser:
    __slots__ = ('s', 'pos', 'n', 'stack')

    def __init__(self, s: str) -> None:
        self.s = s
        self.pos = 0
        self.n = len(s)
        self.stack: list = []

    # ---- public entry ----

    def parse(self):
        self._skip_ws()
        if self.pos >= self.n:
            raise JSONError("unexpected end of input", self.n)

        value = _UNSET

        while True:
            # --- deliver a completed value to its parent container ---
            if value is not _UNSET:
                if not self.stack:
                    self._skip_ws()
                    if self.pos < self.n:
                        raise JSONError("trailing garbage", self.pos)
                    return value
                frame = self.stack[-1]
                if frame[0] == 0:          # array
                    frame[1].append(value)
                    frame[2] = 1           # after_value
                else:                       # object
                    frame[1][frame[3]] = value
                    frame[2] = 1           # after_value
                value = _UNSET

            # --- top-level: parse a single value ---
            if not self.stack:
                value = self._parse_value_or_open()
                continue

            # --- inside a container: drive the state machine ---
            frame = self.stack[-1]
            ctype = frame[0]
            state = frame[2]

            if ctype == 0:  # ---- array ----
                if state == 0:              # start: value or ]
                    self._skip_ws()
                    if self.pos >= self.n:
                        raise JSONError("unexpected end of input", self.n)
                    if self.s[self.pos] == ']':
                        self.pos += 1
                        value = frame[1]
                        self.stack.pop()
                    else:
                        value = self._parse_value_or_open()

                elif state == 1:            # after value: , or ]
                    self._skip_ws()
                    if self.pos >= self.n:
                        raise JSONError("unexpected end of input", self.n)
                    ch = self.s[self.pos]
                    if ch == ']':
                        self.pos += 1
                        value = frame[1]
                        self.stack.pop()
                    elif ch == ',':
                        self.pos += 1
                        frame[2] = 2
                    else:
                        raise JSONError("expected , or ]", self.pos)

                else:                       # after comma: value
                    value = self._parse_value_or_open()

            else:  # ---- object ----
                if state == 0:              # start: key or }
                    self._skip_ws()
                    if self.pos >= self.n:
                        raise JSONError("unexpected end of input", self.n)
                    if self.s[self.pos] == '}':
                        self.pos += 1
                        value = frame[1]
                        self.stack.pop()
                    elif self.s[self.pos] == '"':
                        frame[3] = self._parse_string()
                        frame[2] = 3
                    else:
                        raise JSONError("expected string key or }", self.pos)

                elif state == 3:            # after key: :
                    self._skip_ws()
                    if self.pos >= self.n:
                        raise JSONError("unexpected end of input", self.n)
                    if self.s[self.pos] == ':':
                        self.pos += 1
                        frame[2] = 4
                    else:
                        raise JSONError("expected :", self.pos)

                elif state == 4:            # after colon: value
                    value = self._parse_value_or_open()

                elif state == 1:            # after value: , or }
                    self._skip_ws()
                    if self.pos >= self.n:
                        raise JSONError("unexpected end of input", self.n)
                    ch = self.s[self.pos]
                    if ch == '}':
                        self.pos += 1
                        value = frame[1]
                        self.stack.pop()
                    elif ch == ',':
                        self.pos += 1
                        frame[2] = 5
                    else:
                        raise JSONError("expected , or }", self.pos)

                else:                       # state 5 – after comma: key
                    self._skip_ws()
                    if self.pos >= self.n:
                        raise JSONError("unexpected end of input", self.n)
                    if self.s[self.pos] == '"':
                        frame[3] = self._parse_string()
                        frame[2] = 3
                    else:
                        raise JSONError("expected string key", self.pos)

    # ---- helpers ----

    def _skip_ws(self):
        s = self.s
        n = self.n
        p = self.pos
        while p < n and s[p] in ' \t\n\r':
            p += 1
        self.pos = p

    def _parse_value_or_open(self):
        """Return a simple value, or push a container and return _UNSET."""
        self._skip_ws()
        if self.pos >= self.n:
            raise JSONError("unexpected end of input", self.n)
        ch = self.s[self.pos]
        if ch == '[':
            if len(self.stack) >= 500:
                raise JSONError("depth exceeded", self.pos)
            self.pos += 1
            self.stack.append([0, [], 0, None])
            return _UNSET
        if ch == '{':
            if len(self.stack) >= 500:
                raise JSONError("depth exceeded", self.pos)
            self.pos += 1
            self.stack.append([1, {}, 0, None])
            return _UNSET
        return self._parse_simple()

    def _parse_simple(self):
        ch = self.s[self.pos]
        if ch == '"':
            return self._parse_string()
        if ch == 't':
            return self._parse_literal('true', True)
        if ch == 'f':
            return self._parse_literal('false', False)
        if ch == 'n':
            return self._parse_literal('null', None)
        if ch == '-' or ('0' <= ch <= '9'):
            return self._parse_number()
        raise JSONError("unexpected character", self.pos)

    def _parse_literal(self, lit, val):
        s = self.s
        n = self.n
        p = self.pos
        for i in range(len(lit)):
            if p + i >= n:
                raise JSONError("unexpected end of input", n)
            if s[p + i] != lit[i]:
                raise JSONError("invalid literal", p + i)
        self.pos = p + len(lit)
        return val

    def _parse_number(self):
        s = self.s
        n = self.n
        p = self.pos
        start = p
        is_float = False

        # optional sign
        if s[p] == '-':
            p += 1

        # integer part
        if p >= n:
            raise JSONError("unexpected end of input", n)
        ch = s[p]
        if ch == '0':
            p += 1
        elif '1' <= ch <= '9':
            p += 1
            while p < n and '0' <= s[p] <= '9':
                p += 1
        else:
            raise JSONError("invalid number", p)

        # fraction
        if p < n and s[p] == '.':
            is_float = True
            p += 1
            if p >= n:
                raise JSONError("unexpected end of input", n)
            if not ('0' <= s[p] <= '9'):
                raise JSONError("invalid number", p)
            while p < n and '0' <= s[p] <= '9':
                p += 1

        # exponent
        if p < n and (s[p] == 'e' or s[p] == 'E'):
            is_float = True
            p += 1
            if p < n and (s[p] == '+' or s[p] == '-'):
                p += 1
            if p >= n:
                raise JSONError("unexpected end of input", n)
            if not ('0' <= s[p] <= '9'):
                raise JSONError("invalid number", p)
            while p < n and '0' <= s[p] <= '9':
                p += 1

        self.pos = p
        text = s[start:p]
        if is_float:
            return float(text)
        return int(text)

    def _parse_string(self):
        s = self.s
        n = self.n
        self.pos += 1  # skip opening "
        chars: list = []

        while True:
            if self.pos >= n:
                raise JSONError("unexpected end of input", n)
            ch = s[self.pos]

            if ch == '"':
                self.pos += 1
                return ''.join(chars)

            if ch == '\\':
                self.pos += 1
                if self.pos >= n:
                    raise JSONError("unexpected end of input", n)
                esc = s[self.pos]

                if esc == '"':
                    chars.append('"');    self.pos += 1
                elif esc == '\\':
                    chars.append('\\');   self.pos += 1
                elif esc == '/':
                    chars.append('/');    self.pos += 1
                elif esc == 'b':
                    chars.append('\b');   self.pos += 1
                elif esc == 'f':
                    chars.append('\f');   self.pos += 1
                elif esc == 'n':
                    chars.append('\n');   self.pos += 1
                elif esc == 'r':
                    chars.append('\r');   self.pos += 1
                elif esc == 't':
                    chars.append('\t');   self.pos += 1
                elif esc == 'u':
                    self.pos += 1
                    if self.pos + 4 > n:
                        raise JSONError("unexpected end of input", n)
                    h = s[self.pos:self.pos + 4]
                    for i in range(4):
                        c = h[i]
                        if not ('0' <= c <= '9' or 'a' <= c <= 'f' or 'A' <= c <= 'F'):
                            raise JSONError("invalid unicode escape", self.pos + i)
                    code = int(h, 16)
                    self.pos += 4

                    if 0xD800 <= code <= 0xDBFF:
                        # peek for an immediately-following low-surrogate escape
                        if (self.pos + 6 <= n
                                and s[self.pos] == '\\'
                                and s[self.pos + 1] == 'u'):
                            h2 = s[self.pos + 2:self.pos + 6]
                            ok = True
                            for c in h2:
                                if not ('0' <= c <= '9' or 'a' <= c <= 'f' or 'A' <= c <= 'F'):
                                    ok = False
                                    break
                            if ok:
                                code2 = int(h2, 16)
                                if 0xDC00 <= code2 <= 0xDFFF:
                                    combined = (0x10000
                                                + ((code - 0xD800) << 10)
                                                + (code2 - 0xDC00))
                                    chars.append(chr(combined))
                                    self.pos += 6
                                    continue
                        chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    raise JSONError("invalid escape", self.pos)

            elif ord(ch) < 0x20:
                raise JSONError("control character in string", self.pos)

            else:
                chars.append(ch)
                self.pos += 1


def loads(s: str):
    """Parse a JSON document from *s* (strict RFC 8259)."""
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}")
    return _Parser(s).parse()
