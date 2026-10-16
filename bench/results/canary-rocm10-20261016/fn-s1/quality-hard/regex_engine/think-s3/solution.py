"""
Backtracking-priority regular-expression engine (no re/regex/fnmatch/glob).
"""


# ─── AST Nodes ────────────────────────────────────────────────────────────────

class _Lit:
    __slots__ = ('ch',)
    def __init__(self, ch): self.ch = ch

class _Dot: pass
class _Start: pass
class _End: pass
class _Empty: pass

class _ClassNode:
    __slots__ = ('chars', 'ranges', 'escapes', 'negate')
    def __init__(self, chars, ranges, escapes, negate):
        self.chars = chars; self.ranges = ranges; self.escapes = escapes; self.negate = negate

class _Seq:
    __slots__ = ('children',)
    def __init__(self, children): self.children = children

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Group:
    __slots__ = ('idx', 'child')
    def __init__(self, idx, child): self.idx = idx; self.child = child

class _NonGroup:
    __slots__ = ('child',)
    def __init__(self, child): self.child = child

class _Quant:
    __slots__ = ('lo', 'hi', 'greedy', 'child')
    def __init__(self, lo, hi, greedy, child):
        self.lo = lo; self.hi = hi; self.greedy = greedy; self.child = child


# ─── Parser ───────────────────────────────────────────────────────────────────

_DIGITS = frozenset('0123456789')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_WS = frozenset(' \t\n\r\f\v')

