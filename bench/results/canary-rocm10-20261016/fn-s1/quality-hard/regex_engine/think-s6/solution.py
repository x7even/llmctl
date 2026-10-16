"""Backtracking-priority regular-expression engine (pure Python, no re module)."""

_DIGIT = frozenset('0123456789')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')
_ALL_ASCII = frozenset(chr(i) for i in range(128))
_NON_DIGIT = _ALL_ASCII - _DIGIT
_NON_WORD = _ALL_ASCII - _WORD
_NON_SPACE = _ALL_ASCII - _SPACE

_ESCAPE_SETS = {
    'd': _DIGIT, 'D': _NON_DIGIT,
    'w': _WORD, 'W': _NON_WORD,
    's': _SPACE, 'S': _NON_SPACE,
}


class Match:
    __slots__ = ('_s', '_captures', '_num_groups')

    def __init__(self, s, captures, num_groups):
        self._s = s
        self._captures = captures
        self._num_groups = num_groups

    def _check(self, n):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > self._num_groups:
            raise IndexError("no such group")

    def span(self, n=0):
        self._check(n)
        c = self._captures[n]
        return (-1, -1) if c is None else (c[0], c[1])

    def start(self, n=0):
        self._check(n)
        c = self._captures[n]
        return -1 if c is None else c[0]

    def end(self, n=0):
        self._check(n)
        c = self._captures[n]
        return -1 if c is None else c[1]

    def group(self, n=0):
        self._check(n)
        c = self._captures[n]
        return None if c is None else self._s[c[0]:c[1]]

    def groups(self):
        return tuple(self.group(i) for i in range(1, self._num_groups + 1))


class Pattern:
    __slots__ = ('_code', '_num_groups')

    def __init__(self, code, num_groups):
        self._code = code
        self._num_groups = num_groups

    def fullmatch(self, s):
        return _execute(self._code, s, 0, self._num_groups, True)

    def search(self, s):
        for start in range(len(s) + 1):
            r = _execute(self._code, s, start, self._num_groups, False)
            if r is not None:
                return r
        return None


# ─── Parser ────────────────────────────────────────────────────────────────────

