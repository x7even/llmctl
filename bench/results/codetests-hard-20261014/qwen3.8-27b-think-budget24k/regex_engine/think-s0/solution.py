"""Backtracking-priority regular-expression engine (no external regex libs)."""

import sys

# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------

class _Node:
    __slots__ = ('id',)
    _next_id = 0

    def __init__(self):
        _Node._next_id += 1
        self.id = _Node._next_id


class Lit(_Node):
    __slots__ = ('ch',)
    def __init__(self, ch):
        super().__init__()
        self.ch = ch


class Dot(_Node):
    __slots__ = ()


class CClass(_Node):
    __slots__ = ('negated', 'chars', 'ranges')
    def __init__(self, negated, chars, ranges):
        super().__init__()
        self.negated = negated
        self.chars = chars      # set of single chars (str) and ('esc', code)
        self.ranges = ranges    # list of (lo, hi) code-point pairs

    def _positive(self, ch):
        cp = ord(ch)
        for c in self.chars:
            if isinstance(c, tuple):
                code = c[1]
                if code == 'd' and '0' <= ch <= '9':
                    return True
                if code == 'D' and not ('0' <= ch <= '9'):
                    return True
                if code == 'w' and (ch.isalnum() or ch == '_'):
                    return True
                if code == 'W' and not (ch.isalnum() or ch == '_'):
                    return True
                if code == 's' and ch in ' \t\n\r\f\v':
                    return True
                if code == 'S' and ch not in ' \t\n\r\f\v':
                    return True
            else:
                if ch == c:
                    return True
        for lo, hi in self.ranges:
            if lo <= cp <= hi:
                return True
        return False

    def matches(self, ch):
        return self._positive(ch) != self.negated


class Anchor(_Node):
    __slots__ = ('kind',)
    def __init__(self, kind):
        super().__init__()
        self.kind = kind  # '^' or '$'


class Group(_Node):
    __slots__ = ('index', 'children')
    def __init__(self, index, children):
        super().__init__()
        self.index = index
        self.children = children  # list[_Node]


class NonGroup(_Node):
    __slots__ = ('children',)
    def __init__(self, children):
        super().__init__()
        self.children = children


class Alt(_Node):
    __slots__ = ('branches',)
    def __init__(self, branches):
        super().__init__()
        self.branches = branches  # list[list[_Node]]


class Quant(_Node):
    __slots__ = ('atom', 'lo', 'hi', 'lazy')
    def __init__(self, atom, lo, hi, lazy):
        super().__init__()
        self.atom = atom
        self.lo = lo
        self.hi = hi      # None = unbounded
        self.lazy = lazy


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_ESC_MAP = {'d': 'd', 'D': 'D', 'w': 'w', 'W': 'W', 's': 's', 'S': 'S',
            'n': '\n', 't': '\t'}


def _parse_escape(s, pos):
    """s[pos] == '\\'.  Returns (value, new_pos).  value is a single char
    or a 2-char tag like ('esc','d')."""
    if pos + 1 >= len(s):
        raise ValueError("Trailing backslash in pattern")
    ch = s[pos + 1]
    if ch in _ESC_MAP:
        v = _ESC_MAP[ch]
        if v == ch:  # class escape
            return ('esc', ch), pos + 2
        return v, pos + 2
    if ch.isalnum():
        raise ValueError(f"Invalid escape \\{ch}")
    return ch, pos + 2


def _parse_class_char(s, pos):
    """Parse a single character item inside a class (after the opening [).
    Returns (char, new_pos).  char is a single str."""
    if s[pos] == '\\':
        if pos + 1 >= len(s):
            raise ValueError("Trailing backslash in class")
        ch = s[pos + 1]
        if ch in 'dDwWsS':
            raise ValueError("Class escape used as range endpoint")
        if ch == 'n':
            return '\n', pos + 2
        if ch == 't':
            return '\t', pos + 2
        if ch.isalnum():
            raise ValueError(f"Invalid escape \\{ch} in class")
        return ch, pos + 2
    return s[pos], pos + 1


