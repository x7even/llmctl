import sys
import re

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)
sys.setrecursionlimit(1000000)

class SchemeError(Exception):
    def __init__(self, message='', output=''):
        super().__init__(message)
        self.output = output

class Symbol:
    __slots__ = ('name',)
    def __init__(self, name): self.name = name

class Pair:
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr): self.car = car; self.cdr = cdr

class _Nil: pass
NIL = _Nil()

class _Unspecified: pass
UNSPEC = _Unspecified()

class _Unbound: pass
UNBOUND = _Unbound()

class Closure:
    __slots__ = ('params','body','env','vararg')
    def __init__(self, params, body, env, vararg):
        self.params=params; self.body=body; self.env=env; self.vararg=vararg

class Builtin:
    __slots__ = ('func','name','min_args','max_args')
    def __init__(self, func, name, min_args, max_args):
        self.func=func; self.name=name; self.min_args=min_args; self.max_args=max_args

class Frame:
    __slots__ = ('vars',)
    def __init__(self): self.vars = {}

# ─── Reader ───────────────────────────────────────────────────────────────────

class ReadError(Exception): pass

_INT_RE = re.compile(r'[+-]?[0-9]+')

class Reader:
    def __init__(self, source): self.src = source; self.pos = 0

    def read_all(self):
        forms = []
        while True:
            self._skip()
            if self.pos >= len(self.src): break
            forms.append(self._datum())
        return forms

    def _skip(self):
        while self.pos < len(self.src):
            c = self.src[self.pos]
            if c in ' \t\n\r': self.pos += 1
            elif c == ';':
                while self.pos < len(self.src) and self.src[self.pos] != '\n': self.pos += 1
            else: break

    def _datum(self):
        self._skip()
        if self.pos >= len(self.src): raise ReadError("unexpected EOF")
        c = self.src[self.pos]
        if c == '(': self.pos += 1; return self._list()
        if c == ')': raise ReadError("unexpected )")
        if c == "'":
            self.pos += 1
            d = self._datum()
            return Pair(Symbol('quote'), Pair(d, NIL))
        if c == '"': return self._string()
        return self._token()

    def _list(self):
        items = []
        while True:
            self._skip()
            if self.pos >= len(self.src): raise ReadError("unbalanced (")
            if self.src[self.pos] == ')': self.pos += 1; break
            d = self._datum()
            if isinstance(d, Symbol) and d.name == '.':
                if not items: raise ReadError("dot without preceding element")
                tail = self._datum()
                self._skip()
                if self.pos >= len(self.src) or self.src[self.pos] != ')':
                    raise ReadError("expected ) after dotted pair")
                self.pos += 1
                r = tail
                for it in reversed(items): r = Pair(it, r)
                return r
            items.append(d)
        r = NIL
        for it in reversed(items): r = Pair(it, r)
        return r

    def _string(self):
        self.pos += 1
        chars = []
        while True:
            if self.pos >= len(self.src): raise ReadError("unterminated string")
            c = self.src[self.pos]
            if c == '"': self.pos += 1; return ''.join(chars)
            if c == '\\':
                self.pos += 1
                if self.pos >= len(self.src): raise ReadError("unterminated string")
                e = self.src[self.pos]
                if e == '"': chars.append('"')
                elif e == '\\': chars.append('\\')
                elif e == 'n': chars.append('\n')
                else: raise ReadError("invalid escape")
                self.pos += 1
            else:
                chars.append(c); self.pos += 1

    def _token(self):
        start = self.pos
        while self.pos < len(self.src):
            if self.src[self.pos] in ' \t\n\r()";\'': break
            self.pos += 1
        if self.pos == start: raise ReadError("expected token")
        tok = self.src[start:self.pos]
        if tok == '#t': return True
        if tok == '#f': return False
        if tok.startswith('#'): raise ReadError("invalid # literal")
        if _INT_RE.fullmatch(tok): return int(tok)
        return Symbol(tok)

# ─── Utilities ────────────────────────────────────────────────────────────────

_output = []

def truthy(x): return x is not False

def is_proper_list(x):
    while isinstance(x, Pair): x = x.cdr
    return x is NIL

def list_to_python(x):
    r = []
    while isinstance(x, Pair): r.append(x.car); x = x.cdr
    return r

