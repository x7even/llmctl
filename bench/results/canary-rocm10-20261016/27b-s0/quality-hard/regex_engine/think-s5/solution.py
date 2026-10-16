import sys

sys.setrecursionlimit(100000)


# ─── AST Nodes ───────────────────────────────────────────────────────────────

class _Lit:
    __slots__ = ('ch',)
    def __init__(self, ch):
        self.ch = ch

class _Dot:
    __slots__ = ()

class _Class:
    __slots__ = ('ranges',)
    def __init__(self, ranges):
        self.ranges = ranges

class _Anchor:
    __slots__ = ('kind',)
    def __init__(self, kind):
        self.kind = kind  # '^' or '$'

class _Group:
    __slots__ = ('gid', 'body')
    def __init__(self, gid, body):
        self.gid = gid
        self.body = body

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches):
        self.branches = branches

class _Quant:
    __slots__ = ('operand', 'lo', 'hi', 'lazy')
    def __init__(self, operand, lo, hi, lazy):
        self.operand = operand
        self.lo = lo
        self.hi = hi  # -1 for unbounded
        self.lazy = lazy


# ─── Helper Functions ────────────────────────────────────────────────────────

def _merge_ranges(ranges):
    if not ranges:
        return []
    ranges = sorted(ranges)
    merged = [list(ranges[0])]
    for s, e in ranges[1:]:
        if s <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]

def _complement(ranges):
    ranges = _merge_ranges(ranges)
    comp = []
    prev = 0
    for s, e in ranges:
        if s > prev:
            comp.append((prev, s - 1))
        prev = e + 1
    if prev <= 127:
        comp.append((prev, 127))
    return comp

def _class_match(node, ch):
    cp = ord(ch)
    for s, e in node.ranges:
        if s <= cp <= e:
            return True
    return False

_DIGIT_RANGES = [(48, 57)]
_WORD_RANGES = [(48, 57), (65, 90), (95, 95), (97, 122)]
_SPACE_RANGES = [(9, 9), (10, 10), (11, 11), (12, 12), (13, 13), (32, 32)]

def _escape_ranges(ch):
    if ch == 'd':
        return list(_DIGIT_RANGES)
    if ch == 'D':
        return _complement(_DIGIT_RANGES)
    if ch == 'w':
        return list(_WORD_RANGES)
    if ch == 'W':
        return _complement(_WORD_RANGES)
    if ch == 's':
        return list(_SPACE_RANGES)
    if ch == 'S':
        return _complement(_SPACE_RANGES)
    return []


# ─── Parser ──────────────────────────────────────────────────────────────────

