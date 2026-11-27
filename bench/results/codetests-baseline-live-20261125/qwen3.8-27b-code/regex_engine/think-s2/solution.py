import sys
sys.setrecursionlimit(200000)

# ---------- AST Node Classes ----------

class _Node:
    pass

class Literal(_Node):
    __slots__ = ('ch',)
    def __init__(self, ch):
        self.ch = ch

class Dot(_Node):
    __slots__ = ()

class CharClass(_Node):
    __slots__ = ('negated', 'chars')
    def __init__(self, negated, chars):
        self.negated = negated
        self.chars = chars  # frozenset of chars

class AnchorStart(_Node):
    __slots__ = ()

class AnchorEnd(_Node):
    __slots__ = ()

class FullMatchEnd(_Node):
    __slots__ = ()

class Group(_Node):
    __slots__ = ('capturing', 'body', 'group_id')
    def __init__(self, capturing, body, group_id=None):
        self.capturing = capturing
        self.body = body
        self.group_id = group_id

class Seq(_Node):
    __slots__ = ('items',)
    def __init__(self, items):
        self.items = items

class Alt(_Node):
    __slots__ = ('branches',)
    def __init__(self, branches):
        self.branches = branches

class Quantifier(_Node):
    __slots__ = ('atom', 'lo', 'hi', 'lazy')
    def __init__(self, atom, lo, hi, lazy):
        self.atom = atom
        self.lo = lo
        self.hi = hi  # None for unbounded
        self.lazy = lazy

# ---------- Precomputed class char sets ----------

_D = frozenset('0123456789')
_W = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_')
_S = frozenset(' \t\n\r\f\v')
_ALL = frozenset(chr(i) for i in range(128))  # ASCII

def _class_chars(c):
    if c == 'd': return _D
    if c == 'D': return _ALL - _D
    if c == 'w': return _W
    if c == 'W': return _ALL - _W
    if c == 's': return _S
    if c == 'S': return _ALL - _S

# ---------- Parser ----------

