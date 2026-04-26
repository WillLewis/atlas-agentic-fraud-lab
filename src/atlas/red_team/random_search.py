"""Phase 6 deterministic random-mutation baseline search.

Walks ``family_budgets`` in deterministic (sorted) order. For each
family, draws ``per_family_budget`` candidates by:

  1. Picking a target transfer at random from the base partition.
  2. Applying ``apply_candidate_mutation`` for the family.
  3. Calling ``recompute_for_candidate`` to derive the new
     ``FeatureVector`` (history-driven, never direct).
  4. Calling ``score_features`` (one score-query — the budget unit) plus
     ``apply_decision_policy`` to derive the decision action.
  5. Calling ``regenerate_labels_for_candidate`` to determine whether
     the candidate qualifies as ``high_risk_synthetic_activity``.

The score-query counter increments exactly once per ``score_features``
call. Per-family loops abort when the family slice is exhausted; total
``queries_used`` always equals ``sum(family_budgets.values())`` for
positive budgets.

Same ``(rng_seed, base_state, family_budgets, bundle, policy_config)``
→ byte-identical ``RandomSearchResult``.

The result types defined here (``CandidateResult``,
``RandomSearchResult``) are also consumed by
``atlas.red_team.evolutionary_search`` (component 4) and
``atlas.red_team.model_vulnerability_packager`` (component 7).
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping

from atlas.model.policy import DecisionPolicyConfig, apply_decision_policy
from atlas.model.scorer import BaselineModelBundle, score_features
from atlas.red_team.mutations import (
    BaseSearchState,
    apply_candidate_mutation,
    recompute_for_candidate,
    regenerate_labels_for_candidate,
)
from atlas.synthetic.features import FeatureVector

# ---------------------------------------------------------------------------
# Public result types — shared across random + evolutionary + packager
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateResult:
    """One scored candidate produced by a search method."""

    candidate_id: str
    family_id: str
    target_event_id: str
    score: float
    decision_action: str
    synthetic_truth_label: str
    amount_bucket: str
    feature_vector: FeatureVector

    @property
    def is_high_risk(self) -> bool:
        return self.synthetic_truth_label == "high_risk_synthetic_activity"

    @property
    def is_accepted(self) -> bool:
        return self.decision_action == "accept"


@dataclass(frozen=True)
class RandomSearchResult:
    """Deterministic output of one ``random_search`` call.

    ``candidates`` are emitted in the order they were generated (family
    iteration is sorted by ``family_id`` for byte-stability). ``by_family``
    bucket-sorts the same candidates for downstream packaging.
    """

    candidates: tuple[CandidateResult, ...]
    queries_used: int
    by_family: Mapping[str, tuple[CandidateResult, ...]]

    @property
    def valid_high_risk_events_tested(self) -> int:
        return sum(1 for c in self.candidates if c.is_high_risk)

    @property
    def accepted_high_risk_events(self) -> int:
        return sum(1 for c in self.candidates if c.is_high_risk and c.is_accepted)

    @property
    def model_miss_rate(self) -> float:
        """Bible §16.1 — accepted_high_risk / valid_high_risk_tested.

        Returns 0.0 when no high-risk candidates were produced, matching
        the judge's ``atlas.judge.metrics.model_miss_rate`` empty-input
        convention so the §16.7 acceptance comparison stays stable when
        a method finds zero high-risk candidates.
        """
        n_high = self.valid_high_risk_events_tested
        if n_high == 0:
            return 0.0
        return self.accepted_high_risk_events / n_high

    def per_family_counts(self) -> dict[str, dict[str, int]]:
        """Diagnostic — {family_id: {valid: int, accepted: int}}."""
        out: dict[str, dict[str, int]] = {}
        for fam, items in self.by_family.items():
            v = sum(1 for c in items if c.is_high_risk)
            a = sum(1 for c in items if c.is_high_risk and c.is_accepted)
            out[fam] = {"valid_high_risk": v, "accepted_high_risk": a}
        return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def random_search(
    *,
    rng: random.Random,
    base_state: BaseSearchState,
    family_budgets: Mapping[str, int],
    bundle: BaselineModelBundle,
    policy_config: DecisionPolicyConfig,
) -> RandomSearchResult:
    """Deterministic, budget-bounded random-mutation search.

    Args:
        rng: Seeded ``random.Random``. Drives target picks + mutation
             seeds. The same ``rng`` consumed in the same order produces
             byte-identical output.
        base_state: Read-only snapshot of the partition to search over.
        family_budgets: ``{family_id: per_family_query_budget}``. Each
                        value is the number of candidates produced (and
                        score-queries used) for that family.
        bundle: Phase 4 ``BaselineModelBundle`` (loaded once by the
                orchestrator and threaded in here).
        policy_config: Phase 4 ``DecisionPolicyConfig``.

    Returns:
        A ``RandomSearchResult`` with one ``CandidateResult`` per
        candidate, plus the per-family bucketing.
    """
    if len(base_state.transfer_events) == 0:
        raise ValueError(
            "random_search: BaseSearchState has no transfer_events to mutate."
        )

    candidates: list[CandidateResult] = []
    by_family: dict[str, list[CandidateResult]] = defaultdict(list)
    queries_used = 0

    # Walk families in sorted order for byte-stable output regardless of
    # the input dict's iteration order.
    for family_id in sorted(family_budgets):
        budget = int(family_budgets[family_id])
        if budget <= 0:
            by_family[family_id] = []
            continue

        for _ in range(budget):
            target = base_state.transfer_events[
                rng.randrange(len(base_state.transfer_events))
            ]
            mutation_seed = rng.randrange(2**31)
            mutation_rng = random.Random(mutation_seed)

            state = apply_candidate_mutation(
                mutation_rng,
                base_state,
                target["transfer_event_id"],
                family_id,
                mutation_seed=mutation_seed,
            )
            fv = recompute_for_candidate(state)

            # The single budget-counted call.
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

    return RandomSearchResult(
        candidates=tuple(candidates),
        queries_used=queries_used,
        by_family={fam: tuple(items) for fam, items in by_family.items()},
    )
