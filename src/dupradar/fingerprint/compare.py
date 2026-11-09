"""Exact-hash cross-repo duplicate matching.

Today's matching is exact-hash only (no winnowing/near-duplicate scoring --
that is explicitly future work): two functions are considered duplicates
iff their `fingerprint_hash` is byte-identical. `cluster_by_hash` groups
functions sharing a hash across >= 2 DIFFERENT repos into a `Cluster`;
`find_cross_repo_matches` expands each cluster into the flat pairwise
`FingerprintMatch` shape the `compare_fingerprints` MCP tool returns
(`similarity=1.0`, `match_type="exact"` for every match today).

Same-repo duplicates (two functions in the SAME repo sharing a hash) are
intentionally not reported here -- this feature is about finding
duplication ACROSS repos/orgs, not within one.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from dupradar.fingerprint.models import Cluster, FingerprintMatch, FunctionFingerprint


def cluster_by_hash(
    fingerprints_by_repo: Mapping[str, Iterable[FunctionFingerprint]],
) -> list[Cluster]:
    """Group functions sharing an identical `fingerprint_hash` across >= 2
    distinct repos into `Cluster`s. A hash that only appears within a single
    repo (even if it repeats there) is not a cluster -- today's feature is
    cross-repo duplication only.

    Clusters are returned in a deterministic order: by first appearance of
    their hash while iterating `fingerprints_by_repo` in the given order
    (dict iteration order), then functions within each cluster in that same
    discovery order.
    """
    groups: dict[str, list[tuple[str, FunctionFingerprint]]] = defaultdict(list)
    for repo_id, fingerprints in fingerprints_by_repo.items():
        for fp in fingerprints:
            groups[fp.fingerprint_hash].append((repo_id, fp))

    clusters: list[Cluster] = []
    for fingerprint_hash, members in groups.items():
        distinct_repos = {repo_id for repo_id, _ in members}
        if len(distinct_repos) >= 2:
            clusters.append(Cluster(fingerprint_hash=fingerprint_hash, members=tuple(members)))
    return clusters


def find_cross_repo_matches(
    fingerprints_by_repo: Mapping[str, Iterable[FunctionFingerprint]],
    repo_order: list[str] | None = None,
    threshold: float = 1.0,
) -> list[FingerprintMatch]:
    """Exact-hash cross-repo matching, expanded to one `FingerprintMatch`
    per cross-repo pair sharing a hash (same-repo pairs within a cluster are
    skipped). `threshold` is accepted for forward API-compatibility with
    future near-duplicate scoring but is unused today -- matching is always
    exact.

    `repo_order` (defaults to `fingerprints_by_repo`'s own key order)
    determines which side of a pair is reported as `repo_a` vs `repo_b`:
    whichever repo_id comes first in `repo_order` is `repo_a`, giving
    deterministic, non-duplicated output regardless of dict iteration
    order.
    """
    order = repo_order if repo_order is not None else list(fingerprints_by_repo.keys())
    position = {repo_id: i for i, repo_id in enumerate(order)}

    matches: list[FingerprintMatch] = []
    for cluster in cluster_by_hash(fingerprints_by_repo):
        members = cluster.members
        for i in range(len(members)):
            repo_i, fp_i = members[i]
            for j in range(i + 1, len(members)):
                repo_j, fp_j = members[j]
                if repo_i == repo_j:
                    continue  # same-repo pair -- not reported
                if position.get(repo_i, i) <= position.get(repo_j, j):
                    a_repo, a_fp, b_repo, b_fp = repo_i, fp_i, repo_j, fp_j
                else:
                    a_repo, a_fp, b_repo, b_fp = repo_j, fp_j, repo_i, fp_i
                matches.append(
                    FingerprintMatch(
                        function_a=a_fp.function_id,
                        function_b=b_fp.function_id,
                        repo_a=a_repo,
                        repo_b=b_repo,
                        similarity=1.0,
                        match_type="exact",
                    )
                )
    return matches
