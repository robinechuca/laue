#!/usr/bin/env python3

"""
** Permet de faire un pont entre le calcul symbolique et matriciel. **
----------------------------------------------------------------------

Est capable de metre en forme les expressions symbolique ``sympy`` de sorte
a maximiser les performances.

Notes
-----
Si le module ``numexpr`` est installe, certaines optimisations pouront etre faites.
"""

import numbers
import time

import numpy as np
import sympy

from laue.utilities.fork_lambdify import lambdify


__pdoc__ = {"cse_minimize_memory": False,
            "cse_homogeneous": False,
            "evalf": False,
            "simplify": False,
            "subs": False,
            "Lambdify.__getstate__": True,
            "Lambdify.__setstate__": True,
            "Lambdify.__call__": True,
            "Lambdify.__str__": True}

def cse_minimize_memory(r, e):
    """
    Return tuples giving ``(a, b)`` where ``a`` is a symbol and ``b`` is
    either an expression or None. The value of None is used when a
    symbol is no longer needed for subsequent expressions.

    Use of such output can reduce the memory footprint of lambdified
    expressions that contain large, repeated subexpressions.

    Examples
    --------
    >>> from sympy import cse
    >>> from laue.utilities.lambdify import cse_minimize_memory
    >>> from sympy.abc import x, y
    >>> eqs = [(x + y - 1)**2, x, x + y, (x + y)/(2*x + 1) + (x + y - 1)**2, (2*x + 1)**(x + y)]
    >>> defs, rvs = cse_minimize_memory(*cse(eqs))
    >>> for i in defs:
    ...     print(i)
    ...
    (x0, x + y)
    (x1, (x0 - 1)**2)
    (x2, 2*x + 1)
    (_3, x0/x2 + x1)
    (_4, x2**x0)
    (x2, None)
    (_0, x1)
    (x1, None)
    (_2, x0)
    (x0, None)
    (_1, x)
    >>> print(rvs)
    (_0, _1, _2, _3, _4)
    >>>
    """
    if not r:
        return r, e

    from sympy import symbols

    s, p = zip(*r)
    esyms = symbols('_:%d' % len(e))
    syms = list(esyms)
    s = list(s)
    in_use = set(s)
    p = list(p)
    # sort e so those with most sub-expressions appear first
    e = [(e[i], syms[i]) for i in range(len(e))]
    e, syms = zip(*sorted(e,
        key=lambda x: -sum([p[s.index(i)].count_ops()
        for i in x[0].free_symbols & in_use])))
    syms = list(syms)
    p += e
    rv = []
    i = len(p) - 1
    while i >= 0:
        _p = p.pop()
        c = in_use & _p.free_symbols
        if c: # sorting for canonical results
            rv.extend([(s, None) for s in sorted(c, key=str)])
        if i >= len(r):
            rv.append((syms.pop(), _p))
        else:
            rv.append((s[i], _p))
        in_use -= c
        i -= 1
    rv.reverse()
    return rv, esyms

def cse_homogeneous(exprs, **kwargs):
    """
    Same as ``cse`` but the ``reduced_exprs`` are returned
    with the same type as ``exprs`` or a sympified version of the same.

    Parameters
    ----------
    exprs : an Expr, iterable of Expr or dictionary with Expr values
        the expressions in which repeated subexpressions will be identified
    kwargs : additional arguments for the ``cse`` function

    Returns
    -------
    replacements : list of (Symbol, expression) pairs
        All of the common subexpressions that were replaced. Subexpressions
        earlier in this list might show up in subexpressions later in this
        list.
    reduced_exprs : list of sympy expressions
        The reduced expressions with all of the replacements above.

    Examples
    --------
    >>> from sympy.simplify.cse_main import cse
    >>> from sympy import cos, Tuple, Matrix
    >>> from sympy.abc import x
    >>> from laue.utilities.lambdify import cse_homogeneous
    >>> output = lambda x: type(cse_homogeneous(x)[1])
    >>> output(1)
    <class 'sympy.core.numbers.One'>
    >>> output('cos(x)')
    <class 'str'>
    >>> output(cos(x))
    cos
    >>> output(Tuple(1, x))
    <class 'sympy.core.containers.Tuple'>
    >>> output(Matrix([[1,0], [0,1]]))
    <class 'sympy.matrices.dense.MutableDenseMatrix'>
    >>> output([1, x])
    <class 'list'>
    >>> output((1, x))
    <class 'tuple'>
    >>> output({1, x})
    <class 'set'>
    """
    from sympy import cse
    if isinstance(exprs, str):
        from sympy import sympify
        replacements, reduced_exprs = cse_homogeneous(
            sympify(exprs), **kwargs)
        return replacements, repr(reduced_exprs)
    if isinstance(exprs, (list, tuple, set)):
        replacements, reduced_exprs = cse(exprs, **kwargs)
        return replacements, type(exprs)(reduced_exprs)
    if isinstance(exprs, dict):
        keys = list(exprs.keys()) # In order to guarantee the order of the elements.
        replacements, values = cse([exprs[k] for k in keys], **kwargs)
        reduced_exprs = dict(zip(keys, values))
        return replacements, reduced_exprs

    try:
        replacements, (reduced_exprs,) = cse(exprs, **kwargs)
    except TypeError: # For example 'mpf' objects
        return [], exprs
    else:
        return replacements, reduced_exprs

