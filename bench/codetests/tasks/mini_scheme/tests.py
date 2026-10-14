"""Hidden tests for mini_scheme. Each test takes the loaded solution module `m`.

Oracles (nothing here is computed by reference.py):
  * hand-derived expected output strings;
  * Python's own arithmetic / math.factorial / sorted / itertools for classic programs;
  * a small independent closure-based evaluator for randomly generated int/bool
    expression trees (see _Gen), an independent text formatter for random quoted data
    (see _show), and Python `sorted` etc. for randomly generated list programs.
"""
import contextlib
import io
import itertools
import math
import random
import sys


# ------------------------------------------------------------------ helpers

def _digits(n):
    old = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        return str(n)
    finally:
        sys.set_int_max_str_digits(old)


def _check(m, src, want):
    got = m.run(src)
    assert got == want, f"{src!r}: got {got!r}, want {want!r}"


def _disp(m, expr, want):
    _check(m, "(display " + expr + ")", want)


def _fails(m, src, out=None, msg=None):
    """Assert that run(src) raises SchemeError (and nothing else); optionally check .output / str()."""
    try:
        m.run(src)
    except m.SchemeError as e:
        assert isinstance(e.output, str), f"{src!r}: .output is {type(e.output).__name__}"
        if out is not None:
            assert e.output == out, f"{src!r}: .output {e.output!r}, want {out!r}"
        if msg is not None:
            assert str(e) == msg, f"{src!r}: str(e) {str(e)!r}, want {msg!r}"
        return e
    except BaseException as e:
        raise AssertionError(f"{src!r}: raised {type(e).__name__}: {str(e)[:100]} instead of SchemeError")
    raise AssertionError(f"{src!r}: did not raise SchemeError")


# --------------------------------------------------------- 1. reader / printer

def test_lexical_syntax_and_display(m):
    assert issubclass(m.SchemeError, Exception)
    for src in ["", "   \n\t ", "; just a comment", "; c1\n; c2\n", "\r\n"]:
        _check(m, src, "")
    # integers: signs, leading zeros; numeric-looking tokens that are NOT integers are symbols
    _disp(m, "(list 42 -7 +5 007 -0)", "(42 -7 5 7 0)")
    _disp(m, "'(- + 1+ -x 1_000 .5 1.5 ... a.b)", "(- + 1+ -x 1_000 .5 1.5 ... a.b)")
    _disp(m, "(list (number? '+5) (number? '1_000) (symbol? '1_000) (symbol? '.5) (symbol? '-))", "(#t #f #t #t #t)")
    _check(m, "(define 1_0 7) (display 1_0)", "7")
    _disp(m, "'([a b])", "([a b])")           # brackets are ordinary symbol characters
    _disp(m, "(eq? 'Foo 'foo)", "#f")
    # strings and escapes
    _disp(m, r'"a\"b\\c\nd"', 'a"b\\c\nd')
    _disp(m, r'"a\\n"', "a\\n")
    _disp(m, '"x;y (z)"', "x;y (z)")
    _disp(m, '"line1\nline2"', "line1\nline2")
    _disp(m, '""', "")
    # comments, adjacency, delimiters
    _check(m, '(display 1) ; (display 2) "unterminated\n(display 3)', "13")
    _check(m, "(display 1)(display 2)", "12")
    _check(m, '(display"a")(display\'b)', "ab")
    _check(m, "(display 1)\r\n(display 2)\r\n", "12")
    _check(m, "(display (quote x))(display '(quote))", "x(quote)")
    # booleans and printing
    _check(m, "(display #t)(display #f)", "#t#f")
    _disp(m, "'()", "()")
    _disp(m, "'(1 2 3)", "(1 2 3)")
    _disp(m, "'(1 . 2)", "(1 . 2)")
    _disp(m, "'(1 2 . 3)", "(1 2 . 3)")
    _disp(m, "'(1 . (2 3))", "(1 2 3)")
    _disp(m, "'(1 . (2 . (3 . ())))", "(1 2 3)")
    _disp(m, "'(1 (2 3) () . 4)", "(1 (2 3) () . 4)")
    _disp(m, "'((((1))))", "((((1))))")
    _disp(m, "''a", "(quote a)")
    _disp(m, "'(1 'b)", "(1 (quote b))")
    _disp(m, "'(a . 'b)", "(a quote b)")
    _disp(m, "'''x", "(quote (quote x))")
    _disp(m, '\'("a" b "c d")', "(a b c d)")
    _disp(m, "(cons 1 (cons 2 (cons 3 4)))", "(1 2 3 . 4)")
    _disp(m, "(cons '(1) '(2))", "((1) 2)")
    _disp(m, "(cons 1 2)", "(1 . 2)")
    _disp(m, "car", "#<procedure>")
    _disp(m, "(lambda (x) x)", "#<procedure>")
    _disp(m, "(list car (lambda () 1))", "(#<procedure> #<procedure>)")
    _disp(m, "(if #f #f)", "")
    _disp(m, "(list 1 (if #f #f) 2)", "(1  2)")
    _check(m, '(display "a")(newline)(display "b")(newline)', "a\nb\n")
    _syntax_errors(m)
    # top-level values are never printed
    _check(m, '(define x 1) x 5 "s" (+ 1 2) (list 1) (display "ok")', "ok")
    # self-evaluating literals and quote of atoms
    _disp(m, "(list '5 '#t '\"s\" 'sym)", "(5 #t s sym)")


def _syntax_errors(m):
    bad = [
        "(display 1) (display 2",          # missing )
        "(display 1))",                    # extra )
        "(display 1) )",
        '(display 1) (display "abc',       # unterminated string
        '(display 1) (display "a\\qb")',   # unknown escape
        '(display 1) (display "a\\',       # backslash at end of input
        "(display 1) #x",                  # bad # token
        "(display 1) (display #true)",
        "(display 1) (display #T)",
        "(display 1) '",                   # quote without datum
        "(display (list '))",
        "(display 1) ( . 1)",              # misplaced dots
        "(display 1) (1 . )",
        "(display 1) (1 . 2 3)",
        "(display 1) (1 .)",
        "(display 1) .",
        "(display 1) (1 . . 2)",
        "(",
        ")",
        '"',
    ]
    for src in bad:
        _fails(m, src, out="")
    # the same program shape without the syntax error prints everything
    _check(m, "(display 1) (display 2)", "12")
    # a runtime error, by contrast, keeps the earlier output
    _fails(m, "(display 1) (car '()) (display 2)", out="1")
    # tokens that merely look odd are fine
    _disp(m, "'(a.b . c.d)", "(a.b . c.d)")
    _disp(m, "'(1 .5)", "(1 .5)")


# ------------------------------------------------------------------ 2. integers

def _trunc_quot(a, b):
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def test_integer_arithmetic(m):
    _disp(m, "(list (+) (*) (+ 5) (* 5) (- 5) (+ 1 2 3 4) (* 2 3 4) (- 10 1 2 3) (- 0 7))", "(0 1 5 5 -5 10 24 4 -7)")
    _disp(m, "(- -5)", "5")
    _disp(m, "(list (< 1 2 3) (< 1 2 2) (<= 1 2 2) (> 3 2 1) (> 3 3 1) (>= 3 3 1) (>= 3 3 4) (= 2 2 2) (= 2 2 3) (= 5) (< 3) (> 3) (<= 3) (>= 3))",
          "(#t #f #t #t #f #t #f #t #f #t #t #t #t #t)")
    _disp(m, "(list (< -5 -4) (> -5 -4) (= 0 -0) (< 100000000000000000000 100000000000000000001))", "(#t #f #t #t)")
    # quotient / remainder / modulo against an independent oracle, all sign combinations
    vals = list(range(-9, 10))
    divs = [d for d in range(-5, 6) if d != 0]
    exprs, want = [], []
    for a in vals:
        for d in divs:
            q = _trunc_quot(a, d)
            exprs.append(f"(list (quotient {a} {d}) (remainder {a} {d}) (modulo {a} {d}))")
            want.append(f"({q} {a - d * q} {a % d})")
    _disp(m, "(list " + " ".join(exprs) + ")", "(" + " ".join(want) + ")")
    _disp(m, "(list (quotient -7 2) (remainder -7 2) (modulo -7 2) (quotient 7 -2) (remainder 7 -2) (modulo 7 -2))",
          "(-3 -1 1 -3 1 -1)")
    # exactness for big integers (no float intermediates)
    big = 10 ** 30 + 7
    for a, d in [(big, 3), (-big, 3), (big, -(10 ** 15 + 3)), (-big, -(10 ** 15 + 3)), (10 ** 40, 10 ** 20 - 1),
                 (2 ** 100 + 1, -(2 ** 50)), (-(2 ** 100) - 1, 2 ** 50 + 1)]:
        q = _trunc_quot(a, d)
        _disp(m, f"(list (quotient {a} {d}) (remainder {a} {d}) (modulo {a} {d}))", f"({q} {a - d * q} {a % d})")
    _disp(m, "(* 99999999999 99999999999)", str(99999999999 ** 2))
    _disp(m, "(+ 9223372036854775807 1)", str(2 ** 63))
    _disp(m, "(- -9223372036854775808 1)", str(-(2 ** 63) - 1))
    # full printing of huge integers (CPython limits int->str to 4300 digits by default)
    prog = "(define (fact n) (if (= n 0) 1 (* n (fact (- n 1))))) (display (fact 2000)) (newline) (display (number->string (fact 1800)))"
    _check(m, prog, _digits(math.factorial(2000)) + "\n" + _digits(math.factorial(1800)))
    _check(m, "(display (* 1" + "0" * 4500 + " 1" + "0" * 20 + "))", "1" + "0" * 4520)
    # number->string
    _disp(m, '(list (number->string 0) (number->string -42) (number->string 255 16) (number->string -255 16) '
             '(number->string 5 2) (number->string 64 8) (number->string 77 10) (number->string 0 2) (number->string -5 2))',
          "(0 -42 ff -ff 101 100 77 0 -101)")
    _disp(m, '(string-append "n=" (number->string 12) "/" (number->string 4095 16))', "n=12/fff")
    for src in ["(number->string 5 3)", "(number->string 5 1)", "(number->string 5 36)", "(number->string 5 0)",
                "(number->string \"a\")", "(number->string #t)", "(number->string 'a)", "(number->string)",
                "(number->string 1 2 3)", "(number->string 5 #t)"]:
        _fails(m, src)
    # type and arity errors
    for src in ["(+ 1 \"a\")", "(+ 1 #t)", "(+ #f)", "(- 'a)", "(* 2 '())", "(< 1 'a)", "(= 1 \"1\")", "(< 3 2 'a)",
                "(> #t 1)", "(modulo 5 #f)", "(quotient \"a\" 1)", "(remainder 1 'x)", "(-)", "(=)", "(<)", "(>=)",
                "(quotient 1)", "(quotient 1 2 3)", "(remainder 1)", "(modulo)", "(modulo 1 2 3)",
                "(quotient 1 0)", "(remainder 1 0)", "(modulo 1 0)", "(quotient 0 0)", "(modulo 5 (- 3 3))"]:
        _fails(m, src)
    # builtins are first-class
    _disp(m, "(let ((add +) (ops (list + - *))) (list (add 1 2) (apply (car ops) '(5 3)) (apply (car (cdr (cdr ops))) '(5 3))))", "(3 8 15)")


