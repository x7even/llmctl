"""Reference solution for mini_scheme: trampolined AST-walking interpreter.

Tail calls are handled by the loop in `ev`; non-tail recursion uses Python recursion
(run in a thread with a large stack and a raised recursion limit).
"""
import re
import sys
import threading


class SchemeError(Exception):
    def __init__(self, message="", output=""):
        super().__init__(message)
        self.output = output


# ---------------------------------------------------------------- data types

class Sym:
    __slots__ = ("name",)
    table = {}

    def __init__(self, name):
        self.name = name


def intern(name):
    s = Sym.table.get(name)
    if s is None:
        s = Sym.table[name] = Sym(name)
    return s


class Pair:
    __slots__ = ("car", "cdr")

    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr


class _Singleton:
    def __init__(self, name):
        self.name = name


NIL = _Singleton("()")
UNSPEC = _Singleton("unspecified")
UNASSIGNED = _Singleton("unassigned")


class Closure:
    __slots__ = ("params", "rest", "body", "env")

    def __init__(self, params, rest, body, env):
        self.params = params
        self.rest = rest
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ("name", "fn", "lo", "hi")

    def __init__(self, name, fn, lo, hi):
        self.name = name
        self.fn = fn
        self.lo = lo
        self.hi = hi  # None = unbounded


class Env:
    __slots__ = ("vars", "parent")

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent


def err(msg):
    raise SchemeError(msg)


# -------------------------------------------------------------------- reader

_INT = re.compile(r"[+-]?[0-9]+")
_DELIMS = set(" \t\n\r()\";'")
_WS = set(" \t\n\r")
_QUOTE = intern("quote")
_DOT = object()


def tokenize(src):
    toks = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in _WS:
            i += 1
        elif c == ";":
            while i < n and src[i] != "\n":
                i += 1
        elif c in "()'":
            toks.append(c)
            i += 1
        elif c == '"':
            i += 1
            buf = []
            while True:
                if i >= n:
                    err("unterminated string")
                ch = src[i]
                if ch == '"':
                    i += 1
                    break
                if ch == "\\":
                    if i + 1 >= n:
                        err("unterminated string")
                    e = src[i + 1]
                    if e == '"':
                        buf.append('"')
                    elif e == "\\":
                        buf.append("\\")
                    elif e == "n":
                        buf.append("\n")
                    else:
                        err("bad string escape")
                    i += 2
                else:
                    buf.append(ch)
                    i += 1
            toks.append(("str", "".join(buf)))
        else:
            j = i
            while j < n and src[j] not in _DELIMS:
                j += 1
            word = src[i:j]
            i = j
            if _INT.fullmatch(word):
                toks.append(("atom", int(word)))
            elif word == "#t":
                toks.append(("atom", True))
            elif word == "#f":
                toks.append(("atom", False))
            elif word.startswith("#"):
                err("bad # syntax")
            elif word == ".":
                toks.append(("atom", _DOT))
            else:
                toks.append(("atom", intern(word)))
    return toks


def read_all(src):
    toks = tokenize(src)
    forms = []
    # explicit stack of open lists: each frame = [items, dot_seen, tail_set, tail, quote_depth]
    stack = []
    quotes = []  # per frame (and for top level at index 0) count of pending quotes

    pending = [0]  # pending quote count for current context

    def emit(datum):
        # wrap pending quotes
        for _ in range(pending[-1]):
            datum = Pair(_QUOTE, Pair(datum, NIL))
        pending[-1] = 0
        if not stack:
            forms.append(datum)
            return
        fr = stack[-1]
        if fr["dot"] == 1:
            fr["tail"] = datum
            fr["dot"] = 2
        elif fr["dot"] == 2:
            err("bad dotted list")
        else:
            fr["items"].append(datum)

    for t in toks:
        if t == "'":
            pending[-1] += 1
        elif t == "(":
            stack.append({"items": [], "dot": 0, "tail": NIL, "q": pending[-1]})
            pending[-1] = 0
            pending.append(0)
        elif t == ")":
            if not stack:
                err("unexpected )")
            if pending[-1]:
                err("quote without datum")
            fr = stack.pop()
            pending.pop()
            if fr["dot"] == 1:
                err("bad dotted list")
            lst = fr["tail"]
            for item in reversed(fr["items"]):
                lst = Pair(item, lst)
            pending[-1] = fr["q"]
            emit(lst)
        else:
            kind, val = t
            if val is _DOT and kind == "atom":
                if not stack or not stack[-1]["items"] or stack[-1]["dot"] or pending[-1]:
                    err("bad dot")
                stack[-1]["dot"] = 1
            else:
                emit(val)
    if stack:
        err("missing )")
    if pending[0]:
        err("quote without datum")
    return forms


