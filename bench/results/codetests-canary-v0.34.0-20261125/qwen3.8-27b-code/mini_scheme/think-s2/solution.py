import re
import sys

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)
sys.setrecursionlimit(200000)


class SchemeError(Exception):
    def __init__(self, msg='', output=''):
        self.output = output
        super().__init__(msg)


# ─── Value Types ───────────────────────────────────────────────────────────

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('Sym', self.name))

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class _EmptyList:
    _inst = None
    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env

class Builtin:
    __slots__ = ('name', 'func')
    def __init__(self, name, func):
        self.name = name
        self.func = func

class _Unspecified:
    _inst = None
    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

class _Uninitialized:
    _inst = None
    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

EmptyList = _EmptyList()
Unspecified = _Unspecified()
Uninitialized = _Uninitialized()


# ─── Environment ───────────────────────────────────────────────────────────

class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings=None, parent=None):
        self.bindings = bindings if bindings is not None else {}
        self.parent = parent

    def lookup(self, name):
        if name in self.bindings:
            v = self.bindings[name]
            if v is Uninitialized:
                raise SchemeError(f"uninitialized variable: {name}")
            return v
        if self.parent is not None:
            return self.parent.lookup(name)
        raise SchemeError(f"unbound variable: {name}")

    def define(self, name, value):
        self.bindings[name] = value

    def set(self, name, value):
        if name in self.bindings:
            self.bindings[name] = value
            return
        if self.parent is not None:
            self.parent.set(name, value)
            return
        raise SchemeError(f"unbound variable: {name}")


# ─── Helpers ───────────────────────────────────────────────────────────────

def is_proper_list(x):
    cur = x
    while isinstance(cur, Pair):
        cur = cur.cdr
    return cur is EmptyList

def scheme_list_to_pylist(x):
    result = []
    while isinstance(x, Pair):
        result.append(x.car)
        x = x.cdr
    if x is not EmptyList:
        raise SchemeError("expected proper list")
    return result

def make_schemelist(lst):
    result = EmptyList
    for item in reversed(lst):
        result = Pair(item, result)
    return result

def is_truthy(x):
    return x is not False


# ─── Reader ────────────────────────────────────────────────────────────────

def _tokenize(source):
    tokens = []
    i = 0
    n = len(source)
    while i < n:
        c = source[i]
        if c in ' \t\n\r':
            i += 1
        elif c == ';':
            while i < n and source[i] != '\n':
                i += 1
        elif c == '(':
            tokens.append(('LPAREN', None)); i += 1
        elif c == ')':
            tokens.append(('RPAREN', None)); i += 1
        elif c == "'":
            tokens.append(('QUOTE', None)); i += 1
        elif c == '"':
            i += 1
            chars = []
            terminated = False
            while i < n:
                if source[i] == '\\':
                    if i + 1 >= n:
                        raise SchemeError("syntax error: unterminated escape")
                    esc = source[i + 1]
                    if esc == '"':
                        chars.append('"'); i += 2
                    elif esc == '\\':
                        chars.append('\\'); i += 2
                    elif esc == 'n':
                        chars.append('\n'); i += 2
                    else:
                        raise SchemeError(f"syntax error: invalid escape \\{esc}")
                elif source[i] == '"':
                    i += 1; terminated = True; break
                else:
                    chars.append(source[i]); i += 1
            if not terminated:
                raise SchemeError("syntax error: unterminated string")
            tokens.append(('STRING', ''.join(chars)))
        else:
            j = i
            while j < n and source[j] not in ' \t\n\r()";\'':
                j += 1
            tok = source[i:j]
            if tok == '#t':
                tokens.append(('BOOL', True))
            elif tok == '#f':
                tokens.append(('BOOL', False))
            elif tok[0] == '#':
                raise SchemeError(f"syntax error: invalid token {tok}")
            elif re.fullmatch(r'[+-]?[0-9]+', tok):
                tokens.append(('INT', int(tok)))
            else:
                tokens.append(('SYM', tok))
            i = j
    return tokens

def _parse_form(tokens, pos):
    if pos >= len(tokens):
        raise SchemeError("syntax error: unexpected end of input")
    kind, val = tokens[pos]
    if kind == 'LPAREN':
        return _parse_list(tokens, pos)
    elif kind == 'RPAREN':
        raise SchemeError("syntax error: unexpected )")
    elif kind == 'QUOTE':
        pos += 1
        if pos >= len(tokens):
            raise SchemeError("syntax error: quote not followed by datum")
        datum, pos = _parse_form(tokens, pos)
        return make_schemelist([Symbol('quote'), datum]), pos
    elif kind == 'INT':
        return val, pos + 1
    elif kind == 'BOOL':
        return val, pos + 1
    elif kind == 'STRING':
        return val, pos + 1
    elif kind == 'SYM':
        return Symbol(val), pos + 1
    else:
        raise SchemeError("syntax error: unexpected token")

