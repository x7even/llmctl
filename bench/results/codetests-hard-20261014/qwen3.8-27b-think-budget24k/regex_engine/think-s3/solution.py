import sys
sys.setrecursionlimit(200000)


# ─── AST Nodes ───────────────────────────────────────────────────────────────

class _Node:
    pass

class _Literal(_Node):
    __slots__ = ('ch',)
    def __init__(self, ch):
        self.ch = ch

class _Dot(_Node):
    __slots__ = ()

class _CharClass(_Node):
    __slots__ = ('char_set', 'negated')
    def __init__(self, char_set, negated=False):
        self.char_set = char_set
        self.negated = negated

class _ClassEscape(_Node):
    __slots__ = ('code',)
    def __init__(self, code):
        self.code = code

class _AnchorStart(_Node):
    __slots__ = ()

class _AnchorEnd(_Node):
    __slots__ = ()

class _Group(_Node):
    __slots__ = ('index', 'body')
    def __init__(self, index, body):
        self.index = index
        self.body = body

class _NonCapGroup(_Node):
    __slots__ = ('body',)
    def __init__(self, body):
        self.body = body

class _Alt(_Node):
    __slots__ = ('branches',)
    def __init__(self, branches):
        self.branches = branches

class _Seq(_Node):
    __slots__ = ('items',)
    def __init__(self, items):
        self.items = items

class _Quantified(_Node):
    __slots__ = ('atom', 'lo', 'hi', 'lazy')
    def __init__(self, atom, lo, hi, lazy):
        self.atom = atom
        self.lo = lo
        self.hi = hi  # None = unbounded
        self.lazy = lazy


# ─── Character set helpers ───────────────────────────────────────────────────

_ASCII = set(chr(i) for i in range(128))
_DIGITS = set('0123456789')
_WORD = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_')
_SPACE = set(' \t\n\r\f\v')

def _escape_set(code):
    if code == 'd': return _DIGITS
    if code == 'D': return _ASCII - _DIGITS
    if code == 'w': return _WORD
    if code == 'W': return _ASCII - _WORD
    if code == 's': return _SPACE
    if code == 'S': return _ASCII - _SPACE

def _escape_matches(code, ch):
    if code == 'd': return ch in _DIGITS
    if code == 'D': return ch not in _DIGITS
    if code == 'w': return ch in _WORD
    if code == 'W': return ch not in _WORD
    if code == 's': return ch in _SPACE
    if code == 'S': return ch not in _SPACE


# ─── Parser ──────────────────────────────────────────────────────────────────

