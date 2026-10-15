import sys
import re

# Remove int-to-str digit limit if available
try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass

class SchemeError(Exception):
    output: str
    def __init__(self, msg='', output=''):
        super().__init__(msg)
        self.output = output

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class EmptyList:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __repr__(self):
        return '()'

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env

class Builtin:
    __slots__ = ('func', 'name')
    def __init__(self, func, name=''):
        self.func = func
        self.name = name

class Env:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings=None, parent=None):
        self.bindings = bindings if bindings is not None else {}
        self.parent = parent

UNDEFINED = object()
UNDEFINED_LOCAL = object()

def is_true(v):
    return v is not False

def int_to_str(n):
    if n == 0:
        return "0"
    negative = n < 0
    if negative:
        n = -n
    base = 10**9
    digits = []
    while n > 0:
        n, r = divmod(n, base)
        digits.append(r)
    result = str(digits[-1])
    for d in reversed(digits[:-1]):
        result += str(d).zfill(9)
    if negative:
        result = '-' + result
    return result

def number_to_string(n, radix=10):
    if radix == 10:
        return int_to_str(n)
    elif radix == 16:
        if n < 0:
            return '-' + format(-n, 'x')
        return format(n, 'x')
    elif radix == 8:
        if n < 0:
            return '-' + format(-n, 'o')
        return format(n, 'o')
    elif radix == 2:
        if n < 0:
            return '-' + format(-n, 'b')
        return format(n, 'b')
    else:
        raise SchemeError("invalid radix")

def display_value(val, buf, write_mode=False):
    if isinstance(val, bool):
        buf.append('#t' if val else '#f')
    elif isinstance(val, int):
        buf.append(int_to_str(val))
    elif isinstance(val, str):
        if write_mode:
            escaped = val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            buf.append('"' + escaped + '"')
        else:
            buf.append(val)
    elif isinstance(val, Symbol):
        buf.append(val.name)
    elif isinstance(val, (Closure, Builtin)):
        buf.append('#<procedure>')
    elif val is UNDEFINED:
        pass
    elif val is UNDEFINED_LOCAL:
        pass
    elif isinstance(val, EmptyList):
        buf.append('()')
    elif isinstance(val, Pair):
        parts = ['(']
        current = val
        first = True
        while isinstance(current, Pair):
            if not first:
                parts.append(' ')
            first = False
            display_value(current.car, parts, write_mode)
            if isinstance(current.cdr, Pair):
                current = current.cdr
            else:
                parts.append(' . ')
                display_value(current.cdr, parts, write_mode)
                break
        parts.append(')')
        buf.append(''.join(parts))

def write_value(val, buf):
    display_value(val, buf, write_mode=True)

def is_proper_list(v):
    if isinstance(v, EmptyList):
        return True
    if isinstance(v, Pair):
        return is_proper_list(v.cdr)
    return False

def list_length(v):
    if not is_proper_list(v):
        raise SchemeError("length: not a proper list")
    n = 0
    while isinstance(v, Pair):
        n += 1
        v = v.cdr
    return n

def list_reverse(v):
    if not is_proper_list(v):
        raise SchemeError("reverse: not a proper list")
    result = EmptyList()
    while isinstance(v, Pair):
        result = Pair(v.car, result)
        v = v.cdr
    return result

def list_append(args):
    if not args:
        return EmptyList()
    last = args[-1]
    if len(args) == 1:
        return last
    # Build the result
    # All but last must be proper lists
    for a in args[:-1]:
        if not is_proper_list(a):
            raise SchemeError("append: not a proper list")
    # Build reversed
    result = last
    for a in reversed(args[:-1]):
        # Reverse a, then append to result
        # Actually, let's build iteratively
        pass
    # Better: walk all lists except last, build a list, then set cdr to last
    if len(args) == 1:
        return last
    # Collect all elements from all proper lists except last
    elements = []
    for a in args[:-1]:
        while isinstance(a, Pair):
            elements.append(a.car)
            a = a.cdr
    if not elements:
        return last
    # Build list
    result = Pair(elements[-1], last)
    for elem in reversed(elements[:-1]):
        result = Pair(elem, result)
    return result

