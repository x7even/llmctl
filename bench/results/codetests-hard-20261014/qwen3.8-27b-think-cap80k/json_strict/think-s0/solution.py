class JSONError(ValueError):
    pos: int
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def loads(s: str):
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)
    i = 0

    # Stack frames:
    #   ['array', list, phase]       phase in {'first','after_elem','after_comma'}
    #   ['object', dict, phase, key] phase in {'first','after_key','value','after_value','after_comma'}
    stack = []
    depth = 0
    result = None

    # State: VAL, KEY, STR, ESC, UNI, NUM, LIT, ARR_CE, OBJ_CE, OBJ_COLON, DONE
    state = 'VAL'

    # String
    str_buf = []
    str_is_key = False
    uni_count = 0
    uni_digits = []

    # Number
    num_buf = []
    num_phase = ''
    has_frac = False
    has_exp = False

    # Literal
    lit_expected = ''
    lit_pos = 0

    WS = ' \t\n\r'
    DIGITS = '0123456789'
    HEX = '0123456789abcdefABCDEF'

    def skip_ws():
        nonlocal i
        while i < n and s[i] in WS:
            i += 1

    def is_num_cont(c, ph):
        if ph == 'sign':
            return c in DIGITS
        if ph == 'int_zero':
            return c == '.' or c == 'e' or c == 'E'
        if ph == 'int_digit':
            return c in DIGITS or c == '.' or c == 'e' or c == 'E'
        if ph == 'frac_dot':
            return c in DIGITS
        if ph == 'frac_digit':
            return c in DIGITS or c == 'e' or c == 'E'
        if ph == 'exp':
            return c == '+' or c == '-' or c in DIGITS
        if ph == 'exp_sign':
            return c in DIGITS
        if ph == 'exp_digit':
            return c in DIGITS
        return False

    def num_complete(ph):
        return ph in ('int_zero', 'int_digit', 'frac_digit', 'exp_digit')

    def finish_number():
        nonlocal state, result
        num_str = ''.join(num_buf)
        if has_frac or has_exp:
            val = float(num_str)
        else:
            val = int(num_str)
        # complete_value(val) inlined:
        if not stack:
            state = 'DONE'
            result = val
        else:
            top = stack[-1]
            if top[0] == 'array':
                top[1].append(val)
                top[2] = 'after_elem'
                state = 'ARR_CE'
            else:
                top[1][top[3]] = val
                top[2] = 'after_value'
                state = 'OBJ_CE'

    def finish_value(val):
        nonlocal state, result
        if not stack:
            state = 'DONE'
            result = val
        else:
            top = stack[-1]
            if top[0] == 'array':
                top[1].append(val)
                top[2] = 'after_elem'
                state = 'ARR_CE'
            else:
                top[1][top[3]] = val
                top[2] = 'after_value'
                state = 'OBJ_CE'

    def finish_key(key):
        nonlocal state
        top = stack[-1]
        top[3] = key
        top[2] = 'after_key'
        state = 'OBJ_COLON'

    while True:
        if state == 'VAL':
            skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '[':
                if depth >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                i += 1
                depth += 1
                stack.append(['array', [], 'first'])
            elif c == '{':
                if depth >= 500:
                    raise JSONError("maximum nesting depth exceeded", i)
                i += 1
                depth += 1
                stack.append(['object', {}, 'first', None])
                state = 'KEY'
            elif c == '"':
                i += 1
                state = 'STR'
                str_buf = []
                str_is_key = False
            elif c == '-' or c in DIGITS:
                i += 1
                state = 'NUM'
                num_buf = [c]
                if c == '-':
                    num_phase = 'sign'
                elif c == '0':
                    num_phase = 'int_zero'
                else:
                    num_phase = 'int_digit'
                has_frac = False
                has_exp = False
            elif c == 't':
                i += 1
                state = 'LIT'
                lit_expected = 'true'
                lit_pos = 1
            elif c == 'f':
                i += 1
                state = 'LIT'
                lit_expected = 'false'
                lit_pos = 1
            elif c == 'n':
                i += 1
                state = 'LIT'
                lit_expected = 'null'
                lit_pos = 1
            elif c == ']':
                if stack and stack[-1][0] == 'array' and stack[-1][2] == 'first':
                    i += 1
                    depth -= 1
                    val = stack[-1][1]
                    stack.pop()
                    finish_value(val)
                else:
                    raise JSONError("unexpected ']'", i)
            else:
                raise JSONError(f"unexpected character {c!r}", i)

        elif state == 'KEY':
            skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == '}':
                if stack[-1][2] == 'first':
                    i += 1
                    depth -= 1
                    val = stack[-1][1]
                    stack.pop()
                    finish_value(val)
                else:
                    raise JSONError("unexpected '}'", i)
            elif c == '"':
                i += 1
                state = 'STR'
                str_buf = []
                str_is_key = True
            else:
                raise JSONError(f"expected string key or '}}'", i)

        elif state == 'STR':
            if i >= n:
                raise JSONError("unterminated string", n)
            c = s[i]
            if c == '"':
                i += 1
                val = ''.join(str_buf)
                if str_is_key:
                    finish_key(val)
                else:
                    finish_value(val)
            elif c == '\\':
                i += 1
                state = 'ESC'
            elif ord(c) < 0x20:
                raise JSONError("control character in string", i)
            else:
                j = i
                while j < n:
                    ch = s[j]
                    if ch == '"' or ch == '\\' or ord(ch) < 0x20:
                        break
                    j += 1
                if j < n and ord(s[j]) < 0x20:
                    raise JSONError("control character in string", j)
                str_buf.append(s[i:j])
                i = j

        elif state == 'ESC':
            if i >= n:
                raise JSONError("unterminated escape sequence", n)
            c = s[i]
            if c == '"':
                str_buf.append('"')
                i += 1
                state = 'STR'
            elif c == '\\':
                str_buf.append('\\')
                i += 1
                state = 'STR'
            elif c == '/':
                str_buf.append('/')
                i += 1
                state = 'STR'
            elif c == 'b':
                str_buf.append('\b')
                i += 1
                state = 'STR'
            elif c == 'f':
                str_buf.append('\f')
                i += 1
                state = 'STR'
            elif c == 'n':
                str_buf.append('\n')
                i += 1
                state = 'STR'
            elif c == 'r':
                str_buf.append('\r')
                i += 1
                state = 'STR'
            elif c == 't':
                str_buf.append('\t')
                i += 1
                state = 'STR'
            elif c == 'u':
                i += 1
                state = 'UNI'
                uni_count = 0
                uni_digits = []
            else:
                raise JSONError(f"invalid escape character {c!r}", i)

        elif state == 'UNI':
            if i >= n:
                raise JSONError("incomplete \\u escape", n)
            c = s[i]
            if c not in HEX:
                raise JSONError(f"invalid hex digit {c!r}", i)
            uni_digits.append(c)
            i += 1
            uni_count += 1
            if uni_count == 4:
                cp = int(''.join(uni_digits), 16)
                if 0xD800 <= cp <= 0xDBFF:
                    # High surrogate: check for low surrogate pair
                    if i + 6 <= n and s[i] == '\\' and s[i + 1] == 'u':
                        h2 = s[i + 2:i + 6]
                        if all(ch in HEX for ch in h2):
                            lo = int(h2, 16)
                            if 0xDC00 <= lo <= 0xDFFF:
                                combined = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                                str_buf.append(chr(combined))
                                i += 6
                                state = 'STR'
                                continue
                    str_buf.append(chr(cp))
                    state = 'STR'
                else:
                    str_buf.append(chr(cp))
                    state = 'STR'

        elif state == 'NUM':
            if i < n:
                c = s[i]
                if is_num_cont(c, num_phase):
                    num_buf.append(c)
                    i += 1
                    old = num_phase
                    if old == 'sign':
                        num_phase = 'int_zero' if c == '0' else 'int_digit'
                    elif old == 'int_zero':
                        if c == '.':
                            num_phase = 'frac_dot'
                            has_frac = True
                        else:
                            num_phase = 'exp'
                            has_exp = True
                    elif old == 'int_digit':
                        if c in DIGITS:
                            num_phase = 'int_digit'
                        elif c == '.':
                            num_phase = 'frac_dot'
                            has_frac = True
                        else:
                            num_phase = 'exp'
                            has_exp = True
                    elif old == 'frac_dot':
                        num_phase = 'frac_digit'
                    elif old == 'frac_digit':
                        if c in DIGITS:
                            num_phase = 'frac_digit'
                        else:
                            num_phase = 'exp'
                            has_exp = True
                    elif old == 'exp':
                        if c == '+' or c == '-':
                            num_phase = 'exp_sign'
                        else:
                            num_phase = 'exp_digit'
                    elif old == 'exp_sign':
                        num_phase = 'exp_digit'
                    elif old == 'exp_digit':
                        num_phase = 'exp_digit'
                else:
                    if not num_complete(num_phase):
                        raise JSONError("incomplete number", i)
                    finish_number()
            else:
                if not num_complete(num_phase):
                    raise JSONError("incomplete number", n)
                finish_number()

        elif state == 'LIT':
            if i >= n:
                raise JSONError("incomplete literal", n)
            c = s[i]
            if c == lit_expected[lit_pos]:
                i += 1
                lit_pos += 1
                if lit_pos == len(lit_expected):
                    if lit_expected == 'true':
                        val = True
                    elif lit_expected == 'false':
                        val = False
                    else:
                        val = None
                    finish_value(val)
            else:
                raise JSONError(f"invalid literal at position {i}", i)

        elif state == 'ARR_CE':
            skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == ',':
                i += 1
                stack[-1][2] = 'after_comma'
                state = 'VAL'
            elif c == ']':
                i += 1
                depth -= 1
                val = stack[-1][1]
                stack.pop()
                finish_value(val)
            else:
                raise JSONError(f"expected ',' or ']]'", i)

        elif state == 'OBJ_CE':
            skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == ',':
                i += 1
                stack[-1][2] = 'after_comma'
                state = 'KEY'
            elif c == '}':
                i += 1
                depth -= 1
                val = stack[-1][1]
                stack.pop()
                finish_value(val)
            else:
                raise JSONError(f"expected ',' or '}}'", i)

        elif state == 'OBJ_COLON':
            skip_ws()
            if i >= n:
                raise JSONError("unexpected end of input", n)
            c = s[i]
            if c == ':':
                i += 1
                stack[-1][2] = 'value'
                state = 'VAL'
            else:
                raise JSONError(f"expected ':'", i)

        elif state == 'DONE':
            skip_ws()
            if i >= n:
                return result
            else:
                raise JSONError("trailing garbage", i)
