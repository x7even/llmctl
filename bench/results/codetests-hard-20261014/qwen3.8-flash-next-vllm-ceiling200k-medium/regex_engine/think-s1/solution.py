import sys
sys.setrecursionlimit(100000)

_next_id = 0

def _new_id():
    global _next_id
    _next_id += 1
    return _new_id


class _Lit:
    __slots__ = ('ch', 'id')
    def __init__(self, ch):
        self.ch = ch
        self.id = _new_id()

class _Dot:
    __slots__ = ('id',)
    def __init__(self):
        self.id = _new_id()

class _Class:
    __slots__ = ('negated', 'items', 'id')
    def __init__(self, negated, items):
        self.negated = negated
        self.items = items
        self.id = _new_id()

class _Group:
    __slots__ = ('index', 'child', 'id')
    def __init__(self, index, child):
        self.index = index
        self.child = child
        self.id = _new_id()

class _Alt:
    __slots__ = ('branches', 'id')
    def __init__(self, branches):
        self.branches = branches
        self.id = _new_id()

class _Seq:
    __slots__ = ('children', 'id')
    def __init__(self, children):
        self.children = children
        self.id = _new_id()

class _Quant:
    __slots__ = ('child', 'lo', 'hi', 'greedy', 'id')
    def __init__(self, child, lo, hi, greedy):
        self.child = child
        self.lo = lo
        self.hi = hi
        self.greedy = greedy
        self.id = _new_id()

class _Anchor:
    __slots__ = ('kind', 'id')
    def __init__(self, kind):
        self.kind = kind
        self.id = _new_id()

class _Empty:
    __slots__ = ('id',)
    def __init__(self):
        self.id = _new_id()


_DIGITS = frozenset('0123456789')
_WORD_CHARS = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE_CHARS = frozenset(' \t\n\r\f\v')


def _class_match(cls, ch):
    found = False
    for item in cls.items:
        t = item[0]
        if t == 'char':
            if ch == item[1]:
                found = True
                break
        elif t == 'range':
            if item[1] <= ch <= item[2]:
                found = True
                break
        elif t == 'escape':
            esc = item[1]
            if esc == 'd':
                if ch in _DIGITS:
                    found = True
                    break
            elif esc == 'w':
                if ch in _WORD_CHARS:
                    found = True
                    break
            elif esc == 's':
                if ch in _SPACE_CHARS:
                    found = True
                    break
    if cls.negated:
        return not found
    return found


