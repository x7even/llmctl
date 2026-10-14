Write a Python module that implements an interpreter for a small, precisely specified Scheme subset. Standard library only. Do not use `eval`, `exec` or `compile` to run the Scheme code (write a real reader and evaluator).

## Public API

```python
class SchemeError(Exception):
    output: str          # text written by display/newline before the error; default ''

def run(source: str) -> str: ...
```

`run(source)` creates a **fresh global environment** (nothing is shared between two calls to `run`), reads the whole `source`, then evaluates the top-level forms one after another, in order. It returns the concatenation of all text written by `display` and `newline` (nothing else is ever added to the output; the value of a top-level form is discarded and never printed; do not write to stdout).

If anything goes wrong, `run` raises `SchemeError` (and never any other exception type: no `TypeError`, `KeyError`, `ZeroDivisionError`, `RecursionError`, ... may leak out for any of the error situations listed below). The raised exception's `.output` attribute is a `str` holding all text written by `display`/`newline` **up to the moment of the error** (it is `''` if nothing was written). `str(exc)` is the human-readable message; its content is unspecified except for errors raised by the Scheme `error` procedure (see below).

## Lexical syntax and reader

* Whitespace (space, tab, `\n`, `\r`) separates tokens. `;` starts a comment that runs to the end of the line (but a `;` inside a string literal is part of the string).
* `(` and `)` delimit lists. `[` and `]` are **not** parentheses; they are ordinary symbol characters (so `[a` is a symbol).
* A token ends at whitespace or at any of `( ) " ; '`. Those characters never occur inside a symbol or number.
* **Integers**: a token is an integer **if and only if** it matches `[+-]?[0-9]+` completely (ASCII digits only). `-5`, `+5`, `007` are integers (-5, 5, 7). `-`, `+`, `1+`, `-x`, `1_000`, `.5`, `1.5`, `...` are **symbols** (there are no floating point numbers). Integers have arbitrary precision.
* `#t` and `#f` are the booleans. Any other token starting with `#` is a syntax error.
* **Strings** are written in double quotes. The only escapes are `\"`, `\\` and `\n` (newline); any other backslash escape is a syntax error. A string may contain raw newlines, parentheses and semicolons. An unterminated string is a syntax error.
* **Symbols** are all other tokens, case-sensitive (`Foo` and `foo` differ).
* `'x` is shorthand for `(quote x)`, for any datum `x` (`''a` is `(quote (quote a))`). A `'` that is not followed by a datum is a syntax error.
* A list may be written in dotted form: `(1 . 2)`, `(1 2 . 3)`, `(1 . (2 3))` (the last equals `(1 2 3)`). The dot must be a token consisting of exactly `.`, must be preceded by at least one element, and followed by exactly one datum and then `)`; anything else is a syntax error. `()` is the empty list.
* An unbalanced `(` or `)` is a syntax error.
* The **whole** source is read before anything is evaluated. If there is any syntax error, `run` raises `SchemeError` with `.output == ''` without evaluating any form. An empty or comment-only source is valid and yields `''`.

## Data types

integers (arbitrary precision), booleans, strings (immutable), symbols, pairs/lists, the empty list `()`, procedures (closures and builtins), and a special *unspecified* value (see below). Booleans are **not** numbers (`(number? #t)` is `#f`, `(+ 1 #t)` is an error). Strings and symbols are different types.

**Truthiness: only `#f` is false.** Everything else is true, including `0`, `()`, `""` and the unspecified value.

## Evaluation

