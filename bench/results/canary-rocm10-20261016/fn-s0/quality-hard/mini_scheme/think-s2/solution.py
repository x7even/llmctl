import sys
import re

try:
    sys.setrecursionlimit(200000)
except Exception:
    pass
try:
    sys.set_int_max_str_digits(0)
except (AttributeError, ValueError):
    pass


class SchemeError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output


# === Data Types ===

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

class NilType:
    pass
NIL = NilType()

class UnspecifiedType:
    pass
UNSPECIFIED = UnspecifiedType()

class UninitializedType:
    pass
UNINITIALIZED = UninitializedType()

class SchemeBool:
    __slots__ = ('value',)
    def __init__(self, value):
        self.value = value

TRUE = SchemeBool(True)
FALSE = SchemeBool(False)

class Closure:
    __slots__ = ('formals', 'body', 'env')
    def __init__(self, formals, body, env):
        self.formals = formals
        self.body = body
        self.env = env

class Builtin:
    __slots__ = ('name', 'func', 'min_args', 'max_args')
    def __init__(self, name, func, min_args=0, max_args=None):
        self.name = name
        self.func = func
        self.min_args = min_args
        self.max_args = max_args


# === Environment ===

class Frame:
    __slots__ = ('bindings', 'parent')
    def __init__(self, bindings=None, parent=None):
        self.bindings = bindings if bindings is not None else {}
        self.parent = parent

    def lookup(self, name):
        frame = self
        while frame is not None:
            if name in frame.bindings:
                val = frame.bindings[name]
                if val is UNINITIALIZED:
                    raise SchemeError(f"variable not yet defined: {name}")
                return val
            frame = frame.parent
        raise SchemeError(f"unbound variable: {name}")

    def set(self, name, value):
        frame = self
        while frame is not None:
            if name in frame.bindings:
                frame.bindings[name] = value
                return
            frame = frame.parent
        raise SchemeError(f"unbound variable: {name}")

    def define(self, name, value):
        self.bindings[name] = value


# === Reader ===

def tokenize(source):
    tokens = []
    i = 0
    n = len(source)
    while i < n:
        c = source[i]
        if c in ' \t\n\r':
            i += 1
            continue
        if c == ';':
            while i < n and source[i] != '\n':
                i += 1
            continue
        if c == '(':
            tokens.append(('(', '('))
            i += 1
            continue
        if c == ')':
            tokens.append((')', ')'))
            i += 1
            continue
        if c == "'":
            tokens.append(("'", "'"))
            i += 1
            continue
        if c == '"':
            i += 1
            chars = []
            closed = False
            while i < n:
                c = source[i]
                if c == '"':
                    closed = True
                    i += 1
                    break
                if c == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError("unterminated string escape")
                    ec = source[i]
                    if ec == '"':
                        chars.append('"')
                    elif ec == '\\':
                        chars.append('\\')
                    elif ec == 'n':
                        chars.append('\n')
                    else:
                        raise SchemeError(f"invalid escape: \\{ec}")
                    i += 1
                else:
                    chars.append(c)
                    i += 1
            if not closed:
                raise SchemeError("unterminated string")
            tokens.append(('string', ''.join(chars)))
            continue
        start = i
        while i < n and source[i] not in ' \t\n\r()";\'':
            i += 1
        tokens.append(('atom', source[start:i]))
    return tokens


_int_re = re.compile(r'^[+-]?[0-9]+$')