class _Parser:
    def __init__(self, pattern):
        self.s = pattern
        self.pos = 0
        self.n = len(pattern)
        self.num_groups = 0

    def parse(self):
        node = self._parse_alt()
        if self.pos != self.n:
            raise ValueError(f"Unexpected character at position {self.pos}")
        return node

    def _parse_alt(self):
        branches = [self._parse_seq()]
        while self.pos < self.n and self.s[self.pos] == '|':
            self.pos += 1
            branches.append(self._parse_seq())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _parse_seq(self):
        items = []
        while self.pos < self.n and self.s[self.pos] != '|':
            items.append(self._parse_item())
        if not items:
            return _Seq([])
        if len(items) == 1:
            return items[0]
        return _Seq(items)

    def _parse_item(self):
        atom = self._parse_atom()
        if self.pos < self.n and self.s[self.pos] in '*+?{':
            if isinstance(atom, (_AnchorStart, _AnchorEnd)):
                raise ValueError("Cannot quantify anchor")
            lo, hi, lazy = self._parse_quantifier()
            return _Quantified(atom, lo, hi, lazy)
        return atom

    def _parse_atom(self):
        ch = self.s[self.pos]
        if ch in '*+?{':
            raise ValueError(f"Nothing to repeat at position {self.pos}")
        if ch == '(':
            return self._parse_group()
        if ch == '[':
            return self._parse_class()
        if ch == '.':
            self.pos += 1
            return _Dot()
        if ch == '^':
            self.pos += 1
            return _AnchorStart()
        if ch == '$':
            self.pos += 1
            return _AnchorEnd()
        if ch == '\\':
            return self._parse_escape_outside()
        if ch == ')':
            raise ValueError(f"Unmatched ) at position {self.pos}")
        self.pos += 1
        return _Literal(ch)

    def _parse_group(self):
        assert self.s[self.pos] == '('
        self.pos += 1
        if self.pos < self.n and self.s[self.pos] == '?':
            self.pos += 1
            if self.pos < self.n and self.s[self.pos] == ':':
                self.pos += 1
                body = self._parse_alt()
                if self.pos >= self.n or self.s[self.pos] != ')':
                    raise ValueError("Unclosed (?:")
                self.pos += 1
                return _NonCapGroup(body)
            else:
                raise ValueError(f"Invalid group syntax at position {self.pos - 2}")
        self.num_groups += 1
        idx = self.num_groups
        body = self._parse_alt()
        if self.pos >= self.n or self.s[self.pos] != ')':
            raise ValueError("Unclosed (")
        self.pos += 1
        return _Group(idx, body)

    def _parse_escape_outside(self):
        assert self.s[self.pos] == '\\'
        self.pos += 1
        if self.pos >= self.n:
            raise ValueError("Trailing backslash in pattern")
        ch = self.s[self.pos]
        if ch in 'dDwWsS':
            self.pos += 1
            return _ClassEscape(ch)
        if ch == 'n':
            self.pos += 1
            return _Literal('\n')
        if ch == 't':
            self.pos += 1
            return _Literal('\t')
        if not (ch.isalpha() or ch.isdigit()):
            self.pos += 1
            return _Literal(ch)
        raise ValueError(f"Invalid escape \\{ch}")

    def _parse_class(self):
        assert self.s[self.pos] == '['
        self.pos += 1
        negated = False
        if self.pos < self.n and self.s[self.pos] == '^':
            negated = True
            self.pos += 1

        char_set = set()
        first = True
        while True:
            if self.pos >= self.n:
                raise ValueError("Unclosed [")
            ch = self.s[self.pos]
            if ch == ']' and not first:
                self.pos += 1
                break
            # Parse one item
            if ch == '\\':
                self.pos += 1
                if self.pos >= self.n:
                    raise ValueError("Trailing backslash in class")
                ech = self.s[self.pos]
                if ech in 'dDwWsS':
                    self.pos += 1
                    # Check for range: escape followed by -
                    if self.pos < self.n and self.s[self.pos] == '-' and \
                       self.pos + 1 < self.n and self.s[self.pos + 1] != ']':
                        raise ValueError("Cannot use class escape in range")
                    char_set |= _escape_set(ech)
                elif ech == 'n':
                    self.pos += 1
                    char_set.add('\n')
                elif ech == 't':
                    self.pos += 1
                    char_set.add('\t')
                elif not (ech.isalpha() or ech.isdigit()):
                    self.pos += 1
                    char_set.add(ech)
                else:
                    raise ValueError(f"Invalid escape \\{ech} in class")
            else:
                self.pos += 1
                char_set.add(ch)

            # Check for range (only for single-char items, not escapes)
            if self.pos < self.n and self.s[self.pos] == '-' and \
               self.pos + 1 < self.n and self.s[self.pos + 1] != ']':
                # Potential range
                # The item we just added must be a single char (not an escape)
                # We need to check: was the last thing a single char or an escape?
                # Since we added to char_set, we need to track this differently.
                # Let me restructure...
                pass  # handled below

            first = False

        # Actually, the range logic above is wrong because I'm adding to a set
        # immediately. Let me redo the class parsing.
        # I'll redo this entirely.
        raise RuntimeError("unreachable")

    def _parse_quantifier(self):
        ch = self.s[self.pos]
        if ch == '*':
            self.pos += 1
            lo, hi = 0, None
        elif ch == '+':
            self.pos += 1
            lo, hi = 1, None
        elif ch == '?':
            self.pos += 1
            lo, hi = 0, 1
        elif ch == '{':
            self.pos += 1
            start = self.pos
            while self.pos < self.n and self.s[self.pos].isdigit():
                self.pos += 1
            m_str = self.s[start:self.pos]
            if not m_str:
                raise ValueError("Invalid {")
            m = int(m_str)
            if self.pos < self.n and self.s[self.pos] == ',':
                self.pos += 1
                start = self.pos
                while self.pos < self.n and self.s[self.pos].isdigit():
                    self.pos += 1
                n_str = self.s[start:self.pos]
                if n_str:
                    n_val = int(n_str)
                    if m > n_val:
                        raise ValueError(f"m > n in {{{m},{n_val}}}")
                    lo, hi = m, n_val
                else:
                    lo, hi = m, None
            elif self.pos < self.n and self.s[self.pos] == '}':
                self.pos += 1
                lo, hi = m, m
            else:
                raise ValueError("Invalid {")
        else:
            raise ValueError(f"Invalid quantifier")

        lazy = False
        if self.pos < self.n and self.s[self.pos] == '?':
            lazy = True
            self.pos += 1
        return (lo, hi, lazy)


