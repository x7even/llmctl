"""Backtracking-priority regular-expression engine from scratch (no re/regex/fnmatch/glob)."""
import sys

# ─── Character sets ───────────────────────────────────────────────────────────
_DIGITS = frozenset('0123456789')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')
_ALL_ASCII = frozenset(chr(i) for i in range(128))
_ESC_SETS = {
    'd': _DIGITS, 'D': _ALL_ASCII - _DIGITS,
    'w': _WORD,   'W': _ALL_ASCII - _WORD,
    's': _SPACE,  'S': _ALL_ASCII - _SPACE,
}

# ─── AST nodes ────────────────────────────────────────────────────────────────
class _Lit:
    __slots__ = ('ch',)
    def __init__(self, ch): self.ch = ch

class _Any:
    __slots__ = ()

class _Class:
    __slots__ = ('neg', 'chars')
    def __init__(self, neg, chars): self.neg = neg; self.chars = chars

class _Anchor:
    __slots__ = ('kind',)
    def __init__(self, kind): self.kind = kind  # 'S' or 'E'

class _Group:
    __slots__ = ('child', 'gnum')
    def __init__(self, child, gnum): self.child = child; self.gnum = gnum

class _Seq:
    __slots__ = ('children',)
    def __init__(self, children): self.children = children

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Quant:
    __slots__ = ('child', 'lo', 'hi', 'greedy')
    def __init__(self, child, lo, hi, greedy): self.child = child; self.lo = lo; self.hi = hi; self.greedy = greedy

# ─── can_match_empty ──────────────────────────────────────────────────────────
def _empty(node):
    if isinstance(node, (_Lit, _Any, _Class)): return False
    if isinstance(node, _Anchor): return True
    if isinstance(node, _Group): return _empty(node.child)
    if isinstance(node, _Seq): return all(_empty(c) for c in node.children)
    if isinstance(node, _Alt): return any(_empty(b) for b in node.branches)
    if isinstance(node, _Quant): return node.lo == 0 or _empty(node.child)
    return False