# --------------------------------------------- 3. truthiness, equality, predicates

def test_truthiness_equality_and_predicates(m):
    # only #f is false
    cases = [
        ("(if 0 'y 'n)", "y"), ("(if '() 'y 'n)", "y"), ("(if \"\" 'y 'n)", "y"), ("(if #f 'y 'n)", "n"),
        ("(if (if #f #f) 'y 'n)", "y"), ("(if 'sym 'y 'n)", "y"), ("(if car 'y 'n)", "y"), ("(if #t 'y 'n)", "y"),
        ("(if (not 0) 'y 'n)", "n"), ("(not '())", "#f"), ("(not #f)", "#t"), ("(not \"\")", "#f"),
        ("(not (not 5))", "#t"), ("(not (null? '(1)))", "#t"),
        ("(and 1 2 3)", "3"), ("(and 1 #f 3)", "#f"), ("(and)", "#t"), ("(and 0)", "0"), ("(and 0 '() \"\")", ""),
        ("(and '() 1)", "1"), ("(or)", "#f"), ("(or #f #f)", "#f"), ("(or #f 0)", "0"), ("(or '() 5)", "()"),
        ("(or #f #f 'c 'd)", "c"), ("(or 7)", "7"), ("(and #t #t)", "#t"),
        ("(cond (#f 1) (else 2))", "2"), ("(cond (0 'zero) (else 'no))", "zero"), ("(cond ('() 'nil))", "nil"),
        ("(cond (5))", "5"), ("(cond (#f) (7))", "7"), ("(cond (#f 1))", ""), ("(cond (#f 1) (#f 2))", ""),
        ("(cond (#t 1 2 3))", "3"), ("(cond ((= 1 2) 'a) ((= 1 1) 'b) (else 'c))", "b"),
        ("(if #t 1)", "1"), ("(if #f 1)", ""),
    ]
    for expr, want in cases:
        _disp(m, expr, want)
    _check(m, "(display (cond ((begin (display \"t\") #f) (display \"x\")) ((begin (display \"u\") 3) (display \"y\") 9) (else (display \"z\"))))",
           "tuy9")
    # booleans and integers are different types
    for expr, want in [("(number? #t)", "#f"), ("(number? #f)", "#f"), ("(number? 5)", "#t"), ("(number? \"5\")", "#f"),
                       ("(number? 'a)", "#f"), ("(number? '5)", "#t"), ("(number? '())", "#f"),
                       ("(symbol? 'a)", "#t"), ("(symbol? \"a\")", "#f"), ("(symbol? '())", "#f"), ("(symbol? #t)", "#f"),
                       ("(symbol? (car '(a)))", "#t"), ("(symbol? 5)", "#f"),
                       ("(string? \"a\")", "#t"), ("(string? 'a)", "#f"), ("(string? 5)", "#f"), ("(string? (string-append))", "#t"),
                       ("(procedure? car)", "#t"), ("(procedure? (lambda () 1))", "#t"), ("(procedure? 'car)", "#f"),
                       ("(procedure? (car (list car)))", "#t"), ("(procedure? 5)", "#f"), ("(procedure? '())", "#f"),
                       ("(list? '())", "#t"), ("(list? '(1))", "#t"), ("(list? '(1 . 2))", "#f"), ("(list? 5)", "#f"),
                       ("(list? (cons 1 (cons 2 3)))", "#f"), ("(list? (cons 1 (cons 2 '())))", "#t"), ("(list? \"\")", "#f"),
                       ("(pair? '())", "#f"), ("(pair? '(1))", "#t"), ("(pair? '(1 . 2))", "#t"), ("(pair? \"a\")", "#f"),
                       ("(null? '())", "#t"), ("(null? #f)", "#f"), ("(null? 0)", "#f"), ("(null? \"\")", "#f"),
                       ("(null? (cdr '(1)))", "#t"), ("(null? '(()))", "#f")]:
        _disp(m, expr, want)
    # eq?
    for expr, want in [("(eq? 'a 'a)", "#t"), ("(eq? 'a 'b)", "#f"), ("(eq? 5 5)", "#t"), ("(eq? 5 6)", "#f"),
                       ("(eq? 100000000000000000000 100000000000000000000)", "#t"),
                       ("(eq? (* 100000 100000) (+ 9999999999 1))", "#t"),
                       ("(eq? '() '())", "#t"), ("(eq? #t #t)", "#t"), ("(eq? #f #f)", "#t"), ("(eq? #t #f)", "#f"),
                       ("(eq? 1 #t)", "#f"), ("(eq? 0 #f)", "#f"), ("(eq? '() #f)", "#f"), ("(eq? '() 0)", "#f"),
                       ("(eq? (list 1) (list 1))", "#f"), ("(eq? (cons 1 2) (cons 1 2))", "#f"),
                       ("(let ((p (list 1))) (eq? p p))", "#t"), ("(eq? \"abc\" (string-append \"ab\" \"c\"))", "#f"),
                       ("(let ((s (string-append \"ab\" \"c\"))) (eq? s s))", "#t"),
                       ("(eq? car car)", "#t"), ("(eq? car cdr)", "#f"), ("(eq? (lambda () 1) (lambda () 1))", "#f"),
                       ("(let ((f (lambda () 1))) (eq? f f))", "#t"), ("(eq? 'a \"a\")", "#f"), ("(eq? 5 '5)", "#t"),
                       ("(eq? (car '(x y)) 'x)", "#t")]:
        _disp(m, expr, want)
    # equal?
    for expr, want in [("(equal? 1 1)", "#t"), ("(equal? 1 2)", "#f"), ("(equal? 1 #t)", "#f"), ("(equal? 0 #f)", "#f"),
                       ("(equal? #t #t)", "#t"), ("(equal? #f #f)", "#t"), ("(equal? #t #f)", "#f"),
                       ("(equal? \"a\" \"a\")", "#t"), ("(equal? \"a\" \"b\")", "#f"), ("(equal? \"\" \"\")", "#t"),
                       ("(equal? 'a \"a\")", "#f"), ("(equal? \"a\" 'a)", "#f"), ("(equal? 'a 'a)", "#t"),
                       ("(equal? '(1 2 (3)) '(1 2 (3)))", "#t"), ("(equal? '(1 2) '(1 3))", "#f"), ("(equal? '(1 2) '(1 2 3))", "#f"),
                       ("(equal? '(1 . 2) '(1 . 2))", "#t"), ("(equal? '(1 . 2) '(1 2))", "#f"), ("(equal? '() '())", "#t"),
                       ("(equal? '() #f)", "#f"), ("(equal? '() '(()))", "#f"), ("(equal? '(1 #t) '(1 1))", "#f"),
                       ("(equal? '(1 #f) (list 1 #f))", "#t"), ("(equal? '(\"a\" b) (list \"a\" 'b))", "#t"),
                       ("(equal? '(\"a\" b) (list 'a 'b))", "#f"), ("(equal? car car)", "#t"), ("(equal? car cdr)", "#f"),
                       ("(equal? (lambda () 1) (lambda () 1))", "#f"),
                       ("(equal? 100000000000000000000 (* 10000000000 10000000000))", "#t"),
                       ("(equal? 12345678901234567890 12345678901234567891)", "#f"),
                       ("(equal? '(1 (2 (3 \"x\"))) (list 1 (list 2 (list 3 \"x\"))))", "#t"),
                       ("(equal? '(1 (2 (3 \"x\"))) (list 1 (list 2 (list 3 \"y\"))))", "#f"),
                       ("(equal? (cons 1 (cons 2 '())) '(1 2))", "#t"), ("(equal? 5 '5)", "#t")]:
        _disp(m, expr, want)
    # booleans are not numbers in arithmetic either
    _fails(m, "(display \"a\") (+ 1 #t)", out="a")
    _fails(m, "(display \"a\") (< #f #t)", out="a")