def _parse_class(s, pos):
    """s[pos] == '['.  Returns (CClass, new_pos)."""
    pos += 1
    negated = False
    if pos < len(s) and s[pos] == '^':
        negated = True
        pos += 1

    chars = set()
    ranges = []

    # First ] right after [ or [^ is literal
    if pos < len(s) and s[pos] == ']':
        chars.add(']')
        pos += 1

    while pos < len(s):
        if s[pos] == ']':
            pos += 1
            break

        if s[pos] == '\\':
            val, pos = _parse_escape(s, pos)
            if isinstance(val, tuple):
                # class escape – cannot form a range
                if pos < len(s) and s[pos] == '-' and (pos + 1 >= len(s) or s[pos + 1] != ']'):
                    raise ValueError("Class escape in range")
                chars.add(val)
            else:
                # single char (could be \n, \t, or escaped literal)
                if pos + 1 < len(s) and s[pos] == '-' and s[pos + 1] != ']':
                    pos += 1
                    end_ch, pos = _parse_class_char(s, pos)
                    if val > end_ch:
                        raise ValueError("Invalid range in class")
                    ranges.append((ord(val), ord(end_ch)))
                else:
                    chars.add(val)
        else:
            ch = s[pos]
            pos += 1
            if pos + 1 < len(s) and s[pos] == '-' and s[pos + 1] != ']':
                pos += 1
                end_ch, pos = _parse_class_char(s, pos)
                if ch > end_ch:
                    raise ValueError("Invalid range in class")
                ranges.append((ord(ch), ord(end_ch)))
            else:
                chars.add(ch)

    if pos >= len(s):
        raise ValueError("Unclosed character class")
    return CClass(negated, chars, ranges), pos


def _parse_quantifier(s, pos):
    """s[pos] is one of * + ? {.  Returns (lo, hi, new_pos)."""
    if s[pos] == '*':
        return 0, None, pos + 1
    if s[pos] == '+':
        return 1, None, pos + 1
    if s[pos] == '?':
        return 0, 1, pos + 1
    # '{'
    end = s.find('}', pos + 1)
    if end == -1:
        raise ValueError("Unclosed { in quantifier")
    inner = s[pos + 1:end]
    if ',' in inner:
        parts = inner.split(',')
        if len(parts) != 2:
            raise ValueError("Invalid quantifier")
        m_str, n_str = parts
        if not m_str or not m_str.isdigit():
            raise ValueError("Invalid quantifier")
        if n_str and not n_str.isdigit():
            raise ValueError("Invalid quantifier")
        lo = int(m_str)
        hi = int(n_str) if n_str else None
        if hi is not None and lo > hi:
            raise ValueError("m > n in quantifier")
    else:
        if not inner or not inner.isdigit():
            raise ValueError("Invalid quantifier")
        lo = hi = int(inner)
    return lo, hi, end + 1


def _parse_atom(s, pos, group_counter):
    ch = s[pos]
    if ch == '(':
        return _parse_group(s, pos, group_counter)
    if ch == '[':
        return _parse_class(s, pos)
    if ch == '.':
        return Dot(), pos + 1
    if ch == '^':
        return Anchor('^'), pos + 1
    if ch == '$':
        return Anchor('$'), pos + 1
    if ch == '\\':
        val, pos = _parse_escape(s, pos)
        if isinstance(val, tuple):
            # class escape outside a class – not valid as a standalone atom
            # Actually the spec says \d \D \w \W \s \S are valid escapes
            # They should match as a class.  Let's wrap in a CClass.
            code = val[1]
            if code == 'd':
                return CClass(False, set(), [(ord('0'), ord('9'))]), pos
            if code == 'D':
                return CClass(True, set(), [(ord('0'), ord('9'))]), pos
            if code == 'w':
                # [A-Za-z0-9_]
                return CClass(False, {'_'}, [(ord('A'), ord('Z')), (ord('a'), ord('z')), (ord('0'), ord('9'))]), pos
            if code == 'W':
                return CClass(True, {'_'}, [(ord('A'), ord('Z')), (ord('a'), ord('z')), (ord('0'), ord('9'))]), pos
            if code == 's':
                return CClass(False, set(' \t\n\r\f\v'), []), pos
            if code == 'S':
                return CClass(True, set(' \t\n\r\f\v'), []), pos
        return Lit(val), pos
    return Lit(ch), pos + 1


