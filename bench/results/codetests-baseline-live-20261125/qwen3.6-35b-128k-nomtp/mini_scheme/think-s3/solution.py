import sys
import threading

class SchemeError(Exception):
    def __init__(self, msg, output=''):
        super().__init__(msg)
        self.output = output

# --- Data Structures ---
class Env(dict):
    __slots__ = ('parent',)
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
    def lookup(self, name):
        if name in self: return self[name]
        if self.parent: return self.parent.lookup(name)
        raise SchemeError(f"Unbound variable: {name}")
    def set(self, name, val):
        if name in self: self[name] = val
        elif self.parent: self.parent.set(name, val)
        else: raise SchemeError(f"Unbound variable: {name}")
    def new(self):
        return Env(self)

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env

class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')
    def __init__(self, name, func, min_args, max_args):
        self.name = name
        self.func = func
        self.min_args = min_args
        self.max_args = max_args

class Unspecified:
    __slots__ = ()
    def __repr__(self): return '<unspecified>'

Unspecified = Unspecified()
Nil = ()  # Empty list

# --- AST Nodes ---
class Int: __slots__ = ('val',); def __init__(self, v): self.val = v
class Bool: __slots__ = ('val',); def __init__(self, v): self.val = v
class Str: __slots__ = ('val',); def __init__(self, v): self.val = v
class Sym: __slots__ = ('val',); def __init__(self, v): self.val = v
class List: __slots__ = ('items',); def __init__(self, items): self.items = items
class Quote: __slots__ = ('expr',); def __init__(self, expr): self.expr = expr
class If: __slots__ = ('test', 'then', 'els'); def __init__(self, t, th, e): self.test, self.then, self.els = t, th, e
class Define: __slots__ = ('name', 'val', 'body'); def __init__(self, n, v, b): self.name, self.val, self.body = n, v, b
class Set!: __slots__ = ('name', 'val'); def __init__(self, n, v): self.name, self.val = n, v
class Begin: __slots__ = ('body'); def __init__(self, b): self.body = b
class Cond: __slots__ = ('clauses'); def __init__(self, c): self.clauses = c
class And: __slots__ = ('exprs'); def __init__(self, e): self.exprs = e
class Or: __slots__ = ('exprs'); def __init__(self, e): self.exprs = e
class Let: __slots__ = ('bindings', 'body'); def __init__(self, b, bd): self.bindings, self.body = b, bd
class LetStar: __slots__ = ('bindings', 'body'); def __init__(self, b, bd): self.bindings, self.body = b, bd
class LetRec: __slots__ = ('bindings', 'body'); def __init__(self, b, bd): self.bindings, self.body = b, bd
class Lambda: __slots__ = ('formals', 'body'); def __init__(self, f, b): self.formals, self.body = f, b
class Apply: __slots__ = ('func', 'args'); def __init__(self, f, a): self.func, self.args = f, a

# --- Reader ---
def tokenize(source):
    tokens = []
    i = 0
    n = len(source)
    while i < n:
        c = source[i]
        if c in ' \t\n\r':
            i += 1
        elif c == ';':
            while i < n and source[i] != '\n': i += 1
        elif c == '"':
            i += 1
            s = []
            while i < n and source[i] != '"':
                if source[i] == '\\':
                    i += 1
                    if i >= n: raise SchemeError("Unterminated string")
                    esc = source[i]
                    if esc == '"': s.append('"')
                    elif esc == '\\': s.append('\\')
                    elif esc == 'n': s.append('\n')
                    else: raise SchemeError(f"Invalid escape: \\{esc}")
                else:
                    s.append(source[i])
                i += 1
            if i >= n: raise SchemeError("Unterminated string")
            tokens.append(Str(''.join(s)))
            i += 1
        elif c in '()\'':
            tokens.append(c)
            i += 1
        elif c == '[':
            # [ is part of symbol
            j = i
            while j < n and source[j] not in ' \t\n\r()\'"': j += 1
            tokens.append(Sym(source[i:j]))
            i = j
        elif c in '+-' and i+1 < n and source[i+1].isdigit():
            j = i+1
            while j < n and source[j].isdigit(): j += 1
            tokens.append(Int(int(source[i:j])))
            i = j
        elif c.isdigit():
            j = i
            while j < n and source[j].isdigit(): j += 1
            tokens.append(Int(int(source[i:j])))
            i = j
        else:
            j = i
            while j < n and source[j] not in ' \t\n\r()\'"': j += 1
            tok = source[i:j]
            if tok == '#t': tokens.append(Bool(True))
            elif tok == '#f': tokens.append(Bool(False))
            elif tok.startswith('#'): raise SchemeError("Invalid syntax starting with #")
            else: tokens.append(Sym(tok))
            i = j
    return tokens

