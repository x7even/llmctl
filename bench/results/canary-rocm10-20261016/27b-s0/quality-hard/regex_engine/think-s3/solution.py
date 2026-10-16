import sys
sys.setrecursionlimit(200000)


# ─── AST Nodes ───────────────────────────────────────────────────────────────

class _Lit:
    __slots__ = ('ch',)
    def __init__(self, ch): self.ch = ch

class _Dot:
    __slots__ = ()

class _Class:
    __slots__ = ('negated', 'chars')
    def __init__(self, negated, chars): self.negated = negated; self.chars = frozenset(chars)

class _Group:
    __slots__ = ('idx', 'body')
    def __init__(self, idx, body): self.idx = idx; self.body = body

class _NonGroup:
    __slots__ = ('body',)
    def __init__(self, body): self.body = body

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Seq:
    __slots__ = ('items',)
    def __init__(self, items): self.items = items

class _Quant:
    __slots__ = ('body', 'lo', 'hi', 'lazy')
    def __init__(self, body, lo, hi, lazy):
        self.body = body; self.lo = lo; self.hi = hi; self.lazy = lazy

class _AnchorStart:
    __slots__ = ()

class _AnchorEnd:
    __slots__ = ()


# ─── Parser ──────────────────────────────────────────────────────────────────

