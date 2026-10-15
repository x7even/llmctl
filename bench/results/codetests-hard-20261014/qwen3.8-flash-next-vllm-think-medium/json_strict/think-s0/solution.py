import re

class JSONError(ValueError):
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos

_STR_SPECIAL = re.compile(r'["\\]|[\x00-\x1f]')

def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"the JSON object must be str, not {type(s).__name__}")

    n = len(s)
    i = 0

    while i < n and s[i] in ' \t\n\r':
        i += 1
    if i >= n:
        raise JSONError("empty input", i)

    stack = []
    state = 'value'
    result = None

    while True:
        if state == 'value':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)

            c = s[i]
            if c == '{':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(['o', {}, None])
                i += 1
                state = 'obj_start'
            elif c == '[':
                if len(stack) >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                stack.append(['a', [], None])
                i += 1
                state = 'arr_start'
            elif c == '"':
                val, i = _parse_string(s, i, n)
                if not stack:
                    result = val; state = 'done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val); state = 'arr_comma'
                else:
                    stack[-1][1][stack[-1][2]] = val; state = 'obj_comma'
            elif c == 't' or c == 'f' or c == 'n':
                val, i = _parse_literal(s, i, n)
                if not stack:
                    result = val; state = 'done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val); state = 'arr_comma'
                else:
                    stack[-1][1][stack[-1][2]] = val; state = 'obj_comma'
            elif c == '-' or ('0' <= c <= '9'):
                val, i = _parse_number(s, i, n)
                if not stack:
                    result = val; state = 'done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val); state = 'arr_comma'
                else:
                    stack[-1][1][stack[-1][2]] = val; state = 'obj_comma'
            else:
                raise JSONError("unexpected character", i)

        elif state == 'arr_start':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ']':
                i += 1
                val = stack.pop()[1]
                if not stack:
                    result = val; state = 'done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val); state = 'arr_comma'
                else:
                    stack[-1][1][stack[-1][2]] = val; state = 'obj_comma'
            else:
                state = 'value'

        elif state == 'arr_comma':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ',':
                i += 1
                state = 'value'
            elif s[i] == ']':
                i += 1
                val = stack.pop()[1]
                if not stack:
                    result = val; state = 'done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val); state = 'arr_comma'
                else:
                    stack[-1][1][stack[-1][2]] = val; state = 'obj_comma'
            else:
                raise JSONError("expected ',' or ']'", i)

        elif state == 'obj_start':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == '}':
                i += 1
                val = stack.pop()[1]
                if not stack:
                    result = val; state = 'done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val); state = 'arr_comma'
                else:
                    stack[-1][1][stack[-1][2]] = val; state = 'obj_comma'
            elif s[i] == '"':
                key, i = _parse_string(s, i, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("expected '\"' or '}'", i)

        elif state == 'obj_colon':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ':':
                i += 1
                state = 'value'
            else:
                raise JSONError("expected ':'", i)

        elif state == 'obj_comma':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == ',':
                i += 1
                state = 'obj_key'
            elif s[i] == '}':
                i += 1
                val = stack.pop()[1]
                if not stack:
                    result = val; state = 'done'
                elif stack[-1][0] == 'a':
                    stack[-1][1].append(val); state = 'arr_comma'
                else:
                    stack[-1][1][stack[-1][2]] = val; state = 'obj_comma'
            else:
                raise JSONError("expected ',' or '}'", i)

        elif state == 'obj_key':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                raise JSONError("unexpected end of input", n)
            if s[i] == '"':
                key, i = _parse_string(s, i, n)
                stack[-1][2] = key
                state = 'obj_colon'
            else:
                raise JSONError("expected '\"'", i)

        elif state == 'done':
            while i < n and s[i] in ' \t\n\r':
                i += 1
            if i >= n:
                return result
            raise JSONError("trailing data", i)


def _parse_string(s, i, n):
    i += 1
    parts = []

    while True:
        m = _STR_SPECIAL.search(s, i)
        if m is None:
            raise JSONError("unterminated string", n)
        j = m.start()
        if j > i:
            parts.append(s[i:j])