class _Parser:
    def __init__(self, pattern):
        self.p = pattern
        self.pos = 0
        self.ngroups = 0

    def parse(self):
        node = self._alt()
        if self.pos != len(self.p):
            raise ValueError("unexpected ')'")
        return node

    def _alt(self):
        branches = [self._seq()]
        while self.pos < len(self.p) and self.p[self.pos] == '|':
            self.pos += 1
            branches.append(self._seq())
        return branches[0] if len(branches) == 1 else _Alt(branches)

    def _seq(self):
        items = []
        while self.pos < len(self.p) and self.p[self.pos] not in ('|', ')'):
            items.append(self._quantified())
        if not items:
            return _Empty()
        return items[0] if len(items) == 1 else _Seq(items)

    def _quantified(self):
        atom = self._atom()
        if self.pos < len(self.p) and self.p[self.pos] in ('*', '+', '?', '{'):
            if isinstance(atom, (_Start, _End)):
                raise ValueError("nothing to repeat")
            q = self._quantifier()
            if q is not None:
                return _Quant(q[0], q[1], q[2], atom)
        return atom

    def _quantifier(self):
        ch = self.p[self.pos]
        if ch == '*':
            self.pos += 1; return self._lazy(0, None)
        if ch == '+':
            self.pos += 1; return self._lazy(1, None)
        if ch == '?':
            self.pos += 1; return self._lazy(0, 1)
        if ch == '{':
            return self._brace()
        return None

    def _lazy(self, lo, hi):
        greedy = True
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            greedy = False; self.pos += 1
        return (lo, hi, greedy)

    def _brace(self):
        save = self.pos
        self.pos += 1
        ms = self.pos
        while self.pos < len(self.p) and self.p[self.pos] in _DIGITS:
            self.pos += 1
        if self.pos == ms:
            self.pos = save; raise ValueError("invalid quantifier")
        m = int(self.p[ms:self.pos])
        if self.pos < len(self.p) and self.p[self.pos] == '}':
            self.pos += 1; return self._lazy(m, m)
        if self.pos < len(self.p) and self.p[self.pos] == ',':
            self.pos += 1
            ns = self.pos
            while self.pos < len(self.p) and self.p[self.pos] in _DIGITS:
                self.pos += 1
            if self.pos < len(self.p) and self.p[self.pos] == '}':
                self.pos += 1
                if ns == self.pos:
                    return self._lazy(m, None)
                n = int(self.p[ns:self.pos])
                if m > n:
                    raise ValueError("min > max")
                return self._lazy(m, n)
        self.pos = save
        raise ValueError("invalid quantifier")

    def _atom(self):
        if self.pos >= len(self.p):
            return _Empty()
        ch = self.p[self.pos]
        if ch == '(':
            return self._group()
        if ch == '[':
            return self._class()
        if ch == '.':
            self.pos += 1; return _Dot()
        if ch == '^':
            self.pos += 1; return _Start()
        if ch == '$':
            self.pos += 1; return _End()
        if ch == '\\':
            return self._escape()
        if ch in ('*', '+', '?', '{'):
            raise ValueError("nothing to repeat")
        if ch == ')':
            raise ValueError("unbalanced parenthesis")
        self.pos += 1
        return _Lit(ch)

    def _group(self):
        self.pos += 1  # '('
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            self.pos += 1
            if self.pos >= len(self.p) or self.p[self.pos] != ':':
                raise ValueError("unsupported group syntax")
            self.pos += 1
            child = self._alt()
            if self.pos >= len(self.p) or self.p[self.pos] != ')':
                raise ValueError("unbalanced parenthesis")
            self.pos += 1
            return _NonGroup(child)
        self.ngroups += 1
        idx = self.ngroups
        child = self._alt()
        if self.pos >= len(self.p) or self.p[self.pos] != ')':
            raise ValueError("unbalanced parenthesis")
        self.pos += 1
        return _Group(idx, child)

    def _escape(self):
        self.pos += 1
        if self.pos >= len(self.p):
            raise ValueError("backslash at end of pattern")
        ch = self.p[self.pos]; self.pos += 1
        if ch in 'dDwWsS':
            return _ClassNode(set(), [], {ch}, False)
        if ch == 'n': return _Lit('\n')
        if ch == 't': return _Lit('\t')
        if not ch.isalnum():
            return _Lit(ch)
        raise ValueError(f"invalid escape \\{ch}")

    def _class(self):
        self.pos += 1  # '['
        negate = False
        if self.pos < len(self.p) and self.p[self.pos] == '^':
            negate = True; self.pos += 1
        chars = set(); ranges = []; escapes = set()
        first = True; prev_range = False
        while True:
            if self.pos >= len(self.p):
                raise ValueError("unterminated character class")
            if self.p[self.pos] == ']' and not first:
                self.pos += 1; break
            first = False
            item = self._class_item()
            if isinstance(item, str) and len(item) == 1:
                if (not prev_range and self.pos < len(self.p) and self.p[self.pos] == '-'
                        and self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']'):
                    self.pos += 1
                    item2 = self._class_item()
                    if not (isinstance(item2, str) and len(item2) == 1):
                        raise ValueError("invalid range")
                    if ord(item) > ord(item2):
                        raise ValueError("range start > end")
                    ranges.append((item, item2)); prev_range = True
                else:
                    chars.add(item); prev_range = False
            else:
                if (self.pos < len(self.p) and self.p[self.pos] == '-'
                        and self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']'):
                    raise ValueError("class escape cannot be range start")
                escapes.add(item); prev_range = False
        return _ClassNode(chars, ranges, escapes, negate)

    def _class_item(self):
        if self.pos >= len(self.p):
            raise ValueError("unterminated character class")
        ch = self.p[self.pos]
        if ch == '\\':
            self.pos += 1
            if self.pos >= len(self.p):
                raise ValueError("backslash at end")
            ch2 = self.p[self.pos]; self.pos += 1
            if ch2 in 'dDwWsS': return ch2
            if ch2 == 'n': return '\n'
            if ch2 == 't': return '\t'
            if not ch2.isalnum(): return ch2
            raise ValueError(f"invalid escape in class \\{ch2}")
        self.pos += 1
        return ch


# ─── Compiler (AST → instruction list) ────────────────────────────────────────

