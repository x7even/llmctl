import sys
sys.setrecursionlimit(300000)

# --- AST Nodes ---
class _Seq:
    __slots__ = ('nodes',)
    def __init__(self, nodes): self.nodes = nodes

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Lit:
    __slots__ = ('ch',)
    def __init__(self, ch): self.ch = ch

class _Any:
    pass

class _Start:
    pass

class _End:
    pass

class _ClassEsc:
    __slots__ = ('kind',)
    def __init__(self, kind): self.kind = kind

class _CharClass:
    __slots__ = ('negated', 'items')
    def __init__(self, negated, items):
        self.negated = negated
        self.items = items

class _Group:
    __slots__ = ('idx', 'body')
    def __init__(self, idx, body):
        self.idx = idx
        self.body = body

class _NonCap:
    __slots__ = ('body',)
    def __init__(self, body): self.body = body

class _Quant:
    __slots__ = ('atom', 'lo', 'hi', 'greedy')
    def __init__(self, atom, lo, hi, greedy):
        self.atom = atom
        self.lo = lo
        self.hi = hi
        self.greedy = greedy

# --- Character sets ---
_DIGITS = frozenset('0123456789')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')

def _class_esc_match(kind, ch):
    if kind == 'd': return ch in _DIGITS
    if kind == 'D': return ch not in _DIGITS
    if kind == 'w': return ch in _WORD
    if kind == 'W': return ch not in _WORD
    if kind == 's': return ch in _SPACE
    if kind == 'S': return ch not in _SPACE
    return False

def _charclass_match(cc, ch):
    found = False
    for item in cc.items:
        if isinstance(item, tuple):
            if ord(item[0]) <= ord(ch) <= ord(item[1]):
                found = True
                break
        elif isinstance(item, str):
            if ch == item:
                found = True
                break
        elif isinstance(item, _ClassEsc):
            if _class_esc_match(item.kind, ch):
                found = True
                break
    if cc.negated:
        return not found
    return found

def _is_simple(node):
    return isinstance(node, (_Lit, _Any, _ClassEsc, _CharClass))

def _match_simple(node, pos, s):
    if isinstance(node, _Lit):
        return pos < len(s) and s[pos] == node.ch
    if isinstance(node, _Any):
        return pos < len(s) and s[pos] != '\n'
    if isinstance(node, _ClassEsc):
        return pos < len(s) and _class_esc_match(node.kind, s[pos])
    if isinstance(node, _CharClass):
        return pos < len(s) and _charclass_match(node, s[pos])
    return False