class _Parser:
    def __init__(self, pattern):
        self.pat = pattern
        self.n = len(pattern)
        self.pos = 0
        self.group_count = 0

    def _err(self, msg):
        raise ValueError(f"{msg} (at position {self.pos})")

    def _peek(self, offset=0):
        p = self.pos + offset
        if p < self.n:
            return self.pat[p]
        return None

    def _advance(self):
        ch = self.pat[self.pos]
        self.pos += 1
        return ch

    def parse(self):
        node = self._parse_alternation()
        if self.pos != self.n:
            self._err(f"Unexpected character '{self.pat[self.pos]}'")
        return node, self.group_count

    def _parse_alternation(self):
        branches = [self._parse_sequence()]
        while self._peek() == '|':
            self._advance()
            branches.append(self._parse_sequence())
        if len(branches) == 1:
            return branches[0]
        return Alt(branches)

    def _parse_sequence(self):
        items = []
        while self.pos < self.n:
            ch = self._peek()
            if ch == '|' or ch == ')':
                break
            if ch in '*+?{':
                self._err("Quantifier with nothing to repeat")
            item = self._parse_quantified_atom()
            items.append(item)
        if not items:
            return Seq([])
        if len(items) == 1:
            return items[0]
        return Seq(items)

    def _parse_quantified_atom(self):
        atom = self._parse_atom()
        ch = self._peek()
        if ch is None:
            return atom
        if ch in '*+?':
            self._advance()
            lazy = False
            if self._peek() == '?':
                lazy = True
                self._advance()
            lo, hi = {'*': (0, None), '+': (1, None), '?': (0, 1)}[ch]
            return Quantifier(atom, lo, hi, lazy)
        elif ch == '{':
            save = self.pos
            self._advance()  # consume {
            # Parse m
            ms = self.pos
            while self.pos < self.n and self.pat[self.pos].isdigit():
                self.pos += 1
            me = self.pos
            m_str = self.pat[ms:me]
            if not m_str:
                self.pos = save
                self._err("Invalid quantifier: missing digits")
            m = int(m_str)
            ch2 = self._peek()
            if ch2 == '}':
                self._advance()
                lazy = False
                if self._peek() == '?':
                    lazy = True
                    self._advance()
                return Quantifier(atom, m, m, lazy)
            elif ch2 == ',':
                self._advance()
                ns = self.pos
                while self.pos < self.n and self.pat[self.pos].isdigit():
                    self.pos += 1
                ne = self.pos
                n_str = self.pat[ns:ne]
                ch3 = self._peek()
                if ch3 == '}':
                    self._advance()
                    lazy = False
                    if self._peek() == '?':
                        lazy = True
                        self._advance()
                    if n_str:
                        n = int(n_str)
                        if m > n:
                            self._err(f"Invalid quantifier: {{m,n}} with m > n")
                        return Quantifier(atom, m, n, lazy)
                    else:
                        return Quantifier(atom, m, None, lazy)
                else:
                    self.pos = save
                    self._err("Invalid quantifier: unclosed brace")
            else:
                self.pos = save
                self._err("Invalid quantifier")
        return atom

    def _parse_atom(self):
        ch = self._peek()
        if ch is None:
            self._err("Unexpected end of pattern")
        if ch == '.':
            self._advance()
            return Dot()
        elif ch == '^':
            self._advance()
            return AnchorStart()
        elif ch == '$':
            self._advance()
            return AnchorEnd()
        elif ch == '\\':
            self._advance()
            return self._parse_escape()
        elif ch == '[':
            self._advance()
            return self._parse_char_class()
        elif ch == '(':
            self._advance()
            return self._parse_group()
        else:
            self._advance()
            return Literal(ch)

    def _parse_escape(self):
        ch = self._peek()
        if ch is None:
            self._err("Backslash at end of pattern")
        self._advance()
        if ch in 'dDwWsS':
            return CharClass(ch in 'DWS', _class_chars(ch))
        elif ch == 'n':
            return Literal('\n')
        elif ch == 't':
            return Literal('\t')
        elif ch.isalpha() or ch.isdigit():
            self._err(f"Invalid escape: \\{ch}")
        else:
            return Literal(ch)

    def _parse_char_class(self):
        negated = False
        if self._peek() == '^':
            negated = True
            self._advance()
        chars = set()
        first = True
        while True:
            ch = self._peek()
            if ch is None:
                self._err("Unclosed character class")
            if ch == ']':
                if first:
                    chars.add(']')
                    self._advance()
                    first = False
                    continue
                else:
                    self._advance()
                    break
            # Parse an item
            if ch == '\\':
                self._advance()
                ch2 = self._peek()
                if ch2 is None:
                    self._err("Backslash at end in character class")
                self._advance()
                if ch2 in 'dDwWsS':
                    # Class escape
                    if self._peek() == '-' and self._peek(1) != ']':
                        self._err("Class escape cannot be used in a range")
                    chars.update(_class_chars(ch2))
                elif ch2 == 'n':
                    item_char = '\n'
                    self._class_range_or_add(chars, item_char)
                elif ch2 == 't':
                    item_char = '\t'
                    self._class_range_or_add(chars, item_char)
                elif ch2.isalpha() or ch2.isdigit():
                    self._err(f"Invalid escape in class: \\{ch2}")
                else:
                    item_char = ch2
                    self._class_range_or_add(chars, item_char)
            else:
                self._advance()
                item_char = ch
                self._class_range_or_add(chars, item_char)
            first = False
        return CharClass(negated, frozenset(chars))

    def _class_range_or_add(self, chars, item_char):
        if self._peek() == '-' and self._peek(1) != ']':
            self._advance()  # consume -
            end_char = self._class_single_char()
            if ord(item_char) > ord(end_char):
                self._err("Invalid range in character class")
            for c in range(ord(item_char), ord(end_char) + 1):
                chars.add(chr(c))
        else:
            chars.add(item_char)

    def _class_single_char(self):
        ch = self._peek()
        if ch is None:
            self._err("Unexpected end in class range")
        if ch == '\\':
            self._advance()
            ch2 = self._peek()
            if ch2 is None:
                self._err("Backslash at end in class range")
            self._advance()
            if ch2 == 'n':
                return '\n'
            elif ch2 == 't':
                return '\t'
            elif ch2 in 'dDwWsS':
                self._err("Class escape as range endpoint")
            elif ch2.isalpha() or ch2.isdigit():
                self._err(f"Invalid escape in class range: \\{ch2}")
            else:
                return ch2
        else:
            self._advance()
            return ch

    def _parse_group(self):
        # Already consumed '('
        if self._peek() == '?' and self._peek(1) == ':':
            self._advance()  # ?
            self._advance()  # :
            body = self._parse_alternation()
            if self._peek() != ')':
                self._err("Unclosed non-capturing group")
            self._advance()  # )
            return Group(False, body)
        elif self._peek() == '?':
            self._err("Invalid group syntax")
        else:
            self.group_count += 1
            gid = self.group_count
            body = self._parse_alternation()
            if self._peek() != ')':
                self._err("Unclosed group")
            self._advance()  # )
            return Group(True, body, gid)

# ---------- Matcher (generator-based backtracking) ----------

def _match(node, pos, s, captures):
    """Generator yielding end positions in priority order."""
    if isinstance(node, Seq):
        yield from _match_seq(node.items, 0, pos, s, captures)
    elif isinstance(node, Alt):
        for branch in node.branches:
            save = captures.copy()
            found = False
            for result in _match(branch, pos, s, captures):
                yield result
                found = True
                break
            if found:
                return
            captures[:] = save
    elif isinstance(node, Group):
        if node.capturing:
            gid = node.group_id - 1
            start = pos
            for result in _match(node.body, pos, s, captures):
                captures[gid] = (start, result)
                yield result
                return
        else:
            yield from _match(node.body, pos, s, captures)
    elif isinstance(node, Literal):
        if pos < len(s) and s[pos] == node.ch:
            yield pos + 1
    elif isinstance(node, Dot):
        if pos < len(s) and s[pos] != '\n':
            yield pos + 1
    elif isinstance(node, CharClass):
        if pos < len(s):
            c = s[pos]
            if node.negated:
                if c not in node.chars:
                    yield pos + 1
            else:
                if c in node.chars:
                    yield pos + 1
    elif isinstance(node, AnchorStart):
        if pos == 0:
            yield pos
    elif isinstance(node, AnchorEnd):
        if pos == len(s) or (pos == len(s) - 1 and s[pos] == '\n'):
            yield pos
    elif isinstance(node, FullMatchEnd):
        if pos == len(s):
            yield pos
    else:
        raise ValueError(f"Unknown node type: {type(node)}")

