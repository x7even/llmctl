import sys

# Character sets for escapes
_DIGITS = set('0123456789')
_WORD = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_')
_SPACE = set(' \t\n\r\f\v')
_ALL = set(chr(i) for i in range(256))

class Match:
    def __init__(self, captures, s, end_idx):
        self.captures = captures
        self.s = s
        self.end_idx = end_idx

    def span(self, n: int = 0) -> tuple[int, int]:
        if not isinstance(n, int) or n < 0 or n >= len(self.captures):
            raise IndexError
        if n == 0:
            return (0, self.end_idx)
        c = self.captures[n]
        if c is None:
            return (-1, -1)
        return c

    def start(self, n: int = 0) -> int:
        return self.span(n)[0]

    def end(self, n: int = 0) -> int:
        return self.span(n)[1]

    def group(self, n: int = 0) -> "str | None":
        if not isinstance(n, int) or n < 0 or n >= len(self.captures):
            raise IndexError
        if n == 0:
            return self.s[0:self.end_idx]
        c = self.captures[n]
        if c is None:
            return None
        return self.s[c[0]:c[1]]

    def groups(self) -> tuple["str | None", ...]:
        return tuple(self.s[c[0]:c[1]] if c is not None else None for c in self.captures[1:])


class Pattern:
    def __init__(self, instrs, num_groups):
        self.instrs = instrs
        self.num_groups = num_groups

    def fullmatch(self, s: str) -> "Match | None":
        return _run(self.instrs, s, 0, self.num_groups, fullmatch=True)

    def search(self, s: str) -> "Match | None":
        for i in range(len(s) + 1):
            m = _run(self.instrs, s, i, self.num_groups, fullmatch=False)
            if m:
                return m
        return None


def _run(instrs, s, start_idx, num_groups, fullmatch):
    captures = [None] * num_groups
    stack = []  # backtrack points: (ip, s_idx, captures_snapshot)
    ip = start_idx
    s_idx = start_idx
    q_state = None  # state for current quantifier loop

    while ip < len(instrs):
        instr = instrs[ip]

        if instr[0] == 'QUANT':
            lo, hi, lazy, body_start, body_end, next_ip = instr[1:]
            q_state = {'c': 0, 'mark': None, 'lo': lo, 'hi': hi, 'lazy': lazy, 
                       'body_start': body_start, 'body_end': body_end, 'next_ip': next_ip}
            ip = body_start
            continue

        # Execute instruction
        if instr[0] == 'LIT':
            if s_idx >= len(s) or s[s_idx] != instr[1]:
                if not stack: return None
                ip, s_idx, captures = stack.pop()
                continue
            ip += 1
            s_idx += 1
        elif instr[0] == 'DOT':
            if s_idx >= len(s) or s[s_idx] == '\n':
                if not stack: return None
                ip, s_idx, captures = stack.pop()
                continue
            ip += 1
            s_idx += 1
        elif instr[0] == 'CLASS':
            chars, negated = instr[1], instr[2]
            if s_idx >= len(s) or (instr[1].get(s[s_idx], False) == negated):
                if not stack: return None
                ip, s_idx, captures = stack.pop()
                continue
            ip += 1
            s_idx += 1
        elif instr[0] == 'ANCHOR_START':
            if s_idx != 0:
                if not stack: return None
                ip, s_idx, captures = stack.pop()
                continue
            ip += 1
        elif instr[0] == 'ANCHOR_END':
            if s_idx != len(s) and not (s_idx == len(s) - 1 and s[s_idx] == '\n'):
                if not stack: return None
                ip, s_idx, captures = stack.pop()
                continue
            ip += 1
        elif instr[0] == 'GROUP_OPEN':
            captures[instr[1]] = (s_idx, None)
            ip += 1
        elif instr[0] == 'GROUP_CLOSE':
            captures[instr[1]] = (captures[instr[1]][0], s_idx)
            ip += 1
        elif instr[0] == 'ALT':
            stack.append((ip, s_idx, captures.copy()))
            ip += 1
        elif instr[0] == 'JUMP':
            ip = instr[1]
        elif instr[0] == 'MATCH':
            if fullmatch and s_idx != len(s):
                if not stack: return None
                ip, s_idx, captures = stack.pop()
                continue
            return Match(captures, s, s_idx)
        elif instr[0] == 'FAIL':
            if not stack: return None
            ip, s_idx, captures = stack.pop()
            continue
        else:
            # Should not happen
            if not stack: return None
            ip, s_idx, captures = stack.pop()
            continue

        # Check if we finished a quantifier body
        if q_state and ip == q_state['body_end']:
            c = q_state['c'] + 1
            mark = q_state['mark']
            lo, hi, lazy, body_start, body_end, next_ip = (
                q_state['lo'], q_state['hi'], q_state['lazy'],
                q_state['body_start'], q_state['body_end'], q_state['next_ip']
            )
            if c < lo:
                q_state['c'] = c
                ip = body_start
            else:
                if lazy:
                    ip = next_ip
                    q_state = None
                else:  # greedy
                    if (hi == float('inf') or c < hi) and mark != s_idx:
                        mark = s_idx
                        q_state['c'] = c
                        q_state['mark'] = mark
                        ip = body_start
                    else:
                        ip = next_ip
                        q_state = None

    return None


