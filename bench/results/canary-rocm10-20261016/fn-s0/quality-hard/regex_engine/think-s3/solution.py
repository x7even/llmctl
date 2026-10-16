import sys
sys.setrecursionlimit(200000)

# ─── AST node types ───────────────────────────────────────────────────────────

class _Lit:
    __slots__ = ('char', 'nid')
    def __init__(self, char, nid): self.char = char; self.nid = nid

class _Dot:
    __slots__ = ('nid',)
    def __init__(self, nid): self.nid = nid

class _CC:
    __slots__ = ('chars', 'negated', 'nid')
    def __init__(self, chars, negated, nid): self.chars = chars; self.negated = negated; self.nid = nid

class _Grp:
    __slots__ = ('index', 'child', 'nid')
    def __init__(self, index, child, nid): self.index = index; self.child = child; self.nid = nid

class _NC:
    __slots__ = ('child', 'nid')
    def __init__(self, child, nid): self.child = child; self.nid = nid

class _Alt:
    __slots__ = ('branches', 'nid')
    def __init__(self, branches, nid): self.branches = branches; self.nid = nid

class _Seq:
    __slots__ = ('items', 'nid')
    def __init__(self, items, nid): self.items = items; self.nid = nid

class _Q:
    __slots__ = ('child', 'lo', 'hi', 'greedy', 'nid')
    def __init__(self, child, lo, hi, greedy, nid):
        self.child = child; self.lo = lo; self.hi = hi; self.greedy = greedy; self.nid = nid

class _AS:
    __slots__ = ('nid',)
    def __init__(self, nid): self.nid = nid

class _AE:
    __slots__ = ('nid',)
    def __init__(self, nid): self.nid = nid


# ─── Parser ───────────────────────────────────────────────────────────────────

_DIGITS = set('0123456789')
_WS = set(' \t\n\r\f\x0b')
_WORD = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')

