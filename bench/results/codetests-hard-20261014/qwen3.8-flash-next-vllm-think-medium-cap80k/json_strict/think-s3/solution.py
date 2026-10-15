import re

class JSONError(ValueError):
    def __init__(self, message, pos):
        super().__init__(message)
        self.pos = pos

_HEX = frozenset('0123456789abcdefABCDEF')
_WS = frozenset(' \t\n\r')
_STR_SPECIAL = re.compile(r'["\\\x00-\x1f]')

def _hex4(s, pos, n):
    if pos + 4 > n:
        raise JSONError("unexpected end of input", n)
    for i in range(4):
        if s[pos + i] not in _HEX:
            raise JSONError("invalid hex digit in escape", pos + i)
    return int(s[pos:pos + 4], 16)

def _parse_str(s, pos, n):
    pos += 1
    parts = []
    while True:
        m = _STR_SPECIAL.search(s, pos)
        if m is None:
            raise JSONError("unterminated string", n)
        if m.start() > pos:
            parts.append(s[pos:m.start()])
        pos = m.start()
        c = s[pos]
        if c == '"':
            pos += 1
            return ''.join(parts), pos
        if c == '\\':
            pos += 1
            if pos >= n:
                raise JSONError("unterminated string", n)
            e = s[pos]
            if e == '"': parts.append('"'); pos += 1
            elif e == '\\': parts.append('\\'); pos += 1
            elif e == '/': parts.append('/'); pos += 1
            elif e == 'b': parts.append('\b'); pos += 1
            elif e == 'f': parts.append('\f'); pos += 1
            elif e == 'n': parts.append('\n'); pos += 1
            elif e == 'r': parts.append('\r'); pos += 1
            elif e == 't': parts.append('\t'); pos += 1
            elif e == 'u':
                pos += 1
                cp = _hex4(s, pos, n)
                pos += 4
                if 0xD800 <= cp <= 0xDBFF:
                    if pos + 1 < n and s[pos] == '\\' and s[pos + 1] == 'u':
                        cp2 = _hex4(s, pos + 2, n)
                        if 0xDC00 <= cp2 <= 0xDFFF:
                            parts.append(chr(0x10000 + ((cp - 0xD800) << 10) + (cp2 - 0xDC00)))
                            pos += 6
                            continue
                        parts.append(chr(cp))
                    else:
                        parts.append(chr(cp))
                else:
                    parts.append(chr(cp))
            else:
                raise JSONError("invalid escape character", pos)
        else:
            raise JSONError("control character in string", pos)