def _parse_group(s, pos, group_counter):
    # s[pos] == '('
    pos += 1
    if pos < len(s) and s[pos] == '?':
        if pos + 1 < len(s) and s[pos + 1] == ':':
            pos += 2
            children, pos = _parse_alt(s, pos, group_counter)
            if pos >= len(s) or s[pos] != ')':
                raise ValueError("Unclosed non-capturing group")
            pos += 1
            return NonGroup(children), pos
        else:
            raise ValueError("Invalid group syntax (?...)")
    # capturing group
    children, pos = _parse_alt(s, pos, group_counter)
    if pos >= len(s) or s[pos] != ')':
        raise ValueError("Unclosed group")
    pos += 1
    group_counter[0] += 1
    return Group(group_counter[0], children), pos


def _parse_quantified(s, pos, group_counter):
    atom, pos = _parse_atom(s, pos, group_counter)
    if isinstance(atom, Anchor):
        if pos < len(s) and s[pos] in '*+?{':
            raise ValueError("Cannot quantify anchor")
        return atom, pos
    if pos < len(s) and s[pos] in '*+?{':
        lo, hi, pos = _parse_quantifier(s, pos)
        lazy = False
        if pos < len(s) and s[pos] == '?':
            lazy = True
            pos += 1
        return Quant(atom, lo, hi, lazy), pos
    return atom, pos


def _parse_seq(s, pos, group_counter):
    nodes = []
    while pos < len(s) and s[pos] not in '|)':
        if s[pos] in '*+?{':
            if not nodes:
                raise ValueError("Nothing to repeat")
            if isinstance(nodes[-1], Quant):
                raise ValueError("Multiple quantifiers")
            raise ValueError("Nothing to repeat")
        node, pos = _parse_quantified(s, pos, group_counter)
        nodes.append(node)
    return nodes, pos


def _parse_alt(s, pos, group_counter):
    branches = []
    branch, pos = _parse_seq(s, pos, group_counter)
    branches.append(branch)
    while pos < len(s) and s[pos] == '|':
        pos += 1
        branch, pos = _parse_seq(s, pos, group_counter)
        branches.append(branch)
    if len(branches) == 1:
        return branches[0], pos
    return Alt(branches), pos


def _parse_pattern(pattern):
    group_counter = [0]
    nodes, pos = _parse_alt(pattern, 0, group_counter)
    if pos != len(pattern):
        raise ValueError(f"Unexpected character at position {pos}")
    return nodes, group_counter[0]


# ---------------------------------------------------------------------------
# Matcher  (iterative, with failure memo)
# ---------------------------------------------------------------------------

def _match_atom(node, s, pos, caps):
    """Match a single non-Quant, non-Seq atom.  Returns (pos, caps) or None."""
    if isinstance(node, Lit):
        if pos < len(s) and s[pos] == node.ch:
            return pos + 1, caps
        return None
    if isinstance(node, Dot):
        if pos < len(s) and s[pos] != '\n':
            return pos + 1, caps
        return None
    if isinstance(node, CClass):
        if pos < len(s) and node.matches(s[pos]):
            return pos + 1, caps
        return None
    if isinstance(node, Anchor):
        if node.kind == '^':
            if pos == 0:
                return pos, caps
        else:  # '$'
            if pos == len(s) or (pos == len(s) - 1 and s[pos] == '\n'):
                return pos, caps
        return None
    if isinstance(node, Group):
        start = pos
        res = _match_children(node.children, s, pos, caps)
        if res is None:
            return None
        p, c = res
        nc = list(caps)
        nc[node.index] = (start, p)
        return p, nc
    if isinstance(node, NonGroup):
        return _match_children(node.children, s, pos, caps)
    if isinstance(node, Alt):
        for branch in node.branches:
            res = _match_children(branch, s, pos, caps)
            if res is not None:
                return res
        return None
    # Should not reach here for Quant (handled by _match_children)
    return None


def _match_children(children, s, pos, caps):
    """Match a list of nodes sequentially.  Returns (pos, caps) or None."""
    i = 0
    n = len(children)
    while i < n:
        node = children[i]
        if isinstance(node, Quant):
            # Build rest as a closure over the remaining children
            rest = children[i + 1:]
            res = _match_quant(node, s, pos, caps, rest)
            if res is None:
                return None
            pos, caps = res
            i += 1
        else:
            res = _match_atom(node, s, pos, caps)
            if res is None:
                return None
            pos, caps = res
            i += 1
    return pos, caps


