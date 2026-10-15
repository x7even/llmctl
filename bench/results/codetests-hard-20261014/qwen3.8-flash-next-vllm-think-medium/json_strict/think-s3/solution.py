"""Strict RFC 8259 JSON parser (no json/simplejson/ast/eval/exec/compile)."""


class JSONError(ValueError):
    """Raised when JSON parsing fails."""

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    """Parse a JSON string and return the corresponding Python object."""
    if not isinstance(s, str):
        raise TypeError(
            f"the JSON object must be str, not {type(s).__name__}"
        )
    return _Parser(s).parse()


class _Parser:
    __slots__ = ("s", "pos", "length")

    def __init__(self, s: str) -> None:
        self.s = s
        self.pos = 0
        self.length = len(s)

    # ------------------------------------------------------------------
    # Main iterative parser (no recursion, depth-limited to 500)
    # ------------------------------------------------------------------
    def parse(self):
        s = self.s
        n = self.length
        pos = 0
        state = "value"
        stack = []  # ('array', list) | ('object', dict, key)
        result = None

        while True:
            if state == "value":
                while pos < n and s[pos] in " \t\n\r":
                    pos += 1
                if pos >= n:
                    self.pos = pos
                    raise JSONError("unexpected end of input", pos)
                ch = s[pos]
                if ch == "[":
                    if len(stack) >= 500:
                        self.pos = pos
                        raise JSONError("maximum nesting depth exceeded", pos)
                    pos += 1
                    stack.append(["array", []])
                    state = "arr_first"
                elif ch == "{":
                    if len(stack) >= 500:
                        self.pos = pos
                        raise JSONError("maximum nesting depth exceeded", pos)
                    pos += 1
                    stack.append(["object", {}, None])
                    state = "obj_first"
                elif ch == '"':
                    self.pos = pos
                    result = self._parse_string()
                    pos = self.pos
                    state = "return"
                elif ch == "t":
                    self.pos = pos
                    result = self._parse_literal("true", True)
                    pos = self.pos
                    state = "return"
                elif ch == "f":
                    self.pos = pos
                    result = self._parse_literal("false", False)
                    pos = self.pos
                    state = "return"
                elif ch == "n":
                    self.pos = pos
                    result = self._parse_literal("null", None)
                    pos = self.pos
                    state = "return"
                elif ch == "-" or "0" <= ch <= "9":
                    self.pos = pos
                    result = self._parse_number()
                    pos = self.pos
                    state = "return"
                else:
                    self.pos = pos
                    raise JSONError(f"unexpected character {ch!r}", pos)

            elif state == "return":
                if not stack:
                    while pos < n and s[pos] in " \t\n\r":
                        pos += 1
                    if pos < n:
                        self.pos = pos
                        raise JSONError("trailing characters", pos)
                    self.pos = pos
                    return result
                top = stack[-1]
                if top[0] == "array":
                    top[1].append(result)
                    state = "arr_after"
                else:
                    top[1][top[2]] = result
                    state = "obj_after"

            elif state == "arr_first":
                while pos < n and s[pos] in " \t\n\r":
                    pos += 1
                if pos >= n:
                    self.pos = pos
                    raise JSONError("unexpected end of input", pos)
                if s[pos] == "]":
                    pos += 1
                    result = stack.pop()[1]
                    state = "return"
                else:
                    state = "value"

            elif state == "arr_after":
                while pos < n and s[pos] in " \t\n\r":
                    pos += 1
                if pos >= n:
                    self.pos = pos
                    raise JSONError("unexpected end of input", pos)
                ch = s[pos]
                if ch == "]":
                    pos += 1
                    result = stack.pop()[1]
                    state = "return"
                elif ch == ",":
                    pos += 1
                    state = "value"
                else:
                    self.pos = pos
                    raise JSONError("expected ',' or ']'", pos)

            elif state == "obj_first":
                while pos < n and s[pos] in " \t\n\r":
                    pos += 1
                if pos >= n:
                    self.pos = pos
                    raise JSONError("unexpected end of input", pos)
                if s[pos] == "}":
                    pos += 1
                    result = stack.pop()[1]
                    state = "return"
                elif s[pos] == '"':
                    self.pos = pos
                    key = self._parse_string()
                    pos = self.pos
                    stack[-1][2] = key
                    state = "obj_colon"
                else:
                    self.pos = pos
                    raise JSONError("expected '\"' or '}'", pos)

            elif state == "obj_colon":
                while pos < n and s[pos] in " \t\n\r":
                    pos += 1
                if pos >= n:
                    self.pos = pos
                    raise JSONError("unexpected end of input", pos)
                if s[pos] == ":":
                    pos += 1
                    state = "value"
                else:
                    self.pos = pos
                    raise JSONError("expected ':'", pos)

            elif state == "obj_after":
                while pos < n and s[pos] in " \t\n\r":
                    pos += 1
                if pos >= n:
                    self.pos = pos
                    raise JSONError("unexpected end of input", pos)
                ch = s[pos]
                if ch == "}":
                    pos += 1
                    result = stack.pop()[1]
                    state = "return"
                elif ch == ",":
                    pos += 1
                    while pos < n and s[pos] in " \t\n\r":
                        pos += 1
                    if pos >= n:
                        self.pos = pos
                        raise JSONError("unexpected end of input", pos)
                    if s[pos] == '"':
                        self.pos = pos
                        key = self._parse_string()
                        pos = self.pos
                        stack[-1][2] = key
                        state = "obj_colon"
                    else:
                        self.pos = pos
                        raise JSONError("expected '\"'", pos)
                else:
                    self.pos = pos
                    raise JSONError("expected ',' or '}'", pos)

    # ------------------------------------------------------------------
    # String
    # ------------------------------------------------------------------
    def _parse_string(self):
        s = self.s
        n = self.length
        pos = self.pos  # points at opening '"'
        pos += 1
        chars = []

        while True:
            if pos >= n:
                self.pos = pos
                raise JSONError("unterminated string", pos)
            ch = s[pos]
            if ch == '"':
                pos += 1
                self.pos = pos
                return "".join(chars)
            elif ch == "\\":
                pos += 1
                if pos >= n:
                    self.pos = pos
                    raise JSONError("unterminated escape", pos)
                esc = s[pos]
                if esc == '"':
                    chars.append('"')
                    pos += 1
                elif esc == "\\":
                    chars.append("\\")
                    pos += 1
                elif esc == "/":
                    chars.append("/")
                    pos += 1
                elif esc == "b":
                    chars.append("\b")
                    pos += 1
                elif esc == "f":
                    chars.append("\f")
                    pos += 1
                elif esc == "n":
                    chars.append("\n")
                    pos += 1
                elif esc == "r":
                    chars.append("\r")
                    pos += 1
                elif esc == "t":
                    chars.append("\t")
                    pos += 1
                elif esc == "u":
                    pos += 1  # skip 'u'
                    # parse exactly 4 ASCII hex digits
                    code = 0
                    for _ in range(4):
                        if pos >= n:
                            self.pos = pos
                            raise JSONError(
                                "unexpected end of input in \\u escape", pos
                            )
                        c = s[pos]
                        if "0" <= c <= "9":
                            d = ord(c) - 48
                        elif "a" <= c <= "f":
                            d = ord(c) - 87
                        elif "A" <= c <= "F":
                            d = ord(c) - 55
                        else:
                            self.pos = pos
                            raise JSONError("invalid hex digit", pos)
                        code = code * 16 + d
                        pos += 1
                    # surrogate handling
                    if 0xD800 <= code <= 0xDBFF:
                        # high surrogate – look for immediately following low
                        if (
                            pos + 6 <= n
                            and s[pos] == "\\"
                            and s[pos + 1] == "u"
                        ):
                            # validate next 4 chars are hex
                            ok = True
                            for i in range(4):
                                c2 = s[pos + 2 + i]
                                if not (
                                    "0" <= c2 <= "9"
                                    or "a" <= c2 <= "f"
                                    or "A" <= c2 <= "F"
                                ):
                                    ok = False
                                    break
                            if ok:
                                lo = (
                                    (ord(s[pos + 2]) - 48 if s[pos + 2] <= "9"
                                     else (ord(s[pos + 2]) - 87 if s[pos + 2] <= "f"
                                           else ord(s[pos + 2]) - 55)) << 12
                                    | (ord(s[pos + 3]) - 48 if s[pos + 3] <= "9"
                                       else (ord(s[pos + 3]) - 87 if s[pos + 3] <= "f"
                                             else ord(s[pos + 3]) - 55)) << 8
                                    | (ord(s[pos + 4]) - 48 if s[pos + 4] <= "9"
                                       else (ord(s[pos + 4]) - 87 if s[pos + 4] <= "f"
                                             else ord(s[pos + 4]) - 55)) << 4
                                    | (ord(s[pos + 5]) - 48 if s[pos + 5] <= "9"
                                       else (ord(s[pos + 5]) - 87 if s[pos + 5] <= "f"
                                             else ord(s[pos + 5]) - 55))
                                )
                                if 0xDC00 <= lo <= 0xDFFF:
                                    combined = (
                                        0x10000
                                        + ((code - 0xD800) << 10)
                                        + (lo - 0xDC00)
                                    )
                                    chars.append(chr(combined))
                                else:
                                    chars.append(chr(code))
                                    chars.append(chr(lo))
                                pos += 6
                            else:
                                chars.append(chr(code))
                        else:
                            chars.append(chr(code))
                    else:
                        chars.append(chr(code))
                else:
                    self.pos = pos
                    raise JSONError(f"invalid escape '\\{esc}'", pos)
            elif ord(ch) < 0x20:
                self.pos = pos
                raise JSONError("control character in string", pos)
            else:
                chars.append(ch)
                pos += 1

    # ------------------------------------------------------------------
    # Number
    # ------------------------------------------------------------------
    def _parse_number(self):
        s = self.s
        n = self.length
        pos = self.pos
        start = pos
        is_float = False

        # optional minus
        if s[pos] == "-":
            pos += 1

        # integer part: 0 | [1-9][0-9]*
        if pos >= n:
            self.pos = pos
            raise JSONError("expected digit", pos)
        ch = s[pos]
        if ch == "0":
            pos += 1
        elif "1" <= ch <= "9":
            pos += 1
            while pos < n and "0" <= s[pos] <= "9":
                pos += 1
        else:
            self.pos = pos
            raise JSONError("expected digit", pos)

        # fraction: .[0-9]+
        if pos < n and s[pos] == ".":
            is_float = True
            pos += 1
            if pos >= n:
                self.pos = pos
                raise JSONError("expected digit after '.'", pos)
            if not ("0" <= s[pos] <= "9"):
                self.pos = pos
                raise JSONError("expected digit after '.'", pos)
            while pos < n and "0" <= s[pos] <= "9":
                pos += 1

        # exponent: [eE][+-]?[0-9]+
        if pos < n and (s[pos] == "e" or s[pos] == "E"):
            is_float = True
            pos += 1
            if pos < n and (s[pos] == "+" or s[pos] == "-"):
                pos += 1
            if pos >= n:
                self.pos = pos
                raise JSONError("expected digit in exponent", pos)
            if not ("0" <= s[pos] <= "9"):
                self.pos = pos
                raise JSONError("expected digit in exponent", pos)
            while pos < n and "0" <= s[pos] <= "9":
                pos += 1

        text = s[start:pos]
        self.pos = pos
        if is_float:
            return float(text)
        return int(text)

    # ------------------------------------------------------------------
    # Literal (true / false / null)
    # ------------------------------------------------------------------
    def _parse_literal(self, expected, value):
        s = self.s
        n = self.length
        pos = self.pos
        for c in expected:
            if pos >= n:
                self.pos = pos
                raise JSONError("unexpected end of input", pos)
            if s[pos] != c:
                self.pos = pos
                raise JSONError(f"expected '{expected}'", pos)
            pos += 1
        self.pos = pos
        return value
