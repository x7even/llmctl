"""Strict RFC 8259 JSON parser (standard library only, no json/simplejson/ast/eval/exec/compile)."""


class JSONError(ValueError):
    """Raised when JSON parsing fails."""

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    """Parse a JSON document from *s* and return the corresponding Python object."""
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}"
        )
    return _Parser(s).parse()


class _Parser:
    __slots__ = ("s", "pos", "depth", "n")

    def __init__(self, s: str) -> None:
        self.s = s
        self.pos = 0
        self.depth = 0
        self.n = len(s)

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _error(self, pos: int):
        raise JSONError("JSON parse error", pos)

    def _skip_ws(self) -> None:
        s = self.s
        n = self.n
        p = self.pos
        while p < n:
            c = s[p]
            if c == " " or c == "\t" or c == "\n" or c == "\r":
                p += 1
            else:
                break
        self.pos = p

    # ------------------------------------------------------------------ #
    #  Top-level entry (iterative to avoid RecursionError)
    # ------------------------------------------------------------------ #

    def parse(self):
        self._skip_ws()
        if self.pos >= self.n:
            self._error(self.pos)

        # stack entries: (is_object: bool, container, key)
        stack: list = []
        state = "VALUE"
        value = None
        s = self.s
        n = self.n

        while True:
            # ---- expecting a JSON value ---- #
            if state == "VALUE":
                self._skip_ws()
                if self.pos >= n:
                    self._error(self.pos)
                c = s[self.pos]
                if c == "{":
                    self.pos += 1
                    self.depth += 1
                    if self.depth > 500:
                        self._error(self.pos - 1)
                    stack.append((True, {}, None))
                    state = "OBJ_FIRST"
                elif c == "[":
                    self.pos += 1
                    self.depth += 1
                    if self.depth > 500:
                        self._error(self.pos - 1)
                    stack.append((False, [], None))
                    state = "ARR_FIRST"
                elif c == '"':
                    value = self._parse_string()
                    state = "ASSIGN"
                elif c == "t":
                    value = self._parse_literal("true", True)
                    state = "ASSIGN"
                elif c == "f":
                    value = self._parse_literal("false", False)
                    state = "ASSIGN"
                elif c == "n":
                    value = self._parse_literal("null", None)
                    state = "ASSIGN"
                elif c == "-" or ("0" <= c <= "9"):
                    value = self._parse_number()
                    state = "ASSIGN"
                else:
                    self._error(self.pos)

            # ---- assign completed value to enclosing container ---- #
            elif state == "ASSIGN":
                if not stack:
                    state = "TOP_DONE"
                else:
                    is_obj, container, key = stack[-1]
                    if is_obj:
                        container[key] = value
                        state = "OBJ_NEXT"
                    else:
                        container.append(value)
                        state = "ARR_NEXT"

            # ---- just opened '[', expect value or ']' ---- #
            elif state == "ARR_FIRST":
                self._skip_ws()
                if self.pos >= n:
                    self._error(self.pos)
                if s[self.pos] == "]":
                    self.pos += 1
                    value = stack.pop()[1]
                    self.depth -= 1
                    state = "ASSIGN"
                else:
                    state = "VALUE"

            # ---- after a value inside '[', expect ',' or ']' ---- #
            elif state == "ARR_NEXT":
                self._skip_ws()
                if self.pos >= n:
                    self._error(self.pos)
                c = s[self.pos]
                if c == "]":
                    self.pos += 1
                    value = stack.pop()[1]
                    self.depth -= 1
                    state = "ASSIGN"
                elif c == ",":
                    self.pos += 1
                    state = "VALUE"
                else:
                    self._error(self.pos)

            # ---- just opened '{', expect key or '}' ---- #
            elif state == "OBJ_FIRST":
                self._skip_ws()
                if self.pos >= n:
                    self._error(self.pos)
                c = s[self.pos]
                if c == "}":
                    self.pos += 1
                    value = stack.pop()[1]
                    self.depth -= 1
                    state = "ASSIGN"
                elif c == '"':
                    key = self._parse_string()
                    stack[-1] = (True, stack[-1][1], key)
                    state = "OBJ_COLON"
                else:
                    self._error(self.pos)

            # ---- after key, expect ':' ---- #
            elif state == "OBJ_COLON":
                self._skip_ws()
                if self.pos >= n:
                    self._error(self.pos)
                if s[self.pos] == ":":
                    self.pos += 1
                    state = "VALUE"
                else:
                    self._error(self.pos)

            # ---- after value inside '{', expect ',' or '}' ---- #
            elif state == "OBJ_NEXT":
                self._skip_ws()
                if self.pos >= n:
                    self._error(self.pos)
                c = s[self.pos]
                if c == "}":
                    self.pos += 1
                    value = stack.pop()[1]
                    self.depth -= 1
                    state = "ASSIGN"
                elif c == ",":
                    self.pos += 1
                    state = "OBJ_KEY"
                else:
                    self._error(self.pos)

            # ---- after ',' inside '{', expect key ---- #
            elif state == "OBJ_KEY":
                self._skip_ws()
                if self.pos >= n:
                    self._error(self.pos)
                c = s[self.pos]
                if c == '"':
                    key = self._parse_string()
                    stack[-1] = (True, stack[-1][1], key)
                    state = "OBJ_COLON"
                else:
                    self._error(self.pos)

            # ---- top-level value done, expect only whitespace ---- #
            elif state == "TOP_DONE":
                self._skip_ws()
                if self.pos < n:
                    self._error(self.pos)
                return value

    # ------------------------------------------------------------------ #
    #  String
    # ------------------------------------------------------------------ #

    def _parse_string(self) -> str:
        s = self.s
        n = self.n
        self.pos += 1  # skip opening "
        parts: list = []

        while True:
            if self.pos >= n:
                self._error(self.pos)

            # fast scan: consume runs of "safe" characters
            start = self.pos
            while self.pos < n:
                c = s[self.pos]
                if c == '"' or c == "\\" or c < " ":
                    break
                self.pos += 1
            if self.pos > start:
                parts.append(s[start:self.pos])

            if self.pos >= n:
                self._error(self.pos)

            c = s[self.pos]
            if c == '"':
                self.pos += 1
                break
            elif c == "\\":
                self.pos += 1
                if self.pos >= n:
                    self._error(self.pos)
                e = s[self.pos]
                if e == '"':
                    parts.append('"')
                    self.pos += 1
                elif e == "\\":
                    parts.append("\\")
                    self.pos += 1
                elif e == "/":
                    parts.append("/")
                    self.pos += 1
                elif e == "b":
                    parts.append("\b")
                    self.pos += 1
                elif e == "f":
                    parts.append("\f")
                    self.pos += 1
                elif e == "n":
                    parts.append("\n")
                    self.pos += 1
                elif e == "r":
                    parts.append("\r")
                    self.pos += 1
                elif e == "t":
                    parts.append("\t")
                    self.pos += 1
                elif e == "u":
                    self._parse_unicode_escape(parts)
                else:
                    self._error(self.pos)
            else:
                # raw control character (c < 0x20)
                self._error(self.pos)

        return "".join(parts)

    # ------------------------------------------------------------------ #
    #  \uXXXX with surrogate-pair handling
    # ------------------------------------------------------------------ #

    def _parse_unicode_escape(self, parts: list) -> None:
        s = self.s
        n = self.n
        # self.pos currently points to 'u'; advance past it
        self.pos += 1
        start = self.pos

        if start + 4 > n:
            self._error(n)

        # validate exactly four ASCII hex digits
        for i in range(4):
            c = s[start + i]
            if not (("0" <= c <= "9") or ("a" <= c <= "f") or ("A" <= c <= "F")):
                self._error(start + i)

        hex_str = s[start : start + 4]
        self.pos = start + 4
        cp = int(hex_str, 16)

        if 0xD800 <= cp <= 0xDBFF:
            # high surrogate – look for an immediately-following low-surrogate escape
            if (
                self.pos + 6 <= n
                and s[self.pos] == "\\"
                and s[self.pos + 1] == "u"
            ):
                lo_start = self.pos + 2
                # validate the four hex digits of the candidate low surrogate
                valid = True
                for i in range(4):
                    c = s[lo_start + i]
                    if not (("0" <= c <= "9") or ("a" <= c <= "f") or ("A" <= c <= "F")):
                        valid = False
                        break
                if valid:
                    lo_cp = int(s[lo_start : lo_start + 4], 16)
                    if 0xDC00 <= lo_cp <= 0xDFFF:
                        combined = 0x10000 + ((cp - 0xD800) << 10) + (lo_cp - 0xDC00)
                        parts.append(chr(combined))
                        self.pos = lo_start + 4
                        return
            # unpaired high surrogate – keep as lone code-point
            parts.append(chr(cp))
        elif 0xDC00 <= cp <= 0xDFFF:
            # lone low surrogate
            parts.append(chr(cp))
        else:
            parts.append(chr(cp))

    # ------------------------------------------------------------------ #
    #  Number
    # ------------------------------------------------------------------ #

    def _parse_number(self):
        s = self.s
        n = self.n
        start = self.pos

        # optional leading '-'
        if s[self.pos] == "-":
            self.pos += 1
            if self.pos >= n:
                self._error(self.pos)

        # integer part: 0 | [1-9][0-9]*
        c = s[self.pos]
        if c == "0":
            self.pos += 1
        elif "1" <= c <= "9":
            self.pos += 1
            while self.pos < n and "0" <= s[self.pos] <= "9":
                self.pos += 1
        else:
            self._error(self.pos)

        is_float = False

        # optional fraction: '.' [0-9]+
        if self.pos < n and s[self.pos] == ".":
            is_float = True
            self.pos += 1
            if self.pos >= n:
                self._error(self.pos)
            if not ("0" <= s[self.pos] <= "9"):
                self._error(self.pos)
            while self.pos < n and "0" <= s[self.pos] <= "9":
                self.pos += 1

        # optional exponent: [eE] [+-]? [0-9]+
        if self.pos < n and (s[self.pos] == "e" or s[self.pos] == "E"):
            is_float = True
            self.pos += 1
            if self.pos < n and (s[self.pos] == "+" or s[self.pos] == "-"):
                self.pos += 1
            if self.pos >= n:
                self._error(self.pos)
            if not ("0" <= s[self.pos] <= "9"):
                self._error(self.pos)
            while self.pos < n and "0" <= s[self.pos] <= "9":
                self.pos += 1

        text = s[start : self.pos]
        if is_float:
            return float(text)
        return int(text)

    # ------------------------------------------------------------------ #
    #  true / false / null
    # ------------------------------------------------------------------ #

    def _parse_literal(self, expected: str, value):
        s = self.s
        n = self.n
        for i in range(len(expected)):
            if self.pos >= n:
                self._error(self.pos)
            if s[self.pos] != expected[i]:
                self._error(self.pos)
            self.pos += 1
        return value
