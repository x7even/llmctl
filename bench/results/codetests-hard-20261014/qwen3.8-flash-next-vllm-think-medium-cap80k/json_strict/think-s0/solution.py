"""Strict RFC 8259 JSON parser — hand-written, no json/ast/eval/exec/compile."""

class JSONError(ValueError):
    """Raised for every JSON parse failure. Stores the byte offset in .pos."""
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    """Parse a JSON document from a string. Strict RFC 8259."""
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}"
        )
    return _Parser(s).parse()


# ─── internal parser ──────────────────────────────────────────────────────────

_HEX = frozenset('0123456789abcdefABCDEF')
_WS  = frozenset(' \t\n\r')


class _Parser:
    __slots__ = ('s', 'pos', 'n')

    def __init__(self, s: str):
        self.s = s
        self.pos = 0
        self.n = len(s)

    # ── helpers ────────────────────────────────────────────────────────────

    def _err(self, msg: str, pos: int):
        raise JSONError(msg, pos)

    def _skip_ws(self):
        s, n = self.s, self.n
        pos = self.pos
        while pos < n and s[pos] in _WS:
            pos += 1
        self.pos = pos

    def _check_trailing(self):
        self._skip_ws()
        if self.pos < self.n:
            self._err("trailing characters", self.pos)

    def _expect_literal(self, lit: str):
        s, n, pos = self.s, self.n, self.pos
        end = pos + len(lit)
        if end > n:
            remaining = s[pos:]
            if lit.startswith(remaining):
                self._err("unexpected end of input", n)
            for i in range(len(remaining)):
                if remaining[i] != lit[i]:
                    self._err("invalid literal", pos + i)
            self._err("unexpected end of input", n)  # unreachable
        if s[pos:end] != lit:
            for i in range(len(lit)):
                if s[pos + i] != lit[i]:
                    self._err("invalid literal", pos + i)
        self.pos = end

    # ── number ─────────────────────────────────────────────────────────────

    def _parse_number(self):
        s, n = self.s, self.n
        start = self.pos

        if s[self.pos] == '-':
            self.pos += 1

        if self.pos >= n:
            self._err("unexpected end of input", n)

        c = s[self.pos]
        if c == '0':
            self.pos += 1
        elif '1' <= c <= '9':
            self.pos += 1
            while self.pos < n and '0' <= s[self.pos] <= '9':
                self.pos += 1
        else:
            self._err("expected digit", self.pos)

        is_float = False

        # fraction
        if self.pos < n and s[self.pos] == '.':
            is_float = True
            self.pos += 1
            if self.pos >= n:
                self._err("unexpected end of input", n)
            if not ('0' <= s[self.pos] <= '9'):
                self._err("expected digit", self.pos)
            while self.pos < n and '0' <= s[self.pos] <= '9':
                self.pos += 1

        # exponent
        if self.pos < n and s[self.pos] in 'eE':
            is_float = True
            self.pos += 1
            if self.pos < n and s[self.pos] in '+-':
                self.pos += 1
            if self.pos >= n:
                self._err("unexpected end of input", n)
            if not ('0' <= s[self.pos] <= '9'):
                self._err("expected digit", self.pos)
            while self.pos < n and '0' <= s[self.pos] <= '9':
                self.pos += 1

        text = s[start:self.pos]
        return float(text) if is_float else int(text)

    # ── string ─────────────────────────────────────────────────────────────

    def _parse_string(self):
        s, n = self.s, self.n
        pos = self.pos + 1  # skip opening "
        parts: list[str] = []
        run_start = pos

        while pos < n:
            c = s[pos]

            if c == '"':
                if run_start < pos:
                    parts.append(s[run_start:pos])
                self.pos = pos + 1
                return ''.join(parts)

            if c == '\\':
                if run_start < pos:
                    parts.append(s[run_start:pos])
                pos += 1
                if pos >= n:
                    self._err("unexpected end of input", n)
                esc = s[pos]

                if esc == '"':
                    parts.append('"'); pos += 1
                elif esc == '\\':
                    parts.append('\\'); pos += 1
                elif esc == '/':
                    parts.append('/'); pos += 1
                elif esc == 'b':
                    parts.append('\b'); pos += 1
                elif esc == 'f':
                    parts.append('\f'); pos += 1
                elif esc == 'n':
                    parts.append('\n'); pos += 1
                elif esc == 'r':
                    parts.append('\r'); pos += 1
                elif esc == 't':
                    parts.append('\t'); pos += 1
                elif esc == 'u':
                    pos += 1
                    if pos + 4 > n:
                        self._err("unexpected end of input", n)
                    for i in range(4):
                        if s[pos + i] not in _HEX:
                            self._err("invalid hex digit", pos + i)
                    code = int(s[pos:pos + 4], 16)
                    pos += 4

                    if 0xD800 <= code <= 0xDBFF:
                        # high surrogate – try to combine with next \uXXXX
                        if (pos + 6 <= n
                                and s[pos] == '\\'
                                and s[pos + 1] == 'u'):
                            h = s[pos + 2:pos + 6]
                            ok = True
                            for i in range(4):
                                if h[i] not in _HEX:
                                    ok = False
                                    break
                            if ok:
                                lo = int(h, 16)
                                if 0xDC00 <= lo <= 0xDFFF:
                                    combined = (0x10000
                                                + ((code - 0xD800) << 10)
                                                + (lo - 0xDC00))
                                    parts.append(chr(combined))
                                    pos += 6
                                    run_start = pos
                                    continue
                        parts.append(chr(code))
                    elif 0xDC00 <= code <= 0xDFFF:
                        parts.append(chr(code))
                    else:
                        parts.append(chr(code))
                    run_start = pos
                else:
                    self._err("invalid escape", pos)
                    # unreachable
                run_start = pos
                continue

            if ord(c) < 0x20:
                self._err("control character in string", pos)

            pos += 1

        self._err("unexpected end of input", n)

    # ── deliver a completed value into the enclosing container ─────────────

    def _deliver(self, value, stack):
        if not stack:
            return None
        frame = stack[-1]
        if frame[0] == 'array':
            frame[1].append(value)
            return 'array_elem'
        else:
            frame[1][frame[2]] = value
            frame[2] = None
            return 'obj_value'

    # ── main iterative parse loop ──────────────────────────────────────────

    def parse(self):
        s, n = self.s, self.n
        stack: list[list] = []
        depth = 0
        state = 'value'
        result = None

        while True:
            # ── expecting a value ──
            if state == 'value':
                self._skip_ws()
                pos = self.pos
                if pos >= n:
                    self._err("unexpected end of input", n)

                c = s[pos]

                if c == '"':
                    result = self._parse_string()

                elif c == '{':
                    if depth >= 500:
                        self._err("maximum nesting depth exceeded", pos)
                    depth += 1
                    stack.append(['object', {}, None])
                    self.pos = pos + 1
                    self._skip_ws()
                    if self.pos >= n:
                        self._err("unexpected end of input", n)
                    if s[self.pos] == '}':
                        self.pos += 1
                        result = stack[-1][1]
                        stack.pop()
                        depth -= 1
                        state = self._deliver(result, stack)
                        if state is None:
                            self._check_trailing()
                            return result
                    else:
                        state = 'obj_key'
                    continue

                elif c == '[':
                    if depth >= 500:
                        self._err("maximum nesting depth exceeded", pos)
                    depth += 1
                    stack.append(['array', []])
                    self.pos = pos + 1
                    self._skip_ws()
                    if self.pos >= n:
                        self._err("unexpected end of input", n)
                    if s[self.pos] == ']':
                        self.pos += 1
                        result = stack[-1][1]
                        stack.pop()
                        depth -= 1
                        state = self._deliver(result, stack)
                        if state is None:
                            self._check_trailing()
                            return result
                    else:
                        state = 'value'
                    continue

                elif c == 't':
                    self._expect_literal("true")
                    result = True
                elif c == 'f':
                    self._expect_literal("false")
                    result = False
                elif c == 'n':
                    self._expect_literal("null")
                    result = None
                elif c == '-' or ('0' <= c <= '9'):
                    result = self._parse_number()
                else:
                    self._err("unexpected character", pos)

                state = self._deliver(result, stack)
                if state is None:
                    self._check_trailing()
                    return result

            # ── after a value inside an array ──
            elif state == 'array_elem':
                self._skip_ws()
                pos = self.pos
                if pos >= n:
                    self._err("unexpected end of input", n)
                c = s[pos]
                if c == ',':
                    self.pos = pos + 1
                    state = 'value'
                elif c == ']':
                    self.pos = pos + 1
                    result = stack[-1][1]
                    stack.pop()
                    depth -= 1
                    state = self._deliver(result, stack)
                    if state is None:
                        self._check_trailing()
                        return result
                else:
                    self._err("expected ',' or ']'", pos)

            # ── expecting a key (string) in an object ──
            elif state == 'obj_key':
                self._skip_ws()
                pos = self.pos
                if pos >= n:
                    self._err("unexpected end of input", n)
                if s[pos] == '"':
                    key = self._parse_string()
                    stack[-1][2] = key
                    state = 'obj_colon'
                else:
                    self._err("expected string key", pos)

            # ── expecting ':' after a key ──
            elif state == 'obj_colon':
                self._skip_ws()
                pos = self.pos
                if pos >= n:
                    self._err("unexpected end of input", n)
                if s[pos] == ':':
                    self.pos = pos + 1
                    state = 'value'
                else:
                    self._err("expected ':'", pos)

            # ── after a value inside an object ──
            elif state == 'obj_value':
                self._skip_ws()
                pos = self.pos
                if pos >= n:
                    self._err("unexpected end of input", n)
                c = s[pos]
                if c == ',':
                    self.pos = pos + 1
                    state = 'obj_key'
                elif c == '}':
                    self.pos = pos + 1
                    result = stack[-1][1]
                    stack.pop()
                    depth -= 1
                    state = self._deliver(result, stack)
                    if state is None:
                        self._check_trailing()
                        return result
                else:
                    self._err("expected ',' or '}'", pos)

        # unreachable
        self._err("unexpected end of input", n)