def parse(tokens):
    pos = 0
    def peek(): return tokens[pos] if pos < len(tokens) else None
    def advance(): nonlocal pos; pos += 1; return tokens[pos-1]
    def expect(val):
        t = advance()
        if t != val: raise SchemeError(f"Expected {val}, got {t}")
    def parse_expr():
        t = peek()
        if t is None: raise SchemeError("Unexpected end of input")
        if isinstance(t, (Int, Bool, Str, Sym)):
            return advance()
        if t == '(':
            advance()
            items = []
            while peek() != ')':
                items.append(parse_expr())
            expect(')')
            return List(items)
        if t == ')':
            raise SchemeError("Unbalanced parentheses")
        if t == '[':
            # [ is part of symbol, but here it's a token. Spec says [ is not paren, so treat as symbol start?
            # Actually tokenizer already handles [ as symbol char. So this branch won't be hit.
            raise SchemeError("Unexpected [")
        if t == "'":
            advance()
            return Quote(parse_expr())
        raise SchemeError(f"Unexpected token: {t}")
    def parse_dotted_list(items):
        # Handle dotted forms: (1 . 2) or (1 2 . 3)
        if peek() == '.':
            advance()
            last = parse_expr()
            expect(')')
            if len(items) == 0: raise SchemeError("Dotted list must have at least one element")
            # Build pair chain
            if len(items) == 1:
                return Pair(items[0], last)
            else:
                p = items[-1]
                for i in range(len(items)-2, -1, -1):
                    p = Pair(items[i], p)
                return Pair(p.car, Pair(p.cdr, last))
        else:
            expect(')')
            if len(items) == 0: return Nil
            p = items[-1]
            for i in range(len(items)-2, -1, -1):
                p = Pair(items[i], p)
            return p
    def parse_list():
        advance() # skip (
        items = []
        while peek() != ')':
            items.append(parse_expr())
            if peek() == '.':
                return parse_dotted_list(items)
        return parse_dotted_list(items)
    def parse():
        asts = []
        while pos < len(tokens):
            t = peek()
            if t == '(':
                asts.append(parse_list())
            elif t == ')':
                raise SchemeError("Unbalanced parentheses")
            elif t == '[':
                # [ is ordinary symbol char, but tokenizer already consumed it as part of symbol.
                # If it appears alone, it's a syntax error or part of symbol. Spec says [ is not paren.
                # Tokenizer handles [ as symbol char, so this won't happen.
                raise SchemeError("Unexpected [")
            elif t == "'":
                advance()
                asts.append(Quote(parse_expr()))
            elif t == ';':
                while pos < len(tokens) and tokens[pos] != '\n': pos += 1
            else:
                raise SchemeError(f"Unexpected token: {t}")
        return asts

    # Pair implementation
    class Pair:
        __slots__ = ('car', 'cdr')
        def __init__(self, c, d): self.car, self.cdr = c, d
        def __repr__(self): return f"({self.car} . {self.cdr})"
    
    # Re-parse with Pair support
    pos = 0
    def parse_expr2():
        t = peek()
        if t is None: raise SchemeError("Unexpected end")
        if isinstance(t, (Int, Bool, Str, Sym)): return advance()
        if t == '(':
            advance()
            items = []
            while peek() != ')':
                items.append(parse_expr2())
            return parse_dotted_list2(items)
        if t == ')': raise SchemeError("Unbalanced")
        if t == "'":
            advance()
            return Quote(parse_expr2())
        raise SchemeError(f"Unexpected: {t}")
    def parse_dotted_list2(items):
        if peek() == '.':
            advance()
            last = parse_expr2()
            expect(')')
            if not items: raise SchemeError("Dotted list needs head")
            p = items[-1]
            for i in range(len(items)-2, -1, -1):
                p = Pair(items[i], p)
            return Pair(p.car, Pair(p.cdr, last))
        else:
            expect(')')
            if not items: return Nil
            p = items[-1]
            for i in range(len(items)-2, -1, -1):
                p = Pair(items[i], p)
            return p
    def parse_list2():
        advance()
        items = []
        while peek() != ')':
            items.append(parse_expr2())
            if peek() == '.': return parse_dotted_list2(items)
        return parse_dotted_list2(items)
    def parse2():
        asts = []
        while pos < len(tokens):
            t = peek()
            if t == '(': asts.append(parse_list2())
            elif t == ')': raise SchemeError("Unbalanced")
            elif t == "'":
                advance()
                asts.append(Quote(parse_expr2()))
            elif t == ';':
                while pos < len(tokens) and tokens[pos] != '\n': pos += 1
            else: raise SchemeError(f"Unexpected: {t}")
        return asts
    return parse2()

