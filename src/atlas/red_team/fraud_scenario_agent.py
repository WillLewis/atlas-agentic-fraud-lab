"""Phase 6 round-level orchestrator.

Local deterministic orchestrator — NOT an LLM. Reads
``config/round_config.yaml`` for the requested ``round_id``, intersects
the round's ``allowed_family_ids`` and ``search_methods`` with what the
request asked for, calls the score-query allocator, dispatches to each
enabled search method with its own deterministic RNG split, aggregates
the per-method ``CandidateResult``s, and emits the deterministic
``found_adaptive_set_event_ids`` collection that downstream judge calls
consume (``POST /judge/evaluate-fix`` from Phase 5).

Caching pattern mirrors Phase 5 ``atlas.judge.evaluate``:

  * Process-local caches for the trained baseline bundle, the decision
    policy config, and the loaded ``BaseSearchState``.
  * ``reset_caches()`` for tests.

Determinism guarantees:

  * Same ``(run_id, round_id, search_methods, max_score_queries,
    allowed_family_ids, seed, dataset, round_config, baseline)`` →
    byte-identical ``RedTeamSearchResult``.
  * Per-method RNG seeds derived from a stable hash of
    ``(seed, method)`` so adding/removing methods in the round does not
    perturb the others' candidate sequences.
  * ``found_adaptive_set_event_ids`` is sorted + deduplicated.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence

import yaml

from atlas.model.policy import (
    DEFAULT_OUTPUTS_ROOT,
    DecisionPolicyConfig,
    resolve_decision_policy_config,
)
from atlas.model.scorer import (
    BaselineModelBundle,
    MissingBaselineModelError,
    load_baseline_bundle,
)
from atlas.model.loader import DEFAULT_DATA_DIR
from atlas.red_team.evolutionary_search import evolutionary_search
from atlas.red_team.graph_probe import GRAPH_RELEVANT_FAMILIES, graph_probe
from atlas.red_team.mutations import ALLOWED_FAMILY_IDS, BaseSearchState
from atlas.red_team.random_search import (
    CandidateResult,
    RandomSearchResult,
    random_search,
)
from atlas.red_team.scoring_query_allocator import (
    SEARCH_METHODS,
    allocate_queries,
    per_method_budgets,
)

# ---------------------------------------------------------------------------
# Path conventions
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_ROUND_CONFIG_PATH: Final[Path] = REPO_ROOT / "config" / "round_config.yaml"

# Default seed when the request doesn't provide one. Matches the synthetic
# generator's DEFAULT_TEST_SEED so a default-seed search produces output
# stable across the demo lifecycle.
DEFAULT_SEARCH_SEED: Final[int] = 42


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RedTeamSearchResult:
    """Aggregated output of one ``run_search`` call.

    Maps directly into the OpenAPI ``RedTeamSearchResponse`` shape; the
    route handler in component 8 composes the
    ``model_vulnerability_cards`` field around this from the packager
    (component 7).
    """

    run_id: str
    round_id: int
    valid_high_risk_events_tested: int
    accepted_high_risk_events: int
    model_miss_rate: float
    miss_rate_lift_vs_random: float | None
    found_adaptive_set_event_ids: tuple[str, ...]
    candidates: tuple[CandidateResult, ...]
    by_method: dict[str, RandomSearchResult]
    queries_used: int


# ---------------------------------------------------------------------------
# Caches
# ---------------------------------------------------------------------------

_BUNDLE_CACHE: dict[str, BaselineModelBundle] = {}
_POLICY_CACHE: dict[str, DecisionPolicyConfig] = {}
_BASE_STATE_CACHE: dict[str, BaseSearchState] = {}
_ROUND_CONFIG_CACHE: dict[str, dict] = {}


def reset_caches() -> None:
    """Test-only — drop all cached artifacts so the next call reloads."""
    _BUNDLE_CACHE.clear()
    _POLICY_CACHE.clear()
    _BASE_STATE_CACHE.clear()
    _ROUND_CONFIG_CACHE.clear()


# ---------------------------------------------------------------------------
# Round config loader
# ---------------------------------------------------------------------------


def _load_round_config_doc(path: Path) -> dict:
    cache_key = str(path)
    cached = _ROUND_CONFIG_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if not path.exists():
        raise FileNotFoundError(
            f"round_config.yaml not found at {path}. "
            "Phase 6 search requires config/round_config.yaml to exist."
        )
    with path.open("r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    _ROUND_CONFIG_CACHE[cache_key] = doc
    return doc


def _round_entry(round_id: int, path: Path) -> dict:
    doc = _load_round_config_doc(path)
    rounds = doc.get("rounds") or []
    for entry in rounds:
        if int(entry.get("round_id", -1)) == int(round_id):
            return entry
    available = [int(e.get("round_id", -1)) for e in rounds]
    raise ValueError(
        f"unknown round_id {round_id}; available in {path.name}: {available}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_for_method(base_seed: int, method: str) -> int:
    """Stable per-method seed so adding/removing methods doesn't perturb
    the others' candidate sequences.
    """
    h = hashlib.blake2b(
        f"{base_seed}|{method}".encode("utf-8"), digest_size=4
    ).hexdigest()
    return int(h, 16)


def _get_bundle(model_version: str | None = None) -> BaselineModelBundle:
    return _get_bundle_for_outputs(model_version, outputs_root=DEFAULT_OUTPUTS_ROOT)


def _get_bundle_for_outputs(
    model_version: str | None = None,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> BaselineModelBundle:
    """Phase 8 extension: when ``model_version`` is None, return the
    cached default baseline (Phase 6 behavior). When set, load from
    ``outputs/baseline_models/<model_version>/`` so the round engine
    can score against round-state versions.
    """
    version = model_version or "baseline_v1"
    cache_key = f"{outputs_root.resolve()}|{version}"
    bundle = _BUNDLE_CACHE.get(cache_key)
    if bundle is not None:
        return bundle
    local_dir = outputs_root / "baseline_models" / version
    if local_dir.exists():
        bundle = load_baseline_bundle(local_dir)
    elif version == "baseline_v1":
        bundle = load_baseline_bundle()
    else:
        # Phase 7 candidate models live under
        # ``outputs/baseline_models/<defensive_fix_id>/``.
        candidate_dir = REPO_ROOT / "outputs" / "baseline_models" / version
        bundle = load_baseline_bundle(candidate_dir)
    _BUNDLE_CACHE[cache_key] = bundle
    return bundle


def _get_policy_config(threshold_version: str | None = None) -> DecisionPolicyConfig:
    return _get_policy_config_for_outputs(
        threshold_version, outputs_root=DEFAULT_OUTPUTS_ROOT
    )


def _get_policy_config_for_outputs(
    threshold_version: str | None = None,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> DecisionPolicyConfig:
    """Phase 8 extension: when ``threshold_version`` is None, return the
    cached default config (Phase 6 behavior). When set, the persisted
    ``thresholds_v1`` resolves through the effective outputs-first
    threshold resolver; alternate versions resolve to
    ``outputs/decision_thresholds/<version>.yaml`` (Phase 7 layout).
    """
    cache_key = f"{outputs_root.resolve()}|{threshold_version or '__default__'}"
    cfg = _POLICY_CACHE.get(cache_key)
    if cfg is not None:
        return cfg
    cfg = resolve_decision_policy_config(
        threshold_version,
        outputs_root=outputs_root,
    )
    _POLICY_CACHE[cache_key] = cfg
    return cfg


def _get_base_state(data_dir: Path) -> BaseSearchState:
    cache_key = str(data_dir)
    state = _BASE_STATE_CACHE.get(cache_key)
    if state is None:
        state = BaseSearchState.from_dataset_dir(data_dir)
        _BASE_STATE_CACHE[cache_key] = state
    return state


# ---------------------------------------------------------------------------
# Method dispatch
# ---------------------------------------------------------------------------


def _dispatch_method(
    *,
    method: str,
    rng: random.Random,
    base_state: BaseSearchState,
    family_budgets: dict[str, int],
    bundle: BaselineModelBundle,
    policy_config: DecisionPolicyConfig,
) -> RandomSearchResult:
    if method == "random":
        return random_search(
            rng=rng,
            base_state=base_state,
            family_budgets=family_budgets,
            bundle=bundle,
            policy_config=policy_config,
        )
    if method == "evolutionary":
        return evolutionary_search(
            rng=rng,
            base_state=base_state,
            family_budgets=family_budgets,
            bundle=bundle,
            policy_config=policy_config,
        )
    if method == "graph_probe":
        # Only graph-relevant families are picked up by graph_probe; pre-
        # filter the budget so unused queries surface as "queries_used <
        # allocated" rather than confusing per-family rows.
        gp_budget = {
            f: b for f, b in family_budgets.items() if f in GRAPH_RELEVANT_FAMILIES
        }
        return graph_probe(
            rng=rng,
            base_state=base_state,
            family_budgets=gp_budget,
            bundle=bundle,
            policy_config=policy_config,
        )
    raise ValueError(f"unknown search_method {method!r}; expected one of {list(SEARCH_METHODS)}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_search(
    *,
    run_id: str,
    round_id: int,
    search_methods: Sequence[str],
    max_score_queries: int,
    allowed_family_ids: Sequence[str] | None = None,
    seed: int = DEFAULT_SEARCH_SEED,
    data_dir: Path = DEFAULT_DATA_DIR,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
    round_config_path: Path = DEFAULT_ROUND_CONFIG_PATH,
    current_model_version: str | None = None,
    current_threshold_version: str | None = None,
) -> RedTeamSearchResult:
    """Deterministic Phase 6 red-team search orchestration.

    Args:
        run_id, round_id: surfaced in the result for downstream judge
            correlation. ``round_id`` selects the round entry from
            ``round_config.yaml``.
        search_methods: requested methods. Intersected with the round's
            enabled methods and the global ``SEARCH_METHODS`` allow-list.
        max_score_queries: hard cap on total score-queries across all
            methods + families. Honored exactly when the intersection is
            non-empty.
        allowed_family_ids: requested family subset. ``None`` means
            "everything the round allows". Intersected with the round
            entry's ``allowed_family_ids`` and the schema's 7-family
            canonical registry (``ALLOWED_FAMILY_IDS``).
        seed: master seed for RNG splits. Defaults to ``DEFAULT_SEARCH_SEED``.
        data_dir, outputs_root, round_config_path: load roots — wired in
            from tests and the round engine.
        current_model_version, current_threshold_version: Phase 8
            round-state extension. When ``None`` (default), search uses
            the persisted baseline ``baseline_v1`` + ``thresholds_v1``
            (Phase 6 behavior preserved). When set, the round engine
            passes the round-state's accepted versions so search scores
            candidates against the current state of the loop.

    Returns:
        ``RedTeamSearchResult`` with aggregated metrics, the sorted
        ``found_adaptive_set_event_ids``, the per-method results, and
        the flat ``candidates`` tuple for downstream packaging.

    Raises:
        ValueError: round_id unknown, intersection of families/methods is
            empty, ``max_score_queries < 0``, or any other allocator
            input violation.
        MissingBaselineModelError: trained baseline missing on disk.
    """
    if max_score_queries < 0:
        raise ValueError(f"max_score_queries must be >= 0; got {max_score_queries}")
    if not search_methods:
        raise ValueError("run_search requires at least one search_method")

    round_entry = _round_entry(round_id, round_config_path)

    round_families: list[str] = list(round_entry.get("allowed_family_ids") or [])
    round_methods: list[str] = list(round_entry.get("search_methods") or [])

    # Family intersection: round allow-list ∩ request ∩ canonical registry.
    if allowed_family_ids is None:
        final_families = sorted(set(round_families) & set(ALLOWED_FAMILY_IDS))
    else:
        final_families = sorted(
            set(round_families) & set(allowed_family_ids) & set(ALLOWED_FAMILY_IDS)
        )
    if not final_families:
        raise ValueError(
            f"empty family intersection: round {round_id} allows "
            f"{round_families}; request asked for {allowed_family_ids}; "
            f"canonical registry is {list(ALLOWED_FAMILY_IDS)}."
        )

    # Method intersection: round allow-list ∩ request ∩ global allow-list.
    final_methods = sorted(
        set(round_methods) & set(search_methods) & set(SEARCH_METHODS)
    )
    if not final_methods:
        raise ValueError(
            f"empty method intersection: round {round_id} enables "
            f"{round_methods}; request asked for {list(search_methods)}; "
            f"global allow-list is {list(SEARCH_METHODS)}."
        )

    # Cached resources (raise MissingBaselineModelError naturally if absent).
    bundle = _get_bundle_for_outputs(
        current_model_version, outputs_root=outputs_root
    )
    policy_config = _get_policy_config_for_outputs(
        current_threshold_version, outputs_root=outputs_root
    )
    base_state = _get_base_state(data_dir)

    # Allocate budget across (method, family) pairs.
    allocations = allocate_queries(
        search_methods=final_methods,
        family_ids=final_families,
        max_score_queries=max_score_queries,
    )
    per_method = per_method_budgets(allocations)

    # Dispatch each method with its own deterministic RNG.
    by_method: dict[str, RandomSearchResult] = {}
    all_candidates: list[CandidateResult] = []
    queries_used = 0
    for method in final_methods:
        method_rng = random.Random(_seed_for_method(seed, method))
        family_budget = per_method.get(method, {})
        result = _dispatch_method(
            method=method,
            rng=method_rng,
            base_state=base_state,
            family_budgets=family_budget,
            bundle=bundle,
            policy_config=policy_config,
        )
        by_method[method] = result
        all_candidates.extend(result.candidates)
        queries_used += result.queries_used

    # Aggregate metrics.
    total_valid = sum(1 for c in all_candidates if c.is_high_risk)
    total_accepted = sum(1 for c in all_candidates if c.is_high_risk and c.is_accepted)
    aggregate_miss_rate = (total_accepted / total_valid) if total_valid > 0 else 0.0

    # miss_rate_lift_vs_random: only computable if "random" actually ran
    # AND produced at least one valid high-risk event (so the denominator
    # is non-zero and meaningful).
    lift: float | None = None
    if "random" in by_method:
        rand_result = by_method["random"]
        if rand_result.valid_high_risk_events_tested > 0:
            random_miss = rand_result.model_miss_rate
            if random_miss > 0.0:
                lift = aggregate_miss_rate / random_miss

    # Deterministic, sorted, deduplicated found_adaptive_set_event_ids.
    # Source: target_event_ids of accepted-high-risk candidates — the
    # base events around which red-team mutations succeeded. The judge
    # consumes these via Phase 5's load_eval_set("found_adaptive_set",
    # found_adaptive_set_event_ids=...).
    found_ids = tuple(
        sorted({c.target_event_id for c in all_candidates if c.is_high_risk and c.is_accepted})
    )

    return RedTeamSearchResult(
        run_id=run_id,
        round_id=round_id,
        valid_high_risk_events_tested=total_valid,
        accepted_high_risk_events=total_accepted,
        model_miss_rate=round(aggregate_miss_rate, 4),
        miss_rate_lift_vs_random=(round(lift, 4) if lift is not None else None),
        found_adaptive_set_event_ids=found_ids,
        candidates=tuple(all_candidates),
        by_method=by_method,
        queries_used=queries_used,
    )


__all__ = [
    "RedTeamSearchResult",
    "DEFAULT_ROUND_CONFIG_PATH",
    "DEFAULT_SEARCH_SEED",
    "MissingBaselineModelError",
    "reset_caches",
    "run_search",
]
