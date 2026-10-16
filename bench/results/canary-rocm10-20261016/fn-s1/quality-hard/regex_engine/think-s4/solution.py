"""Backtracking-priority regular-expression engine implemented from scratch."""
import sys
sys.setrecursionlimit(200_000)

# ─── AST node types ───────────────────────────────────────────────────────────

class _Lit:
    __slots__ = ('char', 'nid')
    def __init__(self, char, nid): self.char = char; self.nid = nid

class _Dot:
    __slots__ = ('nid',)
    def __init__(self, nid): self.nid = nid

class _Class:
    __slots__ = ('chars', 'nid')
    def __init__(self, chars, nid): self.chars = chars; self.nid = nid

class _Start:
    __slots__ = ('nid',)
    def __init__(self, nid): self.nid = nid

class _End:
    __slots__ = ('nid',)
    def __init__(self, nid): self.nid = nid

class _Concat:
    __slots__ = ('children', 'nid')
    def __init__(self, children, nid): self.children = children; self.nid = nid

class _Alt:
    __slots__ = ('branches', 'nid')
    def __init__(self, branches, nid): self.branches = branches; self.nid = nid

class _Group:
    __slots__ = ('child', 'num', 'nid')
    def __init__(self, child, num, nid): self.child = child; self.num = num; self.nid = nid

class _Quant:
    __slots__ = ('child', 'lo', 'hi', 'greedy', 'nid')
    def __init__(self, child, lo, hi, greedy, nid):
        self.child = child; self.lo = lo; self.hi = hi; self.greedy = greedy; self.nid = nid

class _Empty:
    __slots__ = ('nid',)
    def __init__(self, nid): self.nid = nid

# ─── Helper sets ──────────────────────────────────────────────────────────────

_DIGITS = frozenset('0123456789')
_WS = frozenset(' \t\n\r\f\v')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_ALL_ASCII = frozenset(chr(c) for c in range(128))

def _escape_set(ch):
    if ch == 'd': return _DIGITS
    if ch == 'D': return _ALL_ASCII - _DIGITS
    if ch == 'w': return _WORD
    if ch == 'W': return _ALL_ASCII - _WORD
    if ch == 's': return _WS
    if ch == 'S': return _ALL_ASCII - _WS

# ─── Parser ───────────────────────────────────────────────────────────────────