# ─── Parser ───────────────────────────────────────────────────────────────────
class _Parser:
    def __init__(self, pat):
        self.p = pat; self.i = 0; self.ng = 0

    def parse(self):
        ast = self._alt()
        if self.i != len(self.p):
            raise ValueError("unexpected character")
        return ast

    def _alt(self):
        br = [self._seq()]
        while self.i < len(self.p) and self.p[self.i] == '|':
            self.i += 1
            br.append(self._seq())
        return br[0] if len(br) == 1 else _Alt(br)

    def _seq(self):
        items = []
        while self.i < len(self.p) and self.p[self.i] not in '|)':
            items.append(self._quant())
        if not items: return _Seq([])
        return items[0] if len(items) == 1 else _Seq(items)

    def _quant(self):
        # check "nothing to repeat"
        if self.i < len(self.p) and self.p[self.i] in '*+?{':
            if self.p[self.i] == '{':
                # try to see if it's a valid quantifier; if so, error (nothing to repeat)
                # if not valid, it's still an error per spec
                pass
            raise ValueError("nothing to repeat")
        atom = self._atom()
        # check for quantifier
        if self.i >= len(self.p): return atom
        ch = self.p[self.i]
        if ch == '*':
            self.i += 1; return self._finish_quant(atom, 0, None)
        if ch == '+':
            self.i += 1; return self._finish_quant(atom, 1, None)
        if ch == '?':
            self.i += 1; return self._finish_quant(atom, 0, 1)
        if ch == '{':
            return self._brace_quant(atom)
        return atom

    def _finish_quant(self, atom, lo, hi):
        greedy = True
        if self.i < len(self.p) and self.p[self.i] == '?':
            greedy = False; self.i += 1
        # quantifier after quantifier?
        if self.i < len(self.p) and self.p[self.i] in '*+?{':
            if self.p[self.i] == '{':
                raise ValueError("quantifier after quantifier")
            raise ValueError("quantifier after quantifier")
        if lo == 0 and hi == 0:
            return _Seq([])  # x{0} matches empty, groups don't participate
        return _Quant(atom, lo, hi, greedy)

    def _brace_quant(self, atom):
        start = self.i
        self.i += 1  # skip '{'
        ms = self.i
        while self.i < len(self.p) and self.p[self.i].isdigit(): self.i += 1
        if self.i == ms:
            raise ValueError("invalid quantifier")
        m = int(self.p[ms:self.i])
        if self.i < len(self.p) and self.p[self.i] == ',':
            self.i += 1
            ns = self.i
            while self.i < len(self.p) and self.p[self.i].isdigit(): self.i += 1
            if self.i < len(self.p) and self.p[self.i] == '}':
                n = int(self.p[ns:self.i]) if self.i > ns else None
                self.i += 1
            else:
                raise ValueError("invalid quantifier")
        elif self.i < len(self.p) and self.p[self.i] == '}':
            n = m; self.i += 1
        else:
            raise ValueError("invalid quantifier")
        if n is not None and m > n:
            raise ValueError("min > max")
        return self._finish_quant(atom, m, n)

    def _atom(self):
        ch = self.p[self.i]
        if ch == '(': return self._group()
        if ch == '[': return self._cls()
        if ch == '.':
            self.i += 1; return _Any()
        if ch == '^':
            self.i += 1; return _Anchor('S')
        if ch == '$':
            self.i += 1; return _Anchor('E')
        if ch == '\\': return self._esc()
        if ch in '*+?':
            raise ValueError("nothing to repeat")
        self.i += 1
        return _Lit(ch)

    def _group(self):
        self.i += 1  # skip '('
        if self.i + 1 < len(self.p) and self.p[self.i] == '?' and self.p[self.i+1] == ':':
            self.i += 2
            child = self._alt()
            if self.i >= len(self.p) or self.p[self.i] != ')':
                raise ValueError("unbalanced parens")
            self.i += 1
            return _Group(child, 0)
        if self.i < len(self.p) and self.p[self.i] == '?':
            raise ValueError("unsupported group syntax")
        self.ng += 1; gnum = self.ng
        child = self._alt()
        if self.i >= len(self.p) or self.p[self.i] != ')':
            raise ValueError("unbalanced parens")
        self.i += 1
        return _Group(child, gnum)

    def _cls(self):
        self.i += 1  # skip '['
        neg = False
        if self.i < len(self.p) and self.p[self.i] == '^':
            neg = True; self.i += 1
        chars = set()
        first = True
        while True:
            if self.i >= len(self.p):
                raise ValueError("unterminated class")
            if self.p[self.i] == ']' and not first:
                self.i += 1; break
            first = False
            item = self._cls_item()
            # check range
            if (item[0] == 'c' and self.i < len(self.p) and self.p[self.i] == '-'
                    and self.i + 1 < len(self.p) and self.p[self.i+1] != ']'):
                self.i += 1  # skip '-'
                end = self._cls_item()
                if end[0] != 'c':
                    raise ValueError("invalid range")
                if ord(item[1]) > ord(end[1]):
                    raise ValueError("invalid range")
                for c in range(ord(item[1]), ord(end[1])+1):
                    chars.add(chr(c))
            elif (item[0] == 'e' and self.i < len(self.p) and self.p[self.i] == '-'
                  and self.i + 1 < len(self.p) and self.p[self.i+1] != ']'):
                raise ValueError("class escape in range")
            else:
                if item[0] == 'c':
                    chars.add(item[1])
                else:
                    chars |= _ESC_SETS[item[1]]
        if neg:
            chars = _ALL_ASCII - chars
        return _Class(neg, frozenset(chars))

    def _cls_item(self):
        ch = self.p[self.i]
        if ch == '\\':
            self.i += 1
            if self.i >= len(self.p):
                raise ValueError("backslash at end")
            e = self.p[self.i]
            if e in 'dDwWsS':
                self.i += 1; return ('e', e)
            if e == 'n': self.i += 1; return ('c', '\n')
            if e == 't': self.i += 1; return ('c', '\t')
            if not e.isalnum():
                self.i += 1; return ('c', e)
            raise ValueError("invalid class escape")
        self.i += 1
        return ('c', ch)

    def _esc(self):
        self.i += 1  # skip '\'
        if self.i >= len(self.p):
            raise ValueError("backslash at end")
        e = self.p[self.i]
        if e in 'dDwWsS':
            self.i += 1; return _Class(False, _ESC_SETS[e])
        if e == 'n': self.i += 1; return _Lit('\n')
        if e == 't': self.i += 1; return _Lit('\t')
        if not e.isalnum():
            self.i += 1; return _Lit(e)
        raise ValueError("invalid escape")

