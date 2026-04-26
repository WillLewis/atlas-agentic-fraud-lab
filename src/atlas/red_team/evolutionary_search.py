"""Phase 6 deterministic adaptive search.

Smallest robust mutation-and-selection loop that improves over
``random_search`` under a fixed query budget on at least one seeded
``model_vulnerability`` family (Bible §18 Phase 6 acceptance).

Per-family loop:

  1. Generation 0 — random population (~``budget // generations`` candidates).
  2. Tournament-rank the current population:
       Tier 0 — ``is_high_risk AND is_accepted`` (the wins).
       Tier 1 — ``is_high_risk`` only (caught — useful when the scorer
                eventually tightens; preserves the "consistent label-flip"
                signal regardless of acceptance).
       Tier 2 — near-threshold by score proximity (``score`` between
                ``challenge_score_threshold - 0.10`` and
                ``challenge_score_threshold``) — promising near-misses.
       Tier 3 — everything else.
       Within tier: higher score wins (tie-break).
  3. Re-mutate around the top-K winners with new mutation seeds —
     same target_event_id (and therefore same customer base_risk),
     different recipient / amount / channel choices. Reliably re-flips
     labels for "good" targets while exploring micro-variations.
  4. Repeat until the family budget is exhausted.

Score-query budget bounds total ``score_features`` calls — exactly one
per candidate, identical to ``random_search``. Same
``(rng_seed, base_state, family_budgets, bundle, policy_config)`` →
byte-identical ``EvolutionaryResult``.
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

# ``EvolutionaryResult`` is shape-compatible with ``RandomSearchResult``;
# downstream packagers consume them interchangeably. Provenance lives in
# the call site, not the type system.
EvolutionaryResult = RandomSearchResult

# Tournament tuning constants. Kept tight so the loop stays simple +
# testable; tunable from one place if Phase 7 needs a different shape.
_DEFAULT_GENERATIONS: Final[int] = 5
_NEAR_THRESHOLD_BAND: Final[float] = 0.10


# ---------------------------------------------------------------------------
# Tournament ranking
# ---------------------------------------------------------------------------


def _tournament_key(c: CandidateResult, *, challenge_threshold: float):
    """Return a sort key — lower = better.

    Keep the function pure of side-effects: same input → same key, so
    ``sorted(...)`` is byte-stable.
    """
    if c.is_high_risk and c.is_accepted:
        tier = 0
    elif c.is_high_risk:
        tier = 1
    elif (challenge_threshold - _NEAR_THRESHOLD_BAND) <= c.score < challenge_threshold:
        tier = 2
    else:
        tier = 3
    # Tie-break: higher score is better (closer to action), then by
    # candidate_id for full byte-stability across runs.
    return (tier, -c.score, c.candidate_id)


def _select_winners(
    population: list[CandidateResult],
    *,
    k: int,
    challenge_threshold: float,
) -> list[CandidateResult]:
    if not population:
        return []
    return sorted(
        population, key=lambda c: _tournament_key(c, challenge_threshold=challenge_threshold)
    )[:k]


# ---------------------------------------------------------------------------
# Per-family evolutionary loop
# ---------------------------------------------------------------------------


def _score_one(
    *,
    rng_seed: int,
    base_state: BaseSearchState,
    family_id: str,
    target_event_id: str,
    bundle: BaselineModelBundle,
    policy_config: DecisionPolicyConfig,
) -> CandidateResult:
    """Generate, score, and label one candidate. Single-source-of-truth
    for the per-candidate pipeline used by both the initial random
    generation and the winner re-mutations.
    """
    mutation_rng = random.Random(rng_seed)
    state = apply_candidate_mutation(
        mutation_rng,
        base_state,
        target_event_id,
        family_id,
        mutation_seed=rng_seed,
    )
    fv = recompute_for_candidate(state)
    score = score_features(fv, bundle)
    decision = apply_decision_policy(score, fv, policy_config)
    label_rng = random.Random(state.candidate_id)
    label = regenerate_labels_for_candidate(label_rng, state)
    return CandidateResult(
        candidate_id=state.candidate_id,
        family_id=family_id,
        target_event_id=target_event_id,
        score=score,
        decision_action=decision.decision_action,
        synthetic_truth_label=label["synthetic_truth_label"],
        amount_bucket=state.target_transfer["amount_bucket"],
        feature_vector=fv,
    )


def _evolve_one_family(
    *,
    rng: random.Random,
    base_state: BaseSearchState,
    family_id: str,
    budget: int,
    bundle: BaselineModelBundle,
    policy_config: DecisionPolicyConfig,
    generations: int,
) -> list[CandidateResult]:
    """Run the adaptive loop for ONE family within its budget slice.

    Returns the full population produced (one ``CandidateResult`` per
    score-query). The total length always equals ``budget``.
    """
    if budget <= 0:
        return []

    pop_size = max(2, budget // generations)
    remaining = budget
    population: list[CandidateResult] = []

    # Generation 0 — random initial population.
    init_count = min(pop_size, remaining)
    for _ in range(init_count):
        target = base_state.transfer_events[
            rng.randrange(len(base_state.transfer_events))
        ]
        seed = rng.randrange(2**31)
        population.append(
            _score_one(
                rng_seed=seed,
                base_state=base_state,
                family_id=family_id,
                target_event_id=target["transfer_event_id"],
                bundle=bundle,
                policy_config=policy_config,
            )
        )
    remaining -= init_count

    # Generations 1+ — re-mutate around tournament-ranked winners,
    # mixed with a fixed fraction of random exploration so the loop
    # cannot get stuck re-mutating low-base-risk losers when gen 0 is
    # unlucky.
    while remaining > 0:
        # Tier-0 / tier-1 winners only — re-mutating tier-2/3 losers
        # doesn't compound, so when no real winners exist we fall back
        # to pure random exploration this generation.
        high_risk_winners = [
            c for c in population if c.is_high_risk
        ]
        winners = _select_winners(
            high_risk_winners,
            k=max(1, pop_size // 2),
            challenge_threshold=policy_config.challenge_score_threshold,
        )

        gen_size = min(pop_size, remaining)
        if not winners:
            # Fallback: pure random exploration — same expected yield as
            # random_search per query, and gives the next generation a
            # chance to find actual winners.
            n_winners = 0
        else:
            # Mix: ~2/3 winner re-mutation + ~1/3 random exploration.
            # Keeps determinism (integer split) and prevents the loop
            # from collapsing onto a small winner pool.
            n_random = max(1, gen_size // 3)
            n_winners = gen_size - n_random

        # Winner re-mutations.
        for _ in range(n_winners):
            parent = winners[rng.randrange(len(winners))]
            seed = rng.randrange(2**31)
            population.append(
                _score_one(
                    rng_seed=seed,
                    base_state=base_state,
                    family_id=family_id,
                    target_event_id=parent.target_event_id,
                    bundle=bundle,
                    policy_config=policy_config,
                )
            )

        # Random exploration (also covers the no-winners fallback case).
        for _ in range(gen_size - n_winners):
            target = base_state.transfer_events[
                rng.randrange(len(base_state.transfer_events))
            ]
            seed = rng.randrange(2**31)
            population.append(
                _score_one(
                    rng_seed=seed,
                    base_state=base_state,
                    family_id=family_id,
                    target_event_id=target["transfer_event_id"],
                    bundle=bundle,
                    policy_config=policy_config,
                )
            )

        remaining -= gen_size

    return population


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def evolutionary_search(
    *,
    rng: random.Random,
    base_state: BaseSearchState,
    family_budgets: Mapping[str, int],
    bundle: BaselineModelBundle,
    policy_config: DecisionPolicyConfig,
    generations: int = _DEFAULT_GENERATIONS,
) -> EvolutionaryResult:
    """Deterministic adaptive search with the same budget contract as
    ``random_search``.

    Same ``(rng_seed, base_state, family_budgets, bundle, policy_config,
    generations)`` → byte-identical result.
    """
    if len(base_state.transfer_events) == 0:
        raise ValueError(
            "evolutionary_search: BaseSearchState has no transfer_events to mutate."
        )
    if generations < 1:
        raise ValueError(f"generations must be >= 1; got {generations}")

    candidates: list[CandidateResult] = []
    by_family: dict[str, list[CandidateResult]] = defaultdict(list)
    queries_used = 0

    for family_id in sorted(family_budgets):
        budget = int(family_budgets[family_id])
        family_results = _evolve_one_family(
            rng=rng,
            base_state=base_state,
            family_id=family_id,
            budget=budget,
            bundle=bundle,
            policy_config=policy_config,
            generations=generations,
        )
        candidates.extend(family_results)
        by_family[family_id] = family_results
        queries_used += len(family_results)

    return EvolutionaryResult(
        candidates=tuple(candidates),
        queries_used=queries_used,
        by_family={fam: tuple(items) for fam, items in by_family.items()},
    )
