import re

class JSONError(ValueError):
    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(f"{message} (position {pos})")

_STR_SCAN = re.compile(r'["\\\x00-\x1f]')
_SIMPLE_ESC = {
    '"': '"', '\\': '\\', '/': '/',
    'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t',
}
_HEX_SET = frozenset('0123456789abcdefABCDEF')


def _parse_string(s, i, n):
    i += 1  # skip opening "
    parts = []
    while True:
        m = _STR_SCAN.search(s, i)
        if m is None:
            raise JSONError("Unterminated string", n)
        j = m.start()
        if j > i:
            parts.append(s[i:j])
        c = s[j]
        if c == '"':
            return ''.join(parts), j + 1
        if c == '\\':
            i = j + 1
            if i >= n:
                raise JSONError("Unexpected end of input", n)
            c2 = s[i]
            if c2 in _SIMPLE_ESC:
                parts.append(_SIMPLE_ESC[c2])
                i += 1
            elif c2 == 'u':
                i += 1
                for k in range(4):
                    if i + k >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i + k] not in _HEX_SET:
                        raise JSONError("Invalid unicode escape", i + k)
                code = int(s[i:i + 4], 16)
                i += 4
                if 0xD800 <= code <= 0xDBFF:
                    if (i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u'
                            and s[i + 2] in _HEX_SET and s[i + 3] in _HEX_SET
                            and s[i + 4] in _HEX_SET and s[i + 5] in _HEX_SET):
                        lo = int(s[i + 2:i + 6], 16)
                        if 0xDC00 <= lo <= 0xDFFF:
                            parts.append(chr(0x10000 + ((code - 0xD800) << 10) + (lo - 0xDC00)))
                            i += 6
                            continue
                    parts.append(chr(code))
                else:
                    parts.append(chr(code))
            else:
                raise JSONError("Invalid escape", i)
        else:
            raise JSONError("Control character in string", j)


def _parse_number(s, i, n):
    start = i
    if s[i] == '-':
        i += 1
    if i >= n:
        raise JSONError("Unexpected end of input", n)
    c = s[i]
    if c == '0':
        i += 1
    elif '1' <= c <= '9':
        i += 1
        while i < n and '0' <= s[i] <= '9':
            i += 1
    else:
        raise JSONError("Invalid number", i)
    is_float = False
    if i < n and s[i] == '.':
        is_float = True
        i += 1
        if i >= n:
            raise JSONError("Unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("Invalid number", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1
    if i < n and s[i] in 'eE':
        is_float = True
        i += 1
        if i < n and s[i] in '+-':
            i += 1
        if i >= n:
            raise JSONError("Unexpected end of input", n)
        if not ('0' <= s[i] <= '9'):
            raise JSONError("Invalid number", i)
        while i < n and '0' <= s[i] <= '9':
            i += 1
    text = s[start:i]
    if is_float:
        return float(text), i
    return int(text), i


def _match_lit(s, i, n, lit):
    for j in range(len(lit)):
        if i + j >= n:
            raise JSONError("Unexpected end of input", n)
        if s[i + j] != lit[j]:
            raise JSONError("Invalid literal", i + j)
    return i + len(lit)


def loads(s):
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__}")

    n = len(s)
    i = 0
    depth = 0
    MAX_DEPTH = 500

    # stack entries: [is_obj, container, state, key]
    # array states: 0=expect value or ], 1=expect , or ], 2=expect value
    # obj states: 0=expect " or }, 1=expect :, 2=expect value, 3=expect , or }, 4=expect "
    stack = []
    value = None
    have_value = False

    while True:
        # skip whitespace
        while i < n and s[i] in ' \t\n\r':
            i += 1

        # deliver a completed value to its parent container
        if have_value:
            if not stack:
                if i < n:
                    raise JSONError("Extra data", i)
                return value
            e = stack[-1]
            if e[0] == 0:
                e[1].append(value)
                e[2] = 1
            else:
                e[1][e[3]] = value
                e[2] = 3
            have_value = False
            continue

        # determine what the current context expects
        if not stack:
            pass  # top-level: fall through to value parsing
        else:
            e = stack[-1]
            if e[0] == 0:  # array
                st = e[2]
                if st == 0:
                    if i >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i] == ']':
                        stack.pop()
                        value = e[1]
                        have_value = True
                        depth -= 1
                        continue
                elif st == 1:
                    if i >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i] == ',':
                        i += 1
                        e[2] = 2
                        continue
                    if s[i] == ']':
                        stack.pop()
                        value = e[1]
                        have_value = True
                        depth -= 1
                        continue
                    raise JSONError("Expected ',' or ']'", i)
                else:  # st == 2
                    if i >= n:
                        raise JSONError("Unexpected end of input", n)
            else:  # object
                st = e[2]
                if st == 0:
                    if i >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i] == '}':
                        stack.pop()
                        value = e[1]
                        have_value = True
                        depth -= 1
                        continue
                    if s[i] == '"':
                        e[3], i = _parse_string(s, i, n)
                        e[2] = 1
                        continue
                    raise JSONError("Expected '\"' or '}'", i)
                elif st == 1:
                    if i >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i] == ':':
                        i += 1
                        e[2] = 2
                        continue
                    raise JSONError("Expected ':'", i)
                elif st == 2:
                    if i >= n:
                        raise JSONError("Unexpected end of input", n)
                elif st == 3:
                    if i >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i] == ',':
                        i += 1
                        e[2] = 4
                        continue
                    if s[i] == '}':
                        stack.pop()
                        value = e[1]
                        have_value = True
                        depth -= 1
                        continue
                    raise JSONError("Expected ',' or '}'", i)
                else:  # st == 4
                    if i >= n:
                        raise JSONError("Unexpected end of input", n)
                    if s[i] == '"':
                        e[3], i = _parse_string(s, i, n)
                        e[2] = 1
                        continue
                    raise JSONError("Expected '\"'", i)

        # ---- parse a value ----
        if i >= n:
            raise JSONError("Unexpected end of input", n)
        c = s[i]
        if c == '"':
            value, i = _parse_string(s, i, n)
            have_value = True
        elif c == '[':
            if depth >= MAX_DEPTH:
                raise JSONError("Maximum nesting depth exceeded", i)
            depth += 1
            stack.append([0, [], 0, None])
            i += 1
        elif c == '{':
            if depth >= MAX_DEPTH:
                raise JSONError("Maximum nesting depth exceeded", i)
            depth += 1
            stack.append([1, {}, 0, None])
            i += 1
        elif c == 't':
            i = _match_lit(s, i, n, 'true')
            value = True
            have_value = True
        elif c == 'f':
            i = _match_lit(s, i, n, 'false')
            value = False
            have_value = True
        elif c == 'n':
            i = _match_lit(s, i, n, 'null')
            value = None
            have_value = True
        elif c == '-' or ('0' <= c <= '9'):
            value, i = _parse_number(s, i, n)
            have_value = True
        else:
            raise JSONError("Unexpected character", i)