# ─── Compiler (AST → instruction list) ───────────────────────────────────────
# Opcodes
_OP_CHAR, _OP_CLASS, _OP_ANY, _OP_START, _OP_END = 0,1,2,3,4
_OP_SPLIT, _OP_JUMP, _OP_GSTART, _OP_GEND = 5,6,7,8
_OP_SETM, _OP_JIM, _OP_ACCEPT, _OP_FAIL = 9,10,11,12

class _Compiler:
    def __init__(self):
        self.code = []
        self.qid = 0

    def compile(self, ast):
        self._emit(ast, 0)
        self.code.append((_OP_ACCEPT,))

    def _here(self): return len(self.code)

    def _emit(self, node, risky):
        if isinstance(node, _Seq):
            for c in node.children: self._emit(c, risky)
        elif isinstance(node, _Alt):
            self._emit_alt(node.branches, risky)
        elif isinstance(node, _Lit):
            self.code.append((_OP_CHAR, node.ch))
        elif isinstance(node, _Class):
            self.code.append((_OP_CLASS, node.chars))
        elif isinstance(node, _Any):
            self.code.append((_OP_ANY,))
        elif isinstance(node, _Anchor):
            self.code.append((_OP_START,) if node.kind=='S' else (_OP_END,))
        elif isinstance(node, _Group):
            if node.gnum:
                self.code.append((_OP_GSTART, node.gnum))
                self._emit(node.child, risky)
                self.code.append((_OP_GEND, node.gnum))
            else:
                self._emit(node.child, risky)
        elif isinstance(node, _Quant):
            self._emit_quant(node, risky)

    def _emit_alt(self, branches, risky):
        if len(branches) == 1:
            self._emit(branches[0], risky); return
        # SPLIT(branch0, next_alt)
        after = self._here() + 1 + 0  # placeholder
        # We'll emit: SPLIT(b0, b1); b0_code; JUMP(after); b1_code; ...; after:
        self._emit_alt_rec(branches, 0, risky)

    def _emit_alt_rec(self, branches, idx, risky):
        if idx == len(branches) - 1:
            self._emit(branches[idx], risky); return
        # SPLIT(this_branch, next)
        sp = self._here()
        self.code.append((_OP_SPLIT, 0, 0, 1-risky))  # placeholder targets
        # emit this branch
        self._emit(branches[idx], risky)
        # JUMP(after_all)
        jp = self._here()
        self.code.append((_OP_JUMP, 0))
        # next branch
        nxt = self._here()
        self._emit_alt_rec(branches, idx+1, risky)
        after = self._here()
        # patch SPLIT
        self.code[sp] = (_OP_SPLIT, sp+1, nxt, 1-risky)
        # patch JUMP
        self.code[jp] = (_OP_JUMP, after)

    def _emit_quant(self, node, risky):
        child_empty = _empty(node.child)
        child_risky = risky or child_empty
        qid = self.qid; self.qid += 1
        lo, hi, greedy = node.lo, node.hi, node.greedy

        if hi is None:  # unbounded
            # forced iterations (lo copies)
            for _ in range(lo):
                self._emit(node.child, child_risky)
            # optional loop
            loop = self._here()
            if greedy:
                jim = self._here()
                self.code.append((_OP_JIM, qid, 0, 1-child_risky))  # patch target later
                self.code.append((_OP_SETM, qid))
                sp = self._here()
                self.code.append((_OP_SPLIT, 0, 0, 1-child_risky))
                self._emit(node.child, child_risky)
                self.code.append((_OP_JUMP, loop))
                after = self._here()
                self.code[jim] = (_OP_JIM, qid, after, 1-child_risky)
                self.code[sp] = (_OP_SPLIT, sp+1, after, 1-child_risky)
            else:
                # lazy
                sp = self._here()
                self.code.append((_OP_SPLIT, 0, 0, 1-child_risky))
                after = self._here()
                # continuation will be emitted after this quantifier
                # Actually for lazy, "after" is the continuation.
                # We need to jump to continuation, then the check/body.
                # Structure: SPLIT(after, check); after: <cont>; check: JIM fail; SETM; body; JUMP(sp)
                # But "after" is where the continuation goes, which is AFTER this quantifier.
                # We'll use a special approach: the SPLIT's "after" target is the next instruction
                # after the quantifier code. We'll patch it later.
                # For now, emit check+body, then JUMP back.
                # Actually let me restructure:
                # loop:
                #   SPLIT(after, check)   <- SPLIT here
                # after: (continuation follows naturally after the quantifier)
                # check:
                #   JIM qid, fail
                #   SETM qid
                #   <body>
                #   JUMP loop
                # fail: FAIL
                # But "after" must be AFTER the quantifier in the code.
                # I'll emit: SPLIT, then the check/body/fail, then a marker for "after".
                # The continuation will be at the marker.
                # Problem: the continuation is emitted by the caller AFTER _emit_quant returns.
                # So I need "after" to be the position right after this quantifier's code.
                # I'll emit the quantifier code, then return. The caller emits continuation.
                # The SPLIT target "after" = position after all quantifier code.
                # I'll patch it after emitting everything.
                # Let me emit: SPLIT(after, check), check_code, body, JUMP(loop), FAIL, <after>
                # where <after> is the end of this function.
                check = self._here()
                # JIM
                jim2 = self._here()
                self.code.append((_OP_JIM, qid, 0, 1-child_risky))
                self.code.append((_OP_SETM, qid))
                self._emit(node.child, child_risky)
                self.code.append((_OP_JUMP, loop))
                fail = self._here()
                self.code.append((_OP_FAIL,))
                after = self._here()
                self.code[sp] = (_OP_SPLIT, after, check, 1-child_risky)
                self.code[jim2] = (_OP_JIM, qid, fail, 1-child_risky)
        else:
            # bounded: unroll
            # forced
            for _ in range(lo):
                self._emit(node.child, child_risky)
            # optional (hi - lo) iterations
            if hi == lo:
                return  # no optional
            if greedy:
                jumps_to_after = []
                for _ in range(hi - lo):
                    jim = self._here()
                    self.code.append((_OP_JIM, qid, 0, 1-child_risky))
                    self.code.append((_OP_SETM, qid))
                    sp = self._here()
                    self.code.append((_OP_SPLIT, 0, 0, 1-child_risky))
                    self._emit(node.child, child_risky)
                    jumps_to_after.append((jim, sp))
                after = self._here()
                for jim, sp in jumps_to_after:
                    self.code[jim] = (_OP_JIM, qid, after, 1-child_risky)
                    self.code[sp] = (_OP_SPLIT, sp+1, after, 1-child_risky)
            else:
                # lazy bounded
                splits = []
                for _ in range(hi - lo):
                    sp = self._here()
                    self.code.append((_OP_SPLIT, 0, 0, 1-child_risky))
                    check = self._here()
                    jim = self._here()
                    self.code.append((_OP_JIM, qid, 0, 1-child_risky))
                    self.code.append((_OP_SETM, qid))
                    self._emit(node.child, child_risky)
                    splits.append((sp, check, jim))
                after = self._here()
                fail = self._here()
                self.code.append((_OP_FAIL,))
                # patch: SPLIT targets: after, check
                # JIM targets: fail
                # But "after" is the end of quantifier code. The continuation follows.
                # Actually for lazy, the SPLIT's first target is "after" (try stopping first).
                # The "after" is the continuation, which comes after this code.
                # I need to patch after the caller emits the continuation.
                # Hmm, this is tricky. Let me use a different approach.
                # I'll make "after" = fail (which backtracks), and the real continuation
                # is reached by falling through after the quantifier.
                # Actually, let me restructure lazy bounded:
                # SPLIT(continuation, check1)
                # check1: JIM fail; SETM; body; SPLIT(continuation, check2)
                # check2: JIM fail; SETM; body; ... ; JUMP(continuation)
                # fail: FAIL
                # continuation: <rest>
                # The "continuation" target is the position AFTER the quantifier code.
                # I'll emit the code, then the caller emits continuation.
                # I'll store the positions to patch and patch them after.
                # For now, set after = self._here() (which is the end of quantifier code).
                # The continuation will be at self._here() when the caller emits it.
                # But I can't know that position yet!
                # Solution: emit a JUMP placeholder at the end, and have the caller
                # emit the continuation there.
                # Actually, the simplest: make the "after" target be the position right
                # after the FAIL instruction. The caller's code follows immediately.
                # So after = self._here() is correct IF the caller emits right after.
                # Let me just set after = self._here() and patch.
                # But wait, I already emitted FAIL at position 'fail'. After = fail+1.
                # The caller will emit at fail+1. So after = fail+1. ✓
                for sp, check, jim in splits:
                    self.code[sp] = (_OP_SPLIT, after, check, 1-child_risky)
                    self.code[jim] = (_OP_JIM, qid, fail, 1-child_risky)