def python_to_list(items):
    r = NIL
    for it in reversed(items): r = Pair(it, r)
    return r

def lookup(sym, env):
    for frame in env:
        if sym.name in frame.vars:
            v = frame.vars[sym.name]
            if isinstance(v, _Unbound): raise SchemeError(f"unbound variable: {sym.name}")
            return v
    raise SchemeError(f"unbound variable: {sym.name}")

def set_var(sym, val, env):
    for frame in env:
        if sym.name in frame.vars:
            frame.vars[sym.name] = val; return
    raise SchemeError(f"set!: unbound variable: {sym.name}")

def display_repr(x):
    if x is True: return '#t'
    if x is False: return '#f'
    if isinstance(x, int): return str(x)
    if isinstance(x, str): return x
    if isinstance(x, Symbol): return x.name
    if x is NIL: return '()'
    if isinstance(x, _Unspecified): return ''
    if isinstance(x, Pair): return _disp_pair(x)
    if isinstance(x, (Closure, Builtin)): return '#<procedure>'
    return str(x)

def _disp_pair(p):
    parts = []; cur = p
    while isinstance(cur, Pair): parts.append(display_repr(cur.car)); cur = cur.cdr
    if cur is NIL: return '(' + ' '.join(parts) + ')'
    return '(' + ' '.join(parts) + ' . ' + display_repr(cur) + ')'

def write_repr(x):
    if isinstance(x, str):
        return '"' + x.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n') + '"'
    if isinstance(x, Pair): return _write_pair(x)
    return display_repr(x)

def _write_pair(p):
    parts = []; cur = p
    while isinstance(cur, Pair): parts.append(write_repr(cur.car)); cur = cur.cdr
    if cur is NIL: return '(' + ' '.join(parts) + ')'
    return '(' + ' '.join(parts) + ' . ' + write_repr(cur) + ')'

# ─── Builtins ─────────────────────────────────────────────────────────────────

def _ci(x, name):
    if isinstance(x, bool) or not isinstance(x, int): raise SchemeError(f"{name}: expected integer")
    return x

def _td(a, b):
    q = abs(a) // abs(b)
    return -q if (a < 0) ^ (b < 0) else q

def bi_add(args):
    r = 0
    for a in args: r += _ci(a, '+')
    return r

def bi_sub(args):
    if len(args) == 1: return -_ci(args[0], '-')
    r = _ci(args[0], '-')
    for a in args[1:]: r -= _ci(a, '-')
    return r

def bi_mul(args):
    r = 1
    for a in args: r *= _ci(a, '*')
    return r

def bi_quotient(args):
    a=_ci(args[0],'quotient'); b=_ci(args[1],'quotient')
    if b==0: raise SchemeError("division by zero")
    return _td(a,b)

def bi_remainder(args):
    a=_ci(args[0],'remainder'); b=_ci(args[1],'remainder')
    if b==0: raise SchemeError("division by zero")
    return a - _td(a,b)*b

def bi_modulo(args):
    a=_ci(args[0],'modulo'); b=_ci(args[1],'modulo')
    if b==0: raise SchemeError("division by zero")
    return a % b

def bi_eq(args):
    for a in args: _ci(a,'=')
    for i in range(len(args)-1):
        if args[i]!=args[i+1]: return False
    return True

def bi_lt(args):
    for a in args: _ci(a,'<')
    for i in range(len(args)-1):
        if args[i]>=args[i+1]: return False
    return True

def bi_gt(args):
    for a in args: _ci(a,'>')
    for i in range(len(args)-1):
        if args[i]<=args[i+1]: return False
    return True

def bi_lte(args):
    for a in args: _ci(a,'<=')
    for i in range(len(args)-1):
        if args[i]>args[i+1]: return False
    return True

def bi_gte(args):
    for a in args: _ci(a,'>=')
    for i in range(len(args)-1):
        if args[i]<args[i+1]: return False
    return True

def bi_num2str(args):
    n=_ci(args[0],'number->string'); radix=10
    if len(args)==2:
        radix=_ci(args[1],'number->string')
        if radix not in (2,8,10,16): raise SchemeError("invalid radix")
    if radix==10: return str(n)
    neg=n<0; n=abs(n)
    if radix==2: s=bin(n)[2:]
    elif radix==8: s=oct(n)[2:]
    else: s=hex(n)[2:]
    return ('-'+s) if neg else s

