"""Backtracking-priority regular-expression engine (no re/regex/fnmatch/glob)."""

# ─── Character-class constants (ASCII) ───────────────────────────────────────
_DIGIT = set(range(48, 58))
_WORD = set(range(48, 58)) | set(range(65, 91)) | {95} | set(range(97, 123))
_SPACE = {32, 9, 10, 13, 12, 11}
_ALL_ASCII = set(range(128))

_ESCAPE_SETS = {
    'd': _DIGIT, 'D': _ALL_ASCII - _DIGIT,
    'w': _WORD,  'W': _ALL_ASCII - _WORD,
    's': _SPACE, 'S': _ALL_ASCII - _SPACE,
}

# ─── AST nodes ───────────────────────────────────────────────────────────────
class _Lit:
    __slots__ = ('ch',)
    def __init__(self, ch): self.ch = ch

class _Dot:
    __slots__ = ()

class _Cls:
    __slots__ = ('match_set',)
    def __init__(self, ms): self.match_set = ms

class _Seq:
    __slots__ = ('children',)
    def __init__(self, ch): self.children = ch

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, br): self.branches = br

class _Grp:
    __slots__ = ('idx', 'child')
    def __init__(self, i, c): self.idx = i; self.child = c

class _NC:
    __slots__ = ('child',)
    def __init__(self, c): self.child = c

class _Q:
    __slots__ = ('child', 'lo', 'hi', 'greedy')
    def __init__(self, c, lo, hi, g): self.child = c; self.lo = lo; self.hi = hi; self.greedy = g

class _AS:
    __slots__ = ()

class _AE:
    __slots__ = ()

