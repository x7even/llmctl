import sys
sys.setrecursionlimit(100000)

# === AST Node Classes ===

class _Node:
    pass

class _Lit(_Node):
    __slots__ = ('ch',)
    def __init__(self, ch):
        self.ch = ch

class _Dot(_Node):
    __slots__ = ()

class _Caret(_Node):
    __slots__ = ()

class _Dollar(_Node):
    __slots__ = ()

class _Class(_Node):
    __slots__ = ('negated', 'items')
    def __init__(self, negated, items):
        self.negated = negated
        self.items = items

class _ClassEsc(_Node):
    __slots__ = ('cls',)
    def __init__(self, cls):
        self.cls = cls

class _Group(_Node):
    __slots__ = ('capturing', 'index', 'body')
    def __init__(self, capturing, index, body):
        self.capturing = capturing
        self.index = index
        self.body = body

class _Alt(_Node):
    __slots__ = ('branches',)
    def __init__(self, branches):
        self.branches = branches

class _Quant(_Node):
    __slots__ = ('atom', 'lo', 'hi', 'lazy')
    def __init__(self, atom, lo, hi, lazy):
        self.atom = atom
        self.lo = lo
        self.hi = hi
        self.lazy = lazy

# === Character matching helpers ===

_DIGITS = frozenset('0123456789')
_WORD = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')

def _class_esc_matches(cls, ch):
    if cls == 'd':
        return ch in _DIGITS
    if cls == 'D':
        return ch not in _DIGITS
    if cls == 'w':
        return ch in _WORD
    if cls == 'W':
        return ch not in _WORD
    if cls == 's':
        return ch in _SPACE
    if cls == 'S':
        return ch not in _SPACE
    return False

def _class_matches(cls_node, ch):
    matched = False
    for item in cls_node.items:
        if item[0] == 'char':
            if ch == item[1]:
                matched = True
                break
        elif item[0] == 'range':
            if item[1] <= ch <= item[2]:
                matched = True
                break
        elif item[0] == 'class':
            if _class_esc_matches(item[1], ch):
                matched = True
                break
    return not matched if cls_node.negated else matched

# === Parser ===

