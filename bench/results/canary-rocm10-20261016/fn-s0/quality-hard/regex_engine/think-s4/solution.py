import sys
sys.setrecursionlimit(100000)

# ==================== AST Nodes ====================

class _Lit:
    __slots__ = ('ch',)
    def __init__(self, ch): self.ch = ch

class _Dot:
    pass

class _Class:
    __slots__ = ('chars',)
    def __init__(self, chars): self.chars = chars

class _Start:
    pass

class _End:
    pass

class _Group:
    __slots__ = ('child', 'gid')
    def __init__(self, child, gid): self.child = child; self.gid = gid

class _Alt:
    __slots__ = ('branches',)
    def __init__(self, branches): self.branches = branches

class _Concat:
    __slots__ = ('items',)
    def __init__(self, items): self.items = items

class _Quant:
    __slots__ = ('child', 'lo', 'hi', 'greedy')
    def __init__(self, child, lo, hi, greedy):
        self.child = child; self.lo = lo; self.hi = hi; self.greedy = greedy

# ==================== Constants ====================

_DIGITS = frozenset('0123456789')
_WORD = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SPACE = frozenset(' \t\n\r\f\v')
_ALL_ASCII = frozenset(chr(c) for c in range(128))

def _escape_set(ch):
    if ch == 'd': return frozenset('0123456789')
    if ch == 'D': return _ALL_ASCII - frozenset('0123456789')
    if ch == 'w': return _WORD
    if ch == 'W': return _ALL_ASCII - _WORD
    if ch == 's': return _SPACE
    if ch == 'S': return _ALL_ASCII - _SPACE
    return frozenset()

# ==================== Parser ====================