# ─── Parser ──────────────────────────────────────────────────────────────────
class _Parser:
    def __init__(self, pat):
        self.p = pat
        self.n = len(pat)
        self.i = 0
        self.ng = 0  # number of capturing groups

    def _peek(self):
        return self.p[self.i] if self.i < self.n else None

    def _adv(self):
        c = self.p[self.i]; self.i += 1; return c

    def parse(self):
        r = self._alt()
        if self.i != self.n:
            raise ValueError("unexpected character")
        return r

    def _alt(self):
        branches = [self._seq()]
        while self._peek() == '|':
            self._adv()
            branches.append(self._seq())
        return branches[0] if len(branches) == 1 else _Alt(branches)

    def _seq(self):
        items = []
        prev_q = False
        while True:
            c = self._peek()
            if c is None or c in ('|', ')'):
                break
            # quantifier with nothing to repeat
            if c in ('*', '+', '?'):
                if prev_q:
                    raise ValueError("multiple quantifiers")
                raise ValueError("nothing to repeat")
            if c == '{':
                if prev_q:
                    raise ValueError("multiple quantifiers")
                raise ValueError("nothing to repeat")
            atom = self._atom()
            q = self._try_quant()
            if q is not None:
                if prev_q:
                    raise ValueError("multiple quantifiers")
                if isinstance(atom, (_AS, _AE)):
                    raise ValueError("cannot quantify anchor")
                lo, hi = q
                greedy = True
                if self._peek() == '?':
                    self._adv()
                    greedy = False
                atom = _Q(atom, lo, hi, greedy)
                prev_q = True
            else:
                prev_q = False
            items.append(atom)
        if not items:
            return _Seq([])
        return items[0] if len(items) == 1 else _Seq(items)

    def _try_quant(self):
        c = self._peek()
        if c == '*':
            self._adv(); return (0, None)
        if c == '+':
            self._adv(); return (1, None)
        if c == '?':
            self._adv(); return (0, 1)
        if c == '{':
            self._adv()
            m_s = ''
            while self._peek() is not None and self._peek().isdigit():
                m_s += self._adv()
            if not m_s:
                raise ValueError("invalid quantifier")
            if self._peek() == ',':
                self._adv()
                n_s = ''
                while self._peek() is not None and self._peek().isdigit():
                    n_s += self._adv()
                if self._peek() == '}':
                    self._adv()
                    m = int(m_s)
                    n = int(n_s) if n_s else None
                    if n is not None and m > n:
                        raise ValueError("m > n")
                    return (m, n)
                raise ValueError("invalid quantifier")
            if self._peek() == '}':
                self._adv()
                v = int(m_s)
                return (v, v)
            raise ValueError("invalid quantifier")
        return None

    def _atom(self):
        c = self._peek()
        if c is None:
            raise ValueError("unexpected end")
        if c == '.':
            self._adv(); return _Dot()
        if c == '^':
            self._adv(); return _AS()
        if c == '$':
            self._adv(); return _AE()
        if c == '[':
            return self._cls()
        if c == '(':
            return self._grp()
        if c == '\\':
            return self._esc_atom()
        if c in ('*', '+', '?', '{'):
            raise ValueError("nothing to repeat")
        self._adv(); return _Lit(c)

    def _esc_atom(self):
        self._adv()  # backslash
        if self.i >= self.n:
            raise ValueError("trailing backslash")
        c = self._adv()
        if c in 'dDwWsS':
            return _Cls(_ESCAPE_SETS[c])
        if c == 'n':
            return _Lit('\n')
        if c == 't':
            return _Lit('\t')
        if c.isalpha() or c.isdigit():
            raise ValueError(f"invalid escape \\{c}")
        return _Lit(c)

    def _grp(self):
        self._adv()  # '('
        if self._peek() == '?':
            self._adv()
            if self._peek() == ':':
                self._adv()
                child = self._alt()
                if self._peek() != ')':
                    raise ValueError("unbalanced parens")
                self._adv()
                return _NC(child)
            raise ValueError("unsupported group syntax")
        self.ng += 1
        idx = self.ng
        child = self._alt()
        if self._peek() != ')':
            raise ValueError("unbalanced parens")
        self._adv()
        return _Grp(idx, child)

    def _cls(self):
        self._adv()  # '['
        neg = False
        if self._peek() == '^':
            neg = True; self._adv()
        ms = set()
        first = True
        while True:
            if self.i >= self.n:
                raise ValueError("unclosed class")
            if self._peek() == ']' and not first:
                self._adv(); break
            # parse one item
            ch, is_esc = self._cls_item()
            if is_esc:
                # class escape – check for illegal range
                if self._peek() == '-' and self.i + 1 < self.n and self.p[self.i + 1] != ']':
                    raise ValueError("invalid range with class escape")
                ms.update(_ESCAPE_SETS[ch])
                first = False
                continue
            # single character item
            first = False
            if self._peek() == '-' and self.i + 1 < self.n and self.p[self.i + 1] != ']':
                self._adv()  # consume '-'
                ech, eesc = self._cls_item()
                if eesc:
                    raise ValueError("invalid range endpoint")
                if ord(ch) > ord(ech):
                    raise ValueError("invalid range")
                for o in range(ord(ch), ord(ech) + 1):
                    ms.add(o)
            else:
                ms.add(ord(ch))
        if neg:
            ms = _ALL_ASCII - ms
        return _Cls(ms)

    def _cls_item(self):
        """Return (char, is_escape). is_escape=True means it's a class escape like \\d."""
        if self._peek() == '\\':
            self._adv()
            if self.i >= self.n:
                raise ValueError("trailing backslash in class")
            c = self._adv()
            if c in 'dDwWsS':
                return (c, True)
            if c == 'n':
                return ('\n', False)
            if c == 't':
                return ('\t', False)
            if c.isalpha() or c.isdigit():
                raise ValueError(f"invalid escape in class \\{c}")
            return (c, False)
        if self._peek() == ']' and self.i == self._cls_start_check():
            # ']' as first char – handled by caller via 'first' flag
            pass
        return (self._adv(), False)

    def _cls_start_check(self):
        return -1  # unused; first-char logic is in caller


# ─── Compiler: AST → instruction list ────────────────────────────────────────
def _count_quants(node):
    if isinstance(node, _Q):
        return 1 + _count_quants(node.child)
    if isinstance(node, _Seq):
        return sum(_count_quants(c) for c in node.children)
    if isinstance(node, _Alt):
        return sum(_count_quants(c) for c in node.branches)
    if isinstance(node, (_Grp, _NC)):
        return _count_quants(node.child)
    return 0