def scheme_eq(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, int) or isinstance(b, int):
        return isinstance(a, int) and isinstance(b, int) and a == b
    if isinstance(a, Symbol) or isinstance(b, Symbol):
        return isinstance(a, Symbol) and isinstance(b, Symbol) and a.name == b.name
    if isinstance(a, str) or isinstance(b, str):
        return isinstance(a, str) and isinstance(b, str) and a is b
    if a is UNDEFINED and b is UNDEFINED:
        return True
    return a is b

def scheme_equal(a, b):
    stack = [(a, b)]
    while stack:
        x, y = stack.pop()
        if isinstance(x, bool) or isinstance(y, bool):
            if not (isinstance(x, bool) and isinstance(y, bool) and x == y):
                return False
        elif isinstance(x, int) or isinstance(y, int):
            if not (isinstance(x, int) and isinstance(y, int) and x == y):
                return False
        elif isinstance(x, str) or isinstance(y, str):
            if not (isinstance(x, str) and isinstance(y, str) and x == y):
                return False
        elif isinstance(x, Symbol) or isinstance(y, Symbol):
            if not (isinstance(x, Symbol) and isinstance(y, Symbol) and x.name == y.name):
                return False
        elif x is UNDEFINED and y is UNDEFINED:
            continue
        elif isinstance(x, (Closure, Builtin)) or isinstance(y, (Closure, Builtin)):
            if x is not y:
                return False
        elif isinstance(x, EmptyList) or isinstance(y, EmptyList):
            if not (isinstance(x, EmptyList) and isinstance(y, EmptyList)):
                return False
        elif isinstance(x, Pair) and isinstance(y, Pair):
            stack.append((x.cdr, y.cdr))
            stack.append((x.car, y.car))
        else:
            return False
    return True

def iterate_proper_list(lst):
    """Yield elements of a proper list. Raise if not proper."""
    while isinstance(lst, Pair):
        yield lst.car
        lst = lst.cdr
    if not isinstance(lst, EmptyList):
        raise SchemeError("expected proper list")

def tokenize(source):
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
            tokens.append('(')
            i += 1
        elif c == ')':
            tokens.append(')')
            i += 1
        elif c == "'":
            tokens.append("'")
            i += 1
        elif c == '"':
            i += 1
            s = []
            terminated = False
            while i < n:
                if source[i] == '\\' and i + 1 < n:
                    if source[i+1] == '"':
                        s.append('"')
                        i += 2
                    elif source[i+1] == '\\':
                        s.append('\\')
                        i += 2
                    elif source[i+1] == 'n':
                        s.append('\n')
                        i += 2
                    else:
                        raise SchemeError("invalid escape in string")
                elif source[i] == '"':
                    i += 1
                    terminated = True
                    break
                else:
                    s.append(source[i])
                    i += 1
            if not terminated:
                raise SchemeError("unterminated string")
            tokens.append(('str', ''.join(s)))
        else:
            start = i
            while i < n and source[i] not in ' \t\n\r()";\'':
                i += 1
            token = source[start:i]
            if token == '#t':
                tokens.append(True)
            elif token == '#f':
                tokens.append(False)
            elif token.startswith('#'):
                raise SchemeError(f"invalid token: {token}")
            elif re.fullmatch(r'[+-]?[0-9]+', token):
                tokens.append(int(token))
            else:
                tokens.append(Symbol(token))
    return tokens

def parse_one(tokens, i):
    tok = tokens[i]
    if tok == '(':
        i += 1
        return parse_list(tokens, i)
    if tok == "'":
        i += 1
        if i >= len(tokens):
            raise SchemeError("quote not followed by datum")
        datum, i = parse_one(tokens, i)
        return Pair(Symbol('quote'), Pair(datum, EmptyList())), i
    if tok == ')':
        raise SchemeError("unexpected )")
    if isinstance(tok, tuple) and tok[0] == 'str':
        return tok[1], i + 1
    return tok, i + 1