class _Parser:
    def __init__(self, pattern):
        self.p = pattern
        self.pos = 0
        self.ngroups = 0

    def parse(self):
        node = self._alternation()
        if self.pos != len(self.p):
            raise ValueError("unmatched ')'")
        return node

    def _alternation(self):
        branches = [self._concat()]
        while self.pos < len(self.p) and self.p[self.pos] == '|':
            self.pos += 1
            branches.append(self._concat())
        return branches[0] if len(branches) == 1 else ('alt', branches)

    def _concat(self):
        items = []
        while self.pos < len(self.p) and self.p[self.pos] not in '|)':
            if items and items[-1][1] and self.p[self.pos] in '*+?{':
                raise ValueError("quantifier after quantifier")
            node, quantified = self._quantified()
            items.append((node, quantified))
        if not items:
            return ('empty',)
        if len(items) == 1:
            return items[0][0]
        return ('concat', [it[0] for it in items])

    def _quantified(self):
        atom = self._atom()
        if self.pos < len(self.p) and self.p[self.pos] in '*+?{':
            if atom[0] in ('assert_start', 'assert_end'):
                raise ValueError("quantifier after anchor")
            lo, hi, greedy = self._quantifier()
            return (('quant', atom, lo, hi, greedy), True)
        return (atom, False)

    def _quantifier(self):
        c = self.p[self.pos]
        if c == '*':
            lo, hi = 0, None
            self.pos += 1
        elif c == '+':
            lo, hi = 1, None
            self.pos += 1
        elif c == '?':
            lo, hi = 0, 1
            self.pos += 1
        elif c == '{':
            lo, hi = self._brace()
        else:
            raise ValueError("internal")
        greedy = True
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            greedy = False
            self.pos += 1
        return lo, hi, greedy

    def _brace(self):
        start = self.pos
        self.pos += 1  # skip {
        # read m
        m_start = self.pos
        while self.pos < len(self.p) and self.p[self.pos].isdigit():
            self.pos += 1
        if self.pos == m_start:
            self.pos = start
            raise ValueError("invalid quantifier")
        m = int(self.p[m_start:self.pos])
        if self.pos < len(self.p) and self.p[self.pos] == '}':
            self.pos += 1
            return m, m
        if self.pos < len(self.p) and self.p[self.pos] == ',':
            self.pos += 1
            n_start = self.pos
            while self.pos < len(self.p) and self.p[self.pos].isdigit():
                self.pos += 1
            if self.pos < len(self.p) and self.p[self.pos] == '}':
                if self.pos == n_start:
                    n = None
                else:
                    n = int(self.p[n_start:self.pos])
                self.pos += 1
                if n is not None and m > n:
                    raise ValueError("min > max in quantifier")
                return m, n
        self.pos = start
        raise ValueError("invalid quantifier")

    def _atom(self):
        if self.pos >= len(self.p):
            raise ValueError("nothing to repeat")
        c = self.p[self.pos]
        if c in '*+?':
            raise ValueError("nothing to repeat")
        if c == '{':
            # try to parse as quantifier – it's an error either way
            self._brace()  # will raise
            raise ValueError("nothing to repeat")
        if c == '(':
            return self._group()
        if c == '[':
            return self._class()
        if c == '.':
            self.pos += 1
            return ('dot',)
        if c == '^':
            self.pos += 1
            return ('assert_start',)
        if c == '$':
            self.pos += 1
            return ('assert_end',)
        if c == '\\':
            return self._escape()
        self.pos += 1
        return ('lit', c)

    def _escape(self):
        self.pos += 1  # skip backslash
        if self.pos >= len(self.p):
            raise ValueError("backslash at end of pattern")
        c = self.p[self.pos]
        if c in 'dDwWsS':
            self.pos += 1
            return ('class', _ESCAPE_SETS[c])
        if c == 'n':
            self.pos += 1
            return ('lit', '\n')
        if c == 't':
            self.pos += 1
            return ('lit', '\t')
        if not c.isalnum():
            self.pos += 1
            return ('lit', c)
        raise ValueError("invalid escape")

    def _group(self):
        self.pos += 1  # skip (
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            if self.pos + 1 < len(self.p) and self.p[self.pos + 1] == ':':
                self.pos += 2
                inner = self._alternation()
                if self.pos >= len(self.p) or self.p[self.pos] != ')':
                    raise ValueError("unmatched (")
                self.pos += 1
                return ('noncap', inner)
            raise ValueError("unsupported group syntax")
        self.ngroups += 1
        g = self.ngroups
        inner = self._alternation()
        if self.pos >= len(self.p) or self.p[self.pos] != ')':
            raise ValueError("unmatched (")
        self.pos += 1
        return ('group', g, inner)

    def _class(self):
        self.pos += 1  # skip [
        negated = False
        if self.pos < len(self.p) and self.p[self.pos] == '^':
            negated = True
            self.pos += 1
        chars = set()
        # first ] is literal
        if self.pos < len(self.p) and self.p[self.pos] == ']':
            chars.add(']')
            self.pos += 1
        while self.pos < len(self.p):
            if self.p[self.pos] == ']':
                self.pos += 1
                break
            item = self._class_item()
            if item[0] == 'set':
                # class escape – check for illegal range
                if (self.pos < len(self.p) and self.p[self.pos] == '-'
                        and self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']'):
                    raise ValueError("class escape in range")
                chars |= item[1]
            else:
                c = item[1]
                if (self.pos < len(self.p) and self.p[self.pos] == '-'
                        and self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']'):
                    self.pos += 1  # skip -
                    end_item = self._class_item()
                    if end_item[0] == 'set':
                        raise ValueError("class escape as range end")
                    e = end_item[1]
                    if ord(c) > ord(e):
                        raise ValueError("bad range")
                    for cp in range(ord(c), ord(e) + 1):
                        chars.add(chr(cp))
                else:
                    chars.add(c)
        else:
            raise ValueError("unterminated character class")
        if negated:
            chars = _ALL_ASCII - chars
        return ('class', frozenset(chars))

    def _class_item(self):
        if self.pos >= len(self.p):
            raise ValueError("unterminated character class")
        c = self.p[self.pos]
        if c == '\\':
            self.pos += 1
            if self.pos >= len(self.p):
                raise ValueError("backslash at end")
            c2 = self.p[self.pos]
            if c2 in 'dDwWsS':
                self.pos += 1
                return ('set', _ESCAPE_SETS[c2])
            if c2 == 'n':
                self.pos += 1
                return ('char', '\n')
            if c2 == 't':
                self.pos += 1
                return ('char', '\t')
            if not c2.isalnum():
                self.pos += 1
                return ('char', c2)
            raise ValueError("invalid escape in class")
        self.pos += 1
        return ('char', c)


