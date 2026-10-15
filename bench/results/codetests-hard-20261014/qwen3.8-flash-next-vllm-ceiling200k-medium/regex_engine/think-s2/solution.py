def compile(pattern):
    parser = _Parser(pattern)
    ast = parser.parse()
    compiler = _Compiler()
    instructions = compiler.compile(ast)
    return Pattern(instructions, parser.num_groups, compiler.num_quants)


class Pattern:
    def __init__(self, instructions, num_groups, num_quants):
        self._instrs = instructions
        self._ng = num_groups
        self._nq = num_quants

    def fullmatch(self, s):
        result = _vm(self._instrs, s, 0, self._ng, self._nq, True, set())
        if result is None:
            return None
        return Match(s, result[0], result[1], result[2], self._ng)

    def search(self, s):
        memo = set()
        for start in range(len(s) + 1):
            result = _vm(self._instrs, s, start, self._ng, self._nq, False, memo)
            if result is not None:
                return Match(s, result[0], result[1], result[2], self._ng)
        return None


class Match:
    def __init__(self, s, start, end, captures, num_groups):
        self._s = s
        self._start = start
        self._end = end
        self._captures = captures
        self._ng = num_groups

    def span(self, n=0):
        if n == 0:
            return (self._start, self._end)
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError(n)
        c = self._captures[n - 1]
        if c is None:
            return (-1, -1)
        return c

    def start(self, n=0):
        return self.span(n)[0]

    def end(self, n=0):
        return self.span(n)[1]

    def group(self, n=0):
        if n == 0:
            return self._s[self._start:self._end]
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError(n)
        c = self._captures[n - 1]
        if c is None:
            return None
        return self._s[c[0]:c[1]]

    def groups(self):
        result = []
        for i in range(self._ng):
            c = self._captures[i]
            if c is None:
                result.append(None)
            else:
                result.append(self._s[c[0]:c[1]])
        return tuple(result)


# ─── Parser ───────────────────────────────────────────────────────────────────

_DIGITS = frozenset('0123456789')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')

_ESCAPE_CLASSES = {
    'd': (_DIGITS, False), 'D': (_DIGITS, True),
    'w': (_WORD, False), 'W': (_WORD, True),
    's': (_SPACE, False), 'S': (_SPACE, True),
}


class _Lit:
    __slots__ = ('c',)
    def __init__(self, c): self.c = c

class _Any:
    __slots__ = ()

class _Cls:
    __slots__ = ('chars', 'neg')
    def __init__(self, chars, neg): self.chars = chars; self.neg = neg

class _As:
    __slots__ = ()

class _Ae:
    __slots__ = ()

class _Grp:
    __slots__ = ('num', 'child')
    def __init__(self, num, child): self.num = num; self.child = child

class _NCG:
    __slots__ = ('child',)
    def __init__(self, child): self.child = child

class _Seq:
    __slots__ = ('items',)
    def __init__(self, items): self.items = items

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Quant:
    __slots__ = ('child', 'lo', 'hi', 'greedy')
    def __init__(self, child, lo, hi, greedy): self.child = child; self.lo = lo; self.hi = hi; self.greedy = greedy