def evalf(x, n=15):
    """
    ** Alias vers ``sympy.N``. **

    Gere recursivement les objets qui n'ont pas
    de methodes ``evalf``.
    """
    if isinstance(x, (sympy.Atom, numbers.Number)):
        if str(x) == "pi":
            return sympy.pi.evalf(n=n)
        if str(x) == "E":
            return sympy.E.evalf(n=n)
        return x
    try:
        if isinstance(x, (tuple, list, set)):
            x = type(x)([evalf(e, n=n) for e in x])
        else:
            x = type(x)(*(evalf(e, n=n) for e in x.args))
    except AttributeError:
        pass
    try:
        return sympy.N(x, n=n)
    except AttributeError:
        return x

def simplify(x, **kwargs):
    """
    ** Alias vers ``sympy.simplify``. **

    Gere recursivement les objets qui n'ont pas
    de methodes pour etre directement simplifiables.

    Ajoute une factorisation recursive afin de privilegier
    les "*" plutot que les "+" de sorte a reduire les erreurs
    de calcul.
    """
    for _ in range(2):
        try:
            new_x = sympy.simplify(sympy.factor(x, deep=True, fraction=False), **kwargs)
        except AttributeError:
            if isinstance(x, (tuple, list, set)):
                new_x = type(x)([simplify(e, **kwargs) for e in x])
            else:
                new_x = type(x)(*(simplify(e, **kwargs) for e in x.args))

        if str(new_x) == str(x):
            break
        x = new_x
    return new_x

def subs(x, replacements):
    """
    ** Alias vers ``sympy.subs``. **

    Gere recursivement les objets qui n'ont pas de methode ``.subs``.
    """
    try:
        return x.subs(replacements)
    except AttributeError:
        if isinstance(x, (tuple, list, set)):
            return type(x)([subs(e, replacements) for e in x])
        return type(x)(*(subs(e, replacements) for e in x.args))

def time_cost(x):
    """
    ** Estime la complexite d'une expression. **

    Cela est tres utile pour ``sympy.simplify`` concernant
    l'argument ``measure``. Cette metrique permet de minimiser
    le temps de calcul plutot que l'elegence de l'expression.
    """
    defs, rvs = cse_minimize_memory(*sympy.cse(x))
    return sum(sympy.count_ops(expr) for var, expr in defs) + len(defs)