* Integers, strings and booleans evaluate to themselves. A symbol evaluates to the value of the variable it names (innermost binding first, then global). Referencing an unbound variable is an error. Global variables are looked up when a reference is evaluated, so a function may refer to a global defined later.
* `()` evaluated unquoted, and any non-empty form whose head is not a special form, is a procedure application. A dotted form used as an application is an error.
* **Application order**: first the operator expression is evaluated, then the operand expressions **left to right**, and only then is it checked that the operator value is a procedure (otherwise error) and that the argument count is acceptable (otherwise error), and then the procedure is called. So in `(5 (display "x"))` the `x` is written before the error is raised.
* Procedures: `(lambda formals body...)`. `formals` is either a proper list of symbols (fixed arity), a dotted list `(a b . rest)` (at least 2 arguments, the remaining ones collected into a fresh list bound to `rest`, which is `()` if none), or a lone symbol `args` (any number of arguments, all collected into a list). A closure called with a wrong number of arguments is an error. Closures capture their defining environment (lexical scope) and variables are shared, not copied, so mutation by `set!` is visible to every closure that captured the variable. **Every call creates a fresh set of parameter bindings** (closures created in different iterations of a loop do not share parameters).
* A *body* is a non-empty sequence of forms; its value is the value of the last form. A body that is empty is a malformed form.
* The *unspecified value* is what `display`, `newline`, `set!`, `define`, an `if` without alternative whose test is false, and a `cond` in which no clause matched return. When `display` prints it, it prints nothing (the empty string) - also inside a list.

### Special forms

All of these are recognised by the head symbol being the keyword (local variables never use a keyword as their name in the tests). A malformed special form (wrong shape, e.g. `(if)`, `(lambda)`, `(let ((x)) x)`, `(define)`, `(begin)`, `(quote)`, a non-symbol where a variable is required) raises `SchemeError` when it is **evaluated** (tests only contain malformed forms that are actually reached).

* `(quote datum)`: the datum, unevaluated. Quoted lists are ordinary lists/pairs, quoted symbols are symbols.
* `(if test then)` / `(if test then else)`.
* `(define name expr)` and `(define (name . formals) body...)` (the latter is `(define name (lambda formals body...))`; `formals` may be dotted or a lone symbol as for `lambda`, e.g. `(define (f . args) ...)`). At top level `define` creates or overwrites a global variable (including redefining a builtin such as `length` or `append`; user definitions take effect for later code, and must not change the behaviour of other builtins). Inside a body see "Internal definitions".
* `(set! name expr)`: `expr` is evaluated first, then the innermost existing binding of `name` is updated; if `name` is not bound anywhere, error.
* `(begin e1 e2 ...)`: evaluates in order, value of the last. A `begin` at top level may contain `define`s, which then define globals.
* `(cond clause...)` where a clause is `(test e1 e2 ...)`, `(test)` or `(else e1 e2 ...)` (`else` only as the last clause). Clauses are tried in order; for the first whose test is true, the `e`s are evaluated in order and the value of the last is the result; for `(test)` with no expressions the result is the value of the test itself. If no clause matches and there is no `else`, the result is unspecified. (`=>` is not supported.)
* `(and e ...)`: evaluates left to right and stops at the first `#f` (returning `#f`); otherwise returns the value of the last expression; `(and)` is `#t`. `(or e ...)`: stops at the first true value and returns that value; if none, `#f`; `(or)` is `#f`.
* `(let ((v init) ...) body...)`: all `init`s are evaluated left to right **in the outer scope**, then bound simultaneously. `(let () body...)` is allowed.
* `(let* ((v init) ...) body...)`: sequential; each `init` sees the earlier bindings.
* `(letrec ((v init) ...) body...)`: all `v` are in scope in all `init`s; the `init`s are evaluated in order. Reading a `letrec` variable before its `init` has been evaluated is an error (`(letrec ((a b) (b 1)) a)` is an error, `(letrec ((f (lambda () g)) (g 2)) (f))` is `2`).
* Named let: `(let name ((v init) ...) body...)` is like a `letrec`-bound procedure `name` taking `v ...`, called with the `init` values. The `init`s are evaluated left to right in the **outer** scope (so `name` is not visible in them); `name` is visible in the body only. Each iteration (call of `name`) gets fresh bindings of the `v`s.