# ------------------------------------------------------------------- helpers

def to_pylist(p, what="list"):
    out = []
    while type(p) is Pair:
        out.append(p.car)
        p = p.cdr
    if p is not NIL:
        err(f"improper {what}")
    return out


def from_pylist(items, tail=NIL):
    r = tail
    for x in reversed(items):
        r = Pair(x, r)
    return r


def is_proper(p):
    while type(p) is Pair:
        p = p.cdr
    return p is NIL


def _write_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def to_text(x, write=False):
    out = []

    def go(x):
        t = type(x)
        if t is bool:
            out.append("#t" if x else "#f")
        elif t is int:
            out.append(str(x))
        elif t is str:
            out.append(_write_str(x) if write else x)
        elif t is Sym:
            out.append(x.name)
        elif x is NIL:
            out.append("()")
        elif x is UNSPEC:
            pass
        elif t is Pair:
            out.append("(")
            first = True
            while type(x) is Pair:
                if not first:
                    out.append(" ")
                first = False
                go(x.car)
                x = x.cdr
            if x is not NIL:
                out.append(" . ")
                go(x)
            out.append(")")
        else:
            out.append("#<procedure>")

    go(x)
    return "".join(out)


def is_equal(a, b):
    while True:
        ta, tb = type(a), type(b)
        if ta is not tb:
            return False
        if ta is Pair:
            if not is_equal(a.car, b.car):
                return False
            a, b = a.cdr, b.cdr
            continue
        if ta is int or ta is str or ta is bool:
            return a == b
        return a is b


def is_eq(a, b):
    ta = type(a)
    if ta is not type(b):
        return False
    if ta is int or ta is bool:
        return a == b
    return a is b


# ---------------------------------------------------------------- evaluator

S = intern
K_QUOTE, K_IF, K_DEFINE, K_SET, K_LAMBDA, K_BEGIN, K_COND, K_AND, K_OR, K_LET, K_LETSTAR, K_LETREC = range(12)
SPECIAL = {
    S("quote"): K_QUOTE, S("if"): K_IF, S("define"): K_DEFINE, S("set!"): K_SET,
    S("lambda"): K_LAMBDA, S("begin"): K_BEGIN, S("cond"): K_COND, S("and"): K_AND,
    S("or"): K_OR, S("let"): K_LET, S("let*"): K_LETSTAR, S("letrec"): K_LETREC,
}
SYM_ELSE = S("else")
SYM_DEFINE = S("define")


def make_closure(formals, body, env):
    params = []
    rest = None
    while type(formals) is Pair:
        if type(formals.car) is not Sym:
            err("bad formals")
        params.append(formals.car)
        formals = formals.cdr
    if formals is not NIL:
        if type(formals) is not Sym:
            err("bad formals")
        rest = formals
    if type(body) is not Pair:
        err("empty body")
    return Closure(tuple(params), rest, body, env)


_body_cache = {}


def body_info(body):
    """Return (forms list, names of internal defines) for a body (Pair chain)."""
    info = _body_cache.get(body)
    if info is None:
        forms = to_pylist(body, "body")
        names = []
        for f in forms:
            if type(f) is Pair and f.car is SYM_DEFINE:
                t = f.cdr
                if type(t) is not Pair:
                    err("bad define")
                target = t.car
                if type(target) is Pair:
                    target = target.car
                if type(target) is not Sym:
                    err("bad define")
                names.append(target)
        info = _body_cache[body] = (forms, tuple(names))
    return info