class _Parser:
    def __init__(self, pattern):
        self.pattern = pattern
        self.pos = 0
        self.num_groups = 0

    def parse(self):
        node = self._parse_alternation()
        if self.pos < len(self.pattern):
            raise ValueError("unexpected character")
        return node

    def _peek(self):
        if self.pos < len(self.pattern):
            return self.pattern[self.pos]
        return None

    def _advance(self):
        ch = self.pattern[self.pos]
        self.pos += 1
        return ch

    def _parse_alternation(self):
        branches = [self._parse_sequence()]
        while self._peek() == '|':
            self._advance()
            branches.append(self._parse_sequence())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _parse_sequence(self):
        items = []
        while True:
            ch = self._peek()
            if ch is None or ch == '|' or ch == ')':
                break
            items.append(self._parse_quantified())
        if len(items) == 0:
            return _Empty()
        if len(items) == 1:
            return items[0]
        return _Seq(items)

    def _parse_quantified(self):
        atom = self._parse_atom()
        ch = self._peek()
        if ch in ('*', '+', '?', '{'):
            return self._parse_quantifier(atom)
        return atom

    def _parse_quantifier(self, atom):
        ch = self._peek()
        if ch == '*':
            self._advance()
            lo, hi = 0, None
        elif ch == '+':
            self._advance()
            lo, hi = 1, None
        elif ch == '?':
            self._advance()
            lo, hi = 0, 1
        elif ch == '{':
            lo, hi = self._parse_brace()
        else:
            raise ValueError("invalid quantifier")

        greedy = True
        if self._peek() == '?':
            self._advance()
            greedy = False

        nxt = self._peek()
        if nxt in ('*', '+', '?', '{'):
            raise ValueError("multiple quantifiers")

        return _Quant(atom, lo, hi, greedy)

    def _parse_brace(self):
        start = self.pos
        self._advance()  # consume '{'

        m_start = self.pos
        while self.pos < len(self.pattern) and self.pattern[self.pos] in _DIGITS:
            self.pos += 1
        if self.pos == m_start:
            raise ValueError("invalid quantifier brace")
        m = int(self.pattern[m_start:self.pos])

        if self.pos < len(self.pattern) and self.pattern[self.pos] == ',':
            self._advance()
            n_start = self.pos
            while self.pos < len(self.pattern) and self.pattern[self.pos] in _DIGITS:
                self.pos += 1
            if n_start == self.pos:
                n = None
            else:
                n = int(self.pattern[n_start:self.pos])
        else:
            n = m

        if self.pos >= len(self.pattern) or self.pattern[self.pos] != '}':
            raise ValueError("invalid quantifier brace")
        self._advance()  # consume '}'

        if n is not None and m > n:
            raise ValueError("m > n in quantifier")

        return m, n

    def _parse_atom(self):
        ch = self._peek()
        if ch is None:
            raise ValueError("unexpected end of pattern")
        if ch == '(':
            return self._parse_group()
        elif ch == '[':
            return self._parse_class()
        elif ch == '.':
            self._advance()
            return _Dot()
        elif ch == '^':
            self._advance()
            return _Anchor('^')
        elif ch == '$':
            self._advance()
            return _Anchor('$')
        elif ch == '\\':
            return self._parse_escape()
        elif ch in ('*', '+', '?', '{'):
            raise ValueError("quantifier with nothing to repeat")
        elif ch == ')':
            raise ValueError("unmatched ')'")
        else:
            self._advance()
            return _Lit(ch)

    def _parse_group(self):
        self._advance()  # consume '('
        if self._peek() == '?':
            if self.pos + 1 < len(self.pattern) and self.pattern[self.pos + 1] == ':':
                self._advance()  # consume '?'
                self._advance()  # consume ':'
                child = self._parse_alternation()
                if self._peek() != ')':
                    raise ValueError("unmatched '('")
                self._advance()  # consume ')'
                return _Group(0, child)
            else:
                raise ValueError("unsupported group syntax")
        else:
            self.num_groups += 1
            index = self.num_groups
            child = self._parse_alternation()
            if self._peek() != ')':
                raise ValueError("unmatched '('")
            self._advance()  # consume ')'
            return _Group(index, child)

    def _parse_escape(self):
        self._advance()  # consume '\'
        ch = self._peek()
        if ch is None:
            raise ValueError("backslash at end of pattern")
        self._advance()

        if ch == 'd':
            return _Class(False, [('escape', 'd')])
        elif ch == 'D':
            return _Class(True, [('escape', 'd')])
        elif ch == 'w':
            return _Class(False, [('escape', 'w')])
        elif ch == 'W':
            return _Class(True, [('escape', 'w')])
        elif ch == 's':
            return _Class(False, [('escape', 's')])
        elif ch == 'S':
            return _Class(True, [('escape', 's')])
        elif ch == 'n':
            return _Lit('\n')
        elif ch == 't':
            return _Lit('\t')
        elif ch.isalpha() or ch.isdigit():
            raise ValueError("invalid escape")
        else:
            return _Lit(ch)

    def _parse_class(self):
        self._advance()  # consume '['
        negated = False
        if self._peek() == '^':
            negated = True
            self._advance()

        items = []

        # Leading ']' is literal
        if self._peek() == ']':
            self._advance()
            items.append(('char', ']'))

        while True:
            ch = self._peek()
            if ch is None:
                raise ValueError("unterminated character class")
            if ch == ']':
                self._advance()
                break

            item = self._parse_class_item()

            # Check for range
            if self._peek() == '-' and self.pos + 1 < len(self.pattern) and self.pattern[self.pos + 1] != ']':
                self._advance()  # consume '-'
                end_item = self._parse_class_item()
                if item[0] != 'char' or end_item[0] != 'char':
                    raise ValueError("invalid range in character class")
                if item[1] > end_item[1]:
                    raise ValueError("range out of order")
                items.append(('range', item[1], end_item[1]))
            else:
                items.append(item)

        return _Class(negated, items)

    def _parse_class_item(self):
        ch = self._peek()
        if ch is None:
            raise ValueError("unterminated character class")
        if ch == '\\':
            self._advance()
            ch = self._peek()
            if ch is None:
                raise ValueError("backslash at end of pattern")
            self._advance()
            if ch in 'dDwWsS':
                return ('escape', ch.lower())
            elif ch == 'n':
                return ('char', '\n')
            elif ch == 't':
                return ('char', '\t')
            elif ch.isalpha() or ch.isdigit():
                raise ValueError("invalid escape in class")
            else:
                return ('char', ch)
        else:
            self._advance()
            return ('char', ch)


def _match_node(node, pos, cont, captures, s, failed):
    key = (node.id, pos)
    if key in failed:
        return False
    result = _do_match(node, pos, cont, captures, s, failed)
    if not result:
        failed.add(key)
    return result


