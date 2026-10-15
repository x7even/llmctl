class _Lit:
    __slots__ = ('c',)
    def __init__(self, c): self.c = c

class _Any:
    pass

class _AnchorStart:
    pass

class _AnchorEnd:
    pass

class _Class:
    __slots__ = ('negated', 'ranges', 'chars', 'escapes')
    def __init__(self, negated, ranges, chars, escapes):
        self.negated = negated
        self.ranges = ranges
        self.chars = chars
        self.escapes = escapes

class _Group:
    __slots__ = ('capturing', 'gid', 'child')
    def __init__(self, capturing, gid, child):
        self.capturing = capturing
        self.gid = gid
        self.child = child

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Seq:
    __slots__ = ('items',)
    def __init__(self, items): self.items = items

class _Quant:
    __slots__ = ('child', 'lo', 'hi', 'greedy')
    def __init__(self, child, lo, hi, greedy):
        self.child = child
        self.lo = lo
        self.hi = hi
        self.greedy = greedy

# Bytecode opcodes
_OP_LIT = 0
_OP_ANY = 1
_OP_CLASS = 2
_OP_ASSERT_START = 3
_OP_ASSERT_END = 4
_OP_SPLIT = 5
_OP_JUMP = 6
_OP_SAVE = 7
_OP_SAVE_END = 8
_OP_MARK = 9
_OP_INC = 10
_OP_CHECK_MARK = 11
_OP_CHECK_HI = 12
_OP_CHECK_LO = 13
_OP_ACCEPT = 14

_DIGITS = set('0123456789')
_WS = set(' \t\n\r\f\v')
_WORD = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_')

