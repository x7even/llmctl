import sys

# --- Constants ---
_ALL_ASCII = frozenset(chr(i) for i in range(128))
_DIGITS = frozenset('0123456789')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')
_NOT_DIGITS = _ALL_ASCII - _DIGITS
_NOT_WORD = _ALL_ASCII - _WORD
_NOT_SPACE = _ALL_ASCII - _SPACE

# --- AST Nodes ---
class _Lit:
    __slots__ = ('c',)
    def __init__(self, c): self.c = c
class _Dot: pass
class _Class:
    __slots__ = ('s',)
    def __init__(self, s): self.s = s
class _AnchorStart: pass
class _AnchorEnd: pass
class _Group:
    __slots__ = ('num', 'child')
    def __init__(self, num, child): self.num = num; self.child = child
class _NonCap:
    __slots__ = ('child',)
    def __init__(self, child): self.child = child
class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches
class _Concat:
    __slots__ = ('items',)
    def __init__(self, items): self.items = items
class _Quant:
    __slots__ = ('body', 'lo', 'hi', 'greedy')
    def __init__(self, body, lo, hi, greedy):
        self.body = body; self.lo = lo; self.hi = hi; self.greedy = greedy

# --- Parser ---
class _Parser:
    def __init__(self, pattern):
        self.p = pattern
        self.pos = 0
        self.ngroups = 0

    def _peek(self):
        return self.p[self.pos] if self.pos < len(self.p) else None

    def _advance(self):
        self.pos += 1

    def parse(self):
        result = self._parse_alt()
        if self.pos != len(self.p):
            raise ValueError("unexpected character")
        return result, self.ngroups

    def _parse_alt(self):
        branches = [self._parse_concat()]
        while self._peek() == '|':
            self._advance()
            branches.append(self._parse_concat())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _parse_concat(self):
        items = []
        while True:
            c = self._peek()
            if c is None or c in ('|', ')'):
                break
            if c in ('*', '+', '?', '{'):
                raise ValueError("nothing to repeat")
            items.append(self._parse_quantified())
        if len(items) == 0:
            return _Concat([])
        if len(items) == 1:
            return items[0]
        return _Concat(items)

    def _parse_quantified(self):
        atom = self._parse_atom()
        is_anchor = isinstance(atom, (_AnchorStart, _AnchorEnd))
        c = self._peek()
        if c in ('*', '+', '?', '{'):
            if is_anchor:
                raise ValueError("cannot quantify anchor")
            lo, hi = self._parse_quantifier()
            greedy = True
            if self._peek() == '?':
                self._advance()
                greedy = False
            nc = self._peek()
            if nc in ('*', '+', '?', '{'):
                raise ValueError("quantifier after quantifier")
            return _Quant(atom, lo, hi, greedy)
        return atom

    def _parse_quantifier(self):
        # self.pos points to one of *+?{
        c = self._peek()
        if c == '*':
            self._advance(); return (0, None)
        if c == '+':
            self._advance(); return (1, None)
        if c == '?':
            self._advance(); return (0, 1)
        # c == '{'
        self._advance()
        m = self._parse_digits()
        if m is None:
            raise ValueError("invalid quantifier")
        if self._peek() == '}':
            self._advance(); return (m, m)
        if self._peek() == ',':
            self._advance()
            if self._peek() == '}':
                self._advance(); return (m, None)
            n = self._parse_digits()
            if n is None:
                raise ValueError("invalid quantifier")
            if self._peek() == '}':
                self._advance()
                if m > n:
                    raise ValueError("m > n in quantifier")
                return (m, n)
            raise ValueError("invalid quantifier")
        raise ValueError("invalid quantifier")

    def _parse_digits(self):
        start = self.pos
        while self.pos < len(self.p) and self.p[self.pos].isdigit():
            self.pos += 1
        if self.pos == start:
            return None
        return int(self.p[start:self.pos])

    def _parse_atom(self):
        c = self._peek()
        if c is None:
            raise ValueError("unexpected end of pattern")
        if c == '.':
            self._advance(); return _Dot()
        if c == '^':
            self._advance(); return _AnchorStart()
        if c == '$':
            self._advance(); return _AnchorEnd()
        if c == '[':
            return self._parse_class()
        if c == '(':
            return self._parse_group()
        if c == '\\':
            return self._parse_escape()
        if c in ('*', '+', '?', '{', ')', '|'):
            raise ValueError("nothing to repeat")
        self._advance()
        return _Lit(c)

    def _parse_escape(self):
        self._advance()  # consume backslash
        if self.pos >= len(self.p):
            raise ValueError("backslash at end of pattern")
        c = self.p[self.pos]
        self._advance()
        if c == 'd': return _Class(_DIGITS)
        if c == 'D': return _Class(_NOT_DIGITS)
        if c == 'w': return _Class(_WORD)
        if c == 'W': return _Class(_NOT_WORD)
        if c == 's': return _Class(_SPACE)
        if c == 'S': return _Class(_NOT_SPACE)
        if c == 'n': return _Lit('\n')
        if c == 't': return _Lit('\t')
        if c.isalpha() or c.isdigit():
            raise ValueError("invalid escape")
        return _Lit(c)

    def _parse_group(self):
        self._advance()  # consume '('
        if self._peek() == '?' and self.pos + 1 < len(self.p) and self.p[self.pos + 1] == ':':
            self._advance(); self._advance()  # consume '?:'
            child = self._parse_alt()
            if self._peek() != ')':
                raise ValueError("unbalanced parentheses")
            self._advance()
            return _NonCap(child)
        if self._peek() == '?':
            raise ValueError("unsupported group syntax")
        self.ngroups += 1
        num = self.ngroups
        child = self._parse_alt()
        if self._peek() != ')':
            raise ValueError("unbalanced parentheses")
        self._advance()
        return _Group(num, child)

    def _parse_class(self):
        self._advance()  # consume '['
        negated = False
        if self._peek() == '^':
            negated = True
            self._advance()
        chars = set()
        first = True
        while True:
            c = self._peek()
            if c is None:
                raise ValueError("unterminated character class")
            if c == ']' and not first:
                self._advance()
                break
            first = False
            # Parse one item
            if c == '\\':
                item = self._parse_class_escape()
                if item is None:
                    raise ValueError("invalid class escape")
                if isinstance(item, frozenset):
                    # class escape like \d
                    if self._peek() == '-' and self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']':
                        raise ValueError("class escape in range")
                    chars |= item
                else:
                    # single char
                    lo_char = item
                    if self._peek() == '-' and self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']':
                        self._advance()  # consume '-'
                        hi_item = self._parse_class_single()
                        if hi_item is None:
                            raise ValueError("invalid range end")
                        if isinstance(hi_item, frozenset):
                            raise ValueError("class escape in range")
                        if ord(lo_char) > ord(hi_item):
                            raise ValueError("invalid range")
                        for ci in range(ord(lo_char), ord(hi_item) + 1):
                            chars.add(chr(ci))
                    else:
                        chars.add(lo_char)
            else:
                lo_char = self._parse_class_single()
                if lo_char is None:
                    raise ValueError("invalid class char")
                if self._peek() == '-' and self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']':
                    self._advance()  # consume '-'
                    hi_item = self._parse_class_single()
                    if hi_item is None:
                        raise ValueError("invalid range end")
                    if isinstance(hi_item, frozenset):
                        raise ValueError("class escape in range")
                    if ord(lo_char) > ord(hi_item):
                        raise ValueError("invalid range")
                    for ci in range(ord(lo_char), ord(hi_item) + 1):
                        chars.add(chr(ci))
                else:
                    chars.add(lo_char)
        result_set = frozenset(chars)
        if negated:
            result_set = _ALL_ASCII - result_set
        return _Class(result_set)

    def _parse_class_escape(self):
        self._advance()  # consume backslash
        if self.pos >= len(self.p):
            raise ValueError("backslash at end of class")
        c = self.p[self.pos]
        self._advance()
        if c == 'd': return _DIGITS
        if c == 'D': return _NOT_DIGITS
        if c == 'w': return _WORD
        if c == 'W': return _NOT_WORD
        if c == 's': return _SPACE
        if c == 'S': return _NOT_SPACE
        if c == 'n': return '\n'
        if c == 't': return '\t'
        if c.isalpha() or c.isdigit():
            raise ValueError("invalid class escape")
        return c

    def _parse_class_single(self):
        c = self._peek()
        if c is None:
            return None
        if c == ']':
            return None
        if c == '\\':
            return self._parse_class_escape()
        self._advance()
        return c

