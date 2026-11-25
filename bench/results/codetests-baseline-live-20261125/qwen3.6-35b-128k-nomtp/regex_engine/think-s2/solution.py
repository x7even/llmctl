import sys

sys.setrecursionlimit(10000)

DIGITS = set('0123456789')
WORD = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
WHITESPACE = set(' \t\n\r\f\v')
ALL = set(chr(i) for i in range(256))

class Node: pass
class Literal(Node):
    def __init__(self, c): self.c = c
class Dot(Node): pass
class Class(Node):
    def __init__(self, chars, neg=False): self.chars = chars; self.neg = neg
class Start(Node): pass
class End(Node): pass
class Group(Node):
    def __init__(self, gid, body): self.gid = gid; self.body = body
class Alt(Node):
    def __init__(self, left, right): self.left = left; self.right = right
class Quant(Node):
    def __init__(self, atom, lo, hi, lazy=False): self.atom = atom; self.lo = lo; self.hi = hi; self.lazy = lazy
class Concat(Node):
    def __init__(self, children): self.children = children
class Empty(Node): pass

class Parser:
    def __init__(self, pat):
        self.pat = pat
        self.i = 0
        self.gid = 0
        
    def parse(self):
        node = self.parse_expr()
        if self.i < len(self.pat):
            raise ValueError("Unexpected character")
        return node
        
    def parse_expr(self):
        left = self.parse_concat()
        while self.i < len(self.pat) and self.pat[self.i] == '|':
            self.i += 1
            right = self.parse_concat()
            left = Alt(left, right)
        return left
        
    def parse_concat(self):
        children = []
        while self.i < len(self.pat) and self.pat[self.i] not in '|)':
            children.append(self.parse_quant())
        if not children: return Empty()
        if len(children) == 1: return children[0]
        return Concat(children)
        
    def parse_quant(self):
        atom = self.parse_atom()
        if isinstance(atom, (Start, End, Empty)):
            if self.i < len(self.pat) and self.pat[self.i] in '*+?{':
                raise ValueError("Quantifier with nothing to repeat")
        elif isinstance(atom, Quant):
            if self.i < len(self.pat) and self.pat[self.i] in '*+?{':
                raise ValueError("Quantifier after quantifier")
                
        if self.i < len(self.pat) and self.pat[self.i] in '*+?':
            q = self.pat[self.i]
            self.i += 1
            lazy = False
            if self.i < len(self.pat) and self.pat[self.i] == '?':
                lazy = True
                self.i += 1
            if q == '*': lo, hi = 0, float('inf')
            elif q == '+': lo, hi = 1, float('inf')
            else: lo, hi = 0, 1
            return Quant(atom, lo, hi, lazy)
        elif self.i < len(self.pat) and self.pat[self.i] == '{':
            return self.parse_braces(atom)
        return atom
        
    def parse_braces(self, atom):
        self.i += 1
        if self.i >= len(self.pat): raise ValueError("Unexpected end")
        start = self.i
        while self.i < len(self.pat) and self.pat[self.i].isdigit():
            self.i += 1
        if self.i == start: raise ValueError("Invalid quantifier")
        m = int(self.pat[start:self.i])
        
        if self.i < len(self.pat) and self.pat[self.i] == '}':
            self.i += 1
            return Quant(atom, m, m, False)
        elif self.i < len(self.pat) and self.pat[self.i] == ',':
            self.i += 1
            if self.i >= len(self.pat): raise ValueError("Unexpected end")
            start2 = self.i
            while self.i < len(self.pat) and self.pat[self.i].isdigit():
                self.i += 1
            if self.i == start2:
                return Quant(atom, m, float('inf'), False)
            else:
                n = int(self.pat[start2:self.i])
                if self.i < len(self.pat) and self.pat[self.i] == '}':
                    self.i += 1
                    if m > n: raise ValueError("Invalid quantifier")
                    lazy = False
                    if self.i < len(self.pat) and self.pat[self.i] == '?':
                        lazy = True
                        self.i += 1
                    return Quant(atom, m, n, lazy)
                else:
                    raise ValueError("Invalid quantifier")
        else:
            raise ValueError("Invalid quantifier")
            
    def parse_atom(self):
        if self.i >= len(self.pat): raise ValueError("Unexpected end")
        c = self.pat[self.i]
        
        if c == '(':
            self.i += 1
            if self.i < len(self.pat) and self.pat[self.i] == '?':
                self.i += 1
                if self.i < len(self.pat) and self.pat[self.i] == ':':
                    self.i += 1
                    body = self.parse_expr()
                    if self.i < len(self.pat) and self.pat[self.i] == ')':
                        self.i += 1
                        return Group(0, body)
                    else:
                        raise ValueError("Unclosed group")
                else:
                    raise ValueError("Invalid group syntax")
            else:
                self.gid += 1
                body = self.parse_expr()
                if self.i < len(self.pat) and self.pat[self.i] == ')':
                    self.i += 1
                    return Group(self.gid, body)
                else:
                    raise ValueError("Unclosed group")
                    
        elif c == '[':
            return self.parse_class()
        elif c == '.':
            self.i += 1
            return Dot()
        elif c == '^':
            self.i += 1
            return Start()
        elif c == '$':
            self.i += 1
            return End()
        elif c == '\\':
            self.i += 1
            if self.i >= len(self.pat): raise ValueError("Invalid escape")
            esc = self.pat[self.i]
            if esc == 'd': self.i += 1; return Class(DIGITS)
            elif esc == 'D': self.i += 1; return Class(ALL - DIGITS)
            elif esc == 'w': self.i += 1; return Class(WORD)
            elif esc == 'W': self.i += 1; return Class(ALL - WORD)
            elif esc == 's': self.i += 1; return Class(WHITESPACE)
            elif esc == 'S': self.i += 1; return Class(ALL - WHITESPACE)
            elif esc == 'n': self.i += 1; return Literal('\n')
            elif esc == 't': self.i += 1; return Literal('\t')
            elif esc.isalnum():
                raise ValueError("Invalid escape")
            else:
                self.i += 1
                return Literal(esc)
        else:
            self.i += 1
            return Literal(c)
            
    def parse_class(self):
        self.i += 1
        neg = False
        if self.i < len(self.pat) and self.pat[self.i] == '^':
            neg = True
            self.i += 1
        chars = set()
        while self.i < len(self.pat) and self.pat[self.i] != ']':
            if self.i < len(self.pat) and self.pat[self.i] == '\\':
                self.i += 1
                if self.i >= len(self.pat): raise ValueError("Invalid class escape")
                esc = self.pat[self.i]
                if esc == 'd': chars |= DIGITS
                elif esc == 'D': chars |= ALL - DIGITS
                elif esc == 'w': chars |= WORD
                elif esc == 'W': chars |= ALL - WORD
                elif esc == 's': chars |= WHITESPACE
                elif esc == 'S': chars |= ALL - WHITESPACE
                elif esc.isalnum():
                    raise ValueError("Invalid class escape")
                else:
                    chars.add(esc)
                self.i += 1
            else:
                item = self.pat[self.i]
                self.i += 1
                if self.i < len(self.pat) and self.pat[self.i] == '-' and self.i + 1 < len(self.pat) and self.pat[self.i+1] != ']':
                    self.i += 1
                    if self.i >= len(self.pat): raise ValueError("Invalid range")
                    end_char = self.pat[self.i]
                    self.i += 1
                    if end_char == '\\':
                        raise ValueError("Invalid range")
                    if ord(item) > ord(end_char):
                        raise ValueError("Invalid range")
                    for code in range(ord(item), ord(end_char) + 1):
                        chars.add(chr(code))
                else:
                    chars.add(item)
                    
        if self.i >= len(self.pat):
            raise ValueError("Unclosed class")
        self.i += 1
        return Class(chars, neg)

