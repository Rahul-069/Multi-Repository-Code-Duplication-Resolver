"""`register_repo` and `scan_repo_fingerprints` MCP tool logic.

Each function here is the PLAIN, directly-importable implementation behind
one MCP tool -- `server.py` wraps each in a thin `@mcp.tool()`-decorated
function that just calls through, so tests (and anything else) can call
this real logic directly without a live MCP server connection.

This is the only code in the project that ever reads raw repo file
contents off disk. Everything returned is a `mcp_server.schemas` wire type
(`.model_dump()`-ed to a plain dict) -- those shapes never carry source
text or the normalized `ast.dump` string, only hashes/metadata derived
from them.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from dupradar.fingerprint.adapters.python_adapter import PythonAdapter
from dupradar.fingerprint.models import FunctionFingerprint as InternalFingerprint
from dupradar.fingerprint.normalize import normalize_and_hash
from dupradar.mcp_server import cache
from dupradar.mcp_server.schemas import FunctionFingerprint as WireFingerprint
from dupradar.mcp_server.schemas import RegisterRepoResult, ScanRepoFingerprintsResult

_adapter = PythonAdapter()


def register_repo(repo_id: str, path: str) -> dict:
    """Validate `path` is an existing directory, walk its `*.py` files to
    compute file_count / loc_total (non-blank lines) / language_breakdown,
    cache the resolved root path under `repo_id`, and return a
    `RegisterRepoResult`-shaped dict.

    Re-registering an already-known `repo_id` resets its previously scanned
    fingerprints (see `cache.register`) -- callers must call
    `scan_repo_fingerprints` again afterward.
    """
    root = Path(path)
    if not root.is_dir():
        raise ValueError(f"register_repo: path '{path}' is not an existing directory")
    root = root.resolve()

    py_files = sorted(root.rglob("*.py"))
    file_count = len(py_files)
    loc_total = 0
    for file_path in py_files:
        text = file_path.read_text(encoding="utf-8")
        loc_total += sum(1 for line in text.splitlines() if line.strip())

    cache.register(repo_id, root)

    result = RegisterRepoResult(
        repo_id=repo_id,
        file_count=file_count,
        loc_total=loc_total,
        language_breakdown={".py": file_count},
    )
    return result.model_dump()


def scan_repo_fingerprints(repo_id: str) -> dict:
    """Walk `repo_id`'s cached root, run the Python adapter + normalizer +
    hasher over every function/method found (at any nesting depth, in
    every `.py` file), cache the resulting fingerprints, and return a
    `ScanRepoFingerprintsResult`-shaped dict.

    Raises `ValueError` if `repo_id` was never registered.
    """
    if not cache.is_registered(repo_id):
        raise ValueError(
            f"scan_repo_fingerprints: repo_id '{repo_id}' is not registered; call register_repo first"
        )

    root = cache.get_root(repo_id)
    assert root is not None  # guaranteed by is_registered() above

    functions: list[InternalFingerprint] = []
    for file_path in sorted(root.rglob("*.py")):
        source = file_path.read_text(encoding="utf-8")
        rel_path = file_path.relative_to(root).as_posix()
        for chunk in _adapter.extract_chunks(source, rel_path):
            normalized = normalize_and_hash(chunk.node)
            function_id = f"{repo_id}:{chunk.qualified_name}"
            functions.append(
                InternalFingerprint(
                    function_id=function_id,
                    qualified_name=chunk.qualified_name,
                    file_path=chunk.file_path,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    token_count=normalized.token_count,
                    fingerprint_hash=normalized.fingerprint_hash,
                    param_count=normalized.param_count,
                )
            )

    cache.set_functions(repo_id, functions)

    result = ScanRepoFingerprintsResult(
        repo_id=repo_id,
        functions=[WireFingerprint(**dataclasses.asdict(fp)) for fp in functions],
    )
    return result.model_dump()