class Lambdify:
    """
    ** Permet de manipuler plus simplement une fonction. **
    """
    def __init__(self, args, expr, *, _simplify=True):
        """
        ** Prepare la fonction. **

        Parameters
        ----------
        args : iterable
            Les parametres d'entre de la fonction.
        expr : sympy.core
            L'expresion sympy a vectoriser.
        """
        # Preparation symbolique.
        self.args = [arg for arg in sympy.sympify(args)]
        self.args_name = [str(arg) for arg in self.args]
        self.args_position = {arg: i for i, arg in enumerate(self.args_name)}
        self.expr = expr

        # Preparation vectoriele.
        if _simplify:
            self.expr = evalf(
                simplify(
                    self.expr,
                    measure=time_cost,
                    inverse=True,
                    rational=False
                ),
                n=30
            )
        self.fct = lambdify(self.args, self.expr, cse=True, modules="numpy")
        try:
            self.fct_numexpr = lambdify(self.args, evalf(self.expr, n=15), cse=True, modules="numexpr")
        except (ImportError, TypeError, RuntimeError):
            self.fct_numexpr = None

    def __str__(self, name="lambdifygenerated"):
        '''
        ** Offre une representation explicite de la fonction. **

        Parameters
        ----------
        name : str
            Le nom a donner a la fonction.

        Examples
        --------
        >>> from sympy.abc import x, y; from sympy import cos, pi
        >>> from laue.utilities.lambdify import Lambdify
        >>>
        >>> print(Lambdify([x, y], pi*cos(x + y) + x + y), end="")
        def _lambdifygenerated_numexpr(x, y):
            """Perform calculations in float64 using the numexpr module."""
            from numexpr import evaluate
            x0 = evaluate('x + y', truediv=True)
            _0 = evaluate('x0 + 3.14159265358979*cos(x0)', truediv=True)
            return _0
        <BLANKLINE>
        def _lambdifygenerated_numpy(x, y):
            """Perform calculations in small float using the numpy module."""
            from numpy import *
            x0 = x + y
            _0 = x0 + 3.14159265358979*cos(x0)
            return _0
        <BLANKLINE>
        def _lambdifygenerated_numpy128(x, y):
            """Perform calculations in float128 using the numpy module."""
            from numpy import *
            x0 = x + y
            _0 = x0 + float128('3.14159265358979323846264338328')*cos(x0)
            return _0
        <BLANKLINE>
        def _lambdifygenerated_sympy():
            """Returns the tree of the sympy expression."""
            from sympy import *
            x, y = symbols('x y')
            return x + y + 3.14159265358979323846264338328*cos(x + y)
        <BLANKLINE>
        def lambdifygenerated(*args, **kwargs):
            """
            ** Choose the most suitable function according to
            the type and size of the input data. **
        <BLANKLINE>
            Parameters
            ----------
            *args
                Les parametres ordonnes de la fonction.
            **kwargs
                Les parametres nomes de la fonction. Ils
                ont le dessus sur les args en cas d'ambiguite.
            """
            assert len(args) <= 2, f'The function cannot take {len(args)} arguments.'
            assert not set(kwargs) - {'x', 'y'}, f'You cannot provide {kwargs}.'
            import sympy
            if not args and not kwargs:
                return _lambdifygenerated_sympy()
            args = list(args)
            if len(args) < 2:
                args += sympy.symbols(' '.join(['x', 'y'][len(args):]))
            if kwargs:
                for arg, value in kwargs.items():
                    args[{'x': 0, 'y': 1}[arg]] = value
            if any(isinstance(a, sympy.Basic) for a in args):
                sub = {arg: value for arg, value in zip(['x', 'y'], args)}
                from laue.utilities.lambdify import subs
                return subs(_lambdifygenerated_sympy(), sub)
            if any(a.dtype == np.float128 for a in args if isinstance(a, np.ndarray)):
                return _lambdifygenerated_numpy128(*args)
            import numpy as np
            if (
                    (max((a.size for a in args if isinstance(a, np.ndarray)), default=0) >= 157741)
                    and all(a.dtype == np.float64 for a in args if isinstance(a, np.ndarray))
                ):
                return _lambdifygenerated_numexpr(*args)
            return _lambdifygenerated_numpy(*args)
        >>>
        '''
        assert isinstance(name, str), f"'name' has to be str, not {type(name).__name__}."
        import re

        # Code numexpr.
        if self.fct_numexpr is not None:
            code = self.fct_numexpr.__doc__.split("\n")
            code[0] = code[0].replace("_lambdifygenerated", f"_{name}_numexpr")
            code.insert(1, '    """Perform calculations in float64 using the numexpr module."""')
            code.insert(2, "    from numexpr import evaluate")
        else:
            code = []

        # Code < float 64
        new_code = lambdify(self.args, evalf(self.expr, n=15), cse=True, modules="numpy").__doc__.split("\n")
        new_code[0] = new_code[0].replace("_lambdifygenerated", f"_{name}_numpy")
        new_code.insert(1, '    """Perform calculations in small float using the numpy module."""')
        new_code.insert(2, "    from numpy import *")
        code.extend(new_code)

        # Code float 128
        f_mod = re.compile(r"""(?:[+-]*
            (?:
              \. [0-9]+ (?:_[0-9]+)*
              (?: e [+-]? [0-9]+ (?:_[0-9]+)* )?
            | [0-9]+ (?:_[0-9]+)* \. (?: [0-9]+ (?:_[0-9]+)* )?
              (?: e [+-]? [0-9]+ (?:_[0-9]+)* )?
            | [0-9]+ (?:_[0-9]+)*
              e [+-]? [0-9]+ (?:_[0-9]+)*
            ))""", re.VERBOSE | re.IGNORECASE) # Model d'un flottant.
        new_code_str = self.fct.__doc__
        new_code_str = re.sub(f_mod, lambda m: f"float128({repr(m.group())})", new_code_str)
        new_code = new_code_str.split("\n")
        new_code[0] = new_code[0].replace("_lambdifygenerated", f"_{name}_numpy128")
        new_code.insert(1, '    """Perform calculations in float128 using the numpy module."""')
        new_code.insert(2, "    from numpy import *")
        code.extend(new_code)

        # Expression formelle
        code.append(f"def _{name}_sympy():")
        code.append( '    """Returns the tree of the sympy expression."""')
        code.append( "    from sympy import *")
        code.append(f"    {', '.join(self.args_name)} = symbols('{' '.join(self.args_name)}')")
        code.append(f"    return {self.expr}")
        code.append( "")

        # Fonction principale Equivalent as self.__call__.
        code.append(f"def {name}(*args, **kwargs):")
        code.append( '    """')
        code.append( "    ** Choose the most suitable function according to")
        code.append( "    the type and size of the input data. **")
        code.append( "")
        code.append( "    Parameters")
        code.append( "    ----------")
        code.append( "    *args")
        code.append( "        Les parametres ordonnes de la fonction.")
        code.append( "    **kwargs")
        code.append( "        Les parametres nomes de la fonction. Ils")
        code.append( "        ont le dessus sur les args en cas d'ambiguite.")
        code.append( '    """')

        code.append( "    assert len(args) <= %d, f'The function cannot take {len(args)} arguments.'" % len(self.args))
        code.append( "    assert not set(kwargs) - {%s}, f'You cannot provide {kwargs}.'" % ", ".join(self.args_position))
        code.append( "    import sympy")
        code.append( "    if not args and not kwargs:")
        code.append(f"        return _{name}_sympy()")

        code.append( "    args = list(args)")
        code.append(f"    if len(args) < {len(self.args)}:")
        code.append(f"        args += sympy.symbols(' '.join({self.args_name}[len(args):]))")
        code.append( "    if kwargs:")
        code.append( "        for arg, value in kwargs.items():")
        code.append(f"            args[{self.args_position}[arg]] = value")

        code.append( "    if any(isinstance(a, sympy.Basic) for a in args):")
        code.append( "        sub = {arg: value for arg, value in zip(%s, args)}" % self.args_name)
        code.append( "        from laue.utilities.lambdify import subs")
        code.append(f"        return subs(_{name}_sympy(), sub)")

        if hasattr(np, "float128"):
            if self.fct_numexpr is None:
                code.append( "    import numpy as np")
            code.append( "    if any(a.dtype == np.float128 for a in args if isinstance(a, np.ndarray)):")
            code.append(f"        return _{name}_numpy128(*args)")
        if self.fct_numexpr is not None:
            code.append( "    import numpy as np")
            code.append( "    if (")
            code.append( "            (max((a.size for a in args if isinstance(a, np.ndarray)), default=0) >= 157741)")
            code.append( "            and all(a.dtype == np.float64 for a in args if isinstance(a, np.ndarray))")
            code.append( "        ):")
            code.append(f"        return _{name}_numexpr(*args)")
        code.append(f"    return _{name}_numpy(*args)")

        code.append( "")
        return "\n".join(code)

    def __repr__(self):
        """
        ** Offre une representation evaluable de l'objet. **

        Examples
        --------
        >>> from sympy.abc import x, y; from sympy import cos
        >>> from laue.utilities.lambdify import Lambdify
        >>>
        >>> Lambdify([x, y], cos(x + y) + x + y)
        Lambdify([x, y], x + y + cos(x + y))
        >>>
        """
        return f"Lambdify([{', '.join(self.args_name)}], {self.expr})"

    def __call__(self, *args, **kwargs):
        """
        ** Evalue la fonction. **

        Parameters
        ----------
        *args
            Les parametres ordonnes de la fonction.
        **kwargs
            Les parametres nomes de la fonction. Ils
            ont le dessus sur les args en cas d'ambiguite.

        Examples
        --------
        >>> from sympy.abc import x, y; from sympy import cos
        >>> from laue.utilities.lambdify import Lambdify
        >>> l = Lambdify([x, y], x + y + cos(x + y))

        Les cas symboliques.
        >>> l() # Retourne l'expression sympy.
        x + y + cos(x + y)
        >>> l(x) # Complete la suite en rajoutant 'y'.
        x + y + cos(x + y)
        >>> l(y) # Complete aussi en rajoutant 'y'.
        2*y + cos(2*y)
        >>> l(x, y) # Retourne une copie de l'expression sympy.
        x + y + cos(x + y)
        >>> l(1, y=2*y) # Il est possible de faire un melange symbolique / numerique.
        2*y + cos(2*y + 1) + 1
        >>>

        Les cas purement numeriques.
        >>> import numpy as np
        >>> l(-1, 1)
        1.0
        >>> l(x=-1, y=1)
        1.0
        >>> np.round(l(0, np.linspace(-1, 1, 5)), 2)
        array([-0.46,  0.38,  1.  ,  1.38,  1.54])
        >>>
        """
        # Cas patologiques.
        if not args and not kwargs:
            return self.expr
        if len(args) > len(self.args):
            raise IndexError(f"La fonction ne prend que {len(self.args)} arguments. "
                f"Or vous en avez fournis {len(args)}.")
        
        # Recuperation des arguments complets.
        args = list(args)
        args += self.args[len(args):]
        if kwargs:
            if set(kwargs) - set(self.args_position):
                raise NameError(f"Les parametres {set(kwargs) - set(self.args_position)} "
                    f"ne sont pas admissible, seul {set(self.args_position)} sont admissibles.")
            for arg, value in kwargs.items():
                args[self.args_position[arg]] = value

        # Cas symbolique.
        if any(isinstance(a, sympy.Basic) for a in args):
            sub = {arg: value for arg, value in zip(self.args, args)}
            return subs(self.expr, sub)

        # Cas numerique.
        if (
                (self.fct_numexpr is not None)
                and (max((a.size for a in args if isinstance(a, np.ndarray)), default=0) >= 157741)
                and all(a.dtype == np.float64 for a in args if isinstance(a, np.ndarray))
            ):
            return self.fct_numexpr(*args)
        return self.fct(*args)

    def __getstate__(self):
        """
        ** Extrait l'information serialisable. **

        Examples
        --------
        >>> from sympy.abc import x, y; from sympy import cos
        >>> from laue.utilities.lambdify import Lambdify
        >>>
        >>> l = Lambdify([x, y], cos(x + y) + x + y)
        >>> l.__getstate__()
        {'args': [x, y], 'expr': x + y + cos(x + y)}
        >>>
        """
        return {"args": self.args,
                "expr": self.expr}

    def __setstate__(self, state):
        """
        ** Instancie l'objet a partir de l'etat. **

        Examples
        --------
        >>> import pickle
        >>> from sympy.abc import x, y; from sympy import cos
        >>> from laue.utilities.lambdify import Lambdify
        >>>
        >>> l = Lambdify([x, y], cos(x + y) + x + y)
        >>> l
        Lambdify([x, y], x + y + cos(x + y))
        >>> pickle.loads(pickle.dumps(l))
        Lambdify([x, y], x + y + cos(x + y))
        >>>
        """
        self.__init__(state["args"], state["expr"], _simplify=False)