# ------------------------------------------------------------ 4. lists, apply

def test_lists_apply_and_shadowing(m):
    for expr, want in [
        ("(list)", "()"), ("(list 1 2 3)", "(1 2 3)"), ("(list '(1) \"s\" 'a)", "((1) s a)"),
        ("(car (cons 1 2))", "1"), ("(cdr (cons 1 2))", "2"), ("(cdr '(1))", "()"), ("(car (cdr '(1 2 3)))", "2"),
        ("(cons 1 '(2))", "(1 2)"), ("(cons 1 '())", "(1)"), ("(car '((a) b))", "(a)"), ("(cdr '(1 . 2))", "2"),
        ("(length '())", "0"), ("(length '(1 2 3))", "3"), ("(length '((1 2) (3)))", "2"), ("(length (list '() '()))", "2"),
        ("(reverse '())", "()"), ("(reverse '(1 (2 3) 4))", "(4 (2 3) 1)"), ("(reverse '(1))", "(1)"),
        ("(append)", "()"), ("(append '(1 2))", "(1 2)"), ("(append '(1) '(2 3) '() '(4))", "(1 2 3 4)"),
        ("(append '(1) 2)", "(1 . 2)"), ("(append '() 5)", "5"), ("(append '() '())", "()"), ("(append '(1) '(2 . 3))", "(1 2 . 3)"),
        ("(append '((1)) '((2)))", "((1) (2))"), ("(append 5)", "5"),
        ("(let ((t (list 3))) (eq? t (cdr (cdr (append '(1 2) t)))))", "#t"),
        ("(let ((l (list 1 2))) (eq? l (append l)))", "#t"),
        ("(let ((l (list 1 2))) (eq? l (append '() l)))", "#t"),
        ("(apply + '(1 2 3))", "6"), ("(apply + 1 2 '(3 4))", "10"), ("(apply + '())", "0"), ("(apply list 1 '(2))", "(1 2)"),
        ("(apply (lambda (a . r) r) 1 2 '(3))", "(2 3)"), ("(apply apply (list + (list 1 2)))", "3"), ("(apply car '((1 2)))", "1"),
        ("(apply (lambda args args) '())", "()"), ("(apply list '())", "()"), ("(apply - 10 '(1 2))", "7"),
        ("(apply string-append (list \"a\" \"b\"))", "ab"), ("(apply append '((1) (2) (3)))", "(1 2 3)"),
    ]:
        _disp(m, expr, want)
    for src in ["(car '())", "(cdr '())", "(car 5)", "(cdr \"s\")", "(car #f)", "(cdr (cdr '(1)))", "(car)", "(car '(1) '(2))",
                "(cons 1)", "(cons 1 2 3)", "(length '(1 . 2))", "(length 5)", "(length)", "(length '(1) '(2))",
                "(reverse '(1 . 2))", "(reverse 5)", "(append '(1 . 2) '(3))", "(append 1 '(2))", "(append '(1) 2 '(3))",
                "(apply + 1)", "(apply + 1 2)", "(apply +)", "(apply 5 '())", "(apply + '(1 . 2))", "(string-append \"a\" 1)",
                "(string-append 'a)", "(list? )", "(null?)", "(pair? 1 2)", "(not)", "(not 1 2)", "(eq? 1)", "(equal? 1 2 3)"]:
        _fails(m, src)
    # strings
    _disp(m, '(list (string-append) (string-append "a") (string-append "a" "bc" "" "d"))', "( a abcd)")
    # shadowing builtins with local bindings
    _check(m, "(define (f list) (car list)) (display (f '(9 8)))", "9")
    _check(m, "(display (let ((length 3)) (+ length 1)))", "4")
    _check(m, "(display ((lambda (append) (append 1)) (lambda (x) (* x 10))))", "10")
    _check(m, "(define (g car) (car 5)) (display (g (lambda (x) (* x x))))", "25")
    # user redefinitions of builtins take effect but do not change other builtins
    prog = """
    (define (length l) (if (null? l) 0 (+ 1 (length (cdr l)))))
    (define (append a b) (if (null? a) b (cons (car a) (append (cdr a) b))))
    (define (reverse l) (if (null? l) '() (append (reverse (cdr l)) (list (car l)))))
    (display (list (length '(1 2 3)) (append '(1) '(2)) (reverse '(1 2 3))))
    (display (apply + 1 '(2 3)))
    (display (list? '(1 2)))
    (display (equal? '(1 2) (list 1 2)))
    (display (apply list '(4 5)))
    (define car cdr)
    (display (car '(1 2)))
    (display (cdr '(1 2)))
    """
    _check(m, prog, "(3 (1 2) (3 2 1))6#t#t(4 5)(2)(2)")
    # each run starts with pristine builtins
    _check(m, "(display (car '(1 2)))", "1")


# --------------------------------------------------- 5. closures and mutation

def test_closures_and_mutation(m):
    prog = """
    (define (make-counter)
      (let ((n 0))
        (lambda () (set! n (+ n 1)) n)))
    (define c1 (make-counter))
    (define c2 (make-counter))
    (c1) (c1)
    (display (list (c1) (c2) (c1) (c2)))
    """
    _check(m, prog, "(3 1 4 2)")
    # shared state between closures made in the same call
    prog = """
    (define (make-cell v)
      (cons (lambda () v) (lambda (x) (set! v x))))
    (define a (make-cell 1))
    (define b (make-cell 100))
    (define get-a (car a))
    ((cdr a) 42)
    (display (list (get-a) ((car b))))
    ((cdr b) (+ (get-a) 1))
    (display (list ((car a)) ((car b))))
    """
    _check(m, prog, "(42 100)(42 43)")
    # bank account with message passing
    prog = """
    (define (make-account balance)
      (define (withdraw amount)
        (if (>= balance amount)
            (begin (set! balance (- balance amount)) balance)
            'insufficient))
      (define (deposit amount) (set! balance (+ balance amount)) balance)
      (define (dispatch m)
        (cond ((eq? m 'withdraw) withdraw)
              ((eq? m 'deposit) deposit)
              ((eq? m 'balance) balance)
              (else (error "unknown request" m))))
      dispatch)
    (define acc (make-account 100))
    (define acc2 (make-account 5))
    (display ((acc 'withdraw) 30)) (newline)
    (display ((acc 'withdraw) 80)) (newline)
    (display ((acc 'deposit) 50)) (newline)
    (display (list (acc 'balance) (acc2 'balance) ((acc2 'withdraw) 6) ((acc2 'deposit) 1)))
    (newline)
    (acc 'close)
    """
    e = _fails(m, prog, msg="unknown request close")
    assert e.output == "70\ninsufficient\n120\n(120 5 insufficient 6)\n", repr(e.output)
    # lexical (not dynamic) scoping; closures see later mutation of captured variables
    _check(m, "(define x 1) (define (f) x) (display (let ((x 2)) (f))) (display ((lambda (x) (f)) 3))", "11")
    _check(m, "(define (g x) (lambda () x)) (define h (g 7)) (display (let ((x 99)) (h)))", "7")
    _check(m, "(define (mk n) (lambda () (set! n (+ n 1)) n)) (define a (mk 0)) (define b (mk 10)) (a) (b) (a) (display (list (a) (b)))", "(3 12)")
    _check(m, "(define total 0) (define (add! n) (set! total (+ total n)) total) (add! 5) (add! 6) (display total)", "11")
    _check(m, "(define x 1) (define (f) (set! x (+ x 10)) x) (display (list (f) (f) x))", "(11 21 21)")
    _check(m, "(display (let ((x 1)) (let ((get (lambda () x))) (set! x 5) (get))))", "5")
    _check(m, "(define (f x) (set! x (* x 2)) x) (define y 4) (display (list (f y) y))", "(8 4)")
    _check(m, "(display (let ((x 1)) (let ((x 2)) (set! x 3)) x))", "1")
    _check(m, "(define x 1) (display (let ((x 2)) (set! x 3) x)) (display x)", "31")
    # set! and define print nothing
    _check(m, "(define x 1) (set! x 2) (display (if #f #f))", "")
    # curried closures and composition
    _check(m, "(define add3 (lambda (a) (lambda (b) (lambda (c) (+ a b c))))) (display (((add3 1) 2) 3))", "6")
    _check(m, "(define (compose f g) (lambda (x) (f (g x)))) (define inc (lambda (x) (+ x 1))) (define dbl (lambda (x) (* x 2))) "
              "(display (list ((compose inc dbl) 5) ((compose dbl inc) 5)))", "(11 12)")
    # accumulator generator using internal defines
    prog = """
    (define (make-acc)
      (define total 0)
      (define (add! n) (set! total (+ total n)) total)
      add!)
    (define a (make-acc))
    (define b (make-acc))
    (a 1) (a 2) (b 10)
    (display (list (a 0) (b 0)))
    """
    _check(m, prog, "(3 10)")
    # every iteration of a loop gets fresh bindings
    prog = """
    (define thunks
      (let loop ((i 0) (acc '()))
        (if (= i 4)
            (reverse acc)
            (loop (+ i 1) (cons (lambda () (* i 10)) acc)))))
    (define (call-all l) (if (null? l) '() (cons ((car l)) (call-all (cdr l)))))
    (display (call-all thunks))
    """
    _check(m, prog, "(0 10 20 30)")
    prog = """
    (define (make-list-of-closures n)
      (let loop ((i 0) (acc '()))
        (if (= i n) acc
            (let ((j (* i i)))
              (loop (+ i 1) (cons (lambda () (set! j (+ j 1)) j) acc))))))
    (define fs (make-list-of-closures 3))
    ((car fs)) ((car fs))
    (display (list ((car fs)) ((car (cdr fs))) ((car (cdr (cdr fs))))))
    """
    _check(m, prog, "(7 2 1)")
    # recursion between closures stored in variables
    _check(m, "(define fib (lambda (n) (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2)))))) (display (fib 15))", "610")
    # Y combinator (applicative order)
    prog = """
    (define Y
      (lambda (f)
        ((lambda (x) (f (lambda (v) ((x x) v))))
         (lambda (x) (f (lambda (v) ((x x) v)))))))
    (define fact (Y (lambda (self) (lambda (n) (if (= n 0) 1 (* n (self (- n 1))))))))
    (display (fact 10))
    """
    _check(m, prog, "3628800")
    # Church numerals
    prog = """
    (define zero (lambda (f) (lambda (x) x)))
    (define (succ n) (lambda (f) (lambda (x) (f ((n f) x)))))
    (define (add a b) (lambda (f) (lambda (x) ((a f) ((b f) x)))))
    (define (to-int n) ((n (lambda (k) (+ k 1))) 0))
    (define three (succ (succ (succ zero))))
    (display (to-int (add three (succ three))))
    """
    _check(m, prog, "7")