# --- Compiler ---
def _compile_ast(ast):
    instrs = []
    slot_count = [0]

    def emit(instr):
        instrs.append(instr)
        return len(instrs) - 1

    def next_idx():
        slot_count[0] += 1
        return slot_count[0] - 1

    _NEXT_IDX = {
        'char': 2, 'class': 2, 'any': 1,
        'assert_start': 1, 'assert_end': 1,
        'mark': 2, 'mark_end': 2, 'jump': 1,
        'init': 2, 'repeat': 5,
    }

    def patch(idx, target):
        op = instrs[idx][0]
        ni = _NEXT_IDX[op]
        instrs[idx][ni] = target

    def compile_node(node):
        if isinstance(node, _Lit):
            idx = emit(['char', node.c, -1])
            return (idx, [idx])
        if isinstance(node, _Dot):
            idx = emit(['any', -1])
            return (idx, [idx])
        if isinstance(node, _Class):
            idx = emit(['class', node.s, -1])
            return (idx, [idx])
        if isinstance(node, _AnchorStart):
            idx = emit(['assert_start', -1])
            return (idx, [idx])
        if isinstance(node, _AnchorEnd):
            idx = emit(['assert_end', -1])
            return (idx, [idx])
        if isinstance(node, _Concat):
            if not node.items:
                idx = emit(['jump', -1])
                return (idx, [idx])
            first_start = None
            cur_exits = None
            for item in node.items:
                s, e = compile_node(item)
                if first_start is None:
                    first_start = s
                else:
                    for ex in cur_exits:
                        patch(ex, s)
                cur_exits = e
            return (first_start, cur_exits)
        if isinstance(node, _Alt):
            if len(node.branches) == 1:
                return compile_node(node.branches[0])
            branch_idx = emit(['branch', -1, -1])
            s1, e1 = compile_node(node.branches[0])
            rest = _Alt(node.branches[1:])
            s2, e2 = compile_node(rest)
            instrs[branch_idx][1] = s1
            instrs[branch_idx][2] = s2
            return (branch_idx, e1 + e2)
        if isinstance(node, _Group):
            mark_idx = emit(['mark', node.num, -1])
            s, e = compile_node(node.child)
            patch(mark_idx, s)
            end_idx = emit(['mark_end', node.num, -1])
            for ex in e:
                patch(ex, end_idx)
            return (mark_idx, [end_idx])
        if isinstance(node, _NonCap):
            return compile_node(node.child)
        if isinstance(node, _Quant):
            if node.lo == 0 and node.hi == 0:
                idx = emit(['jump', -1])
                return (idx, [idx])
            slot = next_idx()
            init_idx = emit(['init', slot, -1])
            repeat_idx = emit(['repeat', -1, node.lo, node.hi, node.greedy, -1, slot])
            instrs[init_idx][2] = repeat_idx
            body_start = len(instrs)
            s, e = compile_node(node.body)
            loop_idx = emit(['repeat_loop', slot, repeat_idx])
            for ex in e:
                patch(ex, loop_idx)
            instrs[repeat_idx][1] = body_start
            return (init_idx, [repeat_idx])
        raise ValueError("unknown node type")

    start, exits = compile_node(ast)
    success_idx = emit(['success'])
    for ex in exits:
        patch(ex, success_idx)
    return instrs, slot_count[0]