def _compile(node, instrs, qid_ref):
    """Append instructions for *node*. qid_ref is a single-element list [next_qid]."""
    if isinstance(node, _Lit):
        instrs.append(('char', node.ch))
    elif isinstance(node, _Dot):
        instrs.append(('dot',))
    elif isinstance(node, _Cls):
        instrs.append(('class', node.match_set))
    elif isinstance(node, _AS):
        instrs.append(('as',))
    elif isinstance(node, _AE):
        instrs.append(('ae',))
    elif isinstance(node, _Seq):
        for c in node.children:
            _compile(c, instrs, qid_ref)
    elif isinstance(node, _Alt):
        _compile_alt(node.branches, instrs, qid_ref)
    elif isinstance(node, _Grp):
        instrs.append(('save', node.idx))
        _compile(node.child, instrs, qid_ref)
        instrs.append(('rest', node.idx))
    elif isinstance(node, _NC):
        _compile(node.child, instrs, qid_ref)
    elif isinstance(node, _Q):
        _compile_q(node, instrs, qid_ref)


def _compile_alt(branches, instrs, qid_ref):
    if len(branches) == 1:
        _compile(branches[0], instrs, qid_ref)
        return
    sp = len(instrs)
    instrs.append(('split', 0, 0))  # placeholder
    _compile(branches[0], instrs, qid_ref)
    jp = len(instrs)
    instrs.append(('jmp', 0))  # placeholder
    nxt = len(instrs)
    _compile_alt(branches[1:], instrs, qid_ref)
    end = len(instrs)
    instrs[sp] = ('split', sp + 1, nxt)
    instrs[jp] = ('jmp', end)


def _compile_q(node, instrs, qid_ref):
    qid = qid_ref[0]; qid_ref[0] += 1
    lo, hi, greedy = node.lo, node.hi, node.greedy
    instrs.append(('qinit', qid))
    # forced iterations
    for _ in range(lo):
        _compile(node.child, instrs, qid_ref)
        instrs.append(('qinc', qid))
    if greedy:
        loop = len(instrs)
        instrs.append(('qchk', qid, 0, hi))  # placeholder after_pc
        instrs.append(('qsm', qid))
        sp = len(instrs)
        instrs.append(('split', 0, 0))  # placeholder
        it = len(instrs)
        _compile(node.child, instrs, qid_ref)
        instrs.append(('qinc', qid))
        instrs.append(('jmp', loop))
        after = len(instrs)
        instrs[loop] = ('qchk', qid, after, hi)
        instrs[sp] = ('split', it, after)
    else:
        loop = len(instrs)
        instrs.append(('split', 0, 0))  # placeholder
        it = len(instrs)
        instrs.append(('qcf', qid, hi))
        instrs.append(('qsm', qid))
        _compile(node.child, instrs, qid_ref)
        instrs.append(('qinc', qid))
        instrs.append(('jmp', loop))
        after = len(instrs)
        instrs[loop] = ('split', after, it)


