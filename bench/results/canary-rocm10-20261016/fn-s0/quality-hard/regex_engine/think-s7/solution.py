import sys
sys.setrecursionlimit(200000)

INF = float('inf')

# ─── AST Nodes ───

class _Lit:
    __slots__ = ('char','_id')
    def __init__(self, char): self.char=char; self._id=id(self)

class _Dot:
    __slots__ = ('_id',)
    def __init__(self): self._id=id(self)

class _Class:
    __slots__ = ('items','negated','_id')
    def __init__(self, items, negated): self.items=items; self.negated=negated; self._id=id(self)

class _Group:
    __slots__ = ('index','child','_id')
    def __init__(self, index, child): self.index=index; self.child=child; self._id=id(self)

class _Seq:
    __slots__ = ('children','_id')
    def __init__(self, children): self.children=children; self._id=id(self)

class _Alt:
    __slots__ = ('branches','_id')
    def __init__(self, branches): self.branches=branches; self._id=id(self)

class _Quant:
    __slots__ = ('child','lo','hi','greedy','_id')
    def __init__(self, child, lo, hi, greedy): self.child=child; self.lo=lo; self.hi=hi; self.greedy=greedy; self._id=id(self)

class _AncS:
    __slots__ = ('_id',)
    def __init__(self): self._id=id(self)

class _AncE:
    __slots__ = ('_id',)
    def __init__(self): self._id=id(self)

# ─── Parser ───

_DIGITS = set('0123456789')
_LETTERS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')

def _is_digit(c): return c in _DIGITS
def _is_alpha(c): return c in _LETTERS

