import sys
sys.setrecursionlimit(100000)

_DIGITS = frozenset('0123456789')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')

def _match_chartype(kind, ch):
    if kind == 'd': return ch in _DIGITS
    if kind == 'D': return ch not in _DIGITS
    if kind == 'w': return ch in _WORD
    if kind == 'W': return ch not in _WORD
    if kind == 's': return ch in _SPACE
    if kind == 'S': return ch not in _SPACE
    return False

# --- AST Nodes ---
class _Node:
    _nid = 0
    def __init__(self):
        _Node._nid += 1
        self.id = _Node._nid

class _Lit(_Node):
    __slots__ = ('ch',)
    def __init__(self, ch): super().__init__(); self.ch = ch

class _Any(_Node): pass

class _Cls(_Node):
    __slots__ = ('chars','neg')
    def __init__(self, chars, neg): super().__init__(); self.chars=chars; self.neg=neg

class _CT(_Node):
    __slots__ = ('kind',)
    def __init__(self, kind): super().__init__(); self.kind=kind

class _Seq(_Node):
    __slots__ = ('ch',)
    def __init__(self, ch): super().__init__(); self.ch=ch

class _Alt(_Node):
    __slots__ = ('br',)
    def __init__(self, br): super().__init__(); self.br=br

class _Grp(_Node):
    __slots__ = ('idx','child')
    def __init__(self, idx, child): super().__init__(); self.idx=idx; self.child=child

class _NC(_Node):
    __slots__ = ('child',)
    def __init__(self, child): super().__init__(); self.child=child

class _Q(_Node):
    __slots__ = ('child','lo','hi','greedy')
    def __init__(self, child, lo, hi, greedy):
        super().__init__(); self.child=child; self.lo=lo; self.hi=hi; self.greedy=greedy

class _AS(_Node): pass
class _AE(_Node): pass

