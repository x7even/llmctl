"""Backtracking-priority regular-expression engine (no re/regex/fnmatch/glob)."""

def compile(pattern):
    parser = _Parser(pattern)
    ast = parser.parse()
    compiler = _Compiler(parser.num_groups)
    code = compiler.compile(ast)
    return Pattern(code, parser.num_groups)


class Pattern:
    __slots__ = ('_code', '_ngroups')
    def __init__(self, code, ngroups):
        self._code = code
        self._ngroups = ngroups
    def fullmatch(self, s):
        m = _Matcher(self._code, self._ngroups, s, True)
        return m.run(0)
    def search(self, s):
        m = _Matcher(self._code, self._ngroups, s, False)
        for start in range(len(s) + 1):
            r = m.run(start)
            if r is not None:
                return r
        return None


class Match:
    __slots__ = ('_s', '_spans', '_ngroups')
    def __init__(self, s, spans, ngroups):
        self._s = s
        self._spans = spans
        self._ngroups = ngroups
    def span(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ngroups:
            raise IndexError(n)
        return self._spans[n]
    def start(self, n=0):
        return self.span(n)[0]
    def end(self, n=0):
        return self.span(n)[1]
    def group(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ngroups:
            raise IndexError(n)
        s, e = self._spans[n]
        if s == -1:
            return None
        return self._s[s:e]
    def groups(self):
        out = []
        for i in range(1, self._ngroups + 1):
            s, e = self._spans[i]
            if s == -1:
                out.append(None)
            else:
                out.append(self._s[s:e])
        return tuple(out)


# ─── Parser ───────────────────────────────────────────────────────────────────

_DIGITS = frozenset('0123456789')
_WORD = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')
_ALL_ASCII = frozenset(chr(i) for i in range(128))

class _Parser:
    def __init__(self, pattern):
        self.pat = pattern
        self.pos = 0
        self.num_groups = 0

    def parse(self):
        node = self._alt()
        if self.pos < len(self.pat):
            raise ValueError("unbalanced parentheses")
        return node

    def _peek(self):
        if self.pos < len(self.pat):
            return self.pat[self.pos]
        return None

    def _alt(self):
        branches = [self._concat()]
        while self._peek() == '|':
            self.pos += 1
            branches.append(self._concat())
        if len(branches) == 1:
            return branches[0]
        return ('alt', branches)

    def _concat(self):
        items = []
        while self.pos < len(self.pat) and self.pat[self.pos] not in '|)':
            items.append(self._quantified())
        if not items:
            return ('empty',)
        if len(items) == 1:
            return items[0]
        return ('concat', items)

    def _quantified(self):
        atom = self._atom()
        c = self._peek()
        if c is None or c not in '*+?{':
            return atom
        # quantifier present
        if atom[0] in ('start', 'end'):
            raise ValueError("quantifier on assertion")
        lo, hi = self._parse_quantifier_body(c)
        lazy = False
        if self._peek() == '?':
            lazy = True
            self.pos += 1
        # quantifier after quantifier?
        nc = self._peek()
        if nc is not None and nc in '*+?{':
            raise ValueError("quantifier after quantifier")
        return ('quant', atom, lo, hi, not lazy)

    def _parse_quantifier_body(self, c):
        if c == '*':
            self.pos += 1
            return (0, None)
        if c == '+':
            self.pos += 1
            return (1, None)
        if c == '?':
            self.pos += 1
            return (0, 1)
        # c == '{'
        return self._parse_counted()

    def _parse_counted(self):
        start = self.pos
        self.pos += 1  # skip '{'
        m = self._parse_int()
        if m is None:
            self.pos = start
            raise ValueError("invalid quantifier")
        if self._peek() == ',':
            self.pos += 1
            n = self._parse_int()
            if self._peek() != '}':
                self.pos = start
                raise ValueError("invalid quantifier")
            self.pos += 1  # skip '}'
            if n is not None and n < m:
                raise ValueError("quantifier min > max")
            return (m, n)
        else:
            if self._peek() != '}':
                self.pos = start
                raise ValueError("invalid quantifier")
            self.pos += 1
            return (m, m)

    def _parse_int(self):
        s = self.pos
        while self.pos < len(self.pat) and self.pat[self.pos].isdigit():
            self.pos += 1
        if self.pos == s:
            return None
        return int(self.pat[s:self.pos])

    def _atom(self):
        c = self._peek()
        if c is None:
            raise ValueError("unexpected end of pattern")
        if c in '*+?{':
            raise ValueError("quantifier with nothing to repeat")
        if c == ')':
            raise ValueError("unbalanced parentheses")
        if c == '(':
            return self._group()
        if c == '[':
            return self._class()
        if c == '.':
            self.pos += 1
            return ('any',)
        if c == '^':
            self.pos += 1
            return ('start',)
        if c == '$':
            self.pos += 1
            return ('end',)
        if c == '\\':
            return self._escape_atom()
        # ordinary literal
        self.pos += 1
        return ('lit', c)

    def _escape_atom(self):
        self.pos += 1  # skip backslash
        c = self._peek()
        if c is None:
            raise ValueError("backslash at end of pattern")
        self.pos += 1
        if c == 'd':
            return ('cls', _DIGITS, False)
        if c == 'D':
            return ('cls', _DIGITS, True)
        if c == 'w':
            return ('cls', _WORD, False)
        if c == 'W':
            return ('cls', _WORD, True)
        if c == 's':
            return ('cls', _SPACE, False)
        if c == 'S':
            return ('cls', _SPACE, True)
        if c == 'n':
            return ('lit', '\n')
        if c == 't':
            return ('lit', '\t')
        if c.isalpha() or c.isdigit():
            raise ValueError("invalid escape")
        return ('lit', c)

    def _group(self):
        self.pos += 1  # skip '('
        if self._peek() == '?':
            self.pos += 1
            if self._peek() == ':':
                self.pos += 1
                node = self._alt()
                if self._peek() != ')':
                    raise ValueError("unbalanced parentheses")
                self.pos += 1
                return ('nongroup', node)
            raise ValueError("unsupported group syntax")
        self.num_groups += 1
        gnum = self.num_groups
        node = self._alt()
        if self._peek() != ')':
            raise ValueError("unbalanced parentheses")
        self.pos += 1
        return ('group', gnum, node)

    def _class(self):
        self.pos += 1  # skip '['
        negated = False
        if self._peek() == '^':
            negated = True
            self.pos += 1
        chars = set()
        first = True
        while True:
            if self.pos >= len(self.pat):
                raise ValueError("unterminated character class")
            c = self.pat[self.pos]
            if c == ']' and not first:
                self.pos += 1
                break
            first = False
            # parse one item
            item = self._class_item()
            if item is None:
                # it was ']' as first char
                chars.add(']')
                continue
            # check for range
            if isinstance(item, str) and self.pos < len(self.pat) and self.pat[self.pos] == '-':
                # look ahead: is the char after '-' a ']' or end?
                if self.pos + 1 < len(self.pat) and self.pat[self.pos + 1] != ']':
                    self.pos += 1  # skip '-'
                    item2 = self._class_item()
                    if item2 is None:
                        # ']' after '-' → literal '-' and literal ']'
                        chars.add(item)
                        chars.add('-')
                        chars.add(']')
                        self.pos += 1  # skip ']'
                        continue
                    if not isinstance(item2, str):
                        raise ValueError("invalid range in character class")
                    if ord(item) > ord(item2):
                        raise ValueError("invalid range in character class")
                    for ch in range(ord(item), ord(item2) + 1):
                        chars.add(chr(ch))
                    continue
                else:
                    # '-' at end or followed by ']' → literal '-'
                    chars.add(item)
                    chars.add('-')
                    continue
            chars.add(item)
        return ('cls', frozenset(chars), negated)

    def _class_item(self):
        c = self.pat[self.pos]
        if c == ']' and self.pos == self._class_start + (1 if self._neg else 0):
            # handled externally
            pass
        if c == '\\':
            self.pos += 1
            if self.pos >= len(self.pat):
                raise ValueError("backslash at end of pattern")
            e = self.pat[self.pos]
            self.pos += 1
            if e == 'd':
                return _DIGITS
            if e == 'D':
                return _DIGITS  # will be negated externally; handled below
            if e == 'w':
                return _WORD
            if e == 'W':
                return _WORD
            if e == 's':
                return _SPACE
            if e == 'S':
                return _SPACE
            if e == 'n':
                return '\n'
            if e == 't':
                return '\t'
            if e.isalpha() or e.isdigit():
                raise ValueError("invalid escape in character class")
            return e
        self.pos += 1
        return c

    def _class(self):
        self.pos += 1  # skip '['
        negated = False
        if self._peek() == '^':
            negated = True
            self.pos += 1
        chars = set()
        first = True
        while True:
            if self.pos >= len(self.pat):
                raise ValueError("unterminated character class")
            if self.pat[self.pos] == ']' and not first:
                self.pos += 1
                break
            first = False
            item, is_esc, esc_neg = self._class_item_full()
            if item is None:
                # literal ']' as first char
                chars.add(']')
                continue
            # check range
            if not is_esc and self.pos < len(self.pat) and self.pat[self.pos] == '-':
                if self.pos + 1 < len(self.pat) and self.pat[self.pos + 1] != ']':
                    self.pos += 1  # skip '-'
                    item2, is_esc2, esc_neg2 = self._class_item_full()
                    if item2 is None:
                        chars.add(item)
                        chars.add('-')
                        chars.add(']')
                        self.pos += 1
                        continue
                    if is_esc2:
                        raise ValueError("class-escape in range")
                    if ord(item) > ord(item2):
                        raise ValueError("invalid range")
                    for ch in range(ord(item), ord(item2) + 1):
                        chars.add(chr(ch))
                    continue
                else:
                    chars.add(item)
                    chars.add('-')
                    continue
            if is_esc:
                if esc_neg:
                    chars |= (_ALL_ASCII - item)
                else:
                    chars |= item
            else:
                chars.add(item)
        return ('cls', frozenset(chars), negated)

    def _class_item_full(self):
        """Return (char_or_set, is_escape, esc_negated). None means literal ']' first char."""
        c = self.pat[self.pos]
        if c == '\\':
            self.pos += 1
            if self.pos >= len(self.pat):
                raise ValueError("backslash at end of pattern")
            e = self.pat[self.pos]
            self.pos += 1
            if e == 'd':
                return (_DIGITS, True, False)
            if e == 'D':
                return (_DIGITS, True, True)
            if e == 'w':
                return (_WORD, True, False)
            if e == 'W':
                return (_WORD, True, True)
            if e == 's':
                return (_SPACE, True, False)
            if e == 'S':
                return (_SPACE, True, True)
            if e == 'n':
                return ('\n', False, False)
            if e == 't':
                return ('\t', False, False)
            if e.isalpha() or e.isdigit():
                raise ValueError("invalid escape in character class")
            return (e, False, False)
        self.pos += 1
        return (c, False, False)


# ─── Compiler ─────────────────────────────────────────────────────────────────

class _Compiler:
    def __init__(self, ngroups):
        self.code = []
        self.ngroups = ngroups
        self._counter_id = 0
        self._mark_id = 0

    def compile(self, ast):
        self._emit(ast)
        self.code.append(('accept',))
        return self.code

    def _emit(self, node):
        kind = node[0]
        if kind == 'lit':
            self.code.append(('lit', node[1]))
        elif kind == 'any':
            self.code.append(('any',))
        elif kind == 'cls':
            self.code.append(('cls', node[1], node[2]))
        elif kind == 'start':
            self.code.append(('start',))
        elif kind == 'end':
            self.code.append(('end',))
        elif kind == 'empty':
            pass
        elif kind == 'concat':
            for item in node[1]:
                self._emit(item)
        elif kind == 'alt':
            self._emit_alt(node[1])
        elif kind == 'group':
            gnum = node[1]
            self.code.append(('cap_start', gnum))
            self._emit(node[2])
            self.code.append(('cap_end', gnum))
        elif kind == 'nongroup':
            self._emit(node[1])
        elif kind == 'quant':
            self._emit_quant(node[1], node[2], node[3], node[4])
        else:
            raise ValueError("unknown node")

    def _emit_alt(self, branches):
        if len(branches) == 1:
            self._emit(branches[0])
            return
        split_pc = len(self.code)
        self.code.append(None)  # placeholder
        self._emit(branches[0])
        jump_pc = len(self.code)
        self.code.append(None)  # placeholder jump
        rest_start = len(self.code)
        self._emit_alt(branches[1:])
        self.code[split_pc] = ('split', split_pc + 1, rest_start)
        self.code[jump_pc] = ('jump', len(self.code))

    def _emit_quant(self, child, lo, hi, greedy):
        if lo == 0 and hi == 0:
            return  # skip entirely
        cid = self._counter_id
        self._counter_id += 1
        mid = self._mark_id
        self._mark_id += 1
        check_pc = len(self.code)
        self.code.append(None)  # placeholder loop check
        body_start = len(self.code)
        self._emit(child)
        self.code.append(('loop_back', cid, check_pc))
        exit_pc = len(self.code)
        self.code[check_pc] = ('loop', body_start, exit_pc, cid, lo, hi, greedy, mid)


# ─── Matcher ──────────────────────────────────────────────────────────────────

class _Matcher:
    def __init__(self, code, ngroups, s, fullmatch):
        self.code = code
        self.ngroups = ngroups
        self.s = s
        self.n = len(s)
        self.fullmatch = fullmatch
        self.memo = set()

    def run(self, start):
        code = self.code
        s = self.s
        n = self.n
        ngroups = self.ngroups
        fullmatch = self.fullmatch
        memo = self.memo

        pc = 0
        pos = start
        captures = [(-1, -1)] * (ngroups + 1)  # index 0 unused for groups
        cap_starts = [-1] * (ngroups + 1)
        counters = [0] * self._counter_count()
        marks = [-1] * self._mark_count()
        stack = []

        while True:
            # memo check
            if (pc, pos) in memo:
                if not stack:
                    return None
                pc, pos, captures, cap_starts, counters, marks, action = stack.pop()
                if action is not None:
                    self._do_action(action, marks, counters)
                continue

            instr = code[pc]
            tag = instr[0]

            if tag == 'accept':
                if fullmatch and pos != n:
                    memo.add((pc, pos))
                    if not stack:
                        return None
                    pc, pos, captures, cap_starts, counters, marks, action = stack.pop()
                    if action is not None:
                        self._do_action(action, marks, counters)
                    continue
                # success
                spans = [(-1, -1)] * (ngroups + 1)
                spans[0] = (start, pos)
                for g in range(1, ngroups + 1):
                    spans[g] = captures[g]
                return Match(s, spans, ngroups)

            elif tag == 'lit':
                if pos < n and s[pos] == instr[1]:
                    pos += 1
                    pc += 1
                else:
                    memo.add((pc, pos))
                    if not stack:
                        return None
                    pc, pos, captures, cap_starts, counters, marks, action = stack.pop()
                    if action is not None:
                        self._do_action(action, marks, counters)

            elif tag == 'any':
                if pos < n and s[pos] != '\n':
                    pos += 1
                    pc += 1
                else:
                    memo.add((pc, pos))
                    if not stack:
                        return None
                    pc, pos, captures, cap_starts, counters, marks, action = stack.pop()
                    if action is not None:
                        self._do_action(action, marks, counters)

            elif tag == 'cls':
                cset, neg = instr[1], instr[2]
                if pos < n:
                    ch = s[pos]
                    ok = (ch in cset) if not neg else (ch not in cset)
                    if ok:
                        pos += 1
                        pc += 1
                        continue
                memo.add((pc, pos))
                if not stack:
                    return None
                pc, pos, captures, cap_starts, counters, marks, action = stack.pop()
                if action is not None:
                    self._do_action(action, marks, counters)

            elif tag == 'start':
                if pos == 0:
                    pc += 1
                else:
                    memo.add((pc, pos))
                    if not stack:
                        return None
                    pc, pos, captures, cap_starts, counters, marks, action = stack.pop()
                    if action is not None:
                        self._do_action(action, marks, counters)

            elif tag == 'end':
                if pos == n or (pos == n - 1 and s[pos] == '\n'):
                    pc += 1
                else:
                    memo.add((pc, pos))
                    if not stack:
                        return None
                    pc, pos, captures, cap_starts, counters, marks, action = stack.pop()
                    if action is not None:
                        self._do_action(action, marks, counters)

            elif tag == 'split':
                _, pc1, pc2 = instr
                stack.append((pc2, pos, captures[:], cap_starts[:], counters[:], marks[:], None))
                pc = pc1

            elif tag == 'jump':
                pc = instr[1]

            elif tag == 'cap_start':
                cap_starts[instr[1]] = pos
                pc += 1

            elif tag == 'cap_end':
                g = instr[1]
                captures[g] = (cap_starts[g], pos)
                pc += 1

            elif tag == 'loop':
                _, body_pc, exit_pc, cid, lo, hi, greedy, mid = instr
                c = counters[cid]
                if c < lo:
                    # forced iteration
                    pc = body_pc
                    continue
                # optional
                if hi is not None and c >= hi:
                    pc = exit_pc
                    continue
                if pos == marks[mid]:
                    if greedy:
                        pc = exit_pc
                    else:
                        memo.add((pc, pos))
                        if not stack:
                            return None
                        pc, pos, captures, cap_starts, counters, marks, action = stack.pop()
                        if action is not None:
                            self._do_action(action, marks, counters)
                    continue
                if greedy:
                    stack.append((exit_pc, pos, captures[:], cap_starts[:], counters[:], marks[:], None))
                    marks[mid] = pos
                    pc = body_pc
                else:
                    stack.append((body_pc, pos, captures[:], cap_starts[:], counters[:], marks[:],
                                  ('set_mark_inc', mid, pos, cid)))
                    pc = exit_pc

            elif tag == 'loop_back':
                _, cid, check_pc = instr
                counters[cid] += 1
                pc = check_pc

            else:
                raise ValueError("unknown instruction")

    def _do_action(self, action, marks, counters):
        if action[0] == 'set_mark_inc':
            _, mid, mpos, cid = action
            marks[mid] = mpos
            counters[cid] += 1

    def _counter_count(self):
        cnt = 0
        for instr in self.code:
            if instr[0] == 'loop':
                cnt = max(cnt, instr[4] + 1)
            if instr[0] == 'loop_back':
                cnt = max(cnt, instr[1] + 1)
        return cnt + 1

    def _mark_count(self):
        cnt = 0
        for instr in self.code:
            if instr[0] == 'loop':
                cnt = max(cnt, instr[7] + 1)
        return cnt + 1
