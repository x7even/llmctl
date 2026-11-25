"""Backtracking-priority regular-expression engine (no external regex libraries)."""

# ─── Constants ────────────────────────────────────────────────────────────────

_DIGITS = frozenset('0123456789')
_WORD = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    'abcdefghijklmnopqrstuvwxyz'
    '0123456789_'
)
_SPACE = frozenset(' \t\n\r\f\v')
_ALL_ASCII = frozenset(chr(i) for i in range(128))
_D_SET = _ALL_ASCII - _DIGITS
_W_SET = _ALL_ASCII - _WORD
_S_SET = _ALL_ASCII - _SPACE

_CLASS_ESCAPE_SETS = {
    'd': _DIGITS, 'D': _D_SET,
    'w': _WORD,   'W': _W_SET,
    's': _SPACE,  'S': _S_SET,
}

# ─── AST Nodes ────────────────────────────────────────────────────────────────

class _Lit:
    __slots__ = ('ch',)
    def __init__(self, ch): self.ch = ch

class _Dot:
    __slots__ = ()

class _Cls:
    __slots__ = ('chars', 'negated')
    def __init__(self, chars, negated): self.chars = chars; self.negated = negated

class _Anc:
    __slots__ = ('kind',)
    def __init__(self, kind): self.kind = kind

class _Grp:
    __slots__ = ('index', 'children')
    def __init__(self, index, children): self.index = index; self.children = children

class _Ngrp:
    __slots__ = ('children',)
    def __init__(self, children): self.children = children

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Qty:
    __slots__ = ('atom', 'lo', 'hi', 'lazy')
    def __init__(self, atom, lo, hi, lazy):
        self.atom = atom; self.lo = lo; self.hi = hi; self.lazy = lazy

# ─── Parser ───────────────────────────────────────────────────────────────────