def parse_all(tokens):
    pos = [0]

    def peek():
        if pos[0] < len(tokens):
            return tokens[pos[0]]
        return None

    def consume():
        tok = tokens[pos[0]]
        pos[0] += 1
        return tok

    def parse_datum():
        if pos[0] >= len(tokens):
            raise SchemeError("unexpected end of input")
        kind, val = consume()
        if kind == '(':
            return parse_list_body()
        if kind == ')':
            raise SchemeError("unexpected )")
        if kind == "'":
            datum = parse_datum()
            return Pair(Symbol('quote'), Pair(datum, NIL))
        if kind == 'string':
            return val
        return parse_atom(val)

    def parse_list_body():
        elements = []
        has_dot = False
        cdr_val = None
        while True:
            if pos[0] >= len(tokens):
                raise SchemeError("unexpected end of input, expected )")
            kind, val = peek()
            if kind == ')':
                consume()
                break
            if kind == 'atom' and val == '.':
                if has_dot:
                    raise SchemeError("multiple dots in list")
                if not elements:
                    raise SchemeError("dot with no preceding elements")
                consume()
                has_dot = True
                cdr_val = parse_datum()
                if pos[0] >= len(tokens):
                    raise SchemeError("unexpected end of input, expected )")
                kind2, val2 = consume()
                if kind2 != ')':
                    raise SchemeError("expected ) after dotted pair")
                break
            elements.append(parse_datum())
        if has_dot:
            result = cdr_val
            for elem in reversed(elements):
                result = Pair(elem, result)
            return result
        else:
            result = NIL
            for elem in reversed(elements):
                result = Pair(elem, result)
            return result

    def parse_atom(s):
        if s == '#t':
            return TRUE
        if s == '#f':
            return FALSE
        if s.startswith('#'):
            raise SchemeError(f"invalid token: {s}")
        if _int_re.match(s):
            return int(s)
        return Symbol(s)

    forms = []
    while pos[0] < len(tokens):
        forms.append(parse_datum())
    return forms


# === Utilities ===

def scheme_list_to_py(lst):
    result = []
    while isinstance(lst, Pair):
        result.append(lst.car)
        lst = lst.cdr
    if not isinstance(lst, NilType):
        raise SchemeError("not a proper list")
    return result

def py_list_to_scheme(lst):
    result = NIL
    for item in reversed(lst):
        result = Pair(item, result)
    return result

def truthy(val):
    return val is not FALSE

def is_proper_list(val):
    while isinstance(val, Pair):
        val = val.cdr
    return isinstance(val, NilType)

def is_procedure(val):
    return isinstance(val, (Closure, Builtin))

def int_to_str(n):
    if n == 0:
        return '0'
    if n < 0:
        return '-' + int_to_str(-n)
    result = []
    while n > 0:
        result.append(chr(48 + n % 10))
        n //= 10
    return ''.join(reversed(result))

def int_to_str_radix(n, radix):
    digits = '0123456789abcdef'
    if n == 0:
        return '0'
    neg = n < 0
    n = abs(n)
    result = []
    while n > 0:
        result.append(digits[n % radix])
        n //= radix
    s = ''.join(reversed(result))
    if neg:
        return '-' + s
    return s


# === Display ===

def display_repr(val, output, write_mode=False):
    if val is TRUE:
        output.append('#t')
    elif val is FALSE:
        output.append('#f')
    elif isinstance(val, int):
        output.append(int_to_str(val))
    elif isinstance(val, str):
        if write_mode:
            output.append(_escape_string(val))
        else:
            output.append(val)
    elif isinstance(val, Symbol):
        output.append(val.name)
    elif isinstance(val, NilType):
        output.append('()')
    elif isinstance(val, UnspecifiedType):
        pass
    elif isinstance(val, (Closure, Builtin)):
        output.append('#<procedure>')
    elif isinstance(val, Pair):
        output.append('(')
        first = True
        current = val
        while isinstance(current, Pair):
            if not first:
                output.append(' ')
            first = False
            display_repr(current.car, output, write_mode)
            current = current.cdr
        if isinstance(current, NilType):
            output.append(')')
        else:
            output.append(' . ')
            display_repr(current, output, write_mode)
            output.append(')')
    else:
        output.append(str(val))

def _escape_string(s):
    parts = ['"']
    for c in s:
        if c == '"':
            parts.append('\\"')
        elif c == '\\':
            parts.append('\\\\')
        elif c == '\n':
            parts.append('\\n')
        else:
            parts.append(c)
    parts.append('"')
    return ''.join(parts)

def write_repr(val):
    out = []
    display_repr(val, out, write_mode=True)
    return ''.join(out)


# === Evaluator ===

class TailCall:
    __slots__ = ('proc', 'args')
    def __init__(self, proc, args):
        self.proc = proc
        self.args = args

_current_output = []