class _Parser:
    def __init__(self, pattern):
        self.p = pattern
        self.pos = 0
        self.num_groups = 0
        self._nid = 0

    def _nid(self):
        self._nid += 1
        return self._nid

    def parse(self):
        node = self._alt()
        if self.pos != len(self.p):
            raise ValueError("Invalid pattern: unexpected character")
        return node, self.num_groups

    def _alt(self):
        branches = [self._seq()]
        while self.pos < len(self.p) and self.p[self.pos] == '|':
            self.pos += 1
            branches.append(self._seq())
        if len(branches) == 1:
            return branches[0]
        return _Alt(tuple(branches), self._nid())

    def _seq(self):
        items = []
        while self.pos < len(self.p) and self.p[self.pos] not in '|)':
            items.append(self._quantified())
        if not items:
            return _Empty(self._nid())
        if len(items) == 1:
            return items[0]
        return _Concat(tuple(items), self._nid())

    def _quantified(self):
        atom = self._atom()
        if self.pos < len(self.p):
            ch = self.p[self.pos]
            if ch in '*+?':
                if isinstance(atom, (_Start, _End)):
                    raise ValueError("Cannot quantify anchor")
                self.pos += 1
                greedy = True
                if self.pos < len(self.p) and self.p[self.pos] == '?':
                    greedy = False
                    self.pos += 1
                if ch == '*': lo, hi = 0, None
                elif ch == '+': lo, hi = 1, None
                else: lo, hi = 0, 1
                result = _Quant(atom, lo, hi, greedy, self._nid())
                if self.pos < len(self.p) and self.p[self.pos] in '*+?{':
                    raise ValueError("Quantifier after quantifier")
                return result
            elif ch == '{':
                if isinstance(atom, (_Start, _End)):
                    raise ValueError("Cannot quantify anchor")
                lo, hi, greedy = self._brace()
                result = _Quant(atom, lo, hi, greedy, self._nid())
                if self.pos < len(self.p) and self.p[self.pos] in '*+?{':
                    raise ValueError("Quantifier after quantifier")
                return result
        return atom

    def _brace(self):
        self.pos += 1  # skip '{'
        start = self.pos
        while self.pos < len(self.p) and self.p[self.pos] in _DIGITS:
            self.pos += 1
        if self.pos == start:
            raise ValueError("Invalid quantifier: missing digits")
        m = int(self.p[start:self.pos])
        hi = m
        if self.pos < len(self.p) and self.p[self.pos] == ',':
            self.pos += 1
            nstart = self.pos
            while self.pos < len(self.p) and self.p[self.pos] in _DIGITS:
                self.pos += 1
            if self.pos > nstart:
                hi = int(self.p[nstart:self.pos])
                if m > hi:
                    raise ValueError("m > n in quantifier")
            else:
                hi = None
        if self.pos >= len(self.p) or self.p[self.pos] != '}':
            raise ValueError("Invalid quantifier: missing }")
        self.pos += 1
        greedy = True
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            greedy = False
            self.pos += 1
        return m, hi, greedy

    def _atom(self):
        if self.pos >= len(self.p):
            return _Empty(self._nid())
        ch = self.p[self.pos]
        if ch == '(':
            return self._group()
        if ch == '[':
            return self._class()
        if ch == '.':
            self.pos += 1
            return _Dot(self._nid())
        if ch == '^':
            self.pos += 1
            return _Start(self._nid())
        if ch == '$':
            self.pos += 1
            return _End(self._nid())
        if ch == '\\':
            return self._escape_atom()
        if ch in '*+?':
            raise ValueError("Nothing to repeat")
        self.pos += 1
        return _Lit(ch, self._nid())

    def _group(self):
        self.pos += 1  # skip '('
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            if self.pos + 1 < len(self.p) and self.p[self.pos + 1] == ':':
                self.pos += 2
                child = self._alt()
                if self.pos >= len(self.p) or self.p[self.pos] != ')':
                    raise ValueError("Unclosed group")
                self.pos += 1
                return _Group(child, 0, self._nid())
            raise ValueError("Unsupported group syntax")
        self.num_groups += 1
        num = self.num_groups
        child = self._alt()
        if self.pos >= len(self.p) or self.p[self.pos] != ')':
            raise ValueError("Unclosed group")
        self.pos += 1
        return _Group(child, num, self._nid())

    def _escape_atom(self):
        self.pos += 1
        if self.pos >= len(self.p):
            raise ValueError("Backslash at end of pattern")
        ch = self.p[self.pos]
        self.pos += 1
        if ch in 'dDwWsS':
            return _Class(_escape_set(ch), self._nid())
        if ch == 'n': return _Lit('\n', self._nid())
        if ch == 't': return _Lit('\t', self._nid())
        if ch.isalpha() or ch.isdigit():
            raise ValueError(f"Invalid escape \\{ch}")
        return _Lit(ch, self._nid())

    def _class(self):
        self.pos += 1  # skip '['
        negate = False
        if self.pos < len(self.p) and self.p[self.pos] == '^':
            negate = True
            self.pos += 1
        chars = set()
        # First ']' right after [ or [^ is literal
        if self.pos < len(self.p) and self.p[self.pos] == ']':
            chars.add(']')
            self.pos += 1
        while self.pos < len(self.p):
            if self.p[self.pos] == ']':
                self.pos += 1
                if negate:
                    result = _ALL_ASCII - frozenset(chars)
                else:
                    result = frozenset(chars)
                return _Class(result, self._nid())
            # Parse one item
            item_ch, is_esc, item_set = self._class_item()
            # Check for range: next char is '-' and char after is not ']'
            if (self.pos < len(self.p) and self.p[self.pos] == '-'
                    and self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']'):
                if is_esc:
                    raise ValueError("Class escape cannot be start of range")
                self.pos += 1  # skip '-'
                end_ch, end_esc, _ = self._class_item()
                if end_esc:
                    raise ValueError("Class escape cannot be end of range")
                if item_ch > end_ch:
                    raise ValueError("Invalid range")
                for c in range(ord(item_ch), ord(end_ch) + 1):
                    chars.add(chr(c))
            else:
                if is_esc:
                    chars.update(item_set)
                else:
                    chars.add(item_ch)
        raise ValueError("Unterminated character class")

    def _class_item(self):
        if self.p[self.pos] == '\\':
            self.pos += 1
            if self.pos >= len(self.p):
                raise ValueError("Backslash at end of class")
            ch = self.p[self.pos]
            self.pos += 1
            if ch in 'dDwWsS':
                return (None, True, _escape_set(ch))
            if ch == 'n': return ('\n', False, None)
            if ch == 't': return ('\t', False, None)
            if ch.isalpha() or ch.isdigit():
                raise ValueError(f"Invalid escape in class \\{ch}")
            return (ch, False, None)
        ch = self.p[self.pos]
        self.pos += 1
        return (ch, False, None)

# ─── Matcher ──────────────────────────────────────────────────────────────────

