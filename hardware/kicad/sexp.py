"""A small reader and writer for KiCad's s-expression files.

A parsed file is nested Python lists. Unquoted tokens (symbols and numbers) are `Sym`, quoted
strings are plain `str`, so the two never compare equal and `dump()` can put the quotes back.
"""
import re

_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')
_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "r": "\r"}


class Sym(str):
    """An unquoted token: a keyword, a number, a bare identifier."""
    __slots__ = ()

    def __eq__(self, other):
        return type(other) is Sym and str.__eq__(self, other)

    def __ne__(self, other):
        return not self.__eq__(other)

    __hash__ = str.__hash__

    def __repr__(self):
        return f"Sym({str.__repr__(self)})"


def _unescape(body):
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), body)


def _escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")


def parse(text):
    """Parse one top-level list and return it."""
    stack = [[]]
    for m in _TOKEN.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            if not stack:
                raise ValueError("unbalanced ')'")
            stack[-1].append(done)
        elif t[0] == '"':
            stack[-1].append(_unescape(t[1:-1]))
        else:
            stack[-1].append(Sym(t))
    if len(stack) != 1:
        raise ValueError("unbalanced '('")
    if len(stack[0]) != 1:
        raise ValueError(f"expected one top-level list, found {len(stack[0])}")
    return stack[0][0]


def _atom(a):
    return str(a) if isinstance(a, Sym) else '"' + _escape(a) + '"'


def dump(node, depth=0):
    """Write a node the way KiCad does: one list per line, tabs, atoms-only lists inline."""
    if not isinstance(node, list):
        return _atom(node)
    if all(not isinstance(x, list) for x in node):
        return "(" + " ".join(_atom(x) for x in node) + ")"
    out = []
    head = []
    i = 0
    while i < len(node) and not isinstance(node[i], list):
        head.append(_atom(node[i]))
        i += 1
    out.append("(" + " ".join(head))
    pad = "\t" * (depth + 1)
    for x in node[i:]:
        out.append("\n" + pad + dump(x, depth + 1))
    out.append("\n" + "\t" * depth + ")")
    return "".join(out)


def find(node, head):
    """The first child list whose first atom is `head`, or None."""
    for x in node:
        if isinstance(x, list) and x and isinstance(x[0], Sym) and str.__eq__(x[0], head):
            return x
    return None


def find_all(node, head):
    """Every child list whose first atom is `head`."""
    return [x for x in node if isinstance(x, list) and x and isinstance(x[0], Sym) and str.__eq__(x[0], head)]