def parse_list(tokens, i):
    elements = []
    while i < len(tokens):
        tok = tokens[i]
        if tok == ')':
            i += 1
            result = EmptyList()
            for elem in reversed(elements):
                result = Pair(elem, result)
            return result, i
        if isinstance(tok, Symbol) and tok.name == '.':
            if not elements:
                raise SchemeError("dot must be preceded by at least one element")
            i += 1
            if i >= len(tokens):
                raise SchemeError("dot not followed by datum")
            tail, i = parse_one(tokens, i)
            if i >= len(tokens) or tokens[i] != ')':
                raise SchemeError("expected ) after dotted list")
            i += 1
            result = Pair(tail, EmptyList())
            for elem in reversed(elements):
                result = Pair(elem, result)
            return result, i
        elem, i = parse_one(tokens, i)
        elements.append(elem)
    raise SchemeError("unbalanced parenthesis")

def read_all(source):
    tokens = tokenize(source)
    forms = []
    i = 0
    n = len(tokens)
    while i < n:
        form, i = parse_one(tokens, i)
        forms.append(form)
    return forms

def make_global_env():
    env = Env({}, None)
    return env

def lookup(name, env):
    e = env
    while e is not None:
        if name in e.bindings:
            val = e.bindings[name]
            if val is UNDEFINED_LOCAL:
                raise SchemeError(f"variable '{name}' referenced before definition")
            return val
        e = e.parent
    raise SchemeError(f"unbound variable: {name}")

def set_variable(name, value, env):
    e = env
    while e is not None:
        if name in e.bindings:
            e.bindings[name] = value
            return
        e = e.parent
    raise SchemeError(f"unbound variable: {name}")

def bind_params(closure, args):
    formals = closure.formals
    if isinstance(formals, Symbol):
        # Lone symbol: all args in a list
        lst = EmptyList()
        for a in reversed(args):
            lst = Pair(a, lst)
        return Env({formals.name: lst}, closure.env)
    elif isinstance(formals, Pair):
        # Proper list or dotted list
        fixed = []
        rest_sym = None
        current = formals
        while isinstance(current, Pair):
            if isinstance(current.cdr, Pair):
                fixed.append(current.car)
                current = current.cdr
            elif isinstance(current.cdr, Symbol):
                fixed.append(current.car)
                rest_sym = current.cdr
                break
            elif isinstance(current.cdr, EmptyList):
                fixed.append(current.car)
                break
            else:
                raise SchemeError("malformed formals")
        if rest_sym is not None:
            if len(args) < len(fixed):
                raise SchemeError("wrong number of arguments")
            bindings = {}
            for i, v in enumerate(fixed):
                bindings[v.name] = args[i]
            rest_lst = EmptyList()
            for a in reversed(args[len(fixed):]):
                rest_lst = Pair(a, rest_lst)
            bindings[rest_sym.name] = rest_lst
            return Env(bindings, closure.env)
        else:
            if len(args) != len(fixed):
                raise SchemeError("wrong number of arguments")
            bindings = {}
            for i, v in enumerate(fixed):
                bindings[v.name] = args[i]
            return Env(bindings, closure.env)
    else:
        raise SchemeError("malformed formals")

def scan_internal_defines(body_forms):
    """Return list of names from top-level (define name ...) forms in body."""
    names = []
    for f in body_forms:
        if isinstance(f, Pair) and isinstance(f.car, Symbol) and f.car.name == 'define':
            rest = f.cdr
            if rest is EmptyList:
                continue
            first = rest.car
            if isinstance(first, Symbol):
                names.append(first.name)
            elif isinstance(first, Pair):
                if isinstance(first.car, Symbol):
                    names.append(first.car.name)
    return names