# ----------------------------------------------- 6. binding forms and scoping

def test_binding_forms_and_internal_defines(m):
    # let: inits in outer scope, simultaneous binding
    _check(m, "(define x 10) (display (let ((x 1) (y x)) (list x y)))", "(1 10)")
    _check(m, "(display (let () 5))", "5")
    _check(m, "(display (let ((x 1)) (display \"a\") (display \"b\") x))", "ab1")
    # let*: sequential
    _check(m, "(display (let* ((x 1) (y (+ x 1)) (z (* y 3))) (list x y z)))", "(1 2 6)")
    _check(m, "(display (let* ((x 1) (x (+ x 1))) x))", "2")
    _check(m, "(display (let* () 9))", "9")
    # letrec
    _check(m, "(display (letrec ((ev? (lambda (n) (if (= n 0) #t (od? (- n 1))))) (od? (lambda (n) (if (= n 0) #f (ev? (- n 1)))))) (list (ev? 10) (od? 10) (ev? 7))))",
           "(#t #f #f)")
    _check(m, "(display (letrec ((f (lambda () g)) (g 2)) (f)))", "2")
    _check(m, "(display (letrec ((a 1) (b (+ a 1))) b))", "2")
    _fails(m, "(display \"x\") (letrec ((a b) (b 1)) a)", out="x")
    # named let: init expressions are evaluated in the outer scope, name visible in body only
    _check(m, "(define f 5) (display (let f ((x f)) (if (> x 0) (f (- x 1)) 'done)))", "done")
    _check(m, "(define (loop) 'outer) (display (let loop ((i 0)) (if (< i 3) (loop (+ i 1)) i)))", "3")
    _check(m, "(display (let loop () 'zero-bindings))", "zero-bindings")
    _check(m, "(display (let loop ((i 0) (acc '())) (if (= i 5) (reverse acc) (loop (+ i 1) (cons (* i i) acc)))))", "(0 1 4 9 16)")
    _check(m, "(let loop ((i 0)) (if (< i 3) (begin (display i) (loop (+ i 1)))))", "012")
    _fails(m, "(display (let n ((i 1)) 5)) (display n)", out="5")        # name not visible after the let
    # internal definitions
    prog = """
    (define (f n)
      (define (ev? n) (if (= n 0) #t (od? (- n 1))))
      (define (od? n) (if (= n 0) #f (ev? (- n 1))))
      (list (ev? n) (od? n)))
    (display (f 7)) (display (f 10))
    """
    _check(m, prog, "(#f #t)(#t #f)")
    _check(m, "(define (f) (display \"a\") (define y 2) (display y) y) (display (f))", "a22")
    _check(m, "(define (f) (define (g) y) (define y 5) (g)) (display (f))", "5")
    _check(m, "(define (f) (define a 1) (define b (+ a 1)) (define c (* b 10)) (list a b c)) (display (f))", "(1 2 20)")
    # reading a body-defined variable before its define is an error, even if a global exists
    _fails(m, "(define x 'global) (define (f) (display \"A\") (display x) (define x 1) x) (f)", out="A")
    _fails(m, "(define x 'global) (define (f) (define y x) (define x 1) y) (f)", out="")
    # ... but a closure created earlier may use a later definition once it has run
    _check(m, "(define x 'global) (define (f) (define (g) x) (define x 'local) (g)) (display (f)) (display x)", "localglobal")
    # internal defines are local to their body, in every kind of body
    _fails(m, "(define (f) (define z 1) z) (display (f)) (display z)", out="1")
    _check(m, "(define b 100) (display (let () (define b 1) b)) (display b)", "1100")
    _check(m, "(display (let ((a 1)) (define b (+ a 1)) (* a b)))", "2")
    _check(m, "(display (let* ((a 1)) (define (sq x) (* x x)) (sq (+ a 2))))", "9")
    _check(m, "(display (letrec ((a 1)) (define b 2) (+ a b)))", "3")
    _check(m, "(display (let loop ((i 0)) (define j (* i 2)) (if (< i 3) (loop (+ i 1)) j)))", "6")
    _check(m, "(define q 'top) (define (f) (define q 'inner) q) (display (list (f) q))", "(inner top)")
    # top-level define semantics
    _check(m, "(define (f) (g)) (define (g) 1) (display (f))", "1")                     # late binding of globals
    _check(m, "(define (f) 1) (define (g) (f)) (define (f) 2) (display (g))", "2")
    _check(m, "(define x 1) (define x 2) (display x)", "2")
    _check(m, "(begin (define q 1) (define w 2)) (display (+ q w))", "3")
    _fails(m, "(display x) (define x 1)", out="")
    # rest parameters
    for expr, want in [("((lambda args args) 1 2 3)", "(1 2 3)"), ("((lambda args args))", "()"),
                       ("((lambda (a . r) (list a r)) 1)", "(1 ())"), ("((lambda (a . r) (list a r)) 1 2 3)", "(1 (2 3))"),
                       ("((lambda (a b . r) (list a b r)) 1 2)", "(1 2 ())"), ("((lambda (a) a) 5)", "5")]:
        _disp(m, expr, want)
    _check(m, "(define (f a b . rest) (list a b rest)) (display (f 1 2)) (display (f 1 2 3 4))", "(1 2 ())(1 2 (3 4))")
    _check(m, "(define (f . args) (length args)) (display (list (f) (f 1) (f 1 2 3)))", "(0 1 3)")
    _fails(m, "(define (f a b . rest) a) (display \"k\") (f 1)", out="k")
    # body value is the last form
    _check(m, "(define (f) 1 2 3) (display (f)) (display ((lambda () (display \"x\") 'y)))", "3xy")


# --------------------------------------------------------- 7. evaluation order