# Redo the class parser properly with range support:

class _Parser2:
    def __init__(self, pattern):
        self.s = pattern
        self.pos = 0
        self.n = len(pattern)
        self.num_groups = 0

    def parse(self):
        node = self._parse_alt()
        if self.pos != self.n:
            raise ValueError(f"Unexpected character at position {self.pos}")
        return node

    def _parse_alt(self):
        branches = [self._parse_seq()]
        while self.pos < self.n and self.s[self.pos] == '|':
            self.pos += 1
            branches.append(self._parse_seq())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _parse_seq(self):
        items = []
        while self.pos < self.n and self.s[self.pos] != '|':
            items.append(self._parse_item())
        if not items:
            return _Seq([])
        if len(items) == 1:
            return items[0]
        return _Seq(items)

    def _parse_item(self):
        atom = self._parse_atom()
        if self.pos < self.n and self.s[self.pos] in '*+?{':
            if isinstance(atom, (_AnchorStart, _AnchorEnd)):
                raise ValueError("Cannot quantify anchor")
            lo, hi, lazy = self._parse_quantifier()
            return _Quantified(atom, lo, hi, lazy)
        return atom

    def _parse_atom(self):
        ch = self.s[self.pos]
        if ch in '*+?{':
            raise ValueError(f"Nothing to repeat at position {self.pos}")
        if ch == '(':
            return self._parse_group()
        if ch == '[':
            return self._parse_class()
        if ch == '.':
            self.pos += 1
            return _Dot()
        if ch == '^':
            self.pos += 1
            return _AnchorStart()
        if ch == '$':
            self.pos += 1
            return _AnchorEnd()
        if ch == '\\':
            return self._parse_escape_outside()
        if ch == ')':
            raise ValueError(f"Unmatched ) at position {self.pos}")
        self.pos += 1
        return _Literal(ch)

    def _parse_group(self):
        self.pos += 1  # skip (
        if self.pos < self.n and self.s[self.pos] == '?':
            self.pos += 1
            if self.pos < self.n and self.s[self.pos] == ':':
                self.pos += 1
                body = self._parse_alt()
                if self.pos >= self.n or self.s[self.pos] != ')':
                    raise ValueError("Unclosed (?:")
                self.pos += 1
                return _NonCapGroup(body)
            else:
                raise ValueError(f"Invalid group syntax at position {self.pos - 2}")
        self.num_groups += 1
        idx = self.num_groups
        body = self._parse_alt()
        if self.pos >= self.n or self.s[self.pos] != ')':
            raise ValueError("Unclosed (")
        self.pos += 1
        return _Group(idx, body)

    def _parse_escape_outside(self):
        self.pos += 1  # skip \
        if self.pos >= self.n:
            raise ValueError("Trailing backslash in pattern")
        ch = self.s[self.pos]
        if ch in 'dDwWsS':
            self.pos += 1
            return _ClassEscape(ch)
        if ch == 'n':
            self.pos += 1
            return _Literal('\n')
        if ch == 't':
            self.pos += 1
            return _Literal('\t')
        if not (ch.isalpha() or ch.isdigit()):
            self.pos += 1
            return _Literal(ch)
        raise ValueError(f"Invalid escape \\{ch}")

    def _parse_class_item(self):
        """Parse a single item in a character class.
        Returns (value, is_escape) where value is a char or escape code.
        is_escape is True if it's a class escape (\\d etc)."""
        ch = self.s[self.pos]
        if ch == '\\':
            self.pos += 1
            if self.pos >= self.n:
                raise ValueError("Trailing backslash in class")
            ech = self.s[self.pos]
            if ech in 'dDwWsS':
                self.pos += 1
                return (ech, True)
            elif ech == 'n':
                self.pos += 1
                return ('\n', False)
            elif ech == 't':
                self.pos += 1
                return ('\t', False)
            elif not (ech.isalpha() or ech.isdigit()):
                self.pos += 1
                return (ech, False)
            else:
                raise ValueError(f"Invalid escape \\{ech} in class")
        else:
            self.pos += 1
            return (ch, False)

    def _parse_class(self):
        self.pos += 1  # skip [
        negated = False
        if self.pos < self.n and self.s[self.pos] == '^':
            negated = True
            self.pos += 1

        char_set = set()
        first = True
        while True:
            if self.pos >= self.n:
                raise ValueError("Unclosed [")
            ch = self.s[self.pos]
            if ch == ']' and not first:
                self.pos += 1
                break

            # Parse one item
            val, is_esc = self._parse_class_item()

            # Check for range
            if not is_esc and self.pos < self.n and self.s[self.pos] == '-' and \
               self.pos + 1 < self.n and self.s[self.pos + 1] != ']':
                # It's a range: val - end_val
                self.pos += 1  # skip -
                end_val, end_is_esc = self._parse_class_item()
                if end_is_esc:
                    raise ValueError("Cannot use class escape as range end")
                if val > end_val:
                    raise ValueError(f"Invalid range {val!r}-{end_val!r}")
                for c in range(ord(val), ord(end_val) + 1):
                    char_set.add(chr(c))
            elif is_esc:
                char_set |= _escape_set(val)
            else:
                char_set.add(val)

            first = False

        return _CharClass(char_set, negated)

    def _parse_quantifier(self):
        ch = self.s[self.pos]
        if ch == '*':
            self.pos += 1
            lo, hi = 0, None
        elif ch == '+':
            self.pos += 1
            lo, hi = 1, None
        elif ch == '?':
            self.pos += 1
            lo, hi = 0, 1
        elif ch == '{':
            self.pos += 1
            start = self.pos
            while self.pos < self.n and self.s[self.pos].isdigit():
                self.pos += 1
            m_str = self.s[start:self.pos]
            if not m_str:
                raise ValueError("Invalid {")
            m = int(m_str)
            if self.pos < self.n and self.s[self.pos] == ',':
                self.pos += 1
                start = self.pos
                while self.pos < self.n and self.s[self.pos].isdigit():
                    self.pos += 1
                n_str = self.s[start:self.pos]
                if n_str:
                    n_val = int(n_str)
                    if m > n_val:
                        raise ValueError(f"m > n in {{{m},{n_val}}}")
                    lo, hi = m, n_val
                else:
                    lo, hi = m, None
            elif self.pos < self.n and self.s[self.pos] == '}':
                self.pos += 1
                lo, hi = m, m
            else:
                raise ValueError("Invalid {")
        else:
            raise ValueError(f"Invalid quantifier")

        lazy = False
        if self.pos < self.n and self.s[self.pos] == '?':
            lazy = True
            self.pos += 1
        return (lo, hi, lazy)