def _parse_list(tokens, pos):
    pos += 1
    if pos < len(tokens) and tokens[pos][0] == 'RPAREN':
        return EmptyList, pos + 1
    elements = []
    while True:
        if pos >= len(tokens):
            raise SchemeError("syntax error: unbalanced parenthesis")
        kind, val = tokens[pos]
        if kind == 'RPAREN':
            return make_schemelist(elements), pos + 1
        if kind == 'SYM' and val == '.' and elements:
            if pos + 1 >= len(tokens) or tokens[pos + 1][0] == 'RPAREN':
                raise SchemeError("syntax error: dot must be followed by a datum")
            pos += 1
            dot_elem, pos = _parse_form(tokens, pos)
            if pos >= len(tokens) or tokens[pos][0] != 'RPAREN':
                raise SchemeError("syntax error: dotted list must end with )")
            result = dot_elem
            for e in reversed(elements):
                result = Pair(e, result)
            return result, pos + 1
        elem, pos = _parse_form(tokens, pos)
        elements.append(elem)

def read_all(source):
    tokens = _tokenize(source)
    forms = []
    pos = 0
    while pos < len(tokens):
        form, pos = _parse_form(tokens, pos)
        forms.append(form)
    return forms


# ─── Display / Write ───────────────────────────────────────────────────────

def display_repr(x):
    if x is False:
        return "#f"
    if x is True:
        return "#t"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, str):
        return x
    if isinstance(x, Symbol):
        return x.name
    if x is EmptyList:
        return "()"
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if x is Unspecified:
        return ""
    if isinstance(x, Pair):
        return _display_pair(x)
    return ""

def _display_pair(p):
    parts = []
    cur = p
    while isinstance(cur, Pair):
        parts.append(display_repr(cur.car))
        cur = cur.cdr
    if cur is EmptyList:
        return "(" + " ".join(parts) + ")"
    else:
        return "(" + " ".join(parts) + " . " + display_repr(cur) + ")"

def write_repr(x):
    if x is False:
        return "#f"
    if x is True:
        return "#t"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, str):
        return '"' + x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    if isinstance(x, Symbol):
        return x.name
    if x is EmptyList:
        return "()"
    if isinstance(x, (Closure, Builtin)):
        return "#<procedure>"
    if x is Unspecified:
        return ""
    if isinstance(x, Pair):
        return _write_pair(x)
    return ""

def _write_pair(p):
    parts = []
    cur = p
    while isinstance(cur, Pair):
        parts.append(write_repr(cur.car))
        cur = cur.cdr
    if cur is EmptyList:
        return "(" + " ".join(parts) + ")"
    else:
        return "(" + " ".join(parts) + " . " + write_repr(cur) + ")"


# ─── Evaluator ─────────────────────────────────────────────────────────────

class _Final:
    __slots__ = ('value',)
    def __init__(self, value):
        self.value = value

def eval_expr(expr, env, output):
    """Evaluate expr in non-tail position. Returns a value."""
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        return expr
    if isinstance(expr, Symbol):
        return env.lookup(expr.name)
    if expr is EmptyList:
        raise SchemeError("() is not a valid expression")
    if isinstance(expr, (Closure, Builtin)):
        return expr
    if expr is Unspecified:
        return expr
    if isinstance(expr, Pair):
        if not is_proper_list(expr):
            raise SchemeError("dotted list used as application")
        forms = scheme_list_to_pylist(expr)
        if not forms:
            raise SchemeError("empty list as expression")
        head = forms[0]
        if isinstance(head, Symbol):
            name = head.name
            if name == 'quote':
                if len(forms) != 2:
                    raise SchemeError("malformed quote")
                return forms[1]
            elif name == 'if':
                if len(forms) not in (3, 4):
                    raise SchemeError("malformed if")
                test_val = eval_expr(forms[1], env, output)
                if is_truthy(test_val):
                    return eval_expr(forms[2], env, output)
                elif len(forms) == 4:
                    return eval_expr(forms[3], env, output)
                else:
                    return Unspecified
            elif name == 'begin':
                if len(forms) < 2:
                    raise SchemeError("malformed begin")
                body = forms[1:]
                for i in range(len(body) - 1):
                    eval_expr(body[i], env, output)
                return eval_expr(body[-1], env, output)
            elif name == 'define':
                _eval_define(forms, env, output)
                return Unspecified
            elif name == 'set!':
                if len(forms) != 3:
                    raise SchemeError("malformed set!")
                if not isinstance(forms[1], Symbol):
                    raise SchemeError("set!: name must be a symbol")
                val = eval_expr(forms[2], env, output)
                env.set(forms[1].name, val)
                return Unspecified
            elif name == 'cond':
                return _eval_cond(forms, env, output)
            elif name == 'and':
                exprs = forms[1:]
                if not exprs:
                    return True
                for e in exprs:
                    val = eval_expr(e, env, output)
                    if val is False:
                        return False
                return val
            elif name == 'or':
                exprs = forms[1:]
                if not exprs:
                    return False
                for e in exprs:
                    val = eval_expr(e, env, output)
                    if is_truthy(val):
                        return val
                return False
            elif name == 'lambda':
                if len(forms) < 3:
                    raise SchemeError("malformed lambda")
                formals = forms[1]
                body = forms[2:]
                _validate_formals(formals)
                return Closure(formals, body, env)
            elif name == 'let':
                if len(forms) < 3:
                    raise SchemeError("malformed let")
                if isinstance(forms[1], Symbol):
                    return _eval_named_let(forms, env, output)
                else:
                    return _eval_let(forms, env, output)
            elif name == 'let*':
                if len(forms) < 3:
                    raise SchemeError("malformed let*")
                return _eval_let_star(forms, env, output)
            elif name == 'letrec':
                if len(forms) < 3:
                    raise SchemeError("malformed letrec")
                return _eval_letrec(forms, env, output)
        # Application
        return _eval_application(forms, env, output)
    raise SchemeError(f"unexpected expression type")