def _parse_pattern(pattern):
    p = pattern
    length = len(p)
    pos = 0
    num_groups = 0

    def parse_pattern():
        nonlocal pos, num_groups
        branches = [parse_branch()]
        while pos < length and p[pos] == '|':
            pos += 1
            branches.append(parse_branch())
        if len(branches) == 1:
            return branches[0]
        else:
            return _Alt(branches)

    def parse_branch():
        nonlocal pos
        elements = []
        while pos < length and p[pos] != '|' and p[pos] != ')':
            ch = p[pos]
            if ch in '*+?{':
                raise ValueError("Quantifier with nothing to repeat")
            elem = parse_element()
            elements.append(elem)
        return elements

    def parse_element():
        nonlocal pos
        atom = parse_atom()
        if pos < length:
            ch = p[pos]
            if ch in '*+?{':
                if isinstance(atom, _Caret) or isinstance(atom, _Dollar):
                    raise ValueError("Cannot quantify ^ or $")
                lo, hi, lazy = parse_quantifier()
                return _Quant(atom, lo, hi, lazy)
        return atom

    def parse_atom():
        nonlocal pos, num_groups
        ch = p[pos]
        if ch == '(':
            return parse_group()
        elif ch == '[':
            return parse_char_class()
        elif ch == '.':
            pos += 1
            return _Dot()
        elif ch == '^':
            pos += 1
            return _Caret()
        elif ch == '$':
            pos += 1
            return _Dollar()
        elif ch == '\\':
            return parse_escape()
        else:
            pos += 1
            return _Lit(ch)

    def parse_group():
        nonlocal pos, num_groups
        # p[pos] == '('
        pos += 1  # consume '('
        if pos + 1 < length and p[pos] == '?' and p[pos + 1] == ':':
            pos += 2  # consume '?:'
            capturing = False
            index = 0
        elif pos + 1 < length and p[pos] == '?':
            # (?... but not (?:  -> invalid
            raise ValueError("Invalid group syntax")
        else:
            capturing = True
            num_groups += 1
            index = num_groups

        body = parse_pattern()

        if pos >= length or p[pos] != ')':
            raise ValueError("Unclosed group")
        pos += 1  # consume ')'
        return _Group(capturing, index, body)

    def parse_char_class():
        nonlocal pos
        # p[pos] == '['
        pos += 1  # consume '['
        negated = False
        if pos < length and p[pos] == '^':
            negated = True
            pos += 1

        items = []
        first = True
        while pos < length:
            ch = p[pos]
            if ch == ']':
                if first:
                    items.append(('char', ']'))
                    pos += 1
                    first = False
                    continue
                else:
                    pos += 1
                    break

            if ch == '\\':
                pos += 1
                if pos >= length:
                    raise ValueError("Unterminated escape in character class")
                esc_ch = p[pos]
                if esc_ch in 'dDwWsS':
                    pos += 1
                    items.append(('class', esc_ch))
                    first = False
                    # Check for invalid range
                    if pos + 1 < length and p[pos] == '-' and p[pos + 1] != ']':
                        raise ValueError("Class escape cannot be part of a range")
                    continue
                elif esc_ch == 'n':
                    pos += 1
                    items.append(('char', '\n'))
                    first = False
                    if pos + 1 < length and p[pos] == '-' and p[pos + 1] != ']':
                        pos += 1  # consume '-'
                        end_item = _parse_class_char()
                        if end_item[0] == 'class':
                            raise ValueError("Class escape cannot be part of a range")
                        if end_item[1] < '\n':
                            raise ValueError("Invalid range in character class")
                        items.pop()
                        items.append(('range', '\n', end_item[1]))
                    continue
                elif esc_ch == 't':
                    pos += 1
                    items.append(('char', '\t'))
                    first = False
                    if pos + 1 < length and p[pos] == '-' and p[pos + 1] != ']':
                        pos += 1  # consume '-'
                        end_item = _parse_class_char()
                        if end_item[0] == 'class':
                            raise ValueError("Class escape cannot be part of a range")
                        if end_item[1] < '\t':
                            raise ValueError("Invalid range in character class")
                        items.pop()
                        items.append(('range', '\t', end_item[1]))
                    continue
                elif esc_ch.isalnum():
                    raise ValueError(f"Invalid escape: \\{esc_ch}")
                else:
                    pos += 1
                    items.append(('char', esc_ch))
                    first = False
                    if pos + 1 < length and p[pos] == '-' and p[pos + 1] != ']':
                        pos += 1  # consume '-'
                        end_item = _parse_class_char()
                        if end_item[0] == 'class':
                            raise ValueError("Class escape cannot be part of a range")
                        if end_item[1] < esc_ch:
                            raise ValueError("Invalid range in character class")
                        items.pop()
                        items.append(('range', esc_ch, end_item[1]))
                    continue
            else:
                pos += 1
                items.append(('char', ch))
                first = False
                if pos + 1 < length and p[pos] == '-' and p[pos + 1] != ']':
                    pos += 1  # consume '-'
                    end_item = _parse_class_char()
                    if end_item[0] == 'class':
                        raise ValueError("Class escape cannot be part of a range")
                    if end_item[1] < ch:
                        raise ValueError("Invalid range in character class")
                    items.pop()
                    items.append(('range', ch, end_item[1]))
                continue

        if pos >= length:
            raise ValueError("Unclosed character class")
        return _Class(negated, items)

    def _parse_class_char():
        nonlocal pos
        ch = p[pos]
        if ch == '\\':
            pos += 1
            if pos >= length:
                raise ValueError("Unterminated escape in character class")
            esc_ch = p[pos]
            if esc_ch in 'dDwWsS':
                pos += 1
                return ('class', esc_ch)
            elif esc_ch == 'n':
                pos += 1
                return ('char', '\n')
            elif esc_ch == 't':
                pos += 1
                return ('char', '\t')
            elif esc_ch.isalnum():
                raise ValueError(f"Invalid escape: \\{esc_ch}")
            else:
                pos += 1
                return ('char', esc_ch)
        else:
            pos += 1
            return ('char', ch)

    def parse_escape():
        nonlocal pos
        # p[pos] == '\\'
        pos += 1
        if pos >= length:
            raise ValueError("Trailing backslash in pattern")
        ch = p[pos]
        if ch in 'dDwWsS':
            pos += 1
            return _ClassEsc(ch)
        elif ch == 'n':
            pos += 1
            return _Lit('\n')
        elif ch == 't':
            pos += 1
            return _Lit('\t')
        elif ch.isalnum():
            raise ValueError(f"Invalid escape: \\{ch}")
        else:
            pos += 1
            return _Lit(ch)

    def parse_quantifier():
        nonlocal pos
        ch = p[pos]
        if ch == '*':
            pos += 1
            lazy = _check_lazy()
            return (0, None, lazy)
        elif ch == '+':
            pos += 1
            lazy = _check_lazy()
            return (1, None, lazy)
        elif ch == '?':
            pos += 1
            lazy = _check_lazy()
            return (0, 1, lazy)
        elif ch == '{':
            return _parse_brace_quantifier()
        else:
            raise ValueError(f"Invalid quantifier: {ch}")

    def _check_lazy():
        nonlocal pos
        if pos < length and p[pos] == '?':
            pos += 1
            return True
        return False

    def _parse_brace_quantifier():
        nonlocal pos
        # p[pos] == '{'
        pos += 1  # consume '{'

        # Parse m
        start = pos
        while pos < length and p[pos].isdigit():
            pos += 1
        if pos == start:
            raise ValueError("Invalid quantifier: {")
        m = int(p[start:pos])

        if pos < length and p[pos] == '}':
            pos += 1  # consume '}'
            lazy = _check_lazy()
            return (m, m, lazy)
        elif pos < length and p[pos] == ',':
            pos += 1  # consume ','
            if pos < length and p[pos] == '}':
                pos += 1  # consume '}'
                lazy = _check_lazy()
                return (m, None, lazy)
            else:
                start = pos
                while pos < length and p[pos].isdigit():
                    pos += 1
                if pos == start:
                    raise ValueError("Invalid quantifier")
                n_val = int(p[start:pos])
                if pos >= length or p[pos] != '}':
                    raise ValueError("Invalid quantifier: unclosed brace")
                pos += 1  # consume '}'
                if m > n_val:
                    raise ValueError("m > n in quantifier")
                lazy = _check_lazy()
                return (m, n_val, lazy)
        else:
            raise ValueError("Invalid quantifier")

    ast = parse_pattern()
    if pos != length:
        # Should not happen if parsing is correct, but just in case
        if p[pos] == ')':
            raise ValueError("Unbalanced parenthesis")
        raise ValueError(f"Unexpected character at position {pos}")
    return ast, num_groups

