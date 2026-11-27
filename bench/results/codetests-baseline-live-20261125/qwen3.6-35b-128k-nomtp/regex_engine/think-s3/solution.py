class Match:
    def __init__(self, text, captures, num_groups):
        self.text = text
        self.captures = captures
        self.num_groups = num_groups

    def span(self, n: int = 0) -> tuple[int, int]:
        if n < 0 or n > self.num_groups:
            raise IndexError
        s = self.captures[n]
        return (-1, -1) if s is None else s

    def start(self, n: int = 0) -> int:
        if n < 0 or n > self.num_groups:
            raise IndexError
        s = self.captures[n]
        return -1 if s is None else s[0]

    def end(self, n: int = 0) -> int:
        if n < 0 or n > self.num_groups:
            raise IndexError
        s = self.captures[n]
        return -1 if s is None else s[1]

    def group(self, n: int = 0) -> "str | None":
        if n < 0 or n > self.num_groups:
            raise IndexError
        s = self.captures[n]
        if s is None:
            return None
        return self.text[s[0]:s[1]]

    def groups(self) -> tuple["str | None", ...]:
        return tuple(self.captures[i] if self.captures[i] is not None else None for i in range(1, self.num_groups + 1))


class Pattern:
    def __init__(self, insns, num_groups):
        self.insns = insns
        self.num_groups = num_groups

    def fullmatch(self, s: str) -> "Match | None":
        return self._run(s, 0, fullmatch=True)

    def search(self, s: str) -> "Match | None":
        n = len(s)
        for start in range(n + 1):
            res = self._run(s, start, fullmatch=False)
            if res:
                return res
        return None

    def _run(self, text, start_pos, fullmatch=False):
        n = len(text)
        captures = [None] * (self.num_groups + 1)
        cap_starts = [-1] * (self.num_groups + 1)
        stack = []

        ip = 0
        pos = start_pos
        captures[0] = (start_pos, None)

        while ip < len(self.insns):
            instr = self.insns[ip]
            op = instr[0]

            if op == 'LIT':
                if pos < n and text[pos] == instr[1]:
                    pos += 1
                    ip += 1
                else:
                    if not stack:
                        return None
                    bp = stack.pop()
                    ip, pos, captures, cap_starts = self._restore(bp)
                    continue

            elif op == 'DOT':
                if pos < n and text[pos] != '\n':
                    pos += 1
                    ip += 1
                else:
                    if not stack:
                        return None
                    bp = stack.pop()
                    ip, pos, captures, cap_starts = self._restore(bp)
                    continue

            elif op == 'START':
                if pos == 0:
                    ip += 1
                else:
                    if not stack:
                        return None
                    bp = stack.pop()
                    ip, pos, captures, cap_starts = self._restore(bp)
                    continue

            elif op == 'END':
                if pos == n or (pos == n - 1 and text[pos] == '\n'):
                    ip += 1
                else:
                    if not stack:
                        return None
                    bp = stack.pop()
                    ip, pos, captures, cap_starts = self._restore(bp)
                    continue

            elif op == 'CLASS':
                char_set, negated = instr[1], instr[2]
                if pos < n:
                    c = text[pos]
                    in_set = c in char_set
                    if negated:
                        in_set = not in_set
                    if in_set:
                        pos += 1
                        ip += 1
                    else:
                        if not stack:
                            return None
                        bp = stack.pop()
                        ip, pos, captures, cap_starts = self._restore(bp)
                        continue
                else:
                    if not stack:
                        return None
                    bp = stack.pop()
                    ip, pos, captures, cap_starts = self._restore(bp)
                    continue

            elif op == 'ESC':
                esc = instr[1]
                if pos < n:
                    c = text[pos]
                    in_set = False
                    if esc == 'd':
                        in_set = c in '0123456789'
                    elif esc == 'D':
                        in_set = c not in '0123456789'
                    elif esc == 'w':
                        in_set = c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'
                    elif esc == 'W':
                        in_set = c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'
                    elif esc == 's':
                        in_set = c in ' \t\n\r\f\v'
                    elif esc == 'S':
                        in_set = c not in ' \t\n\r\f\v'
                    if in_set:
                        pos += 1
                        ip += 1
                    else:
                        if not stack:
                            return None
                        bp = stack.pop()
                        ip, pos, captures, cap_starts = self._restore(bp)
                        continue
                else:
                    if not stack:
                        return None
                    bp = stack.pop()
                    ip, pos, captures, cap_starts = self._restore(bp)
                    continue

            elif op == 'CAP_OPEN':
                gid = instr[1]
                cap_starts[gid] = pos
                ip += 1

            elif op == 'CAP_CLOSE':
                gid = instr[1]
                if cap_starts[gid] != -1:
                    captures[gid] = (cap_starts[gid], pos)
                ip += 1

            elif op == 'ALT':
                _, next_ip, right_ip = instr
                stack.append(('ALT', next_ip, right_ip, pos, captures[:], cap_starts[:]))
                ip = next_ip

            elif op == 'QUANT':
                lo, hi, lazy, start_ip, end_ip, next_ip, c, mark = instr[1:9]
                while True:
                    if c < lo:
                        stack.append(('QUANT', lo, hi, lazy, start_ip, end_ip, next_ip, c, mark, ip, pos, captures[:], cap_starts[:]))
                        ip = start_ip
                        break
                    else:
                        if lazy:
                            ip = next_ip
                            break
                        else:
                            if (hi == -1 or c < hi) and pos != mark:
                                mark = pos
                                stack.append(('QUANT', lo, hi, lazy, start_ip, end_ip, next_ip, c, mark, ip, pos, captures[:], cap_starts[:]))
                                ip = start_ip
                                break
                            else:
                                ip = next_ip
                                break

            else:
                captures[0] = (start_pos, pos)
                if fullmatch and pos != n:
                    return None
                return Match(text, captures, self.num_groups)

        captures[0] = (start_pos, pos)
        if fullmatch and pos != n:
            return None
        return Match(text, captures, self.num_groups)

    def _restore(self, bp):
        if bp[0] == 'ALT':
            _, next_ip, right_ip, pos, captures, cap_starts = bp
            return next_ip, pos, captures, cap_starts
        elif bp[0] == 'QUANT':
            _, _, _, _, _, _, next_ip, c, mark, ip, pos, captures, cap_starts = bp
            self.insns[ip][6] = c
            self.insns[ip][7] = mark
            return next_ip, pos, captures, cap_starts
        return None