def loads(s):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")

    n = len(s)
    pos = 0

    _VAL, _ARR_START, _ARR_COMMA, _ARR_NEXT = 0, 1, 2, 3
    _OBJ_START, _OBJ_COLON, _OBJ_VAL, _OBJ_COMMA, _OBJ_NEXT, _DONE = 4, 5, 6, 7, 8, 9

    state = _VAL
    stack = []
    result = None

    while True:
        if state == _VAL:
            while pos < n and s[pos] in _WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            c = s[pos]

            if c == '"':
                val, pos = _parse_str(s, pos, n)
            elif c == '[':
                stack.append(('array', []))
                if len(stack) > 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                state = _ARR_START
                continue
            elif c == '{':
                stack.append(('object', {}, [None]))
                if len(stack) > 500:
                    raise JSONError("maximum nesting depth exceeded", pos)
                pos += 1
                state = _OBJ_START
                continue
            elif c == 't':
                for i, ch in enumerate('true'):
                    if pos + i >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[pos + i] != ch:
                        raise JSONError("invalid value", pos + i)
                pos += 4
                val = True
            elif c == 'f':
                for i, ch in enumerate('false'):
                    if pos + i >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[pos + i] != ch:
                        raise JSONError("invalid value", pos + i)
                pos += 5
                val = False
            elif c == 'n':
                for i, ch in enumerate('null'):
                    if pos + i >= n:
                        raise JSONError("unexpected end of input", n)
                    if s[pos + i] != ch:
                        raise JSONError("invalid value", pos + i)
                pos += 4
                val = None
            elif c == '-' or '0' <= c <= '9':
                start = pos
                isf = False
                if s[pos] == '-':
                    pos += 1
                if pos >= n:
                    raise JSONError("unexpected end of input", n)
                if s[pos] == '0':
                    pos += 1
                elif '1' <= s[pos] <= '9':
                    pos += 1
                    while pos < n and '0' <= s[pos] <= '9':
                        pos += 1
                else:
                    raise JSONError("invalid number", pos)
                if pos < n and s[pos] == '.':
                    isf = True
                    pos += 1
                    if pos >= n:
                        raise JSONError("unexpected end of input", n)
                    if not ('0' <= s[pos] <= '9'):
                        raise JSONError("invalid number", pos)
                    while pos < n and '0' <= s[pos] <= '9':
                        pos += 1
                if pos < n and s[pos] in 'eE':
                    isf = True
                    pos += 1
                    if pos < n and s[pos] in '+-':
                        pos += 1
                    if pos >= n:
                        raise JSONError("unexpected end of input", n)
                    if not ('0' <= s[pos] <= '9'):
                        raise JSONError("invalid number", pos)
                    while pos < n and '0' <= s[pos] <= '9':
                        pos += 1
                txt = s[start:pos]
                val = float(txt) if isf else int(txt)
            else:
                raise JSONError("invalid value", pos)

            if not stack:
                result = val
                state = _DONE
            elif stack[-1][0] == 'array':
                stack[-1][1].append(val)
                state = _ARR_COMMA
            else:
                stack[-1][1][stack[-1][2][0]] = val
                state = _OBJ_COMMA

        elif state == _ARR_START:
            while pos < n and s[pos] in _WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ']':
                pos += 1
                val = stack[-1][1]
                stack.pop()
                if not stack:
                    result = val
                    state = _DONE
                elif stack[-1][0] == 'array':
                    stack[-1][1].append(val)
                    state = _ARR_COMMA
                else:
                    stack[-1][1][stack[-1][2][0]] = val
                    state = _OBJ_COMMA
            else:
                state = _VAL

        elif state == _ARR_COMMA:
            while pos < n and s[pos] in _WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ']':
                pos += 1
                val = stack[-1][1]
                stack.pop()
                if not stack:
                    result = val
                    state = _DONE
                elif stack[-1][0] == 'array':
                    stack[-1][1].append(val)
                    state = _ARR_COMMA
                else:
                    stack[-1][1][stack[-1][2][0]] = val
                    state = _OBJ_COMMA
            elif s[pos] == ',':
                pos += 1
                state = _ARR_NEXT
            else:
                raise JSONError("expected , or ]", pos)

        elif state == _ARR_NEXT:
            while pos < n and s[pos] in _WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ']':
                raise JSONError("trailing comma", pos)
            state = _VAL

        elif state == _OBJ_START:
            while pos < n and s[pos] in _WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == '}':
                pos += 1
                val = stack[-1][1]
                stack.pop()
                if not stack:
                    result = val
                    state = _DONE
                elif stack[-1][0] == 'array':
                    stack[-1][1].append(val)
                    state = _ARR_COMMA
                else:
                    stack[-1][1][stack[-1][2][0]] = val
                    state = _OBJ_COMMA
            elif s[pos] == '"':
                key, pos = _parse_str(s, pos, n)
                stack[-1][2][0] = key
                state = _OBJ_COLON
            else:
                raise JSONError("expected key or }", pos)

        elif state == _OBJ_COLON:
            while pos < n and s[pos] in _WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == ':':
                pos += 1
                state = _OBJ_VAL
            else:
                raise JSONError("expected :", pos)

        elif state == _OBJ_VAL:
            state = _VAL

        elif state == _OBJ_COMMA:
            while pos < n and s[pos] in _WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == '}':
                pos += 1
                val = stack[-1][1]
                stack.pop()
                if not stack:
                    result = val
                    state = _DONE
                elif stack[-1][0] == 'array':
                    stack[-1][1].append(val)
                    state = _ARR_COMMA
                else:
                    stack[-1][1][stack[-1][2][0]] = val
                    state = _OBJ_COMMA
            elif s[pos] == ',':
                pos += 1
                state = _OBJ_NEXT
            else:
                raise JSONError("expected , or }", pos)

        elif state == _OBJ_NEXT:
            while pos < n and s[pos] in _WS:
                pos += 1
            if pos >= n:
                raise JSONError("unexpected end of input", n)
            if s[pos] == '}':
                raise JSONError("trailing comma", pos)
            if s[pos] == '"':
                key, pos = _parse_str(s, pos, n)
                stack[-1][2][0] = key
                state = _OBJ_COLON
            else:
                raise JSONError("expected key", pos)

        elif state == _DONE:
            while pos < n and s[pos] in _WS:
                pos += 1
            if pos < n:
                raise JSONError("trailing garbage", pos)
            return result
