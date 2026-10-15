"""Reference regex engine: parser -> small VM program -> explicit-stack backtracking with
failure memoisation keyed on (pc, pos, loop registers)."""

_WORD = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
_DIGIT = frozenset("0123456789")
_SPACE = frozenset(" \t\n\r\f\v")
_ALNUM = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
_INF = None
_DIGITS = "0123456789"


# ----------------------------------------------------------------------------- parser
class _Parser:
    def __init__(self, p):
        self.p = p
        self.i = 0
        self.ngroups = 0

    def peek(self):
        return self.p[self.i] if self.i < len(self.p) else None

    def parse(self):
        node = self.alt()
        if self.i < len(self.p):  # only an unmatched ')' can stop alt()
            raise ValueError("unbalanced parenthesis")
        return node

    def alt(self):
        branches = [self.seq()]
        while self.peek() == "|":
            self.i += 1
            branches.append(self.seq())
        return branches[0] if len(branches) == 1 else ("alt", branches)

    def seq(self):
        items = []
        while True:
            c = self.peek()
            if c is None or c in "|)":
                break
            atom = self.atom()
            quantifiable = atom[0] not in ("bol", "eol")
            q = self.quant()
            if q is not None:
                if not quantifiable:
                    raise ValueError("nothing to repeat")
                lo, hi, lazy = q
                atom = ("rep", atom, lo, hi, lazy)
                nxt = self.peek()
                if nxt is not None and (nxt in "*+?" or (nxt == "{" and self.try_brace() is not None)):
                    raise ValueError("multiple repeat")
            items.append(atom)
        return ("cat", items)

    def try_brace(self):
        """If a valid {m} {m,} {m,n} starts at self.i return (lo, hi, newi) else None."""
        p, j = self.p, self.i + 1
        k = j
        while k < len(p) and p[k] in _DIGITS:
            k += 1
        if k == j:
            return None
        lo = int(p[j:k])
        if k < len(p) and p[k] == "}":
            return lo, lo, k + 1
        if k < len(p) and p[k] == ",":
            k2 = k + 1
            m = k2
            while m < len(p) and p[m] in _DIGITS:
                m += 1
            if m < len(p) and p[m] == "}":
                return (lo, _INF, m + 1) if m == k2 else (lo, int(p[k2:m]), m + 1)
        return None

    def quant(self):
        c = self.peek()
        if c == "*":
            lo, hi = 0, _INF
        elif c == "+":
            lo, hi = 1, _INF
        elif c == "?":
            lo, hi = 0, 1
        elif c == "{":
            r = self.try_brace()
            if r is None:
                raise ValueError("bad brace")
            lo, hi, ni = r
            if hi is not None and hi < lo:
                raise ValueError("min greater than max")
            self.i = ni - 1
        else:
            return None
        self.i += 1
        lazy = False
        if self.peek() == "?":
            lazy = True
            self.i += 1
        return lo, hi, lazy

    def atom(self):
        c = self.p[self.i]
        if c == "(":
            self.i += 1
            if self.peek() == "?":
                if self.p[self.i:self.i + 2] != "?:":
                    raise ValueError("unsupported group syntax")
                self.i += 2
                node = self.alt()
                capture = None
            else:
                self.ngroups += 1
                capture = self.ngroups
                node = self.alt()
            if self.peek() != ")":
                raise ValueError("missing )")
            self.i += 1
            return node if capture is None else ("group", capture, node)
        if c in "*+?":
            raise ValueError("nothing to repeat")
        if c == "{":
            if self.try_brace() is not None:
                raise ValueError("nothing to repeat")
            raise ValueError("bare {")
        if c == ".":
            self.i += 1
            return ("any",)
        if c == "^":
            self.i += 1
            return ("bol",)
        if c == "$":
            self.i += 1
            return ("eol",)
        if c == "[":
            return self.charclass()
        if c == "\\":
            self.i += 1
            e = self.escape()
            if isinstance(e, str):
                return ("lit", e)
            return ("set", False, [], [e])
        self.i += 1
        return ("lit", c)

    def escape(self):
        """After a backslash: returns a literal char (str) or a class-letter tuple ('cls', 'd')."""
        if self.i >= len(self.p):
            raise ValueError("trailing backslash")
        c = self.p[self.i]
        self.i += 1
        if c in "dDwWsS":
            return ("cls", c)
        if c == "n":
            return "\n"
        if c == "t":
            return "\t"
        if c in _ALNUM:
            raise ValueError("bad escape")
        return c

    def charclass(self):
        self.i += 1  # '['
        neg = False
        if self.peek() == "^":
            neg = True
            self.i += 1
        ranges, classes = [], []
        first = True
        while True:
            c = self.peek()
            if c is None:
                raise ValueError("unterminated class")
            if c == "]" and not first:
                self.i += 1
                break
            first = False
            a = self.class_atom()
            dash = self.peek() == "-" and self.p[self.i + 1:self.i + 2] not in ("]", "")
            if isinstance(a, tuple):
                if dash:
                    raise ValueError("bad range")
                classes.append(a)
                continue
            if dash:
                self.i += 1
                b = self.class_atom()
                if isinstance(b, tuple) or b < a:
                    raise ValueError("bad range")
                ranges.append((a, b))
            else:
                ranges.append((a, a))
        return ("set", neg, ranges, classes)

    def class_atom(self):
        c = self.p[self.i]
        self.i += 1
        if c == "\\":
            return self.escape()
        return c


