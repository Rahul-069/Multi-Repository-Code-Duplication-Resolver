"""In-memory, per-process cache of registered repo roots and their scanned
fingerprints.

`REPO_CACHE` is the actual module-level cache: `{repo_id: {"root": Path,
"functions": list[FunctionFingerprint] | None}}`. `functions` is `None`
until `scan_repo_fingerprints` has run for that repo_id at least once since
its last `register_repo` call. No persistence -- a fresh server process
starts with an empty cache, by design.

The functions below are thin, typed convenience wrappers around that dict
for `tools_repo.py`/`tools_compare.py` (and tests) to use instead of poking
the dict directly; nothing here depends on pydantic or MCP.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from dupradar.fingerprint.models import FunctionFingerprint


class RepoCacheEntry(TypedDict):
    root: Path
    functions: list[FunctionFingerprint] | None


REPO_CACHE: dict[str, RepoCacheEntry] = {}


def register(repo_id: str, root: Path) -> None:
    """Register (or re-register) a repo root under `repo_id`. Re-registering
    an existing repo_id resets its previously scanned fingerprints -- callers
    must `scan_repo_fingerprints` again after re-registering."""
    REPO_CACHE[repo_id] = {"root": root, "functions": None}


def is_registered(repo_id: str) -> bool:
    return repo_id in REPO_CACHE


def get_root(repo_id: str) -> Path | None:
    entry = REPO_CACHE.get(repo_id)
    return entry["root"] if entry is not None else None


def set_functions(repo_id: str, functions: list[FunctionFingerprint]) -> None:
    if repo_id not in REPO_CACHE:
        raise KeyError(f"cannot cache functions for unregistered repo_id {repo_id!r}")
    REPO_CACHE[repo_id]["functions"] = functions


def get_functions(repo_id: str) -> list[FunctionFingerprint] | None:
    """`None` means either "not registered" or "registered but not yet
    scanned" -- callers that need to distinguish those should check
    `is_registered` first."""
    entry = REPO_CACHE.get(repo_id)
    return entry["functions"] if entry is not None else None


def clear() -> None:
    """Test-only helper: reset the whole cache so tests don't leak
    repo_id/state into each other across test functions."""
    REPO_CACHE.clear()