def test_evaluation_order(m):
    trace = lambda tag, val: f"(begin (display \"{tag}\") {val})"
    _check(m, f"(display (list {trace('a', 1)} {trace('b', 2)} {trace('c', 3)}))", "abc(1 2 3)")
    _check(m, f"(display ((begin (display \"f\") +) {trace('1', 1)} {trace('2', 2)}))", "f123")
    _check(m, f"(display (+ {trace('a', 1)} (* {trace('b', 2)} {trace('c', 3)})))", "abc7")
    _check(m, f"(display (cons {trace('1', 1)} {trace('2', 2)}))", "12(1 . 2)")
    _check(m, f"(display (let ((a {trace('1', 1)}) (b {trace('2', 2)}) (c {trace('3', 3)})) (list a b c)))", "123(1 2 3)")
    _check(m, f"(display (let* ((a {trace('1', 1)}) (b {trace('2', 2)})) (list a b)))", "12(1 2)")
    _check(m, f"(display (letrec ((a {trace('1', 1)}) (b {trace('2', 2)})) (list a b)))", "12(1 2)")
    _check(m, f"(display (let lp ((a {trace('1', 1)}) (b {trace('2', 2)})) (list a b)))", "12(1 2)")
    _check(m, f"(define (f a b c) (list a b c)) (display (f {trace('x', 1)} {trace('y', 2)} {trace('z', 3)}))", "xyz(1 2 3)")
    _check(m, "(define n 0) (define (next!) (set! n (+ n 1)) n) (display (list (next!) (next!) (next!)))", "(1 2 3)")
    _check(m, "(define n 0) (define (next!) (set! n (+ n 1)) n) (display (- (next!) (next!)))", "-1")
    _check(m, "(define n 0) (define (next!) (set! n (+ n 1)) n) (display (apply list (next!) (next!) (list (next!))))", "(1 2 3)")
    # short-circuiting and untaken branches
    _check(m, "(and #f (display \"no\")) (or 1 (display \"no\")) (if #t (display \"a\") (display \"b\")) (if #f (display \"c\") (display \"d\"))", "ad")
    _check(m, "(cond (#t (display \"1\")) ((display \"no\") 2)) (cond (#f 1) (else (display \"e\")))", "1e")
    _check(m, "(display (and 1 (display \"x\") 2))", "x2")
    _check(m, "(display (or #f (begin (display \"x\") #f) (begin (display \"y\") 3) (begin (display \"z\") 4)))", "xy3")
    # operator and operands are evaluated before the call is checked
    _fails(m, "(5 (display \"x\"))", out="x")
    _fails(m, "((lambda () 1) (display \"y\"))", out="y")
    _fails(m, "(define (f a) a) (f (display \"p\") (display \"q\"))", out="pq")
    _fails(m, "(+ 1 \"a\" (display \"z\"))", out="z")
    _fails(m, "(car (display \"w\"))", out="w")
    _fails(m, "(undefined-fn (display \"u\"))", out="")      # operator is evaluated first: unbound before operands
    _fails(m, "((begin (display \"f\") 5) (begin (display \"a\") 1))", out="fa")
    _fails(m, "(set! nope (begin (display \"e\") 1))", out="e")
    _fails(m, "(display (list 1 (begin (display \"s\") (car '()))))", out="s")
    _fails(m, "(display (< 3 2 (begin (display \"k\") 'a)))", out="k")


# ----------------------------------------------------------------- 8. errors

def test_error_handling(m):
    fn = _fails
    fn(m, "(display \"a\") (car '()) (display \"b\")", out="a")
    fn(m, "(display 1) (display undefined-var) (display 2)", out="1")
    fn(m, "(display \"p\") (5 3)", out="p")
    fn(m, "(\"str\")")
    fn(m, "((list 1) 2)")
    fn(m, "(1)")
    fn(m, "(())")
    fn(m, "()")
    fn(m, "((quote x) 1)")
    fn(m, "(#f)")
    fn(m, "(define (f a b) a) (display \"k\") (f 1)", out="k")
    fn(m, "(define (f a b) a) (f 1 2 3)")
    fn(m, "(define (f) 1) (f 1)")
    fn(m, "((lambda (x) x))")
    fn(m, "((lambda (x) x) 1 2)")
    fn(m, "((lambda (a b . r) a) 1)")
    fn(m, "((lambda () 1) 1)")
    for src in ["(display)", "(display 1 2)", "(newline 1)", "(error)", "(list? 1 2)", "(procedure?)", "(symbol?)"]:
        fn(m, src)
    fn(m, "(display \"ab\") (newline) (display (list 1 (car 5)))", out="ab\n")
    fn(m, "(set! zz 1)")
    fn(m, "(define (f) (set! undefined-thing 1)) (f)")
    # malformed special forms (evaluated at top level, after earlier output)
    for src in ["(if)", "(if 1)", "(if 1 2 3 4)", "(lambda)", "(lambda (x))", "(lambda (1) 1)", "(let ((x)) x)", "(let ((1 2)) 3)",
                "(let ((x 1 2)) x)", "(let ((x 1)))", "(define)", "(define x)", "(define x 1 2)", "(define 5 1)", "(begin)", "(quote)",
                "(quote 1 2)", "(set! 1 2)", "(set! x)", "(cond 5)", "(let x)"]:
        fn(m, "(display \"o\") " + src, out="o")
    fn(m, "(1 . 2)")
    # error: message formats
    fn(m, "(error \"boom\")", out="", msg="boom")
    fn(m, "(display \"pre\") (error \"m\") (display \"post\")", out="pre", msg="m")
    fn(m, "(error \"bad thing:\" 42 \"str\" '(a \"b\"))", msg="bad thing: 42 \"str\" (a \"b\")")
    fn(m, "(error \"x\" 'sym #t #f '() -3)", msg="x sym #t #f () -3")
    fn(m, "(error \"q\" \"a\\\"b\\\\c\\nd\")", msg='q "a\\"b\\\\c\\nd"')
    fn(m, "(error \"ends\" (cons 1 \"s\"))", msg='ends (1 . "s")')
    fn(m, "(error \"nested\" '((\"a\" . 1) (b \"c d\")))", msg='nested (("a" . 1) (b "c d"))')
    fn(m, "(error \"with-str\" (list \"x\" 'y))", msg='with-str ("x" y)')
    fn(m, "(error \"proc\" car)", msg="proc #<procedure>")
    fn(m, "(error (string-append \"con\" \"cat\") (+ 1 2))", msg="concat 3")
    fn(m, "(error 'not-a-string \"x\")")
    fn(m, "(error 5)")
    fn(m, "(define (f n) (if (= n 0) (error \"deep\" n) (+ 1 (f (- n 1))))) (display \"s\") (f 100)", out="s", msg="deep 0")
    fn(m, "(define (f n) (if (= n 0) (car '()) (+ 1 (f (- n 1))))) (display \"s\") (f 3000)", out="s")
    fn(m, "(apply error '(\"via apply\" 1))", msg="via apply 1")
    # errors raised through apply / higher-order code carry the output so far
    fn(m, "(define (each f l) (if (null? l) 'done (begin (f (car l)) (each f (cdr l))))) (each (lambda (x) (display x) (car x)) '(1 2 3))", out="1")
    # SchemeError is an Exception, run returns str and never prints
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = m.run("(display \"hello\") (newline) (display (list 1 2))")
        try:
            m.run("(display \"zzz\") (car 1)")
        except m.SchemeError:
            pass
    assert r == "hello\n(1 2)" and isinstance(r, str)
    assert buf.getvalue() == "", f"run must not print to stdout, printed {buf.getvalue()!r}"
    # fresh global environment per run; state does not leak, nor survive errors
    assert m.run("(define x 1) (define (f) 2) (display x)") == "1"
    fn(m, "(display x)")
    fn(m, "(display (f))")
    assert m.run("(define (car x) 0) (display (car '(5)))") == "0"
    assert m.run("(display (car '(5)))") == "5"
    fn(m, "(define y 1) (car '())")
    fn(m, "(display y)")
    assert m.run("(define (loop n) (if (= n 0) 'ok (loop (- n 1)))) (display (loop 10))") == "ok"
    # exception attributes survive pickling-free introspection
    e = fn(m, "(display 7) (error \"E\" 1)")
    assert isinstance(e, Exception) and e.output == "7" and str(e) == "E 1"


# ------------------------------------------------------------- 9/10/11. tail calls

def test_tail_calls_long_loops(m):
    prog = """
    (define (loop i acc) (if (= i 300000) acc (loop (+ i 1) (+ acc i))))
    (display (loop 0 0))
    """
    _check(m, prog, str(sum(range(300000))))
    prog = """
    (define (my-even? n) (if (= n 0) #t (my-odd? (- n 1))))
    (define (my-odd? n) (if (= n 0) #f (my-even? (- n 1))))
    (display (list (my-even? 200000) (my-odd? 199999)))
    """
    _check(m, prog, "(#t #t)")
    prog = """
    (define (even? n) (if (= n 0) #t (odd? (- n 1))))
    (define (odd? n) (if (= n 0) #f (even? (- n 1))))
    (display (even? 60001))
    """
    _check(m, prog, "#f")


_BIG, _SMALL = 100000, 20000


def test_tail_calls_in_conditionals(m):
    b, s = _BIG, _SMALL
    prog = f"""
    (define counter 0)
    (define (t-cond n) (cond ((= n 0) 'done) ((> n 0) (t-cond (- n 1))) (else 'neg)))
    (define (t-cond-multi n) (cond ((= n 0) 'done) (else (set! counter (+ counter 1)) (t-cond-multi (- n 1)))))
    (define (t-and n) (and #t (if (= n 0) 'done (t-and (- n 1)))))
    (define (t-and2 n) (if (= n 0) 'done (and (>= n 0) (t-and2 (- n 1)))))
    (define (t-or n) (or #f (if (= n 0) 'done (t-or (- n 1)))))
    (define (t-or2 n) (or (= n 0) (t-or2 (- n 1))))
    (define (t-begin n) (begin 1 2 (if (= n 0) 'done (t-begin (- n 1)))))
    (define (t-a n) (cond ((= n 0) 'done) (else (t-b (- n 1)))))
    (define (t-b n) (and (>= n 0) (or #f (t-a n))))
    (display (list (t-cond {b}) (t-cond-multi {s}) (t-and {b}) (t-and2 {s}) (t-or {b}) (t-or2 {s}) (t-begin {b}) (t-a {s})))
    (display counter)
    """
    _check(m, prog, f"(done done done done done #t done done){s}")