class _Parser:
    def __init__(self, pattern):
        self.pat = pattern
        self.pos = 0
        self.num_groups = 0

    def parse(self):
        node = self._alt()
        if self.pos < len(self.pat):
            if self.pat[self.pos] == ')':
                raise ValueError("unbalanced parenthesis")
            raise ValueError("unexpected character")
        return node

    def _alt(self):
        branches = [self._seq()]
        while self.pos < len(self.pat) and self.pat[self.pos] == '|':
            self.pos += 1
            branches.append(self._seq())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _seq(self):
        items = []
        while self.pos < len(self.pat) and self.pat[self.pos] not in ('|', ')'):
            items.append(self._quantified())
        if len(items) == 0:
            return _Seq([])
        if len(items) == 1:
            return items[0]
        return _Seq(items)

    def _quantified(self):
        atom = self._atom()
        if atom is None:
            return _Seq([])
        if self.pos >= len(self.pat):
            return atom
        c = self.pat[self.pos]
        if c in ('*', '+', '?'):
            if isinstance(atom, (_As, _Ae)):
                raise ValueError("cannot quantify assertion")
            self.pos += 1
            lo, hi = self._simple_bounds(c)
            greedy = True
            if self.pos < len(self.pat) and self.pat[self.pos] == '?':
                self.pos += 1
                greedy = False
            if self.pos < len(self.pat) and self.pat[self.pos] in ('*', '+', '?', '{'):
                raise ValueError("quantifier after quantifier")
            return _Quant(atom, lo, hi, greedy)
        if c == '{':
            saved = self.pos
            result = self._try_counted()
            if result is not None:
                if isinstance(atom, (_As, _Ae)):
                    raise ValueError("cannot quantify assertion")
                lo, hi, greedy = result
                if self.pos < len(self.pat) and self.pat[self.pos] in ('*', '+', '?', '{'):
                    raise ValueError("quantifier after quantifier")
                return _Quant(atom, lo, hi, greedy)
            self.pos = saved
        return atom

    def _simple_bounds(self, c):
        if c == '*': return (0, None)
        if c == '+': return (1, None)
        return (0, 1)

    def _try_counted(self):
        saved = self.pos
        self.pos += 1  # skip {
        m = self._digits()
        if m is None:
            self.pos = saved
            return None
        lo = int(m)
        if self.pos < len(self.pat) and self.pat[self.pos] == ',':
            self.pos += 1
            n_str = self._digits()
            if n_str is not None:
                hi = int(n_str)
            else:
                hi = None
        else:
            hi = lo
        if self.pos >= len(self.pat) or self.pat[self.pos] != '}':
            self.pos = saved
            return None
        self.pos += 1  # skip }
        if hi is not None and lo > hi:
            raise ValueError("min > max in quantifier")
        greedy = True
        if self.pos < len(self.pat) and self.pat[self.pos] == '?':
            self.pos += 1
            greedy = False
        return (lo, hi, greedy)

    def _digits(self):
        start = self.pos
        while self.pos < len(self.pat) and self.pat[self.pos].isdigit():
            self.pos += 1
        if self.pos == start:
            return None
        return self.pat[start:self.pos]

    def _atom(self):
        if self.pos >= len(self.pat):
            return None
        c = self.pat[self.pos]
        if c == '.':
            self.pos += 1
            return _Any()
        if c == '^':
            self.pos += 1
            return _As()
        if c == '$':
            self.pos += 1
            return _Ae()
        if c == '\\':
            return self._escape()
        if c == '[':
            return self._class()
        if c == '(':
            return self._group()
        if c in ('*', '+', '?', '|', ')'):
            raise ValueError("nothing to repeat")
        self.pos += 1
        return _Lit(c)

    def _escape(self):
        self.pos += 1  # skip backslash
        if self.pos >= len(self.pat):
            raise ValueError("backslash at end of pattern")
        c = self.pat[self.pos]
        self.pos += 1
        if c in _ESCAPE_CLASSES:
            chars, neg = _ESCAPE_CLASSES[c]
            return _Cls(chars, neg)
        if c == 'n': return _Lit('\n')
        if c == 't': return _Lit('\t')
        if c.isalpha() or c.isdigit():
            raise ValueError(f"invalid escape \\{c}")
        return _Lit(c)

    def _class(self):
        self.pos += 1  # skip [
        neg = False
        if self.pos < len(self.pat) and self.pat[self.pos] == '^':
            neg = True
            self.pos += 1
        chars = set()
        first = True
        while True:
            if self.pos >= len(self.pat):
                raise ValueError("unclosed character class")
            if self.pat[self.pos] == ']' and not first:
                self.pos += 1
                break
            first = False
            item_type, item_val = self._class_item()
            # check for range
            if item_type == 'char' and self.pos < len(self.pat) and self.pat[self.pos] == '-':
                next_idx = self.pos + 1
                if next_idx < len(self.pat) and self.pat[next_idx] != ']':
                    self.pos += 1  # skip -
                    end_type, end_val = self._class_item()
                    if end_type != 'char':
                        raise ValueError("invalid range end")
                    if ord(item_val) > ord(end_val):
                        raise ValueError("invalid range")
                    for code in range(ord(item_val), ord(end_val) + 1):
                        chars.add(chr(code))
                    continue
            if item_type == 'escape':
                if self.pos < len(self.pat) and self.pat[self.pos] == '-':
                    next_idx = self.pos + 1
                    if next_idx < len(self.pat) and self.pat[next_idx] != ']':
                        raise ValueError("class escape in range")
                chars.update(item_val)
            else:
                chars.add(item_val)
        return _Cls(frozenset(chars), neg)

    def _class_item(self):
        if self.pat[self.pos] == '\\':
            self.pos += 1
            if self.pos >= len(self.pat):
                raise ValueError("backslash at end of class")
            c = self.pat[self.pos]
            self.pos += 1
            if c in _ESCAPE_CLASSES:
                chars, neg = _ESCAPE_CLASSES[c]
                if neg:
                    all_chars = frozenset(chr(i) for i in range(128))
                    return ('escape', all_chars - chars)
                return ('escape', chars)
            if c == 'n': return ('char', '\n')
            if c == 't': return ('char', '\t')
            if c.isalpha() or c.isdigit():
                raise ValueError(f"invalid escape in class \\{c}")
            return ('char', c)
        else:
            c = self.pat[self.pos]
            self.pos += 1
            return ('char', c)

    def _group(self):
        self.pos += 1  # skip (
        if self.pos < len(self.pat) and self.pat[self.pos] == '?':
            self.pos += 1
            if self.pos < len(self.pat) and self.pat[self.pos] == ':':
                self.pos += 1
                child = self._alt()
                if self.pos >= len(self.pat) or self.pat[self.pos] != ')':
                    raise ValueError("unclosed group")
                self.pos += 1
                return _NCG(child)
            raise ValueError("unsupported (?...) syntax")
        self.num_groups += 1
        gnum = self.num_groups
        child = self._alt()
        if self.pos >= len(self.pat) or self.pat[self.pos] != ')':
            raise ValueError("unclosed group")
        self.pos += 1
        return _Grp(gnum, child)