# === Matcher ===

def _match_seq(elements, pos, s, captures, n, cont):
    """Match a sequence of elements. CPS: cont(pos, captures) -> result."""
    if not elements:
        return cont(pos, captures)

    elem = elements[0]
    rest = elements[1:]

    if isinstance(elem, _Quant):
        def q_cont(pos2, caps2):
            return _match_seq(rest, pos2, s, caps2, n, cont)
        return _match_quant(elem, q_cont, pos, s, captures, n)
    elif isinstance(elem, _Group) or isinstance(elem, _Alt):
        def e_cont(pos2, caps2):
            return _match_seq(rest, pos2, s, caps2, n, cont)
        return _match_atom_cont(elem, pos, s, captures, n, e_cont)
    else:
        result = _match_atom(elem, pos, s, captures, n)
        if result is None:
            return None
        return _match_seq(rest, result, s, captures, n, cont)

def _match_atom(atom, pos, s, captures, n):
    """Match a single atom. Returns new pos or None."""
    if isinstance(atom, _Lit):
        if pos < n and s[pos] == atom.ch:
            return pos + 1
        return None
    elif isinstance(atom, _Dot):
        if pos < n and s[pos] != '\n':
            return pos + 1
        return None
    elif isinstance(atom, _Caret):
        if pos == 0:
            return pos
        return None
    elif isinstance(atom, _Dollar):
        if pos == n or (pos == n - 1 and s[pos] == '\n'):
            return pos
        return None
    elif isinstance(atom, _Class):
        if pos < n and _class_matches(atom, s[pos]):
            return pos + 1
        return None
    elif isinstance(atom, _ClassEsc):
        if pos < n and _class_esc_matches(atom.cls, s[pos]):
            return pos + 1
        return None
    else:
        raise ValueError(f"Unexpected atom type in _match_atom: {type(atom)}")

def _match_atom_cont(atom, pos, s, captures, n, cont):
    """Match a group or alternation atom with continuation."""
    if isinstance(atom, _Group):
        old_captures = captures[:]
        if atom.capturing:
            captures[atom.index] = (pos, pos)
        def group_cont(pos2, caps2):
            if atom.capturing:
                caps2[atom.index] = (pos, pos2)
            return cont(pos2, caps2)
        result = _match_seq(atom.body, pos, s, captures, n, group_cont)
        if result is not None:
            return result
        else:
            captures[:] = old_captures
            return None
    elif isinstance(atom, _Alt):
        for branch in atom.branches:
            old_captures = captures[:]
            result = _match_seq(branch, pos, s, captures, n, cont)
            if result is not None:
                return result
            captures[:] = old_captures
        return None
    else:
        raise ValueError(f"Unexpected atom type in _match_atom_cont: {type(atom)}")