def eval_tail(expr, env, output):
    """Evaluate expr in tail position using trampoline."""
    while True:
        result = _step_tail(expr, env, output)
        if isinstance(result, _Final):
            return result.value
        expr, env = result

def _step_tail(expr, env, output):
    if isinstance(expr, bool):
        return _Final(expr)
    if isinstance(expr, int):
        return _Final(expr)
    if isinstance(expr, str):
        return _Final(expr)
    if isinstance(expr, Symbol):
        return _Final(env.lookup(expr.name))
    if expr is EmptyList:
        raise SchemeError("() is not a valid expression")
    if isinstance(expr, (Closure, Builtin)):
        return _Final(expr)
    if expr is Unspecified:
        return _Final(expr)
    if isinstance(expr, Pair):
        if not is_proper_list(expr):
            raise SchemeError("dotted list used as application")
        forms = scheme_list_to_pylist(expr)
        if not forms:
            raise SchemeError("empty list as expression")
        head = forms[0]
        if isinstance(head, Symbol):
            name = head.name
            if name == 'quote':
                if len(forms) != 2:
                    raise SchemeError("malformed quote")
                return _Final(forms[1])
            elif name == 'if':
                if len(forms) not in (3, 4):
                    raise SchemeError("malformed if")
                test_val = eval_expr(forms[1], env, output)
                if is_truthy(test_val):
                    return (forms[2], env)
                elif len(forms) == 4:
                    return (forms[3], env)
                else:
                    return _Final(Unspecified)
            elif name == 'begin':
                if len(forms) < 2:
                    raise SchemeError("malformed begin")
                body = forms[1:]
                for i in range(len(body) - 1):
                    eval_expr(body[i], env, output)
                return (body[-1], env)
            elif name == 'define':
                _eval_define(forms, env, output)
                return _Final(Unspecified)
            elif name == 'set!':
                if len(forms) != 3:
                    raise SchemeError("malformed set!")
                if not isinstance(forms[1], Symbol):
                    raise SchemeError("set!: name must be a symbol")
                val = eval_expr(forms[2], env, output)
                env.set(forms[1].name, val)
                return _Final(Unspecified)
            elif name == 'cond':
                return _step_tail_cond(forms, env, output)
            elif name == 'and':
                exprs = forms[1:]
                if not exprs:
                    return _Final(True)
                val = eval_expr(exprs[0], env, output)
                if val is False:
                    return _Final(False)
                if len(exprs) == 1:
                    return _Final(val)
                return (make_schemelist([Symbol('and')] + exprs[1:]), env)
            elif name == 'or':
                exprs = forms[1:]
                if not exprs:
                    return _Final(False)
                val = eval_expr(exprs[0], env, output)
                if is_truthy(val):
                    return _Final(val)
                if len(exprs) == 1:
                    return _Final(False)
                return (make_schemelist([Symbol('or')] + exprs[1:]), env)
            elif name == 'lambda':
                if len(forms) < 3:
                    raise SchemeError("malformed lambda")
                formals = forms[1]
                body = forms[2:]
                _validate_formals(formals)
                return _Final(Closure(formals, body, env))
            elif name == 'let':
                if len(forms) < 3:
                    raise SchemeError("malformed let")
                if isinstance(forms[1], Symbol):
                    return _step_tail_named_let(forms, env, output)
                else:
                    return _step_tail_let(forms, env, output)
            elif name == 'let*':
                if len(forms) < 3:
                    raise SchemeError("malformed let*")
                return _step_tail_let_star(forms, env, output)
            elif name == 'letrec':
                if len(forms) < 3:
                    raise SchemeError("malformed letrec")
                return _step_tail_letrec(forms, env, output)
        # Application in tail position
        return _step_tail_application(forms, env, output)
    raise SchemeError("unexpected expression in tail position")

def _step_tail_cond(forms, env, output):
    clauses = forms[1:]
    if not clauses:
        raise SchemeError("malformed cond")
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair) or not is_proper_list(clause):
            raise SchemeError("malformed cond clause")
        cl = scheme_list_to_pylist(clause)
        if not cl:
            raise SchemeError("malformed cond clause")
        test = cl[0]
        exprs = cl[1:]
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("else must be last cond clause")
            if not exprs:
                raise SchemeError("else clause requires expressions")
            for e in exprs[:-1]:
                eval_expr(e, env, output)
            return (exprs[-1], env)
        else:
            test_val = eval_expr(test, env, output)
            if is_truthy(test_val):
                if not exprs:
                    return _Final(test_val)
                for e in exprs[:-1]:
                    eval_expr(e, env, output)
                return (exprs[-1], env)
    return _Final(Unspecified)

