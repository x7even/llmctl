import sys
sys.setrecursionlimit(100000)

_DIGITS = frozenset('0123456789')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')

class _CharSet:
    __slots__ = ('negated', 'chars', 'ranges', 'escapes')
    def __init__(self, negated, chars, ranges, escapes):
        self.negated = negated
        self.chars = chars
        self.ranges = ranges
        self.escapes = escapes
    def matches(self, ch):
        result = False
        if ch in self.chars:
            result = True
        else:
            for lo, hi in self.ranges:
                if lo <= ch <= hi:
                    result = True
                    break
        if not result:
            for esc in self.escapes:
                if esc == 'd':
                    if ch in _DIGITS: result = True; break
                elif esc == 'w':
                    if ch in _WORD: result = True; break
                elif esc == 's':
                    if ch in _SPACE: result = True; break
                elif esc == 'D':
                    if ch not in _DIGITS: result = True; break
                elif esc == 'W':
                    if ch not in _WORD: result = True; break
                elif esc == 'S':
                    if ch not in _SPACE: result = True; break
        if self.negated:
            return not result
        return result

class _Node:
    __slots__ = ()

class _Lit(_Node):
    __slots__ = ('ch',)
    def __init__(self, ch): self.ch = ch

class _Any(_Node):
    __slots__ = ()

class _ClassEscape(_Node):
    __slots__ = ('kind',)
    def __init__(self, kind): self.kind = kind

class _Class(_Node):
    __slots__ = ('cs',)
    def __init__(self, cs): self.cs = cs

class _Group(_Node):
    __slots__ = ('idx', 'child')
    def __init__(self, idx, child): self.idx = idx; self.child = child

class _Alt(_Node):
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Seq(_Node):
    __slots__ = ('items',)
    def __init__(self, items): self.items = items

class _Quant(_Node):
    __slots__ = ('lo', 'hi', 'child', 'lazy', 'empty')
    def __init__(self, lo, hi, child, lazy):
        self.lo = lo; self.hi = hi; self.child = child; self.lazy = lazy; self.empty = False

class _AnchorS(_Node):
    __slots__ = ()

class _AnchorE(_Node):
    __slots__ = ()