class Parser:
    def __init__(self, pattern):
        self.pat = pattern
        self.pos = 0
        self.num_groups = 0
        self.insns = []
        self.can_quantify = True

    def parse(self):
        self.insns = []
        self.num_groups = 0
        self.can_quantify = True
        self.parse_pattern()
        if self.pos != len(self.pat):
            raise ValueError("Unexpected characters")
        return self.insns, self.num_groups

    def peek(self):
        return self.pat[self.pos] if self.pos < len(self.pat) else None

    def advance(self):
        c = self.pat[self.pos]
        self.pos += 1
        return c

    def parse_pattern(self):
        self.parse_branch()
        while self.peek() == '|':
            alt_start = len(self.insns)
            self.advance()
            self.parse_branch()
            self.insns.insert(alt_start, ['ALT', alt_start + 1, len(self.insns)])

    def parse_branch(self):
        self.parse_element()
        while self.peek() not in (None, '|', ')'):
            self.parse_element()

    def parse_element(self):
        atom_start = len(self.insns)
        c = self.peek()
        if c is None:
            return
        if c == '.':
            self.advance()
            self.insns.append(['DOT'])
        elif c == '^':
            self.advance()
            self.insns.append(['START'])
            self.can_quantify = False
        elif c == '$':
            self.advance()
            self.insns.append(['END'])
            self.can_quantify = False
        elif c == '(':
            self.advance()
            if self.peek() == '?':
                self.advance()
                if self.peek() == ':':
                    self.advance()
                    self.parse_branch()
                    if self.peek() != ')':
                        raise ValueError("Unclosed group")
                    self.advance()
                else:
                    raise ValueError("Invalid group")
            else:
                self.num_groups += 1
                gid = self.num_groups
                self.insns.append(['CAP_OPEN', gid])
                self.parse_branch()
                if self.peek() != ')':
                    raise ValueError("Unclosed group")
                self.advance()
                self.insns.append(['CAP_CLOSE', gid])
            self.can_quantify = True
        elif c == '[':
            self.insns.append(self.parse_class())
            self.can_quantify = True
        elif c == '\\':
            self.advance()
            esc = self.advance()
            if esc in 'dDwWsS':
                self.insns.append(['ESC', esc])
                self.can_quantify = True
            elif esc in 'ntr':
                self.insns.append(['LIT', {'n': '\n', 't': '\t', 'r': '\r'}[esc]])
                self.can_quantify = True
            elif esc.isalnum():
                raise ValueError("Invalid escape")
            else:
                self.insns.append(['LIT', '\\' + esc])
                self.can_quantify = True
        else:
            self.insns.append(['LIT', self.advance()])
            self.can_quantify = True

        if self.can_quantify and self.peek() in '*+?{':
            self.parse_quantifier(atom_start)

    def parse_quantifier(self, atom_start):
        c = self.advance()
        lazy = False
        if c == '?':
            lazy = True
            c = self.peek()
            if c not in '*+{':
                raise ValueError("Invalid quantifier")
            self.advance()

        if c == '*':
            lo, hi = 0, -1
        elif c == '+':
            lo, hi = 1, -1
        elif c == '{':
            if self.pos >= len(self.pat):
                raise ValueError("Invalid quantifier")
            start = self.pos
            while self.pos < len(self.pat) and self.pat[self.pos].isdigit():
                self.pos += 1
            if self.pos == start:
                raise ValueError("Invalid quantifier")
            m = int(self.pat[start:self.pos])
            if self.peek() == ',':
                self.advance()
                if self.peek() == '}':
                    self.advance()
                    hi = -1
                else:
                    start2 = self.pos
                    while self.pos < len(self.pat) and self.pat[self.pos].isdigit():
                        self.pos += 1
                    if self.pos == start2:
                        raise ValueError("Invalid quantifier")
                    n = int(self.pat[start2:self.pos])
                    if m > n:
                        raise ValueError("Invalid quantifier")
                    if self.peek() != '}':
                        raise ValueError("Invalid quantifier")
                    self.advance()
                    hi = n
            elif self.peek() == '}':
                self.advance()
                hi = m
            else:
                raise ValueError("Invalid quantifier")
        else:
            raise ValueError("Invalid quantifier")

        end_ip = len(self.insns)
        self.insns.insert(atom_start, ['QUANT', lo, hi, lazy, atom_start + 1, end_ip + 1, atom_start + 2, 0, None])
        self.can_quantify = False

    def parse_class(self):
        self.advance()  # [
        negated = False
        if self.peek() == '^':
            negated = True
            self.advance()

        char_set = set()
        while True:
            c = self.peek()
            if c is None:
                raise ValueError("Unclosed class")
            if c == ']':
                self.advance()
                break

            if c == '\\':
                self.advance()
                esc = self.advance()
                if esc in 'dDwWsS':
                    char_set.add(esc)
                    if self.peek() == '-' and self.pos + 1 < len(self.pat) and self.pat[self.pos + 1] != ']':
                        raise ValueError("Invalid range in class")
                elif esc in 'ntr':
                    char_set.add({'n': '\n', 't': '\t', 'r': '\r'}[esc])
                    if self.peek() == '-' and self.pos + 1 < len(self.pat) and self.pat[self.pos + 1] != ']':
                        raise ValueError("Invalid range in class")
                else:
                    if esc.isalnum():
                        raise ValueError("Invalid escape")
                    char_set.add('\\' + esc)
                    if self.peek() == '-' and self.pos + 1 < len(self.pat) and self.pat[self.pos + 1] != ']':
                        raise ValueError("Invalid range in class")
            else:
                char_set.add(c)
                self.advance()
                if self.peek() == '-' and self.pos + 1 < len(self.pat) and self.pat[self.pos + 1] != ']':
                    self.advance()  # -
                    end_c = self.peek()
                    if end_c is None or end_c == ']':
                        raise ValueError("Invalid range")
                    self.advance()
                    if end_c == '\\':
                        raise ValueError("Invalid range")
                    char_set.update(range(ord(char_set.pop()), ord(end_c) + 1))

        full_set = set()
        for item in char_set:
            if isinstance(item, str) and len(item) == 1:
                full_set.add(item)
            elif item == 'd':
                full_set.update('0123456789')
            elif item == 'D':
                full_set.update([chr(i) for i in range(128) if chr(i) not in '0123456789'])
            elif item == 'w':
                full_set.update('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
            elif item == 'W':
                full_set.update([chr(i) for i in range(128) if chr(i) not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'])
            elif item == 's':
                full_set.update(' \t\n\r\f\v')
            elif item == 'S':
                full_set.update([chr(i) for i in range(128) if chr(i) not in ' \t\n\r\f\v'])
        return ['CLASS', frozenset(full_set), negated]


def compile(pattern: str) -> "Pattern":
    parser = Parser(pattern)
    insns, num_groups = parser.parse()
    return Pattern(insns, num_groups)
