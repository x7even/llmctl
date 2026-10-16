import sys

# AST Node types
class _Literal:
    __slots__ = ('ch',)
    def __init__(self, ch): self.ch = ch

class _Dot:
    __slots__ = ()

class _AssertStart:
    __slots__ = ()

class _AssertEnd:
    __slots__ = ()

class _CharClass:
    __slots__ = ('items', 'negated')
    def __init__(self, items, negated):
        self.items = items
        self.negated = negated

class _Group:
    __slots__ = ('idx', 'child')
    def __init__(self, idx, child):
        self.idx = idx
        self.child = child

class _Concat:
    __slots__ = ('children',)
    def __init__(self, children): self.children = children

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Quant:
    __slots__ = ('child', 'lo', 'hi', 'greedy')
    def __init__(self, child, lo, hi, greedy):
        self.child = child
        self.lo = lo
        self.hi = hi
        self.greedy = greedy

# --- Parser ---

_DIGITS = set('0123456789')
_CLASS_ESCAPES = set('dDwWsS')
_WHITESPACE = ' \t\n\r\f\v'

def _is_word_char(ch):
    return ('a' <= ch <= 'z') or ('A' <= ch <= 'Z') or ('0' <= ch <= '9') or ch == '_'

def _is_digit(ch):
    return '0' <= ch <= '9'

def _is_space(ch):
    return ch in _WHITESPACE

def _matches_class_escape(ch, esc):
    if esc == 'd': return _is_digit(ch)
    if esc == 'D': return not _is_digit(ch)
    if esc == 'w': return _is_word_char(ch)
    if esc == 'W': return not _is_word_char(ch)
    if esc == 's': return _is_space(ch)
    if esc == 'S': return not _is_space(ch)
    return False

def _class_matches(ch, items, negated):
    for item in items:
        if item[0] == 'c':
            if ch == item[1]:
                return not negated
        elif item[0] == 'r':
            if item[1] <= ch <= item[2]:
                return not negated
        elif item[0] == 'e':
            if _matches_class_escape(ch, item[1]):
                return not negated
    return negated