### Internal definitions

The body of `lambda`, `define`, `let`, `let*`, `letrec` and named `let` may contain `(define ...)` forms directly among its forms (not nested inside `if`, `begin`, etc.), at any position. They have `letrec*` semantics: all names defined directly in a body are bound in a scope that covers the **entire** body, and the definitions are executed in order when evaluation reaches them. Consequently inner functions can be mutually recursive, and **reading such a variable before its `define` has been executed is an error, even if a global of the same name exists** (e.g. `(define (f) (display x) (define x 1) x)` with a global `x` raises `SchemeError`). Internal definitions are local to their body: they are invisible after it returns. (Duplicate names in one body or between parameters and internal definitions are not tested.)

### Tail calls (mandatory)

The following are tail positions, and a procedure call in a tail position must not grow the Python call stack or any other structure in proportion to the number of such calls:

* the body of a closure: its last form;
* both branches of `if`; the last expression of the chosen `cond` clause (also `else`); the last expression of `and` and of `or`; the last form of `begin`; the last form of the body of `let`, `let*`, `letrec` and named `let`;
* a call to `apply`: `(apply f args...)` in a tail position calls `f` as a tail call.

Therefore a tail-recursive loop of 300000 iterations, and mutual tail recursion (`even?`/`odd?` written in Scheme) to depth 200000, must run correctly using constant stack. Non-tail recursion must also work to a depth of at least 5000 nested Scheme calls (for example building a list recursively with `(cons x (recur ...))`, or `(+ 1 (f (- n 1)))`); you may raise the Python recursion limit, run the evaluator in a thread with a large stack, or use an explicit stack - the tests run in a normal Python process, and your module must not crash it. (Unbounded recursion is not tested.) Lists of 100000 elements must be supported by `length`, `reverse`, `append`, `list?`, `equal?` and `display` without hitting recursion limits.

## Builtins

All builtins are ordinary global variables holding procedures; they can be passed around, put in lists, called through `apply`, and redefined or shadowed by user code. Calling a builtin with the wrong number of arguments, or with arguments of the wrong type, raises `SchemeError` (after all arguments are evaluated). Arity is given below.

**Numbers** (all arguments must be integers, not booleans):
* `+` (0 or more; `(+)` is 0), `*` (0 or more; `(*)` is 1), `-` (1 or more; one argument negates, otherwise subtracts the rest from the first from left to right).
* `quotient`, `remainder`, `modulo` (exactly 2 integers). `quotient` truncates toward zero; `remainder` has the sign of the dividend (first argument); `modulo` has the sign of the divisor (second argument): `(quotient -7 2)` = -3, `(remainder -7 2)` = -1, `(modulo -7 2)` = 1, `(quotient 7 -2)` = -3, `(remainder 7 -2)` = 1, `(modulo 7 -2)` = -1. A zero second argument raises `SchemeError`. These must be exact for arbitrarily large integers.
* `=`, `<`, `>`, `<=`, `>=`: **one or more** arguments, chained: `(< a b c)` is true iff `a<b` and `b<c`; with a single argument the result is `#t`. All arguments are evaluated and type-checked before comparing (`(< 3 2 'a)` is an error, not `#f`). Zero arguments is an error. The result is a boolean.
* `(number->string n)` and `(number->string n radix)`: decimal text of the integer (`-42` for negatives); radix may be 2, 8, 10 or 16 (lowercase hex digits, negative numbers as `-ff`); any other radix, or a non-integer argument, is an error. Integers of any size must print in full (for example the 5736-digit value of `2000!` must be displayed completely and correctly - note that recent CPython versions limit `int`-to-`str` conversion to 4300 digits by default).