def eval_expr(expr, env, is_tail, output):
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        return expr
    if expr is TRUE or expr is FALSE:
        return expr
    if isinstance(expr, NilType):
        return expr
    if isinstance(expr, UnspecifiedType):
        return expr
    if isinstance(expr, Symbol):
        return env.lookup(expr.name)
    if isinstance(expr, Pair):
        head = expr.car
        if isinstance(head, Symbol):
            name = head.name
            if name == 'quote':
                return _handle_quote(expr, env)
            elif name == 'if':
                return _handle_if(expr, env, is_tail, output)
            elif name == 'define':
                return _handle_define(expr, env, output)
            elif name == 'set!':
                return _handle_set(expr, env, output)
            elif name == 'begin':
                return _handle_begin(expr, env, is_tail, output)
            elif name == 'cond':
                return _handle_cond(expr, env, is_tail, output)
            elif name == 'and':
                return _handle_and(expr, env, is_tail, output)
            elif name == 'or':
                return _handle_or(expr, env, is_tail, output)
            elif name == 'lambda':
                return _handle_lambda(expr, env)
            elif name == 'let':
                return _handle_let(expr, env, is_tail, output)
            elif name == 'let*':
                return _handle_letstar(expr, env, is_tail, output)
            elif name == 'letrec':
                return _handle_letrec(expr, env, is_tail, output)
            elif name == 'apply':
                return _handle_apply(expr, env, is_tail, output)
        return _handle_application(expr, env, is_tail, output)
    raise SchemeError("invalid expression")


def _handle_quote(expr, env):
    rest = expr.cdr
    if isinstance(rest, NilType):
        raise SchemeError("malformed quote")
    return rest.car

def _handle_if(expr, env, is_tail, output):
    rest = expr.cdr
    if isinstance(rest, NilType):
        raise SchemeError("malformed if")
    test = eval_expr(rest.car, env, False, output)
    rest = rest.cdr
    if isinstance(rest, NilType):
        raise SchemeError("malformed if")
    then_expr = rest.car
    rest = rest.cdr
    if truthy(test):
        return eval_expr(then_expr, env, is_tail, output)
    else:
        if isinstance(rest, NilType):
            return UNSPECIFIED
        return eval_expr(rest.car, env, is_tail, output)

def _handle_define(expr, env, output):
    rest = expr.cdr
    if isinstance(rest, NilType):
        raise SchemeError("malformed define")
    target = rest.car
    if isinstance(target, Symbol):
        rest2 = rest.cdr
        if isinstance(rest2, NilType):
            raise SchemeError("malformed define")
        val = eval_expr(rest2.car, env, False, output)
        env.define(target.name, val)
        return UNSPECIFIED
    elif isinstance(target, Pair):
        name = target.car
        if not isinstance(name, Symbol):
            raise SchemeError("malformed define")
        formals = target.cdr
        body_rest = rest.cdr
        if isinstance(body_rest, NilType):
            raise SchemeError("malformed define")
        body = []
        br = body_rest
        while isinstance(br, Pair):
            body.append(br.car)
            br = br.cdr
        if not body:
            raise SchemeError("malformed define")
        closure = Closure(formals, body, env)
        env.define(name.name, closure)
        return UNSPECIFIED
    else:
        raise SchemeError("malformed define")

def _handle_set(expr, env, output):
    rest = expr.cdr
    if isinstance(rest, NilType):
        raise SchemeError("malformed set!")
    name = rest.car
    if not isinstance(name, Symbol):
        raise SchemeError("malformed set!")
    rest = rest.cdr
    if isinstance(rest, NilType):
        raise SchemeError("malformed set!")
    val = eval_expr(rest.car, env, False, output)
    env.set(name.name, val)
    return UNSPECIFIED

def _handle_begin(expr, env, is_tail, output):
    forms = []
    rest = expr.cdr
    while isinstance(rest, Pair):
        forms.append(rest.car)
        rest = rest.cdr
    if not forms:
        raise SchemeError("malformed begin")
    for form in forms[:-1]:
        eval_expr(form, env, False, output)
    return eval_expr(forms[-1], env, is_tail, output)