# ─── State ───────────────────────────────────────────────────────────────────

class _State:
    __slots__ = ('s', 'captures')
    def __init__(self, s, num_groups):
        self.s = s
        self.captures = [None] * (num_groups + 1)

    def snapshot(self):
        return self.captures.copy()

    def restore(self, snap):
        self.captures = snap


# ─── Matcher ─────────────────────────────────────────────────────────────────

def _match(node, pos, state, cont):
    """Try to match node at pos. Call cont(new_pos) for each successful match
    in priority order. If cont returns True, return True. Otherwise try next.
    If no match, return False."""
    t = type(node)

    if t is _Literal:
        if pos < len(state.s) and state.s[pos] == node.ch:
            return cont(pos + 1)
        return False

    if t is _Dot:
        if pos < len(state.s) and state.s[pos] != '\n':
            return cont(pos + 1)
        return False

    if t is _CharClass:
        if pos < len(state.s):
            c = state.s[pos]
            if node.negated:
                if c not in node.char_set:
                    return cont(pos + 1)
            else:
                if c in node.char_set:
                    return cont(pos + 1)
        return False

    if t is _ClassEscape:
        if pos < len(state.s):
            if _escape_matches(node.code, state.s[pos]):
                return cont(pos + 1)
        return False

    if t is _AnchorStart:
        if pos == 0:
            return cont(pos)
        return False

    if t is _AnchorEnd:
        s = state.s
        ln = len(s)
        if pos == ln:
            return cont(pos)
        if pos == ln - 1 and ln > 0 and s[pos] == '\n':
            return cont(pos)
        return False

    if t is _Seq:
        return _match_seq(node.items, 0, pos, state, cont)

    if t is _Alt:
        for branch in node.branches:
            save = state.snapshot()
            if _match(branch, pos, state, cont):
                return True
            state.restore(save)
        return False

    if t is _Group:
        save = state.snapshot()
        gstart = pos
        gidx = node.index
        def gcont(p):
            state.captures[gidx] = (gstart, p)
            return cont(p)
        if _match(node.body, pos, state, gcont):
            return True
        state.restore(save)
        return False

    if t is _NonCapGroup:
        return _match(node.body, pos, state, cont)

    if t is _Quantified:
        if node.lazy:
            return _match_lazy_q(node, pos, state, cont)
        else:
            return _match_greedy_q(node, pos, state, cont)

    raise ValueError(f"Unknown node type: {t}")