# ─── Matcher ──────────────────────────────────────────────────────────────────
def _match(code, s, start, full, ngroups):
    n = len(s)
    pc = 0
    pos = start
    # backtrack stack: list of (pc, pos, trail_len)
    stack = []
    # trail for undoing captures/marks
    trail = []
    # captures: list of (start, end) or None, index 0 unused
    captures = [None] * (ngroups + 1)
    # group starts stack: list of (gnum, pos)
    gstack = []
    # marks: dict qid -> pos or None
    marks = {}
    # memo: set of (pc, pos) that are dead ends
    memo = set()

    while True:
        # memo check
        if (pc, pos) in memo:
            if not stack:
                return None
            pc, pos, tl = stack.pop()
            _undo(trail, captures, gstack, marks, tl)
            continue

        op = code[pc]
        tag = op[0]

        if tag == _OP_ACCEPT:
            if full and pos != n:
                if not stack: return None
                pc, pos, tl = stack.pop()
                _undo(trail, captures, gstack, marks, tl)
                continue
            return _build_match(pos, captures, ngroups)

        elif tag == _OP_CHAR:
            if pos < n and s[pos] == op[1]:
                pos += 1; pc += 1
            else:
                if not stack: return None
                pc, pos, tl = stack.pop()
                _undo(trail, captures, gstack, marks, tl)

        elif tag == _OP_CLASS:
            if pos < n and s[pos] in op[1]:
                pos += 1; pc += 1
            else:
                if not stack: return None
                pc, pos, tl = stack.pop()
                _undo(trail, captures, gstack, marks, tl)

        elif tag == _OP_ANY:
            if pos < n and s[pos] != '\n':
                pos += 1; pc += 1
            else:
                if not stack: return None
                pc, pos, tl = stack.pop()
                _undo(trail, captures, gstack, marks, tl)

        elif tag == _OP_START:
            if pos == 0:
                pc += 1
            else:
                if not stack: return None
                pc, pos, tl = stack.pop()
                _undo(trail, captures, gstack, marks, tl)

        elif tag == _OP_END:
            if pos == n or (pos == n - 1 and n > 0 and s[n-1] == '\n'):
                pc += 1
            else:
                if not stack: return None
                pc, pos, tl = stack.pop()
                _undo(trail, captures, gstack, marks, tl)

        elif tag == _OP_SPLIT:
            _, ta, tb, memo_ok = op
            if memo_ok:
                stack.append((pc, pos, len(trail)))
            else:
                stack.append((pc, pos, len(trail), 0))  # 0 = don't memo
            pc = ta

        elif tag == _OP_JUMP:
            pc = op[1]

        elif tag == _OP_GSTART:
            gnum = op[1]
            trail.append(('gs', gnum, len(gstack)))
            gstack.append((gnum, pos))
            pc += 1

        elif tag == _OP_GEND:
            gnum = op[1]
            # pop group start
            gs_gnum, gs_pos = gstack[-1]
            gstack.pop()
            trail.append(('ge', gnum, captures[gnum]))
            captures[gnum] = (gs_pos, pos)
            pc += 1

        elif tag == _OP_SETM:
            qid = op[1]
            old = marks.get(qid)
            trail.append(('m', qid, old))
            marks[qid] = pos
            pc += 1

        elif tag == _OP_JIM:
            _, qid, target, _ = op
            if marks.get(qid) == pos:
                pc = target
            else:
                pc += 1

        elif tag == _OP_FAIL:
            if not stack: return None
            pc, pos, tl = stack.pop()[:3]
            _undo(trail, captures, gstack, marks, tl)

        else:
            raise RuntimeError("bad opcode")

    return None


