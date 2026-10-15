import sys
sys.setrecursionlimit(200000)

# ==================== AST Nodes ====================

class _Empty:
    __slots__ = ()

class _Literal:
    __slots__ = ('ch',)
    def __init__(self, ch): self.ch = ch

class _Dot:
    __slots__ = ()

class _CharClass:
    __slots__ = ('items', 'negated')
    def __init__(self, items, negated):
        self.items = items
        self.negated = negated

class _AnchorStart:
    __slots__ = ()

class _AnchorEnd:
    __slots__ = ()

class _Group:
    __slots__ = ('index', 'child')
    def __init__(self, index, child):
        self.index = index
        self.child = child

class _NonCapGroup:
    __slots__ = ('child',)
    def __init__(self, child): self.child = child

class _Alternation:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Sequence:
    __slots__ = ('items',)
    def __init__(self, items): self.items = items

class _Quantifier:
    __slots__ = ('child', 'lo', 'hi', 'greedy')
    def __init__(self, child, lo, hi, greedy):
        self.child = child
        self.lo = lo
        self.hi = hi
        self.greedy = greedy

# ==================== Character Sets ====================

_DIGIT = frozenset('0123456789')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')

def _class_escape_match(name, ch):
    if name == 'd': return ch in _DIGIT
    if name == 'D': return ch not in _DIGIT
    if name == 'w': return ch in _WORD
    if name == 'W': return ch not in _WORD
    if name == 's': return ch in _SPACE
    if name == 'S': return ch not in _SPACE
    return False

def _charclass_matches(cc, ch):
    result = False
    for item in cc.items:
        if item[0] == 'char':
            if ch == item[1]:
                result = True; break
        elif item[0] == 'range':
            if item[1] <= ch <= item[2]:
                result = True; break
        elif item[0] == 'class':
            if _class_escape_match(item[1], ch):
                result = True; break
    if cc.negated:
        return not result
    return result

# ==================== Parser ====================