def _match_seq(items, i, pos, state, cont):
    if i == len(items):
        return cont(pos)
    save = state.snapshot()
    if _match(items[i], pos, state, lambda p: _match_seq(items, i + 1, p, state, cont)):
        return True
    state.restore(save)
    return False


def _match_greedy_q(node, pos, state, cont):
    X = node.atom
    lo = node.lo
    hi = node.hi
    c = 0
    mark = None

    if c < lo:
        # Forced iteration
        return _match(X, pos, state,
                      lambda p: _match_greedy_q_inner(node, p, state, cont, c + 1, mark))
    else:
        # Optional iteration (greedy)
        if (hi is None or c < hi) and pos != mark:
            result = _match(X, pos, state,
                            lambda p: _match_greedy_q_inner(node, p, state, cont, c + 1, pos))
            if result:
                return True
            # Iteration failed (or all its continuations failed), try rest
        return cont(pos)


def _match_greedy_q_inner(node, pos, state, cont, c, mark):
    X = node.atom
    lo = node.lo
    hi = node.hi

    if c < lo:
        return _match(X, pos, state,
                      lambda p: _match_greedy_q_inner(node, p, state, cont, c + 1, mark))
    else:
        if (hi is None or c < hi) and pos != mark:
            result = _match(X, pos, state,
                            lambda p: _match_greedy_q_inner(node, p, state, cont, c + 1, pos))
            if result:
                return True
        return cont(pos)


