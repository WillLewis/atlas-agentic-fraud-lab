"""Phase 6 graph-relationship-driven search.

Same per-candidate mechanic as ``random_search`` (mutate → recompute →
score → policy → regenerate label) — the difference is **target
selection**:

  * Target picks are **weighted by customer graph degree** (count of
    edges touching the customer in ``base_state.graph_edges``). High-
    degree customers are more likely to mutate into the
    ``shared_recipient_high_degree`` / ``shared_device_high_degree`` /
    ``entity_graph_risk`` reason-code cohorts after recomputation.
  * Operates **only on graph-relevant families**
    (``GRAPH_RELEVANT_FAMILIES`` below). Families whose mutations don't
    move graph features are silently skipped — the orchestrator
    (component 6) is expected to filter ``family_budgets`` to the
    graph-relevant subset before calling, but the silent-skip keeps
    this module robust to misuse.

Result type is identical to ``RandomSearchResult`` — downstream
packagers consume it interchangeably.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Final, Mapping

from atlas.model.policy import DecisionPolicyConfig, apply_decision_policy
from atlas.model.scorer import BaselineModelBundle, score_features
from atlas.red_team.mutations import (
    BaseSearchState,
    apply_candidate_mutation,
    recompute_for_candidate,
    regenerate_labels_for_candidate,
)
from atlas.red_team.random_search import CandidateResult, RandomSearchResult
from atlas.synthetic.graph import GraphEdge

# Families whose mutations move graph-derived features
# (``shared_device_degree`` / ``shared_recipient_degree`` /
# ``entity_graph_risk_score``). See
# ``atlas.red_team.mutations.mutate_transfer_context`` —
# ``low_velocity_high_graph_risk`` and ``overfit_fix_failure`` add a new
# ``attempted_transfer_to`` edge AND swap to a high-reuse recipient,
# which directly bumps the recomputed graph features for the target
# customer.
GRAPH_RELEVANT_FAMILIES: Final[frozenset[str]] = frozenset(
    {"low_velocity_high_graph_risk", "overfit_fix_failure"}
)

GraphProbeResult = RandomSearchResult


# ---------------------------------------------------------------------------
# Customer-degree precompute
# ---------------------------------------------------------------------------


def _customer_degree(graph_edges: tuple[GraphEdge, ...]) -> dict[str, int]:
    """Count edges touching each ``cust_*`` node, regardless of direction."""
    out: dict[str, int] = defaultdict(int)
    for edge in graph_edges:
        if edge["source_node_type"] == "customer":
            out[edge["source_node_id"]] += 1
        if edge["target_node_type"] == "customer":
            out[edge["target_node_id"]] += 1
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def graph_probe(
    *,
    rng: random.Random,
    base_state: BaseSearchState,
    family_budgets: Mapping[str, int],
    bundle: BaselineModelBundle,
    policy_config: DecisionPolicyConfig,
) -> GraphProbeResult:
    """Deterministic, budget-bounded graph-relationship search.

    Same byte-stable contract as ``random_search``. Non-graph-relevant
    families consume zero budget (silently skipped); ``queries_used``
    reflects only the work actually done.
    """
    if len(base_state.transfer_events) == 0:
        raise ValueError(
            "graph_probe: BaseSearchState has no transfer_events to mutate."
        )

    cust_degree = _customer_degree(base_state.graph_edges)
    # Pre-compute the per-transfer weight (customer degree + 1 floor so
    # transfers from zero-degree customers still have a chance to be
    # picked deterministically).
    transfers = list(base_state.transfer_events)
    weights = [cust_degree.get(t["customer_id"], 0) + 1 for t in transfers]

    candidates: list[CandidateResult] = []
    by_family: dict[str, list[CandidateResult]] = defaultdict(list)
    queries_used = 0

    for family_id in sorted(family_budgets):
        budget = int(family_budgets[family_id])
        if budget <= 0 or family_id not in GRAPH_RELEVANT_FAMILIES:
            by_family[family_id] = []
            continue

        for _ in range(budget):
            target = rng.choices(transfers, weights=weights, k=1)[0]
            seed = rng.randrange(2**31)

            mutation_rng = random.Random(seed)
            state = apply_candidate_mutation(
                mutation_rng,
                base_state,
                target["transfer_event_id"],
                family_id,
                mutation_seed=seed,
            )
            fv = recompute_for_candidate(state)
            score = score_features(fv, bundle)
            queries_used += 1
            decision = apply_decision_policy(score, fv, policy_config)
            label_rng = random.Random(state.candidate_id)
            label = regenerate_labels_for_candidate(label_rng, state)

            result = CandidateResult(
                candidate_id=state.candidate_id,
                family_id=family_id,
                target_event_id=target["transfer_event_id"],
                score=score,
                decision_action=decision.decision_action,
                synthetic_truth_label=label["synthetic_truth_label"],
                amount_bucket=state.target_transfer["amount_bucket"],
                feature_vector=fv,
            )
            candidates.append(result)
            by_family[family_id].append(result)

    return GraphProbeResult(
        candidates=tuple(candidates),
        queries_used=queries_used,
        by_family={fam: tuple(items) for fam, items in by_family.items()},
    )