class _Parser:
    def __init__(self, pattern):
        self.p = pattern
        self.pos = 0
        self.group_count = 0

    def parse(self):
        node = self._parse_alt()
        if self.pos < len(self.p):
            if self.p[self.pos] == ')':
                raise ValueError("unbalanced parenthesis")
            raise ValueError("unexpected character: " + repr(self.p[self.pos]))
        return node

    def _parse_alt(self):
        branches = [self._parse_concat()]
        while self.pos < len(self.p) and self.p[self.pos] == '|':
            self.pos += 1
            branches.append(self._parse_concat())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _parse_concat(self):
        items = []
        while self.pos < len(self.p) and self.p[self.pos] not in '|)':
            items.append(self._parse_quant())
        if len(items) == 0:
            return _Concat([])
        if len(items) == 1:
            return items[0]
        return _Concat(items)

    def _parse_quant(self):
        atom = self._parse_atom()
        if self.pos >= len(self.p):
            return atom
        ch = self.p[self.pos]
        if ch in '*+?':
            if isinstance(atom, (_AssertStart, _AssertEnd)):
                raise ValueError("cannot quantify anchor")
            self.pos += 1
            if ch == '*': lo, hi = 0, None
            elif ch == '+': lo, hi = 1, None
            else: lo, hi = 0, 1
            greedy = True
            if self.pos < len(self.p) and self.p[self.pos] == '?':
                greedy = False
                self.pos += 1
            return _Quant(atom, lo, hi, greedy)
        elif ch == '{':
            saved = self.pos
            self.pos += 1
            m = self._parse_digits()
            if m is None:
                self.pos = saved
                raise ValueError("invalid quantifier: {")
            if self.pos < len(self.p) and self.p[self.pos] == ',':
                self.pos += 1
                n = self._parse_digits()
                if n is not None and n < m:
                    raise ValueError("min > max in quantifier")
                hi = n
            else:
                hi = None
            if self.pos >= len(self.p) or self.p[self.pos] != '}':
                self.pos = saved
                raise ValueError("invalid quantifier: {")
            self.pos += 1
            if isinstance(atom, (_AssertStart, _AssertEnd)):
                raise ValueError("cannot quantify anchor")
            lo = m
            greedy = True
            if self.pos < len(self.p) and self.p[self.pos] == '?':
                greedy = False
                self.pos += 1
            return _Quant(atom, lo, hi, greedy)
        return atom

    def _parse_digits(self):
        start = self.pos
        while self.pos < len(self.p) and self.p[self.pos] in _DIGITS:
            self.pos += 1
        if self.pos == start:
            return None
        return int(self.p[start:self.pos])

    def _parse_atom(self):
        if self.pos >= len(self.p):
            return _Concat([])
        ch = self.p[self.pos]
        if ch == '(':
            return self._parse_group()
        elif ch == '[':
            return self._parse_class()
        elif ch == '.':
            self.pos += 1
            return _Dot()
        elif ch == '^':
            self.pos += 1
            return _AssertStart()
        elif ch == '$':
            self.pos += 1
            return _AssertEnd()
        elif ch == '\\':
            return self._parse_escape()
        elif ch in '*+?{':
            raise ValueError("quantifier with nothing to repeat")
        elif ch == ')':
            raise ValueError("unbalanced parenthesis")
        else:
            self.pos += 1
            return _Literal(ch)

    def _parse_escape(self):
        self.pos += 1  # skip backslash
        if self.pos >= len(self.p):
            raise ValueError("backslash at end of pattern")
        ch = self.p[self.pos]
        if ch in _CLASS_ESCAPES:
            self.pos += 1
            items = [('e', ch)]
            return _CharClass(items, ch in 'DWS')
        elif ch == 'n':
            self.pos += 1
            return _Literal('\n')
        elif ch == 't':
            self.pos += 1
            return _Literal('\t')
        elif not ch.isalnum():
            self.pos += 1
            return _Literal(ch)
        else:
            raise ValueError("invalid escape: \\" + ch)

    def _parse_class_char(self):
        """Parse a single character (not class escape) inside a class. Returns the char."""
        if self.pos >= len(self.p):
            raise ValueError("unterminated character class")
        ch = self.p[self.pos]
        if ch == '\\':
            self.pos += 1
            if self.pos >= len(self.p):
                raise ValueError("unterminated character class")
            c2 = self.p[self.pos]
            if c2 in _CLASS_ESCAPES:
                raise ValueError("class escape in range")
            elif c2 == 'n':
                self.pos += 1
                return '\n'
            elif c2 == 't':
                self.pos += 1
                return '\t'
            elif not c2.isalnum():
                self.pos += 1
                return c2
            else:
                raise ValueError("invalid escape in character class")
        else:
            self.pos += 1
            return ch

    def _parse_class(self):
        self.pos += 1  # skip [
        negated = False
        if self.pos < len(self.p) and self.p[self.pos] == '^':
            negated = True
            self.pos += 1
        items = []
        first = True
        while True:
            if self.pos >= len(self.p):
                raise ValueError("unterminated character class")
            if self.p[self.pos] == ']' and not first:
                self.pos += 1
                return _CharClass(items, negated)
            first = False
            # Parse one item
            if self.p[self.pos] == '\\':
                self.pos += 1
                if self.pos >= len(self.p):
                    raise ValueError("unterminated character class")
                c = self.p[self.pos]
                if c in _CLASS_ESCAPES:
                    self.pos += 1
                    # Check for illegal range: \d-x where x != ]
                    if self.pos < len(self.p) and self.p[self.pos] == '-' and \
                       self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']':
                        raise ValueError("class escape in range")
                    items.append(('e', c))
                    continue
                elif c == 'n':
                    self.pos += 1
                    lo = '\n'
                elif c == 't':
                    self.pos += 1
                    lo = '\t'
                elif not c.isalnum():
                    self.pos += 1
                    lo = c
                else:
                    raise ValueError("invalid escape in character class")
                # Check for range
                if self.pos < len(self.p) and self.p[self.pos] == '-' and \
                   self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']':
                    self.pos += 1
                    hi = self._parse_class_char()
                    if ord(lo) > ord(hi):
                        raise ValueError("invalid range in character class")
                    items.append(('r', lo, hi))
                else:
                    items.append(('c', lo))
            else:
                lo = self.p[self.pos]
                self.pos += 1
                # Check for range
                if self.pos < len(self.p) and self.p[self.pos] == '-' and \
                   self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']':
                    self.pos += 1
                    hi = self._parse_class_char()
                    if ord(lo) > ord(hi):
                        raise ValueError("invalid range in character class")
                    items.append(('r', lo, hi))
                else:
                    items.append(('c', lo))

    def _parse_group(self):
        self.pos += 1  # skip (
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            self.pos += 1
            if self.pos < len(self.p) and self.p[self.pos] == ':':
                self.pos += 1
                child = self._parse_alt()
                if self.pos >= len(self.p) or self.p[self.pos] != ')':
                    raise ValueError("unbalanced parenthesis")
                self.pos += 1
                return _Group(0, child)
            else:
                raise ValueError("unsupported group syntax")
        else:
            self.group_count += 1
            idx = self.group_count
            child = self._parse_alt()
            if self.pos >= len(self.p) or self.p[self.pos] != ')':
                raise ValueError("unbalanced parenthesis")
            self.pos += 1
            return _Group(idx, child)