# --- Matcher ---
def _match(instrs, s, start, full, num_groups, num_slots):
    n = len(s)
    captures = [(-1, -1)] * (num_groups + 1)
    slots = [(0, -1)] * num_slots
    stack = []
    memo = set()
    pc = 0
    pos = start

    while True:
        instr = instrs[pc]
        op = instr[0]

        if op == 'char':
            if pos < n and s[pos] == instr[1]:
                pos += 1
                pc = instr[2]
                continue
        elif op == 'class':
            if pos < n and s[pos] in instr[1]:
                pos += 1
                pc = instr[2]
                continue
        elif op == 'any':
            if pos < n and s[pos] != '\n':
                pos += 1
                pc = instr[1]
                continue
        elif op == 'assert_start':
            if pos == 0:
                pc = instr[1]
                continue
        elif op == 'assert_end':
            if pos == n or (pos == n - 1 and s[pos] == '\n'):
                pc = instr[1]
                continue
        elif op == 'mark':
            g = instr[1]
            stack.append(('mark_undo', g, captures[g]))
            captures[g] = (pos, -1)
            pc = instr[2]
            continue
        elif op == 'mark_end':
            g = instr[1]
            stack.append(('mark_end_undo', g, captures[g]))
            captures[g] = (captures[g][0], pos)
            pc = instr[2]
            continue
        elif op == 'jump':
            pc = instr[1]
            continue
        elif op == 'branch':
            stack.append(('branch', instr[2], pos, captures[:], slots[:]))
            pc = instr[1]
            continue
        elif op == 'init':
            slot_id = instr[1]
            slots[slot_id] = (0, -1)
            pc = instr[2]
            continue
        elif op == 'repeat':
            body_start, lo, hi, greedy, next_pc, slot_id = instr[1], instr[2], instr[3], instr[4], instr[5], instr[6]
            c, mark = slots[slot_id]
            mark_flag = 1 if (mark == pos) else 0
            if hi is None:
                memo_key = (pc, pos, mark_flag)
            else:
                memo_key = (pc, pos, c, mark_flag)
            if memo_key in memo:
                pass  # fall through to backtrack
            else:
                stack.append(('enter_repeat', pc, pos, c, mark_flag, hi is None))
                if c < lo:
                    pc = body_start
                    continue
                if greedy:
                    if (hi is None or c < hi) and pos != mark:
                        slots[slot_id] = (c, pos)
                        stack.append(('greedy_repeat', next_pc, pos, captures[:], slots[:]))
                        pc = body_start
                        continue
                    else:
                        pc = next_pc
                        continue
                else:
                    stack.append(('lazy_repeat', body_start, pos, c, mark, hi, slot_id, captures[:], slots[:]))
                    pc = next_pc
                    continue
        elif op == 'repeat_loop':
            slot_id, repeat_pc = instr[1], instr[2]
            c, mark = slots[slot_id]
            slots[slot_id] = (c + 1, mark)
            pc = repeat_pc
            continue
        elif op == 'success':
            if full and pos != n:
                pass  # fall through to backtrack
            else:
                captures[0] = (start, pos)
                return captures

        # Backtrack
        found = False
        while stack:
            frame = stack.pop()
            ft = frame[0]
            if ft == 'mark_undo' or ft == 'mark_end_undo':
                captures[frame[1]] = frame[2]
            elif ft == 'enter_repeat':
                if frame[5]:  # unbounded
                    memo.add((frame[1], frame[2], frame[4]))
                else:
                    memo.add((frame[1], frame[2], frame[3], frame[4]))
            elif ft == 'branch':
                pc, pos = frame[1], frame[2]
                captures[:] = frame[3]
                slots[:] = frame[4]
                found = True
                break
            elif ft == 'greedy_repeat':
                pc, pos = frame[1], frame[2]
                captures[:] = frame[3]
                slots[:] = frame[4]
                found = True
                break
            elif ft == 'lazy_repeat':
                body_start, pos, c, mark, hi, slot_id = frame[1], frame[2], frame[3], frame[4], frame[5], frame[6]
                captures[:] = frame[7]
                slots[:] = frame[8]
                if (hi is not None and c >= hi) or pos == mark:
                    continue
                slots[slot_id] = (c, pos)
                pc = body_start
                found = True
                break
        if not found:
            return None