class _Parser:
    def __init__(self, s):
        self.s = s
        self.pos = 0
        self.num_groups = 0

    def parse(self):
        nodes = self._parse_alt()
        if self.pos != len(self.s):
            raise ValueError(f"unexpected character at position {self.pos}")
        return nodes, self.num_groups

    def _parse_alt(self):
        branches = [self._parse_seq()]
        while self.pos < len(self.s) and self.s[self.pos] == '|':
            self.pos += 1
            branches.append(self._parse_seq())
        if len(branches) == 1:
            return branches[0]
        return [_Alt(branches)]

    def _parse_seq(self):
        nodes = []
        while self.pos < len(self.s) and self.s[self.pos] not in '|)':
            ch = self.s[self.pos]
            if ch in '*+?':
                raise ValueError("nothing to repeat")
            if ch == '{':
                raise ValueError("nothing to repeat")
            node = self._parse_atom()
            if self.pos < len(self.s) and self.s[self.pos] in '*+?{':
                if isinstance(node, _Anchor):
                    raise ValueError("cannot quantify anchor")
                lo, hi, lazy = self._parse_quant()
                node = _Quant(node, lo, hi, lazy)
                if self.pos < len(self.s) and self.s[self.pos] in '*+?{':
                    raise ValueError("quantifier after quantifier")
            nodes.append(node)
        return nodes

    def _parse_atom(self):
        ch = self.s[self.pos]
        if ch == '.':
            self.pos += 1
            return _Dot()
        if ch == '^':
            self.pos += 1
            return _Anchor('^')
        if ch == '$':
            self.pos += 1
            return _Anchor('$')
        if ch == '(':
            return self._parse_group()
        if ch == '[':
            return self._parse_class()
        if ch == '\\':
            return self._parse_escape()
        self.pos += 1
        return _Lit(ch)

    def _parse_group(self):
        self.pos += 1  # skip '('
        if self.pos < len(self.s) and self.s[self.pos] == '?':
            if self.pos + 1 >= len(self.s):
                raise ValueError("invalid group")
            if self.s[self.pos + 1] == ':':
                self.pos += 2
                body = self._parse_alt()
                if self.pos >= len(self.s) or self.s[self.pos] != ')':
                    raise ValueError("unclosed group")
                self.pos += 1
                return _Group(0, body)
            else:
                raise ValueError("invalid group syntax")
        else:
            self.num_groups += 1
            gid = self.num_groups
            body = self._parse_alt()
            if self.pos >= len(self.s) or self.s[self.pos] != ')':
                raise ValueError("unclosed group")
            self.pos += 1
            return _Group(gid, body)

    def _parse_class(self):
        self.pos += 1  # skip '['
        negated = False
        if self.pos < len(self.s) and self.s[self.pos] == '^':
            negated = True
            self.pos += 1

        ranges = []
        first = True

        while True:
            if self.pos >= len(self.s):
                raise ValueError("unclosed character class")
            ch = self.s[self.pos]
            if ch == ']':
                if first:
                    ranges.append((93, 93))
                    self.pos += 1
                    first = False
                    continue
                else:
                    self.pos += 1
                    break

            # Parse an item
            if ch == '\\':
                self.pos += 1
                if self.pos >= len(self.s):
                    raise ValueError("unexpected end in class")
                ech = self.s[self.pos]
                if ech in 'dDwWsS':
                    self.pos += 1
                    item_ranges = _escape_ranges(ech)
                    ranges.extend(item_ranges)
                    # After a class escape, - (not followed by ]) is an error
                    if self.pos < len(self.s) and self.s[self.pos] == '-':
                        if self.pos + 1 < len(self.s) and self.s[self.pos + 1] != ']':
                            raise ValueError("range with class escape")
                        ranges.append((45, 45))
                        self.pos += 1
                    first = False
                    continue
                elif ech == 'n':
                    self.pos += 1
                    item_start = item_end = 10
                elif ech == 't':
                    self.pos += 1
                    item_start = item_end = 9
                elif ech.isalnum():
                    raise ValueError(f"invalid escape in class: \\{ech}")
                else:
                    self.pos += 1
                    item_start = item_end = ord(ech)
            else:
                self.pos += 1
                item_start = item_end = ord(ch)

            first = False

            # Check for range
            if self.pos < len(self.s) and self.s[self.pos] == '-':
                if self.pos + 1 < len(self.s) and self.s[self.pos + 1] != ']':
                    # It's a range
                    self.pos += 1  # skip '-'
                    if self.pos >= len(self.s):
                        raise ValueError("unclosed character class")
                    ech = self.s[self.pos]
                    if ech == '\\':
                        self.pos += 1
                        if self.pos >= len(self.s):
                            raise ValueError("unexpected end in class")
                        ech2 = self.s[self.pos]
                        if ech2 in 'dDwWsS':
                            raise ValueError("range end cannot be class escape")
                        elif ech2 == 'n':
                            self.pos += 1
                            range_end = 10
                        elif ech2 == 't':
                            self.pos += 1
                            range_end = 9
                        elif ech2.isalnum():
                            raise ValueError(f"invalid escape in class: \\{ech2}")
                        else:
                            self.pos += 1
                            range_end = ord(ech2)
                    else:
                        self.pos += 1
                        range_end = ord(ech)

                    if item_start > range_end:
                        raise ValueError("invalid range in class")
                    ranges.append((item_start, range_end))
                else:
                    # '-' is literal (followed by ']')
                    ranges.append((45, 45))
                    self.pos += 1
            else:
                ranges.append((item_start, item_end))

        ranges = _merge_ranges(ranges)
        if negated:
            ranges = _complement(ranges)
        return _Class(ranges)

    def _parse_escape(self):
        self.pos += 1  # skip '\\'
        if self.pos >= len(self.s):
            raise ValueError("trailing backslash")
        ch = self.s[self.pos]
        if ch == 'd':
            self.pos += 1
            return _Class(list(_DIGIT_RANGES))
        if ch == 'D':
            self.pos += 1
            return _Class(_complement(_DIGIT_RANGES))
        if ch == 'w':
            self.pos += 1
            return _Class(list(_WORD_RANGES))
        if ch == 'W':
            self.pos += 1
            return _Class(_complement(_WORD_RANGES))
        if ch == 's':
            self.pos += 1
            return _Class(list(_SPACE_RANGES))
        if ch == 'S':
            self.pos += 1
            return _Class(_complement(_SPACE_RANGES))
        if ch == 'n':
            self.pos += 1
            return _Lit('\n')
        if ch == 't':
            self.pos += 1
            return _Lit('\t')
        if ch.isalnum():
            raise ValueError(f"invalid escape: \\{ch}")
        self.pos += 1
        return _Lit(ch)

    def _parse_quant(self):
        ch = self.s[self.pos]
        if ch == '*':
            self.pos += 1
            lazy = False
            if self.pos < len(self.s) and self.s[self.pos] == '?':
                self.pos += 1
                lazy = True
            return (0, -1, lazy)
        if ch == '+':
            self.pos += 1
            lazy = False
            if self.pos < len(self.s) and self.s[self.pos] == '?':
                self.pos += 1
                lazy = True
            return (1, -1, lazy)
        if ch == '?':
            self.pos += 1
            lazy = False
            if self.pos < len(self.s) and self.s[self.pos] == '?':
                self.pos += 1
                lazy = True
            return (0, 1, lazy)
        if ch == '{':
            self.pos += 1  # skip '{'
            m_start = self.pos
            while self.pos < len(self.s) and self.s[self.pos].isdigit():
                self.pos += 1
            m_end = self.pos
            if m_start == m_end:
                raise ValueError("invalid quantifier")
            m = int(self.s[m_start:m_end])

            if self.pos >= len(self.s):
                raise ValueError("unterminated quantifier")
            if self.s[self.pos] == '}':
                self.pos += 1
                lazy = False
                if self.pos < len(self.s) and self.s[self.pos] == '?':
                    self.pos += 1
                    lazy = True
                return (m, m, lazy)
            elif self.s[self.pos] == ',':
                self.pos += 1
                if self.pos < len(self.s) and self.s[self.pos] == '}':
                    self.pos += 1
                    lazy = False
                    if self.pos < len(self.s) and self.s[self.pos] == '?':
                        self.pos += 1
                        lazy = True
                    return (m, -1, lazy)
                else:
                    n_start = self.pos
                    while self.pos < len(self.s) and self.s[self.pos].isdigit():
                        self.pos += 1
                    n_end = self.pos
                    if n_start == n_end:
                        raise ValueError("invalid quantifier")
                    n = int(self.s[n_start:n_end])
                    if self.pos >= len(self.s) or self.s[self.pos] != '}':
                        raise ValueError("unterminated quantifier")
                    if m > n:
                        raise ValueError("m > n in quantifier")
                    self.pos += 1
                    lazy = False
                    if self.pos < len(self.s) and self.s[self.pos] == '?':
                        self.pos += 1
                        lazy = True
                    return (m, n, lazy)
            else:
                raise ValueError("invalid quantifier")
        raise ValueError("invalid quantifier")


