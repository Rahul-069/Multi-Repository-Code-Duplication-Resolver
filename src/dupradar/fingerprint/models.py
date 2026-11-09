"""Internal dataclasses for the fingerprinting library.

These are intentionally plain `dataclasses` with zero pydantic/MCP
dependency -- kept separate from the wire contract in
`dupradar.mcp_server.schemas`, which is the Step 0 contract everything else
in the project depends on. Field names on `FunctionFingerprint` mirror
`mcp_server.schemas.FunctionFingerprint` 1:1 on purpose, so converting one to
the other is a straight keyword pass-through, e.g.:

    from dataclasses import asdict
    from dupradar.mcp_server.schemas import FunctionFingerprint as WireFingerprint

    wire = WireFingerprint(**asdict(internal_fingerprint))

Nothing in this module ever needs to touch raw source text once a
`FunctionChunk` has been produced by an adapter -- `node` holds a parsed
`ast` subtree, not source text, and it never leaves the process (only
`FunctionFingerprint`/`FingerprintMatch` data derived from it does, via the
MCP tool layer).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

# A function or method definition node, at any nesting depth.
FunctionDefNode = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class FunctionChunk:
    """One function/method extracted from a source file, pre-normalization.

    Produced by a `LanguageAdapter`. `node` is the ORIGINAL (un-normalized)
    ast node -- callers normalize a `copy.deepcopy` of it, never this node
    itself, so the same chunk could in principle be fingerprinted more than
    once without corrupting shared state.
    """

    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    node: FunctionDefNode


@dataclass(frozen=True)
class FunctionFingerprint:
    """Normalized, hashed result for one function.

    Field names/types mirror `mcp_server.schemas.FunctionFingerprint`
    exactly. This is the ONLY shape that is allowed to cross back out of the
    fingerprinting library to the MCP tool layer -- it never carries source
    text or the normalized `ast.dump` string, only the hash/metadata derived
    from them.
    """

    function_id: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    token_count: int
    fingerprint_hash: str
    param_count: int


@dataclass(frozen=True)
class Cluster:
    """A group of functions sharing one `fingerprint_hash` across >= 2
    distinct repos. `members` pairs each fingerprint with the repo_id it
    came from (a plain `FunctionFingerprint` doesn't know its own repo)."""

    fingerprint_hash: str
    members: tuple[tuple[str, FunctionFingerprint], ...]

    @property
    def repo_ids(self) -> frozenset[str]:
        return frozenset(repo_id for repo_id, _ in self.members)


@dataclass(frozen=True)
class FingerprintMatch:
    """Internal mirror of `mcp_server.schemas.FingerprintMatch` -- one
    cross-repo pair sharing a fingerprint_hash."""

    function_a: str
    function_b: str
    repo_a: str
    repo_b: str
    similarity: float
    match_type: str  # "exact" | "near" (only "exact" is produced today)