class _Parser:
    def __init__(self, pattern):
        self.pat = pattern
        self.pos = 0
        self.gid = 0
        self.num_groups = 0

    def parse(self):
        result = self._alternation()
        if self.pos < len(self.pat):
            raise ValueError("unexpected character")
        return result

    def _peek(self):
        if self.pos < len(self.pat):
            return self.pat[self.pos]
        return None

    def _alternation(self):
        branches = [self._sequence()]
        while self._peek() == '|':
            self.pos += 1
            branches.append(self._sequence())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _sequence(self):
        items = []
        while True:
            c = self._peek()
            if c is None or c == '|' or c == ')':
                break
            atom = self._atom()
            if atom is None:
                break
            quant = self._try_quantifier(atom)
            items.append(quant)
        if len(items) == 0:
            return _Seq([])
        if len(items) == 1:
            return items[0]
        return _Seq(items)

    def _atom(self):
        c = self._peek()
        if c is None:
            return None
        if c == '(':
            return self._group()
        if c == '[':
            return self._charclass()
        if c == '.':
            self.pos += 1
            return _Any()
        if c == '^':
            self.pos += 1
            return _AnchorStart()
        if c == '$':
            self.pos += 1
            return _AnchorEnd()
        if c == '\\':
            return self._escape_atom()
        if c in '*+?{':
            return None
        self.pos += 1
        return _Lit(c)

    def _escape_atom(self):
        self.pos += 1  # skip backslash
        if self.pos >= len(self.pat):
            raise ValueError("backslash at end of pattern")
        c = self.pat[self.pos]
        if c == 'd':
            self.pos += 1
            return _Class(False, [], set(), 'd')
        if c == 'D':
            self.pos += 1
            return _Class(True, [], set(), 'd')
        if c == 'w':
            self.pos += 1
            return _Class(False, [], set(), 'w')
        if c == 'W':
            self.pos += 1
            return _Class(True, [], set(), 'w')
        if c == 's':
            self.pos += 1
            return _Class(False, [], set(), 's')
        if c == 'S':
            self.pos += 1
            return _Class(True, [], set(), 's')
        if c == 'n':
            self.pos += 1
            return _Lit('\n')
        if c == 't':
            self.pos += 1
            return _Lit('\t')
        if c.isalpha() or c.isdigit():
            raise ValueError(f"invalid escape \\{c}")
        self.pos += 1
        return _Lit(c)

    def _group(self):
        self.pos += 1  # skip (
        capturing = True
        if self.pos < len(self.pat) and self.pat[self.pos] == '?':
            if self.pos + 1 < len(self.pat) and self.pat[self.pos + 1] == ':':
                capturing = False
                self.pos += 2
            else:
                raise ValueError("unsupported group syntax")
        if capturing:
            self.gid += 1
            self.num_groups = self.gid
            gid = self.gid
        else:
            gid = -1
        child = self._alternation()
        if self._peek() != ')':
            raise ValueError("unbalanced parentheses")
        self.pos += 1
        return _Group(capturing, gid, child)

    def _charclass(self):
        self.pos += 1  # skip [
        negated = False
        if self._peek() == '^':
            negated = True
            self.pos += 1
        ranges = []
        chars = set()
        escapes = set()
        first = True
        while True:
            if self.pos >= len(self.pat):
                raise ValueError("unterminated character class")
            c = self.pat[self.pos]
            if c == ']' and not first:
                self.pos += 1
                break
            first = False
            # Parse one item
            item_type, item_val = self._class_item()
            # Check for range
            if item_type == 'char' and self.pos < len(self.pat) and self.pat[self.pos] == '-':
                # Look ahead: is the next char ']'?
                if self.pos + 1 < len(self.pat) and self.pat[self.pos + 1] == ']':
                    chars.add(item_val)
                    chars.add('-')
                    self.pos += 2  # skip -]
                    continue
                elif self.pos + 1 >= len(self.pat):
                    raise ValueError("unterminated character class")
                else:
                    # Try to parse end of range
                    save = self.pos
                    self.pos += 1  # skip -
                    item_type2, item_val2 = self._class_item()
                    if item_type2 != 'char':
                        raise ValueError("invalid range end in character class")
                    if item_val > item_val2:
                        raise ValueError("invalid range in character class")
                    ranges.append((item_val, item_val2))
                    continue
            elif item_type == 'escape':
                if self.pos < len(self.pat) and self.pat[self.pos] == '-':
                    if self.pos + 1 < len(self.pat) and self.pat[self.pos + 1] == ']':
                        escapes.add(item_val)
                        chars.add('-')
                        self.pos += 2
                        continue
                    else:
                        raise ValueError("class escape cannot be start of range")
                escapes.add(item_val)
            else:
                chars.add(item_val)
        return _Class(negated, ranges, chars, escapes)

    def _class_item(self):
        if self.pos >= len(self.pat):
            raise ValueError("unterminated character class")
        c = self.pat[self.pos]
        if c == '\\':
            self.pos += 1
            if self.pos >= len(self.pat):
                raise ValueError("backslash at end of pattern")
            c2 = self.pat[self.pos]
            if c2 in 'dDwWsS':
                self.pos += 1
                return ('escape', c2)
            if c2 == 'n':
                self.pos += 1
                return ('char', '\n')
            if c2 == 't':
                self.pos += 1
                return ('char', '\t')
            if c2.isalpha() or c2.isdigit():
                raise ValueError(f"invalid escape in class \\{c2}")
            self.pos += 1
            return ('char', c2)
        self.pos += 1
        return ('char', c)

    def _try_quantifier(self, atom):
        if isinstance(atom, (_AnchorStart, _AnchorEnd)):
            # Check if next char is a quantifier (error)
            c = self._peek()
            if c in '*+?{':
                raise ValueError("cannot quantify anchor")
            return atom
        c = self._peek()
        if c is None:
            return atom
        if c == '*':
            self.pos += 1
            greedy = True
            if self._peek() == '?':
                self.pos += 1
                greedy = False
            self._check_no_quant_after()
            return _Quant(atom, 0, None, greedy)
        if c == '+':
            self.pos += 1
            greedy = True
            if self._peek() == '?':
                self.pos += 1
                greedy = False
            self._check_no_quant_after()
            return _Quant(atom, 1, None, greedy)
        if c == '?':
            self.pos += 1
            greedy = True
            if self._peek() == '?':
                self.pos += 1
                greedy = False
            self._check_no_quant_after()
            return _Quant(atom, 0, 1, greedy)
        if c == '{':
            return self._curly_quant(atom)
        return atom

    def _check_no_quant_after(self):
        c = self._peek()
        if c is not None and c in '*+?{':
            raise ValueError("quantifier after quantifier")

    def _curly_quant(self, atom):
        save = self.pos
        self.pos += 1  # skip {
        m_start = self.pos
        while self.pos < len(self.pat) and self.pat[self.pos].isdigit():
            self.pos += 1
        if self.pos == m_start:
            self.pos = save
            raise ValueError("invalid quantifier")
        m = int(self.pat[m_start:self.pos])
        n = m
        if self._peek() == ',':
            self.pos += 1
            n_start = self.pos
            while self.pos < len(self.pat) and self.pat[self.pos].isdigit():
                self.pos += 1
            if self.pos == n_start:
                n = None  # unbounded
            else:
                n = int(self.pat[n_start:self.pos])
        if self._peek() != '}':
            self.pos = save
            raise ValueError("invalid quantifier")
        self.pos += 1  # skip }
        if n is not None and m > n:
            raise ValueError("min > max in quantifier")
        greedy = True
        if self._peek() == '?':
            self.pos += 1
            greedy = False
        self._check_no_quant_after()
        return _Quant(atom, m, n, greedy)