# --- Public API ---
class Match:
    def __init__(self, captures, s, num_groups):
        self._captures = captures
        self._s = s
        self._ng = num_groups

    def span(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError("no such group")
        return self._captures[n]

    def start(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError("no such group")
        return self._captures[n][0]

    def end(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError("no such group")
        return self._captures[n][1]

    def group(self, n=0):
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError("no such group")
        s, e = self._captures[n]
        if s == -1:
            return None
        return self._s[s:e]

    def groups(self):
        result = []
        for i in range(1, self._ng + 1):
            s, e = self._captures[i]
            if s == -1:
                result.append(None)
            else:
                result.append(self._s[s:e])
        return tuple(result)


class Pattern:
    def __init__(self, instrs, num_groups, num_slots):
        self._instrs = instrs
        self._ng = num_groups
        self._ns = num_slots

    def fullmatch(self, s):
        result = _match(self._instrs, s, 0, True, self._ng, self._ns)
        if result is not None:
            return Match(result, s, self._ng)
        return None

    def search(self, s):
        for start in range(len(s) + 1):
            result = _match(self._instrs, s, start, False, self._ng, self._ns)
            if result is not None:
                return Match(result, s, self._ng)
        return None


def compile(pattern):
    parser = _Parser(pattern)
    ast, num_groups = parser.parse()
    instrs, num_slots = _compile_ast(ast)
    return Pattern(instrs, num_groups, num_slots)