def bi_cons(args): return Pair(args[0], args[1])

def bi_car(args):
    if not isinstance(args[0], Pair): raise SchemeError("car: not a pair")
    return args[0].car

def bi_cdr(args):
    if not isinstance(args[0], Pair): raise SchemeError("cdr: not a pair")
    return args[0].cdr

def bi_list(args): return python_to_list(args)

def bi_null(args): return args[0] is NIL

def bi_pair(args): return isinstance(args[0], Pair)

def bi_listp(args): return is_proper_list(args[0])

def bi_length(args):
    n=0; cur=args[0]
    while isinstance(cur, Pair): n+=1; cur=cur.cdr
    if cur is not NIL: raise SchemeError("length: not a proper list")
    return n

def bi_append(args):
    if not args: return NIL
    for a in args[:-1]:
        if not is_proper_list(a): raise SchemeError("append: not a proper list")
    elems=[]
    for a in args[:-1]:
        cur=a
        while isinstance(cur, Pair): elems.append(cur.car); cur=cur.cdr
    r=args[-1]
    for e in reversed(elems): r=Pair(e,r)
    return r

def bi_reverse(args):
    if not is_proper_list(args[0]): raise SchemeError("reverse: not a proper list")
    return python_to_list(reversed(list_to_python(args[0])))

_BUILTIN_APPLY = None

def bi_apply(args):
    func=args[0]; rest=args[1:-1]; last=args[-1]
    if not is_proper_list(last): raise SchemeError("apply: last arg must be a proper list")
    return _call_proc(func, rest + list_to_python(last))

def _call_proc(func, args):
    if isinstance(func, Closure):
        if func.vararg is None:
            if len(args)!=len(func.params): raise SchemeError("wrong number of arguments")
            fr=Frame()
            for p,a in zip(func.params,args): fr.vars[p.name]=a
        else:
            if len(args)<len(func.params): raise SchemeError("wrong number of arguments")
            fr=Frame()
            for p,a in zip(func.params,args): fr.vars[p.name]=a
            fr.vars[func.vararg.name]=python_to_list(args[len(func.params):])
        return _eval_body_full(func.body, [fr]+func.env)
    elif isinstance(func, Builtin):
        _chk_arity(func, args)
        return func.func(args)
    raise SchemeError("not a procedure")

def _chk_arity(b, args):
    if b.min_args is not None and len(args)<b.min_args: raise SchemeError(f"{b.name}: too few arguments")
    if b.max_args is not None and len(args)>b.max_args: raise SchemeError(f"{b.name}: too many arguments")

def bi_eqq(args):
    a,b=args[0],args[1]
    if isinstance(a,bool) or isinstance(b,bool): return a is b
    if isinstance(a,int) and isinstance(b,int): return a==b
    if isinstance(a,Symbol) and isinstance(b,Symbol): return a.name==b.name
    if a is NIL and b is NIL: return True
    return a is b

def bi_equal(args): return _scheme_equal(args[0], args[1])

def _scheme_equal(a,b):
    stack=[(a,b)]
    while stack:
        a,b=stack.pop()
        if a is b: continue
        if isinstance(a,bool) or isinstance(b,bool): return False
        if isinstance(a,int) and isinstance(b,int):
            if a!=b: return False
            continue
        if isinstance(a,str) and isinstance(b,str):
            if a!=b: return False
            continue
        if isinstance(a,Symbol) and isinstance(b,Symbol):
            if a.name!=b.name: return False
            continue
        if a is NIL and b is NIL: continue
        if isinstance(a,Pair) and isinstance(b,Pair):
            stack.append((a.cdr,b.cdr)); stack.append((a.car,b.car)); continue
        return False
    return True

def bi_not(args): return args[0] is False

def bi_numberp(args): return isinstance(args[0],int) and not isinstance(args[0],bool)

def bi_symbolp(args): return isinstance(args[0],Symbol)

def bi_stringp(args): return isinstance(args[0],str)

def bi_procedurep(args): return isinstance(args[0],(Closure,Builtin))