class _Parser:
    def __init__(self, pattern):
        self.pattern = pattern
        self.pos = 0
        self.num_groups = 0

    def parse(self):
        result = self._parse_alternation()
        if self.pos != len(self.pattern):
            raise ValueError("Unexpected character at position %d" % self.pos)
        return result, self.num_groups

    def _parse_alternation(self):
        branches = [self._parse_sequence()]
        while self.pos < len(self.pattern) and self.pattern[self.pos] == '|':
            self.pos += 1
            branches.append(self._parse_sequence())
        if len(branches) == 1:
            return branches[0]
        return _Alternation(branches)

    def _parse_sequence(self):
        items = []
        while self.pos < len(self.pattern) and self.pattern[self.pos] not in '|)':
            items.append(self._parse_quantified())
        if len(items) == 0:
            return _Empty()
        if len(items) == 1:
            return items[0]
        return _Sequence(items)

    def _parse_quantified(self):
        atom = self._parse_atom()
        if self.pos < len(self.pattern):
            ch = self.pattern[self.pos]
            if ch in '*+?{':
                if isinstance(atom, (_AnchorStart, _AnchorEnd)):
                    raise ValueError("Cannot quantify anchor")
                quant = self._make_quantifier(atom)
                if self.pos < len(self.pattern) and self.pattern[self.pos] in '*+?{':
                    raise ValueError("Quantifier after quantifier")
                return quant
        return atom

    def _make_quantifier(self, atom):
        ch = self.pattern[self.pos]
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
            lo, hi = self._parse_brace()
        else:
            raise ValueError("Invalid quantifier")
        greedy = True
        if self.pos < len(self.pattern) and self.pattern[self.pos] == '?':
            greedy = False
            self.pos += 1
        return _Quantifier(atom, lo, hi, greedy)

    def _parse_brace(self):
        start = self.pos
        self.pos += 1  # skip '{'
        if self.pos >= len(self.pattern) or not self.pattern[self.pos].isdigit():
            raise ValueError("Invalid quantifier at position %d" % start)
        m_start = self.pos
        while self.pos < len(self.pattern) and self.pattern[self.pos].isdigit():
            self.pos += 1
        m = int(self.pattern[m_start:self.pos])
        if self.pos < len(self.pattern) and self.pattern[self.pos] == ',':
            self.pos += 1
            n_start = self.pos
            while self.pos < len(self.pattern) and self.pattern[self.pos].isdigit():
                self.pos += 1
            if self.pos == n_start:
                n = None
            else:
                n = int(self.pattern[n_start:self.pos])
                if m > n:
                    raise ValueError("m > n in quantifier")
        else:
            n = m
        if self.pos >= len(self.pattern) or self.pattern[self.pos] != '}':
            raise ValueError("Invalid quantifier at position %d" % start)
        self.pos += 1
        return m, n

    def _parse_atom(self):
        if self.pos >= len(self.pattern):
            return _Empty()
        ch = self.pattern[self.pos]
        if ch in '*+?{':
            raise ValueError("Nothing to repeat at position %d" % self.pos)
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
            return self._parse_escape()
        self.pos += 1
        return _Literal(ch)

    def _parse_escape(self):
        self.pos += 1  # skip backslash
        if self.pos >= len(self.pattern):
            raise ValueError("Backslash at end of pattern")
        ch = self.pattern[self.pos]
        if ch in 'dDwWsS':
            self.pos += 1
            return _CharClass([('class', ch)], False)
        if ch == 'n':
            self.pos += 1
            return _Literal('\n')
        if ch == 't':
            self.pos += 1
            return _Literal('\t')
        if not ch.isalnum():
            self.pos += 1
            return _Literal(ch)
        raise ValueError("Invalid escape: \\%s" % ch)

    def _parse_group(self):
        self.pos += 1  # skip '('
        if self.pos < len(self.pattern) and self.pattern[self.pos] == '?':
            if self.pos + 1 < len(self.pattern) and self.pattern[self.pos + 1] == ':':
                self.pos += 2
                inner = self._parse_alternation()
                if self.pos >= len(self.pattern) or self.pattern[self.pos] != ')':
                    raise ValueError("Unbalanced parentheses")
                self.pos += 1
                return _NonCapGroup(inner)
            else:
                raise ValueError("Unsupported group syntax")
        else:
            self.num_groups += 1
            idx = self.num_groups
            inner = self._parse_alternation()
            if self.pos >= len(self.pattern) or self.pattern[self.pos] != ')':
                raise ValueError("Unbalanced parentheses")
            self.pos += 1
            return _Group(idx, inner)

    def _parse_class(self):
        self.pos += 1  # skip '['
        negated = False
        if self.pos < len(self.pattern) and self.pattern[self.pos] == '^':
            negated = True
            self.pos += 1
        items = []
        first = True
        while True:
            if self.pos >= len(self.pattern):
                raise ValueError("Unterminated character class")
            if self.pattern[self.pos] == ']' and not first:
                self.pos += 1
                break
            if self.pattern[self.pos] == ']' and first:
                item = ('char', ']')
                self.pos += 1
            else:
                item = self._parse_class_item()
            first = False
            if item[0] == 'char':
                if self.pos < len(self.pattern) and self.pattern[self.pos] == '-':
                    if self.pos + 1 < len(self.pattern) and self.pattern[self.pos + 1] != ']':
                        self.pos += 1
                        end_item = self._parse_class_item()
                        if end_item[0] != 'char':
                            raise ValueError("Invalid range end in character class")
                        if item[1] > end_item[1]:
                            raise ValueError("Invalid range in character class")
                        items.append(('range', item[1], end_item[1]))
                        continue
                    elif self.pos + 1 >= len(self.pattern):
                        raise ValueError("Unterminated character class")
                items.append(item)
            elif item[0] == 'class':
                if self.pos < len(self.pattern) and self.pattern[self.pos] == '-':
                    if self.pos + 1 < len(self.pattern) and self.pattern[self.pos + 1] != ']':
                        raise ValueError("Class escape cannot be in range")
                    elif self.pos + 1 >= len(self.pattern):
                        raise ValueError("Unterminated character class")
                items.append(item)
        return _CharClass(items, negated)

    def _parse_class_item(self):
        ch = self.pattern[self.pos]
        if ch == '\\':
            self.pos += 1
            if self.pos >= len(self.pattern):
                raise ValueError("Backslash at end of pattern")
            esc = self.pattern[self.pos]
            if esc in 'dDwWsS':
                self.pos += 1
                return ('class', esc)
            if esc == 'n':
                self.pos += 1
                return ('char', '\n')
            if esc == 't':
                self.pos += 1
                return ('char', '\t')
            if not esc.isalnum():
                self.pos += 1
                return ('char', esc)
            raise ValueError("Invalid escape in character class: \\%s" % esc)
        else:
            self.pos += 1
            return ('char', ch)

# ==================== Matcher ====================