# --- Parser ---
class _Parser:
    def __init__(self, pat):
        self.p = pat; self.pos = 0; self.ng = 0

    def parse(self):
        if not self.p: return _Seq([])
        node = self._alt()
        if self.pos < len(self.p): raise ValueError("unexpected char")
        return node

    def _peek(self):
        return self.p[self.pos] if self.pos < len(self.p) else None

    def _adv(self):
        c = self.p[self.pos]; self.pos += 1; return c

    def _alt(self):
        br = [self._seq()]
        while self._peek() == '|':
            self._adv(); br.append(self._seq())
        return br[0] if len(br)==1 else _Alt(br)

    def _seq(self):
        ch = []
        while self.pos < len(self.p) and self.p[self.pos] not in ('|',')'):
            c = self.p[self.pos]
            if c in ('*','+','?'):
                raise ValueError("nothing to repeat")
            if c == '{':
                raise ValueError("nothing to repeat")
            node = self._quantified()
            if ch and isinstance(ch[-1], _Q):
                nxt = self._peek()
                if nxt in ('*','+','?','{'):
                    raise ValueError("quantifier after quantifier")
            ch.append(node)
        if not ch: return _Seq([])
        return ch[0] if len(ch)==1 else _Seq(ch)

    def _quantified(self):
        atom = self._atom()
        if isinstance(atom, (_AS, _AE)):
            if self._peek() in ('*','+','?','{'):
                raise ValueError("cannot quantify anchor")
            return atom
        c = self._peek()
        if c in ('*','+','?'):
            self._adv()
            gr = True
            if self._peek() == '?': gr = False; self._adv()
            lo,hi = {'*':(0,None),'+':(1,None),'?':(0,1)}[c]
            return _Q(atom, lo, hi, gr)
        if c == '{':
            return self._brace(atom)
        return atom

    def _brace(self, atom):
        self._adv()  # {
        ms = ''
        while self.pos < len(self.p) and self.p[self.pos].isdigit(): ms += self._adv()
        if not ms: raise ValueError("invalid quantifier")
        n = None
        if self.pos < len(self.p) and self.p[self.pos] == ',':
            self._adv()
            ns = ''
            while self.pos < len(self.p) and self.p[self.pos].isdigit(): ns += self._adv()
            if ns: n = int(ns)
        if self.pos >= len(self.p) or self.p[self.pos] != '}':
            raise ValueError("invalid quantifier")
        self._adv()  # }
        m = int(ms)
        if n is not None and m > n: raise ValueError("m>n")
        gr = True
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            gr = False; self._adv()
        return _Q(atom, m, n, gr)

    def _atom(self):
        c = self._peek()
        if c is None: raise ValueError("unexpected end")
        if c in ('*','+','?','{'): raise ValueError("nothing to repeat")
        if c == '}': self._adv(); return _Lit('}')
        if c == '.': self._adv(); return _Any()
        if c == '^': self._adv(); return _AS()
        if c == '$': self._adv(); return _AE()
        if c == '(': return self._group()
        if c == '[': return self._cls()
        if c == '\\': return self._esc()
        self._adv(); return _Lit(c)

    def _esc(self):
        self._adv()  # backslash
        if self.pos >= len(self.p): raise ValueError("trailing backslash")
        c = self._adv()
        if c in 'dDwWsS': return _CT(c)
        if c == 'n': return _Lit('\n')
        if c == 't': return _Lit('\t')
        if not c.isalnum(): return _Lit(c)
        raise ValueError("invalid escape")

    def _group(self):
        self._adv()  # (
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            if self.pos+1 < len(self.p) and self.p[self.pos+1] == ':':
                self._adv(); self._adv()  # ?:
                inner = self._alt()
                if self.pos >= len(self.p) or self.p[self.pos] != ')':
                    raise ValueError("unbalanced")
                self._adv()
                return _NC(inner)
            raise ValueError("unsupported group")
        self.ng += 1; idx = self.ng
        inner = self._alt()
        if self.pos >= len(self.p) or self.p[self.pos] != ')':
            raise ValueError("unbalanced")
        self._adv()
        return _Grp(idx, inner)

    def _cls(self):
        self._adv()  # [
        neg = False
        if self.pos < len(self.p) and self.p[self.pos] == '^':
            neg = True; self._adv()
        chars = set(); first = True
        while True:
            if self.pos >= len(self.p): raise ValueError("unterminated class")
            if self.p[self.pos] == ']' and not first:
                self._adv(); break
            first = False
            it, idata = self._cls_item()
            if it == 'c' and self.pos < len(self.p) and self.p[self.pos] == '-':
                if self.pos+1 < len(self.p) and self.p[self.pos+1] != ']':
                    self._adv()  # -
                    it2, id2 = self._cls_item()
                    if it2 != 'c': raise ValueError("bad range end")
                    if idata > id2: raise ValueError("bad range")
                    for cv in range(ord(idata), ord(id2)+1): chars.add(chr(cv))
                elif self.pos+1 >= len(self.p):
                    raise ValueError("unterminated class")
                else:
                    chars.add('-'); self._adv()
            elif it == 'e':
                if self.pos < len(self.p) and self.p[self.pos] == '-':
                    if self.pos+1 < len(self.p) and self.p[self.pos+1] != ']':
                        raise ValueError("class escape in range")
                    elif self.pos+1 >= len(self.p):
                        raise ValueError("unterminated class")
                    else:
                        chars.add('-'); self._adv()
                chars.update(idata)
            else:
                chars.add(idata)
        return _Cls(chars, neg)

    def _cls_item(self):
        if self.pos >= len(self.p): raise ValueError("unterminated class")
        if self.p[self.pos] == '\\':
            self._adv()
            if self.pos >= len(self.p): raise ValueError("bad escape in class")
            c = self._adv()
            if c in 'dDwWsS':
                if c=='d': return ('e', _DIGITS)
                if c=='D': return ('e', set(chr(i) for i in range(128) if chr(i) not in _DIGITS))
                if c=='w': return ('e', _WORD)
                if c=='W': return ('e', set(chr(i) for i in range(128) if chr(i) not in _WORD))
                if c=='s': return ('e', _SPACE)
                if c=='S': return ('e', set(chr(i) for i in range(128) if chr(i) not in _SPACE))
            if c == 'n': return ('c','\n')
            if c == 't': return ('c','\t')
            if not c.isalnum(): return ('c', c)
            raise ValueError("bad escape in class")
        return ('c', self._adv())

# --- Matcher ---
def _match(node, pos, s, caps, memo, cont):
    if isinstance(node, _Q):
        return _match_q(node, pos, s, caps, memo, cont)
    key = (node.id, pos)
    if key in memo: return None
    r = _match_impl(node, pos, s, caps, memo, cont)
    if r is None: memo.add(key)
    return r

def _match_impl(node, pos, s, caps, memo, cont):
    if isinstance(node, _Lit):
        if pos < len(s) and s[pos] == node.ch: return cont(pos+1)
        return None
    if isinstance(node, _Any):
        if pos < len(s) and s[pos] != '\n': return cont(pos+1)
        return None
    if isinstance(node, _Cls):
        if pos < len(s):
            in_cls = s[pos] in node.chars
            if in_cls != node.neg: return cont(pos+1)
        return None
    if isinstance(node, _CT):
        if pos < len(s) and _match_chartype(node.kind, s[pos]): return cont(pos+1)
        return None
    if isinstance(node, _AS):
        if pos == 0: return cont(pos)
        return None
    if isinstance(node, _AE):
        if pos == len(s) or (pos == len(s)-1 and s[pos]=='\n'): return cont(pos)
        return None
    if isinstance(node, _Seq):
        return _match_seq(node, pos, s, caps, memo, cont)
    if isinstance(node, _Alt):
        for br in node.br:
            saved = dict(caps)
            r = _match(br, pos, s, caps, memo, cont)
            if r is not None: return r
            caps.clear(); caps.update(saved)
        return None
    if isinstance(node, _Grp):
        start = pos
        def gc(np):
            caps[node.idx] = (start, np)
            return cont(np)
        return _match(node.child, pos, s, caps, memo, gc)
    if isinstance(node, _NC):
        return _match(node.child, pos, s, caps, memo, cont)
    return None