def _undo(trail, captures, gstack, marks, target_len):
    while len(trail) > target_len:
        entry = trail.pop()
        t = entry[0]
        if t == 'gs':
            # undo group start: pop gstack
            gstack.pop()
        elif t == 'ge':
            # undo group end: restore capture and push back gstack
            gnum, old_cap = entry[1], entry[2]
            captures[gnum] = old_cap
            # we need to restore the group start on gstack
            # but we don't know the pos... actually we stored gstack length
            # Hmm, let me fix: 'gs' stores the gstack length before push
            # 'ge' needs to restore gstack
            # Let me change the approach: 'gs' entry stores (gnum, old_gstack_len)
            # and we just pop gstack. 'ge' entry stores (gnum, old_cap, old_gstack_entry)
            # Actually let me redo:
            pass
        elif t == 'm':
            qid, old = entry[1], entry[2]
            if old is None:
                marks.pop(qid, None)
            else:
                marks[qid] = old
    # Fix: redo the undo properly
    # (The above has a bug with 'ge' not restoring gstack. Let me fix the trail format.)


# Let me redo the undo with a cleaner trail format:
# Trail entries:
#   ('gs', gnum, gstack_len_before)  -- undo: gstack.pop() (we know it was pushed)
#   ('ge', gnum, old_capture, gstack_entry)  -- undo: captures[gnum]=old, gstack.append(entry)
#   ('m', qid, old_mark)  -- undo: marks[qid]=old or del