def _handle_cond(expr, env, is_tail, output):
    clauses = []
    rest = expr.cdr
    while isinstance(rest, Pair):
        clauses.append(rest.car)
        rest = rest.cdr
    for i, clause in enumerate(clauses):
        if not isinstance(clause, Pair):
            raise SchemeError("malformed cond clause")
        test = clause.car
        body_forms = []
        cr = clause.cdr
        while isinstance(cr, Pair):
            body_forms.append(cr.car)
            cr = cr.cdr
        if isinstance(test, Symbol) and test.name == 'else':
            if i != len(clauses) - 1:
                raise SchemeError("else not last in cond")
            if not body_forms:
                raise SchemeError("malformed cond clause")
            for form in body_forms[:-1]:
                eval_expr(form, env, False, output)
            return eval_expr(body_forms[-1], env, is_tail, output)
        else:
            val = eval_expr(test, env, False, output)
            if truthy(val):
                if not body_forms:
                    return val
                for form in body_forms[:-1]:
                    eval_expr(form, env, False, output)
                return eval_expr(body_forms[-1], env, is_tail, output)
    return UNSPECIFIED

def _handle_and(expr, env, is_tail, output):
    forms = []
    rest = expr.cdr
    while isinstance(rest, Pair):
        forms.append(rest.car)
        rest = rest.cdr
    if not forms:
        return TRUE
    for form in forms[:-1]:
        val = eval_expr(form, env, False, output)
        if not truthy(val):
            return FALSE
    return eval_expr(forms[-1], env, is_tail, output)

def _handle_or(expr, env, is_tail, output):
    forms = []
    rest = expr.cdr
    while isinstance(rest, Pair):
        forms.append(rest.car)
        rest = rest.cdr
    if not forms:
        return FALSE
    for form in forms[:-1]:
        val = eval_expr(form, env, False, output)
        if truthy(val):
            return val
    return eval_expr(forms[-1], env, is_tail, output)

def _handle_lambda(expr, env):
    rest = expr.cdr
    if isinstance(rest, NilType):
        raise SchemeError("malformed lambda")
    formals = rest.car
    body_rest = rest.cdr
    if isinstance(body_rest, NilType):
        raise SchemeError("malformed lambda")
    body = []
    br = body_rest
    while isinstance(br, Pair):
        body.append(br.car)
        br = br.cdr
    if not body:
        raise SchemeError("malformed lambda")
    return Closure(formals, body, env)

def _handle_let(expr, env, is_tail, output):
    rest = expr.cdr
    if isinstance(rest, NilType):
        raise SchemeError("malformed let")
    first = rest.car
    if isinstance(first, Symbol):
        return _handle_named_let(expr, env, is_tail, output)
    bindings = []
    fr = first
    while isinstance(fr, Pair):
        bindings.append(fr.car)
        fr = fr.cdr
    body_forms = []
    br = rest.cdr
    while isinstance(br, Pair):
        body_forms.append(br.car)
        br = br.cdr
    if not body_forms:
        raise SchemeError("malformed let")
    new_bindings = {}
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed let binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed let binding")
        init_rest = b.cdr
        if isinstance(init_rest, NilType):
            raise SchemeError("malformed let binding")
        new_bindings[var.name] = eval_expr(init_rest.car, env, False, output)
    new_env = Frame(new_bindings, env)
    def_names = _scan_defines(body_forms)
    if def_names:
        new_env = Frame({n: UNINITIALIZED for n in def_names}, new_env)
    for form in body_forms[:-1]:
        eval_expr(form, new_env, False, output)
    return eval_expr(body_forms[-1], new_env, is_tail, output)

def _handle_letstar(expr, env, is_tail, output):
    rest = expr.cdr
    if isinstance(rest, NilType):
        raise SchemeError("malformed let*")
    bindings = []
    br = rest.car
    while isinstance(br, Pair):
        bindings.append(br.car)
        br = br.cdr
    body_forms = []
    br2 = rest.cdr
    while isinstance(br2, Pair):
        body_forms.append(br2.car)
        br2 = br2.cdr
    if not body_forms:
        raise SchemeError("malformed let*")
    new_env = Frame({}, env)
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed let* binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed let* binding")
        init_rest = b.cdr
        if isinstance(init_rest, NilType):
            raise SchemeError("malformed let* binding")
        val = eval_expr(init_rest.car, new_env, False, output)
        new_env.define(var.name, val)
    def_names = _scan_defines(body_forms)
    if def_names:
        new_env = Frame({n: UNINITIALIZED for n in def_names}, new_env)
    for form in body_forms[:-1]:
        eval_expr(form, new_env, False, output)
    return eval_expr(body_forms[-1], new_env, is_tail, output)