def evaluate(form, env, output):
    """Evaluate form in env. Form is in tail position. Returns value."""
    while True:
        # Atoms
        if isinstance(form, int):
            return form
        if isinstance(form, bool):
            return form
        if isinstance(form, str):
            return form
        if form is UNDEFINED:
            return UNDEFINED
        if isinstance(form, Symbol):
            return lookup(form.name, env)
        if isinstance(form, EmptyList):
            return form
        if not isinstance(form, Pair):
            raise SchemeError(f"invalid form: {form}")

        head = form.car
        rest = form.cdr

        if isinstance(head, Symbol):
            name = head.name
            if name == 'quote':
                if rest is EmptyList or rest.cdr is not EmptyList:
                    raise SchemeError("malformed quote")
                return rest.car
            elif name == 'if':
                if rest is EmptyList:
                    raise SchemeError("malformed if")
                test_expr = rest.car
                then_cdr = rest.cdr
                if then_cdr is EmptyList:
                    raise SchemeError("malformed if")
                then_expr = then_cdr.car
                else_expr = None
                if then_cdr.cdr is not EmptyList:
                    if then_cdr.cdr.cdr is not EmptyList:
                        raise SchemeError("malformed if")
                    else_expr = then_cdr.cdr.car
                test_val = evaluate(test_expr, env, output)
                if is_true(test_val):
                    form = then_expr
                    continue
                else:
                    if else_expr is not None:
                        form = else_expr
                        continue
                    else:
                        return UNDEFINED
            elif name == 'begin':
                if rest is EmptyList:
                    raise SchemeError("malformed begin")
                body = rest
                while body.cdr is not EmptyList and body.cdr.cdr is not EmptyList:
                    evaluate(body.car, env, output)
                    body = body.cdr
                form = body.car
                continue
            elif name == 'define':
                if rest is EmptyList:
                    raise SchemeError("malformed define")
                first = rest.car
                if isinstance(first, Pair):
                    name_sym = first.car
                    if not isinstance(name_sym, Symbol):
                        raise SchemeError("malformed define")
                    formals = first.cdr
                    body = rest.cdr
                    if body is EmptyList:
                        raise SchemeError("malformed define")
                    body_forms = list(body)
                    lam = Closure(formals, body_forms, env)
                    env.bindings[name_sym.name] = lam
                    return UNDEFINED
                elif isinstance(first, Symbol):
                    if rest.cdr is EmptyList or rest.cdr.cdr is not EmptyList:
                        raise SchemeError("malformed define")
                    expr = rest.cdr.car
                    val = evaluate(expr, env, output)
                    env.bindings[first.name] = val
                    return UNDEFINED
                else:
                    raise SchemeError("malformed define")
            elif name == 'set!':
                if rest is EmptyList or rest.cdr is EmptyList or rest.cdr.cdr is not EmptyList:
                    raise SchemeError("malformed set!")
                var = rest.car
                expr = rest.cdr.car
                if not isinstance(var, Symbol):
                    raise SchemeError("set! variable must be a symbol")
                val = evaluate(expr, env, output)
                set_variable(var.name, val, env)
                return UNDEFINED
            elif name == 'cond':
                clauses = rest
                if clauses is EmptyList:
                    return UNDEFINED
                while True:
                    clause = clauses.car
                    if not isinstance(clause, Pair):
                        raise SchemeError("malformed cond clause")
                    test = clause.car
                    clause_body = clause.cdr
                    is_else = isinstance(test, Symbol) and test.name == 'else'
                    if is_else:
                        if clauses.cdr is not EmptyList:
                            raise SchemeError("else must be last cond clause")
                        if clause_body is EmptyList:
                            raise SchemeError("malformed else clause")
                        exprs = clause_body
                        while exprs.cdr is not EmptyList:
                            evaluate(exprs.car, env, output)
                            exprs = exprs.cdr
                        form = exprs.car
                        continue
                    test_val = evaluate(test, env, output)
                    if is_true(test_val):
                        if clause_body is EmptyList:
                            return test_val
                        exprs = clause_body
                        while exprs.cdr is not EmptyList:
                            evaluate(exprs.car, env, output)
                            exprs = exprs.cdr
                        form = exprs.car
                        continue
                    if clauses.cdr is EmptyList:
                        return UNDEFINED
                    clauses = clauses.cdr
            elif name == 'and':
                exprs = rest
                if exprs is EmptyList:
                    return True
                while exprs.cdr is not EmptyList:
                    val = evaluate(exprs.car, env, output)
                    if val is False:
                        return False
                    exprs = exprs.cdr
                form = exprs.car
                continue
            elif name == 'or':
                exprs = rest
                if exprs is EmptyList:
                    return False
                while exprs.cdr is not EmptyList:
                    val = evaluate(exprs.car, env, output)
                    if is_true(val):
                        return val
                    exprs = exprs.cdr
                form = exprs.car
                continue
            elif name == 'let':
                if rest is EmptyList:
                    raise SchemeError("malformed let")
                first = rest.car
                if isinstance(first, Symbol):
                    # Named let
                    let_name = first
                    if rest.cdr is EmptyList:
                        raise SchemeError("malformed named let")
                    bindings_list = rest.cdr.car
                    body = rest.cdr.cdr
                    if body is EmptyList:
                        raise SchemeError("malformed named let: empty body")
                    if not isinstance(bindings_list, Pair) and not isinstance(bindings_list, EmptyList):
                        raise SchemeError("malformed let bindings")
                    vars_list = []
                    inits = []
                    for binding in iterate_proper_list(bindings_list):
                        if not isinstance(binding, Pair) or binding.cdr is EmptyList or binding.cdr.cdr is not EmptyList:
                            raise SchemeError("malformed let binding")
                        v = binding.car
                        init = binding.cdr.car
                        if not isinstance(v, Symbol):
                            raise SchemeError("let binding variable must be a symbol")
                        vars_list.append(v)
                        inits.append(evaluate(init, env, output))
                    body_forms = list(body)
                    # Create closure env
                    closure_env = Env({}, env)
                    closure = Closure(vars_list, body_forms, closure_env)
                    closure_env.bindings[let_name.name] = closure
                    # Create initial env
                    new_env = Env({}, closure_env)
                    for v, val in zip(vars_list, inits):
                        new_env.bindings[v.name] = val
                    # Handle internal defines in body
                    int_names = scan_internal_defines(body_forms)
                    if int_names:
                        new_env = Env({n: UNDEFINED_LOCAL for n in int_names}, new_env)
                    for f in body_forms[:-1]:
                        evaluate(f, new_env, output)
                    form = body_forms[-1]
                    env = new_env
                    continue
                else:
                    # Regular let
                    bindings_list = first
                    body = rest.cdr
                    if body is EmptyList:
                        raise SchemeError("malformed let: empty body")
                    if not isinstance(bindings_list, Pair) and not isinstance(bindings_list, EmptyList):
                        raise SchemeError("malformed let bindings")
                    new_env = Env({}, env)
                    for binding in iterate_proper_list(bindings_list):
                        if not isinstance(binding, Pair) or binding.cdr is EmptyList or binding.cdr.cdr is not EmptyList:
                            raise SchemeError("malformed let binding")
                        v = binding.car
                        init = binding.cdr.car
                        if not isinstance(v, Symbol):
                            raise SchemeError("let binding variable must be a symbol")
                        new_env.bindings[v.name] = evaluate(init, env, output)
                    body_forms = list(body)
                    int_names = scan_internal_defines(body_forms)
                    if int_names:
                        new_env = Env({n: UNDEFINED_LOCAL for n in int_names}, new_env)
                    for f in body_forms[:-1]:
                        evaluate(f, new_env, output)
                    form = body_forms[-1]
                    env = new_env
                    continue
            elif name == 'let*':
                if rest is EmptyList:
                    raise SchemeError("malformed let*")
                bindings_list = rest.car
                body = rest.cdr
                if body is EmptyList:
                    raise SchemeError("malformed let*: empty body")
                if not isinstance(bindings_list, Pair) and not isinstance(bindings_list, EmptyList):
                    raise SchemeError("malformed let* bindings")
                new_env = Env({}, env)
                for binding in iterate_proper_list(bindings_list):
                    if not isinstance(binding, Pair) or binding.cdr is EmptyList or binding.cdr.cdr is not EmptyList:
                        raise SchemeError("malformed let* binding")
                    v = binding.car
                    init = binding.cdr.car
                    if not isinstance(v, Symbol):
                        raise SchemeError("let* binding variable must be a symbol")
                    new_env.bindings[v.name] = evaluate(init, new_env, output)
                body_forms = list(body)
                int_names = scan_internal_defines(body_forms)
                if int_names:
                    new_env = Env({n: UNDEFINED_LOCAL for n in int_names}, new_env)
                for f in body_forms[:-1]:
                    evaluate(f, new_env, output)
                form = body_forms[-1]
                env = new_env
                continue
            elif name == 'letrec':
                if rest is EmptyList:
                    raise SchemeError("malformed letrec")
                bindings_list = rest.car
                body = rest.cdr
                if body is EmptyList:
                    raise SchemeError("malformed letrec: empty body")
                if not isinstance(bindings_list, Pair) and not isinstance(bindings_list, EmptyList):
                    raise SchemeError("malformed letrec bindings")
                new_env = Env({}, env)
                for binding in iterate_proper_list(bindings_list):
                    if not isinstance(binding, Pair) or binding.cdr is EmptyList or binding.cdr.cdr is not EmptyList:
                        raise SchemeError("malformed letrec binding")
                    v = binding.car
                    if not isinstance(v, Symbol):
                        raise SchemeError("letrec binding variable must be a symbol")
                    new_env.bindings[v.name] = UNDEFINED_LOCAL
                for binding in iterate_proper_list(bindings_list):
                    v = binding.car
                    init = binding.cdr.car
                    new_env.bindings[v.name] = evaluate(init, new_env, output)
                body_forms = list(body)
                int_names = scan_internal_defines(body_forms)
                if int_names:
                    new_env = Env({n: UNDEFINED_LOCAL for n in int_names}, new_env)
                for f in body_forms[:-1]:
                    evaluate(f, new_env, output)
                form = body_forms[-1]
                env = new_env
                continue
            elif name == 'lambda':
                if rest is EmptyList:
                    raise SchemeError("malformed lambda")
                formals = rest.car
                body = rest.cdr
                if body is EmptyList:
                    raise SchemeError("malformed lambda: empty body")
                # Validate formals
                if isinstance(formals, Symbol):
                    pass
                elif isinstance(formals, Pair):
                    current = formals
                    while isinstance(current, Pair):
                        if not isinstance(current.car, Symbol):
                            raise SchemeError("malformed lambda formals")
                        if isinstance(current.cdr, Pair):
                            current = current.cdr
                        elif isinstance(current.cdr, Symbol):
                            pass
                        elif isinstance(current.cdr, EmptyList):
                            pass
                        else:
                            raise SchemeError("malformed lambda formals")
                elif isinstance(formals, EmptyList):
                    pass
                else:
                    raise SchemeError("malformed lambda formals")
                return Closure(formals, list(body), env)
            else:
                # Not a special form - fall through to application
                pass

        # Application
        op_val = evaluate(head, env, output)

        # Check if it's a dotted list (not a proper list) - error for application
        if not isinstance(rest, Pair) and not isinstance(rest, EmptyList):
            raise SchemeError("invalid application: dotted list")

        # Evaluate arguments
        args = []
        for a in rest:
            if isinstance(a, Pair):
                args.append(evaluate(a.car, env, output))
                rest = a.cdr
            else:
                break

        # Handle apply specially for tail calls
        if isinstance(op_val, Builtin) and op_val.name == 'apply':
            if len(args) < 2:
                raise SchemeError("apply: wrong number of arguments")
            f = args[0]
            extra = args[1:-1]
            lst = args[-1]
            if not is_proper_list(lst):
                raise SchemeError("apply: last argument must be a proper list")
            all_args = extra + list(iterate_proper_list(lst))
            if isinstance(f, Builtin):
                return f.func(all_args, output)
            if isinstance(f, Closure):
                new_env = bind_params(f, all_args)
                body_forms = f.body
                int_names = scan_internal_defines(body_forms)
                if int_names:
                    new_env = Env({n: UNDEFINED_LOCAL for n in int_names}, new_env)
                for bf in body_forms[:-1]:
                    evaluate(bf, new_env, output)
                form = body_forms[-1]
                env = new_env
                continue
            raise SchemeError("apply: first argument is not a procedure")

        if isinstance(op_val, Builtin):
            return op_val.func(args, output)
        if isinstance(op_val, Closure):
            new_env = bind_params(op_val, args)
            body_forms = op_val.body
            int_names = scan_internal_defines(body_forms)
            if int_names:
                new_env = Env({n: UNDEFINED_LOCAL for n in int_names}, new_env)
            for bf in body_forms[:-1]:
                evaluate(bf, new_env, output)
            form = body_forms[-1]
            env = new_env
            continue
        raise SchemeError("attempt to apply non-procedure")