# --- Evaluator ---
def make_global_env():
    env = Env()
    # Builtins
    def builtin(name, func, min_a, max_a):
        env[name] = Builtin(name, func, min_a, max_a)
    def check_type(val, tp, name):
        if not isinstance(val, tp): raise SchemeError(f"{name} expected {tp.__name__}, got {type(val).__name__}")
    def check_args(args, min_a, max_a):
        if len(args) < min_a or (max_a != -1 and len(args) > max_a):
            raise SchemeError(f"Wrong number of arguments to {min_a if max_a == -1 else max_a} arguments")
    def to_scheme_list(lst):
        if not lst: return Nil
        p = Nil
        for x in reversed(lst): p = Pair(x, p)
        return p
    def from_scheme_list(lst):
        res = []
        while lst is not Nil and isinstance(lst, Pair):
            res.append(lst.car)
            lst = lst.cdr
        if lst is not Nil: raise SchemeError("Not a proper list")
        return res
    def is_proper_list(lst):
        while lst is not Nil:
            if not isinstance(lst, Pair): return False
            lst = lst.cdr
        return True
    def write_repr(val, quote_strings=False):
        if val is Unspecified: return ""
        if isinstance(val, Int): return str(val.val)
        if isinstance(val, Bool): return "#t" if val.val else "#f"
        if isinstance(val, Str):
            s = val.val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return f'"{s}"' if quote_strings else val.val
        if isinstance(val, Sym): return val.val
        if val is Nil: return "()"
        if isinstance(val, Pair):
            parts = []
            curr = val
            while curr is not Nil:
                if not isinstance(curr, Pair): raise SchemeError("Not a pair")
                parts.append(write_repr(curr.car, quote_strings))
                curr = curr.cdr
            if curr is not Nil:
                parts.append(" . " + write_repr(curr, quote_strings))
            return "(" + " ".join(parts) + ")"
        if isinstance(val, Closure): return "#<procedure>"
        if isinstance(val, Builtin): return "#<procedure>"
        return str(val)
    def display_fn(val):
        if val is Unspecified: return
        if isinstance(val, Int): output_buf.append(str(val.val))
        elif isinstance(val, Bool): output_buf.append("#t" if val.val else "#f")
        elif isinstance(val, Str): output_buf.append(val.val)
        elif isinstance(val, Sym): output_buf.append(val.val)
        elif val is Nil: output_buf.append("()")
        elif isinstance(val, Pair):
            parts = []
            curr = val
            while curr is not Nil:
                if not isinstance(curr, Pair): raise SchemeError("Not a pair")
                parts.append(display_repr(curr.car))
                curr = curr.cdr
            if curr is not Nil:
                parts.append(" . " + display_repr(curr))
            output_buf.append("(" + " ".join(parts) + ")")
        elif isinstance(val, (Closure, Builtin)): output_buf.append("#<procedure>")
        else: output_buf.append(str(val))
    def display_repr(val):
        if val is Unspecified: return ""
        if isinstance(val, Int): return str(val.val)
        if isinstance(val, Bool): return "#t" if val.val else "#f"
        if isinstance(val, Str): return val.val
        if isinstance(val, Sym): return val.val
        if val is Nil: return "()"
        if isinstance(val, Pair):
            parts = []
            curr = val
            while curr is not Nil:
                if not isinstance(curr, Pair): raise SchemeError("Not a pair")
                parts.append(display_repr(curr.car))
                curr = curr.cdr
            if curr is not Nil:
                parts.append(" . " + display_repr(curr))
            return "(" + " ".join(parts) + ")"
        if isinstance(val, (Closure, Builtin)): return "#<procedure>"
        return str(val)
    def number_to_string(n, radix=10):
        if not isinstance(n, Int): raise SchemeError("number->string expects integer")
        val = n.val
        if radix == 10: return str(val)
        if radix == 16:
            s = format(val, 'x')
            return '-' + s if val < 0 else s
        if radix == 8:
            s = format(val, 'o')
            return '-' + s if val < 0 else s
        if radix == 2:
            s = format(val, 'b')
            return '-' + s if val < 0 else s
        raise SchemeError("radix must be 2, 8, 10, or 16")
    def error_fn(*args):
        if not args: raise SchemeError("error requires at least one argument")
        msg = args[0]
        if not isinstance(msg, Str): msg = Str(str(msg))
        parts = [msg.val]
        for a in args[1:]:
            parts.append(" " + write_repr(a, quote_strings=True))
        raise SchemeError("".join(parts))
    def apply_fn(*args):
        if len(args) < 2: raise SchemeError("apply requires at least 2 arguments")
        proc = args[0]
        lst = args[-1]
        if not is_proper_list(lst): raise SchemeError("apply: last argument must be a proper list")
        new_args = list(args[1:-1]) + from_scheme_list(lst)
        return proc.func(new_args)
    def cons_fn(a, b): return Pair(a, b)
    def car_fn(p):
        if not isinstance(p, Pair): raise SchemeError("car: expects pair")
        return p.car
    def cdr_fn(p):
        if not isinstance(p, Pair): raise SchemeError("cdr: expects pair")
        return p.cdr
    def list_fn(*args): return to_scheme_list(args)
    def null_fn(x): return Bool(x is Nil)
    def pair_fn(x): return Bool(isinstance(x, Pair))
    def list_fn_check(x): return Bool(is_proper_list(x))
    def length_fn(l):
        if not is_proper_list(l): raise SchemeError("length: expects proper list")
        c = 0
        while l is not Nil: c += 1; l = l.cdr
        return Int(c)
    def append_fn(*args):
        if not args: return Nil
        for a in args[:-1]:
            if not is_proper_list(a): raise SchemeError("append: arguments except last must be proper lists")
        res = Nil
        for a in reversed(args[:-1]):
            curr = a
            while curr is not Nil:
                res = Pair(curr.car, res)
                curr = curr.cdr
        return Pair(res.car, args[-1]) if res is not Nil else args[-1]
    def reverse_fn(l):
        if not is_proper_list(l): raise SchemeError("reverse: expects proper list")
        res = Nil
        while l is not Nil:
            res = Pair(l.car, res)
            l = l.cdr
        return res
    def eq_fn(a, b):
        if a is b: return Bool(True)
        if type(a) != type(b): return Bool(False)
        if isinstance(a, Int): return Bool(a.val == b.val)
        if isinstance(a, Bool): return Bool(a.val == b.val)
        if isinstance(a, Sym): return Bool(a.val == b.val)
        if a is Nil: return Bool(True)
        return Bool(False)
    def equal_fn(a, b):
        if a is b: return Bool(True)
        if type(a) != type(b): return Bool(False)
        if isinstance(a, Int): return Bool(a.val == b.val)
        if isinstance(a, Bool): return Bool(a.val == b.val)
        if isinstance(a, Sym): return Bool(a.val == b.val)
        if a is Nil: return Bool(True)
        if isinstance(a, Str): return Bool(a.val == b.val)
        if isinstance(a, Pair):
            if not isinstance(b, Pair): return Bool(False)
            return equal_fn(a.car, b.car) and equal_fn(a.cdr, b.cdr)
        return Bool(False)
    def not_fn(x): return Bool(x is False)
    def number_q(x): return Bool(isinstance(x, Int))
    def symbol_q(x): return Bool(isinstance(x, Sym))
    def string_q(x): return Bool(isinstance(x, Str))
    def procedure_q(x): return Bool(isinstance(x, (Closure, Builtin)))
    def string_append_fn(*args):
        for a in args:
            if not isinstance(a, Str): raise SchemeError("string-append: expects strings")
        return Str(''.join(a.val for a in args))
    def add_fn(*args): return Int(sum(a.val for a in args))
    def mul_fn(*args):
        r = 1
        for a in args: r *= a.val
        return Int(r)
    def sub_fn(*args):
        if len(args) == 1: return Int(-args[0].val)
        r = args[0].val
        for a in args[1:]: r -= a.val
        return Int(r)
    def div_fn(a, b):
        if b.val == 0: raise SchemeError("Division by zero")
        return Int(a.val // b.val if (a.val ^ b.val) >= 0 else -(-a.val // b.val))
    def rem_fn(a, b): return Int(a.val % b.val)
    def mod_fn(a, b):
        r = a.val % b.val
        if (r != 0) and ((r ^ b.val) < 0): r -= b.val
        return Int(r)
    def cmp_fn(*args):
        if not args: raise SchemeError("Comparison requires at least one argument")
        for i in range(len(args)-1):
            if not isinstance(args[i], Int) or not isinstance(args[i+1], Int):
                raise SchemeError("Comparison expects integers")
            if args[i].val >= args[i+1].val: return Bool(False)
        return Bool(True)
    def eq_q_fn(*args):
        if not args: raise SchemeError("eq? requires at least one argument")
        for i in range(len(args)-1):
            if not eq_fn(args[i], args[i+1]).val: return Bool(False)
        return Bool(True)
    def equal_q_fn(*args):
        if not args: raise SchemeError("equal? requires at least one argument")
        for i in range(len(args)-1):
            if not equal_fn(args[i], args[i+1]).val: return Bool(False)
        return Bool(True)
    def lt_fn(*args): return cmp_fn(*args)
    def gt_fn(*args):
        if not args: raise SchemeError("Comparison requires at least one argument")
        for i in range(len(args)-1):
            if args[i].val <= args[i+1].val: return Bool(False)
        return Bool(True)
    def le_fn(*args):
        if not args: raise SchemeError("Comparison requires at least one argument")
        for i in range(len(args)-1):
            if args[i].val > args[i+1].val: return Bool(False)
        return Bool(True)
    def ge_fn(*args):
        if not args: raise SchemeError("Comparison requires at least one argument")
        for i in range(len(args)-1):
            if args[i].val < args[i+1].val: return Bool(False)
        return Bool(True)

    builtin('+', lambda args: add_fn(*args), 0, -1)
    builtin('*', lambda args: mul_fn(*args), 0, -1)
    builtin('-', lambda args: sub_fn(*args), 1, -1)
    builtin('quotient', lambda args: div_fn(*args), 2, 2)
    builtin('remainder', lambda args: rem_fn(*args), 2, 2)
    builtin('modulo', lambda args: mod_fn(*args), 2, 2)
    builtin('=', lambda args: eq_q_fn(*args), 1, -1)
    builtin('<', lambda args: lt_fn(*args), 1, -1)
    builtin('>', lambda args: gt_fn(*args), 1, -1)
    builtin('<=', lambda args: le_fn(*args), 1, -1)
    builtin('>=', lambda args: ge_fn(*args), 1, -1)
    builtin('number->string', lambda args: Str(number_to_string(*args)), 1, 2)
    builtin('cons', lambda args: cons_fn(*args), 2, 2)
    builtin('car', lambda args: car_fn(*args), 1, 1)
    builtin('cdr', lambda args: cdr_fn(*args), 1, 1)
    builtin('list', lambda args: list_fn(*args), 0, -1)
    builtin('null?', lambda args: null_fn(*args), 1, 1)
    builtin('pair?', lambda args: pair_fn(*args), 1, 1)
    builtin('list?', lambda args: list_fn_check(*args), 1, 1)
    builtin('length', lambda args: length_fn(*args), 1, 1)
    builtin('append', lambda args: append_fn(*args), 0, -1)
    builtin('reverse', lambda args: reverse_fn(*args), 1, 1)
    builtin('apply', lambda args: apply_fn(*args), 2, -1)
    builtin('eq?', lambda args: eq_q_fn(*args), 1, -1)
    builtin('equal?', lambda args: equal_q_fn(*args), 1, -1)
    builtin('not', lambda args: not_fn(*args), 1, 1)
    builtin('number?', lambda args: number_q(*args), 1, 1)
    builtin('symbol?', lambda args: symbol_q(*args), 1, 1)
    builtin('string?', lambda args: string_q(*args), 1, 1)
    builtin('procedure?', lambda args: procedure_q(*args), 1, 1)
    builtin('string-append', lambda args: string_append_fn(*args), 0, -1)
    builtin('display', lambda args: (display_fn(args[0]), Unspecified)[1], 1, 1)
    builtin('newline', lambda args: (output_buf.append('\n'), Unspecified)[1], 0, 0)
    builtin('error', lambda args: error_fn(*args), 1, -1)
    return env

def eval_ast(ast, env, output_buf):
    # Returns value or raises SchemeError
    # Handles TCO by returning a special marker
    class TailCall:
        def __init__(self, proc, args, env):
            self.proc = proc
            self.args = args
            self.env = env
    def eval_expr(e, env):
        if isinstance(e, Int): return e.val
        if isinstance(e, Bool): return e.val
        if isinstance(e, Str): return e.val
        if isinstance(e, Sym): return env.lookup(e.val)
        if isinstance(e, List):
            if not e.items: return Nil
            head = e.items[0]
            if isinstance(head, Sym) and head.val == 'quote': return e.items[1]
            if isinstance(head, Sym) and head.val == 'if':
                test = eval_expr(e.items[1], env)
                if test is False:
                    if len(e.items) > 2: return eval_expr(e.items[2], env)
                    return Unspecified
                else:
                    return eval_expr(e.items[2], env)
            if isinstance(head, Sym) and head.val == 'define':
                if len(e.items) < 2: raise SchemeError("define requires name and value")
                name = e.items[1]
                if isinstance(name, Sym):
                    val = eval_expr(e.items[2], env)
                    env.set(name.val, val)
                    return Unspecified
                elif isinstance(name, List) and name.items:
                    fname = name.items[0]
                    if not isinstance(fname, Sym): raise SchemeError("define: name must be symbol")
                    formals = name.items[1:]
                    body = e.items[2:]
                    if not body: body = [Unspecified]
                    proc = eval_ast(Lambda(formals, [Begin(body)], env), env, output_buf)
                    env.set(fname.val, proc)
                    return Unspecified
                else: raise SchemeError("define: invalid syntax")
            if isinstance(head, Sym) and head.val == 'set!':
                if len(e.items) < 2: raise SchemeError("set! requires name and value")
                name = e.items[1]
                if not isinstance(name, Sym): raise SchemeError("set!: name must be symbol")
                val = eval_expr(e.items[2], env)
                env.set(name.val, val)
                return Unspecified
            if isinstance(head, Sym) and head.val == 'begin':
                body = e.items[1:]
                if not body: return Unspecified
                res = Unspecified
                for b in body: res = eval_expr(b, env)
                return res
            if isinstance(head, Sym) and head.val == 'cond':
                clauses = e.items[1:]
                for c in clauses:
                    if not isinstance(c, List) or not c.items: raise SchemeError("cond: malformed clause")
                    test = c.items[0]
                    body = c.items[1:]
                    if isinstance(test, Sym) and test.val == 'else':
                        if body:
                            res = Unspecified
                            for b in body: res = eval_expr(b, env)
                            return res
                        else: return Unspecified
                    test_val = eval_expr(test, env)
                    if test_val is not False:
                        if body:
                            res = Unspecified
                            for b in body: res = eval_expr(b, env)
                            return res
                        else: return test_val
                return Unspecified
            if isinstance(head, Sym) and head.val == 'and':
                exprs = e.items[1:]
                if not exprs: return Bool(True)
                res = Unspecified
                for ex in exprs:
                    res = eval_expr(ex, env)
                    if res is False: return Bool(False)
                return res
            if isinstance(head, Sym) and head.val == 'or':
                exprs = e.items[1:]
                if not exprs: return Bool(False)
                for ex in exprs:
                    res = eval_expr(ex, env)
                    if res is not False: return res
                return Bool(False)
            if isinstance(head, Sym) and head.val == 'let':
                if len(e.items) < 2: raise SchemeError("let requires bindings and body")
                bindings = e.items[1]
                body = e.items[2:]
                if not isinstance(bindings, List): raise SchemeError("let: bindings must be list")
                new_env = env.new()
                vals = []
                for b in bindings.items:
                    if not isinstance(b, List) or len(b.items) != 2: raise SchemeError("let: malformed binding")
                    vals.append(eval_expr(b.items[1], env))
                for b, v in zip(bindings.items, vals):
                    new_env.set(b.items[0].val, v)
                res = Unspecified
                for b in body: res = eval_expr(b, new_env)
                return res
            if isinstance(head, Sym) and head.val == 'let*':
                if len(e.items) < 2: raise SchemeError("let* requires bindings and body")
                bindings = e.items[1]
                body = e.items[2:]
                if not isinstance(bindings, List): raise SchemeError("let*: bindings must be list")
                new_env = env.new()
                for b in bindings.items:
                    if not isinstance(b, List) or len(b.items) != 2: raise SchemeError("let*: malformed binding")
                    new_env.set(b.items[0].val, eval_expr(b.items[1], new_env))
                res = Unspecified
                for b in body: res = eval_expr(b, new_env)
                return res
            if isinstance(head, Sym) and head.val == 'letrec':
                if len(e.items) < 2: raise SchemeError("letrec requires bindings and body")
                bindings = e.items[1]
                body = e.items[2:]
                if not isinstance(bindings, List): raise SchemeError("letrec: bindings must be list")
                new_env = env.new()
                for b in bindings.items:
                    if not isinstance(b, List) or len(b.items) != 2: raise SchemeError("letrec: malformed binding")
                    new_env.set(b.items[0].val, Unspecified)
                for b in bindings.items:
                    new_env.set(b.items[0].val, eval_expr(b.items[1], new_env))
                res = Unspecified
                for b in body: res = eval_expr(b, new_env)
                return res
            if isinstance(head, Sym) and head.val == 'lambda':
                if len(e.items) < 2: raise SchemeError("lambda requires formals and body")
                formals = e.items[1]
                body = e.items[2:]
                if not body: body = [Unspecified]
                return Closure(formals, [Begin(body)], env)
            if isinstance(head, Sym) and head.val == 'apply':
                args = e.items[1:]
                if len(args) < 2: raise SchemeError("apply requires at least 2 arguments")
                proc = eval_expr(args[0], env)
                lst = eval_expr(args[-1], env)
                if not is_proper_list(lst): raise SchemeError("apply: last arg must be proper list")
                new_args = [eval_expr(a, env) for a in args[1:-1]] + from_scheme_list(lst)
                return proc.func(new_args)
            # Procedure application
            proc = eval_expr(head, env)
            if not isinstance(proc, (Closure, Builtin)): raise SchemeError("Not a procedure")
            arg_vals = [eval_expr(a, env) for a in e.items[1:]]
            return proc.func(arg_vals)
        if isinstance(e, Quote): return e.expr
        if isinstance(e, Lambda): return Closure(e.formals, e.body, env)
        if isinstance(e, Unspecified): return Unspecified
        return e
    def is_proper_list(lst):
        while lst is not Nil:
            if not isinstance(lst, Pair): return False
            lst = lst.cdr
        return True
    def from_scheme_list(lst):
        res = []
        while lst is not Nil and isinstance(lst, Pair):
            res.append(lst.car)
            lst = lst.cdr
        if lst is not Nil: raise SchemeError("Not a proper list")
        return res
    def call_proc(proc, args, env):
        if isinstance(proc, Builtin):
            proc.func(args)
            return proc.func(args) # builtin func returns value
        if isinstance(proc, Closure):
            formals = proc.formals
            body = proc.body
            if isinstance(formals, Sym):
                if len(args) != 1: raise SchemeError("Wrong number of arguments")
                new_env = proc.env.new()
                new_env.set(formals.val, args[0])
                res = Unspecified
                for b in body: res = eval_expr(b, new_env)
                return res
            elif isinstance(formals, List):
                items = formals.items
                if len(items) == 0:
                    if args: raise SchemeError("Wrong number of arguments")
                    return eval_expr(body[0] if body else Unspecified, proc.env.new())
                if len(items) == 1:
                    sym = items[0]
                    if isinstance(sym, Sym):
                        new_env = proc.env.new()
                        new_env.set(sym.val, to_scheme_list(args))
                        res = Unspecified
                        for b in body: res = eval_expr(b, new_env)
                        return res
                # Dotted or fixed
                if len(args) < len(items): raise SchemeError("Wrong number of arguments")
                new_env = proc.env.new()
                for i, sym in enumerate(items[:-1]):
                    if not isinstance(sym, Sym): raise SchemeError("Invalid formal")
                    new_env.set(sym.val, args[i])
                rest_sym = items[-1]
                if isinstance(rest_sym, Sym):
                    new_env.set(rest_sym.val, to_scheme_list(args[len(items)-1:]))
                else:
                    raise SchemeError("Invalid formal")
                res = Unspecified
                for b in body: res = eval_expr(b, new_env)
                return res
            else: raise SchemeError("Invalid formals")
        raise SchemeError("Not a procedure")
    def eval_loop(e, env):
        # Returns value or TailCall
        if isinstance(e, Int): return e.val
        if isinstance(e, Bool): return e.val
        if isinstance(e, Str): return e.val
        if isinstance(e, Sym): return env.lookup(e.val)
        if isinstance(e, List):
            if not e.items: return Nil
            head = e.items[0]
            if isinstance(head, Sym) and head.val == 'quote': return e.items[1]
            if isinstance(head, Sym) and head.val == 'if':
                test = eval_loop(e.items[1], env)
                if test is False:
                    if len(e.items) > 2: return eval_loop(e.items[2], env)
                    return Unspecified
                else: return eval_loop(e.items[2], env)
            if isinstance(head, Sym) and head.val == 'define':
                if len(e.items) < 2: raise SchemeError("define requires name and value")
                name = e.items[1]
                if isinstance(name, Sym):
                    val = eval_loop(e.items[2], env)
                    env.set(name.val, val)
                    return Unspecified
                elif isinstance(name, List) and name.items:
                    fname = name.items[0]
                    if not isinstance(fname, Sym): raise SchemeError("define: name must be symbol")
                    formals = name.items[1:]
                    body = e.items[2:]
                    if not body: body = [Unspecified]
                    proc = eval_loop(Lambda(formals, [Begin(body)], env), env)
                    env.set(fname.val, proc)
                    return Unspecified
                else: raise SchemeError("define: invalid syntax")
            if isinstance(head, Sym) and head.val == 'set!':
                if len(e.items) < 2: raise SchemeError("set! requires name and value")
                name = e.items[1]
                if not isinstance(name, Sym): raise SchemeError("set!: name must be symbol")
                val = eval_loop(e.items[2], env)
                env.set(name.val, val)
                return Unspecified
            if isinstance(head, Sym) and head.val == 'begin':
                body = e.items[1:]
                if not body: return Unspecified
                res = Unspecified
                for b in body: res = eval_loop(b, env)
                return res
            if isinstance(head, Sym) and head.val == 'cond':
                clauses = e.items[1:]
                for c in clauses:
                    if not isinstance(c, List) or not c.items: raise SchemeError("cond: malformed clause")
                    test = c.items[0]
                    body = c.items[1:]
                    if isinstance(test, Sym) and test.val == 'else':
                        if body:
                            res = Unspecified
                            for b in body: res = eval_loop(b, env)
                            return res
                        else: return Unspecified
                    test_val = eval_loop(test, env)
                    if test_val is not False:
                        if body:
                            res = Unspecified
                            for b in body: res = eval_loop(b, env)
                            return res
                        else: return test_val
                return Unspecified
            if isinstance(head, Sym) and head.val == 'and'):
                exprs = e.items[1:]
                if not exprs: return Bool(True)
                res = Unspecified
                for ex in exprs:
                    res = eval_loop(ex, env)
                    if res is False: return Bool(False)
                return res
            if isinstance(head, Sym) and head.val == 'or'):
                exprs = e.items[1:]
                if not exprs: return Bool(False)
                for ex in exprs:
                    res = eval_loop(ex, env)
                    if res is not False: return res
                return Bool(False)
            if isinstance(head, Sym) and head.val == 'let'):
                if len(e.items) < 2: raise SchemeError("let requires bindings and body")
                bindings = e.items[1]
                body = e.items[2:]
                if not isinstance(bindings, List): raise SchemeError("let: bindings must be list")
                new_env = env.new()
                vals = []
                for b in bindings.items:
                    if not isinstance(b, List) or len(b.items) != 2: raise SchemeError("let: malformed binding")
                    vals.append(eval_loop(b.items[1], env))
                for b, v in zip(bindings.items, vals):
                    new_env.set(b.items[0].val, v)
                res = Unspecified
                for b in body: res = eval_loop(b, new_env)
                return res
            if isinstance(head, Sym) and head.val == 'let*'):
                if len(e.items) < 2: raise SchemeError("let* requires bindings and body")
                bindings = e.items[1]
                body = e.items[2:]
                if not isinstance(bindings, List): raise SchemeError("let*: bindings must be list")
                new_env = env.new()
                for b in bindings.items:
                    if not isinstance(b, List) or len(b.items) != 2: raise SchemeError("let*: malformed binding")
                    new_env.set(b.items[0].val, eval_loop(b.items[1], new_env))
                res = Unspecified
                for b in body: res = eval_loop(b, new_env)
                return res
            if isinstance(head, Sym) and head.val == 'letrec'):
                if len(e.items) < 2: raise SchemeError("letrec requires bindings and body")
                bindings = e.items[1]
                body = e.items[2:]
                if not isinstance(bindings, List): raise SchemeError("letrec: bindings must be list")
                new_env = env.new()
                for b in bindings.items:
                    if not isinstance(b, List) or len(b.items) != 2: raise SchemeError("letrec: malformed binding")
                    new_env.set(b.items[0].val, Unspecified)
                for b in bindings.items:
                    new_env.set(b.items[0].val, eval_loop(b.items[1], new_env))
                res = Unspecified
                for b in body: res = eval_loop(b, new_env)
                return res
            if isinstance(head, Sym) and head.val == 'lambda'):
                if len(e.items) < 2: raise SchemeError("lambda requires formals and body")
                formals = e.items[1]
                body = e.items[2:]
                if not body: body = [Unspecified]
                return Closure(formals, [Begin(body)], env)
            if isinstance(head, Sym) and head.val == 'apply'):
                args = e.items[1:]
                if len(args) < 2: raise SchemeError("apply requires at least 2 arguments")
                proc = eval_loop(args[0], env)
                lst = eval_loop(args[-1], env)
                if not is_proper_list(lst): raise SchemeError("apply: last arg must be proper list")
                new_args = [eval_loop(a, env) for a in args[1:-1]] + from_scheme_list(lst)
                return call_proc(proc, new_args, env)
            # Procedure application
            proc = eval_loop(head, env)
            if not isinstance(proc, (Closure, Builtin)): raise SchemeError("Not a procedure")
            arg_vals = [eval_loop(a, env) for a in e.items[1:]]
            return call_proc(proc, arg_vals, env)
        if isinstance(e, Quote): return e.expr
        if isinstance(e, Lambda): return Closure(e.formals, e.body, env)
        if isinstance(e, Unspecified): return Unspecified
        return e
    return eval_loop(ast, env)

def run(source: str) -> str:
    output_buf = []
    try:
        tokens = tokenize(source)
        asts = parse(tokens)
        env = make_global_env()
        for ast in asts:
            val = eval_ast(ast, env, output_buf)
    except SchemeError as e:
        raise SchemeError(str(e), ''.join(output_buf))
    except Exception as e:
        raise SchemeError(str(e), ''.join(output_buf))
    return ''.join(output_buf)