class _Parser:
    def __init__(self, s):
        self.s = s
        self.n = len(s)
        self.p = 0
        self.ngroups = 0

    def _peek(self):
        return self.s[self.p] if self.p < self.n else ''

    def _peek2(self):
        return self.s[self.p + 1] if self.p + 1 < self.n else ''

    def parse(self):
        nodes = self._alt()
        if self.p != self.n:
            raise ValueError(f"Unexpected ')' at position {self.p}")
        return nodes

    def _alt(self):
        branches = [self._seq(False)]
        while self.p < self.n and self.s[self.p] == '|':
            self.p += 1
            branches.append(self._seq(False))
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _alt_in_group(self):
        branches = [self._seq(True)]
        while self.p < self.n and self.s[self.p] == '|':
            self.p += 1
            branches.append(self._seq(True))
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _seq(self, in_group):
        items = []
        last_qty = False
        while self.p < self.n:
            ch = self.s[self.p]
            if ch == '|':
                break
            if ch == ')' and in_group:
                break
            if ch in '*+?{':
                if not items:
                    raise ValueError(f"Nothing to repeat at position {self.p}")
                if last_qty:
                    raise ValueError(f"Nothing to repeat at position {self.p}")
                raise ValueError(f"Nothing to repeat at position {self.p}")
            atom = self._atom()
            if isinstance(atom, _Anc):
                items.append(atom)
                last_qty = False
                if self.p < self.n and self.s[self.p] in '*+?{':
                    raise ValueError(f"Cannot quantify {atom.kind} at position {self.p}")
                continue
            if self.p < self.n and self.s[self.p] in '*+?{':
                lo, hi, lazy = self._quant()
                atom = _Qty(atom, lo, hi, lazy)
                last_qty = True
            else:
                last_qty = False
            items.append(atom)
        return items

    def _atom(self):
        ch = self.s[self.p]
        if ch == '(':
            return self._group()
        if ch == '[':
            return self._class()
        if ch == '.':
            self.p += 1
            return _Dot()
        if ch == '^':
            self.p += 1
            return _Anc('^')
        if ch == '$':
            self.p += 1
            return _Anc('$')
        if ch == '\\':
            return self._escape()
        self.p += 1
        return _Lit(ch)

    def _group(self):
        if self._peek2() == '?':
            if self.p + 2 < self.n and self.s[self.p + 2] == ':':
                self.p += 3
                children = self._alt_in_group()
                if self.p >= self.n or self.s[self.p] != ')':
                    raise ValueError("Unclosed group")
                self.p += 1
                return _Ngrp(children)
            else:
                raise ValueError(f"Invalid group syntax at position {self.p}")
        else:
            self.p += 1
            self.ngroups += 1
            idx = self.ngroups
            children = self._alt_in_group()
            if self.p >= self.n or self.s[self.p] != ')':
                raise ValueError("Unclosed group")
            self.p += 1
            return _Grp(idx, children)

    def _escape(self):
        self.p += 1
        if self.p >= self.n:
            raise ValueError("Backslash at end of pattern")
        ch = self.s[self.p]
        if ch in 'dDwWsS':
            self.p += 1
            return _Cls(frozenset(_CLASS_ESCAPE_SETS[ch]), ch in 'DWS')
        if ch == 'n':
            self.p += 1
            return _Lit('\n')
        if ch == 't':
            self.p += 1
            return _Lit('\t')
        if ord(ch) < 128 and not ch.isalnum():
            self.p += 1
            return _Lit(ch)
        raise ValueError(f"Invalid escape: \\{ch}")

    def _quant(self):
        ch = self.s[self.p]
        if ch == '*':
            self.p += 1
            lo, hi = 0, None
        elif ch == '+':
            self.p += 1
            lo, hi = 1, None
        elif ch == '?':
            self.p += 1
            lo, hi = 0, 1
        elif ch == '{':
            self.p += 1
            ms = self.p
            while self.p < self.n and self.s[self.p].isdigit():
                self.p += 1
            if self.p == ms:
                raise ValueError("Invalid quantifier")
            m = int(self.s[ms:self.p])
            if self.p < self.n and self.s[self.p] == ',':
                self.p += 1
                if self.p < self.n and self.s[self.p] == '}':
                    self.p += 1
                    lo, hi = m, None
                else:
                    ns = self.p
                    while self.p < self.n and self.s[self.p].isdigit():
                        self.p += 1
                    if self.p == ns:
                        raise ValueError("Invalid quantifier")
                    nn = int(self.s[ns:self.p])
                    if self.p >= self.n or self.s[self.p] != '}':
                        raise ValueError("Invalid quantifier")
                    self.p += 1
                    if m > nn:
                        raise ValueError("min > max in quantifier")
                    lo, hi = m, nn
            elif self.p < self.n and self.s[self.p] == '}':
                self.p += 1
                lo, hi = m, m
            else:
                raise ValueError("Invalid quantifier")
        else:
            raise ValueError(f"Invalid quantifier at position {self.p}")
        lazy = False
        if self.p < self.n and self.s[self.p] == '?':
            lazy = True
            self.p += 1
        return (lo, hi, lazy)

    def _class(self):
        self.p += 1  # skip [
        negated = False
        if self.p < self.n and self.s[self.p] == '^':
            negated = True
            self.p += 1
        chars = set()
        first = True
        while True:
            if self.p >= self.n:
                raise ValueError("Unclosed character class")
            ch = self.s[self.p]
            if ch == ']':
                if first:
                    chars.add(']')
                    self.p += 1
                    first = False
                    if self.p < self.n and self.s[self.p] == '-':
                        if self.p + 1 < self.n and self.s[self.p + 1] != ']':
                            self.p += 1
                            end_ch = self._cls_char()
                            if ord(']') > ord(end_ch):
                                raise ValueError("Invalid range in class")
                            for cc in range(ord(']'), ord(end_ch) + 1):
                                chars.add(chr(cc))
                        else:
                            chars.add('-')
                            self.p += 1
                    continue
                else:
                    self.p += 1
                    break
            if ch == '\\':
                self.p += 1
                if self.p >= self.n:
                    raise ValueError("Unexpected end in class")
                ech = self.s[self.p]
                if ech in 'dDwWsS':
                    self.p += 1
                    chars.update(_CLASS_ESCAPE_SETS[ech])
                    if self.p < self.n and self.s[self.p] == '-':
                        if self.p + 1 < self.n and self.s[self.p + 1] != ']':
                            raise ValueError("Class escape in range")
                        else:
                            chars.add('-')
                            self.p += 1
                    first = False
                    continue
                elif ech == 'n':
                    self.p += 1
                    c = '\n'
                elif ech == 't':
                    self.p += 1
                    c = '\t'
                elif ord(ech) < 128 and not ech.isalnum():
                    self.p += 1
                    c = ech
                else:
                    raise ValueError(f"Invalid escape in class: \\{ech}")
            else:
                c = ch
                self.p += 1
            first = False
            if self.p < self.n and self.s[self.p] == '-':
                if self.p + 1 < self.n and self.s[self.p + 1] != ']':
                    self.p += 1
                    end_ch = self._cls_char()
                    if ord(c) > ord(end_ch):
                        raise ValueError("Invalid range in class")
                    for cc in range(ord(c), ord(end_ch) + 1):
                        chars.add(chr(cc))
                else:
                    chars.add('-')
                    self.p += 1
            else:
                chars.add(c)
        return _Cls(frozenset(chars), negated)

    def _cls_char(self):
        ch = self.s[self.p]
        if ch == '\\':
            self.p += 1
            if self.p >= self.n:
                raise ValueError("Unexpected end in class")
            ech = self.s[self.p]
            if ech == 'n':
                self.p += 1
                return '\n'
            if ech == 't':
                self.p += 1
                return '\t'
            if ord(ech) < 128 and not ech.isalnum():
                self.p += 1
                return ech
            raise ValueError(f"Invalid escape in class range: \\{ech}")
        else:
            self.p += 1
            return ch