def _undo2(trail, captures, gstack, marks, target_len):
    while len(trail) > target_len:
        entry = trail.pop()
        t = entry[0]
        if t == 'gs':
            gstack.pop()
        elif t == 'ge':
            gnum, old_cap, gs_entry = entry[1], entry[2], entry[3]
            captures[gnum] = old_cap
            gstack.append(gs_entry)
        elif t == 'm':
            qid, old = entry[1], entry[2]
            if old is None:
                marks.pop(qid, None)
            else:
                marks[qid] = old


def _match2(code, s, start, full, ngroups):
    n = len(s)
    pc = 0
    pos = start
    stack = []  # (pc, pos, trail_len, memo_ok)
    trail = []
    captures = [None] * (ngroups + 1)
    gstack = []
    marks = {}
    memo = set()

    while True:
        if (pc, pos) in memo:
            if not stack: return None
            spc, spos, stl, _ = stack.pop()
            _undo2(trail, captures, gstack, marks, stl)
            pc, pos = spc, spos
            continue

        op = code[pc]
        tag = op[0]

        if tag == _OP_ACCEPT:
            if full and pos != n:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos
                continue
            return _build_match(pos, captures, ngroups)

        elif tag == _OP_CHAR:
            if pos < n and s[pos] == op[1]:
                pos += 1; pc += 1
            else:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos

        elif tag == _OP_CLASS:
            if pos < n and s[pos] in op[1]:
                pos += 1; pc += 1
            else:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos

        elif tag == _OP_ANY:
            if pos < n and s[pos] != '\n':
                pos += 1; pc += 1
            else:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos

        elif tag == _OP_START:
            if pos == 0:
                pc += 1
            else:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos

        elif tag == _OP_END:
            if pos == n or (pos == n - 1 and n > 0 and s[n-1] == '\n'):
                pc += 1
            else:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos

        elif tag == _OP_SPLIT:
            _, ta, tb, memo_ok = op
            stack.append((pc, pos, len(trail), memo_ok))
            pc = ta

        elif tag == _OP_JUMP:
            pc = op[1]

        elif tag == _OP_GSTART:
            gnum = op[1]
            trail.append(('gs', gnum))
            gstack.append((gnum, pos))
            pc += 1

        elif tag == _OP_GEND:
            gnum = op[1]
            gs_entry = gstack[-1]
            gstack.pop()
            trail.append(('ge', gnum, captures[gnum], gs_entry))
            captures[gnum] = (gs_entry[1], pos)
            pc += 1

        elif tag == _OP_SETM:
            qid = op[1]
            old = marks.get(qid)
            trail.append(('m', qid, old))
            marks[qid] = pos
            pc += 1

        elif tag == _OP_JIM:
            _, qid, target, _ = op
            if marks.get(qid) == pos:
                pc = target
            else:
                pc += 1

        elif tag == _OP_FAIL:
            if not stack: return None
            spc, spos, stl, _ = stack.pop()
            _undo2(trail, captures, gstack, marks, stl)
            pc, pos = spc, spos

        else:
            raise RuntimeError("bad opcode")

    return None