# --- Matcher (iterative backtracking) ---

def _match(s, root, start_pos, num_groups, must_full):
    n = len(s)
    pos = start_pos
    captures = [None] * num_groups

    stack = []
    bt_stack = []

    stack.append(('node', root))

    while True:
        if not stack:
            # Pattern fully matched
            if must_full:
                if pos == n:
                    return (pos, captures)
                # Need to backtrack
                if not bt_stack:
                    return None
                pos, captures, sl, alt = bt_stack.pop()
                del stack[sl:]
                stack.append(alt)
                continue
            else:
                return (pos, captures)

        task = stack.pop()
        kind = task[0]

        if kind == 'node':
            node = task[1]
            ntype = type(node)

            if ntype is _Literal:
                if pos < n and s[pos] == node.ch:
                    pos += 1
                else:
                    if not bt_stack:
                        return None
                    pos, captures, sl, alt = bt_stack.pop()
                    del stack[sl:]
                    stack.append(alt)

            elif ntype is _Dot:
                if pos < n and s[pos] != '\n':
                    pos += 1
                else:
                    if not bt_stack:
                        return None
                    pos, captures, sl, alt = bt_stack.pop()
                    del stack[sl:]
                    stack.append(alt)

            elif ntype is _AssertStart:
                if pos == 0:
                    pass
                else:
                    if not bt_stack:
                        return None
                    pos, captures, sl, alt = bt_stack.pop()
                    del stack[sl:]
                    stack.append(alt)

            elif ntype is _AssertEnd:
                if pos == n or (pos == n - 1 and s[pos] == '\n'):
                    pass
                else:
                    if not bt_stack:
                        return None
                    pos, captures, sl, alt = bt_stack.pop()
                    del stack[sl:]
                    stack.append(alt)

            elif ntype is _CharClass:
                if pos < n and _class_matches(s[pos], node.items, node.negated):
                    pos += 1
                else:
                    if not bt_stack:
                        return None
                    pos, captures, sl, alt = bt_stack.pop()
                    del stack[sl:]
                    stack.append(alt)

            elif ntype is _Concat:
                children = node.children
                for i in range(len(children) - 1, -1, -1):
                    stack.append(('node', children[i]))

            elif ntype is _Alt:
                branches = node.branches
                for i in range(len(branches) - 1, 0, -1):
                    bt_stack.append((pos, captures.copy() if num_groups else captures,
                                     len(stack), ('node', branches[i])))
                stack.append(('node', branches[0]))

            elif ntype is _Group:
                if node.idx > 0:
                    stack.append(('gend', node.idx))
                    stack.append(('gstart', node.idx))
                stack.append(('node', node.child))

            elif ntype is _Quant:
                stack.append(('quant', node, 0, None))

            else:
                # Should not happen
                raise ValueError("unknown node type")

        elif kind == 'gstart':
            idx = task[1]
            captures[idx - 1] = (pos, pos)

        elif kind == 'gend':
            idx = task[1]
            cs = captures[idx - 1]
            captures[idx - 1] = (cs[0], pos)

        elif kind == 'quant':
            node = task[1]
            c = task[2]
            mark = task[3]
            lo = node.lo
            hi = node.hi
            greedy = node.greedy

            if c < lo:
                # Forced iteration
                stack.append(('qafter', node, c + 1, mark))
                stack.append(('node', node.child))
            else:
                can_iter = (hi is None or c < hi) and (mark is None or pos != mark)

                if greedy:
                    if can_iter:
                        bt_stack.append((pos, captures.copy() if num_groups else captures,
                                         len(stack), ('noop',)))
                        stack.append(('qafter', node, c + 1, pos))
                        stack.append(('node', node.child))
                    # else: continue with what follows (already on stack)
                else:
                    # Lazy: try what follows first
                    if can_iter:
                        bt_stack.append((pos, captures.copy() if num_groups else captures,
                                         len(stack), ('qiter', node, c, pos)))
                    # Continue with what follows

        elif kind == 'qafter':
            node = task[1]
            new_c = task[2]
            new_mark = task[3]
            stack.append(('quant', node, new_c, new_mark))

        elif kind == 'qiter':
            node = task[1]
            c = task[2]
            mark = task[3]
            stack.append(('qafter', node, c + 1, mark))
            stack.append(('node', node.child))

        elif kind == 'noop':
            pass

    return None


