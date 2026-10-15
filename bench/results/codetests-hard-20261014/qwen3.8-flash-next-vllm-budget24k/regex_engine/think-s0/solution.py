class Match:
    def __init__(self, s, groups):
        self._s = s
        self._groups = groups

    def span(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n >= len(self._groups):
            raise IndexError("no such group")
        g = self._groups[n]
        if g is None:
            return (-1, -1)
        return g

    def start(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n >= len(self._groups):
            raise IndexError("no such group")
        g = self._groups[n]
        if g is None:
            return -1
        return g[0]

    def end(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n >= len(self._groups):
            raise IndexError("no such group")
        g = self._groups[n]
        if g is None:
            return -1
        return g[1]

    def group(self, n=0):
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n >= len(self._groups):
            raise IndexError("no such group")
        g = self._groups[n]
        if g is None:
            return None
        return self._s[g[0]:g[1]]

    def groups(self):
        result = []
        for g in self._groups[1:]:
            if g is None:
                result.append(None)
            else:
                result.append(self._s[g[0]:g[1]])
        return tuple(result)


class Pattern:
    def __init__(self, program, num_groups):
        self._program = program
        self._num_groups = num_groups

    def fullmatch(self, s):
        result = _run(self._program, s, 0, self._num_groups, require_full=True)
        if result is None:
            return None
        return Match(s, result)

    def search(self, s):
        for start in range(len(s) + 1):
            result = _run(self._program, s, start, self._num_groups, require_full=False)
            if result is not None:
                return Match(s, result)
        return None


# --- AST Nodes ---

class _Lit:
    def __init__(self, ch): self.ch = ch

class _Any: pass

class _Class:
    def __init__(self, items, negated): self.items = items; self.negated = negated

class _Group:
    def __init__(self, idx, child): self.idx = idx; self.child = child

class _NonCap:
    def __init__(self, child): self.child = child

class _Seq:
    def __init__(self, children): self.children = children

class _Alt:
    def __init__(self, branches): self.branches = branches

class _Quant:
    def __init__(self, child, lo, hi, greedy): self.child = child; self.lo = lo; self.hi = hi; self.greedy = greedy

class _AssertStart: pass

class _AssertEnd: pass


# --- Parser ---

class _Parser:
    def __init__(self, pattern):
        self.p = pattern
        self.pos = 0
        self.num_groups = 0
        self._qid = 0

    def next_qid(self):
        self._qid += 1
        return self._qid

    def parse(self):
        node = self._parse_alt()
        if self.pos != len(self.p):
            raise ValueError("unexpected character")
        return node

    def _parse_alt(self):
        branches = [self._parse_seq()]
        while self.pos < len(self.p) and self.p[self.pos] == '|':
            self.pos += 1
            branches.append(self._parse_seq())
        if len(branches) == 1:
            return branches[0]
        return _Alt(branches)

    def _parse_seq(self):
        items = []
        while self.pos < len(self.p) and self.p[self.pos] not in ('|', ')'):
            items.append(self._parse_quantified())
        if len(items) == 0:
            return _Seq([])
        if len(items) == 1:
            return items[0]
        return _Seq(items)

    def _parse_quantified(self):
        atom, is_anchor = self._parse_atom()
        if atom is None:
            return None
        # Check for quantifier
        if self.pos < len(self.p) and self.p[self.pos] in ('*', '+', '?', '{'):
            if is_anchor:
                raise ValueError("cannot quantify anchor")
            quant = self._parse_quantifier()
            if quant is not None:
                if atom is None:
                    raise ValueError("nothing to repeat")
                return _Quant(atom, quant[0], quant[1], quant[2])
        return atom

    def _parse_quantifier(self):
        ch = self.p[self.pos]
        if ch == '*':
            self.pos += 1
            greedy = True
            if self.pos < len(self.p) and self.p[self.pos] == '?':
                self.pos += 1
                greedy = False
            if self.pos < len(self.p) and self.p[self.pos] in ('*', '+', '?', '{'):
                raise ValueError("multiple quantifiers")
            return (0, None, greedy)
        elif ch == '+':
            self.pos += 1
            greedy = True
            if self.pos < len(self.p) and self.p[self.pos] == '?':
                self.pos += 1
                greedy = False
            if self.pos < len(self.p) and self.p[self.pos] in ('*', '+', '?', '{'):
                raise ValueError("multiple quantifiers")
            return (1, None, greedy)
        elif ch == '?':
            self.pos += 1
            greedy = True
            if self.pos < len(self.p) and self.p[self.pos] == '?':
                self.pos += 1
                greedy = False
            if self.pos < len(self.p) and self.p[self.pos] in ('*', '+', '?', '{'):
                raise ValueError("multiple quantifiers")
            return (0, 1, greedy)
        elif ch == '{':
            return self._parse_brace()
        return None

    def _parse_brace(self):
        start = self.pos
        self.pos += 1  # skip {
        # Parse m
        m_start = self.pos
        while self.pos < len(self.p) and self.p[self.pos].isdigit():
            self.pos += 1
        if self.pos == m_start:
            self.pos = start
            return None  # not a valid quantifier, treat { as literal
        m = int(self.p[m_start:self.pos])
        # Parse ,n or ,} or }
        if self.pos < len(self.p) and self.p[self.pos] == ',':
            self.pos += 1
            n_start = self.pos
            while self.pos < len(self.p) and self.p[self.pos].isdigit():
                self.pos += 1
            if self.pos < len(self.p) and self.p[self.pos] == '}':
                self.pos += 1
                if n_start == self.pos - 1:
                    n = None  # {m,}
                else:
                    n = int(self.p[n_start:self.pos - 1])
                    if n < m:
                        raise ValueError("min repeat greater than max repeat")
            else:
                self.pos = start
                return None
        elif self.pos < len(self.p) and self.p[self.pos] == '}':
            self.pos += 1
            n = m
        else:
            self.pos = start
            return None
        # Check for lazy ?
        greedy = True
        if self.pos < len(self.p) and self.p[self.pos] == '?':
            self.pos += 1
            greedy = False
        if self.pos < len(self.p) and self.p[self.pos] in ('*', '+', '?', '{'):
            raise ValueError("multiple quantifiers")
        return (m, n, greedy)

    def _parse_atom(self):
        if self.pos >= len(self.p):
            return None, False
        ch = self.p[self.pos]
        if ch == '(':
            return self._parse_group(), False
        elif ch == '[':
            return self._parse_class(), False
        elif ch == '.':
            self.pos += 1
            return _Any(), False
        elif ch == '^':
            self.pos += 1
            return _AssertStart(), True
        elif ch == '$':
            self.pos += 1
            return _AssertEnd(), True
        elif ch == '\\':
            return self._parse_escape(), False
        elif ch in ('*', '+', '?'):
            raise ValueError("nothing to repeat")
        elif ch == '{':
            # Try to parse as quantifier
            q = self._parse_brace()
            if q is not None:
                raise ValueError("nothing to repeat")
            # It's a literal {
            self.pos += 1
            return _Lit('{'), False
        elif ch == ')':
            raise ValueError("unbalanced parenthesis")
        elif ch == ']':
            self.pos += 1
            return _Lit(']'), False
        else:
            self.pos += 1
            return _Lit(ch), False

    def _parse_escape(self):
        self.pos += 1  # skip backslash
        if self.pos >= len(self.p):
            raise ValueError("backslash at end of pattern")
        ch = self.p[self.pos]
        if ch == 'd':
            self.pos += 1
            return _Class([('d',)], False)
        elif ch == 'D':
            self.pos += 1
            return _Class([('d',)], True)
        elif ch == 'w':
            self.pos += 1
            return _Class([('w',)], False)
        elif ch == 'W':
            self.pos += 1
            return _Class([('w',)], True)
        elif ch == 's':
            self.pos += 1
            return _Class([('s',)], False)
        elif ch == 'S':
            self.pos += 1
            return _Class([('s',)], True)
        elif ch == 'n':
            self.pos += 1
            return _Lit('\n')
        elif ch == 't':
            self.pos += 1
            return _Lit('\t')
        elif ch.isalpha() or ch.isdigit():
            raise ValueError(f"invalid escape \\{ch}")
        else:
            self.pos += 1
            return _Lit(ch)

    def _parse_group(self):
        self.pos += 1  # skip (
        if self.pos + 1 < len(self.p) and self.p[self.pos] == '?' and self.p[self.pos + 1] == ':':
            self.pos += 2
            child = self._parse_alt()
            if self.pos >= len(self.p) or self.p[self.pos] != ')':
                raise ValueError("unbalanced parenthesis")
            self.pos += 1
            return _NonCap(child)
        elif self.pos < len(self.p) and self.p[self.pos] == '?':
            raise ValueError("unsupported group syntax")
        else:
            self.num_groups += 1
            idx = self.num_groups
            child = self._parse_alt()
            if self.pos >= len(self.p) or self.p[self.pos] != ')':
                raise ValueError("unbalanced parenthesis")
            self.pos += 1
            return _Group(idx, child)

    def _parse_class(self):
        self.pos += 1  # skip [
        negated = False
        if self.pos < len(self.p) and self.p[self.pos] == '^':
            negated = True
            self.pos += 1
        items = []
        first = True
        while True:
            if self.pos >= len(self.p):
                raise ValueError("unterminated character class")
            if self.p[self.pos] == ']' and not first:
                self.pos += 1
                break
            first = False
            # Parse one item
            if self.p[self.pos] == '\\':
                self.pos += 1
                if self.pos >= len(self.p):
                    raise ValueError("backslash at end of pattern")
                ch = self.p[self.pos]
                if ch in ('d', 'D', 'w', 'W', 's', 'S'):
                    self.pos += 1
                    items.append((ch.lower(),))
                    # Check for invalid range after class escape
                    if self.pos < len(self.p) and self.p[self.pos] == '-':
                        if self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']':
                            raise ValueError("invalid range in character class")
                        elif self.pos + 1 >= len(self.p):
                            raise ValueError("unterminated character class")
                        else:
                            # '-' followed by ']' is literal '-'
                            items.append(('-',))
                            self.pos += 2
                elif ch == 'n':
                    self.pos += 1
                    c1 = '\n'
                    items.append(self._parse_range_or_single(c1))
                elif ch == 't':
                    self.pos += 1
                    c1 = '\t'
                    items.append(self._parse_range_or_single(c1))
                elif ch.isalpha() or ch.isdigit():
                    raise ValueError(f"invalid escape in class \\{ch}")
                else:
                    self.pos += 1
                    c1 = ch
                    items.append(self._parse_range_or_single(c1))
            elif self.p[self.pos] == ']':
                # first char ']' is literal
                self.pos += 1
                items.append(self._parse_range_or_single(']'))
            else:
                c1 = self.p[self.pos]
                self.pos += 1
                items.append(self._parse_range_or_single(c1))
        return _Class(items, negated)

    def _parse_range_or_single(self, c1):
        if self.pos < len(self.p) and self.p[self.pos] == '-':
            if self.pos + 1 < len(self.p) and self.p[self.pos + 1] != ']':
                # It's a range
                self.pos += 1  # skip -
                c2 = self._parse_class_char()
                if ord(c1) > ord(c2):
                    raise ValueError("bad character range")
                return (c1, c2)
            elif self.pos + 1 >= len(self.p):
                raise ValueError("unterminated character class")
            else:
                # '-' followed by ']' is literal '-'
                self.pos += 1  # skip -
                return (c1,)
        return (c1,)

    def _parse_class_char(self):
        if self.pos >= len(self.p):
            raise ValueError("unterminated character class")
        if self.p[self.pos] == '\\':
            self.pos += 1
            if self.pos >= len(self.p):
                raise ValueError("backslash at end of pattern")
            ch = self.p[self.pos]
            if ch in ('d', 'D', 'w', 'W', 's', 'S'):
                raise ValueError("invalid range endpoint")
            elif ch == 'n':
                self.pos += 1
                return '\n'
            elif ch == 't':
                self.pos += 1
                return '\t'
            elif ch.isalpha() or ch.isdigit():
                raise ValueError(f"invalid escape in class \\{ch}")
            else:
                self.pos += 1
                return ch
        else:
            ch = self.p[self.pos]
            self.pos += 1
            return ch


# --- Compiler ---

def _compile_node(node, program, qid_counter):
    if isinstance(node, _Seq):
        for child in node.children:
            _compile_node(child, program, qid_counter)
    elif isinstance(node, _Alt):
        if len(node.branches) == 1:
            _compile_node(node.branches[0], program, qid_counter)
        else:
            jumps = []
            for i, branch in enumerate(node.branches):
                if i < len(node.branches) - 1:
                    split_pc = len(program)
                    program.append(('SPLIT', 0, 0))  # placeholder
                    _compile_node(branch, program, qid_counter)
                    jump_pc = len(program)
                    program.append(('JUMP', 0))  # placeholder
                    jumps.append((split_pc, jump_pc))
                else:
                    _compile_node(branch, program, qid_counter)
            end_pc = len(program)
            for split_pc, jump_pc in jumps:
                program[split_pc] = ('SPLIT', split_pc + 1, jump_pc + 1)
                program[jump_pc] = ('JUMP', end_pc - jump_pc)
    elif isinstance(node, _Group):
        program.append(('SAVE_START', node.idx))
        _compile_node(node.child, program, qid_counter)
        program.append(('SAVE_END', node.idx))
    elif isinstance(node, _NonCap):
        _compile_node(node.child, program, qid_counter)
    elif isinstance(node, _Quant):
        _compile_quant(node, program, qid_counter)
    elif isinstance(node, _Lit):
        program.append(('CHAR', node.ch))
    elif isinstance(node, _Any):
        program.append(('ANY',))
    elif isinstance(node, _Class):
        program.append(('CLASS', node.items, node.negated))
    elif isinstance(node, _AssertStart):
        program.append(('ASSERT_START',))
    elif isinstance(node, _AssertEnd):
        program.append(('ASSERT_END',))


def _compile_quant(node, program, qid_counter):
    qid = next(qid_counter)
    lo, hi, greedy = node.lo, node.hi, node.greedy

    if lo == 0 and hi == 0:
        # x{0} - matches empty, don't compile body
        return

    # Inline forced iterations
    for _ in range(lo):
        _compile_node(node.child, program, qid_counter)

    if hi is not None and hi == lo:
        # Exact count, no optional part needed
        return

    # Optional loop
    if greedy:
        loop_pc = len(program)
        program.append(('QCHECK', qid, lo, hi, True, 0, 0))  # placeholders
        body_start = len(program)
        _compile_node(node.child, program, qid_counter)
        program.append(('QEND', qid, loop_pc))
        after_pc = len(program)
        program[loop_pc] = ('QCHECK', qid, lo, hi, True, body_start, after_pc)
    else:
        loop_pc = len(program)
        program.append(('QCHECK', qid, lo, hi, False, 0, 0))  # placeholders
        lazy_body_pc = loop_pc + 1
        # QCHECK for lazy: SPLIT(after, lazy_body)
        # lazy_body: check hi/mark, then body
        # We'll handle lazy_body as a separate instruction
        body_start = len(program) + 2  # after QCHECK and QLAZY_BODY
        program.append(('QLAZY_BODY', qid, hi, 0, 0))  # placeholder for body_start, loop_back
        _compile_node(node.child, program, qid_counter)
        program.append(('QEND', qid, loop_pc))
        after_pc = len(program)
        program[loop_pc] = ('QCHECK', qid, lo, hi, False, body_start, after_pc)
        program[lazy_body_pc] = ('QLAZY_BODY', qid, hi, body_start, loop_pc)


# --- VM Execution ---

def _run(program, s, start_pos, num_groups, require_full):
    n = len(s)
    captures = [None] * (num_groups + 1)  # 0..num_groups
    quant_states = {}  # qid -> [c, mark]
    memo = {}  # qid -> set of (pos, c) that failed

    def get_memo(qid):
        if qid not in memo:
            memo[qid] = set()
        return memo[qid]

    def get_qstate(qid):
        if qid not in quant_states:
            quant_states[qid] = [0, None]
        return quant_states[qid]

    stack = []  # backtrack stack

    pc = 0
    pos = start_pos

    while True:
        instr = program[pc]
        op = instr[0]

        if op == 'CHAR':
            if pos < n and s[pos] == instr[1]:
                pos += 1
                pc += 1
            else:
                if not _backtrack():
                    return None
                continue

        elif op == 'ANY':
            if pos < n and s[pos] != '\n':
                pos += 1
                pc += 1
            else:
                if not _backtrack():
                    return None
                continue

        elif op == 'CLASS':
            if pos < n and _match_class(instr[1], instr[2], s[pos]):
                pos += 1
                pc += 1
            else:
                if not _backtrack():
                    return None
                continue

        elif op == 'ASSERT_START':
            if pos == 0:
                pc += 1
            else:
                if not _backtrack():
                    return None
                continue

        elif op == 'ASSERT_END':
            if pos == n or (pos == n - 1 and s[pos] == '\n'):
                pc += 1
            else:
                if not _backtrack():
                    return None
                continue

        elif op == 'SAVE_START':
            stack.append(('SAVE_START', instr[1], pos))
            pc += 1

        elif op == 'SAVE_END':
            g = instr[1]
            # Find matching SAVE_START on stack
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == 'SAVE_START' and stack[i][1] == g:
                    start = stack[i][2]
                    captures[g] = (start, pos)
                    del stack[i]
                    break
            pc += 1

        elif op == 'SPLIT':
            # Push alternative onto stack
            stack.append(('RESUME', instr[2], pos, captures[:], dict(quant_states)))
            pc = instr[1]

        elif op == 'JUMP':
            pc += instr[1]

        elif op == 'MATCH':
            if require_full:
                if pos == n:
                    captures[0] = (start_pos, pos)
                    return captures[:]
                else:
                    if not _backtrack():
                        return None
                    continue
            else:
                captures[0] = (start_pos, pos)
                return captures[:]

        elif op == 'QCHECK':
            _, qid, lo, hi, greedy, body_start, after_pc = instr
            qs = get_qstate(qid)
            c, mark = qs[0], qs[1]

            m = get_memo(qid)
            if (pos, c) in m:
                if not _backtrack():
                    return None
                continue

            if c < lo:
                # Forced iteration
                pc = body_start
                continue

            if greedy:
                if hi is not None and c >= hi:
                    pc = after_pc
                    continue
                if mark is not None and pos == mark:
                    pc = after_pc
                    continue
                qs[1] = pos  # set mark
                # Push after as fallback, and QMARK for memo
                stack.append(('RESUME', after_pc, pos, captures[:], dict(quant_states)))
                stack.append(('QMARK', qid, pos, c))
                pc = body_start
            else:
                # Lazy: try after first
                stack.append(('RESUME', instr[2 + 3], pos, captures[:], dict(quant_states)))  # lazy_body handled by QLAZY_BODY
                stack.append(('QMARK', qid, pos, c))
                pc = after_pc

        elif op == 'QLAZY_BODY':
            _, qid, hi, body_start, loop_back = instr
            qs = get_qstate(qid)
            c, mark = qs[0], qs[1]
            if hi is not None and c >= hi:
                if not _backtrack():
                    return None
                continue
            if mark is not None and pos == mark:
                if not _backtrack():
                    return None
                continue
            qs[1] = pos  # set mark
            pc = body_start

        elif op == 'QEND':
            _, qid, loop_back = instr
            qs = get_qstate(qid)
            qs[0] += 1
            pc = loop_back

        else:
            raise ValueError(f"unknown instruction: {op}")

    def _backtrack():
        while stack:
            entry = stack.pop()
            if entry[0] == 'QMARK':
                _, qid, mpos, mc = entry
                get_memo(qid).add((mpos, mc))
                continue
            elif entry[0] == 'SAVE_START':
                # Shouldn't normally be popped during backtrack, but handle gracefully
                continue
            elif entry[0] == 'RESUME':
                _, epc, epos, ecaps, eqs = entry
                pc = epc
                pos = epos
                captures[:] = ecaps
                quant_states.clear()
                quant_states.update(eqs)
                return True
        return False


def _match_class(items, negated, ch):
    result = False
    for item in items:
        if len(item) == 1:
            tag = item[0]
            if tag == 'd':
                if ch.isdigit():
                    result = True; break
            elif tag == 'w':
                if ch.isalnum() or ch == '_':
                    result = True; break
            elif tag == 's':
                if ch in ' \t\n\r\x0b\x0c':
                    result = True; break
            elif tag == '-':
                if ch == '-':
                    result = True; break
            else:
                if ch == tag:
                    result = True; break
        elif len(item) == 2:
            if item[0] <= ch <= item[1]:
                result = True; break
    if negated:
        return not result
    return result


def compile(pattern):
    parser = _Parser(pattern)
    ast = parser.parse()
    program = []
    qid_counter = iter(range(1, 1000000))
    _compile_node(ast, program, qid_counter)
    program.append(('MATCH',))
    return Pattern(program, parser.num_groups)