def lookup(sym, env):
    e = env
    while e is not None:
        v = e.vars
        if sym in v:
            r = v[sym]
            if r is UNASSIGNED:
                err(f"variable used before definition: {sym.name}")
            return r
        e = e.parent
    err(f"unbound variable: {sym.name}")


def plist(x, lo, hi=None):
    items = to_pylist(x.cdr, "form")
    if len(items) < lo or (hi is not None and len(items) > hi):
        err("malformed special form")
    return items


def ev(x, env):
    while True:
        t = type(x)
        if t is Sym:
            return lookup(x, env)
        if t is not Pair:
            if x is NIL:
                err("missing procedure expression")
            return x
        head = x.car
        k = SPECIAL.get(head) if type(head) is Sym else None
        if k is None:
            f = ev(head, env)
            args = []
            p = x.cdr
            while type(p) is Pair:
                args.append(ev(p.car, env))
                p = p.cdr
            if p is not NIL:
                err("improper application")
        elif k == K_QUOTE:
            return plist(x, 1, 1)[0]
        elif k == K_IF:
            parts = plist(x, 2, 3)
            if ev(parts[0], env) is not False:
                x = parts[1]
                continue
            if len(parts) == 3:
                x = parts[2]
                continue
            return UNSPEC
        elif k == K_DEFINE:
            parts = plist(x, 1)
            target = parts[0]
            if type(target) is Pair:
                name = target.car
                if type(name) is not Sym or len(parts) < 2:
                    err("bad define")
                val = make_closure(target.cdr, x.cdr.cdr, env)
            else:
                if type(target) is not Sym or len(parts) != 2:
                    err("bad define")
                name = target
                val = ev(parts[1], env)
            env.vars[name] = val
            return UNSPEC
        elif k == K_SET:
            parts = plist(x, 2, 2)
            name = parts[0]
            if type(name) is not Sym:
                err("bad set!")
            val = ev(parts[1], env)
            e = env
            while e is not None:
                if name in e.vars:
                    e.vars[name] = val
                    break
                e = e.parent
            else:
                err(f"set! of unbound variable: {name.name}")
            return UNSPEC
        elif k == K_LAMBDA:
            parts = plist(x, 2)
            return make_closure(parts[0], x.cdr.cdr, env)
        elif k == K_BEGIN:
            parts = plist(x, 1)
            for f in parts[:-1]:
                ev(f, env)
            x = parts[-1]
            continue
        elif k == K_COND:
            clauses = plist(x, 0)
            chosen = None
            for i, c in enumerate(clauses):
                cl = to_pylist(c, "clause")
                if not cl:
                    err("bad cond clause")
                if cl[0] is SYM_ELSE:
                    if i != len(clauses) - 1 or len(cl) < 2:
                        err("bad else clause")
                    chosen = cl[1:]
                    break
                v = ev(cl[0], env)
                if v is not False:
                    if len(cl) == 1:
                        return v
                    chosen = cl[1:]
                    break
            if chosen is None:
                return UNSPEC
            for f in chosen[:-1]:
                ev(f, env)
            x = chosen[-1]
            continue
        elif k == K_AND:
            parts = plist(x, 0)
            if not parts:
                return True
            for f in parts[:-1]:
                if ev(f, env) is False:
                    return False
            x = parts[-1]
            continue
        elif k == K_OR:
            parts = plist(x, 0)
            if not parts:
                return False
            for f in parts[:-1]:
                v = ev(f, env)
                if v is not False:
                    return v
            x = parts[-1]
            continue
        else:  # let family
            parts = plist(x, 2)
            named = None
            if k == K_LET and type(parts[0]) is Sym:
                named = parts[0]
                parts = parts[1:]
                if len(parts) < 2:
                    err("malformed named let")
            bindings = to_pylist(parts[0], "bindings")
            names, inits = [], []
            for b in bindings:
                bl = to_pylist(b, "binding")
                if len(bl) != 2 or type(bl[0]) is not Sym:
                    err("bad binding")
                names.append(bl[0])
                inits.append(bl[1])
            body = x.cdr.cdr if named is None else x.cdr.cdr.cdr
            if type(body) is not Pair:
                err("empty body")
            if named is not None:
                args = [ev(i, env) for i in inits]
                env1 = Env(env)
                f = Closure(tuple(names), None, body, env1)
                env1.vars[named] = f
            else:
                if k == K_LET:
                    vals = [ev(i, env) for i in inits]
                    new = Env(env)
                    for n_, v_ in zip(names, vals):
                        new.vars[n_] = v_
                elif k == K_LETSTAR:
                    new = env
                    for n_, i_ in zip(names, inits):
                        v_ = ev(i_, new)
                        new = Env(new)
                        new.vars[n_] = v_
                    new = Env(new)
                else:  # letrec
                    new = Env(env)
                    for n_ in names:
                        new.vars[n_] = UNASSIGNED
                    for n_, i_ in zip(names, inits):
                        new.vars[n_] = ev(i_, new)
                forms, defs = body_info(body)
                for d in defs:
                    new.vars[d] = UNASSIGNED
                for f_ in forms[:-1]:
                    ev(f_, new)
                x = forms[-1]
                env = new
                continue
        # ---- application of f to args (tail position)
        while True:
            if type(f) is Closure:
                n = len(f.params)
                if f.rest is None:
                    if len(args) != n:
                        err("wrong number of arguments")
                else:
                    if len(args) < n:
                        err("wrong number of arguments")
                new = Env(f.env)
                v = new.vars
                for i in range(n):
                    v[f.params[i]] = args[i]
                if f.rest is not None:
                    v[f.rest] = from_pylist(args[n:])
                forms, defs = body_info(f.body)
                for d in defs:
                    v[d] = UNASSIGNED
                for f_ in forms[:-1]:
                    ev(f_, new)
                x = forms[-1]
                env = new
                break
            if type(f) is Builtin:
                if len(args) < f.lo or (f.hi is not None and len(args) > f.hi):
                    err(f"wrong number of arguments to {f.name}")
                if f.name == "apply" and f.fn is _APPLY_MARK:
                    g = args[0]
                    last = to_pylist(args[-1], "argument list")
                    f, args = g, args[1:-1] + last
                    continue
                return f.fn(*args)
            err("not a procedure")


