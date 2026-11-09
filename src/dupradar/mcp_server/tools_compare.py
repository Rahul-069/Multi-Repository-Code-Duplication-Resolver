"""`compare_fingerprints` MCP tool logic.

Pure in-memory comparison over already-scanned fingerprints -- never
touches the filesystem itself (each repo's raw files were only ever read
once, back in `scan_repo_fingerprints`).
"""

from __future__ import annotations

from dupradar.fingerprint.compare import find_cross_repo_matches
from dupradar.mcp_server import cache
from dupradar.mcp_server.schemas import CompareFingerprintsResult
from dupradar.mcp_server.schemas import FingerprintMatch as WireMatch


def compare_fingerprints(repo_ids: list[str], threshold: float = 1.0) -> dict:
    """Read cached fingerprints for every repo_id in `repo_ids` (raising a
    `ValueError` if any of them has not been scanned yet), find cross-repo
    pairs sharing an identical `fingerprint_hash`, and return a
    `CompareFingerprintsResult`-shaped dict.

    `threshold` is accepted for forward API-compatibility with future
    near-duplicate scoring but is unused today -- matching is always exact
    (`similarity=1.0`, `match_type="exact"` for every match).
    """
    fingerprints_by_repo = {}
    for repo_id in repo_ids:
        functions = cache.get_functions(repo_id)
        if functions is None:
            if not cache.is_registered(repo_id):
                raise ValueError(f"compare_fingerprints: repo_id '{repo_id}' is not registered")
            raise ValueError(
                f"compare_fingerprints: repo_id '{repo_id}' has not been scanned yet; "
                "call scan_repo_fingerprints first"
            )
        fingerprints_by_repo[repo_id] = functions

    matches = find_cross_repo_matches(fingerprints_by_repo, repo_order=repo_ids, threshold=threshold)

    result = CompareFingerprintsResult(
        matches=[
            WireMatch(
                function_a=m.function_a,
                function_b=m.function_b,
                repo_a=m.repo_a,
                repo_b=m.repo_b,
                similarity=m.similarity,
                match_type=m.match_type,
            )
            for m in matches
        ]
    )
    return result.model_dump()