class _Parser:
    def __init__(self, pattern):
        self.p = pattern
        self.pos = 0
        self.ngroups = 0

    def _eof(self): return self.pos >= len(self.p)
    def _peek(self): return self.p[self.pos] if self.pos < len(self.p) else None
    def _adv(self): c = self.p[self.pos]; self.pos += 1; return c

    def parse(self):
        node = self._alt()
        if self.pos != len(self.p):
            raise ValueError("unbalanced parentheses")
        return node

    def _alt(self):
        branches = [self._seq()]
        while not self._eof() and self.p[self.pos] == '|':
            self.pos += 1
            branches.append(self._seq())
        return branches[0] if len(branches) == 1 else _Alt(branches)

    def _seq(self):
        items = []
        while not self._eof() and self.p[self.pos] not in ('|', ')'):
            items.append(self._quantified())
        if not items: return _Seq([])
        return items[0] if len(items) == 1 else _Seq(items)

    def _quantified(self):
        atom = self._atom()
        q = self._try_quantifier()
        if q is not None:
            if isinstance(atom, (_AncS, _AncE)):
                raise ValueError("cannot quantify anchor")
            lo, hi, greedy = q
            return _Quant(atom, lo, hi, greedy)
        return atom

    def _atom(self):
        if self._eof():
            return _Seq([])
        c = self.p[self.pos]
        if c == '(':
            return self._group()
        if c == '[':
            return self._class()
        if c == '.':
            self.pos += 1; return _Dot()
        if c == '^':
            self.pos += 1; return _AncS()
        if c == '$':
            self.pos += 1; return _AncE()
        if c == '\\':
            return self._escape_atom()
        if c in ('*','+','?','{'):
            raise ValueError("quantifier with nothing to repeat")
        self.pos += 1
        return _Lit(c)

    def _try_quantifier(self):
        if self._eof(): return None
        c = self.p[self.pos]
        if c in ('*','+','?'):
            self.pos += 1
            greedy = True
            if not self._eof() and self.p[self.pos] == '?':
                self.pos += 1; greedy = False
            if c == '*': return (0, INF, greedy)
            if c == '+': return (1, INF, greedy)
            return (0, 1, greedy)
        if c == '{':
            return self._try_brace()
        return None

    def _try_brace(self):
        save = self.pos
        self.pos += 1  # skip {
        ms = self.pos
        while not self._eof() and _is_digit(self.p[self.pos]): self.pos += 1
        if self.pos == ms:
            self.pos = save; raise ValueError("invalid quantifier")
        m = int(self.p[ms:self.pos])
        if not self._eof() and self.p[self.pos] == '}':
            self.pos += 1
            greedy = True
            if not self._eof() and self.p[self.pos] == '?': self.pos += 1; greedy = False
            return (m, m, greedy)
        if not self._eof() and self.p[self.pos] == ',':
            self.pos += 1
            ns = self.pos
            while not self._eof() and _is_digit(self.p[self.pos]): self.pos += 1
            if not self._eof() and self.p[self.pos] == '}':
                self.pos += 1
                greedy = True
                if not self._eof() and self.p[self.pos] == '?': self.pos += 1; greedy = False
                if ns == self.pos - 1: return (m, INF, greedy)
                n = int(self.p[ns:self.pos-1])
                if m > n: raise ValueError("m > n in quantifier")
                return (m, n, greedy)
        self.pos = save
        raise ValueError("invalid quantifier")

    def _group(self):
        self.pos += 1  # skip (
        if not self._eof() and self.p[self.pos] == '?':
            if self.pos + 1 < len(self.p) and self.p[self.pos+1] == ':':
                self.pos += 2
                child = self._alt()
                if self._eof() or self.p[self.pos] != ')': raise ValueError("unbalanced (")
                self.pos += 1
                return _Group(0, child)
            raise ValueError("unsupported group syntax")
        self.ngroups += 1
        idx = self.ngroups
        child = self._alt()
        if self._eof() or self.p[self.pos] != ')': raise ValueError("unbalanced (")
        self.pos += 1
        return _Group(idx, child)

    def _class(self):
        self.pos += 1  # skip [
        negated = False
        if not self._eof() and self.p[self.pos] == '^':
            negated = True; self.pos += 1
        items = []
        first = True
        while True:
            if self._eof(): raise ValueError("unterminated [")
            if self.p[self.pos] == ']' and not first:
                self.pos += 1; break
            item = self._class_item()
            first = False
            # check for range
            if item[0] == 'c' and not self._eof() and self.p[self.pos] == '-':
                if self.pos + 1 < len(self.p) and self.p[self.pos+1] != ']':
                    self.pos += 1  # skip -
                    end_item = self._class_item()
                    if end_item[0] != 'c': raise ValueError("invalid range end")
                    if item[1] > end_item[1]: raise ValueError("invalid range")
                    items.append(('r', item[1], end_item[1]))
                    continue
                else:
                    # '-' followed by ']' or end: '-' is literal
                    items.append(item)
                    # '-' will be parsed as next item
                    continue
            if item[0] == 'e' and not self._eof() and self.p[self.pos] == '-':
                if self.pos + 1 < len(self.p) and self.p[self.pos+1] != ']':
                    raise ValueError("invalid class range with escape")
            items.append(item)
        return _Class(items, negated)

    def _class_item(self):
        if self._eof(): raise ValueError("unterminated [")
        c = self.p[self.pos]
        if c == '\\':
            self.pos += 1
            if self._eof(): raise ValueError("bad escape in class")
            c2 = self.p[self.pos]
            if c2 in 'dDwWsS':
                self.pos += 1; return ('e', c2)
            if c2 == 'n': self.pos += 1; return ('c', '\n')
            if c2 == 't': self.pos += 1; return ('c', '\t')
            if not _is_alpha(c2) and not _is_digit(c2):
                self.pos += 1; return ('c', c2)
            raise ValueError("bad escape in class")
        if c in ('n','t'):
            # bare n or t are literals in class
            self.pos += 1; return ('c', c)
        self.pos += 1
        return ('c', c)

    def _escape_atom(self):
        self.pos += 1  # skip backslash
        if self._eof(): raise ValueError("backslash at end of pattern")
        c = self.p[self.pos]
        if c in 'dDwWsS':
            self.pos += 1; return _Class([('e', c)], False)
        if c == 'n': self.pos += 1; return _Lit('\n')
        if c == 't': self.pos += 1; return _Lit('\t')
        if not _is_alpha(c) and not _is_digit(c):
            self.pos += 1; return _Lit(c)
        raise ValueError("invalid escape")

# ─── Character class matching ───

_DIGIT_SET = frozenset('0123456789')
_WORD_SET = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE_SET = frozenset(' \t\n\r\f\v')

def _match_esc(etype, ch):
    if etype == 'd': return ch in _DIGIT_SET
    if etype == 'D': return ch not in _DIGIT_SET
    if etype == 'w': return ch in _WORD_SET
    if etype == 'W': return ch not in _WORD_SET
    if etype == 's': return ch in _SPACE_SET
    if etype == 'S': return ch not in _SPACE_SET
    return False

def _match_class(items, negated, ch):
    hit = False
    for it in items:
        if it[0] == 'c':
            if ch == it[1]: hit = True; break
        elif it[0] == 'r':
            if it[1] <= ch <= it[2]: hit = True; break
        elif it[0] == 'e':
            if _match_esc(it[1], ch): hit = True; break
    return hit != negated

# ─── Matcher ───