# ----------------------------------------------------------------------------- compiler
def _make_pred(neg, ranges, classes):
    singles = frozenset(a for a, b in ranges if a == b)
    rng = [(a, b) for a, b in ranges if a != b]
    cl = [c for _, c in classes]

    def pred(ch):
        r = ch in singles
        if not r:
            for a, b in rng:
                if a <= ch <= b:
                    r = True
                    break
        if not r:
            for c in cl:
                if c == "d":
                    r = ch in _DIGIT
                elif c == "D":
                    r = ch not in _DIGIT
                elif c == "w":
                    r = ch in _WORD
                elif c == "W":
                    r = ch not in _WORD
                elif c == "s":
                    r = ch in _SPACE
                else:
                    r = ch not in _SPACE
                if r:
                    break
        return r != neg
    return pred


(CHAR, ANY, SET, BOL, EOL, SPLIT, JMP, SAVE, UNTIL, LAZYITER, ENDITER, LEAVE, MATCH) = range(13)


class _Compiler:
    def __init__(self):
        self.prog = []
        self.loops = []  # (lo, hi, cap) per loop id

    def emit(self, *ins):
        self.prog.append(list(ins))
        return len(self.prog) - 1

    def gen(self, n):
        k = n[0]
        if k == "lit":
            self.emit(CHAR, n[1])
        elif k == "any":
            self.emit(ANY)
        elif k == "set":
            self.emit(SET, _make_pred(n[1], n[2], n[3]))
        elif k == "bol":
            self.emit(BOL)
        elif k == "eol":
            self.emit(EOL)
        elif k == "cat":
            for x in n[1]:
                self.gen(x)
        elif k == "alt":
            jumps = []
            nb = len(n[1])
            for idx, b in enumerate(n[1]):
                if idx < nb - 1:
                    sp = self.emit(SPLIT, 0, 0)
                    self.prog[sp][1] = sp + 1
                    self.gen(b)
                    jumps.append(self.emit(JMP, 0))
                    self.prog[sp][2] = len(self.prog)
                else:
                    self.gen(b)
            for j in jumps:
                self.prog[j][1] = len(self.prog)
        elif k == "group":
            self.emit(SAVE, 2 * n[1])
            self.gen(n[2])
            self.emit(SAVE, 2 * n[1] + 1)
        elif k == "rep":
            _, body, lo, hi, lazy = n
            if hi == 0:
                return  # body can never run
            L = len(self.loops)
            self.loops.append((lo, hi, hi if hi is not None else lo))
            # UNTIL fields: L, lo, hi, lazy, body_pc, exit_pc, lazyiter_pc
            u = self.emit(UNTIL, L, lo, hi, lazy, 0, 0, 0)
            if lazy:
                li = self.emit(LAZYITER, L, hi, 0)
                self.prog[u][7] = li
                self.prog[li][3] = li + 1
            self.prog[u][5] = len(self.prog)
            self.gen(body)
            self.emit(ENDITER, L, u)
            self.prog[u][6] = len(self.prog)
            self.emit(LEAVE, L)


_cache = {}


def compile(pattern):
    if not isinstance(pattern, str):
        raise TypeError("pattern must be str")
    p = _cache.get(pattern)
    if p is None:
        ps = _Parser(pattern)
        ast = ps.parse()
        c = _Compiler()
        c.gen(ast)
        c.emit(MATCH)
        p = Pattern(pattern, c.prog, c.loops, ps.ngroups)
        if len(_cache) > 500:
            _cache.clear()
        _cache[pattern] = p
    return p