OP_LITERAL = 0
OP_DOT = 1
OP_CLASS = 2
OP_START = 3
OP_END = 4
OP_GROUP_OPEN = 5
OP_GROUP_CLOSE = 6
OP_ALT = 7
OP_QUANT = 8
OP_SUCCESS = 9

def compile_node(node, prog):
    if isinstance(node, Literal):
        prog.append((OP_LITERAL, node.c))
    elif isinstance(node, Dot):
        prog.append((OP_DOT,))
    elif isinstance(node, Class):
        prog.append((OP_CLASS, node.chars, node.neg))
    elif isinstance(node, Start):
        prog.append((OP_START,))
    elif isinstance(node, End):
        prog.append((OP_END,))
    elif isinstance(node, Group):
        prog.append((OP_GROUP_OPEN, node.gid))
        compile_node(node.body, prog)
        prog.append((OP_GROUP_CLOSE, node.gid))
    elif isinstance(node, Alt):
        j1 = len(prog)
        compile_node(node.left, prog)
        j2 = len(prog)
        compile_node(node.right, prog)
        prog.append((OP_ALT, j1, j2))
    elif isinstance(node, Quant):
        j_next = len(prog)
        compile_node(node.atom, prog)
        prog.append((OP_QUANT, node.lo, node.hi, node.lazy, j_next))
    elif isinstance(node, Concat):
        for child in node.children:
            compile_node(child, prog)
    elif isinstance(node, Empty):
        pass