class _Compiler:
    def __init__(self):
        self.code = []
        self.qid_counter = 0
        self.num_groups = 0

    def compile(self, ast, num_groups):
        self.num_groups = num_groups
        self._emit(ast)
        self.code.append((_OP_ACCEPT,))
        return self.code

    def _emit(self, node):
        if isinstance(node, _Seq):
            for item in node.items:
                self._emit(item)
        elif isinstance(node, _Alt):
            jmp_targets = []
            for i, branch in enumerate(node.branches):
                if i < len(node.branches) - 1:
                    split_idx = len(self.code)
                    self.code.append((_OP_SPLIT, 0, 0))
                    self._emit(branch)
                    jmp_idx = len(self.code)
                    self.code.append((_OP_JUMP, 0))
                    jmp_targets.append(jmp_idx)
                    self.code[split_idx] = (_OP_SPLIT, split_idx + 1, len(self.code))
                else:
                    self._emit(branch)
            end = len(self.code)
            for j in jmp_targets:
                self.code[j] = (_OP_JUMP, end)
        elif isinstance(node, _Group):
            if node.capturing:
                self.code.append((_OP_SAVE, node.gid))
                self._emit(node.child)
                self.code.append((_OP_SAVE_END, node.gid))
            else:
                self._emit(node.child)
        elif isinstance(node, _Lit):
            self.code.append((_OP_LIT, node.c))
        elif isinstance(node, _Any):
            self.code.append((_OP_ANY,))
        elif isinstance(node, _AnchorStart):
            self.code.append((_OP_ASSERT_START,))
        elif isinstance(node, _AnchorEnd):
            self.code.append((_OP_ASSERT_END,))
        elif isinstance(node, _Class):
            self.code.append((_OP_CLASS, node))
        elif isinstance(node, _Quant):
            self._emit_quant(node)
        else:
            raise ValueError("unknown node")

    def _emit_quant(self, node):
        lo = node.lo
        hi = node.hi
        greedy = node.greedy
        qid = self.qid_counter
        self.qid_counter += 1

        if lo == 0 and hi == 0:
            # x{0} matches empty, don't run child
            return

        # Forced iterations: emit child lo times
        # For efficiency, use a loop for forced part
        if lo > 0:
            # Loop: check count < lo, run child, inc, repeat
            loop_start = len(self.code)
            self.code.append((_OP_CHECK_LO, qid, lo, 0))  # if count >= lo, goto target
            self._emit(node.child)
            self.code.append((_OP_INC, qid))
            self.code.append((_OP_JUMP, loop_start))
            # Patch CHECK_LO target
            self.code[loop_start] = (_OP_CHECK_LO, qid, lo, len(self.code))

        # Optional loop
        if hi is None or hi > lo:
            if greedy:
                loop_start = len(self.code)
                split_idx = len(self.code)
                self.code.append((_OP_SPLIT, 0, 0))
                # try iteration
                if hi is not None:
                    self.code.append((_OP_CHECK_HI, qid, hi, 0))  # if count >= hi, goto stop
                self.code.append((_OP_CHECK_MARK, qid, 0))  # if pos == mark, goto stop
                self.code.append((_OP_MARK, qid))
                self._emit(node.child)
                self.code.append((_OP_INC, qid))
                self.code.append((_OP_JUMP, loop_start))
                stop_idx = len(self.code)
                self.code[split_idx] = (_OP_SPLIT, split_idx + 1, stop_idx)
                if hi is not None:
                    self.code[loop_start + 1] = (_OP_CHECK_HI, qid, hi, stop_idx)
                # Patch CHECK_MARK
                for i in range(loop_start + 2, stop_idx):
                    if self.code[i][0] == _OP_CHECK_MARK and self.code[i][2] == 0:
                        self.code[i] = (_OP_CHECK_MARK, qid, stop_idx)
                        break
            else:
                # Lazy
                loop_start = len(self.code)
                split_idx = len(self.code)
                self.code.append((_OP_SPLIT, 0, 0))
                # stop (first alternative)
                stop_idx = len(self.code)
                # try iteration (second alternative) - placed after stop
                # Actually for lazy: SPLIT(stop, iterate)
                # stop is the first target, iterate is the second
                # But we need stop to come first in the code...
                # Let me restructure: SPLIT points to stop_idx and iter_start
                # The code after SPLIT is the continuation (what follows quantifier)
                # But we don't know what follows yet...
                # Better: emit the loop, and the "stop" just falls through
                # SPLIT(iter_start, fall_through)
                # For lazy: SPLIT(fall_through, iter_start)
                # Actually the SPLIT semantics: try first target first, then second on backtrack
                # Lazy: try stop first → SPLIT(stop, iter)
                # But stop is "continue after quantifier" which is whatever comes next
                # Let me use: SPLIT(stop_target, iter_target) where stop_target = after the loop
                # We need to know where "after the loop" is...
                # Trick: put the iteration code BEFORE the loop start, and use JUMP
                # Actually let me restructure:

                # Remove the SPLIT we just added
                self.code.pop()  # remove the SPLIT
                # Emit: JUMP to stop, then iteration code, then JUMP back
                # No, that doesn't work for backtracking.

                # Correct approach for lazy:
                # loop_start: SPLIT(stop_target, iter_start)
                # stop_target: (what follows - we'll patch later, but it's just fall-through)
                # Actually, the SPLIT pushes both targets. First tried is stop_target.
                # If stop_target path fails, we backtrack to iter_start.
                # iter_start: CHECK_HI, CHECK_MARK, MARK, child, INC, JUMP(loop_start)
                # stop_target is just the code after the loop.

                # Problem: we don't know where "after the loop" is until we emit it.
                # Solution: emit iteration code first, then patch.

                iter_start = len(self.code) + 1  # after the SPLIT
                # Emit iteration code
                if hi is not None:
                    self.code.append((_OP_CHECK_HI, qid, hi, 0))  # patch to loop_end
                self.code.append((_OP_CHECK_MARK, qid, 0))  # patch to loop_end
                self.code.append((_OP_MARK, qid))
                self._emit(node.child)
                self.code.append((_OP_INC, qid))
                self.code.append((_OP_JUMP, loop_start))
                loop_end = len(self.code)
                # Now emit SPLIT at loop_start position
                self.code.insert(loop_start, (_OP_SPLIT, loop_end, iter_start))
                # Patch CHECK_HI and CHECK_MARK targets
                for i in range(iter_start, loop_end):
                    if self.code[i][0] == _OP_CHECK_HI and self.code[i][2] == 0:
                        self.code[i] = (_OP_CHECK_HI, qid, hi, loop_end)
                    elif self.code[i][0] == _OP_CHECK_MARK and self.code[i][2] == 0:
                        self.code[i] = (_OP_CHECK_MARK, qid, loop_end)
                        break
        # else: hi == lo, no optional loop needed (forced part already handled)