def _handle_letrec(expr, env, is_tail, output):
    rest = expr.cdr
    if isinstance(rest, NilType):
        raise SchemeError("malformed letrec")
    bindings = []
    br = rest.car
    while isinstance(br, Pair):
        bindings.append(br.car)
        br = br.cdr
    body_forms = []
    br2 = rest.cdr
    while isinstance(br2, Pair):
        body_forms.append(br2.car)
        br2 = br2.cdr
    if not body_forms:
        raise SchemeError("malformed letrec")
    new_bindings = {}
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed letrec binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed letrec binding")
        new_bindings[var.name] = UNINITIALIZED
    new_env = Frame(new_bindings, env)
    for b in bindings:
        var = b.car
        init_rest = b.cdr
        if isinstance(init_rest, NilType):
            raise SchemeError("malformed letrec binding")
        val = eval_expr(init_rest.car, new_env, False, output)
        new_env.define(var.name, val)
    def_names = _scan_defines(body_forms)
    if def_names:
        new_env = Frame({n: UNINITIALIZED for n in def_names}, new_env)
    for form in body_forms[:-1]:
        eval_expr(form, new_env, False, output)
    return eval_expr(body_forms[-1], new_env, is_tail, output)

def _handle_named_let(expr, env, is_tail, output):
    rest = expr.cdr
    name = rest.car
    bindings_node = rest.cdr.car
    body_rest = rest.cdr.cdr
    body_forms = []
    while isinstance(body_rest, Pair):
        body_forms.append(body_rest.car)
        body_rest = body_rest.cdr
    if not body_forms:
        raise SchemeError("malformed let")
    bindings = []
    br = bindings_node
    while isinstance(br, Pair):
        bindings.append(br.car)
        br = br.cdr
    init_vals = []
    var_syms = []
    for b in bindings:
        if not isinstance(b, Pair):
            raise SchemeError("malformed let binding")
        var = b.car
        if not isinstance(var, Symbol):
            raise SchemeError("malformed let binding")
        var_syms.append(var)
        init_rest = b.cdr
        if isinstance(init_rest, NilType):
            raise SchemeError("malformed let binding")
        init_vals.append(eval_expr(init_rest.car, env, False, output))
    formals = py_list_to_scheme(var_syms)
    letrec_frame = Frame({}, env)
    closure = Closure(formals, body_forms, letrec_frame)
    letrec_frame.define(name.name, closure)
    if is_tail:
        return TailCall(closure, init_vals)
    else:
        return call_closure(closure, init_vals, output)

def _handle_apply(expr, env, is_tail, output):
    args_nodes = []
    rest = expr.cdr
    while isinstance(rest, Pair):
        args_nodes.append(rest.car)
        rest = rest.cdr
    if len(args_nodes) < 2:
        raise SchemeError("malformed apply")
    proc = eval_expr(args_nodes[0], env, False, output)
    args = []
    for i in range(1, len(args_nodes) - 1):
        args.append(eval_expr(args_nodes[i], env, False, output))
    lst = eval_expr(args_nodes[-1], env, False, output)
    elements = scheme_list_to_py(lst)
    args.extend(elements)
    if not is_procedure(proc):
        raise SchemeError("apply: not a procedure")
    _check_arity(proc, args)
    if is_tail:
        return TailCall(proc, args)
    else:
        if isinstance(proc, Builtin):
            return proc.func(args)
        else:
            return call_closure(proc, args, output)

def _handle_application(expr, env, is_tail, output):
    proc = eval_expr(expr.car, env, False, output)
    args = []
    rest = expr.cdr
    while isinstance(rest, Pair):
        args.append(eval_expr(rest.car, env, False, output))
        rest = rest.cdr
    if not isinstance(rest, NilType):
        raise SchemeError("dotted form in application")
    if not is_procedure(proc):
        raise SchemeError("not a procedure")
    _check_arity(proc, args)
    if is_tail:
        return TailCall(proc, args)
    else:
        if isinstance(proc, Builtin):
            return proc.func(args)
        else:
            return call_closure(proc, args, output)