class _Matcher:
    def __init__(self, ast, num_groups):
        self.ast = ast
        self.num_groups = num_groups

    def fullmatch(self, s):
        self.s = s
        self._memo = set()
        captures = {i: None for i in range(1, self.num_groups + 1)}
        n = len(s)
        if self._match(self.ast, 0, captures, lambda p: p == n):
            return _Match(captures, 0, n, s, self.num_groups)
        return None

    def search(self, s):
        self.s = s
        self._memo = set()
        n = len(s)
        for start in range(n + 1):
            captures = {i: None for i in range(1, self.num_groups + 1)}
            end = [None]
            def cont(p):
                end[0] = p
                return True
            if self._match(self.ast, start, captures, cont):
                return _Match(captures, start, end[0], s, self.num_groups)
        return None

    def _match(self, node, pos, captures, cont):
        tp = type(node)
        if tp is _Empty:
            return cont(pos)
        if tp is _Literal:
            if pos < len(self.s) and self.s[pos] == node.ch:
                return cont(pos + 1)
            return False
        if tp is _Dot:
            if pos < len(self.s) and self.s[pos] != '\n':
                return cont(pos + 1)
            return False
        if tp is _CharClass:
            if pos < len(self.s) and _charclass_matches(node, self.s[pos]):
                return cont(pos + 1)
            return False
        if tp is _AnchorStart:
            if pos == 0:
                return cont(pos)
            return False
        if tp is _AnchorEnd:
            slen = len(self.s)
            if pos == slen or (pos == slen - 1 and self.s[pos] == '\n'):
                return cont(pos)
            return False
        if tp is _Group:
            return self._match_group(node, pos, captures, cont)
        if tp is _NonCapGroup:
            return self._match(node.child, pos, captures, cont)
        if tp is _Alternation:
            return self._match_alt(node, pos, captures, cont)
        if tp is _Sequence:
            return self._match_seq(node, 0, pos, captures, cont)
        if tp is _Quantifier:
            return self._match_quant(node, pos, captures, cont)
        raise AssertionError("Unknown node type")

    def _match_group(self, node, pos, captures, cont):
        saved = dict(captures)
        captures[node.index] = (pos, None)

        def after_child(new_pos):
            captures[node.index] = (pos, new_pos)
            result = cont(new_pos)
            if not result:
                captures.clear()
                captures.update(saved)
            return result

        result = self._match(node.child, pos, captures, after_child)
        if not result:
            captures.clear()
            captures.update(saved)
        return result

    def _match_alt(self, node, pos, captures, cont):
        for branch in node.branches:
            if self._match(branch, pos, captures, cont):
                return True
        return False

    def _match_seq(self, node, idx, pos, captures, cont):
        if idx >= len(node.items):
            return cont(pos)
        def next_item(new_pos):
            return self._match_seq(node, idx + 1, new_pos, captures, cont)
        return self._match(node.items[idx], pos, captures, next_item)

    def _match_quant(self, node, pos, captures, cont):
        if node.lo == 0 and node.hi == 0:
            return cont(pos)

        saved = dict(captures)
        nid = id(node)
        hi = node.hi
        lo = node.lo
        greedy = node.greedy
        child = node.child
        memo = self._memo

        def loop(c, mark, p):
            if c < lo:
                def after_iter(new_pos):
                    return loop(c + 1, mark, new_pos)
                return self._match(child, p, captures, after_iter)

            # Optional phase
            if hi is None:
                memo_key = (nid, p)
            else:
                memo_key = (nid, p, c)
            if memo_key in memo:
                return False

            if greedy:
                can_iter = (hi is None or c < hi) and (p != mark)
                if can_iter:
                    def after_iter(new_pos):
                        return loop(c + 1, p, new_pos)
                    if self._match(child, p, captures, after_iter):
                        return True
                if cont(p):
                    return True
            else:
                if cont(p):
                    return True
                can_iter = (hi is None or c < hi) and (p != mark)
                if can_iter:
                    def after_iter(new_pos):
                        return loop(c + 1, p, new_pos)
                    if self._match(child, p, captures, after_iter):
                        return True

            memo.add(memo_key)
            return False

        result = loop(0, None, pos)
        if not result:
            captures.clear()
            captures.update(saved)
        return result

# ==================== Match Object ====================

class _Match:
    def __init__(self, captures, start, end, s, num_groups):
        self._captures = captures
        self._start = start
        self._end = end
        self._s = s
        self._num_groups = num_groups

    def span(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > self._num_groups:
            raise IndexError("group index out of range")
        if n == 0:
            return (self._start, self._end)
        cap = self._captures.get(n)
        if cap is None:
            return (-1, -1)
        return cap

    def start(self, n=0):
        return self.span(n)[0]

    def end(self, n=0):
        return self.span(n)[1]

    def group(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > self._num_groups:
            raise IndexError("group index out of range")
        if n == 0:
            return self._s[self._start:self._end]
        cap = self._captures.get(n)
        if cap is None:
            return None
        return self._s[cap[0]:cap[1]]

    def groups(self):
        result = []
        for i in range(1, self._num_groups + 1):
            cap = self._captures.get(i)
            if cap is None:
                result.append(None)
            else:
                result.append(self._s[cap[0]:cap[1]])
        return tuple(result)

# ==================== Public API ====================

Match = _Match

class Pattern:
    def __init__(self, ast, num_groups):
        self._ast = ast
        self._num_groups = num_groups

    def fullmatch(self, s):
        matcher = _Matcher(self._ast, self._num_groups)
        return matcher.fullmatch(s)

    def search(self, s):
        matcher = _Matcher(self._ast, self._num_groups)
        return matcher.search(s)

def compile(pattern: str) -> Pattern:
    parser = _Parser(pattern)
    ast, num_groups = parser.parse()
    return Pattern(ast, num_groups)