class _Compiler:
    def __init__(self, ngroups):
        self.ins = []
        self.ngroups = ngroups
        self.nmarks = 0
        self.ncounts = 0

    def compile(self, ast):
        self._emit(ast)
        self.ins.append(('match',))
        return self.ins

    def _emit(self, node):
        if isinstance(node, _Empty):
            return
        if isinstance(node, _Lit):
            self.ins.append(('char', node.ch)); return
        if isinstance(node, _Dot):
            self.ins.append(('dot',)); return
        if isinstance(node, _ClassNode):
            self.ins.append(('class', self._charset(node))); return
        if isinstance(node, _Start):
            self.ins.append(('start',)); return
        if isinstance(node, _End):
            self.ins.append(('end',)); return
        if isinstance(node, _Seq):
            for c in node.children: self._emit(c)
            return
        if isinstance(node, _Alt):
            self._emit_alt(node); return
        if isinstance(node, _Group):
            self.ins.append(('save', node.idx * 2))
            self._emit(node.child)
            self.ins.append(('save', node.idx * 2 + 1)); return
        if isinstance(node, _NonGroup):
            self._emit(node.child); return
        if isinstance(node, _Quant):
            self._emit_quant(node); return

    def _emit_alt(self, node):
        jumps = []
        for i, br in enumerate(node.branches):
            if i < len(node.branches) - 1:
                sp = len(self.ins)
                self.ins.append(None)
                self._emit(br)
                jp = len(self.ins)
                self.ins.append(('jump', 0))
                jumps.append(jp)
                self.ins[sp] = ('split', sp + 1, len(self.ins), False)
            else:
                self._emit(br)
        end = len(self.ins)
        for jp in jumps:
            self.ins[jp] = ('jump', end)

    def _emit_quant(self, node):
        lo, hi, greedy, child = node.lo, node.hi, node.greedy, node.child
        if lo == 0 and hi == 0:
            return
        ms = self.nmarks; self.nmarks += 1
        cs = self.ncounts; self.ncounts += 1
        self.ins.append(('init', ms, cs))
        for _ in range(lo):
            self._emit(child)
            self.ins.append(('inc', cs))
        if hi is None or hi > lo:
            loop = len(self.ins)
            if hi is not None:
                cc = len(self.ins); self.ins.append(None)
            cm = len(self.ins); self.ins.append(None)
            sp = len(self.ins); self.ins.append(None)
            body = len(self.ins)
            self.ins.append(('mark', ms))
            self._emit(child)
            self.ins.append(('inc', cs))
            self.ins.append(('jump', loop))
            stop = len(self.ins)
            if hi is not None:
                self.ins[cc] = ('check_count', cs, hi, cm, stop)
            self.ins[cm] = ('check_mark', ms, stop, sp)
            if greedy:
                self.ins[sp] = ('split', body, stop, True)
            else:
                self.ins[sp] = ('split', stop, body, True)

    def _charset(self, node):
        cs = set(node.chars)
        for lo, hi in node.ranges:
            for c in range(ord(lo), ord(hi) + 1):
                cs.add(chr(c))
        for e in node.escapes:
            if e == 'd': cs.update('0123456789')
            elif e == 'D': cs.update(chr(c) for c in range(128) if chr(c) not in '0123456789')
            elif e == 'w': cs.update(_WORD)
            elif e == 'W': cs.update(chr(c) for c in range(128) if chr(c) not in _WORD)
            elif e == 's': cs.update(_WS)
            elif e == 'S': cs.update(chr(c) for c in range(128) if chr(c) not in _WS)
        if node.negate:
            cs = set(chr(c) for c in range(128)) - cs
        return frozenset(cs)


# ─── Matcher (iterative VM with backtracking) ─────────────────────────────────