def _match_quant(node, s, pos, caps, rest):
    """Match a Quant node.  *rest* is the list of nodes that follow.
    Returns (pos, caps) or None."""
    if node.lo == 0 and node.hi == 0:
        # x{0} or x{0,0}: match empty without running atom
        return _match_children(rest, s, pos, caps)

    if node.lazy:
        # ---- lazy: try stopping first, then one more iteration ----
        c = 0
        mark = None
        while True:
            if c < node.lo:
                res = _match_atom(node.atom, s, pos, caps)
                if res is None:
                    return None
                pos, caps = res
                c += 1
                continue
            # try to stop
            res = _match_children(rest, s, pos, caps)
            if res is not None:
                return res
            # try one more iteration
            if (node.hi is not None and c >= node.hi) or pos == mark:
                return None
            mark = pos
            res = _match_atom(node.atom, s, pos, caps)
            if res is None:
                return None
            pos, caps = res
            c += 1
    else:
        # ---- greedy: collect stop-points, try in reverse ----
        c = 0
        mark = None
        stops = []
        while True:
            if c < node.lo:
                res = _match_atom(node.atom, s, pos, caps)
                if res is None:
                    return None
                pos, caps = res
                c += 1
                continue
            stops.append((pos, list(caps)))
            if (node.hi is None or c < node.hi) and pos != mark:
                mark = pos
                res = _match_atom(node.atom, s, pos, caps)
                if res is None:
                    break
                pos, caps = res
                c += 1
            else:
                break
        for sp, sc in reversed(stops):
            res = _match_children(rest, s, sp, sc)
            if res is not None:
                return res
        return None