def _eval_cond(forms, env, output):
    clauses = forms[1:]
    if not clauses:
        raise SchemeError("malformed cond")
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair) or not is_proper_list(clause):
            raise SchemeError("malformed cond clause")
        cl = scheme_list_to_pylist(clause)
        if not cl:
            raise SchemeError("malformed cond clause")
        test = cl[0]
        exprs = cl[1:]
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("else must be last cond clause")
            if not exprs:
                raise SchemeError("else clause requires expressions")
            val = Unspecified
            for e in exprs:
                val = eval_expr(e, env, output)
            return val
        else:
            test_val = eval_expr(test, env, output)
            if is_truthy(test_val):
                if not exprs:
                    return test_val
                val = Unspecified
                for e in exprs:
                    val = eval_expr(e, env, output)
                return val
    return Unspecified

def _eval_application(forms, env, output):
    op = eval_expr(forms[0], env, output)
    args = [eval_expr(a, env, output) for a in forms[1:]]
    if isinstance(op, Closure):
        body, new_env = _apply_closure(op, args)
        return eval_body(body, new_env, output)
    elif isinstance(op, Builtin):
        return op.func(args)
    else:
        raise SchemeError("attempt to call non-procedure")

def _step_tail_application(forms, env, output):
    op = eval_expr(forms[0], env, output)
    args = [eval_expr(a, env, output) for a in forms[1:]]
    # Check for apply in tail position
    if isinstance(op, Builtin) and op.name == 'apply':
        if len(args) < 2:
            raise SchemeError("apply: expected at least 2 arguments")
        f = args[0]
        mid = args[1:-1]
        lst = args[-1]
        if not is_proper_list(lst):
            raise SchemeError("apply: last argument must be a proper list")
        all_args = mid + scheme_list_to_pylist(lst)
        if isinstance(f, Closure):
            body, new_env = _apply_closure(f, all_args)
            return (make_schemelist(body) if len(body) == 1 else _make_begin(body), new_env)
        elif isinstance(f, Builtin):
            return _Final(f.func(all_args))
        else:
            raise SchemeError("apply: first argument is not a procedure")
    if isinstance(op, Closure):
        body, new_env = _apply_closure(op, args)
        if len(body) == 1:
            return (body[0], new_env)
        else:
            return (_make_begin(body), new_env)
    elif isinstance(op, Builtin):
        return _Final(op.func(args))
    else:
        raise SchemeError("attempt to call non-procedure")

def _make_begin(body):
    """Create a (begin e1 e2 ...) form from a list of expressions."""
    return make_schemelist([Symbol('begin')] + body)

def _apply_closure(closure, args):
    """Returns (body, new_env)."""
    formals = closure.formals
    if isinstance(formals, Symbol):
        arg_list = make_schemelist(args)
        new_env = Env({formals.name: arg_list}, closure.env)
    elif is_proper_list(formals):
        params = scheme_list_to_pylist(formals)
        if len(args) != len(params):
            raise SchemeError(f"wrong number of arguments: expected {len(params)}, got {len(args)}")
        new_env = Env({}, closure.env)
        for param, arg in zip(params, args):
            new_env.bindings[param.name] = arg
    else:
        # Dotted list
        params = []
        cur = formals
        while isinstance(cur, Pair):
            params.append(cur.car)
            cur = cur.cdr
        rest_sym = cur
        if len(args) < len(params):
            raise SchemeError(f"wrong number of arguments: expected at least {len(params)}, got {len(args)}")
        new_env = Env({}, closure.env)
        for i, param in enumerate(params):
            new_env.bindings[param.name] = args[i]
        new_env.bindings[rest_sym.name] = make_schemelist(args[len(params):])
    return closure.body, new_env

def _validate_formals(formals):
    if isinstance(formals, Symbol):
        return
    if is_proper_list(formals):
        for s in scheme_list_to_pylist(formals):
            if not isinstance(s, Symbol):
                raise SchemeError("formals must be symbols")
        return
    if isinstance(formals, Pair):
        cur = formals
        while isinstance(cur, Pair):
            if not isinstance(cur.car, Symbol):
                raise SchemeError("formals must be symbols")
            cur = cur.cdr
        if not isinstance(cur, Symbol):
            raise SchemeError("rest parameter must be a symbol")
        return
    raise SchemeError("invalid formals")

def _eval_define(forms, env, output):
    if len(forms) == 3 and isinstance(forms[1], Symbol):
        name = forms[1].name
        val = eval_expr(forms[2], env, output)
        env.define(name, val)
    elif len(forms) >= 3 and isinstance(forms[1], Pair):
        name_sym = forms[1].car
        if not isinstance(name_sym, Symbol):
            raise SchemeError("define: name must be a symbol")
        formals = forms[1].cdr
        body = forms[2:]
        _validate_formals(formals)
        closure = Closure(formals, body, env)
        env.define(name_sym.name, closure)
    else:
        raise SchemeError("malformed define")