class _Parser:
    def __init__(self, pattern):
        self.p = pattern
        self.pos = 0
        self.n = len(pattern)
        self.ngroups = 0

    def parse(self):
        node = self._alt()
        if self.pos != self.n:
            raise ValueError("unbalanced parentheses")
        return node

    def _alt(self):
        branches = [self._seq()]
        while self.pos < self.n and self.p[self.pos] == '|':
            self.pos += 1
            branches.append(self._seq())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _seq(self):
        items = []
        while self.pos < self.n and self.p[self.pos] not in ('|', ')'):
            ch = self.p[self.pos]
            if ch in ('*', '+', '?'):
                raise ValueError("quantifier with nothing to repeat")
            if ch == '{':
                saved = self.pos
                q = self._try_brace()
                if q is not None:
                    raise ValueError("quantifier with nothing to repeat")
                self.pos = saved
            atom = self._atom()
            q = self._try_quant()
            if q is not None:
                if isinstance(atom, (_AnchorS, _AnchorE)):
                    raise ValueError("cannot quantify anchor")
                items.append(_Quant(q[0], q[1], atom, q[2]))
                if self.pos < self.n:
                    nc = self.p[self.pos]
                    if nc in ('*', '+', '?'):
                        raise ValueError("quantifier after quantifier")
                    if nc == '{':
                        sv = self.pos
                        q2 = self._try_brace()
                        if q2 is not None:
                            raise ValueError("quantifier after quantifier")
                        self.pos = sv
            else:
                items.append(atom)
        if len(items) == 0:
            return _Seq([])
        if len(items) == 1:
            return items[0]
        return _Seq(items)

    def _atom(self):
        ch = self.p[self.pos]
        if ch == '.':
            self.pos += 1
            return _Any()
        if ch == '^':
            self.pos += 1
            return _AnchorS()
        if ch == '$':
            self.pos += 1
            return _AnchorE()
        if ch == '(':
            return self._group()
        if ch == '[':
            return self._cls()
        if ch == '\\':
            return self._esc()
        if ch in ('*', '+', '?'):
            raise ValueError("quantifier with nothing to repeat")
        self.pos += 1
        return _Lit(ch)

    def _group(self):
        self.pos += 1
        if self.pos + 1 < self.n and self.p[self.pos] == '?' and self.p[self.pos + 1] == ':':
            self.pos += 2
            inner = self._alt()
            if self.pos >= self.n or self.p[self.pos] != ')':
                raise ValueError("unbalanced parentheses")
            self.pos += 1
            return _Group(0, inner)
        if self.pos < self.n and self.p[self.pos] == '?':
            raise ValueError("unsupported group syntax")
        self.ngroups += 1
        idx = self.ngroups
        inner = self._alt()
        if self.pos >= self.n or self.p[self.pos] != ')':
            raise ValueError("unbalanced parentheses")
        self.pos += 1
        return _Group(idx, inner)

    def _esc(self):
        self.pos += 1
        if self.pos >= self.n:
            raise ValueError("backslash at end of pattern")
        ch = self.p[self.pos]
        if ch in 'dDwWsS':
            self.pos += 1
            return _ClassEscape(ch)
        if ch == 'n':
            self.pos += 1
            return _Lit('\n')
        if ch == 't':
            self.pos += 1
            return _Lit('\t')
        if ch.isalpha() or ch.isdigit():
            raise ValueError("invalid escape")
        self.pos += 1
        return _Lit(ch)

    def _cls(self):
        self.pos += 1
        negated = False
        if self.pos < self.n and self.p[self.pos] == '^':
            negated = True
            self.pos += 1
        chars = set()
        ranges = []
        escapes = []
        first = True
        while True:
            if self.pos >= self.n:
                raise ValueError("unterminated character class")
            if self.p[self.pos] == ']' and not first:
                self.pos += 1
                break
            first = False
            item = self._cls_item()
            if item[0] == 'char':
                if (self.pos < self.n and self.p[self.pos] == '-' and
                        self.pos + 1 < self.n and self.p[self.pos + 1] != ']'):
                    self.pos += 1
                    item2 = self._cls_item()
                    if item2[0] != 'char':
                        raise ValueError("invalid range")
                    if item[1] > item2[1]:
                        raise ValueError("invalid range")
                    ranges.append((item[1], item2[1]))
                else:
                    chars.add(item[1])
            else:
                if self.pos < self.n and self.p[self.pos] == '-' and \
                        self.pos + 1 < self.n and self.p[self.pos + 1] != ']':
                    raise ValueError("class escape in range")
                escapes.append(item[1])
        return _Class(_CharSet(negated, chars, ranges, escapes))

    def _cls_item(self):
        if self.p[self.pos] == '\\':
            self.pos += 1
            if self.pos >= self.n:
                raise ValueError("backslash at end of class")
            ch = self.p[self.pos]
            if ch in 'dDwWsS':
                self.pos += 1
                return ('esc', ch)
            if ch == 'n':
                self.pos += 1
                return ('char', '\n')
            if ch == 't':
                self.pos += 1
                return ('char', '\t')
            if ch.isalpha() or ch.isdigit():
                raise ValueError("invalid escape in class")
            self.pos += 1
            return ('char', ch)
        else:
            ch = self.p[self.pos]
            self.pos += 1
            return ('char', ch)

    def _try_quant(self):
        if self.pos >= self.n:
            return None
        ch = self.p[self.pos]
        if ch == '*':
            self.pos += 1
            return (0, None, self._lazy())
        if ch == '+':
            self.pos += 1
            return (1, None, self._lazy())
        if ch == '?':
            self.pos += 1
            return (0, 1, self._lazy())
        if ch == '{':
            return self._try_brace()
        return None

    def _lazy(self):
        if self.pos < self.n and self.p[self.pos] == '?':
            self.pos += 1
            return True
        return False

    def _try_brace(self):
        start = self.pos
        self.pos += 1
        ms = self.pos
        while self.pos < self.n and self.p[self.pos].isdigit():
            self.pos += 1
        if self.pos == ms:
            self.pos = start
            return None
        m = int(self.p[ms:self.pos])
        if self.pos < self.n and self.p[self.pos] == ',':
            self.pos += 1
            ns = self.pos
            while self.pos < self.n and self.p[self.pos].isdigit():
                self.pos += 1
            if ns == self.pos:
                n = None
            else:
                n = int(self.p[ns:self.pos])
        else:
            n = m
        if self.pos >= self.n or self.p[self.pos] != '}':
            self.pos = start
            return None
        self.pos += 1
        if n is not None and m > n:
            raise ValueError("m > n in quantifier")
        return (m, n, self._lazy())