# --- Public API ---

class Match:
    __slots__ = ('_s', '_start', '_end', '_captures', '_num_groups')

    def __init__(self, s, start, end, captures, num_groups):
        self._s = s
        self._start = start
        self._end = end
        self._captures = captures
        self._num_groups = num_groups

    def span(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError("no such group")
        if n < 0 or n > self._num_groups:
            raise IndexError("no such group")
        if n == 0:
            return (self._start, self._end)
        c = self._captures[n - 1]
        if c is None:
            return (-1, -1)
        return c

    def start(self, n=0):
        return self.span(n)[0]

    def end(self, n=0):
        return self.span(n)[1]

    def group(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError("no such group")
        if n < 0 or n > self._num_groups:
            raise IndexError("no such group")
        if n == 0:
            return self._s[self._start:self._end]
        c = self._captures[n - 1]
        if c is None:
            return None
        return self._s[c[0]:c[1]]

    def groups(self):
        result = []
        for i in range(self._num_groups):
            c = self._captures[i]
            if c is None:
                result.append(None)
            else:
                result.append(self._s[c[0]:c[1]])
        return tuple(result)


class Pattern:
    __slots__ = ('_root', '_num_groups')

    def __init__(self, root, num_groups):
        self._root = root
        self._num_groups = num_groups

    def fullmatch(self, s):
        result = _match(s, self._root, 0, self._num_groups, True)
        if result is not None:
            end_pos, caps = result
            return Match(s, 0, end_pos, caps, self._num_groups)
        return None

    def search(self, s):
        for start in range(len(s) + 1):
            result = _match(s, self._root, start, self._num_groups, False)
            if result is not None:
                end_pos, caps = result
                return Match(s, start, end_pos, caps, self._num_groups)
        return None


def compile(pattern):
    parser = _Parser(pattern)
    root = parser.parse()
    return Pattern(root, parser.group_count)