def execute(prog, s, start_pos, max_gid):
    pos = start_pos
    pc = 0
    captures = [None] * (max_gid + 1)
    stack = []
    
    while pc < len(prog):
        op, *args = prog[pc]
        pc += 1
        
        if op == OP_LITERAL:
            if pos < len(s) and s[pos] == args[0]:
                pos += 1
            else:
                if not stack: return None
                bp, bpc, bcaps, btype, bdata = stack.pop()
                pos, pc, captures = bp, bpc, bcaps
                if btype == 'ALT':
                    pc = bdata
                elif btype == 'QUANT':
                    lo, hi, lazy, next_pc, c, mark = bdata
                    if lazy:
                        if (hi != float('inf') and c >= hi) or (mark is not None and pos == mark):
                            return None
                        mark = pos
                        c += 1
                    else:
                        pc = next_pc
                continue
                
        elif op == OP_DOT:
            if pos < len(s) and s[pos] != '\n':
                pos += 1
            else:
                if not stack: return None
                bp, bpc, bcaps, btype, bdata = stack.pop()
                pos, pc, captures = bp, bpc, bcaps
                if btype == 'ALT':
                    pc = bdata
                elif btype == 'QUANT':
                    lo, hi, lazy, next_pc, c, mark = bdata
                    if lazy:
                        if (hi != float('inf') and c >= hi) or (mark is not None and pos == mark):
                            return None
                        mark = pos
                        c += 1
                    else:
                        pc = next_pc
                continue
                
        elif op == OP_CLASS:
            chars, neg = args
            ch = s[pos] if pos < len(s) else None
            matched = (ch in chars) if ch is not None else False
            if neg: matched = not matched
            if matched:
                pos += 1
            else:
                if not stack: return None
                bp, bpc, bcaps, btype, bdata = stack.pop()
                pos, pc, captures = bp, bpc, bcaps
                if btype == 'ALT':
                    pc = bdata
                elif btype == 'QUANT':
                    lo, hi, lazy, next_pc, c, mark = bdata
                    if lazy:
                        if (hi != float('inf') and c >= hi) or (mark is not None and pos == mark):
                            return None
                        mark = pos
                        c += 1
                    else:
                        pc = next_pc
                continue
                
        elif op == OP_START:
            if pos != 0:
                if not stack: return None
                bp, bpc, bcaps, btype, bdata = stack.pop()
                pos, pc, captures = bp, bpc, bcaps
                if btype == 'ALT':
                    pc = bdata
                elif btype == 'QUANT':
                    lo, hi, lazy, next_pc, c, mark = bdata
                    if lazy:
                        if (hi != float('inf') and c >= hi) or (mark is not None and pos == mark):
                            return None
                        mark = pos
                        c += 1
                    else:
                        pc = next_pc
                continue
                
        elif op == OP_END:
            if pos != len(s) and not (pos == len(s) - 1 and s[pos] == '\n'):
                if not stack: return None
                bp, bpc, bcaps, btype, bdata = stack.pop()
                pos, pc, captures = bp, bpc, bcaps
                if btype == 'ALT':
                    pc = bdata
                elif btype == 'QUANT':
                    lo, hi, lazy, next_pc, c, mark = bdata
                    if lazy:
                        if (hi != float('inf') and c >= hi) or (mark is not None and pos == mark):
                            return None
                        mark = pos
                        c += 1
                    else:
                        pc = next_pc
                continue
                
        elif op == OP_GROUP_OPEN:
            gid = args[0]
            if gid != 0:
                captures[gid] = (pos, None)
                
        elif op == OP_GROUP_CLOSE:
            gid = args[0]
            if gid != 0 and captures[gid] is not None:
                captures[gid] = (captures[gid][0], pos)
                
        elif op == OP_ALT:
            j1, j2 = args
            stack.append((pos, pc, captures.copy(), 'ALT', j2))
            pc = j1
            
        elif op == OP_QUANT:
            lo, hi, lazy, next_pc = args
            stack.append((pos, pc, captures.copy(), 'QUANT', (lo, hi, lazy, next_pc, 0, None)))
            
        elif op == OP_SUCCESS:
            if pos == len(s):
                return Match(captures, s)
            else:
                if not stack: return None
                bp, bpc, bcaps, btype, bdata = stack.pop()
                pos, pc, captures = bp, bpc, bcaps
                if btype == 'ALT':
                    pc = bdata
                elif btype == 'QUANT':
                    lo, hi, lazy, next_pc, c, mark = bdata
                    if lazy:
                        if (hi != float('inf') and c >= hi) or (mark is not None and pos == mark):
                            return None
                        mark = pos
                        c += 1
                    else:
                        pc = next_pc
                continue

    return None