# ─── Compiler ─────────────────────────────────────────────────────────────────

class _Compiler:
    def __init__(self):
        self.code = []
        self.num_quants = 0
        self._patches = []
        self._labels = {}
        self._lc = 0

    def _new_label(self):
        self._lc += 1
        return self._lc

    def _emit(self, instr):
        self.code.append(list(instr))
        return len(self.code) - 1

    def _label(self, lbl):
        self._labels[lbl] = len(self.code)

    def _patch(self, idx, field, lbl):
        self._patches.append((idx, field, lbl))

    def _resolve(self):
        for idx, field, lbl in self._patches:
            self.code[idx][field] = self._labels[lbl]
        self.code = [tuple(c) for c in self.code]

    def compile(self, ast):
        self._compile_node(ast)
        self._emit(('ok',))
        self._resolve()
        return self.code

    def _compile_node(self, node):
        if isinstance(node, _Lit):
            self._emit(('lit', node.c))
        elif isinstance(node, _Any):
            self._emit(('any',))
        elif isinstance(node, _Cls):
            self._emit(('cls', node.chars, node.neg))
        elif isinstance(node, _As):
            self._emit(('as',))
        elif isinstance(node, _Ae):
            self._emit(('ae',))
        elif isinstance(node, _Grp):
            self._emit(('gs', node.num))
            self._compile_node(node.child)
            self._emit(('ge', node.num))
        elif isinstance(node, _NCG):
            self._compile_node(node.child)
        elif isinstance(node, _Seq):
            for item in node.items:
                self._compile_node(item)
        elif isinstance(node, _Alt):
            self._compile_alt(node.branches)
        elif isinstance(node, _Quant):
            self._compile_quant(node)
        else:
            raise ValueError("unknown node")

    def _compile_alt(self, branches):
        if len(branches) == 1:
            self._compile_node(branches[0])
            return
        end_label = self._new_label()
        self._compile_alt_rec(branches, 0, end_label)
        self._label(end_label)

    def _compile_alt_rec(self, branches, idx, end_label):
        if idx == len(branches) - 1:
            self._compile_node(branches[idx])
            return
        next_label = self._new_label()
        sp = self._emit(('sp', 0, 0))
        self._patch(sp, 1, next_label)
        self._compile_node(branches[idx])
        jp = self._emit(('jp', 0))
        self._patch(jp, 1, end_label)
        self._label(next_label)
        self._compile_alt_rec(branches, idx + 1, end_label)

    def _compile_quant(self, node):
        child = node.child
        lo, hi, greedy = node.lo, node.hi, node.greedy
        if lo == 0 and hi == 0:
            return
        if hi is not None and hi == 0:
            return
        qid = self.num_quants
        self.num_quants += 1

        # Forced iterations
        for _ in range(lo):
            self._compile_node(child)

        # Optional iterations
        remaining = None if hi is None else hi - lo
        if remaining is not None and remaining == 0:
            return

        if remaining is not None:
            # Unrolled
            self._compile_quant_unrolled(child, remaining, greedy, qid)
        else:
            # Loop (unbounded)
            self._compile_quant_loop(child, greedy, qid)

    def _compile_quant_unrolled(self, child, count, greedy, qid):
        after_label = self._new_label()
        if greedy:
            for i in range(count):
                mc = self._emit(('mc', qid, 0))
                self._patch(mc, 2, after_label)
                self._emit(('ms', qid))
                sp = self._emit(('sp', 0, 0))
                body_label = self._new_label()
                self._patch(sp, 1, body_label)
                self._patch(sp, 2, after_label)
                self._label(body_label)
                self._compile_node(child)
            self._label(after_label)
        else:
            # Lazy unrolled
            dead_label = self._new_label()
            for i in range(count):
                sp = self._emit(('sp', 0, 0))
                stop_label = self._new_label()
                self._patch(sp, 1, stop_label)
                self._patch(sp, 2, stop_label)  # placeholder, fix below
                # Actually: split(stop, body). stop = after quantifier. body = qmark_chk...
                # We need stop to jump to after_label. But after_label is at the end.
                # Let's restructure: all stops jump to after_label.
                self._emit(('jp', 0))  # jump to after (this is the "stop" branch target)
                # Hmm, this doesn't work with split. Let me redo.
                pass
            # Redo lazy unrolled properly
            self.code = self.code[:-(2 * count + 1)]  # undo (messy)
            # Actually let me just redo from scratch
            self._patches = [p for p in self._patches if p[0] < len(self.code)]
            self._compile_quant_unrolled_lazy(child, count, qid, after_label)
            self._label(after_label)

    def _compile_quant_unrolled_lazy(self, child, count, qid, after_label):
        for i in range(count):
            sp = self._emit(('sp', 0, 0))
            body_lbl = self._new_label()
            self._patch(sp, 1, after_label)  # stop → after
            self._patch(sp, 2, body_lbl)     # body
            self._label(body_lbl)
            mc = self._emit(('mc', qid, 0))
            # if pos == mark: fail (dead)
            dead_lbl = self._new_label()
            self._patch(mc, 2, dead_lbl)
            self._emit(('ms', qid))
            self._compile_node(child)
            self._label(dead_lbl)
            self._emit(('fl',))

    def _compile_quant_loop(self, child, greedy, qid):
        if greedy:
            loop_lbl = self._new_label()
            after_lbl = self._new_label()
            self._label(loop_lbl)
            mc = self._emit(('mc', qid, 0))
            self._patch(mc, 2, after_lbl)
            self._emit(('ms', qid))
            sp = self._emit(('sp', 0, 0))
            body_lbl = self._new_label()
            self._patch(sp, 1, body_lbl)
            self._patch(sp, 2, after_lbl)
            self._label(body_lbl)
            self._compile_node(child)
            jp = self._emit(('jp', 0))
            self._patch(jp, 1, loop_lbl)
            self._label(after_lbl)
        else:
            loop_lbl = self._new_label()
            after_lbl = self._new_label()
            self._label(loop_lbl)
            sp = self._emit(('sp', 0, 0))
            body_lbl = self._new_label()
            self._patch(sp, 1, after_lbl)
            self._patch(sp, 2, body_lbl)
            self._label(body_lbl)
            mc = self._emit(('mc', qid, 0))
            dead_lbl = self._new_label()
            self._patch(mc, 2, dead_lbl)
            self._emit(('ms', qid))
            self._compile_node(child)
            jp = self._emit(('jp', 0))
            self._patch(jp, 1, loop_lbl)
            self._label(dead_lbl)
            self._emit(('fl',))
            self._label(after_lbl)