class _Matcher:
    __slots__ = ('s', 'n', 'ins', 'pc', 'pos', 'caps', 'marks', 'counts',
                 'trail', 'stack', 'memo', 'start', 'full')

    def __init__(self, s, ins, start, full, memo):
        self.s = s; self.n = len(s); self.ins = ins
        self.pc = 0; self.pos = start
        self.caps = {}; self.marks = {}; self.counts = {}
        self.trail = []; self.stack = []
        self.memo = memo; self.start = start; self.full = full

    def run(self):
        ins = self.ins; s = self.s; n = self.n
        pc = self.pc; pos = self.pos
        caps = self.caps; marks = self.marks; counts = self.counts
        trail = self.trail; stack = self.stack; memo = self.memo

        while True:
            op = ins[pc][0]

            if op == 'char':
                if pos < n and s[pos] == ins[pc][1]:
                    pos += 1; pc += 1
                else:
                    pc, pos = self._bt(stack, trail, caps, marks, counts, memo)
                    if pc is None: return None

            elif op == 'class':
                if pos < n and s[pos] in ins[pc][1]:
                    pos += 1; pc += 1
                else:
                    pc, pos = self._bt(stack, trail, caps, marks, counts, memo)
                    if pc is None: return None

            elif op == 'dot':
                if pos < n and s[pos] != '\n':
                    pos += 1; pc += 1
                else:
                    pc, pos = self._bt(stack, trail, caps, marks, counts, memo)
                    if pc is None: return None

            elif op == 'start':
                if pos == 0:
                    pc += 1
                else:
                    pc, pos = self._bt(stack, trail, caps, marks, counts, memo)
                    if pc is None: return None

            elif op == 'end':
                if pos == n or (pos == n - 1 and s[pos] == '\n'):
                    pc += 1
                else:
                    pc, pos = self._bt(stack, trail, caps, marks, counts, memo)
                    if pc is None: return None

            elif op == 'full_end':
                if pos == n:
                    pc += 1
                else:
                    pc, pos = self._bt(stack, trail, caps, marks, counts, memo)
                    if pc is None: return None

            elif op == 'save':
                slot = ins[pc][1]
                trail.append((slot, caps.get(slot), 'c'))
                caps[slot] = pos; pc += 1

            elif op == 'init':
                ms, cs = ins[pc][1], ins[pc][2]
                trail.append((ms, marks.get(ms), 'm'))
                marks[ms] = None
                trail.append((cs, counts.get(cs), 'n'))
                counts[cs] = 0; pc += 1

            elif op == 'mark':
                ms = ins[pc][1]
                trail.append((ms, marks.get(ms), 'm'))
                marks[ms] = pos; pc += 1

            elif op == 'inc':
                cs = ins[pc][1]
                old = counts.get(cs, 0)
                trail.append((cs, old, 'n'))
                counts[cs] = old + 1; pc += 1

            elif op == 'check_count':
                _, cs, hi, if_lt, if_ge = ins[pc]
                if counts.get(cs, 0) < hi:
                    pc = if_lt
                else:
                    pc = if_ge

            elif op == 'check_mark':
                _, ms, if_eq, if_ne = ins[pc]
                if marks.get(ms) == pos:
                    pc = if_eq
                else:
                    pc = if_ne

            elif op == 'split':
                _, a, b, is_q = ins[pc]
                if is_q and (pc, pos) in memo:
                    pc = b
                else:
                    if is_q:
                        stack.append(('QE', pc, pos))
                    stack.append((b, pos, len(trail)))
                    pc = a

            elif op == 'jump':
                pc = ins[pc][1]

            elif op == 'match':
                if self.full and pos != n:
                    pc, pos = self._bt(stack, trail, caps, marks, counts, memo)
                    if pc is None: return None
                else:
                    return (pos, dict(caps))

            elif op == 'fail':
                pc, pos = self._bt(stack, trail, caps, marks, counts, memo)
                if pc is None: return None

            else:
                raise RuntimeError(f"unknown op {op}")

    def _bt(self, stack, trail, caps, marks, counts, memo):
        while stack:
            entry = stack.pop()
            if entry[0] == 'QE':
                memo.add((entry[1], entry[2]))
                continue
            pc, pos, tl = entry
            while len(trail) > tl:
                slot, old, typ = trail.pop()
                if typ == 'c': caps[slot] = old
                elif typ == 'm': marks[slot] = old
                else: counts[slot] = old
            return pc, pos
        return None, None


# ─── Public API ───────────────────────────────────────────────────────────────

class Match:
    __slots__ = ('_s', '_start', '_end', '_caps', '_ng')

    def __init__(self, s, start, end, caps, ng):
        self._s = s; self._start = start; self._end = end; self._caps = caps; self._ng = ng

    def span(self, n=0):
        if n == 0: return (self._start, self._end)
        if not isinstance(n, int) or n < 1 or n > self._ng:
            raise IndexError(f"no such group: {n}")
        s = self._caps.get(2 * n); e = self._caps.get(2 * n + 1)
        if s is None or e is None: return (-1, -1)
        return (s, e)

    def start(self, n=0): return self.span(n)[0]
    def end(self, n=0): return self.span(n)[1]

    def group(self, n=0):
        if n == 0: return self._s[self._start:self._end]
        if not isinstance(n, int) or n < 1 or n > self._ng:
            raise IndexError(f"no such group: {n}")
        s = self._caps.get(2 * n); e = self._caps.get(2 * n + 1)
        if s is None or e is None: return None
        return self._s[s:e]

    def groups(self):
        return tuple(self.group(i) for i in range(1, self._ng + 1))


class Pattern:
    __slots__ = ('_ins', '_ng')

    def __init__(self, ins, ng):
        self._ins = ins; self._ng = ng

    def fullmatch(self, s):
        ins = self._ins + [('full_end',)]
        m = _Matcher(s, ins, 0, True, set())
        res = m.run()
        if res is None: return None
        end, caps = res
        return Match(s, 0, end, caps, self._ng)

    def search(self, s):
        memo = set()
        n = len(s)
        for start in range(n + 1):
            m = _Matcher(s, self._ins, start, False, memo)
            res = m.run()
            if res is not None:
                end, caps = res
                return Match(s, start, end, caps, self._ng)
        return None


def compile(pattern: str) -> Pattern:
    parser = _Parser(pattern)
    ast = parser.parse()
    compiler = _Compiler(parser.ngroups)
    ins = compiler.compile(ast)
    return Pattern(ins, parser.ngroups)