# ─── Compiler ─────────────────────────────────────────────────────────────────

def _compile_top(nodes):
    instrs = []
    for node in nodes:
        _cnode(node, instrs)
    instrs.append(('end',))
    return instrs

def _cnode(node, instrs):
    if isinstance(node, _Lit):
        instrs.append(('match', ('pos', frozenset([node.ch]))))
    elif isinstance(node, _Dot):
        instrs.append(('match', ('dot',)))
    elif isinstance(node, _Cls):
        if node.negated:
            instrs.append(('match', ('neg', node.chars)))
        else:
            instrs.append(('match', ('pos', node.chars)))
    elif isinstance(node, _Anc):
        instrs.append(('anchor', node.kind))
    elif isinstance(node, _Grp):
        instrs.append(('gstart', node.index))
        for child in node.children:
            _cnode(child, instrs)
        instrs.append(('gend', node.index))
    elif isinstance(node, _Ngrp):
        for child in node.children:
            _cnode(child, instrs)
    elif isinstance(node, _Alt):
        _calt(node, instrs)
    elif isinstance(node, _Qty):
        _cqty(node, instrs)

def _calt(node, instrs):
    branch_instrs = []
    for branch in node.branches:
        bi = []
        for child in branch:
            _cnode(child, bi)
        branch_instrs.append(bi)
    base = len(instrs)
    branch_starts = []
    off = 1
    for bi in branch_instrs:
        branch_starts.append(base + off)
        off += len(bi) + 1
    end_pc = base + off
    instrs.append(('branch', branch_starts))
    for bi in branch_instrs:
        instrs.extend(bi)
        instrs.append(('jump', end_pc))

def _cqty(node, instrs):
    atom_instrs = []
    _cnode(node.atom, atom_instrs)
    base = len(instrs)
    atom_pc = base + 1
    check_pc = base + 1 + len(atom_instrs)
    after_pc = check_pc + 1
    instrs.append(('qinit', node.lo, node.hi, node.lazy, atom_pc, check_pc, after_pc))
    instrs.extend(atom_instrs)
    instrs.append(('qcheck',))
    instrs.append(('qend',))

# ─── VM ───────────────────────────────────────────────────────────────────────

