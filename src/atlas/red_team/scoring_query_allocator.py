"""Phase 6 deterministic score-query budget allocator.

Splits ``max_score_queries`` across the round's enabled search methods
and allowed families. Default policy:

  1. Equal split across enabled methods.
  2. Equal split across allowed families within each method.
  3. Remainders distributed in a deterministic round-robin so the sum
     equals ``max_score_queries`` exactly (never more, never less).

Returned shape: ``dict[(method, family_id), int]`` with byte-stable
ordering — methods sorted alphabetically, families sorted alphabetically
within each method. The orchestrator (component 6) consumes this and
extracts per-method dicts via :func:`per_method_budgets`.
"""

from __future__ import annotations

from typing import Final, Mapping, Sequence

# The three Phase 6 search methods, in deterministic order. Matches the
# OpenAPI ``RedTeamSearchRequest.search_methods`` enum.
SEARCH_METHODS: Final[tuple[str, ...]] = ("random", "evolutionary", "graph_probe")


def allocate_queries(
    *,
    search_methods: Sequence[str],
    family_ids: Sequence[str],
    max_score_queries: int,
) -> dict[tuple[str, str], int]:
    """Split ``max_score_queries`` across (method, family_id) pairs.

    The sum of the returned dict's values always equals
    ``max_score_queries`` for ``max_score_queries > 0``. Same inputs →
    identical output dict (byte-stable iteration order via sorted keys).

    Raises:
        ValueError: ``max_score_queries < 0``, empty ``search_methods``,
                    empty ``family_ids``, or any method not in
                    ``SEARCH_METHODS``.
    """
    if max_score_queries < 0:
        raise ValueError(
            f"max_score_queries must be >= 0; got {max_score_queries}"
        )
    if not search_methods:
        raise ValueError("allocate_queries requires at least one search_method")
    if not family_ids:
        raise ValueError("allocate_queries requires at least one family_id")

    methods_sorted = sorted(set(search_methods))
    families_sorted = sorted(set(family_ids))

    for m in methods_sorted:
        if m not in SEARCH_METHODS:
            raise ValueError(
                f"unknown search_method {m!r}; expected one of {list(SEARCH_METHODS)}"
            )

    if max_score_queries == 0:
        return {(m, f): 0 for m in methods_sorted for f in families_sorted}

    n_pairs = len(methods_sorted) * len(families_sorted)
    base = max_score_queries // n_pairs
    remainder = max_score_queries - base * n_pairs

    out: dict[tuple[str, str], int] = {}
    pair_index = 0
    for method in methods_sorted:
        for fam in families_sorted:
            extra = 1 if pair_index < remainder else 0
            out[(method, fam)] = base + extra
            pair_index += 1

    # Defensive cross-check — the contract is that the sum equals the
    # input budget exactly. If this ever drifts the orchestrator would
    # over- or under-spend the round's score queries.
    assert sum(out.values()) == max_score_queries, (
        f"allocator math drift: sum={sum(out.values())} expected={max_score_queries}"
    )
    return out


def per_method_budgets(
    allocations: Mapping[tuple[str, str], int],
) -> dict[str, dict[str, int]]:
    """Pivot an ``allocate_queries`` result to ``{method: {family_id: budget}}``.

    The search functions (``random_search``, ``evolutionary_search``,
    ``graph_probe``) all take ``family_budgets: dict[str, int]`` — this
    helper feeds them their slice of the global allocation.
    """
    out: dict[str, dict[str, int]] = {}
    for (method, fam), budget in allocations.items():
        out.setdefault(method, {})[fam] = int(budget)
    return out