class _Parser:
    def __init__(self, pattern):
        self.p = pattern
        self.pos = 0
        self.ng = 0
        self._nid = 0

    def nid(self):
        self._nid += 1
        return self._nid

    def parse(self):
        ast = self._alt()
        if self.pos != len(self.p):
            raise ValueError("unexpected end of pattern")
        return ast

    def _alt(self):
        branches = [self._seq()]
        while self.pos < len(self.p) and self.p[self.pos] == '|':
            self.pos += 1
            branches.append(self._seq())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches, self.nid())

    def _seq(self):
        items = []
        while self.pos < len(self.p) and self.p[self.pos] not in '|)':
            item = self._quantified()
            # quantifier-after-quantifier check
            if isinstance(item, _Q) and self.pos < len(self.p):
                c = self.p[self.pos]
                if c in '*+?':
                    raise ValueError("quantifier after quantifier")
                if c == '{' and self._valid_brace():
                    raise ValueError("quantifier after quantifier")
            items.append(item)
        if len(items) == 0:
            return _Seq([], self.nid())
        if len(items) == 1:
            return items[0]
        return _Seq(items, self.nid())

    def _valid_brace(self):
        save = self.pos
        self.pos += 1
        ok = False
        m0 = self.pos
        while self.pos < len(self.p) and self.p[self.pos] in _DIGITS:
            self.pos += 1
        if self.pos > m0:
            if self.pos < len(self.p) and self.p[self.pos] == ',':
                self.pos += 1
                while self.pos < len(self.p) and self.p[self.pos] in _DIGITS:
                    self.pos += 1
            if self.pos < len(self.p) and self.p[self.pos] == '}':
                ok = True
        self.pos = save
        return ok

    def _quantified(self):
        atom = self._atom()
        if isinstance(atom, (_AS, _AE)):
            if self.pos < len(self.p) and self.p[self.pos] in '*+?{':
                raise ValueError("cannot quantify anchor")
            return atom
        if self.pos < len(self.p):
            c = self.p[self.pos]
            if c == '*':
                self.pos += 1
                g = True
                if self.pos < len(self.p) and self.p[self.pos] == '?':
                    self.pos += 1; g = False
                return _Q(atom, 0, None, g, self.nid())
            if c == '+':
                self.pos += 1
                g = True
                if self.pos < len(self.p) and self.p[self.pos] == '?':
                    self.pos += 1; g = False
                return _Q(atom, 1, None, g, self.nid())
            if c == '?':
                self.pos += 1
                g = True
                if self.pos < len(self.p) and self.p[self.pos] == '?':
                    self.pos += 1; g = False
                return _Q(atom, 0, 1, g, self.nid())
            if c == '{':
                return self._brace(atom)
        return atom

    def _brace(self, atom):
        self.pos += 1  # skip '{'
        m0 = self.pos
        while self.pos < len(self.p) and self.p[self.pos] in _DIGITS:
            self.pos += 1
        if self.pos == m0:
            raise ValueError("invalid quantifier")
        m = int(self.p[m0:self.pos])
        n = None
        if self.pos < len(self.p) and self.p[self.pos] == ',':
            self.pos += 1
            n0 = self.pos
            while self.pos < len(self.p) and self.p[self.pos] in _DIGITS:
                self.pos += 1
            if n0 < self.pos:
                n = int(self.p[n0:self.pos])
                if m > n:
                    raise ValueError("m > n in quantifier")
        else:
            n = m
        if self.pos >= len(self.p) or self.p[self.pos] != '}':
            raise ValueError("invalid quantifier")
        self.pos += 1
        g = True
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            self.pos += 1; g = False
        return _Q(atom, m, n, g, self.nid())

    def _atom(self):
        if self.pos >= len(self.p):
            return _Seq([], self.nid())
        c = self.p[self.pos]
        if c == '.':
            self.pos += 1; return _Dot(self.nid())
        if c == '^':
            self.pos += 1; return _AS(self.nid())
        if c == '$':
            self.pos += 1; return _AE(self.nid())
        if c == '\\':
            return self._esc()
        if c == '[':
            return self._cls()
        if c == '(':
            return self._grp()
        if c in '*+?':
            raise ValueError("quantifier with nothing to repeat")
        if c == ')':
            raise ValueError("unmatched )")
        self.pos += 1
        return _Lit(c, self.nid())

    def _esc(self):
        self.pos += 1
        if self.pos >= len(self.p):
            raise ValueError("backslash at end of pattern")
        c = self.p[self.pos]; self.pos += 1
        if c == 'd': return _CC(set('0123456789'), False, self.nid())
        if c == 'D': return _CC(set('0123456789'), True, self.nid())
        if c == 'w': return _CC(set(_WORD), False, self.nid())
        if c == 'W': return _CC(set(_WORD), True, self.nid())
        if c == 's': return _CC(set(_WS), False, self.nid())
        if c == 'S': return _CC(set(_WS), True, self.nid())
        if c == 'n': return _Lit('\n', self.nid())
        if c == 't': return _Lit('\t', self.nid())
        if not c.isalnum():
            return _Lit(c, self.nid())
        raise ValueError(f"invalid escape \\{c}")

    def _cls_item(self):
        if self.p[self.pos] == '\\':
            self.pos += 1
            if self.pos >= len(self.p):
                raise ValueError("backslash at end of class")
            c = self.p[self.pos]; self.pos += 1
            if c in 'dDwWsS':
                return ('esc', c)
            if c == 'n': return ('ch', '\n')
            if c == 't': return ('ch', '\t')
            if not c.isalnum(): return ('ch', c)
            raise ValueError(f"invalid escape in class \\{c}")
        else:
            c = self.p[self.pos]; self.pos += 1
            return ('ch', c)

    def _cls(self):
        self.pos += 1  # skip '['
        neg = False
        if self.pos < len(self.p) and self.p[self.pos] == '^':
            neg = True; self.pos += 1
        chars = set()
        first = True
        while True:
            if self.pos >= len(self.p):
                raise ValueError("unterminated character class")
            if self.p[self.pos] == ']' and not first:
                self.pos += 1; break
            first = False
            item = self._cls_item()
            if item[0] == 'ch':
                ch = item[1]
                if (self.pos < len(self.p) and self.p[self.pos] == '-'
                        and self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']'):
                    self.pos += 1
                    end = self._cls_item()
                    if end[0] != 'ch':
                        raise ValueError("class escape in range")
                    if ch > end[1]:
                        raise ValueError("invalid range")
                    for cp in range(ord(ch), ord(end[1]) + 1):
                        chars.add(chr(cp))
                else:
                    chars.add(ch)
            else:
                es = item[1]
                if es == 'd': chars.update('0123456789')
                elif es == 'D': chars.update(set(chr(i) for i in range(128)) - set('0123456789'))
                elif es == 'w': chars.update(_WORD)
                elif es == 'W': chars.update(set(chr(i) for i in range(128)) - set(_WORD))
                elif es == 's': chars.update(_WS)
                elif es == 'S': chars.update(set(chr(i) for i in range(128)) - set(_WS))
                if (self.pos < len(self.p) and self.p[self.pos] == '-'
                        and self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']'):
                    raise ValueError("class escape in range")
        return _CC(chars, neg, self.nid())

    def _grp(self):
        self.pos += 1  # skip '('
        if self.pos + 1 < len(self.p) and self.p[self.pos] == '?' and self.p[self.pos + 1] == ':':
            self.pos += 2
            child = self._alt()
            if self.pos >= len(self.p) or self.p[self.pos] != ')':
                raise ValueError("unmatched (")
            self.pos += 1
            return _NC(child, self.nid())
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            raise ValueError("unsupported group syntax")
        self.ng += 1
        idx = self.ng
        child = self._alt()
        if self.pos >= len(self.p) or self.p[self.pos] != ')':
            raise ValueError("unmatched (")
        self.pos += 1
        return _Grp(idx, child, self.nid())