class _Parser:
    def __init__(self, pattern):
        self.pat = pattern
        self.pos = 0
        self.ngroups = 0

    def parse(self):
        node = self._alt()
        if self.pos != len(self.pat):
            raise ValueError("Unexpected character at position %d" % self.pos)
        return node

    def _peek(self):
        return self.pat[self.pos] if self.pos < len(self.pat) else None

    def _advance(self):
        ch = self.pat[self.pos]
        self.pos += 1
        return ch

    def _alt(self):
        branches = [self._concat()]
        while self._peek() == '|':
            self._advance()
            branches.append(self._concat())
        return branches[0] if len(branches) == 1 else _Alt(branches)

    def _concat(self):
        items = []
        while True:
            ch = self._peek()
            if ch is None or ch == '|' or ch == ')':
                break
            items.append(self._quant())
        if not items:
            return _Concat([])
        return items[0] if len(items) == 1 else _Concat(items)

    def _quant(self):
        atom = self._atom()
        q = self._try_quantifier()
        if q is not None:
            greedy = True
            if self._peek() == '?':
                self._advance()
                greedy = False
            if self._is_quant_start():
                raise ValueError("Quantifier after quantifier")
            return _Quant(atom, q[0], q[1], greedy)
        return atom

    def _is_quant_start(self):
        ch = self._peek()
        if ch in ('*', '+', '?'):
            return True
        if ch == '{' and self._valid_brace():
            return True
        return False

    def _valid_brace(self):
        save = self.pos
        self.pos += 1
        m = self._read_digits()
        if m is None:
            self.pos = save
            return False
        ch = self._peek()
        if ch == '}':
            self.pos = save
            return True
        if ch == ',':
            self.pos += 1
            self._read_digits()
            if self._peek() == '}':
                self.pos = save
                return True
        self.pos = save
        return False

    def _try_quantifier(self):
        ch = self._peek()
        if ch == '*':
            self._advance()
            return (0, None)
        if ch == '+':
            self._advance()
            return (1, None)
        if ch == '?':
            self._advance()
            return (0, 1)
        if ch == '{':
            return self._brace_quant()
        return None

    def _brace_quant(self):
        self._advance()
        m = self._read_digits()
        if m is None:
            raise ValueError("Invalid quantifier: expected digit after '{'")
        ch = self._peek()
        if ch == '}':
            self._advance()
            return (m, m)
        if ch == ',':
            self._advance()
            n = self._read_digits()
            if n is not None:
                if self._peek() == '}':
                    self._advance()
                    if m > n:
                        raise ValueError("min > max in quantifier")
                    return (m, n)
                raise ValueError("Invalid quantifier: expected '}'")
            if self._peek() == '}':
                self._advance()
                return (m, None)
            raise ValueError("Invalid quantifier: expected '}'")
        raise ValueError("Invalid quantifier")

    def _read_digits(self):
        start = self.pos
        while self.pos < len(self.pat) and self.pat[self.pos] in _DIGITS:
            self.pos += 1
        if self.pos == start:
            return None
        return int(self.pat[start:self.pos])

    def _atom(self):
        ch = self._peek()
        if ch is None:
            return _Concat([])
        if ch == '(':
            return self._group()
        if ch == '[':
            return self._class()
        if ch == '.':
            self._advance()
            return _Dot()
        if ch == '^':
            self._advance()
            return _Start()
        if ch == '$':
            self._advance()
            return _End()
        if ch == '\\':
            return self._escape()
        if ch in ('*', '+', '?'):
            raise ValueError("Quantifier with nothing to repeat")
        if ch == '{':
            raise ValueError("Invalid quantifier")
        self._advance()
        return _Lit(ch)

    def _group(self):
        self._advance()
        if self._peek() == '?':
            self._advance()
            if self._peek() == ':':
                self._advance()
                child = self._alt()
                if self._peek() != ')':
                    raise ValueError("Unclosed group")
                self._advance()
                return _Group(child, 0)
            raise ValueError("Unsupported group syntax")
        self.ngroups += 1
        gid = self.ngroups
        child = self._alt()
        if self._peek() != ')':
            raise ValueError("Unclosed group")
        self._advance()
        return _Group(child, gid)

    def _escape(self):
        self._advance()
        if self.pos >= len(self.pat):
            raise ValueError("Backslash at end of pattern")
        ch = self._advance()
        if ch in 'dDwWsS':
            return _Class(_escape_set(ch))
        if ch == 'n':
            return _Lit('\n')
        if ch == 't':
            return _Lit('\t')
        if ch.isalpha() or ch.isdigit():
            raise ValueError("Invalid escape \\%s" % ch)
        return _Lit(ch)

    def _class(self):
        self._advance()
        negate = False
        if self._peek() == '^':
            negate = True
            self._advance()
        chars = set()
        # Leading ] is literal
        if self._peek() == ']':
            self._advance()
            if self._peek() == '-':
                self._advance()
                if self._peek() == ']':
                    chars.add(']')
                    chars.add('-')
                else:
                    t2, v2 = self._class_item()
                    if t2 == 'escape':
                        raise ValueError("Class escape as range endpoint")
                    if ord(']') > ord(v2):
                        raise ValueError("Invalid range")
                    for i in range(ord(']'), ord(v2) + 1):
                        chars.add(chr(i))
            else:
                chars.add(']')
        while True:
            if self.pos >= len(self.pat):
                raise ValueError("Unclosed character class")
            if self._peek() == ']':
                self._advance()
                break
            t1, v1 = self._class_item()
            if t1 == 'escape':
                if self._peek() == '-':
                    self._advance()
                    if self._peek() == ']':
                        chars.update(v1)
                        chars.add('-')
                    else:
                        raise ValueError("Class escape cannot be start of range")
                else:
                    chars.update(v1)
            else:
                c1 = v1
                if self._peek() == '-':
                    self._advance()
                    if self._peek() == ']':
                        chars.add(c1)
                        chars.add('-')
                    else:
                        t2, v2 = self._class_item()
                        if t2 == 'escape':
                            raise ValueError("Class escape as range endpoint")
                        c2 = v2
                        if ord(c1) > ord(c2):
                            raise ValueError("Invalid range")
                        for i in range(ord(c1), ord(c2) + 1):
                            chars.add(chr(i))
                else:
                    chars.add(c1)
        if negate:
            chars = set(_ALL_ASCII) - chars
        return _Class(frozenset(chars))

    def _class_item(self):
        ch = self._peek()
        if ch == '\\':
            self._advance()
            if self.pos >= len(self.pat):
                raise ValueError("Backslash at end of pattern")
            ech = self._advance()
            if ech in 'dDwWsS':
                return ('escape', _escape_set(ech))
            if ech == 'n':
                return ('char', '\n')
            if ech == 't':
                return ('char', '\t')
            if ech.isalpha() or ech.isdigit():
                raise ValueError("Invalid escape in class: \\%s" % ech)
            return ('char', ech)
        return ('char', self._advance())

# ==================== Compiler (AST -> Bytecode) ====================