_APPLY_MARK = object()


# ----------------------------------------------------------------- builtins

def build_global(out):
    g = Env()

    def reg(name, lo, hi, fn):
        g.vars[intern(name)] = Builtin(name, fn, lo, hi)

    def num(x):
        if type(x) is not int:
            err("expected integer")
        return x

    def b_add(*a):
        r = 0
        for x in a:
            r += num(x)
        return r

    def b_mul(*a):
        r = 1
        for x in a:
            r *= num(x)
        return r

    def b_sub(*a):
        for x in a:
            num(x)
        if len(a) == 1:
            return -a[0]
        r = a[0]
        for x in a[1:]:
            r -= x
        return r

    def divcheck(a, b):
        num(a)
        num(b)
        if b == 0:
            err("division by zero")

    def quot(a, b):
        divcheck(a, b)
        q = abs(a) // abs(b)
        return q if (a < 0) == (b < 0) else -q

    def rem(a, b):
        divcheck(a, b)
        return a - b * quot(a, b)

    def mod(a, b):
        divcheck(a, b)
        return a % b

    def cmp(op):
        def f(*a):
            for x in a:
                num(x)
            for i in range(len(a) - 1):
                if not op(a[i], a[i + 1]):
                    return False
            return True
        return f

    import operator
    reg("+", 0, None, b_add)
    reg("*", 0, None, b_mul)
    reg("-", 1, None, b_sub)
    reg("quotient", 2, 2, quot)
    reg("remainder", 2, 2, rem)
    reg("modulo", 2, 2, mod)
    reg("=", 1, None, cmp(operator.eq))
    reg("<", 1, None, cmp(operator.lt))
    reg(">", 1, None, cmp(operator.gt))
    reg("<=", 1, None, cmp(operator.le))
    reg(">=", 1, None, cmp(operator.ge))

    def car(p):
        if type(p) is not Pair:
            err("car of non-pair")
        return p.car

    def cdr(p):
        if type(p) is not Pair:
            err("cdr of non-pair")
        return p.cdr

    def length(l):
        n = 0
        while type(l) is Pair:
            n += 1
            l = l.cdr
        if l is not NIL:
            err("length of improper list")
        return n

    def append(*a):
        if not a:
            return NIL
        res = a[-1]
        for l in reversed(a[:-1]):
            res = from_pylist(to_pylist(l), res)
        return res

    def reverse(l):
        r = NIL
        while type(l) is Pair:
            r = Pair(l.car, r)
            l = l.cdr
        if l is not NIL:
            err("reverse of improper list")
        return r

    reg("cons", 2, 2, Pair)
    reg("car", 1, 1, car)
    reg("cdr", 1, 1, cdr)
    reg("list", 0, None, lambda *a: from_pylist(list(a)))
    reg("null?", 1, 1, lambda x: x is NIL)
    reg("pair?", 1, 1, lambda x: type(x) is Pair)
    reg("list?", 1, 1, is_proper)
    reg("length", 1, 1, length)
    reg("append", 0, None, append)
    reg("reverse", 1, 1, reverse)
    reg("eq?", 2, 2, is_eq)
    reg("equal?", 2, 2, is_equal)
    reg("not", 1, 1, lambda x: x is False)
    reg("number?", 1, 1, lambda x: type(x) is int)
    reg("symbol?", 1, 1, lambda x: type(x) is Sym)
    reg("string?", 1, 1, lambda x: type(x) is str)
    reg("procedure?", 1, 1, lambda x: type(x) is Closure or type(x) is Builtin)

    def string_append(*a):
        for s in a:
            if type(s) is not str:
                err("string-append: expected string")
        return "".join(a)

    reg("string-append", 0, None, string_append)

    def n2s(n, radix=10):
        num(n)
        if type(radix) is not int or radix not in (2, 8, 10, 16):
            err("bad radix")
        if radix == 10:
            return str(n)
        digits = format(abs(n), {2: "b", 8: "o", 16: "x"}[radix])
        return ("-" if n < 0 else "") + digits

    reg("number->string", 1, 2, n2s)

    def display(x):
        out.append(to_text(x))
        return UNSPEC

    def newline():
        out.append("\n")
        return UNSPEC

    reg("display", 1, 1, display)
    reg("newline", 0, 0, newline)
    reg("apply", 2, None, _APPLY_MARK)

    def error(msg, *irritants):
        if type(msg) is not str:
            err("error: message must be a string")
        raise SchemeError(" ".join([msg] + [to_text(i, True) for i in irritants]))

    reg("error", 1, None, error)
    return g


def _run(source, out):
    forms = read_all(source)
    g = build_global(out)
    for f in forms:
        ev(f, g)


def run(source):
    out = []
    result = {}

    def target():
        try:
            _run(source, out)
        except SchemeError as e:
            e.output = "".join(out)
            result["exc"] = e
        except RecursionError:
            e = SchemeError("recursion too deep")
            e.output = "".join(out)
            result["exc"] = e
        except BaseException as e:  # pragma: no cover
            result["other"] = e

    old_rec = sys.getrecursionlimit()
    old_digits = sys.get_int_max_str_digits()
    old_stack = threading.stack_size()
    sys.setrecursionlimit(max(old_rec, 400000))
    sys.set_int_max_str_digits(0)
    threading.stack_size(256 * 1024 * 1024)
    try:
        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join()
    finally:
        threading.stack_size(old_stack)
        sys.set_int_max_str_digits(old_digits)
        sys.setrecursionlimit(old_rec)
    if "other" in result:
        raise result["other"]
    if "exc" in result:
        raise result["exc"]
    return "".join(out)