# ─── Compiler ──────────────────────────────────────────────────────────────────

def _compile_ast(node, code, qid_box):
    op = node[0]
    if op == 'lit':
        code.append(('lit', node[1]))
    elif op == 'dot':
        code.append(('dot',))
    elif op == 'class':
        code.append(('class', node[1]))
    elif op == 'assert_start':
        code.append(('assert_start',))
    elif op == 'assert_end':
        code.append(('assert_end',))
    elif op == 'empty':
        pass
    elif op == 'concat':
        for child in node[1]:
            _compile_ast(child, code, qid_box)
    elif op == 'alt':
        _compile_alt(node[1], code, qid_box)
    elif op == 'group':
        code.append(('mark', node[1]))
        _compile_ast(node[2], code, qid_box)
        code.append(('mark_end', node[1]))
    elif op == 'noncap':
        _compile_ast(node[1], code, qid_box)
    elif op == 'quant':
        _compile_quant(node, code, qid_box)
    else:
        raise ValueError("internal")


def _compile_alt(branches, code, qid_box):
    if len(branches) == 1:
        _compile_ast(branches[0], code, qid_box)
        return
    jump_addrs = []
    for i in range(len(branches) - 1):
        split_addr = len(code)
        code.append(None)
        branch_start = len(code)
        _compile_ast(branches[i], code, qid_box)
        jump_addr = len(code)
        code.append(('jump', 0))
        jump_addrs.append(jump_addr)
        rest_start = len(code)
        code[split_addr] = ('split', branch_start, rest_start)
    _compile_ast(branches[-1], code, qid_box)
    end_addr = len(code)
    for ja in jump_addrs:
        code[ja] = ('jump', end_addr)


def _compile_quant(node, code, qid_box):
    child, lo, hi, greedy = node[1], node[2], node[3], node[4]
    qid = qid_box[0]
    qid_box[0] += 1

    qstart_addr = len(code)
    code.append(None)

    body_addr = len(code)
    _compile_ast(child, code, qid_box)
    code.append(('qinc', qid))
    code.append(('jump', qstart_addr))

    qnext_addr = len(code)

    if not greedy:
        lazy_check_addr = len(code)
        code.append(('lazy_check', qid, hi, body_addr))
    else:
        lazy_check_addr = -1

    code[qstart_addr] = ('qstart', qid, lo, hi, greedy, body_addr, qnext_addr, lazy_check_addr)


# ─── VM ────────────────────────────────────────────────────────────────────────