def _match(node, pos, caps, cont, s, slen, memo):
    tp = type(node)
    if tp is _Lit:
        if pos < slen and s[pos] == node.char:
            return cont(pos + 1)
        return False
    if tp is _Dot:
        if pos < slen and s[pos] != '\n':
            return cont(pos + 1)
        return False
    if tp is _Class:
        if pos < slen and _match_class(node.items, node.negated, s[pos]):
            return cont(pos + 1)
        return False
    if tp is _AncS:
        if pos == 0:
            return cont(pos)
        return False
    if tp is _AncE:
        if pos == slen or (pos == slen - 1 and s[pos] == '\n'):
            return cont(pos)
        return False
    if tp is _Seq:
        children = node.children
        n = len(children)
        if n == 0:
            return cont(pos)
        def _seq_cont(i, p):
            if i == n:
                return cont(p)
            return _match(children[i], p, caps, lambda np, _i=i: _seq_cont(_i+1, np), s, slen, memo)
        return _seq_cont(0, pos)
    if tp is _Alt:
        for branch in node.branches:
            saved = caps[:]
            if _match(branch, pos, caps, cont, s, slen, memo):
                return True
            caps[:] = saved
        return False
    if tp is _Group:
        idx = node.index
        if idx == 0:  # non-capturing
            return _match(node.child, pos, caps, cont, s, slen, memo)
        saved = caps[:]
        caps[idx] = (pos, None)
        def _grp_cont(np):
            caps[idx] = (pos, np)
            result = cont(np)
            if not result:
                caps[:] = saved
            return result
        result = _match(node.child, pos, caps, _grp_cont, s, slen, memo)
        if not result:
            caps[:] = saved
        return result
    if tp is _Quant:
        return _match_quant(node, pos, 0, None, caps, cont, s, slen, memo)
    return False

def _match_quant(node, pos, c, mark, caps, cont, s, slen, memo):
    lo = node.lo; hi = node.hi; greedy = node.greedy
    # memo key
    c_norm = c if c < lo else lo
    mk = mark if mark is not None else -1
    mkey = (node._id, pos, c_norm, mk)
    if mkey in memo:
        return False

    if c < lo:
        # forced iteration
        saved = caps[:]
        def _after_forced(np):
            return _match_quant(node, np, c+1, mark, caps, cont, s, slen, memo)
        if _match(node.child, pos, caps, _after_forced, s, slen, memo):
            return True
        caps[:] = saved
        memo.add(mkey)
        return False

    # optional phase
    if greedy:
        can_cont = (hi == INF or c < hi) and pos != mark
        if can_cont:
            saved = caps[:]
            def _after_opt(np):
                return _match_quant(node, np, c+1, pos, caps, cont, s, slen, memo)
            if _match(node.child, pos, caps, _after_opt, s, slen, memo):
                return True
            caps[:] = saved
        # follow
        result = cont(pos)
        if not result:
            memo.add(mkey)
        return result
    else:
        # lazy: try follow first
        if cont(pos):
            return True
        can_cont = (hi == INF or c < hi) and pos != mark
        if not can_cont:
            memo.add(mkey)
            return False
        saved = caps[:]
        def _after_opt(np):
            return _match_quant(node, np, c+1, pos, caps, cont, s, slen, memo)
        if _match(node.child, pos, caps, _after_opt, s, slen, memo):
            return True
        caps[:] = saved
        memo.add(mkey)
        return False

# ─── Public API ───

class Match:
    def __init__(self, caps, s, ngroups):
        self._caps = caps
        self._s = s
        self._ng = ngroups

    def span(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError("no such group")
        c = self._caps[n]
        if c is None: return (-1, -1)
        return c

    def start(self, n=0):
        return self.span(n)[0]

    def end(self, n=0):
        return self.span(n)[1]

    def group(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError("no such group")
        c = self._caps[n]
        if c is None: return None
        return self._s[c[0]:c[1]]

    def groups(self):
        result = []
        for i in range(1, self._ng + 1):
            c = self._caps[i]
            if c is None:
                result.append(None)
            else:
                result.append(self._s[c[0]:c[1]])
        return tuple(result)


class Pattern:
    def __init__(self, ast, ngroups):
        self._ast = ast
        self._ng = ngroups

    def _try(self, s, start, full):
        slen = len(s)
        caps = [None] * (self._ng + 1)
        memo = set()
        if full:
            def final_cont(pos):
                return pos == slen
        else:
            def final_cont(pos):
                return True
        caps[0] = (start, None)
        def set_full_end(pos):
            caps[0] = (start, pos)
            return final_cont(pos)
        if _match(self._ast, start, caps, set_full_end, s, slen, memo):
            return Match(caps, s, self._ng)
        return None

    def fullmatch(self, s):
        return self._try(s, 0, True)

    def search(self, s):
        slen = len(s)
        for start in range(slen + 1):
            m = self._try(s, start, False)
            if m is not None:
                return m
        return None


def compile(pattern: str) -> Pattern:
    parser = _Parser(pattern)
    ast = parser.parse()
    return Pattern(ast, parser.ngroups)