class _Compiler:
    def __init__(self):
        self.code = []
        self.nquant = 0

    def compile(self, node):
        self._emit(node)
        self.code.append(('match',))
        return self.code

    def _emit(self, node):
        if isinstance(node, _Lit):
            self.code.append(('char', node.ch))
        elif isinstance(node, _Dot):
            self.code.append(('any',))
        elif isinstance(node, _Class):
            self.code.append(('class', node.chars))
        elif isinstance(node, _Start):
            self.code.append(('start',))
        elif isinstance(node, _End):
            self.code.append(('end',))
        elif isinstance(node, _Group):
            if node.gid == 0:
                self._emit(node.child)
            else:
                self.code.append(('gopen', node.gid))
                self._emit(node.child)
                self.code.append(('gclose', node.gid))
        elif isinstance(node, _Concat):
            for item in node.items:
                self._emit(item)
        elif isinstance(node, _Alt):
            self._emit_alt(node.branches)
        elif isinstance(node, _Quant):
            self._emit_quant(node)

    def _emit_alt(self, branches):
        if len(branches) == 1:
            self._emit(branches[0])
            return
        split_idx = len(self.code)
        self.code.append(None)
        self._emit(branches[0])
        jump_idx = len(self.code)
        self.code.append(None)
        rest_idx = len(self.code)
        self._emit_alt(branches[1:])
        end_idx = len(self.code)
        self.code[split_idx] = ('split', split_idx + 1, rest_idx)
        self.code[jump_idx] = ('jump', end_idx)

    def _emit_quant(self, node):
        qid = self.nquant
        self.nquant += 1
        lo, hi, greedy = node.lo, node.hi, node.greedy
        if hi is not None and hi == 0:
            return
        # Forced iterations
        for _ in range(lo):
            self._emit(node.child)
        # Initialize quant state
        self.code.append(('qset', qid, lo))
        if greedy:
            self._emit_greedy(node, qid, hi)
        else:
            self._emit_lazy(node, qid, hi)

    def _emit_greedy(self, node, qid, hi):
        l0 = len(self.code)
        check_idx = len(self.code)
        self.code.append(('check', qid, 0))
        cchk_idx = None
        if hi is not None:
            cchk_idx = len(self.code)
            self.code.append(('cchk', qid, hi, 0))
        split_idx = len(self.code)
        self.code.append(None)
        body_addr = len(self.code)
        self.code.append(('mark', qid))
        self._emit(node.child)
        self.code.append(('inc', qid))
        self.code.append(('jump', l0))
        after_addr = len(self.code)
        self.code[check_idx] = ('check', qid, after_addr)
        if cchk_idx is not None:
            self.code[cchk_idx] = ('cchk', qid, hi, after_addr)
        self.code[split_idx] = ('split', body_addr, after_addr)

    def _emit_lazy(self, node, qid, hi):
        l0 = len(self.code)
        check_idx = len(self.code)
        self.code.append(('check', qid, 0))
        cchk_idx = None
        if hi is not None:
            cchk_idx = len(self.code)
            self.code.append(('cchk', qid, hi, 0))
        split_idx = len(self.code)
        self.code.append(None)
        after_addr = len(self.code)
        body_addr = len(self.code)
        self.code.append(('mark', qid))
        self._emit(node.child)
        self.code.append(('inc', qid))
        self.code.append(('jump', l0))
        fail_addr = len(self.code)
        self.code.append(('fail',))
        self.code[check_idx] = ('check', qid, fail_addr)
        if cchk_idx is not None:
            self.code[cchk_idx] = ('cchk', qid, hi, fail_addr)
        self.code[split_idx] = ('split', after_addr, body_addr)

# ==================== VM ====================