def _match_quant(q, cont, pos, s, captures, n):
    """Match a quantified atom. CPS: cont(pos, captures) -> result."""
    # Phase 1: forced iterations
    for _ in range(q.lo):
        old_captures = captures[:]
        result = _match_atom(q.atom, pos, s, captures, n)
        if result is None:
            captures[:] = old_captures
            return None
        pos = result

    # Phase 2: optional iterations
    if q.lazy:
        return _match_lazy(q, cont, pos, s, captures, n)
    else:
        return _match_greedy(q, cont, pos, s, captures, n)

def _match_greedy(q, cont, pos, s, captures, n):
    """Greedy quantifier: try as many iterations as possible, then backtrack."""
    backtrack_stack = []
    mark = None
    c = 0

    while True:
        if q.hi is not None and c >= q.hi:
            break
        if pos == mark:
            break
        mark = pos
        old_pos = pos
        old_captures = captures[:]
        result = _match_atom(q.atom, pos, s, captures, n)
        if result is None:
            captures[:] = old_captures
            break
        backtrack_stack.append((old_pos, old_captures))
        pos = result
        c += 1

    # Try continuation
    result = cont(pos, captures)
    if result is not None:
        return result

    # Backtrack: undo iterations one by one
    while backtrack_stack:
        prev_pos, prev_captures = backtrack_stack.pop()
        captures[:] = prev_captures
        result = cont(prev_pos, captures)
        if result is not None:
            return result

    return None

def _match_lazy(q, cont, pos, s, captures, n):
    """Lazy quantifier: try continuation first, then more iterations."""
    mark = None
    c = 0

    while True:
        # Try continuation
        saved_captures = captures[:]
        result = cont(pos, captures)
        if result is not None:
            return result
        captures[:] = saved_captures

        # Try one more iteration
        if q.hi is not None and c >= q.hi:
            return None
        if pos == mark:
            return None
        mark = pos
        old_captures = captures[:]
        result = _match_atom(q.atom, pos, s, captures, n)
        if result is None:
            captures[:] = old_captures
            return None
        pos = result
        c += 1

# === Public API ===

class Match:
    __slots__ = ('_s', '_start', '_end', '_captures', '_num_groups')

    def __init__(self, s, start, end, captures, num_groups):
        self._s = s
        self._start = start
        self._end = end
        self._captures = captures
        self._num_groups = num_groups

    def span(self, n=0):
        self._check_group(n)
        if n == 0:
            return (self._start, self._end)
        g = self._captures[n]
        if g is None:
            return (-1, -1)
        return g

    def start(self, n=0):
        self._check_group(n)
        if n == 0:
            return self._start
        g = self._captures[n]
        if g is None:
            return -1
        return g[0]

    def end(self, n=0):
        self._check_group(n)
        if n == 0:
            return self._end
        g = self._captures[n]
        if g is None:
            return -1
        return g[1]

    def group(self, n=0):
        self._check_group(n)
        if n == 0:
            return self._s[self._start:self._end]
        g = self._captures[n]
        if g is None:
            return None
        return self._s[g[0]:g[1]]

    def groups(self):
        result = []
        for i in range(1, self._num_groups + 1):
            g = self._captures[i]
            if g is None:
                result.append(None)
            else:
                result.append(self._s[g[0]:g[1]])
        return tuple(result)

    def _check_group(self, n):
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError(f"Invalid group number: {n!r}")
        if n < 0 or n > self._num_groups:
            raise IndexError(f"Invalid group number: {n}")

class Pattern:
    __slots__ = ('_ast', '_num_groups')

    def __init__(self, ast, num_groups):
        self._ast = ast
        self._num_groups = num_groups

    def fullmatch(self, s):
        n = len(s)
        captures = [None] * (self._num_groups + 1)
        def cont(pos, caps):
            if pos == n:
                return pos
            return None
        result = _match_seq(self._ast, 0, s, captures, n, cont)
        if result is None:
            return None
        return Match(s, 0, result, captures, self._num_groups)

    def search(self, s):
        n = len(s)
        def cont(pos, caps):
            return pos
        for start in range(n + 1):
            captures = [None] * (self._num_groups + 1)
            result = _match_seq(self._ast, start, s, captures, n, cont)
            if result is not None:
                return Match(s, start, result, captures, self._num_groups)
        return None

def compile(pattern: str) -> Pattern:
    ast, num_groups = _parse_pattern(pattern)
    return Pattern(ast, num_groups)