def make_builtin(func, name=''):
    return Builtin(func, name)

def build_global_env():
    env = Env({}, None)

    # Numbers
    env.bindings['+'] = make_builtin(lambda args, out: sum(args), '+')
    env.bindings['*'] = make_builtin(lambda args, out: (lambda: (lambda r: r)(eval_product(args)))(), '*')

    # Let me redo these more carefully
    def builtin_plus(args, out):
        for a in args:
            if isinstance(a, bool) or not isinstance(a, int):
                raise SchemeError("+ : non-integer argument")
        return sum(args)

    def builtin_star(args, out):
        for a in args:
            if isinstance(a, bool) or not isinstance(a, int):
                raise SchemeError("* : non-integer argument")
        r = 1
        for a in args:
            r *= a
        return r

    def builtin_minus(args, out):
        for a in args:
            if isinstance(a, bool) or not isinstance(a, int):
                raise SchemeError("- : non-integer argument")
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for a in args[1:]:
            r -= a
        return r

    def builtin_quotient(args, out):
        if len(args) != 2:
            raise SchemeError("quotient: exactly 2 arguments")
        a, b = args
        if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int) or not isinstance(b, int):
            raise SchemeError("quotient: non-integer argument")
        if b == 0:
            raise SchemeError("quotient: division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def builtin_remainder(args, out):
        if len(args) != 2:
            raise SchemeError("remainder: exactly 2 arguments")
        a, b = args
        if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int) or not isinstance(b, int):
            raise SchemeError("remainder: non-integer argument")
        if b == 0:
            raise SchemeError("remainder: division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return a - q * b

    def builtin_modulo(args, out):
        if len(args) != 2:
            raise SchemeError("modulo: exactly 2 arguments")
        a, b = args
        if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int) or not isinstance(b, int):
            raise SchemeError("modulo: non-integer argument")
        if b == 0:
            raise SchemeError("modulo: division by zero")
        r = builtin_remainder([a, b], out)
        if r != 0 and (r < 0) != (b < 0):
            r += b
        return r

    def make_comparison(op_func):
        def cmp(args, out):
            if len(args) == 0:
                raise SchemeError("comparison: at least 1 argument")
            for a in args:
                if isinstance(a, bool) or not isinstance(a, int):
                    raise SchemeError("comparison: non-integer argument")
            for i in range(len(args) - 1):
                if not op_func(args[i], args[i+1]):
                    return False
            return True
        return cmp

    env.bindings['+'] = make_builtin(builtin_plus, '+')
    env.bindings['*'] = make_builtin(builtin_star, '*')
    env.bindings['-'] = make_builtin(builtin_minus, '-')
    env.bindings['quotient'] = make_builtin(builtin_quotient, 'quotient')
    env.bindings['remainder'] = make_builtin(builtin_remainder, 'remainder')
    env.bindings['modulo'] = make_builtin(builtin_modulo, 'modulo')
    env.bindings['='] = make_builtin(make_comparison(lambda a, b: a == b), '=')
    env.bindings['<'] = make_builtin(make_comparison(lambda a, b: a < b), '<')
    env.bindings['>'] = make_builtin(make_comparison(lambda a, b: a > b), '>')
    env.bindings['<='] = make_builtin(make_comparison(lambda a, b: a <= b), '<=')
    env.bindings['>='] = make_builtin(make_comparison(lambda a, b: a >= b), '>=')

    def builtin_number_to_string(args, out):
        if len(args) not in (1, 2):
            raise SchemeError("number->string: wrong number of arguments")
        n = args[0]
        if isinstance(n, bool) or not isinstance(n, int):
            raise SchemeError("number->string: non-integer argument")
        radix = 10
        if len(args) == 2:
            radix = args[1]
            if isinstance(radix, bool) or not isinstance(radix, int) or radix not in (2, 8, 10, 