def _match_lazy_q(node, pos, state, cont):
    X = node.atom
    lo = node.lo
    hi = node.hi
    c = 0
    mark = None

    if c < lo:
        return _match(X, pos, state,
                      lambda p: _match_lazy_q_inner(node, p, state, cont, c + 1, mark))
    else:
        # Lazy: try rest first
        if cont(pos):
            return True
        # Rest failed, try one more iteration
        if (hi is not None and c >= hi) or pos == mark:
            return False
        return _match(X, pos, state,
                      lambda p: _match_lazy_q_inner(node, p, state, cont, c + 1, pos))


def _match_lazy_q_inner(node, pos, state, cont, c, mark):
    X = node.atom
    lo = node.lo
    hi = node.hi

    if c < lo:
        return _match(X, pos, state,
                      lambda p: _match_lazy_q_inner(node, p, state, cont, c + 1, mark))
    else:
        if cont(pos):
            return True
        if (hi is not None and c >= hi) or pos == mark:
            return False
        return _match(X, pos, state,
                      lambda p: _match_lazy_q_inner(node, p, state, cont, c + 1, pos))


# ─── Public API ──────────────────────────────────────────────────────────────

class Match:
    __slots__ = ('_s', '_captures', '_start', '_num_groups')

    def __init__(self, s, captures, start, num_groups):
        self._s = s
        self._captures = captures
        self._start = start
        self._num_groups = num_groups

    def _check(self, n):
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError(f"Invalid group number: {n!r}")
        if n < 0 or n > self._num_groups:
            raise IndexError(f"Invalid group number: {n}")

    def span(self, n=0):
        self._check(n)
        if n == 0:
            return (self._start, self._captures[0][1])
        c = self._captures[n]
        if c is None:
            return (-1, -1)
        return c

    def start(self, n=0):
        self._check(n)
        if n == 0:
            return self._start
        c = self._captures[n]
        if c is None:
            return -1
        return c[0]

    def end(self, n=0):
        self._check(n)
        if n == 0:
            return self._captures[0][1]
        c = self._captures[n]
        if c is None:
            return -1
        return c[1]

    def group(self, n=0):
        self._check(n)
        if n == 0:
            return self._s[self._start:self._captures[0][1]]
        c = self._captures[n]
        if c is None:
            return None
        return self._s[c[0]:c[1]]

    def groups(self):
        result = []
        for i in range(1, self._num_groups + 1):
            c = self._captures[i]
            if c is None:
                result.append(None)
            else:
                result.append(self._s[c[0]:c[1]])
        return tuple(result)


class Pattern:
    __slots__ = ('_ast', '_num_groups')

    def __init__(self, ast, num_groups):
        self._ast = ast
        self._num_groups = num_groups

    def fullmatch(self, s):
        state = _State(s, self._num_groups)
        state.captures[0] = (0, 0)  # will be updated
        target = len(s)
        result = [False]

        def cont(end_pos):
            if end_pos == target:
                state.captures[0] = (0, end_pos)
                result[0] = True
                return True
            return False

        if _match(self._ast, 0, state, cont):
            return Match(s, state.captures, 0, self._num_groups)
        return None

    def search(self, s):
        ln = len(s)
        for start in range(ln + 1):
            state = _State(s, self._num_groups)
            result = [False]

            def cont(end_pos, st=state, stt=start):
                st.captures[0] = (stt, end_pos)
                result[0] = True
                return True

            if _match(self._ast, start, state, cont):
                return Match(s, state.captures, start, self._num_groups)
        return None


def compile(pattern: str) -> Pattern:
    p = _Parser2(pattern)
    ast = p.parse()
    return Pattern(ast, p.num_groups)