def _match_seq(node, pos, s, caps, memo, cont):
    children = node.ch; n = len(children)
    def go(i, p):
        if i >= n: return cont(p)
        child = children[i]
        def nc(np): return go(i+1, np)
        return _match(child, p, s, caps, memo, nc)
    return go(0, pos)

def _match_q(node, pos, s, caps, memo, cont):
    sub = node.child; lo = node.lo; hi = node.hi; gr = node.greedy
    if lo == 0 and hi == 0:
        return cont(pos)
    # forced iterations
    for _ in range(lo):
        saved = dict(caps)
        holder = [None]
        def fc(np):
            holder[0] = np; return np
        r = _match(sub, pos, s, caps, memo, fc)
        if r is None:
            caps.clear(); caps.update(saved)
            return None
        pos = holder[0]
    # optional loop
    if gr:
        return _q_greedy(node, sub, pos, lo, None, s, caps, memo, cont)
    else:
        return _q_lazy(node, sub, pos, lo, None, s, caps, memo, cont)

def _q_greedy(node, sub, pos, c, mark, s, caps, memo, cont):
    if node.hi is None:
        key = ('q', node.id, pos)
    else:
        key = ('q', node.id, pos, c)
    if key in memo: return None
    # try one more iteration
    if (node.hi is None or c < node.hi) and pos != mark:
        saved = dict(caps)
        nm = pos
        holder = [None]
        def ic(np): holder[0] = np; return np
        r = _match(sub, pos, s, caps, memo, ic)
        if r is not None:
            r2 = _q_greedy(node, sub, holder[0], c+1, nm, s, caps, memo, cont)
            if r2 is not None: return r2
        caps.clear(); caps.update(saved)
    # stop
    r = cont(pos)
    if r is not None: return r
    memo.add(key)
    return None

def _q_lazy(node, sub, pos, c, mark, s, caps, memo, cont):
    if node.hi is None:
        key = ('q', node.id, pos)
    else:
        key = ('q', node.id, pos, c)
    if key in memo: return None
    # try stop first
    r = cont(pos)
    if r is not None: return r
    # try one more iteration
    if (node.hi is None or c < node.hi) and pos != mark:
        saved = dict(caps)
        nm = pos
        holder = [None]
        def ic(np): holder[0] = np; return np
        r = _match(sub, pos, s, caps, memo, ic)
        if r is not None:
            r2 = _q_lazy(node, sub, holder[0], c+1, nm, s, caps, memo, cont)
            if r2 is not None: return r2
        caps.clear(); caps.update(saved)
    memo.add(key)
    return None

# --- API ---
class Match:
    def __init__(self, string, fspan, gspans, ng):
        self._s = string; self._f = fspan; self._g = gspans; self._ng = ng

    def _check(self, n):
        if not isinstance(n, int) or isinstance(n, bool): raise IndexError(n)
        if n < 0 or n > self._ng: raise IndexError(n)

    def span(self, n=0):
        self._check(n)
        if n == 0: return self._f
        g = self._g[n-1]
        return g if g is not None else (-1,-1)

    def start(self, n=0): return self.span(n)[0]
    def end(self, n=0): return self.span(n)[1]

    def group(self, n=0):
        self._check(n)
        s,e = self.span(n)
        if s == -1: return None
        return self._s[s:e]

    def groups(self):
        return tuple(self.group(i) for i in range(1, self._ng+1))

class Pattern:
    def __init__(self, tree, ng):
        self._tree = tree; self._ng = ng

    def fullmatch(self, s):
        caps = {}; memo = set()
        def cont(p): return p if p == len(s) else None
        r = _match(self._tree, 0, s, caps, memo, cont)
        if r is None: return None
        return self._mk(s, caps, 0, r)

    def search(self, s):
        memo = set()
        for start in range(len(s)+1):
            caps = {}
            def cont(p): return p
            r = _match(self._tree, start, s, caps, memo, cont)
            if r is not None:
                return self._mk(s, caps, start, r)
        return None

    def _mk(self, s, caps, start, end):
        gs = []
        for i in range(1, self._ng+1):
            gs.append(caps.get(i, None))
        return Match(s, (start, end), gs, self._ng)

def compile(pattern):
    _Node._nid = 0
    p = _Parser(pattern)
    tree = p.parse()
    return Pattern(tree, p.ng)