# ─── Matcher ─────────────────────────────────────────────────────────────────

def _match(nodes, s, start, full, num_groups):
    N = len(s)
    caps = [None] * (num_groups + 1)
    result = _match_seq(nodes, 0, s, start, caps, full)
    if result is not None:
        end_pos, new_caps = result
        new_caps[0] = (start, end_pos)
        return (end_pos, new_caps)
    return None

def _match_seq(nodes, idx, s, pos, caps, full):
    N = len(s)
    while idx < len(nodes):
        node = nodes[idx]

        if isinstance(node, _Lit):
            if pos < N and s[pos] == node.ch:
                pos += 1
                idx += 1
            else:
                return None
        elif isinstance(node, _Dot):
            if pos < N and s[pos] != '\n':
                pos += 1
                idx += 1
            else:
                return None
        elif isinstance(node, _Class):
            if pos < N and _class_match(node, s[pos]):
                pos += 1
                idx += 1
            else:
                return None
        elif isinstance(node, _Anchor):
            if node.kind == '^':
                if pos != 0:
                    return None
                idx += 1
            else:  # '$'
                if not (pos == N or (pos == N - 1 and s[pos] == '\n')):
                    return None
                idx += 1
        elif isinstance(node, _Group):
            if node.gid > 0:
                caps = caps.copy()
                caps[node.gid] = (pos, None)
            result = _match_seq(node.body, 0, s, pos, caps, False)
            if result is None:
                return None
            new_pos, new_caps = result
            if node.gid > 0:
                new_caps[node.gid] = (pos, new_pos)
            pos = new_pos
            caps = new_caps
            idx += 1
        elif isinstance(node, _Alt):
            matched = False
            for branch in node.branches:
                saved_caps = caps.copy()
                result = _match_seq(branch, 0, s, pos, saved_caps, False)
                if result is not None:
                    pos, caps = result
                    matched = True
                    break
            if not matched:
                return None
            idx += 1
        elif isinstance(node, _Quant):
            return _match_quant(node, nodes, idx + 1, s, pos, caps, full)
        else:
            return None

    if full:
        if pos == N:
            return (pos, caps)
        return None
    return (pos, caps)