**Lists and pairs:**
* `(cons a b)`; `(car p)`, `(cdr p)` (1 argument; error if not a pair, including `()`); `(list x ...)` (0 or more).
* `(null? x)`, `(pair? x)`, `(list? x)`: `list?` is true only for proper lists (`()` and chains of pairs ending in `()`).
* `(length l)`: length of a proper list; error otherwise.
* `(append l ...)`: 0 or more arguments; all but the last must be proper lists (error otherwise); the last argument may be any object and is shared, not copied (`(append '(1) 2)` is `(1 . 2)`, `(append)` is `()`, `(append '() x)` is `x`, the very same object).
* `(reverse l)`: proper list required, else error.
* `(apply f a ... lst)`: at least 2 arguments; calls `f` with the arguments `a ...` followed by the elements of the proper list `lst`; error if `lst` is not a proper list.

**Equality and predicates:**
* `(eq? a b)`: same symbol; equal integers (compared by value, even huge ones); same boolean; both `()`; otherwise object identity (for pairs, strings and procedures: `(eq? (list 1) (list 1))` is `#f`, `(let ((p (list 1))) (eq? p p))` is `#t`). `(eq? "abc" (string-append "ab" "c"))` is `#f`. Comparing two separate string literals with `eq?` is not tested.
* `(equal? a b)`: like `eq?` for atoms, but strings are equal if they have the same characters, and pairs are equal if their cars and cdrs are `equal?` (structural, any length of list). An integer is never `equal?` to a boolean (`(equal? 1 #t)` and `(equal? 0 #f)` are `#f`), a symbol is never `equal?` to a string with the same characters, and procedures are equal only if identical.
* `(not x)`: `#t` iff `x` is `#f`.
* `(number? x)` (integers only), `(symbol? x)`, `(string? x)`, `(procedure? x)` (true for closures and builtins).
* `(string-append s ...)`: 0 or more strings; any non-string argument is an error.

**Output and errors:**
* `(display x)` (exactly 1 argument): appends the text representation of `x` to the output (see below); `(newline)` (0 arguments) appends `"\n"`.
* `(error msg irritant ...)`: at least one argument; `msg` must be a string (otherwise it is still a `SchemeError`, with any message). It raises `SchemeError` whose `str()` is `msg` followed, for each irritant, by a single space and the **write representation** of the irritant: `(error "bad thing:" 42 "str" '(a "b"))` gives the message `bad thing: 42 "str" (a "b")`.

## Text representation

`display` prints:
* integers in decimal (`-5`), `#t` / `#f`, strings as their raw characters (no quotes, no escaping), symbols as their name, `()` for the empty list;
* a procedure (closure or builtin) as `#<procedure>`;
* the unspecified value as the empty string;
* a pair as `(` elements separated by single spaces `)`; for a chain of pairs ending in `()` this is a normal list `(1 2 3)`; if the chain ends in some other object `x`, then ` . ` and the representation of `x` precede the closing parenthesis: `(1 2 . 3)`, `(1 . 2)`. Nested lists are printed recursively: `(1 (2 3) () . 4)`. Strings inside lists are printed raw, too: `(display '("a" b))` prints `(a b)`.
* There is no abbreviation for quote forms: `(display ''a)` prints `(quote a)` and `(display '(1 'b))` prints `(1 (quote b))`.

The *write representation* (used only for `error` irritants) is the same, except that **every** string, at any nesting depth, is printed in double quotes with `"` written as `\"`, `\` as `\\` and a newline as `\n`.

## Examples

```scheme
(define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))
(display (fact 20)) (newline)            ; prints 2432902008176640000 and a newline
(display '(1 (2 . 3) "x" y #t))          ; prints (1 (2 . 3) x y #t)
(define (make-counter)
  (let ((n 0)) (lambda () (set! n (+ n 1)) n)))
(define c (make-counter)) (c) (c)
(display (c))                            ; prints 3
(display (car '()))                      ; raises SchemeError (output so far is kept in .output)
```

Output requirements: reply with **one** Python code block containing the complete module. No explanation outside the code block.