class Match:
    def __init__(self, captures, s):
        self.captures = captures
        self.s = s
        self.max_gid = len(captures) - 1
        
    def span(self, n=0):
        if n < 0 or n > self.max_gid:
            raise IndexError("group number out of range")
        if self.captures[n] is None:
            return (-1, -1)
        return self.captures[n]
        
    def start(self, n=0):
        sp = self.span(n)
        return sp[0] if sp[0] != -1 else -1
        
    def end(self, n=0):
        sp = self.span(n)
        return sp[1] if sp[1] != -1 else -1
        
    def group(self, n=0):
        if n < 0 or n > self.max_gid:
            raise IndexError("group number out of range")
        sp = self.span(n)
        if sp[0] == -1:
            return None
        return self.s[sp[0]:sp[1]]
        
    def groups(self):
        return tuple(self.captures[i] if self.captures[i] is not None else None for i in range(1, self.max_gid + 1))

def compile(pattern: str):
    parser = Parser(pattern)
    node = parser.parse()
    prog = []
    compile_node(node, prog)
    prog.append((OP_SUCCESS,))
    return Pattern(prog, parser.gid)

class Pattern:
    def __init__(self, prog, max_gid):
        self.prog = prog
        self.max_gid = max_gid
        
    def fullmatch(self, s: str):
        return execute(self.prog, s, 0, self.max_gid)
        
    def search(self, s: str):
        for i in range(len(s) + 1):
            m = execute(self.prog, s, i, self.max_gid)
            if m is not None:
                return m
        return None