# --- Parser ---
class _Parser:
    def __init__(self, pattern):
        self.pattern = pattern
        self.pos = 0
        self.num_groups = 0

    def parse(self):
        node = self._parse_alternation()
        if self.pos != len(self.pattern):
            raise ValueError("unexpected character")
        return node

    def _parse_alternation(self):
        branches = [self._parse_sequence()]
        while self.pos < len(self.pattern) and self.pattern[self.pos] == '|':
            self.pos += 1
            branches.append(self._parse_sequence())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _parse_sequence(self):
        items = []
        while self.pos < len(self.pattern):
            ch = self.pattern[self.pos]
            if ch == '|' or ch == ')':
                break
            item = self._parse_quantified()
            if item is None:
                break
            items.append(item)
        if len(items) == 0:
            return _Seq([])
        if len(items) == 1:
            return items[0]
        return _Seq(items)

    def _parse_quantified(self):
        atom = self._parse_atom()
        if atom is None:
            return None
        if self.pos < len(self.pattern) and self.pattern[self.pos] in '*+?{':
            if isinstance(atom, (_Start, _End)):
                raise ValueError("nothing to repeat")
            quant = self._parse_quantifier(atom)
            if self.pos < len(self.pattern) and self.pattern[self.pos] in '*+?{':
                raise ValueError("quantifier after quantifier")
            return quant
        return atom

    def _parse_quantifier(self, atom):
        ch = self.pattern[self.pos]
        self.pos += 1
        if ch == '*':
            lo, hi = 0, None
        elif ch == '+':
            lo, hi = 1, None
        elif ch == '?':
            lo, hi = 0, 1
        elif ch == '{':
            lo, hi = self._parse_brace()
        else:
            raise ValueError("internal error")
        greedy = True
        if self.pos < len(self.pattern) and self.pattern[self.pos] == '?':
            greedy = False
            self.pos += 1
        if hi is not None and lo > hi:
            raise ValueError("min repeat greater than max repeat")
        return _Quant(atom, lo, hi, greedy)

    def _parse_brace(self):
        m_start = self.pos
        while self.pos < len(self.pattern) and self.pattern[self.pos].isdigit():
            self.pos += 1
        if self.pos == m_start:
            raise ValueError("invalid quantifier")
        m = int(self.pattern[m_start:self.pos])
        hi = m
        if self.pos < len(self.pattern) and self.pattern[self.pos] == ',':
            self.pos += 1
            n_start = self.pos
            while self.pos < len(self.pattern) and self.pattern[self.pos].isdigit():
                self.pos += 1
            if self.pos > n_start:
                hi = int(self.pattern[n_start:self.pos])
            else:
                hi = None
        if self.pos >= len(self.pattern) or self.pattern[self.pos] != '}':
            raise ValueError("invalid quantifier")
        self.pos += 1
        return m, hi

    def _parse_atom(self):
        if self.pos >= len(self.pattern):
            return None
        ch = self.pattern[self.pos]
        if ch == '(':
            return self._parse_group()
        if ch == '[':
            return self._parse_charclass()
        if ch == '.':
            self.pos += 1
            return _Any()
        if ch == '^':
            self.pos += 1
            return _Start()
        if ch == '$':
            self.pos += 1
            return _End()
        if ch == '\\':
            return self._parse_escape()
        if ch in '*+?{':
            raise ValueError("nothing to repeat")
        if ch == ')':
            raise ValueError("unbalanced parenthesis")
        self.pos += 1
        return _Lit(ch)

    def _parse_escape(self):
        self.pos += 1
        if self.pos >= len(self.pattern):
            raise ValueError("backslash at end of pattern")
        ch = self.pattern[self.pos]
        if ch in 'dDwWsS':
            self.pos += 1
            return _ClassEsc(ch)
        if ch == 'n':
            self.pos += 1
            return _Lit('\n')
        if ch == 't':
            self.pos += 1
            return _Lit('\t')
        if ch.isalpha() or ch.isdigit():
            raise ValueError(f"invalid escape \\{ch}")
        self.pos += 1
        return _Lit(ch)

    def _parse_group(self):
        self.pos += 1  # consume '('
        if self.pos < len(self.pattern) and self.pattern[self.pos] == '?':
            if self.pos + 1 < len(self.pattern) and self.pattern[self.pos + 1] == ':':
                self.pos += 2  # consume '(?:'
                body = self._parse_alternation()
                if self.pos >= len(self.pattern) or self.pattern[self.pos] != ')':
                    raise ValueError("unbalanced parenthesis")
                self.pos += 1
                return _NonCap(body)
            raise ValueError("unsupported group syntax")
        self.num_groups += 1
        idx = self.num_groups
        body = self._parse_alternation()
        if self.pos >= len(self.pattern) or self.pattern[self.pos] != ')':
            raise ValueError("unbalanced parenthesis")
        self.pos += 1
        return _Group(idx, body)

    def _parse_charclass(self):
        self.pos += 1  # consume '['
        negated = False
        if self.pos < len(self.pattern) and self.pattern[self.pos] == '^':
            negated = True
            self.pos += 1
        items = []
        # ] as first char is literal
        if self.pos < len(self.pattern) and self.pattern[self.pos] == ']':
            items.append(']')
            self.pos += 1
        while True:
            if self.pos >= len(self.pattern):
                raise ValueError("unterminated character class")
            if self.pattern[self.pos] == ']':
                self.pos += 1
                break
            item = self._parse_class_item()
            # Check for range
            if isinstance(item, str) and self.pos < len(self.pattern) and self.pattern[self.pos] == '-':
                if self.pos + 1 < len(self.pattern) and self.pattern[self.pos + 1] != ']':
                    self.pos += 1  # consume '-'
                    end_item = self._parse_class_item()
                    if isinstance(end_item, _ClassEsc):
                        raise ValueError("invalid range: class escape as range end")
                    if ord(item) > ord(end_item):
                        raise ValueError("invalid range: start > end")
                    items.append((item, end_item))
                    continue
            elif isinstance(item, _ClassEsc) and self.pos < len(self.pattern) and self.pattern[self.pos] == '-':
                if self.pos + 1 < len(self.pattern) and self.pattern[self.pos + 1] != ']':
                    raise ValueError("invalid range: class escape as range start")
            items.append(item)
        return _CharClass(negated, items)

    def _parse_class_item(self):
        if self.pos >= len(self.pattern):
            raise ValueError("unterminated character class")
        ch = self.pattern[self.pos]
        if ch == '\\':
            self.pos += 1
            if self.pos >= len(self.pattern):
                raise ValueError("backslash at end of character class")
            ech = self.pattern[self.pos]
            if ech in 'dDwWsS':
                self.pos += 1
                return _ClassEsc(ech)
            if ech == 'n':
                self.pos += 1
                return '\n'
            if ech == 't':
                self.pos += 1
                return '\t'
            if ech.isalpha() or ech.isdigit():
                raise ValueError(f"invalid escape in class \\{ech}")
            self.pos += 1
            return ech
        self.pos += 1
        return ch