def _vm(instrs, s, ngroups, start_pos, full):
    n = len(s)
    pos = start_pos
    captures = [None] * (ngroups + 1)
    gstarts = [None] * (ngroups + 1)
    qstack = []
    bstack = []
    pc = 0

    while True:
        instr = instrs[pc]
        it = instr[0]

        if it == 'match':
            matcher = instr[1]
            if pos >= n:
                if not bstack:
                    return None
                e = bstack.pop()
                pos, captures = e[1], e[2]
                pc = _exec_bentry(e, qstack, bstack)
                if pc is None:
                    continue
                continue
            c = s[pos]
            mt = matcher[0]
            if mt == 'dot':
                ok = c != '\n'
            elif mt == 'pos':
                ok = c in matcher[1]
            else:
                ok = c not in matcher[1]
            if ok:
                pos += 1
                pc += 1
            else:
                if not bstack:
                    return None
                e = bstack.pop()
                pos, captures = e[1], e[2]
                pc = _exec_bentry(e, qstack, bstack)
                if pc is None:
                    continue
                continue

        elif it == 'anchor':
            kind = instr[1]
            if kind == '^':
                ok = (pos == 0)
            else:
                ok = (pos == n) or (pos == n - 1 and n > 0 and s[pos] == '\n')
            if ok:
                pc += 1
            else:
                if not bstack:
                    return None
                e = bstack.pop()
                pos, captures = e[1], e[2]
                pc = _exec_bentry(e, qstack, bstack)
                if pc is None:
                    continue
                continue

        elif it == 'gstart':
            gstarts[instr[1]] = pos
            pc += 1

        elif it == 'gend':
            idx = instr[1]
            captures[idx] = (gstarts[idx], pos)
            pc += 1

        elif it == 'branch':
            targets = instr[1]
            if len(targets) > 1:
                bstack.append(('br', targets[1:], pos, list(captures)))
            pc = targets[0]

        elif it == 'jump':
            pc = instr[1]

        elif it == 'qinit':
            _, lo, hi, lazy, atom_pc, check_pc, after_pc = instr
            qstack.append([0, None, lo, hi, lazy, atom_pc, after_pc])
            # Check if we need to do a forced iteration or go to optional phase
            if lo > 0:
                pc = atom_pc
            else:
                # c=0 >= lo, optional phase
                if not lazy:
                    if (hi is None or 0 < hi) and pos != None:
                        qstack[-1][1] = pos
                        bstack.append(('jmp', after_pc, pos, list(captures)))
                        pc = atom_pc
                    else:
                        pc = after_pc
                else:
                    bstack.append(('qr', 0, None, lo, hi, lazy, atom_pc, after_pc, pos, list(captures)))
                    pc = after_pc

        elif it == 'qcheck':
            qs = qstack[-1]
            qs[0] += 1
            c, mark, lo, hi, lazy, atom_pc, after_pc = qs
            if c <= lo:
                pc = atom_pc
            else:
                if not lazy:
                    if (hi is None or c < hi) and pos != mark:
                        qs[1] = pos
                        bstack.append(('jmp', after_pc, pos, list(captures)))
                        pc = atom_pc
                    else:
                        pc = after_pc
                else:
                    bstack.append(('qr', c, mark, lo, hi, lazy, atom_pc, after_pc, pos, list(captures)))
                    pc = after_pc

        elif it == 'qend':
            if qstack:
                qstack.pop()
            pc += 1

        elif it == 'end':
            if full:
                if pos == n:
                    captures[0] = (start_pos, pos)
                    return captures
                if not bstack:
                    return None
                e = bstack.pop()
                pos, captures = e[1], e[2]
                pc = _exec_bentry(e, qstack, bstack)
                if pc is None:
                    continue
            else:
                captures[0] = (start_pos, pos)
                return captures


def _exec_bentry(e, qstack, bstack):
    """Execute a backtrack entry. Returns new pc or None (fail)."""
    et = e[0]
    if et == 'jmp':
        return e[1]
    elif et == 'br':
        targets = e[1]
        pos = e[2]
        if not targets:
            return None
        if len(targets) > 1:
            bstack.append(('br', targets[1:], pos, list(e[3])))
        return targets[0]
    elif et == 'qr':
        _, c, mark, lo, hi, lazy, atom_pc, after_pc, pos, caps = e
        qstack.append([c, mark, lo, hi, lazy, atom_pc, after_pc])
        if (hi is not None and c >= hi) or pos == mark:
            qstack.pop()
            return None
        qstack[-1][1] = pos
        bstack.append(('fail',))
        return atom_pc
    elif et == 'fail':
        return None
    return None


# ─── Public API ───────────────────────────────────────────────────────────────

class Match:
    __slots__ = ('_s', '_caps', '_ng')

    def __init__(self, s, caps, ng):
        self._s = s
        self._caps = caps
        self._ng = ng

    def _chk(self, n):
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError(n)
        if n < 0 or n > self._ng:
            raise IndexError(n)

    def span(self, n=0):
        self._chk(n)
        c = self._caps[n]
        if c is None:
            return (-1, -1)
        return c

    def start(self, n=0):
        self._chk(n)
        c = self._caps[n]
        if c is None:
            return -1
        return c[0]

    def end(self, n=0):
        self._chk(n)
        c = self._caps[n]
        if c is None:
            return -1
        return c[1]

    def group(self, n=0):
        self._chk(n)
        c = self._caps[n]
        if c is None:
            return None
        return self._s[c[0]:c[1]]

    def groups(self):
        return tuple(self.group(i) for i in range(1, self._ng + 1))


class Pattern:
    __slots__ = ('_instrs', '_ng')

    def __init__(self, instrs, ng):
        self._instrs = instrs
        self._ng = ng

    def fullmatch(self, s):
        caps = _vm(self._instrs, s, self._ng, 0, True)
        if caps is None:
            return None
        return Match(s, caps, self._ng)

    def search(self, s):
        for start in range(len(s) + 1):
            caps = _vm(self._instrs, s, self._ng, start, False)
            if caps is not None:
                return Match(s, caps, self._ng)
        return None


def compile(pattern: str) -> Pattern:
    parser = _Parser(pattern)
    ast = parser.parse()
    ng = parser.ngroups
    instrs = _compile_top(ast)
    return Pattern(instrs, ng)
