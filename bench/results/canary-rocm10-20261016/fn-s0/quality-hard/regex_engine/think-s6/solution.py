"""
Backtracking-priority regular expression engine implemented from scratch.
No use of re, regex, fnmatch, glob, or any pattern library.
"""

_DIGIT = frozenset('0123456789')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')
_ALL_ASCII = frozenset(chr(c) for c in range(128))
_NOT_DIGIT = _ALL_ASCII - _DIGIT
_NOT_WORD = _ALL_ASCII - _WORD
_NOT_SPACE = _ALL_ASCII - _SPACE


# ─── AST Nodes ───────────────────────────────────────────────────────────────

class _Lit:
    __slots__ = ('ch',)
    def __init__(self, ch): self.ch = ch

class _Any:
    __slots__ = ()

class _Class:
    __slots__ = ('negated', 'char_set')
    def __init__(self, negated, char_set):
        self.negated = negated
        self.char_set = char_set

class _Start:
    __slots__ = ()

class _End:
    __slots__ = ()

class _Seq:
    __slots__ = ('children',)
    def __init__(self, children): self.children = children

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Group:
    __slots__ = ('child', 'num')
    def __init__(self, child, num): self.child = child; self.num = num

class _Quant:
    __slots__ = ('child', 'lo', 'hi', 'greedy')
    def __init__(self, child, lo, hi, greedy):
        self.child = child; self.lo = lo; self.hi = hi; self.greedy = greedy


# ─── Static analysis: can a node match the empty string? ─────────────────────

def _can_empty(node):
    if isinstance(node, (_Lit, _Any, _Class)):
        return False
    if isinstance(node, (_Start, _End)):
        return True
    if isinstance(node, _Seq):
        return all(_can_empty(c) for c in node.children)
    if isinstance(node, _Alt):
        return any(_can_empty(b) for b in node.branches)
    if isinstance(node, _Group):
        return _can_empty(node.child)
    if isinstance(node, _Quant):
        return node.lo == 0 or _can_empty(node.child)
    return False


# ─── Parser ──────────────────────────────────────────────────────────────────