def _build_match(end, captures, ngroups):
    spans = [None] * (ngroups + 1)
    for i in range(1, ngroups + 1):
        spans[i] = captures[i]
    return _Match(0, end, spans)


# ─── Match class ──────────────────────────────────────────────────────────────
class _Match:
    __slots__ = ('_start', '_end', '_spans', '_ng')
    def __init__(self, start, end, spans):
        self._start = start; self._end = end; self._spans = spans
        self._ng = len(spans) - 1

    def span(self, n=0):
        if n == 0: return (self._start, self._end)
        if n < 0 or n > self._ng: raise IndexError(f"no such group: {n}")
        s = self._spans[n]
        if s is None: return (-1, -1)
        return s

    def start(self, n=0):
        if n == 0: return self._start
        if n < 0 or n > self._ng: raise IndexError(f"no such group: {n}")
        s = self._spans[n]
        if s is None: return -1
        return s[0]

    def end(self, n=0):
        if n == 0: return self._end
        if n < 0 or n > self._ng: raise IndexError(f"no such group: {n}")
        s = self._spans[n]
        if s is None: return -1
        return s[1]

    def group(self, n=0):
        if n == 0:
            return self._s[self._start:self._end] if hasattr(self, '_s') else None
        if n < 0 or n > self._ng: raise IndexError(f"no such group: {n}")
        s = self._spans[n]
        if s is None: return None
        return self._s[s[0]:s[1]] if hasattr(self, '_s') else None

    def groups(self):
        return tuple(
            (self._spans[i][0], self._spans[i][1]) if self._spans[i] else None
            for i in range(1, self._ng + 1)
        )


# Hmm, the Match needs access to the string. Let me store it.
class Match:
    __slots__ = ('_s', '_start', '_end', '_spans', '_ng')
    def __init__(self, s, start, end, spans):
        self._s = s; self._start = start; self._end = end; self._spans = spans
        self._ng = len(spans) - 1

    def span(self, n=0):
        if n == 0: return (self._start, self._end)
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError(f"no such group: {n}")
        s = self._spans[n]
        if s is None: return (-1, -1)
        return s

    def start(self, n=0):
        if n == 0: return self._start
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError(f"no such group: {n}")
        s = self._spans[n]
        if s is None: return -1
        return s[0]

    def end(self, n=0):
        if n == 0: return self._end
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError(f"no such group: {n}")
        s = self._spans[n]
        if s is None: return -1
        return s[1]

    def group(self, n=0):
        if n == 0: return self._s[self._start:self._end]
        if not isinstance(n, int) or n < 0 or n > self._ng:
            raise IndexError(f"no such group: {n}")
        s = self._spans[n]
        if s is None: return None
        return self._s[s[0]:s[1]]

    def groups(self):
        result = []
        for i in range(1, self._ng + 1):
            s = self._spans[i]
            if s is None:
                result.append(None)
            else:
                result.append(self._s[s[0]:s[1]])
        return tuple(result)