# Fix the _compile_quant_unrolled for greedy (rewrite cleanly)
def _compile_quant_unrolled_greedy(comp, child, count, qid):
    after_label = comp._new_label()
    for i in range(count):
        mc = comp._emit(('mc', qid, 0))
        comp._patch(mc, 2, after_label)
        comp._emit(('ms', qid))
        sp = comp._emit(('sp', 0, 0))
        body_label = comp._new_label()
        comp._patch(sp, 1, body_label)
        comp._patch(sp, 2, after_label)
        comp._label(body_label)
        comp._compile_node(child)
    comp._label(after_label)


def _compile_quant_unrolled_lazy2(comp, child, count, qid):
    after_label = comp._new_label()
    for i in range(count):
        sp = comp._emit(('sp', 0, 0))
        body_lbl = comp._new_label()
        comp._patch(sp, 1, after_label)
        comp._patch(sp, 2, body_lbl)
        comp._label(body_lbl)
        mc = comp._emit(('mc', qid, 0))
        dead_lbl = comp._new_label()
        comp._patch(mc, 2, dead_lbl)
        comp._emit(('ms', qid))
        comp._compile_node(child)
        comp._label(dead_lbl)
        comp._emit(('fl',))
    comp._label(after_label)


# Override _compile_quant_unrolled with clean versions
def _compile_quant_unrolled_fixed(self, child, count, greedy, qid):
    if greedy:
        _compile_quant_unrolled_greedy(self, child, count, qid)
    else:
        _compile_quant_unrolled_lazy2(self, child, count, qid)