class Match:
    def __init__(self, s, spans):
        self._s = s
        self._spans = spans

    def span(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError("no such group")
        if n < 0 or n >= len(self._spans):
            raise IndexError("no such group")
        return self._spans[n]

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
        for i in range(1, len(self._spans)):
            s, e = self._spans[i]
            if s == -1:
                result.append(None)
            else:
                result.append(self._s[s:e])
        return tuple(result)


class Pattern:
    def __init__(self, code, num_groups):
        self._code = code
        self._num_groups = num_groups

    def fullmatch(self, s):
        return self._run(s, 0, True)

    def search(self, s):
        memo = set()
        for start in range(len(s) + 1):
            m = self._run(s, start, False, memo)
            if m is not None:
                return m
        return None

    def _run(self, s, start, fullmatch, memo=None):
        if memo is None:
            memo = set()
        code = self._code
        ng = self._num_groups
        n = len(s)
        nq = sum(1 for instr in code if instr[0] in (_OP_MARK, _OP_INC, _OP_CHECK_MARK, _OP_CHECK_HI, _OP_CHECK_LO))
        # Actually, count unique qids
        qids = set()
        for instr in code:
            if instr[0] in (_OP_MARK, _OP_INC, _OP_CHECK_MARK, _OP_CHECK_HI, _OP_CHECK_LO):
                qids.add(instr[1])
        max_qid = max(qids) + 1 if qids else 0

        # Stack entries: (pc, pos, captures_snapshot, qcounts_snapshot, qmarks_snapshot)
        stack = []
        pc = 0
        pos = start
        captures = [(-1, -1)] * (ng + 1)
        qcounts = [0] * max_qid
        qmarks = [None] * max_qid

        # For memo: key is (pc, pos, tuple of active quantifier states)
        # Simplified: (pc, pos) for unbounded, include count for bounded
        # Let's use (pc, pos, tuple(qcounts)) - but this might be too large
        # For the catastrophic patterns, qcounts varies but hi=inf so behavior is same
        # Normalize: for qid with hi=inf, set count to min(count, 1) in memo key
        # Actually let's just use (pc, pos) and accept potential issues with bounded quantifiers
        # For bounded quantifiers (hi <= 100), the extra work is bounded

        # Better memo key: include quantifier states that matter
        # For simplicity, use (pc, pos, tuple(qcounts)) but normalize unbounded counts

        # Determine which qids are bounded
        bounded_qids = set()
        for instr in code:
            if instr[0] == _OP_CHECK_HI:
                bounded_qids.add(instr[1])

        def memo_key(pc, pos, qcounts):
            if bounded_qids:
                normalized = []
                for i in range(max_qid):
                    if i in bounded_qids:
                        normalized.append(qcounts[i])
                    else:
                        normalized.append(min(qcounts[i], 1))
                return (pc, pos, tuple(normalized))
            return (pc, pos)

        def snapshot():
            return (pc, pos, tuple(captures), tuple(qcounts), tuple(qmarks))

        def restore(snap):
            nonlocal pc, pos, captures, qcounts, qmarks
            pc, pos, cap, qc, qm = snap
            captures = list(cap)
            qcounts = list(qc)
            qmarks = list(qm)

        max_steps = 5000000
        steps = 0

        while True:
            steps += 1
            if steps > max_steps:
                return None

            if pc >= len(code):
                return None

            instr = code[pc]
            op = instr[0]

            if op == _OP_LIT:
                c = instr[1]
                if pos < n and s[pos] == c:
                    pos += 1
                    pc += 1
                else:
                    if not stack:
                        memo.add(memo_key(pc, pos, qcounts))
                        return None
                    restore(stack.pop())
                    # After restore, the SPLIT that pushed this entry will try its second target
                    # Actually, restore sets pc to the saved pc which is the second target
                    # No wait - the SPLIT pushes (pc_after_second_target, ...) and sets pc to first target
                    # On backtrack, we restore to pc_after_second_target
                    # Hmm, let me reconsider the stack semantics.

            elif op == _OP_ANY:
                if pos < n and s[pos] != '\n':
                    pos += 1
                    pc += 1
                else:
                    if not stack:
                        memo.add(memo_key(pc, pos, qcounts))
                        return None
                    restore(stack.pop())

            elif op == _OP_CLASS:
                cls = instr[1]
                if pos < n:
                    ch = s[pos]
                    matched = False
                    if ch in cls.chars:
                        matched = True
                    if not matched:
                        for lo_c, hi_c in cls.ranges:
                            if lo_c <= ch <= hi_c:
                                matched = True
                                break
                    if not matched:
                        for esc in cls.escapes:
                            if esc == 'd' and ch.isdigit():
                                matched = True
                                break
                            elif esc == 'w' and ch in _WORD:
                                matched = True
                                break
                            elif esc == 's' and ch in _WS:
                                matched = True
                                break
                    if cls.negated:
                        matched = not matched
                    if matched:
                        pos += 1
                        pc += 1
                    else:
                        if not stack:
                            memo.add(memo_key(pc, pos, qcounts))
                            return None
                        restore(stack.pop())
                else:
                    if not stack:
                        memo.add(memo_key(pc, pos, qcounts))
                        return None
                    restore(stack.pop())

            elif op == _OP_ASSERT_START:
                if pos == 0:
                    pc += 1
                else:
                    if not stack:
                        memo.add(memo_key(pc, pos, qcounts))
                        return None
                    restore(stack.pop())

            elif op == _OP_ASSERT_END:
                if pos == n or (pos == n - 1 and s[pos] == '\n'):
                    pc += 1
                else:
                    if not stack:
                        memo.add(memo_key(pc, pos, qcounts))
                        return None
                    restore(stack.pop())

            elif op == _OP_SPLIT:
                _, target1, target2 = instr
                stack.append((target2, pos, tuple(captures), tuple(qcounts), tuple(qmarks)))
                pc = target1

            elif op == _OP_JUMP:
                pc = instr[1]

            elif op == _OP_SAVE:
                gid = instr[1]
                stack.append((pc + 1, pos, tuple(captures), tuple(qcounts), tuple(qmarks)))
                captures[gid] = (pos, -1)
                pc += 1

            elif op == _OP_SAVE_END:
                gid = instr[1]
                captures[gid] = (captures[gid][0], pos)
                pc += 1

            elif op == _OP_MARK:
                qid = instr[1]
                qmarks[qid] = pos
                pc += 1

            elif op == _OP_INC:
                qid = instr[1]
                qcounts[qid] += 1
                pc += 1

            elif op == _OP_CHECK_MARK:
                _, qid, target = instr
                if qmarks[qid] is not None and pos == qmarks[qid]:
                    pc = target
                else:
                    pc += 1

            elif op == _OP_CHECK_HI:
                _, qid, hi, target = instr
                if qcounts[qid] >= hi:
                    pc = target
                else:
                    pc += 1

            elif op == _OP_CHECK_LO:
                _, qid, lo, target = instr
                if qcounts[qid] >= lo:
                    pc = target
                else:
                    pc += 1

            elif op == _OP_ACCEPT:
                if fullmatch and pos != n:
                    if not stack:
                        memo.add(memo_key(pc, pos, qcounts))
                        return None
                    restore(stack.pop())
                else:
                    # Success! Build match
                    spans = [(-1, -1)] * (ng + 1)
                    spans[0] = (start, pos)
                    for i in range(1, ng + 1):
                        if captures[i][0] != -1 and captures[i][1] != -1:
                            spans[i] = captures[i]
                    return Match(s, spans)

            else:
                return None

            # Check memo after backtracking
            if stack:
                key = memo_key(pc, pos, qcounts)
                if key in memo:
                    # This state was already explored and failed, keep backtracking
                    while stack:
                        restore(stack.pop())
                        key = memo_key(pc, pos, qcounts)
                        if key not in memo:
                            break
                    else:
                        memo.add(memo_key(pc, pos, qcounts))
                        return None


def compile(pattern: str) -> Pattern:
    parser = _Parser(pattern)
    ast = parser.parse()
    compiler = _Compiler()
    code = compiler.compile(ast, parser.num_groups)
    return Pattern(code, parser.num_groups)