def test_tail_calls_in_binding_forms_and_apply(m):
    b, s = _BIG, _SMALL
    prog = f"""
    (define (t-let n) (let ((m (- n 1))) (if (< m 0) 'done (t-let m))))
    (define (t-let* n) (let* ((m (- n 1)) (k m)) (if (< k 0) 'done (t-let* k))))
    (define (t-letrec n) (letrec ((m (- n 1))) (if (< m 0) 'done (t-letrec m))))
    (define (t-named n) (let loop ((i n)) (if (= i 0) 'done (loop (- i 1)))))
    (define (t-named2 n) (let loop ((i n)) (cond ((= i 0) 'done) (else (let ((j (- i 1))) (loop j))))))
    (define (t-apply n) (if (= n 0) 'done (apply t-apply (list (- n 1)))))
    (define (t-body-def n) (define m (- n 1)) (if (< m 0) 'done (t-body-def m)))
    (define (t-lambda n) ((lambda (k) (if (= k 0) 'done (t-lambda (- k 1)))) n))
    (define (t-rest . args) (if (= (car args) 0) 'done (apply t-rest (- (car args) 1) '())))
    (display (list (t-let {b}) (t-let* {s}) (t-letrec {s}) (t-named {s}) (t-named2 {s}) (t-body-def {b}) (t-lambda {s}) (t-rest {s})))
    (display (t-apply {b}))
    """
    _check(m, prog, "(done done done done done done done done)done")
    _fails(m, "(define (t-apply2 n) (apply t-apply2 n)) (t-apply2 3)")


# ----------------------------------------- 12. deep recursion and long lists

def test_deep_recursion_and_long_lists(m):
    prog = """
    (define (build n) (if (= n 0) '() (cons n (build (- n 1)))))
    (define (sum l) (if (null? l) 0 (+ (car l) (sum (cdr l)))))
    (define (count n) (if (= n 0) 0 (+ 1 (count (- n 1)))))
    (define (count2 n) (cond ((= n 0) 0) (else (let ((r (count2 (- n 1)))) (+ r 1)))))
    (define (my-map f l) (if (null? l) '() (cons (f (car l)) (my-map f (cdr l)))))
    (define (my-append a b) (if (null? a) b (cons (car a) (my-append (cdr a) b))))
    (define l (build 5000))
    (display (list (length l) (car l) (sum l) (count 5000) (count2 5000)))
    (display (sum (my-map (lambda (x) (* x 2)) l)))
    (display (length (my-append l l)))
    (display (equal? (my-append l '()) l))
    """
    _check(m, prog, f"(5000 5000 {5000 * 5001 // 2} 5000 5000){5000 * 5001}10000#t")
    # an error raised at depth 5000 is still a SchemeError, with the output so far
    _fails(m, "(define (f n) (if (= n 0) (car '()) (+ 1 (f (- n 1))))) (display \"d\") (f 5000)", out="d")
    # many non-tail frames mixed with other forms
    prog = """
    (define (f n) (if (= n 0) 0 (+ 1 (let* ((a (f (- n 1)))) (and #t (or #f a))))))
    (display (f 4000))
    """
    _check(m, prog, "4000")
    # long lists (50000 elements): length, reverse, append, list?, equal?, display must not recurse per element
    n = 50000
    prog = f"""
    (define (iota n) (let loop ((i n) (acc '())) (if (= i 0) acc (loop (- i 1) (cons i acc)))))
    (define l (iota {n}))
    (define (sum l acc) (if (null? l) acc (sum (cdr l) (+ acc (car l)))))
    (display (list (length l) (car (reverse l)) (length (append l l)) (list? l) (equal? l (iota {n})) (equal? l (reverse (reverse l)))
                   (equal? l (iota {n - 1})) (sum l 0)))
    (newline)
    (display l)
    """
    want = f"({n} {n} {2 * n} #t #t #t #f {n * (n + 1) // 2})\n(" + " ".join(map(str, range(1, n + 1))) + ")"
    _check(m, prog, want)
    # improper long list
    prog = f"""
    (define (build n tail) (let loop ((i n) (acc tail)) (if (= i 0) acc (loop (- i 1) (cons i acc)))))
    (define l (build 50000 'end))
    (display (list (list? l) (pair? l) (car l)))
    """
    _check(m, prog, "(#f #t 1)")
    _fails(m, prog + "(length l)")
    _check(m, "(define l (let loop ((i 0) (a '())) (if (= i 50000) a (loop (+ i 1) (cons (list i) a))))) (display (length (apply append l)))", "50000")


# ------------------------------------------------------------ 13. classic programs

_HOF = """
(define (map f l) (if (null? l) '() (cons (f (car l)) (map f (cdr l)))))
(define (filter p l) (cond ((null? l) '()) ((p (car l)) (cons (car l) (filter p (cdr l)))) (else (filter p (cdr l)))))
(define (foldl f acc l) (if (null? l) acc (foldl f (f acc (car l)) (cdr l))))
(define (foldr f acc l) (if (null? l) acc (f (car l) (foldr f acc (cdr l)))))
(define (for-each f l) (if (null? l) 'done (begin (f (car l)) (for-each f (cdr l)))))
(define (iota a b) (if (> a b) '() (cons a (iota (+ a 1) b))))
"""


def _queens(n):
    return sum(1 for p in itertools.permutations(range(n))
               if all(abs(p[i] - p[j]) != j - i for i in range(n) for j in range(i + 1, n)))


def test_classic_programs(m):
    _check(m, "(define (fib n) (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2))))) (display (fib 20))", "6765")
    _check(m, "(define (fact n) (if (= n 0) 1 (* n (fact (- n 1))))) (display (fact 30))", str(math.factorial(30)))
    _check(m, _HOF + "(display (map (lambda (x) (* x x)) (iota 1 10)))", "(" + " ".join(str(i * i) for i in range(1, 11)) + ")")
    _check(m, _HOF + "(display (filter (lambda (x) (= 0 (modulo x 3))) (iota 1 20)))", "(3 6 9 12 15 18)")
    _check(m, _HOF + "(display (list (foldl + 0 (iota 1 100)) (foldl (lambda (a x) (cons x a)) '() '(1 2 3)) (foldr cons '() '(1 2 3)) (foldr - 0 '(10 4 1))))",
           "(5050 (3 2 1) (1 2 3) 7)")
    _check(m, _HOF + "(for-each (lambda (x) (display x) (display \",\")) '(1 2 3))", "1,2,3,")
    # quicksort / merge sort against sorted()
    data = [5, 3, 9, -1, 0, 3, 12, 7, -8, 5, 5, 100, 2]
    qs = _HOF + """
    (define (qsort l)
      (if (null? l) '()
          (let ((p (car l)) (r (cdr l)))
            (append (qsort (filter (lambda (x) (< x p)) r)) (list p) (qsort (filter (lambda (x) (>= x p)) r))))))
    (display (qsort '(%s)))""" % " ".join(map(str, data))
    _check(m, qs, "(" + " ".join(map(str, sorted(data))) + ")")
    # n-queens (count solutions), checked against an itertools brute force
    queens = """
    (define (queens board-size)
      (define (safe? q dist placed)
        (or (null? placed)
            (and (not (= q (car placed)))
                 (not (= (- q (car placed)) dist))
                 (not (= (- (car placed) q) dist))
                 (safe? q (+ dist 1) (cdr placed)))))
      (define (place k placed)
        (if (= k 0)
            1
            (let loop ((q 1) (total 0))
              (if (> q board-size)
                  total
                  (loop (+ q 1)
                        (if (safe? q 1 placed) (+ total (place (- k 1) (cons q placed))) total))))))
      (place board-size '()))
    (display (list (queens 4) (queens 5) (queens 6)))"""
    _check(m, queens, f"({_queens(4)} {_queens(5)} {_queens(6)})")
    assert _queens(6) == 4
    # primes, gcd, collatz, hanoi, ackermann
    prog = _HOF + """
    (define (prime? n) (and (> n 1) (let loop ((d 2)) (cond ((> (* d d) n) #t) ((= 0 (remainder n d)) #f) (else (loop (+ d 1)))))))
    (define (gcd a b) (if (= b 0) a (gcd b (remainder a b))))
    (define (collatz n steps) (cond ((= n 1) steps) ((= 0 (modulo n 2)) (collatz (quotient n 2) (+ steps 1))) (else (collatz (+ (* 3 n) 1) (+ steps 1)))))
    (define (hanoi n) (if (= n 0) 0 (+ 1 (* 2 (hanoi (- n 1))))))
    (define (ack m n) (cond ((= m 0) (+ n 1)) ((= n 0) (ack (- m 1) 1)) (else (ack (- m 1) (ack m (- n 1))))))
    (display (list (filter prime? (iota 1 50)) (gcd 1071 462) (collatz 27 0) (hanoi 10) (ack 2 3)))
    """
    primes = [p for p in range(2, 51) if all(p % d for d in range(2, p))]

    def collatz(n):
        s = 0
        while n != 1:
            n = n // 2 if n % 2 == 0 else 3 * n + 1
            s += 1
        return s
    _check(m, prog, f"(({' '.join(map(str, primes))}) {math.gcd(1071, 462)} {collatz(27)} {2 ** 10 - 1} 9)")
    # string building
    prog = _HOF + """
    (define (repeat s n) (if (= n 0) "" (string-append s (repeat s (- n 1)))))
    (define (join strs sep)
      (cond ((null? strs) "") ((null? (cdr strs)) (car strs)) (else (string-append (car strs) sep (join (cdr strs) sep)))))
    (display (repeat "ab" 3)) (newline)
    (display (join (map number->string (iota 1 10)) ", ")) (newline)
    (display (join '("x") "-")) (display (join '() "-")) (display (string-append (join '("a" "b") "") "!"))
    """
    _check(m, prog, "ababab\n1, 2, 3, 4, 5, 6, 7, 8, 9, 10\nxab!")
    # association list updates
    prog = """
    (define (assoc-get key al default)
      (cond ((null? al) default) ((equal? (car (car al)) key) (cdr (car al))) (else (assoc-get key (cdr al) default))))
    (define (assoc-set al key val)
      (cond ((null? al) (list (cons key val)))
            ((equal? (car (car al)) key) (cons (cons key val) (cdr al)))
            (else (cons (car al) (assoc-set (cdr al) key val)))))
    (define (assoc-del al key)
      (cond ((null? al) '()) ((equal? (car (car al)) key) (cdr al)) (else (cons (car al) (assoc-del (cdr al) key)))))
    (define db '())
    (set! db (assoc-set db 'a 1))
    (set! db (assoc-set db 'b 2))
    (set! db (assoc-set db "c" 3))
    (set! db (assoc-set db 'a 10))
    (display db) (newline)
    (display (list (assoc-get 'a db 0) (assoc-get "c" db 0) (assoc-get 'zz db 'none)))
    (set! db (assoc-del db 'b))
    (display db)
    (display (assoc-get 'b db "missing"))
    """
    _check(m, prog, "((a . 10) (b . 2) (c . 3))\n(10 3 none)((a . 10) (c . 3))missing")
    # flatten, powerset
    prog = _HOF + """
    (define (flatten x) (cond ((null? x) '()) ((pair? x) (append (flatten (car x)) (flatten (cdr x)))) (else (list x))))
    (define (powerset s) (if (null? s) '(()) (let ((r (powerset (cdr s)))) (append r (map (lambda (x) (cons (car s) x)) r)))))
    (display (flatten '(1 (2 (3 4)) ((5)) () 6)))
    (display (length (powerset (iota 1 10))))
    (display (powerset '(a b)))
    """
    _check(m, prog, "(1 2 3 4 5 6)1024(() (b) (a) (a b))")