# ─── Match / Pattern ─────────────────────────────────────────────────────────

class Match:
    __slots__ = ('_s', '_g')
    def __init__(self, s, g):
        self._s = s; self._g = g

    def span(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n >= len(self._g):
            raise IndexError(n)
        g = self._g[n]
        return g if g is not None else (-1, -1)

    def start(self, n=0):
        return self.span(n)[0]

    def end(self, n=0):
        return self.span(n)[1]

    def group(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n >= len(self._g):
            raise IndexError(n)
        g = self._g[n]
        if g is None: return None
        return self._s[g[0]:g[1]]

    def groups(self):
        return tuple(self.group(i) for i in range(1, len(self._g)))


class Pattern:
    def __init__(self, ast, ng):
        self._ast = ast; self._ng = ng

    def fullmatch(self, s):
        memo = set()
        return self._try(s, 0, True, memo)

    def search(self, s):
        memo = set()
        for start in range(len(s) + 1):
            r = self._try(s, start, False, memo)
            if r is not None:
                return r
        return None

    def _try(self, s, start, full, memo):
        ng = self._ng
        caps = [None] * (ng + 1)
        end_ref = [start]
        n = len(s)

        def final_cont(pos):
            if full and pos != n:
                return False
            end_ref[0] = pos
            return True

        def mn(node, pos, cont):
            tp = type(node)
            if tp is _Seq:
                return _seq(node.items, 0, pos, cont)
            if tp is _Lit:
                if pos < n and s[pos] == node.char:
                    return cont(pos + 1)
                return False
            if tp is _Dot:
                if pos < n and s[pos] != '\n':
                    return cont(pos + 1)
                return False
            if tp is _CC:
                if pos < n:
                    inc = s[pos] in node.chars
                    if node.negated: inc = not inc
                    if inc: return cont(pos + 1)
                return False
            if tp is _AS:
                if pos == 0: return cont(pos)
                return False
            if tp is _AE:
                if pos == n or (pos == n - 1 and s[pos] == '\n'):
                    return cont(pos)
                return False
            if tp is _Alt:
                for br in node.branches:
                    if mn(br, pos, cont): return True
                return False
            if tp is _Grp:
                idx = node.index
                old = caps[idx]
                def gc(p, _i=idx, _sp=pos, _old=old):
                    caps[_i] = (_sp, p)
                    if cont(p): return True
                    caps[_i] = _old
                    return False
                return mn(node.child, pos, gc)
            if tp is _NC:
                return mn(node.child, pos, cont)
            if tp is _Q:
                return _quant(node, pos, cont)
            raise AssertionError

        def _seq(items, i, pos, cont):
            while i < len(items):
                item = items[i]
                tp = type(item)
                if tp is _Lit:
                    if pos < n and s[pos] == item.char:
                        pos += 1; i += 1; continue
                    return False
                if tp is _Dot:
                    if pos < n and s[pos] != '\n':
                        pos += 1; i += 1; continue
                    return False
                if tp is _CC:
                    if pos < n:
                        inc = s[pos] in item.chars
                        if item.negated: inc = not inc
                        if inc: pos += 1; i += 1; continue
                    return False
                if tp is _AS:
                    if pos == 0: i += 1; continue
                    return False
                if tp is _AE:
                    if pos == n or (pos == n - 1 and s[pos] == '\n'):
                        i += 1; continue
                    return False
                # complex item – use CPS
                return mn(item, pos, lambda p, _i=i: _seq(items, _i + 1, p, cont))
            return cont(pos)

        def _quant(node, pos, cont):
            lo = node.lo; hi = node.hi; greedy = node.greedy
            if lo == 0 and hi == 0:
                return cont(pos)
            nid = node.nid

            def loop(p, c, mark):
                key = (nid, p, c, mark)
                if key in memo: return False
                res = _body(p, c, mark)
                if not res: memo.add(key)
                return res

            def _body(p, c, mark):
                if c < lo:
                    return mn(node.child, p, lambda np, _c=c: loop(np, _c + 1, None))
                if greedy:
                    if (hi is None or c < hi) and p != mark:
                        if mn(node.child, p, lambda np, _c=c, _m=p: loop(np, _c + 1, _m)):
                            return True
                        return cont(p)
                    return cont(p)
                else:
                    if cont(p): return True
                    if (hi is not None and c >= hi) or p == mark:
                        return False
                    return mn(node.child, p, lambda np, _c=c, _m=p: loop(np, _c + 1, _m))

            return loop(pos, 0, None)

        if mn(self._ast, start, final_cont):
            caps[0] = (start, end_ref[0])
            return Match(s, caps)
        return None


# ─── Public compile ──────────────────────────────────────────────────────────

def compile(pattern: str) -> Pattern:
    p = _Parser(pattern)
    ast = p.parse()
    return Pattern(ast, p.ng)
