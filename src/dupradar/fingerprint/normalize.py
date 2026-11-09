"""Core fingerprinting normalization: AST -> structure-only SHA256 hash.

Goal (see the project spec for the full algorithm): two functions hash
IDENTICALLY iff they have the same logic, REGARDLESS of the function's own
name, parameter names, local variable names, docstrings, formatting, type
annotations, and literal constant VALUES. They hash DIFFERENTLY if control
flow / statement structure / called-function-or-attribute names differ.

This module is pure `ast` + stdlib -- no file I/O, no pydantic, no MCP --
so it is directly unit-testable against hand-built `ast` nodes or source
snippets.

Algorithm, in order:
  1. `copy.deepcopy` the function node (the ORIGINAL is never mutated).
  2. Collect local names in first-appearance order: params first (signature
     order: posonlyargs, args, vararg, kwonlyargs, kwarg), then every
     Name(Store) encountered walking the body in document order -- a nested
     def/async def/lambda's OWN parameters are skipped, but its body is
     still walked (so references to already-known outer locals, and the
     nested scope's own body-level names, are still found and normalized;
     see `_collect_local_names` for why this keeps the outer function's hash
     insensitive to a nested scope's naming too).
  3. Rewrite every `Name`/`arg` whose identifier is a key in that map to its
     placeholder (`VAR0`, `VAR1`, ...). `Attribute.attr` is never touched
     (e.g. `match` in `re.match(...)` stays `match` -- real structural
     signal). Names not in the map (globals/imports/builtins/other function
     names) are left untouched -- also real structural signal.
  4. Replace every `Constant` by its type: bool -> "BOOL_LIT" (checked
     BEFORE int/float, since `bool` is an `int` subclass), str -> "STR_LIT",
     int/float -> "NUM_LIT". `None`/`Ellipsis` (and anything else, e.g.
     bytes/complex) are left as-is.
  5. Drop a leading docstring statement, if any.
  6. Clear `name`, `decorator_list`, `returns`, and every arg's `annotation`
     -- none of these should affect the hash.
  7. `fingerprint_hash = sha256(ast.dump(node, annotate_fields=False))`.
     `token_count = len(dumped.split())`. `param_count` is computed from the
     ORIGINAL (pre-normalization) node.
"""

from __future__ import annotations

import ast
import copy
import hashlib
from dataclasses import dataclass

from dupradar.fingerprint.models import FunctionDefNode

# Scopes whose OWN parameter list must never be harvested as an outer
# local, during local-name collection (step 2 above).
_NESTED_SCOPE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


@dataclass(frozen=True)
class NormalizedFunction:
    """Result of normalizing+hashing one function node."""

    fingerprint_hash: str
    token_count: int
    param_count: int


def _ordered_param_names(args: ast.arguments) -> list[str]:
    """Every `ast.arg.arg` across posonlyargs/args/vararg/kwonlyargs/kwarg,
    in signature order."""
    names = [a.arg for a in (*args.posonlyargs, *args.args)]
    if args.vararg is not None:
        names.append(args.vararg.arg)
    names.extend(a.arg for a in args.kwonlyargs)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    return names


def _all_args(args: ast.arguments) -> list[ast.arg]:
    """Every `ast.arg` node across posonlyargs/args/vararg/kwonlyargs/kwarg."""
    result = [*args.posonlyargs, *args.args]
    if args.vararg is not None:
        result.append(args.vararg)
    result.extend(args.kwonlyargs)
    if args.kwarg is not None:
        result.append(args.kwarg)
    return result


def _param_count(args: ast.arguments) -> int:
    """len(posonlyargs+args+kwonlyargs) + 1 if vararg + 1 if kwarg."""
    return (
        len(args.posonlyargs)
        + len(args.args)
        + len(args.kwonlyargs)
        + (1 if args.vararg is not None else 0)
        + (1 if args.kwarg is not None else 0)
    )


