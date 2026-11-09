"""Unit tests for the MCP server tool logic (`dupradar.mcp_server.*`).

Every test here calls the PLAIN underlying functions directly (never a
live MCP server/stdio connection) -- that's the whole point of structuring
each tool as "a plain importable function the `@mcp.tool()` wrapper
calls", per the project spec.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dupradar.config import SAMPLE_REPOS_DIR
from dupradar.fingerprint.models import FunctionFingerprint
from dupradar.mcp_server import cache
from dupradar.mcp_server.tools_compare import compare_fingerprints
from dupradar.mcp_server.tools_repo import register_repo, scan_repo_fingerprints


@pytest.fixture(autouse=True)
def _clear_cache():
    """`cache.REPO_CACHE` is a module-level dict -- without resetting it,
    tests would leak repo_ids/state into each other."""
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# register_repo
# ---------------------------------------------------------------------------


class TestRegisterRepoCounts:
    def test_register_repo_counts(self):
        result = register_repo("repo_a", str(SAMPLE_REPOS_DIR / "repo_a_payments"))

        assert result["repo_id"] == "repo_a"
        assert result["file_count"] == 1  # just validators.py
        assert result["language_breakdown"] == {".py": 1}
        # validators.py: 18 total lines, 14 non-blank (verified against the
        # real fixture file independently of this test).
        assert result["loc_total"] == 14

    def test_register_repo_raises_on_missing_directory(self):
        with pytest.raises(ValueError):
            register_repo("nope", str(SAMPLE_REPOS_DIR / "does_not_exist_dir"))


# ---------------------------------------------------------------------------
# scan_repo_fingerprints -- the mandatory privacy test
# ---------------------------------------------------------------------------


class TestPrivacy:
    def test_scan_repo_fingerprints_never_returns_source_text(self):
        repo_path = SAMPLE_REPOS_DIR / "repo_a_payments"
        source = (repo_path / "validators.py").read_text(encoding="utf-8")

        # Real substrings pulled verbatim from the actual source: the
        # function signature, the regex LITERAL VALUE, and a control-flow
        # line referencing both the local var and param names. All three
        # are exactly the kind of thing normalization is supposed to erase
        # before anything crosses the MCP tool boundary.
        forbidden_substrings = [
            "def validate_email(email):",
            r"^[\w\.-]+@[\w\.-]+\.\w+$",
            "if not re.match(pattern, email):",
        ]
        for s in forbidden_substrings:
            assert len(s) >= 10, f"test fixture substring too short to be meaningful: {s!r}"
            assert s in source, f"test fixture substring not actually in the real source: {s!r}"

        register_repo("repo_a", str(repo_path))
        result = scan_repo_fingerprints("repo_a")

        # Recursively stringify the entire returned structure (JSON dump
        # walks every nested dict/list/value) and check none of the
        # forbidden substrings appear anywhere in it.
        haystack = json.dumps(result)
        for forbidden in forbidden_substrings:
            assert forbidden not in haystack, f"privacy leak: found {forbidden!r} in tool output"

        # Structural belt-and-suspenders: every function entry has EXACTLY
        # the FunctionFingerprint fields -- no stray "source"/"code"/"text"
        # key could have smuggled anything through.
        allowed_keys = set(FunctionFingerprint.__dataclass_fields__.keys())
        assert result["functions"], "expected at least one scanned function"
        for fn in result["functions"]:
            assert set(fn.keys()) == allowed_keys

    def test_scan_repo_fingerprints_raises_if_not_registered(self):
        with pytest.raises(ValueError):
            scan_repo_fingerprints("never_registered")

    def test_scan_repo_fingerprints_finds_expected_functions(self):
        repo_path = SAMPLE_REPOS_DIR / "repo_a_payments"
        register_repo("repo_a", str(repo_path))
        result = scan_repo_fingerprints("repo_a")

        names = {fn["qualified_name"] for fn in result["functions"]}
        assert names == {"validate_email", "validate_amount"}
        for fn in result["functions"]:
            assert fn["function_id"] == f"repo_a:{fn['qualified_name']}"


# ---------------------------------------------------------------------------
# compare_fingerprints -- small synthetic data, no filesystem.
# ---------------------------------------------------------------------------


def _fp(function_id: str, qualified_name: str, fingerprint_hash: str) -> FunctionFingerprint:
    return FunctionFingerprint(
        function_id=function_id,
        qualified_name=qualified_name,
        file_path="validators.py",
        start_line=1,
        end_line=5,
        token_count=20,
        fingerprint_hash=fingerprint_hash,
        param_count=1,
    )


class TestCompareFingerprintsCrossRepo:
    def test_compare_fingerprints_cross_repo(self):
        shared_hash = "a" * 64
        unique_hash_x = "b" * 64
        unique_hash_y = "c" * 64

        cache.register("repo_x", Path("fake_root_x"))
        cache.register("repo_y", Path("fake_root_y"))
        cache.set_functions(
            "repo_x",
            [
                _fp("repo_x:validate_email", "validate_email", shared_hash),
                _fp("repo_x:validate_amount", "validate_amount", unique_hash_x),
            ],
        )
        cache.set_functions(
            "repo_y",
            [
                _fp("repo_y:is_valid_email", "is_valid_email", shared_hash),
                _fp("repo_y:validate_shipping_address", "validate_shipping_address", unique_hash_y),
            ],
        )

        result = compare_fingerprints(["repo_x", "repo_y"])

        assert len(result["matches"]) == 1
        match = result["matches"][0]
        assert match["function_a"] == "repo_x:validate_email"
        assert match["function_b"] == "repo_y:is_valid_email"
        assert match["repo_a"] == "repo_x"
        assert match["repo_b"] == "repo_y"
        assert match["similarity"] == 1.0
        assert match["match_type"] == "exact"

    def test_compare_fingerprints_ignores_same_repo_duplicates(self):
        # Two functions sharing a hash WITHIN the same repo must not be
        # reported -- this feature is cross-repo duplication only.
        shared_hash = "d" * 64
        cache.register("repo_x", Path("fake_root_x"))
        cache.register("repo_y", Path("fake_root_y"))
        cache.set_functions(
            "repo_x",
            [
                _fp("repo_x:a", "a", shared_hash),
                _fp("repo_x:b", "b", shared_hash),
            ],
        )
        cache.set_functions("repo_y", [])

        result = compare_fingerprints(["repo_x", "repo_y"])
        assert result["matches"] == []

    def test_compare_fingerprints_raises_if_any_repo_unscanned(self):
        cache.register("repo_x", Path("fake_root_x"))  # registered, never scanned
        with pytest.raises(ValueError):
            compare_fingerprints(["repo_x"])

    def test_compare_fingerprints_raises_if_repo_never_registered(self):
        with pytest.raises(ValueError):
            compare_fingerprints(["totally_unknown_repo"])