def _bind_params(formals, args, env):
    if isinstance(formals, Symbol):
        return Frame({formals.name: py_list_to_scheme(args)}, env)
    if isinstance(formals, NilType):
        if len(args) != 0:
            raise SchemeError("too many arguments")
        return Frame({}, env)
    if isinstance(formals, Pair):
        bindings = {}
        i = 0
        f = formals
        while isinstance(f, Pair):
            param = f.car
            if not isinstance(param, Symbol):
                raise SchemeError("malformed parameter list")
            if i >= len(args):
                raise SchemeError("too few arguments")
            bindings[param.name] = args[i]
            f = f.cdr
            i += 1
        if isinstance(f, Symbol):
            bindings[f.name] = py_list_to_scheme(args[i:])
        elif isinstance(f, NilType):
            if i != len(args):
                raise SchemeError("wrong number of arguments")
        else:
            raise SchemeError("malformed parameter list")
        return Frame(bindings, env)
    raise SchemeError("malformed parameter list")


def _check_arity(proc, args):
    if isinstance(proc, Builtin):
        n = len(args)
        if n < proc.min_args:
            raise SchemeError(f"{proc.name}: too few arguments")
        if proc.max_args is not None and n > proc.max_args:
            raise SchemeError(f"{proc.name}: too many arguments")


def _scan_defines(body):
    names = []
    for form in body:
        if isinstance(form, Pair) and isinstance(form.car, Symbol) and form.car.name == 'define':
            rest = form.cdr
            if not isinstance(rest, NilType):
                target = rest.car
                if isinstance(target, Symbol):
                    names.append(target.name)
                elif isinstance(target, Pair) and isinstance(target.car, Symbol):
                    names.append(target.car.name)
    return names


def call_closure(closure, args, output):
    env = _bind_params(closure.formals, args, closure.env)
    body = closure.body
    def_names = _scan_defines(body)
    if def_names:
        env = Frame({n: UNINITIALIZED for n in def_names}, env)
    return _eval_body(body, env, output)


def _eval_body(body, env, output):
    """Evaluate a body. Last form is in tail position. Uses trampoline."""
    for form in body[:-1]:
        eval_expr(form, env, False, output)
    expr = body[-1]
    while True:
        result = eval_expr(expr, env, True, output)
        if isinstance(result, TailCall):
            proc = result.proc
            args = result.args
            if isinstance(proc, Builtin):
                return proc.func(args)
            elif isinstance(proc, Closure):
                env = _bind_params(proc.formals, args, proc.env)
                body = proc.body
                def_names = _scan_defines(body)
                if def_names:
                    env = Frame({n: UNINITIALIZED for n in def_names}, env)
                for form in body[:-1]:
                    eval_expr(form, env, False, output)
                expr = body[-1]
            else:
                raise SchemeError("not a procedure")
        else:
            return result


# === Builtins ===

def _create_global_env():
    env = Frame({}, None)

    def add(name, func, min_args=0, max_args=None):
        env.define(name, Builtin(name, func, min_args, max_args))

    add('+', _bi_add, 0, None)
    add('*', _bi_mul, 0, None)
    add('-', _bi_sub, 1, None)
    add('quotient', _bi_quotient, 2, 2)
    add('remainder', _bi_remainder, 2, 2)
    add('modulo', _bi_modulo, 2, 2)
    add('=', _bi_eq, 1, None)
    add('<', _bi_lt, 1, None)
    add('>', _bi_gt, 1, None)
    add('<=', _bi_lte, 1, None)
    add('>=', _bi_gte, 1, None)
    add('number->string', _bi_num_str, 1, 2)
    add('cons', _bi_cons, 2, 2)
    add('car', _bi_car, 1, 1)
    add('cdr', _bi_cdr, 1, 1)
    add('list', _bi_list, 0, None)
    add('null?', _bi_null, 1, 1)
    add('pair?', _bi_pair, 1, 1)
    add('list?', _bi_listp, 1, 1)
    add('length', _bi_length, 1, 1)
    add('append', _bi_append, 0, None)
    add('reverse', _bi_reverse, 1, 1)
    add('apply', _bi_apply, 2, None)
    add('eq?', _bi_eqq, 2, 2)
    add('equal?', _bi_equal, 2, 2)
    add('not', _bi_not, 1, 1)
    add('number?', _bi_numberp, 1, 1)
    add('symbol?', _bi_symbolp, 1, 1)
    add('string?', _bi_stringp, 1, 1)
    add('procedure?', _bi_procp, 1, 1)
    add('string-append', _bi_str_append, 0, None)
    add('display', _bi_display, 1, 1)
    add('newline', _bi_newline, 0, 0)
    add('error', _bi_error, 1, None)
    return env