# --- Matcher ---
def _match(node, pos, s, captures, success):
    if isinstance(node, _Lit):
        if pos < len(s) and s[pos] == node.ch:
            return success(pos + 1, captures)
        return None
    if isinstance(node, _Any):
        if pos < len(s) and s[pos] != '\n':
            return success(pos + 1, captures)
        return None
    if isinstance(node, _Start):
        if pos == 0:
            return success(pos, captures)
        return None
    if isinstance(node, _End):
        if pos == len(s) or (pos == len(s) - 1 and s[pos] == '\n'):
            return success(pos, captures)
        return None
    if isinstance(node, _ClassEsc):
        if pos < len(s) and _class_esc_match(node.kind, s[pos]):
            return success(pos + 1, captures)
        return None
    if isinstance(node, _CharClass):
        if pos < len(s) and _charclass_match(node, s[pos]):
            return success(pos + 1, captures)
        return None
    if isinstance(node, _Seq):
        return _match_seq(node.nodes, 0, pos, s, captures, success)
    if isinstance(node, _Alt):
        for branch in node.branches:
            saved = captures[:]
            result = _match(branch, pos, s, captures, success)
            if result is not None:
                return result
            captures[:] = saved
        return None
    if isinstance(node, _Group):
        saved = captures[:]
        def group_success(p, c, _idx=node.idx, _pos=pos):
            c[_idx] = (_pos, p)
            return success(p, c)
        result = _match(node.body, pos, s, captures, group_success)
        if result is not None:
            return result
        captures[:] = saved
        return None
    if isinstance(node, _NonCap):
        saved = captures[:]
        result = _match(node.body, pos, s, captures, success)
        if result is not None:
            return result
        captures[:] = saved
        return None
    if isinstance(node, _Quant):
        return _match_quant(node, pos, s, captures, success)
    raise ValueError("unknown node")

def _match_seq(nodes, idx, pos, s, captures, success):
    if idx >= len(nodes):
        return success(pos, captures)
    if idx == len(nodes) - 1:
        return _match(nodes[idx], pos, s, captures, success)
    def after(p, caps):
        return _match_seq(nodes, idx + 1, p, s, caps, success)
    return _match(nodes[idx], pos, s, captures, after)