class _Matcher:
    __slots__ = ('s', 'n', 'caps', 'failed', 'ngroups')

    def __init__(self, s, ngroups):
        self.s = s
        self.n = len(s)
        self.caps = [None] * (ngroups + 1)
        self.failed = set()
        self.ngroups = ngroups

    def _esc_match(self, kind, ch):
        if kind == 'd': return ch in _DIGITS
        if kind == 'D': return ch not in _DIGITS
        if kind == 'w': return ch in _WORD
        if kind == 'W': return ch not in _WORD
        if kind == 's': return ch in _SPACE
        if kind == 'S': return ch not in _SPACE
        return False

    def _match(self, node, pos, cont):
        tp = type(node)
        if tp is _Lit:
            if pos < self.n and self.s[pos] == node.ch:
                return cont(pos + 1)
            return False
        if tp is _Any:
            if pos < self.n and self.s[pos] != '\n':
                return cont(pos + 1)
            return False
        if tp is _ClassEscape:
            if pos < self.n and self._esc_match(node.kind, self.s[pos]):
                return cont(pos + 1)
            return False
        if tp is _Class:
            if pos < self.n and node.cs.matches(self.s[pos]):
                return cont(pos + 1)
            return False
        if tp is _AnchorS:
            if pos == 0:
                return cont(pos)
            return False
        if tp is _AnchorE:
            if pos == self.n or (pos == self.n - 1 and self.s[pos] == '\n'):
                return cont(pos)
            return False
        if tp is _Seq:
            return self._seq(node.items, 0, pos, cont)
        if tp is _Alt:
            return self._alt(node.branches, 0, pos, cont)
        if tp is _Group:
            return self._grp(node, pos, cont)
        if tp is _Quant:
            return self._quant(node, pos, cont)
        return False

    def _seq(self, items, i, pos, cont):
        if i == len(items):
            return cont(pos)
        return self._match(items[i], pos, lambda p, i=i: self._seq(items, i + 1, p, cont))

    def _alt(self, branches, i, pos, cont):
        if i == len(branches):
            return False
        saved = self.caps.copy()
        if self._match(branches[i], pos, cont):
            return True
        self.caps[:] = saved
        return self._alt(branches, i + 1, pos, cont)

    def _grp(self, node, pos, cont):
        idx = node.idx
        saved_start = self.caps[idx]
        def after(p):
            old = self.caps[idx]
            self.caps[idx] = (pos, p)
            if cont(p):
                return True
            self.caps[idx] = old
            return False
        if self._match(node.child, pos, after):
            return True
        self.caps[idx] = saved_start
        return False

    def _quant(self, node, pos, cont):
        lo, hi, child, lazy = node.lo, node.hi, node.child, node.lazy
        if lo == 0 and hi == 0:
            return cont(pos)
        key = (id(node), pos)
        if key in self.failed:
            return False
        result = self._do_quant(node, lo, hi, child, lazy, pos, cont)
        if not result:
            self.failed.add(key)
        return result

    def _do_quant(self, node, lo, hi, child, lazy, pos, cont):
        def forced(c, p, saved):
            if c >= lo:
                return opt(c, p, None, saved)
            s2 = self.caps.copy()
            def af(np):
                return forced(c + 1, np, s2)
            if self._match(child, p, af):
                return True
            self.caps[:] = s2
            return False

        def opt(c, p, mark, saved):
            if lazy:
                s3 = self.caps.copy()
                if cont(p):
                    return True
                self.caps[:] = s3
                if (hi is not None and c >= hi) or (mark is not None and p == mark):
                    return False
                s4 = self.caps.copy()
                def af(np):
                    return opt(c + 1, np, p, s4)
                if self._match(child, p, af):
                    return True
                self.caps[:] = s4
                return False
            else:
                if (hi is not None and c >= hi) or (mark is not None and p == mark):
                    return cont(p)
                s5 = self.caps.copy()
                def af(np):
                    return opt(c + 1, np, p, s5)
                if self._match(child, p, af):
                    return True
                self.caps[:] = s5
                return cont(p)

        return forced(0, pos, self.caps.copy())

class Match:
    __slots__ = ('_spans', '_text', '_ngroups')
    def __init__(self, text, spans, ngroups):
        self._text = text
        self._spans = spans
        self._ngroups = ngroups

    def _check(self, n):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > self._ngroups:
            raise IndexError("no such group")

    def span(self, n=0):
        self._check(n)
        return self._spans[n] if self._spans[n] is not None else (-1, -1)

    def start(self, n=0):
        self._check(n)
        sp = self._spans[n]
        return sp[0] if sp is not None else -1

    def end(self, n=0):
        self._check(n)
        sp = self._spans[n]
        return sp[1] if sp is not None else -1

    def group(self, n=0):
        self._check(n)
        sp = self._spans[n]
        if sp is None:
            return None
        return self._text[sp[0]:sp[1]]

    def groups(self):
        result = []
        for i in range(1, self._ngroups + 1):
            sp = self._spans[i]
            if sp is None:
                result.append(None)
            else:
                result.append(self._text[sp[0]:sp[1]])
        return tuple(result)

class Pattern:
    __slots__ = ('_ast', '_ngroups')
    def __init__(self, ast, ngroups):
        self._ast = ast
        self._ngroups = ngroups

    def fullmatch(self, s):
        m = _Matcher(s, self._ngroups)
        def cont(p):
            return p == len(s)
        if self._match_root(m, 0, cont):
            return Match(s, m.caps, self._ngroups)
        return None

    def search(self, s):
        for start in range(len(s) + 1):
            m = _Matcher(s, self._ngroups)
            def cont(p):
                return True
            if self._match_root(m, start, cont):
                return Match(s, m.caps, self._ngroups)
        return None

    def _match_root(self, m, start, cont):
        ast = self._ast
        n = self._ngroups
        def outer_cont(p):
            m.caps[0] = (start, p)
            return cont(p)
        return m._match(ast, start, outer_cont)

def compile(pattern: str) -> Pattern:
    parser = _Parser(pattern)
    ast = parser.parse()
    return Pattern(ast, parser.ngroups)