# ─── VM ──────────────────────────────────────────────────────────────────────
def _run(instrs, s, ng, nq, start, full):
    n = len(s)
    pc = 0
    pos = start
    caps = [None] * (ng + 1)
    qs = [(0, -1)] * nq  # (c, mark); -1 == None
    stk = []  # (pc, pos, caps_copy, qs_copy)
    dead = set()

    while True:
        key = (pc, pos)
        if key in dead:
            if not stk:
                return None
            pc, pos, caps, qs = stk.pop()
            continue

        op = instrs[pc][0]

        if op == 'char':
            if pos < n and s[pos] == instrs[pc][1]:
                pos += 1; pc += 1
            else:
                dead.add(key)
                if not stk: return None
                pc, pos, caps, qs = stk.pop()

        elif op == 'dot':
            if pos < n and s[pos] != '\n':
                pos += 1; pc += 1
            else:
                dead.add(key)
                if not stk: return None
                pc, pos, caps, qs = stk.pop()

        elif op == 'class':
            if pos < n and ord(s[pos]) in instrs[pc][1]:
                pos += 1; pc += 1
            else:
                dead.add(key)
                if not stk: return None
                pc, pos, caps, qs = stk.pop()

        elif op == 'as':
            if pos == 0:
                pc += 1
            else:
                dead.add(key)
                if not stk: return None
                pc, pos, caps, qs = stk.pop()

        elif op == 'ae':
            if pos == n or (pos == n - 1 and s[pos] == '\n'):
                pc += 1
            else:
                dead.add(key)
                if not stk: return None
                pc, pos, caps, qs = stk.pop()

        elif op == 'split':
            stk.append((instrs[pc][2], pos, caps[:], qs[:]))
            pc = instrs[pc][1]

        elif op == 'jmp':
            pc = instrs[pc][1]

        elif op == 'save':
            caps[instrs[pc][1]] = pos
            pc += 1

        elif op == 'rest':
            g = instrs[pc][1]
            caps[g] = (caps[g], pos)
            pc += 1

        elif op == 'accept':
            if full and pos != n:
                dead.add(key)
                if not stk: return None
                pc, pos, caps, qs = stk.pop()
            else:
                return _Match(s, start, pos, caps, ng)

        elif op == 'qinit':
            qs[instrs[pc][1]] = (0, -1)
            pc += 1

        elif op == 'qinc':
            q = instrs[pc][1]
            c, m = qs[q]
            qs[q] = (c + 1, m)
            pc += 1

        elif op == 'qsm':
            q = instrs[pc][1]
            c, m = qs[q]
            qs[q] = (c, pos)
            pc += 1

        elif op == 'qchk':
            _, q, after, hi = instrs[pc]
            c, m = qs[q]
            if (hi is not None and c >= hi) or pos == m:
                pc = after
            else:
                pc += 1

        elif op == 'qcf':
            _, q, hi = instrs[pc]
            c, m = qs[q]
            if (hi is not None and c >= hi) or pos == m:
                dead.add(key)
                if not stk: return None
                pc, pos, caps, qs = stk.pop()
            else:
                pc += 1

    return None  # unreachable


# ─── Match ───────────────────────────────────────────────────────────────────
class _Match:
    __slots__ = ('_s', '_s0', '_s1', '_caps', '_ng')

    def __init__(self, s, s0, s1, caps, ng):
        self._s = s; self._s0 = s0; self._s1 = s1; self._caps = caps; self._ng = ng

    def span(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > self._ng:
            raise IndexError("no such group")
        if n == 0:
            return (self._s0, self._s1)
        c = self._caps[n]
        if c is None:
            return (-1, -1)
        return c

    def start(self, n=0):
        return self.span(n)[0]

    def end(self, n=0):
        return self.span(n)[1]

    def group(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > self._ng:
            raise IndexError("no such group")
        if n == 0:
            return self._s[self._s0:self._s1]
        c = self._caps[n]
        if c is None:
            return None
        return self._s[c[0]:c[1]]

    def groups(self):
        out = []
        for i in range(1, self._ng + 1):
            c = self._caps[i]
            if c is None:
                out.append(None)
            else:
                out.append(self._s[c[0]:c[1]])
        return tuple(out)


# ─── Pattern ─────────────────────────────────────────────────────────────────
class Pattern:
    def __init__(self, ast, ng):
        self._ng = ng
        instrs = []
        _compile(ast, instrs, [0])
        instrs.append(('accept',))
        self._instrs = instrs
        self._nq = _count_quants(ast)

    def fullmatch(self, s):
        return _run(self._instrs, s, self._ng, self._nq, 0, True)

    def search(self, s):
        for start in range(len(s) + 1):
            r = _run(self._instrs, s, self._ng, self._nq, start, False)
            if r is not None:
                return r
        return None


# ─── Public compile ──────────────────────────────────────────────────────────
def compile(pattern):
    parser = _Parser(pattern)
    ast = parser.parse()
    return Pattern(ast, parser.ng)