# ------------------------------------------------------- 14. randomized checks

class _Cell:
    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v


class _Gen:
    """Random int/bool expression trees: returns (scheme source, evaluator(env)->python value)."""
    NAMES = ["a", "b", "c", "x", "y"]

    def __init__(self, rng):
        self.r = rng

    def const(self):
        r = self.r
        k = r.random()
        if k < 0.1:
            v = r.choice([-1, 1]) * (10 ** r.randint(18, 25) + r.randint(0, 999))
        else:
            v = r.randint(-12, 12)
        return (str(v), lambda env, v=v: v)

    def var(self, env_names):
        n = self.r.choice(env_names)
        return (n, lambda env, n=n: env[n].v)

    def int_(self, d, names):
        r = self.r
        if d <= 0:
            return self.var(names) if names and r.random() < 0.6 else self.const()
        k = r.randrange(16)
        sub = lambda: self.int_(d - 1, names)
        if k == 0:
            return self.var(names) if names else self.const()
        if k == 1:
            return self.const()
        if k in (2, 3, 4):
            op = r.choice(["+", "-", "*"])
            args = [sub() for _ in range(r.randint(0 if op != "-" else 1, 3))]
            src = f"({op} " + " ".join(a[0] for a in args) + ")" if args else f"({op})"

            def f(env, op=op, args=args):
                vals = [a[1](env) for a in args]
                if op == "+":
                    return sum(vals)
                if op == "*":
                    return math.prod(vals)
                if len(vals) == 1:
                    return -vals[0]
                return vals[0] - sum(vals[1:])
            return (src, f)
        if k == 5:
            op = r.choice(["quotient", "remainder", "modulo"])
            e1, e2 = sub(), sub()
            src = f"(let ((n {e1[0]}) (d {e2[0]})) (if (= d 0) 0 ({op} n d)))"

            def f(env, op=op, e1=e1, e2=e2):
                n, d = e1[1](env), e2[1](env)
                if d == 0:
                    return 0
                q = _trunc_quot(n, d)
                return q if op == "quotient" else n - d * q if op == "remainder" else n % d
            return (src, f)
        if k in (6, 7):
            c, a, b = self.any_(d - 1, names), self.int_(d - 1, names), self.int_(d - 1, names)
            return (f"(if {c[0]} {a[0]} {b[0]})", lambda env: a[1](env) if c[1](env) is not False else b[1](env))
        if k == 8:  # let
            n1, n2 = r.choice(self.NAMES), r.choice(self.NAMES)
            i1, i2 = sub(), sub()
            names2 = list(set(names) | {n1, n2})
            body = self.int_(d - 1, names2)
            src = f"(let (({n1} {i1[0]}) ({n2} {i2[0]})) {body[0]})"

            def f(env):
                v1, v2 = i1[1](env), i2[1](env)
                e2 = dict(env)
                e2[n1] = _Cell(v1)
                e2[n2] = _Cell(v2)
                return body[1](e2)
            return (src, f)
        if k == 9:  # let*
            n1, n2 = r.choice(self.NAMES), r.choice(self.NAMES)
            i1 = sub()
            names1 = list(set(names) | {n1})
            i2 = self.int_(d - 1, names1)
            names2 = list(set(names1) | {n2})
            body = self.int_(d - 1, names2)
            src = f"(let* (({n1} {i1[0]}) ({n2} {i2[0]})) {body[0]})"

            def f(env):
                e1 = dict(env)
                e1[n1] = _Cell(i1[1](env))
                e2 = dict(e1)
                e2[n2] = _Cell(i2[1](e1))
                return body[1](e2)
            return (src, f)
        if k == 10:  # immediately applied lambda
            n1, n2 = r.choice(self.NAMES[:3]), r.choice(self.NAMES[3:])
            a1, a2 = sub(), sub()
            body = self.int_(d - 1, list(set(names) | {n1, n2}))
            src = f"((lambda ({n1} {n2}) {body[0]}) {a1[0]} {a2[0]})"

            def f(env):
                v1, v2 = a1[1](env), a2[1](env)
                e2 = dict(env)
                e2[n1] = _Cell(v1)
                e2[n2] = _Cell(v2)
                return body[1](e2)
            return (src, f)
        if k == 11:  # cond
            clauses = []
            for _ in range(r.randint(1, 3)):
                t = self.any_(d - 1, names)
                if r.random() < 0.2:
                    clauses.append((t, None))
                else:
                    clauses.append((t, self.int_(d - 1, names)))
            els = self.int_(d - 1, names)
            src = "(cond " + " ".join(f"({t[0]} {b[0]})" if b else f"({t[0]})" for t, b in clauses) + f" (else {els[0]}))"

            def f(env):
                for t, b in clauses:
                    v = t[1](env)
                    if v is not False:
                        if b is None:
                            # (test) clause returns the test value; only generated here when it is an int
                            return v
                        return b[1](env)
                return els[1](env)
            # (test) clauses may return a bool; avoid by regenerating those with int test values
            return (src, f) if all(b is not None for _, b in clauses) else self.int_(d, names)
        if k == 12 and names:  # set!
            n = r.choice(names)
            e = sub()
            body = self.int_(d - 1, names)
            return (f"(begin (set! {n} {e[0]}) {body[0]})",
                    lambda env: (env[n].__setattr__("v", e[1](env)), body[1](env))[1])
        if k == 13:
            args = [sub() for _ in range(r.randint(0, 4))]
            return ("(length (list " + " ".join(a[0] for a in args) + "))", lambda env: [a[1](env) for a in args] and len(args) or len(args))
        if k == 14:
            a, b, c = sub(), sub(), sub()
            return (f"(car (cdr (list {a[0]} {b[0]} {c[0]})))", lambda env: (a[1](env), b[1](env), c[1](env))[1])
        # k == 15
        a, b = sub(), sub()
        return (f"(apply + {a[0]} (list {b[0]}))", lambda env: a[1](env) + b[1](env))

    def bool_(self, d, names):
        r = self.r
        k = r.randrange(7)
        if d <= 0 or k == 0:
            v = r.random() < 0.5
            return ("#t" if v else "#f", lambda env, v=v: v)
        if k in (1, 2):
            op = r.choice(["<", ">", "<=", ">=", "="])
            args = [self.int_(d - 1, names) for _ in range(r.randint(1, 4))]
            import operator
            fn = {"<": operator.lt, ">": operator.gt, "<=": operator.le, ">=": operator.ge, "=": operator.eq}[op]

            def f(env):
                vals = [a[1](env) for a in args]
                return all(fn(vals[i], vals[i + 1]) for i in range(len(vals) - 1))
            return (f"({op} " + " ".join(a[0] for a in args) + ")", f)
        if k == 3:
            a = self.any_(d - 1, names)
            return (f"(not {a[0]})", lambda env: a[1](env) is False)
        if k == 4:
            a, b = self.any_(d - 1, names), self.any_(d - 1, names)
            return (f"(equal? {a[0]} {b[0]})", lambda env: (lambda x, y: type(x) is type(y) and x == y)(a[1](env), b[1](env)))
        if k == 5:
            a = self.any_(d - 1, names)
            return (f"(number? {a[0]})", lambda env: type(a[1](env)) is int)
        a, b = self.int_(d - 1, names), self.int_(d - 1, names)
        return (f"(eq? {a[0]} {b[0]})", lambda env: a[1](env) == b[1](env))

    def any_(self, d, names):
        r = self.r
        k = r.randrange(6)
        if d <= 0 or k == 0:
            return self.int_(0, names)
        if k == 1:
            return self.bool_(d, names)
        if k == 2:
            return self.int_(d, names)
        if k in (3, 4):
            op = r.choice(["and", "or"])
            args = [self.any_(d - 1, names) for _ in range(r.randint(0, 3))]

            def f(env, op=op, args=args):
                if op == "and":
                    res = True
                    for a in args:
                        res = a[1](env)
                        if res is False:
                            return False
                    return res
                for a in args:
                    res = a[1](env)
                    if res is not False:
                        return res
                return False
            return (f"({op} " + " ".join(a[0] for a in args) + ")" if args else f"({op})", f)
        c, a, b = self.any_(d - 1, names), self.any_(d - 1, names), self.any_(d - 1, names)
        return (f"(if {c[0]} {a[0]} {b[0]})", lambda env: a[1](env) if c[1](env) is not False else b[1](env))