# ----------------------------------------------------------------------------- matcher
class Match:
    def __init__(self, string, caps, ngroups, start, end):
        self._s = string
        self._n = ngroups
        self._spans = [(start, end)]
        for g in range(1, ngroups + 1):
            a, b = caps[2 * g], caps[2 * g + 1]
            self._spans.append((a, b) if a is not None and b is not None else (-1, -1))

    def _check(self, n):
        if not isinstance(n, int) or n < 0 or n > self._n:
            raise IndexError("no such group")
        return n

    def span(self, n=0):
        return self._spans[self._check(n)]

    def start(self, n=0):
        return self._spans[self._check(n)][0]

    def end(self, n=0):
        return self._spans[self._check(n)][1]

    def group(self, n=0):
        a, b = self._spans[self._check(n)]
        return None if a < 0 else self._s[a:b]

    def groups(self):
        return tuple(self.group(i) for i in range(1, self._n + 1))


class Pattern:
    def __init__(self, pattern, prog, loops, ngroups):
        self.pattern = pattern
        self._prog = prog
        self._loops = loops
        self._ng = ngroups

    def fullmatch(self, s):
        return self._run(s, True)

    def search(self, s):
        return self._run(s, False)

    def _run(self, s, full):
        prog, loops, n = self._prog, self._loops, len(s)
        nl = len(loops)
        caps = [None] * (2 * self._ng + 2)
        count = [0] * nl
        last = [-1] * nl
        cap_of = [c[2] for c in loops]
        seen = set()
        starts = [0] if full else range(n + 1)
        for st in starts:
            stack = []
            pc, pos = 0, st
            while True:
                if nl:
                    key = (pc, pos, tuple(count), tuple([pos != x for x in last]))
                else:
                    key = (pc, pos)
                ok = key not in seen
                if ok:
                    seen.add(key)
                    ins = prog[pc]
                    op = ins[0]
                    if op == CHAR:
                        if pos < n and s[pos] == ins[1]:
                            pos += 1
                            pc += 1
                        else:
                            ok = False
                    elif op == ANY:
                        if pos < n and s[pos] != "\n":
                            pos += 1
                            pc += 1
                        else:
                            ok = False
                    elif op == SET:
                        if pos < n and ins[1](s[pos]):
                            pos += 1
                            pc += 1
                        else:
                            ok = False
                    elif op == BOL:
                        if pos == 0:
                            pc += 1
                        else:
                            ok = False
                    elif op == EOL:
                        if pos == n or (pos == n - 1 and s[pos] == "\n"):
                            pc += 1
                        else:
                            ok = False
                    elif op == SPLIT:
                        stack.append((0, ins[2], pos))
                        pc = ins[1]
                    elif op == JMP:
                        pc = ins[1]
                    elif op == SAVE:
                        stack.append((1, ins[1], caps[ins[1]]))
                        caps[ins[1]] = pos
                        pc += 1
                    elif op == UNTIL:
                        _, L, lo, hi, lazy, body, exitpc, lazypc = ins
                        c = count[L]
                        if c < lo:
                            pc = body
                        elif lazy:
                            stack.append((0, lazypc, pos))
                            pc = exitpc
                        elif (hi is None or c < hi) and pos != last[L]:
                            stack.append((0, exitpc, pos))
                            stack.append((2, L, last[L]))
                            last[L] = pos
                            pc = body
                        else:
                            pc = exitpc
                    elif op == LAZYITER:
                        _, L, hi, body = ins
                        if (hi is not None and count[L] >= hi) or pos == last[L]:
                            ok = False
                        else:
                            stack.append((2, L, last[L]))
                            last[L] = pos
                            pc = body
                    elif op == ENDITER:
                        L = ins[1]
                        stack.append((3, L, count[L]))
                        if count[L] < cap_of[L]:
                            count[L] += 1
                        pc = ins[2]
                    elif op == LEAVE:
                        L = ins[1]
                        stack.append((4, L, count[L], last[L]))
                        count[L] = 0
                        last[L] = -1
                        pc += 1
                    else:  # MATCH
                        if full and pos != n:
                            ok = False
                        else:
                            return Match(s, caps, self._ng, st, pos)
                if not ok:
                    pc = -1
                    while stack:
                        e = stack.pop()
                        k = e[0]
                        if k == 0:
                            pc, pos = e[1], e[2]
                            break
                        elif k == 1:
                            caps[e[1]] = e[2]
                        elif k == 2:
                            last[e[1]] = e[2]
                        elif k == 3:
                            count[e[1]] = e[2]
                        else:
                            count[e[1]] = e[2]
                            last[e[1]] = e[3]
                    if pc < 0:
                        break
        return None