def _parse_pattern(pattern: str):
    pos = 0
    n = len(pattern)
    num_groups = 0

    def parse_escape():
        nonlocal pos
        pos += 1  # skip backslash
        if pos >= n:
            raise ValueError("Trailing backslash in pattern")
        c = pattern[pos]
        if c in 'dDwWsS':
            pos += 1
            return ('class_escape', c)
        elif c == 'n':
            pos += 1
            return ('char', '\n')
        elif c == 't':
            pos += 1
            return ('char', '\t')
        elif c.isalpha() or c.isdigit():
            raise ValueError(f"Invalid escape \\{c}")
        else:
            pos += 1
            return ('char', c)

    def parse_class_body_item():
        nonlocal pos
        if pos >= n:
            raise ValueError("Unclosed character class")
        c = pattern[pos]
        if c == '\\':
            pos += 1
            if pos >= n:
                raise ValueError("Trailing backslash in character class")
            c2 = pattern[pos]
            if c2 in 'dDwWsS':
                pos += 1
                return ('class_escape', c2)
            elif c2 == 'n':
                pos += 1
                return ('char', '\n')
            elif c2 == 't':
                pos += 1
                return ('char', '\t')
            elif c2.isalpha() or c2.isdigit():
                raise ValueError(f"Invalid escape \\{c2} in character class")
            else:
                pos += 1
                return ('char', c2)
        else:
            pos += 1
            return ('char', c)

    def parse_class():
        nonlocal pos
        # pos is at '['
        pos += 1  # skip '['
        negated = False
        if pos < n and pattern[pos] == '^':
            negated = True
            pos += 1
        chars = set()
        # Handle leading ] as literal
        if pos < n and pattern[pos] == ']':
            chars.add(']')
            pos += 1
        while pos < n and pattern[pos] != ']':
            item = parse_class_body_item()
            if item[0] == 'class_escape':
                # Class escape: add all chars in the set
                chars |= _expand_class_escape(item[1])
                # Check for range: class-escape followed by - and not ]
                if pos < n and pattern[pos] == '-' and pos + 1 < n and pattern[pos + 1] != ']':
                    raise ValueError("Range with class escape")
            else:
                ch = item[1]
                # Check for range
                if pos < n and pattern[pos] == '-' and pos + 1 < n and pattern[pos + 1] != ']':
                    pos += 1  # skip '-'
                    end_item = parse_class_body_item()
                    if end_item[0] == 'class_escape':
                        raise ValueError("Range end cannot be class escape")
                    end_ch = end_item[1]
                    if ord(ch) > ord(end_ch):
                        raise ValueError(f"Invalid range {ch}-{end_ch}")
                    for code in range(ord(ch), ord(end_ch) + 1):
                        chars.add(chr(code))
                else:
                    chars.add(ch)
        if pos >= n:
            raise ValueError("Unclosed character class")
        pos += 1  # skip ']'
        return negated, chars

    def _expand_class_escape(c):
        if c == 'd': return set('0123456789')
        if c == 'D': return set(chr(i) for i in range(128)) - set('0123456789')
        if c == 'w': return set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
        if c == 'W': return set(chr(i) for i in range(128)) - set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
        if c == 's': return set(' \t\n\r\f\v')
        if c == 'S': return set(chr(i) for i in range(128)) - set(' \t\n\r\f\v')
        return set()

    def parse_quantifier():
        nonlocal pos
        c = pattern[pos]
        if c == '*':
            pos += 1
            lazy = pos < n and pattern[pos] == '?'
            if lazy: pos += 1
            return (0, None, lazy)
        elif c == '+':
            pos += 1
            lazy = pos < n and pattern[pos] == '?'
            if lazy: pos += 1
            return (1, None, lazy)
        elif c == '?':
            pos += 1
            lazy = pos < n and pattern[pos] == '?'
            if lazy: pos += 1
            return (0, 1, lazy)
        elif c == '{':
            # Check if it's a valid quantifier or literal
            save = pos
            pos += 1
            # Parse m
            m_str = ''
            while pos < n and pattern[pos].isdigit():
                m_str += pattern[pos]
                pos += 1
            if not m_str:
                # Not a valid quantifier, treat { as literal
                pos = save
                return None
            m = int(m_str)
            if pos < n and pattern[pos] == '}':
                pos += 1
                lazy = pos < n and pattern[pos] == '?'
                if lazy: pos += 1
                return (m, m, lazy)
            elif pos < n and pattern[pos] == ',':
                pos += 1
                n_str = ''
                while pos < n and pattern[pos].isdigit():
                    n_str += pattern[pos]
                    pos += 1
                if n_str:
                    nn = int(n_str)
                    if pos >= n or pattern[pos] != '}':
                        raise ValueError("Invalid quantifier")
                    pos += 1
                    if m > nn:
                        raise ValueError(f"Invalid quantifier {{ {m},{nn} }}")
                    lazy = pos < n and pattern[pos] == '?'
                    if lazy: pos += 1
                    return (m, nn, lazy)
                else:
                    if pos >= n or pattern[pos] != '}':
                        raise ValueError("Invalid quantifier")
                    pos += 1
                    lazy = pos < n and pattern[pos] == '?'
                    if lazy: pos += 1
                    return (m, None, lazy)
            else:
                raise ValueError("Invalid quantifier")
        return None

    def parse_atom():
        nonlocal pos, num_groups
        c = pattern[pos]
        if c == '.':
            pos += 1
            return _Dot()
        elif c == '\\':
            result = parse_escape()
            if result[0] == 'class_escape':
                return _Class(False, _expand_class_escape(result[1]))
            else:
                return _Lit(result[1])
        elif c == '[':
            negated, chars = parse_class()
            return _Class(negated, chars)
        elif c == '(':
            pos += 1
            if pos < n and pattern[pos] == '?':
                if pos + 1 < n and pattern[pos + 1] == ':':
                    pos += 2
                    body = parse_alt()
                    if pos >= n or pattern[pos] != ')':
                        raise ValueError("Unclosed non-capturing group")
                    pos += 1
                    return _NonGroup(body)
                else:
                    raise ValueError(f"Invalid group syntax at position {pos}")
            else:
                num_groups += 1
                idx = num_groups
                body = parse_alt()
                if pos >= n or pattern[pos] != ')':
                    raise ValueError("Unclosed group")
                pos += 1
                return _Group(idx, body)
        elif c == ')':
            raise ValueError("Unmatched ')'")
        else:
            pos += 1
            return _Lit(c)

    def parse_quantified_atom():
        nonlocal pos
        atom = parse_atom()
        if pos < n:
            c = pattern[pos]
            if c in '*+?{':
                q = parse_quantifier()
                if q is not None:
                    lo, hi, lazy = q
                    return _Quant(atom, lo, hi, lazy)
        return atom

    def parse_seq():
        nonlocal pos
        items = []
        while pos < n:
            c = pattern[pos]
            if c in ')|':
                break
            if c == '^':
                items.append(_AnchorStart())
                pos += 1
            elif c == '$':
                items.append(_AnchorEnd())
                pos += 1
            else:
                items.append(parse_quantified_atom())
        if not items:
            return _Seq([])
        if len(items) == 1:
            return items[0]
        return _Seq(items)

    def parse_alt():
        nonlocal pos
        branches = [parse_seq()]
        while pos < n and pattern[pos] == '|':
            pos += 1
            branches.append(parse_seq())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    ast = parse_alt()
    if pos != n:
        raise ValueError(f"Unexpected character at position {pos}")
    return ast, num_groups


# ─── Matcher ─────────────────────────────────────────────────────────────────