def compile(pattern: str) -> "Pattern":
    class Parser:
        def __init__(self, pat):
            self.pat = pat
            self.pos = 0
            self.instrs = []
            self.group_count = 0
            self.group_stack = []  # stores index of GROUP_OPEN

        def parse(self):
            self.parse_expr()
            if self.pos < len(self.pat):
                raise ValueError("Unbalanced parentheses")
            self.instrs.append(('MATCH',))
            return self.instrs, self.group_count

        def parse_expr(self):
            self.parse_term()
            while self.pos < len(self.pat) and self.pat[self.pos] == '|':
                self.pos += 1
                self.instrs.append(('ALT',))
                self.parse_term()

        def parse_term(self):
            while self.pos < len(self.pat) and self.pat[self.pos] not in '|)':
                self.parse_atom()
                self.try_quantifier()

        def parse_atom(self):
            if self.pos >= len(self.pat):
                raise ValueError("Unexpected end")
            c = self.pat[self.pos]
            if c == '.':
                self.instrs.append(('DOT',))
                self.pos += 1
            elif c == '^':
                self.instrs.append(('ANCHOR_START',))
                self.pos += 1
            elif c == '$':
                self.instrs.append(('ANCHOR_END',))
                self.pos += 1
            elif c == '(':
                self.parse_group()
            elif c == '[':
                self.parse_class()
            elif c == '\\':
                self.parse_escape()
            elif c == '{':
                raise ValueError("Invalid pattern")
            else:
                self.instrs.append(('LIT', c))
                self.pos += 1

        def parse_group(self):
            self.pos += 1
            is_capturing = True
            if self.pos + 1 < len(self.pat) and self.pat[self.pos:self.pos+2] == '?:':
                is_capturing = False
                self.pos += 2
            if is_capturing:
                self.group_count += 1
                self.instrs.append(('GROUP_OPEN', self.group_count))
            self.group_stack.append(len(self.instrs) - 1)
            self.parse_expr()
            if self.pos >= len(self.pat) or self.pat[self.pos] != ')':
                raise ValueError("Unbalanced parentheses")
            self.pos += 1
            if is_capturing:
                self.instrs.append(('GROUP_CLOSE', self.group_count))
            if self.group_stack:
                self.group_stack.pop()

        def parse_class(self):
            self.pos += 1
            negated = False
            if self.pos < len(self.pat) and self.pat[self.pos] == '^':
                negated = True
                self.pos += 1
            chars = set()
            i = self.pos
            last_was_escape = False
            while i < len(self.pat) and self.pat[i] != ']':
                c = self.pat[i]
                if c == '\\':
                    i += 1
                    if i >= len(self.pat): raise ValueError("Invalid class")
                    c = self.pat[i]
                    if c == 'd': chars.update(_DIGITS)
                    elif c == 'D': chars.update(_ALL - _DIGITS)
                    elif c == 'w': chars.update(_WORD)
                    elif c == 'W': chars.update(_ALL - _WORD)
                    elif c == 's': chars.update(_SPACE)
                    elif c == 'S': chars.update(_ALL - _SPACE)
                    elif c == 'n': chars.add('\n')
                    elif c == 't': chars.add('\t')
                    elif c.isalnum(): raise ValueError("Invalid escape in class")
                    else: chars.add(c)
                    i += 1
                    last_was_escape = True
                elif c not in ']-':
                    chars.add(c)
                    i += 1
                    last_was_escape = False
                elif c == '-' and i + 1 < len(self.pat) and self.pat[i+1] != ']':
                    if last_was_escape: raise ValueError("Invalid class range")
                    i += 1  # -
                    if i >= len(self.pat): raise ValueError("Invalid class")
                    c2 = self.pat[i]
                    if c2 == '\\':
                        i += 1
                        if i >= len(self.pat): raise ValueError("Invalid class")
                        c2 = self.pat[i]
                        if c2.isalnum(): raise ValueError("Invalid escape in class range")
                        last_was_escape = True
                    if c2 in ']-': raise ValueError("Invalid class range")
                    if c > c2: raise ValueError("Invalid class range")
                    for code in range(ord(c), ord(c2)+1):
                        chars.add(chr(code))
                    i += 1
                    last_was_escape = False
                else:
                    i += 1
                    last_was_escape = False
            if i >= len(self.pat): raise ValueError("Unclosed class")
            self.pos = i + 1
            self.instrs.append(('CLASS', chars, negated))

        def parse_escape(self):
            self.pos += 1
            if self.pos >= len(self.pat): raise ValueError("Invalid escape")
            c = self.pat[self.pos]
            if c == 'd': self.instrs.append(('CLASS', _DIGITS, False))
            elif c == 'D': self.instrs.append(('CLASS', _DIGITS, True))
            elif c == 'w': self.instrs.append(('CLASS', _WORD, False))
            elif c == 'W': self.instrs.append(('CLASS', _WORD, True))
            elif c == 's': self.instrs.append(('CLASS', _SPACE, False))
            elif c == 'S': self.instrs.append(('CLASS', _SPACE, True))
            elif c == 'n': self.instrs.append(('LIT', '\n'))
            elif c == 't': self.instrs.append(('LIT', '\t'))
            elif c.isalnum(): raise ValueError("Invalid escape")
            else: self.instrs.append(('LIT', c))
            self.pos += 1

        def try_quantifier(self):
            if self.pos >= len(self.pat) or self.pat[self.pos] not in '*+?{':
                return
            # Validation
            if not self.instrs: raise ValueError("Quantifier at start")
            last = self.instrs[-1]
            if last[0] in ('QUANT', 'ALT', 'GROUP_OPEN', 'ANCHOR_START', 'ANCHOR_END'):
                raise ValueError("Invalid quantifier placement")
            lo, hi, lazy = self.parse_quantifier()
            start_idx = len(self.instrs)
            if self.group_stack:
                start_idx = self.group_stack[-1]
            self.instrs.append(('QUANT', lo, hi, lazy, start_idx, len(self.instrs), len(self.instrs)+1))

        def parse_quantifier(self):
            c = self.pat[self.pos]
            if c == '*':
                self.pos += 1
                lo, hi = 0, float('inf')
            elif c == '+':
                self.pos += 1
                lo, hi = 1, float('inf')
            elif c == '?':
                self.pos += 1
                lo, hi = 0, 1
            elif c == '{':
                self.pos += 1
                m_str = ''
                while self.pos < len(self.pat) and self.pat[self.pos].isdigit():
                    m_str += self.pat[self.pos]
                    self.pos += 1
                if not m_str: raise ValueError("Invalid quantifier")
                m = int(m_str)
                if self.pos < len(self.pat) and self.pat[self.pos] == ',':
                    self.pos += 1
                    if self.pos < len(self.pat) and self.pat[self.pos] == '}':
                        self.pos += 1
                        hi = float('inf')
                    else:
                        n_str = ''
                        while self.pos < len(self.pat) and self.pat[self.pos].isdigit():
                            n_str += self.pat[self.pos]
                            self.pos += 1
                        if not n_str: raise ValueError("Invalid quantifier")
                        n = int(n_str)
                        if m > n: raise ValueError("Invalid quantifier")
                        self.pos += 1  # }
                        hi = n
                elif self.pat[self.pos] == '}':
                    self.pos += 1
                    hi = m
                else:
                    raise ValueError("Invalid quantifier")
            else:
                raise ValueError("Invalid quantifier")
            lazy = False
            if self.pos < len(self.pat) and self.pat[self.pos] == '?':
                lazy = True
                self.pos += 1
            return lo, hi, lazy

    p = Parser(pattern)
    instrs, num_groups = p.parse()
    return Pattern(instrs, num_groups)