def _is_define_form(form):
    if not isinstance(form, Pair) or not is_proper_list(form):
        return False
    lst = scheme_list_to_pylist(form)
    if not lst:
        return False
    return isinstance(lst[0], Symbol) and lst[0].name == 'define'

def _get_define_name(form):
    lst = scheme_list_to_pylist(form)
    if len(lst) == 3 and isinstance(lst[1], Symbol):
        return lst[1].name
    elif len(lst) >= 3 and isinstance(lst[1], Pair):
        ns = lst[1].car
        if isinstance(ns, Symbol):
            return ns.name
    raise SchemeError("malformed define")

def eval_body(body, env, output):
    if not body:
        raise SchemeError("empty body")
    internal_names = []
    for form in body:
        if _is_define_form(form):
            internal_names.append(_get_define_name(form))
    if internal_names:
        new_env = Env(parent=env)
        for nm in internal_names:
            new_env.bindings[nm] = Uninitialized
        env = new_env
    last_value = Unspecified
    for i, form in enumerate(body):
        if _is_define_form(form):
            _eval_define(scheme_list_to_pylist(form), env, output)
            last_value = Unspecified
        elif i == len(body) - 1:
            last_value = eval_tail(form, env, output)
        else:
            last_value = eval_expr(form, env, output)
    return last_value

def _eval_let(forms, env, output):
    bindings_list = forms[1]
    body = forms[2:]
    if not isinstance(bindings_list, Pair) and bindings_list is not EmptyList:
        raise SchemeError("malformed let bindings")
    if not is_proper_list(bindings_list):
        raise SchemeError("malformed let bindings")
    bindings = scheme_list_to_pylist(bindings_list)
    for b in bindings:
        if not isinstance(b, Pair) or not is_proper_list(b):
            raise SchemeError("malformed let binding")
        bl = scheme_list_to_pylist(b)
        if len(bl) != 2:
            raise SchemeError("malformed let binding")
        if not isinstance(bl[0], Symbol):
            raise SchemeError("let binding name must be a symbol")
    # Evaluate inits in outer scope
    vals = [eval_expr(bl[1], env, output) for bl in [scheme_list_to_pylist(b) for b in bindings]]
    new_env = Env({}, env)
    for b, v in zip([scheme_list_to_pylist(bl) for bl in bindings], vals):
        new_env.bindings[b[0].name] = v
    return eval_body(body, new_env, output)

def _step_tail_let(forms, env, output):
    bindings_list = forms[1]
    body = forms[2:]
    if not is_proper_list(bindings_list):
        raise SchemeError("malformed let bindings")
    bindings = scheme_list_to_pylist(bindings_list)
    for b in bindings:
        if not isinstance(b, Pair) or not is_proper_list(b):
            raise SchemeError("malformed let binding")
        bl = scheme_list_to_pylist(b)
        if len(bl) != 2:
            raise SchemeError("malformed let binding")
        if not isinstance(bl[0], Symbol):
            raise SchemeError("let binding name must be a symbol")
    vals = [eval_expr(scheme_list_to_pylist(b)[1], env, output) for b in bindings]
    new_env = Env({}, env)
    for b, v in zip([scheme_list_to_pylist(bl) for bl in bindings], vals):
        new_env.bindings[b[0].name] = v
    if len(body) == 1:
        return (body[0], new_env)
    return (_make_begin(body), new_env)

def _eval_let_star(forms, env, output):
    bindings_list = forms[1]
    body = forms[2:]
    if not is_proper_list(bindings_list):
        raise SchemeError("malformed let* bindings")
    bindings = scheme_list_to_pylist(bindings_list)
    for b in bindings:
        if not isinstance(b, Pair) or not is_proper_list(b):
            raise SchemeError("malformed let* binding")
        bl = scheme_list_to_pylist(b)
        if len(bl) != 2:
            raise SchemeError("malformed let* binding")
        if not isinstance(bl[0], Symbol):
            raise SchemeError("let* binding name must be a symbol")
    new_env = env
    for b in bindings:
        bl = scheme_list_to_pylist(b)
        val = eval_expr(bl[1], new_env, output)
        new_env = Env({bl[0].name: val}, new_env)
    return eval_body(body, new_env, output)

def _step_tail_let_star(forms, env, output):
    bindings_list = forms[1]
    body = forms[2:]
    if not is_proper_list(bindings_list):
        raise SchemeError("malformed let* bindings")
    bindings = scheme_list_to_pylist(bindings_list)
    for b in bindings:
        if not isinstance(b, Pair) or not is_proper_list(b):
            raise SchemeError("malformed let* binding")
        bl = scheme_list_to_pylist(b)
        if len(bl) != 2:
            raise SchemeError("malformed let* binding")
        if not isinstance(bl[0], Symbol):
            raise SchemeError("let* binding name must be a symbol")
    new_env = env
    for b in bindings:
        bl = scheme_list_to_pylist(b)
        val = eval_expr(bl[1], new_env, output)
        new_env = Env({bl[0].name: val}, new_env)
    if len(body) == 1:
        return (body[0], new_env)
    return (_make_begin(body), new_env)

