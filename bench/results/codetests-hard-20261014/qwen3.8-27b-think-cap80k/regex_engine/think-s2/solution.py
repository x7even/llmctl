import sys
sys.setrecursionlimit(100000)

# ─── AST Nodes ───────────────────────────────────────────────────────────────

class _Node:
    _id_counter = 0
    def __init__(self):
        self.id = _Node._id_counter
        _Node._id_counter += 1

class _Literal(_Node):
    __slots__ = ('id', 'char')
    def __init__(self, char):
        super().__init__()
        self.char = char

class _Dot(_Node):
    __slots__ = ('id',)
    def __init__(self):
        super().__init__()

class _CharClass(_Node):
    __slots__ = ('id', 'chars', 'negated')
    def __init__(self, chars, negated):
        super().__init__()
        self.chars = chars
        self.negated = negated

class _Anchor(_Node):
    __slots__ = ('id', 'kind')
    def __init__(self, kind):
        super().__init__()
        self.kind = kind

class _Group(_Node):
    __slots__ = ('id', 'index', 'children')
    def __init__(self, index, children):
        super().__init__()
        self.index = index
        self.children = children

class _Alternation(_Node):
    __slots__ = ('id', 'branches')
    def __init__(self, branches):
        super().__init__()
        self.branches = branches

class _Quantifier(_Node):
    __slots__ = ('id', 'child', 'lo', 'hi', 'lazy')
    def __init__(self, child, lo, hi, lazy):
        super().__init__()
        self.child = child
        self.lo = lo
        self.hi = hi
        self.lazy = lazy

# ─── Parser ──────────────────────────────────────────────────────────────────

_D = frozenset('0123456789')
_W = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_S = frozenset(' \t\n\r\f\v')

def _parse(pattern):
    pos = [0]
    num_groups = [0]
    n = len(pattern)

    def parse_alternation():
        branches = [parse_sequence()]
        while pos[0] < n and pattern[pos[0]] == '|':
            pos[0] += 1
            branches.append(parse_sequence())
        if len(branches) == 1:
            return branches[0]
        return [_Alternation(branches)]

    def parse_sequence():
        items = []
        while pos[0] < n and pattern[pos[0]] not in '|)':
            item = parse_quantified()
            if item is not None:
                items.append(item)
        return items

    def parse_quantified():
        atom = parse_atom()
        if atom is None:
            return None
        if pos[0] < n and pattern[pos[0]] in '*+?{':
            q = parse_quantifier()
            if q is not None:
                return _Quantifier(atom, q[0], q[1], q[2])
        return atom

    def parse_atom():
        if pos[0] >= n:
            return None
        c = pattern[pos[0]]
        if c == '(':
            return parse_group()
        elif c == '.':
            pos[0] += 1
            return _Dot()
        elif c == '^':
            pos[0] += 1
            return _Anchor('^')
        elif c == '$':
            pos[0] += 1
            return _Anchor('$')
        elif c == '\\':
            return parse_escape()
        elif c == '[':
            return parse_class()
        elif c in '*+?{':
            raise ValueError(f"nothing to repeat at position {pos[0]}")
        else:
            pos[0] += 1
            return _Literal(c)

    def parse_group():
        pos[0] += 1  # consume '('
        if pos[0] < n and pattern[pos[0]] == '?':
            if pos[0] + 1 < n and pattern[pos[0] + 1] == ':':
                pos[0] += 2
                children = parse_alternation()
                if pos[0] >= n or pattern[pos[0]] != ')':
                    raise ValueError("unbalanced parenthesis")
                pos[0] += 1
                return _Group(0, children)
            else:
                raise ValueError(f"invalid group syntax at position {pos[0]}")
        else:
            num_groups[0] += 1
            idx = num_groups[0]
            children = parse_alternation()
            if pos[0] >= n or pattern[pos[0]] != ')':
                raise ValueError("unbalanced parenthesis")
            pos[0] += 1
            return _Group(idx, children)

    def parse_escape():
        pos[0] += 1  # consume '\'
        if pos[0] >= n:
            raise ValueError("trailing backslash")
        c = pattern[pos[0]]
        if c == 'd':
            pos[0] += 1
            return _CharClass(_D, False)
        elif c == 'D':
            pos[0] += 1
            return _CharClass(_D, True)
        elif c == 'w':
            pos[0] += 1
            return _CharClass(_W, False)
        elif c == 'W':
            pos[0] += 1
            return _CharClass(_W, True)
        elif c == 's':
            pos[0] += 1
            return _CharClass(_S, False)
        elif c == 'S':
            pos[0] += 1
            return _CharClass(_S, True)
        elif c == 'n':
            pos[0] += 1
            return _Literal('\n')
        elif c == 't':
            pos[0] += 1
            return _Literal('\t')
        elif c.isalpha() or c.isdigit():
            raise ValueError(f"invalid escape \\{c}")
        else:
            pos[0] += 1
            return _Literal(c)

    def parse_class():
        pos[0] += 1  # consume '['
        negated = False
        if pos[0] < n and pattern[pos[0]] == '^':
            negated = True
            pos[0] += 1
        chars = set()
        if pos[0] < n and pattern[pos[0]] == ']':
            chars.add(']')
            pos[0] += 1
        while pos[0] < n and pattern[pos[0]] != ']':
            item = parse_class_item()
            if (pos[0] + 1 < n and pattern[pos[0] + 1] == '-'
                    and pos[0] + 2 < n and pattern[pos[0] + 2] != ']'):
                if item[0] == 'escape':
                    raise ValueError("range with class escape")
                pos[0] += 1  # consume '-'
                end_item = parse_class_item()
                if end_item[0] == 'escape':
                    raise ValueError("range with class escape")
                if item[1] > end_item[1]:
                    raise ValueError(f"invalid character range")
                for code in range(ord(item[1]), ord(end_item[1]) + 1):
                    chars.add(chr(code))
            else:
                if item[0] == 'escape':
                    chars.update(item[1])
                else:
                    chars.add(item[1])
        if pos[0] >= n:
            raise ValueError("unterminated character class")
        pos[0] += 1  # consume ']'
        return _CharClass(chars, negated)

    def parse_class_item():
        if pos[0] >= n:
            raise ValueError("unterminated character class")
        c = pattern[pos[0]]
       