def bi_string_append(args):
    for s in args:
        if not isinstance(s,str): raise SchemeError("string-append: expected string")
    return ''.join(args)

def bi_display(args):
    _output.append(display_repr(args[0])); return UNSPEC

def bi_newline(args):
    _output.append('\n'); return UNSPEC

def bi_error(args):
    if not args: raise SchemeError("error: at least one argument required")
    msg=args[0]
    if not isinstance(msg,str): raise SchemeError(str(msg))
    parts=[msg]
    for irr in args[1:]:
        parts.append(' '); parts.append(write_repr(irr))
    raise SchemeError(''.join(parts))

def make_global_env():
    global _BUILTIN_APPLY
    f=Frame()
    f.vars['+']=Builtin(bi_add,'+',0,None)
    f.vars['-']=Builtin(bi_sub,'-',1,None)
    f.vars['*']=Builtin(bi_mul,'*',0,None)
    f.vars['quotient']=Builtin(bi_quotient,'quotient',2,2)
    f.vars['remainder']=Builtin(bi_remainder,'remainder',2,2)
    f.vars['modulo']=Builtin(bi_modulo,'modulo',2,2)
    f.vars['=']=Builtin(bi_eq,'=',1,None)
    f.vars['<']=Builtin(bi_lt,'<',1,None)
    f.vars['>']=Builtin(bi_gt,'>',1,None)
    f.vars['<=']=Builtin(bi_lte,'<=',1,None)
    f.vars['>=']=Builtin(bi_gte,'>=',1,None)
    f.vars['number->string']=Builtin(bi_num2str,'number->string',1,2)
    f.vars['cons']=Builtin(bi_cons,'cons',2,2)
    f.vars['car']=Builtin(bi_car,'car',1,1)
    f.vars['cdr']=Builtin(bi_cdr,'cdr',1,1)
    f.vars['list']=Builtin(bi_list,'list',0,None)
    f.vars['null?']=Builtin(bi_null,'null?',1,1)
    f.vars['pair?']=Builtin(bi_pair,'pair?',1,1)
    f.vars['list?']=Builtin(bi_listp,'list?',1,1)
    f.vars['length']=Builtin(bi_length,'length',1,1)
    f.vars['append']=Builtin(bi_append,'append',0,None)
    f.vars['reverse']=Builtin(bi_reverse,'reverse',1,1)
    ab=Builtin(bi_apply,'apply',2,None); _BUILTIN_APPLY=ab; f.vars['apply']=ab
    f.vars['eq?']=Builtin(bi_eqq,'eq?',2,2)
    f.vars['equal?']=Builtin(bi_equal,'equal?',2,2)
    f.vars['not']=Builtin(bi_not,'not',1,1)
    f.vars['number?']=Builtin(bi_numberp,'number?',1,1)
    f.vars['symbol?']=Builtin(bi_symbolp,'symbol?',1,1)
    f.vars['string?']=Builtin(bi_stringp,'string?',1,1)
    f.vars['procedure?']=Builtin(bi_procedurep,'procedure?',1,1)
    f.vars['string-append']=Builtin(bi_string_append,'string-append',0,None)
    f.vars['display']=Builtin(bi_display,'display',1,1)
    f.vars['newline']=Builtin(bi_newline,'newline',0,0)
    f.vars['error']=Builtin(bi_error,'error',1,None)
    return [f]

# ─── Evaluator ────────────────────────────────────────────────────────────────

def _is_define(form):
    return isinstance(form,Pair) and isinstance(form.car,Symbol) and form.car.name=='define'

def _define_name(form):
    t=form.cdr.car
    if isinstance(t,Symbol): return t.name
    if isinstance(t,Pair): return t.car.name
    raise SchemeError("malformed define")

def _setup_id(body, env):
    names=[_define_name(f) for f in body if _is_define(f)]
    if not names: return env
    fr=Frame()
    for n in names: fr.vars[n]=UNBOUND
    return [fr]+env