def _check_int(val, op):
    if not isinstance(val, int):
        raise SchemeError(f"{op}: not a number")

def _bi_add(args):
    r = 0
    for a in args:
        _check_int(a, '+')
        r += a
    return r

def _bi_mul(args):
    r = 1
    for a in args:
        _check_int(a, '*')
        r *= a
    return r

def _bi_sub(args):
    _check_int(args[0], '-')
    if len(args) == 1:
        return -args[0]
    r = args[0]
    for a in args[1:]:
        _check_int(a, '-')
        r -= a
    return r

def _bi_quotient(args):
    a, b = args
    _check_int(a, 'quotient')
    _check_int(b, 'quotient')
    if b == 0:
        raise SchemeError("division by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q

def _bi_remainder(args):
    a, b = args
    _check_int(a, 'remainder')
    _check_int(b, 'remainder')
    if b == 0:
        raise SchemeError("division by zero")
    r = abs(a) % abs(b)
    if a < 0:
        r = -r
    return r

def _bi_modulo(args):
    a, b = args
    _check_int(a, 'modulo')
    _check_int(b, 'modulo')
    if b == 0:
        raise SchemeError("division by zero")
    return a % b

def _bi_eq(args):
    for a in args:
        _check_int(a, '=')
    for i in range(len(args) - 1):
        if args[i] != args[i + 1]:
            return FALSE
    return TRUE

def _bi_lt(args):
    for a in args:
        _check_int(a, '<')
    for i in range(len(args) - 1):
        if not (args[i] < args[i + 1]):
            return FALSE
    return TRUE

def _bi_gt(args):
    for a in args:
        _check_int(a, '>')
    for i in range(len(args) - 1):
        if not (args[i] > args[i + 1]):
            return FALSE
    return TRUE

def _bi_lte(args):
    for a in args:
        _check_int(a, '<=')
    for i in range(len(args) - 1):
        if not (args[i] <= args[i + 1]):
            return FALSE
    return TRUE

def _bi_gte(args):
    for a in args:
        _check_int(a, '>=')
    for i in range(len(args) - 1):
        if not (args[i] >= args[i + 1]):
            return FALSE
    return TRUE

def _bi_num_str(args):
    n = args[0]
    _check_int(n, 'number->string')
    radix = 10
    if len(args) == 2:
        radix = args[1]
        _check_int(radix, 'number->string')
        if radix not in (2, 8, 10, 16):
            raise SchemeError("number->string: invalid radix")
    if radix == 10:
        return int_to_str(n)
    return int_to_str_radix(n, radix)

def _bi_cons(args):
    return Pair(args[0], args[1])

def _bi_car(args):
    p = args[0]
    if not isinstance(p, Pair):
        raise SchemeError("car: not a pair")
    return p.car

def _bi_cdr(args):
    p = args[0]
    if not isinstance(p, Pair):
        raise SchemeError("cdr: not a pair")
    return p.cdr

def _bi_list(args):
    return py_list_to_scheme(args)

def _bi_null(args):
    return TRUE if isinstance(args[0], NilType) else FALSE

def _bi_pair(args):
    return TRUE if isinstance(args[0], Pair) else FALSE

def _bi_listp(args):
    return TRUE if is_proper_list(args[0]) else FALSE

def _bi_length(args):
    lst = args[0]
    count = 0
    while isinstance(lst, Pair):
        count += 1
        lst = lst.cdr
    if not isinstance(lst, NilType):
        raise SchemeError("length: not a proper list")
    return count

def _bi_append(args):
    if not args:
        return NIL
    if len(args) == 1:
        return args[0]
    for i in range(len(args) - 1):
        if not is_proper_list(args[i]):
            raise SchemeError("append: not a proper list")
    elements = []
    for i in range(len(args) - 1):
        lst = args[i]
        while isinstance(lst, Pair):
            elements.append(lst.car)
            lst = lst.cdr
    tail = args[-1]
    result = tail
    for elem in reversed(elements):
        result = Pair(elem, result)
    return result

def _bi_reverse(args):
    lst = args[0]
    if not is_proper_list(lst):
        raise SchemeError("reverse: not a proper list")
    result = NIL
    while isinstance(lst, Pair):
        result = Pair(lst.car, result)
        lst = lst.cdr
    return result

def _bi_apply(args):
    proc = args[0]
    individual = args[1:-1]
    lst = args[-1]
    elements = scheme_list_to_py(lst)
    full_args = list(individual) + elements
    if not is_procedure(proc):
        raise SchemeError("apply: not a procedure")
    _check_arity(proc, full_args)
    if isinstance(proc, Builtin):
        return proc.func(full_args)
    else:
        return call_closure(proc, full_args, _current_output)

def _bi_eqq(args):
    a, b = args
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return TRUE if a.name == b.name else FALSE
    if isinstance(a, int) and isinstance(b, int):
        return TRUE if a == b else FALSE
    if a is TRUE and b is TRUE:
        return TRUE
    if a is FALSE and b is FALSE:
        return TRUE
    if isinstance(a, NilType) and isinstance(b, NilType):
        return TRUE
    return TRUE if a is b else FALSE

def _bi_equal(args):
    return TRUE if _scheme_equal(args[0], args[1]) else FALSE

def _scheme_equal(a, b):
    stack = [(a, b)]
    while stack:
        a, b = stack.pop()
        if a is b:
            continue
        if isinstance(a, Pair) and isinstance(b, Pair):
            stack.append((a.car, b.car))
            stack.append((a.cdr, b.cdr))
        elif isinstance(a, str) and isinstance(b, str):
            if a != b:
                return False
        elif isinstance(a, Symbol) and isinstance(b, Symbol):
            if a.name != b.name:
                return False
        elif isinstance(a, int) and isinstance(b, int):
            if a != b:
                return False
        elif a is TRUE and b is TRUE:
            continue
        elif a is FALSE and b is FALSE:
            continue
        elif isinstance(a, NilType) and isinstance(b, NilType):
            continue
        elif isinstance(a, UnspecifiedType) and isinstance(b, UnspecifiedType):
            continue
        else:
            return False
    return True

def _bi_not(args):
    return TRUE if args[0] is FALSE else FALSE

def _bi_numberp(args):
    return TRUE if isinstance(args[0], int) else FALSE

def _bi_symbolp(args):
    return TRUE if isinstance(args[0], Symbol) else FALSE

def _bi_stringp(args):
    return TRUE if isinstance(args[0], str) else FALSE

def _bi_procp(args):
    return TRUE if isinstance(args[0], (Closure, Builtin)) else FALSE

def _bi_str_append(args):
    parts = []
    for s in args:
        if not isinstance(s, str):
            raise SchemeError("string-append: not a string")
        parts.append(s)
    return ''.join(parts)

def _bi_display(args):
    display_repr(args[0], _current_output, write_mode=False)
    return UNSPECIFIED

def _bi_newline(args):
    _current_output.append('\n')
    return UNSPECIFIED

def _bi_error(args):
    msg = args[0]
    if isinstance(msg, str):
        parts = [msg]
        for irr in args[1:]:
            parts.append(' ')
            parts.append(write_repr(irr))
        raise SchemeError(''.join(parts))
    else:
        raise SchemeError(str(msg))


# === Main Entry Point ===

def run(source):
    global _current_output
    _current_output = []
    output = _current_output

    try:
        tokens = tokenize(source)
        forms = parse_all(tokens)
    except SchemeError:
        raise
    except Exception as e:
        raise SchemeError(str(e)) from None

    try:
        global_env = _create_global_env()
        for form in forms:
            eval_expr(form, global_env, False, output)
        return ''.join(output)
    except SchemeError as e:
        e.output = ''.join(output)
        raise
    except RecursionError:
        raise SchemeError("recursion limit exceeded") from None
    except Exception as e:
        raise SchemeError(str(e)) from None