def _match_seq(items, idx, pos, s, captures):
    if idx == len(items):
        yield pos
        return
    node = items[idx]
    if isinstance(node, Quantifier):
        yield from _match_quantifier(node, items, idx + 1, pos, s, captures)
    else:
        for result in _match(node, pos, s, captures):
            for rest in _match_seq(items, idx + 1, result, s, captures):
                yield rest
                return
            # rest failed, try next result from _match(node, ...)

def _match_quantifier(node, items, next_idx, pos, s, captures):
    atom = node.atom
    lo = node.lo
    hi = node.hi
    lazy = node.lazy

    # Forced iterations
    c = 0
    mark = None
    while c < lo:
        save = captures.copy()
        found = False
        for iter_result in _match(atom, pos, s, captures):
            pos = iter_result
            c += 1
            found = True
            break
        if not found:
            captures[:] = save
            return

    if lazy:
        yield from _qf_lazy(atom, hi, c, mark, pos, items, next_idx, s, captures)
    else:
        yield from _qf_greedy(atom, hi, c, mark, pos, items, next_idx, s, captures)

def _qf_greedy(atom, hi, c, mark, pos, items, next_idx, s, captures):
    if (hi is None or c < hi) and pos != mark:
        save = captures.copy()
        new_mark = pos
        for iter_result in _match(atom, pos, s, captures):
            yield from _qf_greedy(atom, hi, c + 1, new_mark, iter_result, items, next_idx, s, captures)
        captures[:] = save
    yield from _match_seq(items, next_idx, pos, s, captures)

def _qf_lazy(atom, hi, c, mark, pos, items, next_idx, s, captures):
    # Try rest first
    for result in _match_seq(items, next_idx, pos, s, captures):
        yield result
        return
    # Rest failed, try one more iteration
    if (hi is not None and c >= hi) or pos == mark:
        return
    save = captures.copy()
    new_mark = pos
    for iter_result in _match(atom, pos, s, captures):
        yield from _qf_lazy(atom, hi, c + 1, new_mark, iter_result, items, next_idx, s, captures)
    captures[:] = save

# ---------- Public API ----------

class Match:
    __slots__ = ('_start', '_end', '_captures', '_num_groups')

    def __init__(self, start, end, captures, num_groups):
        self._start = start
        self._end = end
        self._captures = captures
        self._num_groups = num_groups

    def _check(self, n):
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError("group index must be an integer")
        if n < 0 or n > self._num_groups:
            raise IndexError("group index out of range")

    def span(self, n=0):
        self._check(n)
        if n == 0:
            return (self._start, self._end)
        cap = self._captures[n - 1]
        if cap is None:
            return (-1, -1)
        return cap

    def start(self, n=0):
        self._check(n)
        if n == 0:
            return self._start
        cap = self._captures[n - 1]
        if cap is None:
            return -1
        return cap[0]

    def end(self, n=0):
        self._check(n)
        if n == 0:
            return self._end
        cap = self._captures[n - 1]
        if cap is None:
            return -1
        return cap[1]

    def group(self, n=0):
        self._check(n)
        if n == 0:
            return self._s[self._start:self._end] if hasattr(self, '_s') else None
        cap = self._captures[n - 1]
        if cap is None:
            return None
        return self._s[cap[0]:cap[1]]

    def groups(self):
        return tuple(
            None if c is None else self._s[c[0]:c[1]]
            for c in self._captures
        )

    def __repr__(self):
        return f"<Match object (span=({self._start}, {self._end}))>"


class Pattern:
    def __init__(self, ast, num_groups):
        self._ast = ast
        self._num_groups = num_groups

    def fullmatch(self, s):
        captures = [None] * self._num_groups
        full_ast = Seq([self._ast, FullMatchEnd()])
        for result in _match(full_ast, 0, s, captures):
            m = Match(0, result, captures, self._num_groups)
            m._s = s
            return m
        return None

    def search(self, s):
        for start in range(len(s) + 1):
            captures = [None] * self._num_groups
            for result in _match(self._ast, start, s, captures):
                m = Match(start, result, captures, self._num_groups)
                m._s = s
                return m
        return None


def compile(pattern):
    if not isinstance(pattern, str):
        raise ValueError("pattern must be a string")
    parser = _Parser(pattern)
    ast, num_groups = parser.parse()
    return Pattern(ast, num_groups)