_Compiler._compile_quant_unrolled = _compile_quant_unrolled_fixed


# ─── VM ───────────────────────────────────────────────────────────────────────

def _vm(instructions, s, start_pos, num_groups, num_quants, fullmatch, memo):
    slen = len(s)
    pc = 0
    pos = start_pos
    stack = []  # list of (alt_pc, pos, captures, marks, split_key)
    captures = [None] * num_groups
    marks = [None] * num_quants
    last_popped = None

    while True:
        if pc >= len(instructions):
            # Shouldn't reach here if 'ok' is last
            if not stack:
                return None
            entry = stack.pop()
            if last_popped is not None:
                memo.add(last_popped[4])
            last_popped = entry
            pc, pos, captures, marks = entry[0], entry[1], entry[2], entry[3]
            continue

        key = (pc, pos)
        if key in memo:
            if not stack:
                if last_popped is not None:
                    memo.add(last_popped[4])
                return None
            entry = stack.pop()
            if last_popped is not None:
                memo.add(last_popped[4])
            last_popped = entry
            pc, pos, captures, marks = entry[0], entry[1], entry[2], entry[3]
            continue

        instr = instructions[pc]
        op = instr[0]

        if op == 'lit':
            if pos < slen and s[pos] == instr[1]:
                pos += 1
                pc += 1
                last_popped = None
            else:
                memo.add(key)
                if not stack:
                    if last_popped is not None:
                        memo.add(last_popped[4])
                    return None
                entry = stack.pop()
                if last_popped is not None:
                    memo.add(last_popped[4])
                last_popped = entry
                pc, pos, captures, marks = entry[0], entry[1], entry[2], entry[3]
                continue

        elif op == 'any':
            if pos < slen and s[pos] != '\n':
                pos += 1
                pc += 1
                last_popped = None
            else:
                memo.add(key)
                if not stack:
                    if last_popped is not None:
                        memo.add(last_popped[4])
                    return None
                entry = stack.pop()
                if last_popped is not None:
                    memo.add(last_popped[4])
                last_popped = entry
                pc, pos, captures, marks = entry[0], entry[1], entry[2], entry[3]
                continue

        elif op == 'cls':
            chars, neg = instr[1], instr[2]
            if pos < slen:
                in_set = s[pos] in chars
                if (not neg and in_set) or (neg and not in_set):
                    pos += 1
                    pc += 1
                    last_popped = None
                    continue
            memo.add(key)
            if not stack:
                if last_popped is not None:
                    memo.add(last_popped[4])
                return None
            entry = stack.pop()
            if last_popped is not None:
                memo.add(last_popped[4])
            last_popped = entry
            pc, pos, captures, marks = entry[0], entry[1], entry[2], entry[3]
            continue

        elif op == 'as':
            if pos == 0:
                pc += 1
                last_popped = None
            else:
                memo.add(key)
                if not stack:
                    if last_popped is not None:
                        memo.add(last_popped[4])
                    return None
                entry = stack.pop()
                if last_popped is not None:
                    memo.add(last_popped[4])
                last_popped = entry
                pc, pos, captures, marks = entry[0], entry[1], entry[2], entry[3]
                continue

        elif op == 'ae':
            if pos == slen or (pos == slen - 1 and s[pos] == '\n'):
                pc += 1
                last_popped = None
            else:
                memo.add(key)
                if not stack:
                    if last_popped is not None:
                        memo.add(last_popped[4])
                    return None
                entry = stack.pop()
                if last_popped is not None:
                    memo.add(last_popped[4])
                last_popped = entry
                pc, pos, captures, marks = entry[0], entry[1], entry[2], entry[3]
                continue

        elif op == 'gs':
            g = instr[1]
            captures[g - 1] = (pos, pos)
            pc += 1
            last_popped = None

        elif op == 'ge':
            g = instr[1]
            if captures[g - 1] is not None:
                captures[g - 1] = (captures[g - 1][0], pos)
            pc += 1
            last_popped = None

        elif op == 'sp':
            stack.append((instr[2], pos, captures[:], marks[:], (pc, pos)))
            pc = instr[1]
            last_popped = None

        elif op == 'jp':
            pc = instr[1]
            last_popped = None

        elif op == 'mc':
            qid, target = instr[1], instr[2]
            if marks[qid] == pos:
                pc = target
            else:
                pc += 1
            last_popped = None

        elif op == 'ms':
            marks[instr[1]] = pos
            pc += 1
            last_popped = None

        elif op == 'fl':
            memo.add(key)
            if not stack:
                if last_popped is not None:
                    memo.add(last_popped[4])
                return None
            entry = stack.pop()
            if last_popped is not None:
                memo.add(last_popped[4])
            last_popped = entry
            pc, pos, captures, marks = entry[0], entry[1], entry[2], entry[3]
            continue

        elif op == 'ok':
            if fullmatch and pos != slen:
                memo.add(key)
                if not stack:
                    if last_popped is not None:
                        memo.add(last_popped[4])
                    return None
                entry = stack.pop()
                if last_popped is not None:
                    memo.add(last_popped[4])
                last_popped = entry
                pc, pos, captures, marks = entry[0], entry[1], entry[2], entry[3]
                continue
            return (start_pos, pos, captures[:])

        else:
            raise ValueError(f"unknown instruction {op}")