def _eval_letrec(forms, env, output):
    bindings_list = forms[1]
    body = forms[2:]
    if not is_proper_list(bindings_list):
        raise SchemeError("malformed letrec bindings")
    bindings = scheme_list_to_pylist(bindings_list)
    for b in bindings:
        if not isinstance(b, Pair) or not is_proper_list(b):
            raise SchemeError("malformed letrec binding")
        bl = scheme_list_to_pylist(b)
        if len(bl) != 2:
            raise SchemeError("malformed letrec binding")
        if not isinstance(bl[0], Symbol):
            raise SchemeError("letrec binding name must be a symbol")
    new_env = Env({}, env)
    for b in bindings:
        bl = scheme_list_to_pylist(b)
        new_env.bindings[bl[0].name] = Uninitialized
    for b in bindings:
        bl = scheme_list_to_pylist(b)
        val = eval_expr(bl[1], new_env, output)
        new_env.bindings[bl[0].name] = val
    return eval_body(body, new_env, output)

def _step_tail_letrec(forms, env, output):
    bindings_list = forms[1]
    body = forms[2:]
    if not is_proper_list(bindings_list):
        raise SchemeError("malformed letrec bindings")
    bindings = scheme_list_to_pylist(bindings_list)
    for b in bindings:
        if not isinstance(b, Pair) or not is_proper_list(b):
            raise SchemeError("malformed letrec binding")
        bl = scheme_list_to_pylist(b)
        if len(bl) != 2:
            raise SchemeError("malformed letrec binding")
        if not isinstance(bl[0], Symbol):
            raise SchemeError("letrec binding name must be a symbol")
    new_env = Env({}, env)
    for b in bindings:
        bl = scheme_list_to_pylist(b)
        new_env.bindings[bl[0].name] = Uninitialized
    for b in bindings:
        bl = scheme_list_to_pylist(b)
        val = eval_expr(bl[1], new_env, output)
        new_env.bindings[bl[0].name] = val
    if len(body) == 1:
        return (body[0], new_env)
    return (_make_begin(body), new_env)

def _eval_named_let(forms, env, output):
    let_name = forms[1].name
    bindings_list = forms[2]
    body = forms[3:]
    if not is_proper_list(bindings_list):
        raise SchemeError("malformed named let bindings")
    bindings = scheme_list_to_pylist(bindings_list)
    for b in bindings:
        if not isinstance(b, Pair) or not is_proper_list(b):
            raise SchemeError("malformed named let binding")
        bl = scheme_list_to_pylist(b)
        if len(bl) != 2:
            raise SchemeError("malformed named let binding")
        if not isinstance(bl[0], Symbol):
            raise SchemeError("named let binding name must be a symbol")
    params = [scheme_list_to_pylist(b)[0] for b in bindings]
    inits = [scheme_list_to_pylist(b)[1] for b in bindings]
    # Evaluate inits in outer scope
    init_vals = [eval_expr(init, env, output) for init in inits]
    # Create the letrec-like env
    new_env = Env({}, env)
    for p in params:
        new_env.bindings[p.name] = Uninitialized
    # The procedure: takes params, executes body
    proc = Closure(make_schemelist(params), body, new_env)
    new_env.bindings[let_name] = proc
    # Set the initial parameter values
    for p, v in zip(params, init_vals):
        new_env.bindings[p.name] = v
    # Call the procedure
    return eval_body(body, new_env, output)

def _step_tail_named_let(forms, env, output):
    let_name = forms[1].name
    bindings_list = forms[2]
    body = forms[3:]
    if not is_proper_list(bindings_list):
        raise SchemeError("malformed named let bindings")
    bindings = scheme_list_to_pylist(bindings_list)
    for b in bindings:
        if not isinstance(b, Pair) or not is_proper_list(b):
            raise SchemeError("malformed named let binding")
        bl = scheme_list_to_pylist(b)
        if len(bl) != 2:
            raise SchemeError("malformed named let binding")
        if not isinstance(bl[0], Symbol):
            raise SchemeError("named let binding name must be a symbol")
    params = [scheme_list_to_pylist(b)[0] for b in bindings]
    inits = [scheme_list_to_pylist(b)[1] for b in bindings]
    init_vals = [eval_expr(init, env, output) for init in inits]
    new_env = Env({}, env)
    for p in params:
        new_env.bindings[p.name] = Uninitialized
    proc = Closure(make_schemelist(params), body, new_env)
    new_env.bindings[let_name] = proc
    for p, v in zip(params, init_vals):
        new_env.bindings[p.name] = v
    if len(body) == 1:
        return (body[0], new_env)
    return (_make_begin(body), new_env)


# ─── Builtins ──────────────────────────────────────────────────────────────