def _match_quant(quant, pos, s, captures, success):
    if quant.lo == 0 and quant.hi == 0:
        return success(pos, captures)
    if _is_simple(quant.atom):
        return _match_quant_simple(quant, pos, s, captures, success)
    saved = captures[:]
    result = _quant_loop(quant, 0, None, pos, s, captures, success)
    if result is not None:
        return result
    captures[:] = saved
    return None

def _match_quant_simple(quant, pos, s, captures, success):
    # Forced iterations
    for _ in range(quant.lo):
        if not _match_simple(quant.atom, pos, s):
            return None
        pos += 1
    if quant.greedy:
        # Greedy: match as many as possible, then try stopping from max down to min
        extra = 0
        max_extra = (quant.hi - quant.lo) if quant.hi is not None else (len(s) - pos)
        while extra < max_extra and _match_simple(quant.atom, pos, s):
            pos += 1
            extra += 1
        for k in range(extra, -1, -1):
            p = pos - (extra - k)
            result = success(p, captures)
            if result is not None:
                return result
        return None
    else:
        # Lazy: try stopping first, then one more iteration at a time
        max_extra = (quant.hi - quant.lo) if quant.hi is not None else (len(s) - pos)
        for k in range(0, max_extra + 1):
            if k > 0:
                if not _match_simple(quant.atom, pos, s):
                    break
                pos += 1
            result = success(pos, captures)
            if result is not None:
                return result
        return None

def _quant_loop(quant, c, mark, pos, s, captures, success):
    if c < quant.lo:
        # Forced iteration
        def after(p, caps):
            return _quant_loop(quant, c + 1, mark, p, s, caps, success)
        return _match(quant.atom, pos, s, captures, after)
    if quant.greedy:
        can_iter = (quant.hi is None or c < quant.hi) and pos != mark
        if can_iter:
            saved2 = captures[:]
            def after(p, caps):
                return _quant_loop(quant, c + 1, pos, p, s, caps, success)
            result = _match(quant.atom, pos, s, captures, after)
            if result is not None:
                return result
            captures[:] = saved2
        return success(pos, captures)
    else:  # lazy
        result = success(pos, captures)
        if result is not None:
            return result
        if quant.hi is not None and c >= quant.hi:
            return None
        if pos == mark:
            return None
        saved2 = captures[:]
        def after(p, caps):
            return _quant_loop(quant, c + 1, pos, p, s, caps, success)
        result = _match(quant.atom, pos, s, captures, after)
        if result is not None:
            return result
        captures[:] = saved2
        return None

# --- Public API ---
class Match:
    def __init__(self, s, captures, whole_start, whole_end, num_groups):
        self._s = s
        self._captures = captures
        self._whole_start = whole_start
        self._whole_end = whole_end
        self._num_groups = num_groups

    def span(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > self._num_groups:
            raise IndexError(f"group index {n} out of range")
        if n == 0:
            return (self._whole_start, self._whole_end)
        cap = self._captures[n]
        if cap is None:
            return (-1, -1)
        return cap

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
            cap = self._captures[i]
            if cap is None:
                result.append(None)
            else:
                result.append(self._s[cap[0]:cap[1]])
        return tuple(result)


class Pattern:
    def __init__(self, ast, num_groups):
        self._ast = ast
        self._num_groups = num_groups

    def fullmatch(self, s):
        captures = [None] * (self._num_groups + 1)
        def success(pos, caps):
            if pos == len(s):
                return Match(s, caps[:], 0, pos, self._num_groups)
            return None
        return _match(self._ast, 0, s, captures, success)

    def search(self, s):
        for start in range(len(s) + 1):
            captures = [None] * (self._num_groups + 1)
            def success(pos, caps, _start=start):
                return Match(s, caps[:], _start, pos, self._num_groups)
            result = _match(self._ast, start, s, captures, success)
            if result is not None:
                return result
        return None


def compile(pattern):
    parser = _Parser(pattern)
    ast = parser.parse()
    return Pattern(ast, parser.num_groups)