def _fmt_val(v):
    return "#t" if v is True else "#f" if v is False else str(v)


def _differential_expressions(m):
    rng = random.Random(20261014)
    g = _Gen(rng)
    for i in range(400):
        names = ["a", "b", "c"]
        init = {n: rng.randint(-9, 9) for n in names}
        gen = g.any_ if i % 3 == 0 else g.int_
        src_e, ev = gen(rng.randint(2, 5), names)
        env = {n: _Cell(v) for n, v in init.items()}
        want = _fmt_val(ev(env))
        src = "(define a %d) (define b %d) (define c %d)\n" % tuple(init[n] for n in names)
        # globals a b c are visible; use a wrapper so that set! hits the same bindings in both worlds
        src += f"(display {src_e})"
        got = m.run(src)
        assert got == want, f"program {src!r}: got {got!r}, want {want!r}"


_SYMS = ["a", "b", "foo", "Bar", "x1", "+", "-", "...", "a-b", "1+", "<=?", "set-x!", "a.b", ".5", "-x", "[x]", "quote", "if", "lambda", "define"]
_CHARS = ["a", "b", " ", "(", ")", ";", "'", "\\", '"', "\n", "x", "é", "1", "."]


def _rand_datum(rng, depth):
    k = rng.randrange(9 if depth > 0 else 5)
    if k == 0:
        return ("int", rng.choice([0, 1, -1, 7, -42, 10 ** 22, -(10 ** 21) - 5, 123456]))
    if k == 1:
        return ("bool", rng.random() < 0.5)
    if k == 2:
        return ("str", "".join(rng.choice(_CHARS) for _ in range(rng.randint(0, 6))))
    if k == 3:
        return ("sym", rng.choice(_SYMS))
    if k == 4:
        return ("nil",)
    if k in (5, 6):
        return ("list", [_rand_datum(rng, depth - 1) for _ in range(rng.randint(1, 4))], None)
    if k == 7:
        tail = _rand_datum(rng, 0)
        while tail[0] == "nil":
            tail = _rand_datum(rng, 0)
        return ("list", [_rand_datum(rng, depth - 1) for _ in range(rng.randint(1, 3))], tail)
    return ("quote", _rand_datum(rng, depth - 1))


def _src_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _src(d):
    t = d[0]
    if t == "int":
        return str(d[1])
    if t == "bool":
        return "#t" if d[1] else "#f"
    if t == "str":
        return _src_str(d[1])
    if t == "sym":
        return d[1]
    if t == "nil":
        return "()"
    if t == "quote":
        return "'" + _src(d[1])
    items = [_src(x) for x in d[1]]
    if d[2] is not None:
        items += [".", _src(d[2])]
    return "(" + " ".join(items) + ")"


def _show(d, write):
    t = d[0]
    if t == "int":
        return str(d[1])
    if t == "bool":
        return "#t" if d[1] else "#f"
    if t == "str":
        return _src_str(d[1]) if write else d[1]
    if t == "sym":
        return d[1]
    if t == "nil":
        return "()"
    if t == "quote":
        return "(quote " + _show(d[1], write) + ")"
    items = [_show(x, write) for x in d[1]]
    if d[2] is not None:
        items += [".", _show(d[2], write)]
    return "(" + " ".join(items) + ")"


def _build(d):
    """Scheme expression that constructs the datum at run time."""
    t = d[0]
    if t in ("int", "bool", "str"):
        return _src(d)
    if t in ("sym", "nil"):
        return "'" + _src(d)
    if t == "quote":
        return f"(list 'quote {_build(d[1])})"
    expr = _build(d[2]) if d[2] is not None else "'()"
    for x in reversed(d[1]):
        expr = f"(cons {_build(x)} {expr})"
    return expr


def _differential_data(m):
    rng = random.Random(777)
    for _ in range(250):
        d = _rand_datum(rng, 3)
        quoted = _src(d)
        # quoted literal -> display
        want = _show(d, False)
        got = m.run(f"(display '{quoted})")
        assert got == want, f"display '{quoted}: got {got!r}, want {want!r}"
        # runtime construction is equal? to the literal and prints the same
        built = _build(d)
        got = m.run(f"(define lit '{quoted}) (define built {built}) (display built) (display (equal? lit built))")
        assert got == want + "#t", f"built {built!r}: got {got!r}"
        # error irritants use the write representation
        if d[0] not in ("nil",):
            try:
                m.run(f"(error \"msg:\" '{quoted} 5)")
            except m.SchemeError as e:
                assert str(e) == "msg: " + _show(d, True) + " 5", f"{quoted!r}: message {str(e)!r}"
            else:
                raise AssertionError("error did not raise")


_LISTLIB = _HOF + """
(define (qsort l)
  (if (null? l) '()
      (let ((p (car l)) (r (cdr l)))
        (append (qsort (filter (lambda (x) (< x p)) r)) (list p) (qsort (filter (lambda (x) (>= x p)) r))))))
(define (merge a b)
  (cond ((null? a) b) ((null? b) a)
        ((<= (car a) (car b)) (cons (car a) (merge (cdr a) b)))
        (else (cons (car b) (merge a (cdr b))))))
(define (split l)
  (if (or (null? l) (null? (cdr l))) (cons l '())
      (let ((r (split (cdr (cdr l)))))
        (cons (cons (car l) (car r)) (cons (car (cdr l)) (cdr r))))))
(define (msort l)
  (if (or (null? l) (null? (cdr l))) l
      (let ((s (split l))) (merge (msort (car s)) (msort (cdr s))))))
(define (maximum l) (foldl (lambda (a x) (if (> x a) x a)) (car l) (cdr l)))
(define (insert-sorted x l) (cond ((null? l) (list x)) ((<= x (car l)) (cons x l)) (else (cons (car l) (insert-sorted x (cdr l))))))
"""


def _differential_lists(m):
    rng = random.Random(4242)
    for i in range(40):
        n = rng.choice([0, 1, 2, 3, 7, 20, 60, 150])
        data = [rng.randint(-50, 50) * (10 ** rng.choice([0, 0, 0, 20])) for _ in range(n)]
        lit = "(" + " ".join(map(str, data)) + ")"
        prog = _LISTLIB + f"""
        (define data '{lit})
        (display (qsort data)) (newline)
        (display (msort data)) (newline)
        (display (foldl (lambda (acc x) (insert-sorted x acc)) '() data)) (newline)
        (display (map (lambda (x) (modulo x 7)) data)) (newline)
        (display (filter (lambda (x) (< (remainder x 5) 0)) data)) (newline)
        (display (foldl + 0 data)) (display " ") (display (apply + data)) (display " ") (display (length data))
        (display " ") (display (if (null? data) 'none (maximum data)))
        """
        s = sorted(data)
        show = lambda l: "(" + " ".join(map(str, l)) + ")"
        rem5 = lambda x: x - 5 * _trunc_quot(x, 5)
        want = "\n".join([
            show(s), show(s), show(s), show([x % 7 for x in data]), show([x for x in data if rem5(x) < 0]),
            f"{sum(data)} {sum(data)} {n} {max(data) if data else 'none'}"])
        got = m.run(prog)
        assert got == want, f"data {lit}:\n got {got!r}\nwant {want!r}"


def test_randomized_differential(m):
    _differential_expressions(m)
    _differential_data(m)
    _differential_lists(m)


TESTS = [
    test_lexical_syntax_and_display, test_integer_arithmetic,
    test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation,
    test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling,
    test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply,
    test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential,
]