def _do_match(node, pos, cont, captures, s, failed):
    if isinstance(node, _Lit):
        if pos < len(s) and s[pos] == node.ch:
            return cont(pos + 1)
        return False

    if isinstance(node, _Dot):
        if pos < len(s) and s[pos] != '\n':
            return cont(pos + 1)
        return False

    if isinstance(node, _Class):
        if pos < len(s) and _class_match(node, s[pos]):
            return cont(pos + 1)
        return False

    if isinstance(node, _Anchor):
        if node.kind == '^':
            if pos == 0:
                return cont(pos)
            return False
        else:
            if pos == len(s) or (pos == len(s) - 1 and s[pos] == '\n'):
                return cont(pos)
            return False

    if isinstance(node, _Empty):
        return cont(pos)

    if isinstance(node, _Group):
        if node.index == 0:
            return _match_node(node.child, pos, cont, captures, s, failed)
        saved = captures[node.index]
        def group_cont(new_pos):
            captures[node.index] = (pos, new_pos)
            r = cont(new_pos)
            if not r:
                captures[node.index] = saved
            return r
        return _match_node(node.child, pos, group_cont, captures, s, failed)

    if isinstance(node, _Seq):
        return _match_seq(node.children, 0, pos, cont, captures, s, failed)

    if isinstance(node, _Alt):
        for branch in node.branches:
            if _match_node(branch, pos, cont, captures, s, failed):
                return True
        return False

    if isinstance(node, _Quant):
        return _match_quant(node, pos, cont, captures, s, failed)

    return False


def _match_seq(children, i, pos, cont, captures, s, failed):
    if i == len(children):
        return cont(pos)
    def next_cont(new_pos):
        return _match_seq(children, i + 1, new_pos, cont, captures, s, failed)
    return _match_node(children[i], pos, next_cont, captures, s, failed)


def _match_quant(node, pos, cont, captures, s, failed):
    def loop(c, mark, cur_pos):
        if c < node.lo:
            def forced_cont(new_pos):
                return loop(c + 1, mark, new_pos)
            return _match_node(node.child, cur_pos, forced_cont, captures, s, failed)
        else:
            if node.greedy:
                if (node.hi is None or c < node.hi) and cur_pos != mark:
                    def greedy_cont(new_pos):
                        return loop(c + 1, cur_pos, new_pos)
                    if _match_node(node.child, cur_pos, greedy_cont, captures, s, failed):
                        return True
                return cont(cur_pos)
            else:
                if cont(cur_pos):
                    return True
                if (node.hi is not None and c >= node.hi) or cur_pos == mark:
                    return False
                def lazy_cont(new_pos):
                    return loop(c + 1, cur_pos, new_pos)
                return _match_node(node.child, cur_pos, lazy_cont, captures, s, failed)
    return loop(0, None, pos)


class Match:
    def __init__(self, s, spans, num_groups):
        self._s = s
        self._spans = spans
        self._num_groups = num_groups

    def span(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._num_groups:
            raise IndexError("no such group")
        return self._spans[n]

    def start(self, n=0):
        return self.span(n)[0]

    def end(self, n=0):
        return self.span(n)[1]

    def group(self, n=0):
        s, e = self.span(n)
        if s == -1:
            return None
        return self._s[s:e]

    def groups(self):
        result = []
        for i in range(1, self._num_groups + 1):
            s, e = self._spans[i]
            if s == -1:
                result.append(None)
            else:
                result.append(self._s[s:e])
        return tuple(result)


class Pattern:
    def __init__(self, node, num_groups):
        self._node = node
        self._num_groups = num_groups

    def fullmatch(self, s):
        captures = [None] * (self._num_groups + 1)
        failed = set()

        def end_cont(pos):
            if pos == len(s):
                captures[0] = (0, pos)
                return True
            return False

        if _match_node(self._node, 0, end_cont, captures, s, failed):
            return Match(s, captures, self._num_groups)
        return None

    def search(self, s):
        captures = [None] * (self._num_groups + 1)
        failed = set()

        for start in range(len(s) + 1):
            for i in range(self._num_groups + 1):
                captures[i] = None

            def end_cont(pos, _start=start):
                captures[0] = (_start, pos)
                return True

            if _match_node(self._node, start, end_cont, captures, s, failed):
                return Match(s, list(captures), self._num_groups)
        return None


def compile(pattern: str) -> Pattern:
    parser = _Parser(pattern)
    node = parser.parse()
    return Pattern(node, parser.num_groups)
