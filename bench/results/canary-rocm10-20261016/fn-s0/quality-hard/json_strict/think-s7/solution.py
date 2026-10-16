import re

_STR_SPECIAL = re.compile(r'["\\\x00-\x1f]')


class JSONError(ValueError):
    pos: int

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError("the JSON object must be str, not " + type(s).__name__)

    n = len(s)
    i = 0
    depth = 0

    def _err(msg, pos):
        raise JSONError(msg, pos)

    def _ws():
        nonlocal i
        while i < n and s[i] in ' \t\n\r':
            i += 1

    def _hex4():
        nonlocal i
        v = 0
        for _ in range(4):
            if i >= n:
                _err("unexpected end", n)
            c = s[i]
            if '0' <= c <= '9':
                v = v * 16 + ord(c) - 48
            elif 'a' <= c <= 'f':
                v = v * 16 + ord(c) - 87
            elif 'A' <= c <= 'F':
                v = v * 16 + ord(c) - 55
            else:
                _err("invalid hex digit", i)
            i += 1
        return v

    def _string():
        nonlocal i
        i += 1
        start = i
        m = _STR_SPECIAL.search(s, i)
        if m is None:
            _err("unexpected end", n)
        j = m.start()
        if s[j] == '"':
            r = s[start:j]
            i = j + 1
            return r
        parts = [s[start:j]]
        i = j
        while True:
            if i >= n:
                _err("unexpected end", n)
            c = s[i]
            if c == '"':
                i += 1
                break
            if c == '\\':
                i += 1
                if i >= n:
                    _err("unexpected end", n)
                e = s[i]
                if e == '"':
                    parts.append('"'); i += 1
                elif e == '\\':
                    parts.append('\\'); i += 1
                elif e == '/':
                    parts.append('/'); i += 1
                elif e == 'b':
                    parts.append('\b'); i += 1
                elif e == 'f':
                    parts.append('\f'); i += 1
                elif e == 'n':
                    parts.append('\n'); i += 1
                elif e == 'r':
                    parts.append('\r'); i += 1
                elif e == 't':
                    parts.append('\t'); i += 1
                elif e == 'u':
                    i += 1
                    cp = _hex4()
                    if 0xD800 <= cp <= 0xDBFF:
                        if i + 1 < n and s[i] == '\\' and s[i + 1] == 'u':
                            sv = i
                            i += 2
                            cp2 = _hex4()
                            if 0xDC00 <= cp2 <= 0xDFFF:
                                parts.append(chr(0x10000 + ((cp - 0xD800) << 10) + (cp2 - 0xDC00)))
                            else:
                                i = sv
                                parts.append(chr(cp))
                        else:
                            parts.append(chr(cp))
                    else:
                        parts.append(chr(cp))
                else:
                    _err("invalid escape", i)
            elif c < '\x20':
                _err("control character in string", i)
            else:
                parts.append(c)
                i += 1
        return ''.join(parts)

    def _number():
        nonlocal i
        start = i
        if s[i] == '-':
            i += 1
            if i >= n:
                _err("unexpected end", n)
        c = s[i]
        if c == '0':
            i += 1
        elif '1' <= c <= '9':
            i += 1
            while i < n and '0' <= s[i] <= '9':
                i += 1
        else:
            _err("expected digit", i)
        isf = False
        if i < n and s[i] == '.':
            isf = True
            i += 1
            if i >= n:
                _err("unexpected end", n)
            if not ('0' <= s[i] <= '9'):
                _err("expected digit", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1
        if i < n and s[i] in 'eE':
            isf = True
            i += 1
            if i < n and s[i] in '+-':
                i += 1
            if i >= n:
                _err("unexpected end", n)
            if not ('0' <= s[i] <= '9'):
                _err("expected digit", i)
            while i < n and '0' <= s[i] <= '9':
                i += 1
        txt = s[start:i]
        return float(txt) if isf else int(txt)

    stack = []
    val = None
    st = 'val'

    while True:
        if st == 'val':
            _ws()
            if i >= n:
                _err("unexpected end", n)
            c = s[i]
            if c == '{':
                i += 1
                depth += 1
                if depth > 500:
                    _err("depth limit exceeded", i - 1)
                stack.append(['o', {}, None])
                st = 'o1'
            elif c == '[':
                i += 1
                depth += 1
                if depth > 500:
                    _err("depth limit exceeded", i - 1)
                stack.append(['a', []])
                st = 'a1'
            elif c == '"':
                val = _string()
                st = 'av'
            elif c == 't':
                for ch in 'true':
                    if i >= n:
                        _err("unexpected end", n)
                    if s[i] != ch:
                        _err("invalid literal", i)
                    i += 1
                val = True
                st = 'av'
            elif c == 'f':
                for ch in 'false':
                    if i >= n:
                        _err("unexpected end", n)
                    if s[i] != ch:
                        _err("invalid literal", i)
                    i += 1
                val = False
                st = 'av'
            elif c == 'n':
                for ch in 'null':
                    if i >= n:
                        _err("unexpected end", n)
                    if s[i] != ch:
                        _err("invalid literal", i)
                    i += 1
                val = None
                st = 'av'
            elif c == '-' or '0' <= c <= '9':
                val = _number()
                st = 'av'
            else:
                _err("unexpected character", i)

        elif st == 'av':
            if not stack:
                _ws()
                if i < n:
                    _err("trailing garbage", i)
                return val
            t = stack[-1]
            if t[0] == 'a':
                t[1].append(val)
                st = 'an'
            else:
                t[1][t[2]] = val
                st = 'on'

        elif st == 'a1':
            _ws()
            if i >= n:
                _err("unexpected end", n)
            if s[i] == ']':
                i += 1
                val = stack.pop()[1]
                depth -= 1
                st = 'av'
            else:
                st = 'val'

        elif st == 'an':
            _ws()
            if i >= n:
                _err("unexpected end", n)
            c = s[i]
            if c == ']':
                i += 1
                val = stack.pop()[1]
                depth -= 1
                st = 'av'
            elif c == ',':
                i += 1
                st = 'val'
            else:
                _err("expected , or ]", i)

        elif st == 'o1':
            _ws()
            if i >= n:
                _err("unexpected end", n)
            if s[i] == '}':
                i += 1
                val = stack.pop()[1]
                depth -= 1
                st = 'av'
            elif s[i] == '"':
                stack[-1][2] = _string()
                st = 'oc'
            else:
                _err("expected key or }", i)

        elif st == 'oc':
            _ws()
            if i >= n:
                _err("unexpected end", n)
            if s[i] == ':':
                i += 1
                st = 'val'
            else:
                _err("expected :", i)

        elif st == 'on':
            _ws()
            if i >= n:
                _err("unexpected end", n)
            c = s[i]
            if c == '}':
                i += 1
                val = stack.pop()[1]
                depth -= 1
                st = 'av'
            elif c == ',':
                i += 1
                st = 'ok'
            else:
                _err("expected , or }", i)

        elif st == 'ok':
            _ws()
            if i >= n:
                _err("unexpected end", n)
            if s[i] == '"':
                stack[-1][2] = _string()
                st = 'oc'
            else:
                _err("expected key", i)