def _run_vm(code, s, start, fullmatch, ngroups, memo):
    slen = len(s)
    pc = 0
    pos = start
    captures = [None] * ngroups
    quant = {}
    undo = []
    bt = []

    def do_backtrack():
        while bt:
            npc, npos, ulen = bt.pop()
            while len(undo) > ulen:
                entry = undo.pop()
                if entry[0] == 'c':
                    captures[entry[1]] = entry[2]
                else:
                    qid, old = entry[1], entry[2]
                    if old is None:
                        quant.pop(qid, None)
                    else:
                        quant[qid] = old
            if (npc, npos) in memo:
                continue
            return npc, npos
        return None

    while True:
        key = (pc, pos)
        if key in memo:
            r = do_backtrack()
            if r is None:
                return None
            pc, pos = r
            continue

        instr = code[pc]
        op = instr[0]

        if op == 'char':
            if pos < slen and s[pos] == instr[1]:
                pos += 1
                pc += 1
            else:
                memo.add(key)
                r = do_backtrack()
                if r is None:
                    return None
                pc, pos = r

        elif op == 'class':
            if pos < slen and s[pos] in instr[1]:
                pos += 1
                pc += 1
            else:
                memo.add(key)
                r = do_backtrack()
                if r is None:
                    return None
                pc, pos = r

        elif op == 'any':
            if pos < slen and s[pos] != '\n':
                pos += 1
                pc += 1
            else:
                memo.add(key)
                r = do_backtrack()
                if r is None:
                    return None
                pc, pos = r

        elif op == 'start':
            if pos == 0:
                pc += 1
            else:
                memo.add(key)
                r = do_backtrack()
                if r is None:
                    return None
                pc, pos = r

        elif op == 'end':
            if pos == slen or (pos == slen - 1 and s[pos] == '\n'):
                pc += 1
            else:
                memo.add(key)
                r = do_backtrack()
                if r is None:
                    return None
                pc, pos = r

        elif op == 'gopen':
            gid = instr[1]
            undo.append(('c', gid, captures[gid]))
            captures[gid] = (pos, None)
            pc += 1

        elif op == 'gclose':
            gid = instr[1]
            undo.append(('c', gid, captures[gid]))
            captures[gid] = (captures[gid][0], pos)
            pc += 1

        elif op == 'split':
            bt.append((instr[2], pos, len(undo)))
            pc = instr[1]

        elif op == 'jump':
            pc = instr[1]

        elif op == 'mark':
            qid = instr[1]
            if qid not in quant:
                quant[qid] = [0, None]
            undo.append(('q', qid, quant[qid][:]))
            quant[qid][1] = pos
            pc += 1

        elif op == 'check':
            qid = instr[1]
            if qid in quant and quant[qid][1] == pos:
                pc = instr[2]
            else:
                pc += 1

        elif op == 'inc':
            qid = instr[1]
            undo.append(('q', qid, quant[qid][:]))
            quant[qid][0] += 1
            pc += 1

        elif op == 'cchk':
            qid = instr[1]
            if qid in quant and quant[qid][0] >= instr[2]:
                pc = instr[3]
            else:
                pc += 1

        elif op == 'qset':
            qid = instr[1]
            val = instr[2]
            undo.append(('q', qid, quant.get(qid)))
            quant[qid] = [val, None]
            pc += 1

        elif op == 'fail':
            memo.add(key)
            r = do_backtrack()
            if r is None:
                return None
            pc, pos = r

        elif op == 'match':
            if fullmatch and pos != slen:
                memo.add(key)
                r = do_backtrack()
                if r is None:
                    return None
                pc, pos = r
            else:
                return Match(s, captures[:], start, pos)

        else:
            raise RuntimeError("Unknown opcode: %s" % op)

# ==================== Match ====================

class Match:
    def __init__(self, s, captures, start, end):
        self._s = s
        self._captures = captures
        self._start = start
        self._end = end

    def span(self, n=0):
        if n == 0:
            return (self._start, self._end)
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError("no such group")
        if n < 0 or n > len(self._captures):
            raise IndexError("no such group: %d" % n)
        cap = self._captures[n - 1]
        if cap is None:
            return (-1, -1)
        return (cap[0], cap[1])

    def start(self, n=0):
        return self.span(n)[0]

    def end(self, n=0):
        return self.span(n)[1]

    def group(self, n=0):
        if n == 0:
            return self._s[self._start:self._end]
        if not isinstance(n, int) or isinstance(n, bool):
            raise IndexError("no such group")
        if n < 0 or n > len(self._captures):
            raise IndexError("no such group: %d" % n)
        cap = self._captures[n - 1]
        if cap is None:
            return None
        return self._s[cap[0]:cap[1]]

    def groups(self):
        result = []
        for cap in self._captures:
            if cap is None:
                result.append(None)
            else:
                result.append(self._s[cap[0]:cap[1]])
        return tuple(result)

# ==================== Pattern ====================

class Pattern:
    def __init__(self, code, ngroups):
        self._code = code
        self._ngroups = ngroups

    def fullmatch(self, s):
        memo = set()
        return _run_vm(self._code, s, 0, True, self._ngroups, memo)

    def search(self, s):
        memo = set()
        for start in range(len(s) + 1):
            result = _run_vm(self._code, s, start, False, self._ngroups, memo)
            if result is not None:
                return result
        return None

# ==================== Public API ====================

def compile(pattern: str) -> Pattern:
    parser = _Parser(pattern)
    ast = parser.parse()
    compiler = _Compiler()
    code = compiler.compile(ast)
    return Pattern(code, parser.ngroups)