def _match_node(node, s, pos, caps):
    N = len(s)
    if isinstance(node, _Lit):
        if pos < N and s[pos] == node.ch:
            return (pos + 1, caps)
        return None
    elif isinstance(node, _Dot):
        if pos < N and s[pos] != '\n':
            return (pos + 1, caps)
        return None
    elif isinstance(node, _Class):
        if pos < N and _class_match(node, s[pos]):
            return (pos + 1, caps)
        return None
    elif isinstance(node, _Anchor):
        if node.kind == '^':
            if pos == 0:
                return (pos, caps)
            return None
        else:
            if pos == N or (pos == N - 1 and s[pos] == '\n'):
                return (pos, caps)
            return None
    elif isinstance(node, _Group):
        if node.gid > 0:
            caps = caps.copy()
            caps[node.gid] = (pos, None)
        result = _match_seq(node.body, 0, s, pos, caps, False)
        if result is None:
            return None
        new_pos, new_caps = result
        if node.gid > 0:
            new_caps[node.gid] = (pos, new_pos)
        return (new_pos, new_caps)
    elif isinstance(node, _Alt):
        for branch in node.branches:
            saved_caps = caps.copy()
            result = _match_seq(branch, 0, s, pos, saved_caps, False)
            if result is not None:
                return result
        return None
    else:
        return None

def _match_quant(node, rest_nodes, rest_idx, s, pos, caps, full):
    N = len(s)
    c = 0
    mark = None

    # Forced iterations
    while c < node.lo:
        result = _match_node(node.operand, s, pos, caps)
        if result is None:
            return None
        pos, caps = result
        c += 1

    if node.lazy:
        while True:
            result = _match_seq(rest_nodes, rest_idx, s, pos, caps, full)
            if result is not None:
                return result
            if (node.hi != -1 and c >= node.hi) or pos == mark:
                return None
            mark = pos
            result = _match_node(node.operand, s, pos, caps)
            if result is None:
                return None
            pos, caps = result
            c += 1
    else:
        # Greedy: run as many optional iterations as possible
        states = [(pos, caps.copy())]
        while (node.hi == -1 or c < node.hi) and pos != mark:
            mark = pos
            result = _match_node(node.operand, s, pos, caps)
            if result is None:
                break
            pos, caps = result
            c += 1
            states.append((pos, caps.copy()))

        # Try rest from most iterations to fewest
        for i in range(len(states) - 1, -1, -1):
            saved_pos, saved_caps = states[i]
            result = _match_seq(rest_nodes, rest_idx, s, saved_pos, saved_caps, full)
            if result is not None:
                return result
        return None


# ─── Public API ──────────────────────────────────────────────────────────────

class Match:
    __slots__ = ('_s', '_start', '_end', '_caps')

    def __init__(self, s, start, end, caps):
        self._s = s
        self._start = start
        self._end = end
        self._caps = caps

    def span(self, n=0):
        self._check(n)
        if n == 0:
            return (self._start, self._end)
        c = self._caps[n]
        return c if c is not None else (-1, -1)

    def start(self, n=0):
        self._check(n)
        if n == 0:
            return self._start
        c = self._caps[n]
        return c[0] if c is not None else -1

    def end(self, n=0):
        self._check(n)
        if n == 0:
            return self._end
        c = self._caps[n]
        return c[1] if c is not None else -1

    def group(self, n=0):
        self._check(n)
        if n == 0:
            return self._s[self._start:self._end]
        c = self._caps[n]
        return self._s[c[0]:c[1]] if c is not None else None

    def groups(self):
        return tuple(self.group(i) for i in range(1, len(self._caps)))

    def _check(self, n):
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError("group index must be an integer")
        if n < 0 or n >= len(self._caps):
            raise IndexError(f"no such group: {n}")


class Pattern:
    __slots__ = ('_nodes', '_num_groups')

    def __init__(self, nodes, num_groups):
        self._nodes = nodes
        self._num_groups = num_groups

    def fullmatch(self, s):
        result = _match(self._nodes, s, 0, True, self._num_groups)
        if result is not None:
            end_pos, caps = result
            return Match(s, 0, end_pos, caps)
        return None

    def search(self, s):
        for start in range(len(s) + 1):
            result = _match(self._nodes, s, start, False, self._num_groups)
            if result is not None:
                end_pos, caps = result
                return Match(s, start, end_pos, caps)
        return None


def compile(pattern):
    parser = _Parser(pattern)
    nodes, num_groups = parser.parse()
    return Pattern(nodes, num_groups)