def _match(node, pos, cont, captures, s, memo):
    t = type(node)
    if t is _Lit:
        if pos < len(s) and s[pos] == node.char:
            return cont(pos + 1, captures)
        return False
    if t is _Dot:
        if pos < len(s) and s[pos] != '\n':
            return cont(pos + 1, captures)
        return False
    if t is _Class:
        if pos < len(s) and s[pos] in node.chars:
            return cont(pos + 1, captures)
        return False
    if t is _Start:
        if pos == 0:
            return cont(pos, captures)
        return False
    if t is _End:
        n = len(s)
        if pos == n or (pos == n - 1 and s[pos] == '\n'):
            return cont(pos, captures)
        return False
    if t is _Empty:
        return cont(pos, captures)
    if t is _Concat:
        children = node.children
        def _seq(i, p, caps):
            if i == len(children):
                return cont(p, caps)
            return _match(children[i], p,
                          lambda np, nc, _i=i: _seq(_i + 1, np, nc),
                          caps, s, memo)
        return _seq(0, pos, captures)
    if t is _Alt:
        for branch in node.branches:
            if _match(branch, pos, cont, captures, s, memo):
                return True
        return False
    if t is _Group:
        if node.num == 0:
            return _match(node.child, pos, cont, captures, s, memo)
        gnum = node.num
        def _gcont(new_pos, caps):
            new_caps = list(caps)
            new_caps[gnum] = (pos, new_pos)
            return cont(new_pos, tuple(new_caps))
        return _match(node.child, pos, _gcont, captures, s, memo)
    if t is _Quant:
        return _match_quant(node, pos, cont, captures, s, memo)
    raise RuntimeError("Unknown node")

def _match_quant(node, pos, cont, captures, s, memo):
    lo, hi, greedy = node.lo, node.hi, node.greedy
    if hi is not None and hi == 0:
        return cont(pos, captures)
    nid = node.nid
    child = node.child

    def loop(c, mark, p, caps):
        if hi is None:
            key = (nid, p)
        else:
            key = (nid, p, c)
        if key in memo:
            return False

        if c < lo:
            result = _match(child, p,
                            lambda np, nc, _c=c, _m=mark: loop(_c + 1, _m, np, nc),
                            caps, s, memo)
            if not result:
                memo.add(key)
            return result

        # optional phase (c >= lo)
        if greedy:
            can = (hi is None or c < hi) and p != mark
            if can:
                result = _match(child, p,
                                lambda np, nc, _c=c, _mk=p: loop(_c + 1, _mk, np, nc),
                                caps, s, memo)
                if result:
                    return True
                result = cont(p, caps)
                if not result:
                    memo.add(key)
                return result
            else:
                result = cont(p, caps)
                if not result:
                    memo.add(key)
                return result
        else:
            # lazy
            result = cont(p, caps)
            if result:
                return True
            if (hi is not None and c >= hi) or p == mark:
                memo.add(key)
                return False
            result = _match(child, p,
                            lambda np, nc, _c=c, _mk=p: loop(_c + 1, _mk, np, nc),
                            caps, s, memo)
            if not result:
                memo.add(key)
            return result

    return loop(0, None, pos, captures)

# ─── Public API ───────────────────────────────────────────────────────────────

class Match:
    __slots__ = ('_s', '_start', '_end', '_captures', '_ng')

    def __init__(self, s, start, end, captures, ng):
        self._s = s
        self._start = start
        self._end = end
        self._captures = captures
        self._ng = ng

    def span(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError(n)
        if n < 0 or n > self._ng:
            raise IndexError(n)
        if n == 0:
            return (self._start, self._end)
        cap = self._captures[n]
        if cap is None:
            return (-1, -1)
        return cap

    def start(self, n=0):
        return self.span(n)[0]

    def end(self, n=0):
        return self.span(n)[1]

    def group(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError(n)
        if n < 0 or n > self._ng:
            raise IndexError(n)
        if n == 0:
            return self._s[self._start:self._end]
        cap = self._captures[n]
        if cap is None:
            return None
        return self._s[cap[0]:cap[1]]

    def groups(self):
        out = []
        for i in range(1, self._ng + 1):
            cap = self._captures[i]
            if cap is None:
                out.append(None)
            else:
                out.append(self._s[cap[0]:cap[1]])
        return tuple(out)


class Pattern:
    __slots__ = ('_root', '_ng')

    def __init__(self, root, ng):
        self._root = root
        self._ng = ng

    def fullmatch(self, s):
        memo = set()
        init_caps = tuple([None] * (self._ng + 1))
        n = len(s)
        result = [None]

        def final_cont(pos, caps):
            if pos == n:
                result[0] = (0, pos, caps)
                return True
            return False

        if _match(self._root, 0, final_cont, init_caps, s, memo):
            start, end, caps = result[0]
            return Match(s, start, end, caps, self._ng)
        return None

    def search(self, s):
        memo = set()
        init_caps = tuple([None] * (self._ng + 1))
        n = len(s)
        for start in range(n + 1):
            result = [None]

            def final_cont(pos, caps, _st=start):
                result[0] = (_st, pos, caps)
                return True

            if _match(self._root, start, final_cont, init_caps, s, memo):
                st, en, caps = result[0]
                return Match(s, st, en, caps, self._ng)
        return None


def compile(pattern: str) -> Pattern:
    parser = _Parser(pattern)
    root, ng = parser.parse()
    return Pattern(root, ng)