class _Parser:
    def __init__(self, pattern):
        self.p = pattern
        self.pos = 0
        self.n = len(pattern)
        self.group_count = 0

    def parse(self):
        result = self._alt()
        if self.pos != self.n:
            raise ValueError("unexpected character")
        return result

    def _alt(self):
        branches = [self._seq()]
        while self.pos < self.n and self.p[self.pos] == '|':
            self.pos += 1
            branches.append(self._seq())
        return branches[0] if len(branches) == 1 else _Alt(branches)

    def _seq(self):
        items = []
        while self.pos < self.n and self.p[self.pos] not in ('|', ')'):
            items.append(self._quantified())
        if len(items) == 0:
            return _Seq([])
        if len(items) == 1:
            return items[0]
        return _Seq(items)

    def _quantified(self):
        atom, is_anchor = self._atom()
        if self.pos < self.n:
            ch = self.p[self.pos]
            if ch in ('*', '+', '?') or (ch == '{' and self._valid_brace()):
                if is_anchor:
                    raise ValueError("quantifier after anchor")
                lo, hi = self._quant_params()
                greedy = True
                if self.pos < self.n and self.p[self.pos] == '?':
                    greedy = False
                    self.pos += 1
                if self.pos < self.n and self.p[self.pos] == '+':
                    raise ValueError("possessive quantifier")
                return _Quant(atom, lo, hi, greedy)
        return atom

    def _valid_brace(self):
        save = self.pos
        try:
            i = self.pos + 1
            if i >= self.n: return False
            m_start = i
            while i < self.n and self.p[i] in _DIGIT: i += 1
            if i == m_start: return False
            if i < self.n and self.p[i] == ',':
                i += 1
                while i < self.n and self.p[i] in _DIGIT: i += 1
                if i >= self.n or self.p[i] != '}': return False
            else:
                if i >= self.n or self.p[i] != '}': return False
            return True
        finally:
            pass

    def _quant_params(self):
        ch = self.p[self.pos]
        if ch == '*':
            self.pos += 1; return (0, None)
        if ch == '+':
            self.pos += 1; return (1, None)
        if ch == '?':
            self.pos += 1; return (0, 1)
        # '{'
        self.pos += 1
        ms = self.pos
        while self.pos < self.n and self.p[self.pos] in _DIGIT: self.pos += 1
        m = int(self.p[ms:self.pos])
        if self.pos < self.n and self.p[self.pos] == ',':
            self.pos += 1
            if self.pos < self.n and self.p[self.pos] == '}':
                self.pos += 1; return (m, None)
            ns = self.pos
            while self.pos < self.n and self.p[self.pos] in _DIGIT: self.pos += 1
            n = int(self.p[ns:self.pos])
            if self.pos < self.n and self.p[self.pos] == '}':
                self.pos += 1
                if m > n: raise ValueError(f"{m}>{n}")
                return (m, n)
            raise ValueError("malformed quantifier")
        if self.pos < self.n and self.p[self.pos] == '}':
            self.pos += 1; return (m, m)
        raise ValueError("malformed quantifier")

    def _atom(self):
        """Returns (node, is_anchor)."""
        ch = self.p[self.pos]
        if ch == '^':
            self.pos += 1; return (_Start(), True)
        if ch == '$':
            self.pos += 1; return (_End(), True)
        if ch == '.':
            self.pos += 1; return (_Any(), False)
        if ch == '[':
            return (self._cls(), False)
        if ch == '(':
            return (self._grp(), False)
        if ch == '\\':
            return (self._esc(), False)
        self.pos += 1
        return (_Lit(ch), False)

    def _esc(self):
        self.pos += 1
        if self.pos >= self.n:
            raise ValueError("backslash at end")
        ch = self.p[self.pos]; self.pos += 1
        if ch == 'd': return _Class(False, _DIGIT)
        if ch == 'D': return _Class(False, _NOT_DIGIT)
        if ch == 'w': return _Class(False, _WORD)
        if ch == 'W': return _Class(False, _NOT_WORD)
        if ch == 's': return _Class(False, _SPACE)
        if ch == 'S': return _Class(False, _NOT_SPACE)
        if ch == 'n': return _Lit('\n')
        if ch == 't': return _Lit('\t')
        if ch.isalpha() or ch.isdigit():
            raise ValueError(f"invalid escape \\{ch}")
        return _Lit(ch)

    def _cls(self):
        self.pos += 1  # skip [
        negated = False
        if self.pos < self.n and self.p[self.pos] == '^':
            negated = True; self.pos += 1
        cset = set()
        first = True
        while True:
            if self.pos >= self.n:
                raise ValueError("unterminated class")
            if self.p[self.pos] == ']' and not first:
                self.pos += 1; break
            first = False
            item_set, item_ch = self._cls_item()
            if item_ch is not None and self.pos < self.n and self.p[self.pos] == '-':
                if self.pos + 1 >= self.n:
                    cset.add(item_ch); continue
                if self.p[self.pos + 1] == ']':
                    cset.add(item_ch); continue
                self.pos += 1  # skip -
                r_set, r_ch = self._cls_item()
                if r_ch is None:
                    raise ValueError("invalid range end")
                if item_ch > r_ch:
                    raise ValueError("invalid range")
                for c in range(ord(item_ch), ord(r_ch) + 1):
                    cset.add(chr(c))
            elif item_set is not None:
                if self.pos < self.n and self.p[self.pos] == '-':
                    if self.pos + 1 >= self.n or self.p[self.pos + 1] != ']':
                        raise ValueError("class escape in range")
                    cset.update(item_set)
                else:
                    cset.update(item_set)
            else:
                cset.add(item_ch)
        return _Class(negated, frozenset(cset))

    def _cls_item(self):
        """Returns (set_or_None, char_or_None)."""
        if self.p[self.pos] == '\\':
            self.pos += 1
            if self.pos >= self.n:
                raise ValueError("backslash at end of class")
            ch = self.p[self.pos]; self.pos += 1
            if ch == 'd': return (_DIGIT, None)
            if ch == 'D': return (_NOT_DIGIT, None)
            if ch == 'w': return (_WORD, None)
            if ch == 'W': return (_NOT_WORD, None)
            if ch == 's': return (_SPACE, None)
            if ch == 'S': return (_NOT_SPACE, None)
            if ch == 'n': return (None, '\n')
            if ch == 't': return (None, '\t')
            if ch.isalpha() or ch.isdigit():
                raise ValueError(f"invalid escape \\{ch} in class")
            return (None, ch)
        ch = self.p[self.pos]; self.pos += 1
        return (None, ch)

    def _grp(self):
        self.pos += 1  # skip (
        if self.pos + 1 < self.n and self.p[self.pos] == '?' and self.p[self.pos + 1] == ':':
            self.pos += 2
            child = self._alt()
            if self.pos >= self.n or self.p[self.pos] != ')':
                raise ValueError("unmatched (")
            self.pos += 1
            return _Group(child, 0)
        if self.pos < self.n and self.p[self.pos] == '?':
            raise ValueError("unsupported (?...) syntax")
        self.group_count += 1
        num = self.group_count
        child = self._alt()
        if self.pos >= self.n or self.p[self.pos] != ')':
            raise ValueError("unmatched (")
        self.pos += 1
        return _Group(child, num)


# ─── Compiler (AST → flat instruction list) ─────────────────────────────────

class _Compiler:
    def __init__(self):
        self.code = []
        self.num_loops = 0
        self.loop_info = []  # (lo, hi, greedy, body_can_empty)

    def compile(self, ast, num_groups):
        self._emit(ast)
        self.code.append(('match',))
        return self.code, num_groups, self.num_loops, self.loop_info

    def _emit(self, node):
        if isinstance(node, _Lit):
            self.code.append(('char', node.ch))
        elif isinstance(node, _Any):
            self.code.append(('any',))
        elif isinstance(node, _Class):
            self.code.append(('class', node.char_set, node.negated))
        elif isinstance(node, _Start):
            self.code.append(('astart',))
        elif isinstance(node, _End):
            self.code.append(('aend',))
        elif isinstance(node, _Seq):
            for c in node.children:
                self._emit(c)
        elif isinstance(node, _Alt):
            self._emit_alt(node.branches, 0)
        elif isinstance(node, _Group):
            if node.num > 0:
                self.code.append(('saves', node.num))
                self._emit(node.child)
                self.code.append(('savee', node.num))
            else:
                self._emit(node.child)
        elif isinstance(node, _Quant):
            self._emit_quant(node)

    def _emit_alt(self