def _eval_define(form, env):
    target=form.cdr.car; rest=form.cdr.cdr
    if isinstance(target,Symbol):
        if not isinstance(rest,Pair) or rest.cdr is not NIL: raise SchemeError("malformed define")
        env[0].vars[target.name]=eval_expr(rest.car, env, False)
    elif isinstance(target,Pair):
        fn=target.car
        if not isinstance(fn,Symbol): raise SchemeError("malformed define")
        bl=list_to_python(rest) if is_proper_list(rest) else None
        if bl is None or not bl: raise SchemeError("malformed define")
        params,va=_parse_formals(target.cdr)
        env[0].vars[fn.name]=Closure(params,bl,env,va)
    else: raise SchemeError("malformed define")

def _parse_formals(formals):
    if isinstance(formals,Symbol): return [],formals
    if formals is NIL: return [],None
    if isinstance(formals,Pair):
        params=[]; cur=formals
        while isinstance(cur,Pair):
            if not isinstance(cur.car,Symbol): raise SchemeError("malformed formals")
            params.append(cur.car); cur=cur.cdr
        if cur is NIL: return params,None
        if isinstance(cur,Symbol): return params,cur
        raise SchemeError("malformed formals")
    raise SchemeError("malformed formals")

def _eval_body_full(body, env):
    ne=_setup_id(body, env)
    for form in body[:-1]:
        if _is_define(form): _eval_define(form, ne)
        else: eval_expr(form, ne, False)
    last=body[-1]
    if _is_define(last): _eval_define(last, ne); return UNSPEC
    return eval_expr(last, ne, False)

def _bind_call(closure, args):
    if closure.vararg is None:
        if len(args)!=len(closure.params): raise SchemeError("wrong number of arguments")
        fr=Frame()
        for p,a in zip(closure.params,args): fr.vars[p.name]=a
    else:
        if len(args)<len(closure.params): raise SchemeError("wrong number of arguments")
        fr=Frame()
        for p,a in zip(closure.params,args): fr.vars[p.name]=a
        fr.vars[closure.vararg.name]=python_to_list(args[len(closure.params):])
    return [fr]+closure.env

def _tail_setup(body, env):
    """Prepare body for tail evaluation. Returns (expr, env) or (None, result)."""
    ne=_setup_id(body, env)
    for form in body[:-1]:
        if _is_define(form): _eval_define(form, ne)
        else: eval_expr(form, ne, False)
    last=body[-1]
    if _is_define(last): _eval_define(last, ne); return None, UNSPEC
    return last, ne

