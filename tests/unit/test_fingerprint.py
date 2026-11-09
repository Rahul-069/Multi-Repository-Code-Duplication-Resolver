"""Unit tests for the fingerprinting library (`dupradar.fingerprint.*`).

Most tests build small source snippets inline to pin down one invariant at
a time. `TestSampleRepos` at the bottom runs the REAL adapter over the
actual `sample_repos/` fixture files (path resolved via
`dupradar.config.SAMPLE_REPOS_DIR`, never hardcoded) to prove the planted
cross-repo duplicate -- and both negative controls -- fingerprint
correctly end-to-end.
"""

from __future__ import annotations

import ast
import copy
import itertools

from dupradar.config import SAMPLE_REPOS_DIR
from dupradar.fingerprint.adapters.python_adapter import PythonAdapter
from dupradar.fingerprint.normalize import (
    NormalizedFunction,
    _collect_local_names,
    _StructuralRewriter,
    normalize_and_hash,
)


def _first_function(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise AssertionError("no function found in source")


def _fingerprint(source: str) -> NormalizedFunction:
    return normalize_and_hash(_first_function(source))


def _hash_of(source: str) -> str:
    return _fingerprint(source).fingerprint_hash


# ---------------------------------------------------------------------------
# Same logic must hash identically regardless of naming/formatting/
# docstrings/annotations/literal values.
# ---------------------------------------------------------------------------


class TestInvariance:
    def test_same_logic_different_function_name(self):
        a = _hash_of("def foo(x):\n    return x + 1\n")
        b = _hash_of("def bar(x):\n    return x + 1\n")
        assert a == b

    def test_same_logic_different_param_and_local_names(self):
        a = _hash_of(
            """
def validate_email(email):
    pattern = r"^[\\w.-]+@[\\w.-]+$"
    if not email:
        return False
    if not re.match(pattern, email):
        return False
    return True
"""
        )
        b = _hash_of(
            """
def is_valid_email(address):
    rule = r"^[\\w.-]+@[\\w.-]+$"
    if not address:
        return False
    if not re.match(rule, address):
        return False
    return True
"""
        )
        assert a == b

    def test_same_logic_different_formatting(self):
        a = _hash_of("def f(a,b):\n    return a+b\n")
        b = _hash_of("def f(a, b):\n\n\n    return a + b\n")
        assert a == b

    def test_docstring_vs_no_docstring(self):
        a = _hash_of('def f(a, b):\n    """Adds two numbers."""\n    return a + b\n')
        b = _hash_of("def f(a, b):\n    return a + b\n")
        assert a == b

    def test_annotated_vs_not(self):
        # Keep default-value STRUCTURE identical (none here) -- only vary
        # annotations/return type, since presence/absence of a default is
        # real signal (see TestStructuralDifference below), not something
        # this test is about.
        a = _hash_of("def f(a: int, b: str) -> bool:\n    return a > 0\n")
        b = _hash_of("def f(a, b):\n    return a > 0\n")
        assert a == b

    def test_same_shape_different_literal_values(self):
        a = _hash_of("def f(amount):\n    if amount <= 0:\n        return False\n    return True\n")
        b = _hash_of("def f(total):\n    if total <= 100:\n        return False\n    return True\n")
        assert a == b

    def test_nested_closure_body_local_renamed_consistently(self):
        # A nested function's OWN body-local name is not harvested as the
        # outer function's own param, but it still normalizes consistently
        # (both versions collapse to the same VARn), keeping the outer
        # hash insensitive to the nested scope's naming too.
        a = _hash_of(
            """
def outer(a):
    def inner():
        y = 5
        return a + y
    return inner()
"""
        )
        b = _hash_of(
            """
def outer(z):
    def inner():
        q = 5
        return z + q
    return inner()
"""
        )
        assert a == b


# ---------------------------------------------------------------------------
# Real structural signal must still change the hash.
# ---------------------------------------------------------------------------


class TestStructuralDifference:
    def test_different_control_flow_hashes_differently(self):
        a = _hash_of("def f(a):\n    if a:\n        return 1\n    return 2\n")
        b = _hash_of("def f(a):\n    while a:\n        return 1\n    return 2\n")
        assert a != b

    def test_different_called_function_name_hashes_differently(self):
        a = _hash_of("def f(a):\n    return helper(a)\n")
        b = _hash_of("def f(a):\n    return other(a)\n")
        assert a != b

    def test_attribute_name_is_real_signal_too(self):
        a = _hash_of("def f(a):\n    return re.match(a)\n")
        b = _hash_of("def f(a):\n    return re.search(a)\n")
        assert a != b

    def test_default_value_presence_is_real_signal_not_erased(self):
        # Presence/absence of a default changes the actual call signature;
        # it is not a "literal constant value" difference to normalize away.
        a = _hash_of('def f(a, b="x"):\n    return a\n')
        b = _hash_of("def f(a, b):\n    return a\n")
        assert a != b

    def test_attribute_attr_never_renamed_even_if_it_collides_with_a_local_name(self):
        a = _hash_of("def f(a):\n    match = 5\n    return re.match(a) + match\n")
        b = _hash_of("def f(b):\n    other = 5\n    return re.match(b) + other\n")
        assert a == b


# ---------------------------------------------------------------------------
# Regression: bool is an int subclass -- must never be classified as NUM_LIT.
# ---------------------------------------------------------------------------


class TestBoolLiteralRegression:
    def test_bool_and_equivalent_int_hash_differently(self):
        assert _hash_of("def f():\n    return True\n") != _hash_of("def f():\n    return 1\n")

    def test_true_and_false_hash_the_same_bool_lit(self):
        # Both collapse to the same BOOL_LIT placeholder.
        assert _hash_of("def f():\n    return True\n") == _hash_of("def f():\n    return False\n")

    def test_bool_default_distinct_from_int_default(self):
        a = _hash_of("def f(flag=True):\n    return flag\n")
        b = _hash_of("def f(flag=1):\n    return flag\n")
        assert a != b

    def test_bool_constant_dumps_as_bool_lit_never_num_lit(self):
        """White-box check straight at the normalized dump string, so a
        future refactor that reorders the bool/int `isinstance` checks
        trips this immediately rather than relying only on hash equality."""
        node = _first_function("def f():\n    return True\n")
        working = copy.deepcopy(node)
        mapping = _collect_local_names(working)
        _StructuralRewriter(mapping).visit(working)
        dumped = ast.dump(working, annotate_fields=False)
        assert "BOOL_LIT" in dumped
        assert "NUM_LIT" not in dumped


# ---------------------------------------------------------------------------
# param_count: computed from the ORIGINAL node, across every arg kind.
# ---------------------------------------------------------------------------


class TestParamCount:
    def test_param_count_covers_every_arg_kind(self):
        node = _first_function("def f(a, b, /, c, *args, d, **kwargs):\n    pass\n")
        result = normalize_and_hash(node)
        # a, b (posonly) + c (regular) + d (kwonly) = 4, + 1 vararg + 1 kwarg
        assert result.param_count == 6

    def test_param_count_no_args(self):
        node = _first_function("def f():\n    pass\n")
        assert normalize_and_hash(node).param_count == 0


# ---------------------------------------------------------------------------
# qualified_name convention, produced by the adapter.
# ---------------------------------------------------------------------------


class TestQualifiedNames:
    def test_method_in_class(self):
        source = """
class OrderValidator:
    def validate(self, order):
        return order
"""
        chunks = PythonAdapter().extract_chunks(source, "x.py")
        assert "OrderValidator.validate" in {c.qualified_name for c in chunks}

    def test_nested_function(self):
        source = """
def outer(a):
    def inner(b):
        return a + b
    return inner(1)
"""
        chunks = PythonAdapter().extract_chunks(source, "x.py")
        names = {c.qualified_name for c in chunks}
        assert "outer" in names
        assert "outer.inner" in names

    def test_def_nested_inside_a_block_does_not_add_a_qualifier_segment(self):
        source = """
def outer(flag):
    if flag:
        def inner():
            return 1
        return inner()
    return 0
"""
        chunks = PythonAdapter().extract_chunks(source, "x.py")
        assert "outer.inner" in {c.qualified_name for c in chunks}


# ---------------------------------------------------------------------------
# End-to-end against the real sample_repos fixtures.
# ---------------------------------------------------------------------------


class TestSampleRepos:
    @staticmethod
    def _scan(path) -> dict[str, NormalizedFunction]:
        adapter = PythonAdapter()
        source = path.read_text(encoding="utf-8")
        chunks = adapter.extract_chunks(source, str(path))
        return {chunk.qualified_name: normalize_and_hash(chunk.node) for chunk in chunks}

    def test_planted_duplicate_matches_and_nothing_else_does(self):
        repo_a = self._scan(SAMPLE_REPOS_DIR / "repo_a_payments" / "validators.py")
        repo_b = self._scan(SAMPLE_REPOS_DIR / "repo_b_orders" / "validators.py")
        repo_c = self._scan(SAMPLE_REPOS_DIR / "repo_c_inventory" / "helpers.py")

        # The planted duplicate: same logic, renamed identifiers/locals,
        # different docstring/formatting.
        assert repo_a["validate_email"].fingerprint_hash == repo_b["is_valid_email"].fingerprint_hash

        # The explicit negative-control pair named in the spec.
        assert repo_a["validate_amount"].fingerprint_hash != repo_b["validate_shipping_address"].fingerprint_hash

        all_hashes = {f"repo_a:{name}": r.fingerprint_hash for name, r in repo_a.items()}
        all_hashes.update({f"repo_b:{name}": r.fingerprint_hash for name, r in repo_b.items()})
        all_hashes.update({f"repo_c:{name}": r.fingerprint_hash for name, r in repo_c.items()})

        # Nothing in repo_c_inventory matches anything else -- and, more
        # strongly, the ONLY collision anywhere in the whole dataset is the
        # one planted duplicate above.
        collisions = {
            frozenset((name1, name2))
            for (name1, hash1), (name2, hash2) in itertools.combinations(all_hashes.items(), 2)
            if hash1 == hash2
        }
        assert collisions == {frozenset({"repo_a:validate_email", "repo_b:is_valid_email"})}