def _make_builtins():
    builtins = {}

    def _check_int(x, msg=""):
        if isinstance(x, bool) or not isinstance(x, int):
            raise SchemeError(f"expected integer, got {type(x).__name__}")

    def _check_str(x):
        if not isinstance(x, str):
            raise SchemeError("expected string")

    def _check_proper_list(x):
        if not is_proper_list(x):
            raise SchemeError("expected proper list")

    # Arithmetic
    def b_plus(args):
        for a in args:
            _check_int(a)
        return sum(args)

    def b_times(args):
        for a in args:
            _check_int(a)
        r = 1
        for a in args:
            r *= a
        return r

    def b_minus(args):
        for a in args:
            _check_int(a)
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for a in args[1:]:
            r -= a
        return r

    def b_quotient(args):
        if len(args) != 2:
            raise SchemeError("quotient: expected 2 arguments")
        a, b = args
        _check_int(a); _check_int(b)
        if b == 0:
            raise SchemeError("division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def b_remainder(args):
        if len(args) != 2:
            raise SchemeError("remainder: expected 2 arguments")
        a, b = args
        _check_int(a); _check_int(b)
        if b == 0:
            raise SchemeError("division by zero")
        r = abs(a) % abs(b)
        if a < 0:
            r = -r
        return r

    def b_modulo(args):
        if len(args) != 2:
            raise SchemeError("modulo: expected 2 arguments")
        a, b = args
        _check_int(a); _check_int(b)
        if b == 0:
            raise SchemeError("division by zero")
        return a % b

    def _make_compare(op):
        def cmp(args):
            if not args:
                raise SchemeError("comparison: expected at least 1 argument")
            for a in args:
                _check_int(a)
            for i in range(len(args) - 1):
                if not op(args[i], args[i + 1]):
                    return False
            return True
        return cmp

    def b_num_to_str(args):
        if len(args) not in (1, 2):
            raise SchemeError("number->string: expected 1 or 2 arguments")
        n = args[0]
        _check_int(n)
        radix = 10
        if len(args) == 2:
            radix = args[1]
            _check_int(radix)
            if radix not in (2, 8, 10, 16):
                raise SchemeError("number->string: radix must be 2, 8, 10, or 16")
        if radix == 10:
            return str(n)
        if n == 0:
            return "0"
        negative = n < 0
        n = abs(n)
        chars = "0123456789abcdef"
        digits = []
        while n > 0:
            digits.append(chars[n % radix])
            n //= radix
        result = ''.join(reversed(digits))
        return '-' + result if negative else result

    # Lists
    def b_cons(args):
        if len(args) != 2:
            raise SchemeError("cons: expected 2 arguments")
        return Pair(args[0], args[1])

    def b_car(args):
        if len(args) != 1:
            raise SchemeError("car: expected 1 argument")
        if not isinstance(args[0], Pair):
            raise SchemeError("car: expected a pair")
        return args[0].car

    def b_cdr(args):
        if len(args) != 1:
            raise SchemeError("cdr: expected 1 argument")
        if not isinstance(args[0], Pair):
            raise SchemeError("cdr: expected a pair")
        return args[0].cdr

    def b_list(args):
        return make_schemelist(args)

    def b_null_p(args):
        if len(args) != 1:
            raise SchemeError("null?: expected 1 argument")
        return args[0] is EmptyList

    def b_pair_p(args):
        if len(args) != 1:
            raise SchemeError("pair?: expected 1 argument")
        return isinstance(args[0], Pair)

    def b_list_p(args):
        if len(args) != 1:
            raise SchemeError("list?: expected 1 argument")
        return is_proper_list(args[0])

    def b_length(args):
        if len(args) != 1:
            raise SchemeError("length: expected 1 argument")
        _check_proper_list(args[0])
        count = 0
        cur = args[0]
        while isinstance(cur, Pair):
            count += 1
            cur = cur.cdr
        return count

    def b_append(args):
        for a in args[:-1]:
            _check_proper_list(a)
        result = args[-1] if args else EmptyList
        for a in reversed(args[:-1]):
            cur = a
            while isinstance(cur, Pair):
                result = Pair(cur.car, result)
                cur = cur.cdr
        return result

    def b_reverse(args):
        if len(args) != 1:
            raise SchemeError("reverse: expected 1 argument")
        _check_proper_list(args[0])
        result = EmptyList
        cur = args[0]
        while isinstance(cur, Pair):
            result = Pair(cur.car, result)
            cur = cur.cdr
        return result

    def b_apply(args):
        if len(args) < 2:
            raise SchemeError("apply: expected at least 2 arguments")
        f = args[0]
        mid = args[1:-1]
        lst = args[-1]
        _check_proper_list(lst)
        all_args = mid + scheme_list_to_pylist(lst)
        if isinstance(f, Closure):
            body, new_env = _apply_closure(f, all_args)
            return eval_body(body, new_env, _output_ref)
        elif isinstance(f, Builtin):
            return f.func(all_args)
        else:
            raise SchemeError("apply: first argument is not a procedure")

    # Equality
    def b_eq_p(args):
        if len(args) != 2:
            raise SchemeError("eq?: expected 2 arguments")
        a, b = args
        if isinstance(a, bool) or isinstance(b, bool):
            return isinstance(a, bool) and isinstance(b, bool) and a == b
        if isinstance(a, int) and isinstance(b, int):
            return a == b
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        if a is EmptyList and b is EmptyList:
            return True
        return a is b

    def _equal_p(a, b):
        if isinstance(a, bool) or isinstance(b, bool):
            return isinstance(a, bool) and isinstance(b, bool) and a == b
        if isinstance(a, int) and isinstance(b, int):
            return a == b
        if isinstance(a, str) and isinstance(b, str):
            return a == b
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        if a is EmptyList and b is EmptyList:
            return True
        if isinstance(a, (Closure, Builtin)) and isinstance(b, (Closure, Builtin)):
            return a is b
        if isinstance(a, Pair) and isinstance(b, Pair):
            while isinstance(a, Pair) and isinstance(b, Pair):
                if not _equal_p(a.car, b.car):
                    return False
                a = a.cdr
                b = b.cdr
            return _equal_p(a, b)
        return False

    def b_equal_p(args):
        if len(args) != 2:
            raise SchemeError("equal?: expected 2 arguments")
        return _equal_p(args[0], args[1])

    def b_not(args):
        if len(args) != 1:
            raise SchemeError("not: expected 1 argument")
        return args[0] is False

    def b_number_p(args):
        if len(args) != 1:
            raise SchemeError("number?: expected 1 argument")
        return isinstance(args[0], int) and not isinstance(args[0], bool)

    def b_symbol_p(args):
        if len(args) != 1:
            raise SchemeError("symbol?: expected 1 argument")
        return isinstance(args[0], Symbol)

    def b_string_p(args):
        if len(args) != 1:
            raise SchemeError("string?: expected 1 argument")
        return isinstance(args[0], str)

    def b_procedure_p(args):
        if len(args) != 1:
            raise SchemeError("procedure?: expected 1 argument")
        return isinstance(args[0], (Closure, Builtin))

    def b_string_append(args):
        for a in args:
            _check_str(a)
        return ''.join(args)

    # Output
    _output_ref = None  # Will be set per run

    def b_display(args):
        if len(args) != 1:
            raise SchemeError("display: expected 1 argument")
        _output_ref.append(display_repr(args[0]))
        return Unspecified

    def b_newline(args):
        if len(args) != 0:
            raise SchemeError("newline: expected 0 arguments")
        _output_ref.append("\n")
        return Unspecified

    def b_error(args):
        if len(args) < 1:
            raise SchemeError("error: expected at least 1 argument")
        msg = args[0]
        if not isinstance(msg, str):
            raise SchemeError("error: first argument must be a string")
        result = msg
        for irritant in args[1:]:
            result += " " + write_repr(irritant)
        raise SchemeError(result)

    builtins['+'] = Builtin('+', b_plus)
    builtins['*'] = Builtin('*', b_times)
    builtins['-'] = Builtin('-', b_minus)
    builtins['quotient'] = Builtin('quotient', b_quotient)
    builtins['remainder'] = Builtin('remainder', b_remainder)
    builtins['modulo'] = Builtin('modulo', b_modulo)
    builtins['='] = Builtin('=', _make_compare(lambda a, b: a == b))
    builtins['<'] = Builtin('<', _make_compare(lambda a, b: a < b))
    builtins['>'] = Builtin('>', _make_compare(lambda a, b: a > b))
    builtins['<='] = Builtin('<=', _make_compare(lambda a, b: a <= b))
    builtins['>='] = Builtin('>=', _make_compare(lambda a, b: a >= b))
    builtins['number->string'] = Builtin('number->string', b_num_to_str)
    builtins['cons'] = Builtin('cons', b_cons)
    builtins['car'] = Builtin('car', b_car)
    builtins['cdr'] = Builtin('cdr', b_cdr)
    builtins['list'] = Builtin('list', b_list)
    builtins['null?'] = Builtin('null?', b_null_p)
    builtins['pair?'] = Builtin('pair?', b_pair_p)
    builtins['list?'] = Builtin('list?', b_list_p)
    builtins['length'] = Builtin('length', b_length)
    builtins['append'] = Builtin('append', b_append)
    builtins['reverse'] = Builtin('reverse', b_reverse)
    builtins['apply'] = Builtin('apply', b_apply)
    builtins['eq?'] = Builtin('eq?', b_eq_p)
    builtins['equal?'] = Builtin('equal?', b_equal_p)
    builtins['not'] = Builtin('not', b_not)
    builtins['number?'] = Builtin('number?', b_number_p)
    builtins['symbol?'] = Builtin('symbol?', b_symbol_p)
    builtins['string?'] = Builtin('string?', b_string_p)
    builtins['procedure?'] = Builtin('procedure?', b_procedure_p)
    builtins['string-append'] = Builtin('string-append', b_string_append)
    builtins['display'] = Builtin('display', b_display)
    builtins['newline'] = Builtin('newline', b_newline)
    builtins['error'] = Builtin('error', b_error)

    return builtins


# ─── Global Environment ────────────────────────────────────────────────────

def _make_global_env():
    env = Env()
    builtins = _make_builtins()
    for name, proc in builtins.items():
        env.define(name, proc)
    return env


# ─── Main Entry Point ──────────────────────────────────────────────────────

def run(source):
    global _output_ref
    output = []
    _output_ref = output
    try:
        forms = read_all(source)
        env = _make_global_env()
        for form in forms:
            eval_expr(form, env, output)
        return ''.join(output)
    except SchemeError as e:
        e.output = ''.join(output)
        raise
    except RecursionError:
        raise SchemeError("maximum recursion depth exceeded", ''.join(output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(output))