def _execute(code, s, start, num_groups, fullmatch_mode):
    slen = len(s)
    ncode = len(code)
    captures = [None] * (num_groups + 1)
    quant_state = {}
    bstack = []
    trail = []
    memo = set()

    pc = 0
    pos = start

    while True:
        if pc >= ncode:
            break
        instr = code[pc]
        op = instr[0]

        if op == 'lit':
            if pos < slen and s[pos] == instr[1]:
                pos += 1
                pc += 1
            else:
                r = _bt(bstack, trail, captures, quant_state, memo)
                if r is None:
                    return None
                pc, pos = r
                continue

        elif op == 'class':
            if pos < slen and s[pos] in instr[1]:
                pos += 1
                pc += 1
            else:
                r = _bt(bstack, trail, captures, quant_state, memo)
                if r is None:
                    return None
                pc, pos = r
                continue

        elif op == 'dot':
            if pos < slen and s[pos] != '\n':
                pos += 1
                pc += 1
            else:
                r = _bt(bstack, trail, captures, quant_state, memo)
                if r is None:
                    return None
                pc, pos = r
                continue

        elif op == 'assert_start':
            if pos == 0:
                pc += 1
            else:
                r = _bt(bstack, trail, captures, quant_state, memo)
                if r is None:
                    return None
                pc, pos = r
                continue

        elif op == 'assert_end':
            if pos == slen or (pos == slen - 1 and s[pos] == '\n'):
                pc += 1
            else:
                r = _bt(bstack, trail, captures, quant_state, memo)
                if r is None:
                    return None
                pc, pos = r
                continue

        elif op == 'assert_full_end':
            if pos == slen:
                pc += 1
            else:
                r = _bt(bstack, trail, captures, quant_state, memo)
                if r is None:
                    return None
                pc, pos = r
                continue

        elif op == 'split':
            _, t1, t2 = instr
            bstack.append((t2, pos, len(trail), None))
            pc = t1

        elif op == 'jump':
            pc = instr[1]

        elif op == 'mark':
            g = instr[1]
            trail.append(('cap', g, captures[g]))
            captures[g] = (pos, -1)
            pc += 1

        elif op == 'mark_end':
            g = instr[1]
            trail.append(('cap', g, captures[g]))
            old = captures[g]
            captures[g] = (old[0], pos) if old is not None else (pos, pos)
            pc += 1

        elif op == 'qstart':
            _, qid, lo, hi, greedy, body_addr, next_addr, lca = instr
            if (pc, pos) in memo:
                pc = next_addr
                continue
            qs = quant_state.get(qid)
            if qs is None:
                qs = [0, None]
                quant_state[qid] = qs
            count, mark = qs[0], qs[1]
            if count < lo:
                pc = body_addr
            elif greedy:
                if (hi is None or count < hi) and (mark is None or pos != mark):
                    bstack.append((next_addr, pos, len(trail), (pc, pos)))
                    trail.append(('qstate', qid, count, mark))
                    quant_state[qid] = [count, pos]
                    pc = body_addr
                else:
                    pc = next_addr
            else:
                bstack.append((lca, pos, len(trail), None))
                pc = next_addr

        elif op == 'lazy_check':
            _, qid, hi, body_addr = instr
            qs = quant_state[qid]
            count, mark = qs[0], qs[1]
            if (hi is not None and count >= hi) or (mark is not None and pos == mark):
                r = _bt(bstack, trail, captures, quant_state, memo)
                if r is None:
                    return None
                pc, pos = r
                continue
            trail.append(('qstate', qid, count, mark))
            quant_state[qid] = [count, pos]
            pc = body_addr

        elif op == 'qinc':
            qid = instr[1]
            qs = quant_state[qid]
            trail.append(('qstate', qid, qs[0], qs[1]))
            qs[0] += 1
            pc += 1

        elif op == 'match':
            if fullmatch_mode and pos != slen:
                r = _bt(bstack, trail, captures, quant_state, memo)
                if r is None:
                    return None
                pc, pos = r
                continue
            result_caps = list(captures)
            result_caps[0] = (start, pos)
            return Match(s, result_caps, num_groups)

    return None


def _bt(bstack, trail, captures, quant_state, memo):
    while bstack:
        pc_bt, pos_bt, tl, tag = bstack.pop()
        while len(trail) > tl:
            e = trail.pop()
            if e[0] == 'cap':
                captures[e[1]] = e[2]
            else:
                quant_state[e[1]] = [e[2], e[3]]
        if tag is not None:
            memo.add(tag)
        return (pc_bt, pos_bt)
    return None


# ─── Public API ────────────────────────────────────────────────────────────────

def compile(pattern: str) -> Pattern:
    parser = _Parser(pattern)
    ast = parser.parse()
    code = []
    qid_box = [0]
    _compile_ast(ast, code, qid_box)
    if pattern and pattern[-1] == '\\':
        pass  # already caught by parser
    code.append(('assert_full_end',) if False else ('match',))
    # For fullmatch we need assert_full_end before match
    # Actually let's put it at the very end always and handle in search differently.
    # Rebuild: remove last 'match', add assert_full_end + match
    code.pop()
    code.append(('assert_full_end',))
    code.append(('match',))
    return Pattern(code, parser.ngroups)