def _do_match(pattern_nodes, s, start, full):
    """Core matcher.  Returns (end_pos, captures_list) or None.
    captures_list[0] is always (start, end); 1..N are groups."""
    memo = set()
    ngroups = 0
    # count groups
    def _count_groups(nodes):
        cnt = 0
        for nd in nodes:
            if isinstance(nd, Group):
                cnt += 1
            elif isinstance(nd, NonGroup):
                cnt += _count_groups(nd.children)
            elif isinstance(nd, Alt):
                for br in nd.branches:
                    cnt += _count_groups(br)
            elif isinstance(nd, Quant):
                cnt += _count_groups([nd.atom])
        return cnt
    ngroups = _count_groups(pattern_nodes)

    stack = [(pattern_nodes, 0, start, [None] * (ngroups + 1))]
    # stack items: (children, idx, pos, caps)
    # We use a work-stack for backtracking.

    # Actually, let me use a simpler recursive approach with the memo,
    # but handle quantifiers iteratively to limit recursion depth.
    # The recursion depth is bounded by AST depth (groups, alts), not string length.

    sys.setrecursionlimit(max(sys.getrecursionlimit(), 100000))

    def _mc(children, pos, caps):
        """Match children list.  Returns (pos, caps) or None."""
        for i, node in enumerate(children):
            if isinstance(node, Quant):
                rest = children[i + 1:]
                res = _mq(node, pos, caps, rest)
            else:
                res = _ma(node, pos, caps)
            if res is None:
                return None
            pos, caps = res
        return pos, caps

    def _ma(node, pos, caps):
        key = (node.id, pos)
        if key in memo:
            return None
        res = _ma_inner(node, pos, caps)
        if res is None:
            memo.add(key)
        return res

    def _ma_inner(node, pos, caps):
        if isinstance(node, Lit):
            if pos < len(s) and s[pos] == node.ch:
                return pos + 1, caps
            return None
        if isinstance(node, Dot):
            if pos < len(s) and s[pos] != '\n':
                return pos + 1, caps
            return None
        if isinstance(node, CClass):
            if pos < len(s) and node.matches(s[pos]):
                return pos + 1, caps
            return None
        if isinstance(node, Anchor):
            if node.kind == '^':
                if pos == 0:
                    return pos, caps
            else:
                if pos == len(s) or (pos == len(s) - 1 and s[pos] == '\n'):
                    return pos, caps
            return None
        if isinstance(node, Group):
            st = pos
            res = _mc(node.children, pos, caps)
            if res is None:
                return None
            p, c = res
            nc = list(c)
            nc[node.index] = (st, p)
            return p, nc
        if isinstance(node, NonGroup):
            return _mc(node.children, pos, caps)
        if isinstance(node, Alt):
            for br in node.branches:
                res = _mc(br, pos, caps)
                if res is not None:
                    return res
            return None
        return None

    def _mq(node, pos, caps, rest):
        key = (node.id, pos)
        if key in memo:
            return None
        res = _mq_inner(node, pos, caps, rest)
        if res is None:
            memo.add(key)
        return res

    def _mq_inner(node, pos, caps, rest):
        if node.lo == 0 and node.hi == 0:
            return _mc(rest, pos, caps)

        if node.lazy:
            c = 0
            mark = None
            while True:
                if c < node.lo:
                    res = _ma(node.atom, pos, caps)
                    if res is None:
                        return None
                    pos, caps = res
                    c += 1
                    continue
                res = _mc(rest, pos, caps)
                if res is not None:
                    return res
                if (node.hi is not None and c >= node.hi) or pos == mark:
                    return None
                mark = pos
                res = _ma(node.atom, pos, caps)
                if res is None:
                    return None
                pos, caps = res
                c += 1
        else:
            c = 0
            mark = None
            stops = []
            while True:
                if c < node.lo:
                    res = _ma(node.atom, pos, caps)
                    if res is None:
                        return None
                    pos, caps = res
                    c += 1
                    continue
                stops.append((pos, list(caps)))
                if (node.hi is None or c < node.hi) and pos != mark:
                    mark = pos
                    res = _ma(node.atom, pos, caps)
                    if res is None:
                        break
                    pos, caps = res
                    c += 1
                else:
                    break
            for sp, sc in reversed(stops):
                res = _mc(rest, sp, sc)
                if res is not None:
                    return res
            return None

    # --- main entry ---
    caps = [None] * (ngroups + 1)
    res = _mc(pattern_nodes, start, caps)
    if res is None:
        return None
    end, caps = res
    if full and end != len(s):
        return None
    caps[0] = (start, end)
    return end, caps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class Match:
    __slots__ = ('_s', '_start', '_end', '_groups')

    def __init__(self, s, start, end, groups):
        self._s = s
        self._start = start
        self._end = end
        self._groups = groups  # tuple of (start, end) or None, index 0..N

    def span(self, n=0):
        self._check(n)
        if n == 0:
            return (self._start, self._end)
        g = self._groups[n]
        if g is None:
            return (-1, -1)
        return g

    def start(self, n=0):
        self._check(n)
        if n == 0:
            return self._start
        g = self._groups[n]
        if g is None:
            return -1
        return g[0]

    def end(self, n=0):
        self._check(n)
        if n == 0:
            return self._end
        g = self._groups[n]
        if g is None:
            return -1
        return g[1]

    def group(self, n=0):
        self._check(n)
        if n == 0:
            return self._s[self._start:self._end]
        g = self._groups[n]
        if g is None:
            return None
        return self._s[g[0]:g[1]]

    def groups(self):
        out = []
        for i in range(1, len(self._groups)):
            g = self._groups[i]
            if g is None:
                out.append(None)
            else:
                out.append(self._s[g[0]:g[1]])
        return tuple(out)

    def _check(self, n):
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError(f"Invalid group number {n!r}")
        if n < 0 or n >= len(self._groups):
            raise IndexError(f"Invalid group number {n}")


class Pattern:
    __slots__ = ('_nodes', '_ngroups')

    def __init__(self, nodes, ngroups):
        self._nodes = nodes
        self._ngroups = ngroups

    def fullmatch(self, s):
        res = _do_match(self._nodes, s, 0, True)
        if res is None:
            return None
        end, caps = res
        return Match(s, 0, end, tuple(caps))

    def search(self, s):
        for start in range(len(s) + 1):
            res = _do_match(self._nodes, s, start, False)
            if res is not None:
                end, caps = res
                return Match(s, start, end, tuple(caps))
        return None


def compile(pattern):
    nodes, ngroups = _parse_pattern(pattern)
    return Pattern(nodes, ngroups)