def eval_expr(expr, env, tail=False):
    while True:
        if isinstance(expr,bool): return expr
        if isinstance(expr,int): return expr
        if isinstance(expr,str): return expr
        if isinstance(expr,Symbol): return lookup(expr,env)
        if expr is NIL: raise SchemeError("cannot evaluate ()")
        if isinstance(expr,_Unspecified): return expr
        if not isinstance(expr,Pair): raise SchemeError("cannot evaluate")

        head=expr.car
        if isinstance(head,Symbol):
            nm=head.name

            if nm=='quote':
                if not isinstance(expr.cdr,Pair) or expr.cdr.cdr is not NIL:
                    raise SchemeError("malformed quote")
                return expr.cdr.car

            if nm=='if':
                if not isinstance(expr.cdr,Pair): raise SchemeError("malformed if")
                test=expr.cdr.car; rest1=expr.cdr.cdr
                if not isinstance(rest1,Pair): raise SchemeError("malformed if")
                then_e=rest1.car; rest2=rest1.cdr
                if rest2 is NIL: has_else=False; else_e=None
                elif isinstance(rest2,Pair) and rest2.cdr is NIL: has_else=True; else_e=rest2.car
                else: raise SchemeError("malformed if")
                tv=eval_expr(test,env,False)
                if truthy(tv): expr=then_e; continue
                elif has_else: expr=else_e; continue
                else: return UNSPEC

            if nm=='lambda':
                if not isinstance(expr.cdr,Pair): raise SchemeError("malformed lambda")
                formals=expr.cdr.car; body_r=expr.cdr.cdr
                bl=list_to_python(body_r) if is_proper_list(body_r) else None
                if bl is None or not bl: raise SchemeError("malformed lambda")
                params,va=_parse_formals(formals)
                return Closure(params,bl,env,va)

            if nm=='define':
                _eval_define(expr,env); return UNSPEC

            if nm=='set!':
                if not isinstance(expr.cdr,Pair) or not isinstance(expr.cdr.car,Symbol):
                    raise SchemeError("malformed set!")
                r=expr.cdr.cdr
                if not isinstance(r,Pair) or r.cdr is not NIL: raise SchemeError("malformed set!")
                set_var(expr.cdr.car, eval_expr(r.car,env,False), env); return UNSPEC

            if nm=='begin':
                forms=list_to_python(expr.cdr) if is_proper_list(expr.cdr) else None
                if forms is None or not forms: raise SchemeError("malformed begin")
                for f in forms[:-1]: eval_expr(f,env,False)
                expr=forms[-1]; continue

            if nm=='cond':
                clauses=list_to_python(expr.cdr) if is_proper_list(expr.cdr) else None
                if clauses is None: raise SchemeError("malformed cond")
                res=None
                for i,cl in enumerate(clauses):
                    if not isinstance(cl,Pair): raise SchemeError("malformed cond")
                    test=cl.car; exprs=list_to_python(cl.cdr) if is_proper_list(cl.cdr) else None
                    if exprs is None: raise SchemeError("malformed cond")
                    if isinstance(test,Symbol) and test.name=='else':
                        if i!=len(clauses)-1: raise SchemeError("else not last")
                        if not exprs: return UNSPEC
                        for e in exprs[:-1]: eval_expr(e,env,False)
                        res=exprs[-1]; break
                    tv=eval_expr(test,env,False)
                    if truthy(tv):
                        if not exprs: return tv
                        for e in exprs[:-1]: eval_expr(e,env,False)
                        res=exprs[-1]; break
                if res is None: return UNSPEC
                expr=res; continue

            if nm=='and':
                exprs=list_to_python(expr.cdr) if is_proper_list(expr.cdr) else None
                if exprs is None: raise SchemeError("malformed and")
                if not exprs: return True
                for e in exprs[:-1]:
                    if not truthy(eval_expr(e,env,False)): return False
                expr=exprs[-1]; continue

            if nm=='or':
                exprs=list_to_python(expr.cdr) if is_proper_list(expr.cdr) else None
                if exprs is None: raise SchemeError("malformed or")
                if not exprs: return False
                for e in exprs[:-1]:
                    v=eval_expr(e,env,False)
                    if truthy(v): return v
                expr=exprs[-1]; continue

            if nm=='let':
                if not isinstance(expr.cdr,Pair): raise SchemeError("malformed let")
                first=expr.cdr.car
                if isinstance(first,Symbol):
                    # Named let
                    lname=first
                    if not isinstance(expr.cdr.cdr,Pair): raise SchemeError("malformed named let")
                    bindings=expr.cdr.cdr.car; body_r=expr.cdr.cdr.cdr
                    bl=list_to_python(body_r) if is_proper_list(body_r) else None
                    if bl is None or not bl: raise SchemeError("malformed named let")
                    bnd=list_to_python(bindings) if (bindings is NIL or is_proper_list(bindings)) else None
                    if bnd is None: raise SchemeError("malformed named let bindings")
                    params=[]; inits=[]
                    for b in bnd:
                        if not isinstance(b,Pair) or not isinstance(b.car,Symbol) or \
                           not isinstance(b.cdr,Pair) or b.cdr.cdr is not NIL:
                            raise SchemeError("malformed binding")
                        params.append(b.car); inits.append(eval_expr(b.cdr.car,env,False))
                    fr=Frame(); fr.vars[lname.name]=UNBOUND
                    ne=[fr]+env
                    fr.vars[lname.name]=Closure(params,bl,ne,None)
                    cf=Frame()
                    for p,v in zip(params,inits): cf.vars[p.name]=v
                    ne=[cf]+ne
                    r=_tail_setup(bl,ne)
                    if r[0] is None: return r[1]
                    expr,env=r; continue
                else:
                    # Regular let
                    bindings=first; body_r=expr.cdr.cdr
                    bl=list_to_python(body_r) if is_proper_list(body_r) else None
                    if bl is None or not bl: raise SchemeError("malformed let")
                    bnd=list_to_python(bindings) if (bindings is NIL or is_proper_list(bindings)) else None
                    if bnd is None: raise SchemeError("malformed let bindings")
                    fr=Frame()
                    for b in bnd:
                        if not isinstance(b,Pair) or not isinstance(b.car,Symbol) or \
                           not isinstance(b.cdr,Pair) or b.cdr.cdr is not NIL:
                            raise SchemeError("malformed let binding")
                        fr.vars[b.car.name]=eval_expr(b.cdr.car,env,False)
                    ne=[fr]+env
                    r=_tail_setup(bl,ne)
                    if r[0] is None: return r[1]
                    expr,env=r; continue

            if nm=='let*':
                if not isinstance(expr.cdr,Pair): raise SchemeError("malformed let*")
                bindings=expr.cdr.car; body_r=expr.cdr.cdr
                bl=list_to_python(body_r) if is_proper_list(body_r) else None
                if bl is None or not bl: raise SchemeError("malformed let*")
                bnd=list_to_python(bindings) if (bindings is NIL or is_proper_list(bindings)) else None
                if bnd is None: raise SchemeError("malformed let* bindings")
                ne=env
                for b in bnd:
                    if not isinstance(b,Pair) or not isinstance(b.car,Symbol) or \
                       not isinstance(b.cdr,Pair) or b.cdr.cdr is not NIL:
                        raise SchemeError("malformed let* binding")
                    fr=Frame(); fr.vars[b.car.name]=eval_expr(b.cdr.car,ne,False)
                    ne=[fr]+ne
                r=_tail_setup(bl,ne)
                if r[0] is None: return r[1]
                expr,env=r; continue

            if nm=='letrec':
                if not isinstance(expr.cdr,Pair): raise SchemeError("malformed letrec")
                bindings=expr.cdr.car; body_r=expr.cdr.cdr
                bl=list_to_python(body_r) if is_proper_list(body_r) else None
                if bl is None or not bl: raise SchemeError("malformed letrec")
                bnd=list_to_python(bindings) if (bindings is NIL or is_proper_list(bindings)) else None
                if bnd is None: raise SchemeError("malformed letrec bindings")
                fr=Frame()
                for b in bnd:
                    if not isinstance(b,Pair) or not isinstance(b.car,Symbol) or \
                       not isinstance(b.cdr,Pair) or b.cdr.cdr is not NIL:
                        raise SchemeError("malformed letrec binding")
                    fr.vars[b.car.name]=UNBOUND
                ne=[fr]+env
                for b in bnd:
                    fr.vars[b.car.name]=eval_expr(b.cdr.car,ne,False)
                r=_tail_setup(bl,ne)
                if r[0] is None: return r[1]
                expr,env=r; continue

        # ── Application ──
        func=eval_expr(expr.car,env,False)
        args=[]; cur=expr.cdr
        while isinstance(cur,Pair):
            args.append(eval_expr(cur.car,env,False)); cur=cur.cdr
        if cur is not NIL: raise SchemeError("dotted form in application")

        # apply in tail position
        if func is _BUILTIN_APPLY and tail:
            if len(args)<2: raise SchemeError("apply: at least 2 arguments")
            target=args[0]; rest=args[1:-1]; last=args[-1]
            if not is_proper_list(last): raise SchemeError("apply: last arg must be proper list")
            func=target; args=rest+list_to_python(last)

        if isinstance(func,Closure):
            ne=_bind_call(func,args)
            if tail:
                r=_tail_setup(func.body,ne)
                if r[0] is None: return r[1]
                expr,env=r; continue
            else:
                return _eval_body_full(func.body,ne)
        elif isinstance(func,Builtin):
            _chk_arity(func,args)
            return func.func(args)
        else:
            raise SchemeError("not a procedure")

# ─── Public API ───────────────────────────────────────────────────────────────

def run(source):
    global _output
    _output = []
    try:
        forms = Reader(source).read_all()
    except ReadError as e:
        raise SchemeError(str(e), '')
    except Exception as e:
        raise SchemeError(str(e), '')
    try:
        env = make_global_env()
        for form in forms:
            eval_expr(form, env, False)
    except SchemeError as e:
        if not e.output:
            e.output = ''.join(_output)
        raise
    except RecursionError:
        raise SchemeError("stack overflow", ''.join(_output))
    except Exception as e:
        raise SchemeError(str(e), ''.join(_output))
    return ''.join(_output)