def _collect_local_names(node: FunctionDefNode) -> dict[str, str]:
    """First-seen-order discovery of local names -> VAR0, VAR1, ... map.

    Params (signature order) are discovered first, then the body is walked
    in document order collecting every `ast.Name` Store-context target
    (this naturally includes comprehension targets and tuple/starred
    unpacking targets too -- in CPython's `ast`, those are themselves plain
    `Name` nodes with `ctx=Store()`, so no special-casing is needed beyond
    the generic Name(Store) check).

    A nested `FunctionDef`/`AsyncFunctionDef`/`Lambda` encountered during
    the walk has its OWN `args` field skipped entirely (so its parameters
    are never harvested into the outer map) but every other field --
    crucially its body -- is still walked. That means:
      * a reference inside the nested scope to an already-known outer local
        (a closure variable) still gets collected/normalized consistently, and
      * a genuinely new name first introduced inside the nested scope's own
        body (its own local variable, not a parameter) is ALSO harvested
        into the outer map at that point in the walk.
    The second point keeps the OUTER function's hash insensitive to the
    nested scope's own body-local naming too (both get the same next
    available VARn slot regardless of what they're literally called),
    which matches the overarching "regardless of local variable names"
    invariant for the function as a whole, not just its top-level body.
    """
    order: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            order.append(name)

    for name in _ordered_param_names(node.args):
        add(name)

    def visit_field_value(value: object) -> None:
        if isinstance(value, ast.AST):
            handle_node(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, ast.AST):
                    handle_node(item)

    def handle_node(n: ast.AST) -> None:
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            add(n.id)
        skip_args = isinstance(n, _NESTED_SCOPE_TYPES)
        for field_name, value in ast.iter_fields(n):
            if skip_args and field_name == "args":
                continue
            visit_field_value(value)

    for stmt in node.body:
        handle_node(stmt)

    return {name: f"VAR{i}" for i, name in enumerate(order)}


class _StructuralRewriter(ast.NodeTransformer):
    """Combines steps 3+4 (identifier rewrite + constant typing) in one
    traversal. Both mutate node attributes in place and return the same
    node -- no tree restructuring is needed, just `ast.NodeTransformer`
    because that's the idiomatic tool for an in-place AST rewrite pass.

    This pass is intentionally NOT scope-aware: it rewrites every `Name`/
    `arg` anywhere in the tree (including inside nested defs/lambdas) whose
    identifier is a key in the map, mirroring the spec exactly. Local-name
    COLLECTION (above) is where nested-scope parameters get excluded from
    the map in the first place; by the time this pass runs, "is this
    identifier a key in the map" is the only question that matters.
    """

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id in self._mapping:
            node.id = self._mapping[node.id]
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        if node.arg in self._mapping:
            node.arg = self._mapping[node.arg]
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        value = node.value
        if isinstance(value, bool):  # must precede the int/float check
            node.value = "BOOL_LIT"
        elif isinstance(value, str):
            node.value = "STR_LIT"
        elif isinstance(value, (int, float)):
            node.value = "NUM_LIT"
        # else: None / Ellipsis / anything else -- left as-is.
        return node

    # Deliberately no visit_Attribute override: `Attribute.attr` (e.g.
    # `match` in `re.match(...)`) is never touched, by simply never
    # inspecting it -- the default generic_visit still recurses into
    # `Attribute.value` (so a Name used as the attribute's base, e.g. `re`,
    # is still visited normally).


def _strip_docstring(node: FunctionDefNode) -> None:
    """Remove a leading docstring statement (`Expr(Constant(<str>))`), if
    present. Safe to call after constant typing has already turned the
    string into "STR_LIT", since it is still a `str` either way."""
    if (
        node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ):
        node.body.pop(0)


def normalize_and_hash(node: FunctionDefNode) -> NormalizedFunction:
    """Normalize a deep copy of `node` and compute its structural
    fingerprint. `node` itself is never mutated. `param_count` is computed
    from `node` as originally given (before normalization)."""
    param_count = _param_count(node.args)

    working = copy.deepcopy(node)

    mapping = _collect_local_names(working)
    _StructuralRewriter(mapping).visit(working)
    _strip_docstring(working)

    working.name = "FUNC"
    working.decorator_list = []
    working.returns = None
    for arg in _all_args(working.args):
        arg.annotation = None

    dumped = ast.dump(working, annotate_fields=False)
    fingerprint_hash = hashlib.sha256(dumped.encode("utf-8")).hexdigest()
    token_count = len(dumped.split())

    return NormalizedFunction(
        fingerprint_hash=fingerprint_hash,
        token_count=token_count,
        param_count=param_count,
    )