# ─── Pattern class ────────────────────────────────────────────────────────────
class Pattern:
    def __init__(self, code, ngroups):
        self._code = code; self._ng = ngroups

    def fullmatch(self, s):
        m = _match2(self._code, s, 0, True, self._ng)
        if m is None: return None
        return Match(s, m[0], m[1], m[2])

    def search(self, s):
        for start in range(len(s) + 1):
            m = _match2(self._code, s, start, False, self._ng)
            if m is not None:
                return Match(s, m[0], m[1], m[2])
        return None


# ─── Fix _match2 to return (start, end, spans) ────────────────────────────────
# (Already returns via _build_match, but let me adjust to pass string info)

def _match2(code, s, start, full, ngroups):
    n = len(s)
    pc = 0
    pos = start
    stack = []
    trail = []
    captures = [None] * (ngroups + 1)
    gstack = []
    marks = {}
    memo = set()

    while True:
        if (pc, pos) in memo:
            if not stack: return None
            spc, spos, stl, _ = stack.pop()
            _undo2(trail, captures, gstack, marks, stl)
            pc, pos = spc, spos
            continue

        op = code[pc]
        tag = op[0]

        if tag == _OP_ACCEPT:
            if full and pos != n:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos
                continue
            spans = [None] * (ngroups + 1)
            for i in range(1, ngroups + 1):
                spans[i] = captures[i]
            return (start, pos, spans)

        elif tag == _OP_CHAR:
            if pos < n and s[pos] == op[1]:
                pos += 1; pc += 1
            else:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos

        elif tag == _OP_CLASS:
            if pos < n and s[pos] in op[1]:
                pos += 1; pc += 1
            else:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos

        elif tag == _OP_ANY:
            if pos < n and s[pos] != '\n':
                pos += 1; pc += 1
            else:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos

        elif tag == _OP_START:
            if pos == 0:
                pc += 1
            else:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos

        elif tag == _OP_END:
            if pos == n or (pos == n - 1 and n > 0 and s[n-1] == '\n'):
                pc += 1
            else:
                if not stack: return None
                spc, spos, stl, _ = stack.pop()
                _undo2(trail, captures, gstack, marks, stl)
                pc, pos = spc, spos

        elif tag == _OP_SPLIT:
            _, ta, tb, memo_ok = op
            stack.append((pc, pos, len(trail), memo_ok))
            pc = ta

        elif tag == _OP_JUMP:
            pc = op[1]

        elif tag == _OP_GSTART:
            gnum = op[1]
            trail.append(('gs', gnum))
            gstack.append((gnum, pos))
            pc += 1

        elif tag == _OP_GEND:
            gnum = op[1]
            gs_entry = gstack[-1]
            gstack.pop()
            trail.append(('ge', gnum, captures[gnum], gs_entry))
            captures[gnum] = (gs_entry[1], pos)
            pc += 1

        elif tag == _OP_SETM:
            qid = op[1]
            old = marks.get(qid)
            trail.append(('m', qid, old))
            marks[qid] = pos
            pc += 1

        elif tag == _OP_JIM:
            _, qid, target, _ = op
            if marks.get(qid) == pos:
                pc = target
            else:
                pc += 1

        elif tag == _OP_FAIL:
            if not stack: return None
            spc, spos, stl, _ = stack.pop()
            _undo2(trail, captures, gstack, marks, stl)
            pc, pos = spc, spos

        else:
            raise RuntimeError("bad opcode")

    return None


# ─── Public API ───────────────────────────────────────────────────────────────
def compile(pattern: str) -> Pattern:
    parser = _Parser(pattern)
    ast = parser.parse()
    ngroups = parser.ng
    compiler = _Compiler()
    compiler.compile(ast)
    return Pattern(compiler.code, ngroups)