def _match_node(node, pos, s, caps):
    """Generator yielding (end_pos, caps_list) in priority order."""
    t = type(node)
    if t is _Lit:
        if pos < len(s) and s[pos] == node.ch:
            yield (pos + 1, caps)
    elif t is _Dot:
        if pos < len(s) and s[pos] != '\n':
            yield (pos + 1, caps)
    elif t is _Class:
        if pos < len(s):
            ch = s[pos]
            if (ch in node.chars) != node.negated:
                yield (pos + 1, caps)
    elif t is _AnchorStart:
        if pos == 0:
            yield (pos, caps)
    elif t is _AnchorEnd:
        if pos == len(s) or (pos == len(s) - 1 and s[pos] == '\n'):
            yield (pos, caps)
    elif t is _Group:
        for (ep, nc) in _match_node(node.body, pos, s, caps):
            nc2 = list(nc)
            nc2[node.idx] = (pos, ep)
            yield (ep, nc2)
    elif t is _NonGroup:
        yield from _match_node(node.body, pos, s, caps)
    elif t is _Alt:
        for br in node.branches:
            yield from _match_node(br, pos, s, caps)
    elif t is _Seq:
        yield from _match_seq(node.items, pos, s, caps)
    elif t is _Quant:
        yield from _match_quant(node, pos, s, caps)


def _match_seq(items, pos, s, caps):
    if not items:
        yield (pos, caps)
        return
    first = items[0]
    rest = items[1:]
    for (np, nc) in _match_node(first, pos, s, caps):
        yield from _match_seq(rest, np, s, nc)


def _match_quant(node, pos, s, caps):
    """Match a quantified node. Yields (end_pos, caps) in priority order."""
    body = node.body
    lo = node.lo
    hi = node.hi
    lazy = node.lazy
    seen = set()

    def _body_matches(p, c):
        """Collect body matches at position p with captures c, sorted by (length, priority)."""
        matches = []
        for i, (ep, nc) in enumerate(_match_node(body, p, s, c)):
            matches.append((ep - p, i, ep, nc))
        matches.sort(key=lambda x: (x[0], x[1]))
        return [(ep, nc) for (_, _, ep, nc) in matches]

    def dfs(c, cur_pos, cur_caps, mark):
        if c < lo:
            # Forced iteration
            for (np, nc) in _body_matches(cur_pos, cur_caps):
                yield from dfs(c + 1, np, nc, mark)
            return
        # c >= lo
        if lazy:
            # Try to stop first
            if cur_pos not in seen:
                seen.add(cur_pos)
                yield (cur_pos, cur_caps)
            # Then try one more
            if not (hi is not None and c >= hi) and cur_pos != mark:
                new_mark = cur_pos
                for (np, nc) in _body_matches(cur_pos, cur_caps):
                    yield from dfs(c + 1, np, nc, new_mark)
        else:
            # Greedy: try one more first
            if (hi is None or c < hi) and cur_pos != mark:
                new_mark = cur_pos
                for (np, nc) in _body_matches(cur_pos, cur_caps):
                    yield from dfs(c + 1, np, nc, new_mark)
            # Then stop
            if cur_pos not in seen:
                seen.add(cur_pos)
                yield (cur_pos, cur_caps)

    yield from dfs(0, pos, caps, None)


# ─── Public API ──────────────────────────────────────────────────────────────

class Match:
    __slots__ = ('_s', '_start', '_end', '_caps', '_ng')

    def __init__(self, s, start, end, caps, num_groups):
        self._s = s
        self._start = start
        self._end = end
        self._caps = caps
        self._ng = num_groups

    def span(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError("group index out of range")
        if n == 0:
            return (self._start, self._end)
        c = self._caps[n]
        if c is None:
            return (-1, -1)
        return c

    def start(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError("group index out of range")
        if n == 0:
            return self._start
        c = self._caps[n]
        if c is None:
            return -1
        return c[0]

    def end(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError("group index out of range")
        if n == 0:
            return self._end
        c = self._caps[n]
        if c is None:
            return -1
        return c[1]

    def group(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError("group index out of range")
        if n == 0:
            return self._s[self._start:self._end]
        c = self._caps[n]
        if c is None:
            return None
        return self._s[c[0]:c[1]]

    def groups(self):
        return tuple(self.group(i) for i in range(1, self._ng + 1))


class Pattern:
    __slots__ = ('_ast', '_ng')

    def __init__(self, ast, num_groups):
        self._ast = ast
        self._ng = num_groups

    def fullmatch(self, s):
        caps = [None] * (self._ng + 1)
        for (end, c) in _match_seq(self._ast, 0, s, caps):
            if end == len(s):
                return Match(s, 0, end, c, self._ng)
        return None

    def search(self, s):
        for start in range(len(s) + 1):
            caps = [None] * (self._ng + 1)
            for (end, c) in _match_seq(self._ast, start, s, caps):
                return Match(s, start, end, c, self._ng)
        return None


def compile(pattern: str) -> Pattern:
    ast, ng = _parse_pattern(pattern)
    return Pattern(ast, ng)
