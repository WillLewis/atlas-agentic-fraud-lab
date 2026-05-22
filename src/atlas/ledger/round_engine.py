"""Phase 8 single-round execution primitive.

``execute_one_round`` runs the deterministic Phase 6 → 7 pipeline for
ONE round and emits a fully-materialized ``RoundState`` + one
``LedgerRecord`` row.

Flow:

  1. Load the round entry from ``config/round_config.yaml``.
  2. Red-team search using the run-state's carry-forward
     ``current_model_version`` + ``current_threshold_version``.
  3. Package + persist Phase 6 ``ModelVulnerabilityCard``s as
     ``ModelVulnerabilityRecord``s under
     ``outputs/model_vulnerabilities/`` (the round engine bypasses the
     ``POST /red-team/search`` route and calls
     ``persist_cards_as_records`` directly).
  4. Propose Phase 7 defensive fixes via ``strategy_agent.propose_fixes``
     (3-way intersection: request ∩ round_config ∩ card map).
  5. Deterministic candidate selection rule:
       sort by (model_miss_rate desc, family_id asc, fix_type asc)
       → top ``MAX_CANDIDATES_PER_ROUND`` (default 1).
  6. ``apply_fix`` for the selected candidate, threading the round-state
     versions + ``found_adaptive_set_event_ids`` from search.
  7. Derive before/after metrics from the judge report
     (``baseline.{model_miss_rate, recall_at_fixed_action_rate}`` →
     before; ``fixed.{...}`` → after if applied, else == before).
  8. When no candidate is selected (empty cards / empty intersection),
     run a baseline-vs-self judge call to get a deterministic
     before==after metrics snapshot for the round timeline.
  9. Build ``RoundState``, persist round detail, append
     ``LedgerRecord`` row. Return the ``RoundState``.

The caller (component 5's ``execute_run``) is responsible for
constructing the NEXT round's ``RunState`` from the returned round's
``model_version_after`` / ``threshold_version_after``.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any, Final, Sequence

import yaml

from atlas.blue_team.fix_applier import apply_fix, reports_dir
from atlas.blue_team.manifest import (
    DEFAULT_OUTPUTS_ROOT,
    persist_cards_as_records,
)
from atlas.blue_team.strategy_agent import (
    DEFAULT_ROUND_CONFIG_PATH,
    DefensiveFixCandidate,
    propose_fixes,
)
from atlas.judge.evaluate import evaluate_fix
from atlas.ledger.ledger import (
    DEFAULT_AGENT_ROSTER_VERSION,
    LedgerRecord,
    RoundState,
    RunState,
    append_ledger_record,
    persist_round_state,
)
from atlas.ledger.report_builder import build_round_transcript_summary
from atlas.model.loader import DEFAULT_DATA_DIR
from atlas.red_team.fraud_scenario_agent import run_search
from atlas.red_team.model_vulnerability_packager import (
    ModelVulnerabilityCard,
    package_cards,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Phase 8 evaluates ONE candidate per round. The deterministic selection
# rule picks the top-K from the proposal output. Future phases may
# raise this to handle multi-candidate rounds.
MAX_CANDIDATES_PER_ROUND: Final[int] = 1

# Synthetic defensive_fix_id for the no-candidate baseline-vs-self
# judge call. ``fix_round{N}_no_candidate_baseline_self`` keeps the
# id format public-safe + deterministic.
_NO_CANDIDATE_FIX_ID_TEMPLATE: Final[str] = "fix_round{round_id}_no_candidate_baseline_self"


# ---------------------------------------------------------------------------
# Round config loader (separate cache from strategy_agent's so tests can
# reset just one)
# ---------------------------------------------------------------------------

_ROUND_CONFIG_CACHE: dict[str, dict] = {}


def reset_caches() -> None:
    """Test-only — drop the cached round_config doc."""
    _ROUND_CONFIG_CACHE.clear()


def _load_round_entry(round_id: int, path: Path) -> dict[str, Any]:
    cache_key = str(path)
    doc = _ROUND_CONFIG_CACHE.get(cache_key)
    if doc is None:
        if not path.exists():
            raise FileNotFoundError(
                f"round_config.yaml not found at {path}. "
                "Phase 8 round engine requires config/round_config.yaml."
            )
        with path.open("r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        _ROUND_CONFIG_CACHE[cache_key] = doc
    rounds = doc.get("rounds") or []
    for entry in rounds:
        if int(entry.get("round_id", -1)) == int(round_id):
            return entry
    available = [int(e.get("round_id", -1)) for e in rounds]
    raise ValueError(
        f"unknown round_id {round_id}; available: {available}"
    )


# ---------------------------------------------------------------------------
# Deterministic candidate selection
# ---------------------------------------------------------------------------


def _select_candidates(
    candidates: Sequence[DefensiveFixCandidate],
    cards: Sequence[ModelVulnerabilityCard],
    *,
    seed: int,
    round_id: int,
    k: int = MAX_CANDIDATES_PER_ROUND,
) -> list[DefensiveFixCandidate]:
    """Pick top-K candidates with seed-controlled tie-breaking.

    Severity still leads: candidates with the highest model_miss_rate
    are eligible first. When several candidates tie, use a deterministic
    RNG split from ``(seed, round_id)`` so the same run stays
    reproducible while different Makefile-generated seeds can exercise
    different defensive_fix families.

    The ``model_miss_rate`` lookup is per-card (one card per family).
    """
    if not candidates:
        return []
    miss_rate_by_family: dict[str, float] = {
        c.family_id: c.model_miss_rate for c in cards
    }

    def _key(cand: DefensiveFixCandidate) -> tuple:
        # Resolve family from the candidate's defensive_fix_id —
        # ``fix_round{N}_{family_id}_{fix_type}``. The strategy agent
        # produces the id via ``make_defensive_fix_id``; reverse-deriving
        # the family avoids passing extra metadata through the public
        # candidate shape.
        # Family is stored in the candidate's ``description`` template
        # via ``EXPECTED_BENEFIT_TEMPLATE`` — but the simplest signal is
        # to look at the fix_id and split on the known fix_type suffix.
        for ft in ("model_calibration_fix", "policy_fix", "feature_fix"):
            suffix = f"_{ft}"
            if cand.defensive_fix_id.endswith(suffix):
                stem = cand.defensive_fix_id[: -len(suffix)]
                # stem is "fix_round{N}_{family_id}"
                # round prefix is "fix_round{N}_"
                round_prefix = f"fix_round{cand.round_id}_"
                family_id = stem[len(round_prefix):] if stem.startswith(round_prefix) else stem
                break
        else:
            family_id = "_unknown"

        miss_rate = miss_rate_by_family.get(family_id, 0.0)
        # Negate miss_rate for descending sort with sorted() (which is
        # ascending by default).
        return (-miss_rate, family_id, cand.fix_type, cand.defensive_fix_id)

    ordered = sorted(candidates, key=_key)
    out: list[DefensiveFixCandidate] = []
    remaining = list(ordered)
    h = hashlib.blake2b(
        f"{int(seed)}|{int(round_id)}|candidate_selection".encode("utf-8"),
        digest_size=4,
    ).hexdigest()
    rng = random.Random(int(h, 16))

    while remaining and len(out) < k:
        top_miss = -_key(remaining[0])[0]
        tied = [cand for cand in remaining if -_key(cand)[0] == top_miss]
        picked = tied[rng.randrange(len(tied))]
        out.append(picked)
        remaining = [cand for cand in remaining if cand.defensive_fix_id != picked.defensive_fix_id]

    return out


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


def _load_judge_report(
    judge_report_id: str, *, outputs_root: Path
) -> dict[str, Any]:
    """Load a persisted judge report by id."""
    path = reports_dir(outputs_root) / f"{judge_report_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"judge report {judge_report_id!r} not found at {path}"
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _metrics_from_report(
    report: dict[str, Any], *, applied: bool
) -> tuple[float, float, float, float]:
    """Return ``(miss_rate_before, miss_rate_after, recall_before, recall_after)``.

    When ``applied`` is False, ``after == before`` because the round-
    state versions don't advance.
    """
    baseline = report.get("baseline", {}) or {}
    fixed = report.get("fixed", {}) or {}

    miss_before = float(baseline.get("model_miss_rate", 0.0))
    recall_before = float(baseline.get("recall_at_fixed_action_rate", 0.0))
    if applied:
        miss_after = float(fixed.get("model_miss_rate", miss_before))
        recall_after = float(fixed.get("recall_at_fixed_action_rate", recall_before))
    else:
        miss_after = miss_before
        recall_after = recall_before
    return miss_before, miss_after, recall_before, recall_after


def _run_baseline_self_judge(
    *,
    run_state: RunState,
    round_id: int,
    found_adaptive_set_event_ids: list[str],
    outputs_root: Path,
    data_dir: Path,
) -> dict[str, Any]:
    """When no fix candidate is selected, run a baseline-vs-self judge
    call so the round_state still carries deterministic before==after
    metrics (Bible §18 Phase 8: "ledger can reproduce the same metrics").
    """
    fix_id = _NO_CANDIDATE_FIX_ID_TEMPLATE.format(round_id=round_id)
    report = evaluate_fix(
        run_id=run_state.run_id,
        round_id=round_id,
        defensive_fix_id=fix_id,
        baseline_model_version=run_state.current_model_version,
        candidate_model_version=run_state.current_model_version,
        baseline_threshold_version=run_state.current_threshold_version,
        candidate_threshold_version=run_state.current_threshold_version,
        found_adaptive_set_event_ids=found_adaptive_set_event_ids or None,
        data_dir=data_dir,
        outputs_root=outputs_root,
    )
    # Persist the report so the ledger can reference it.
    report_path = reports_dir(outputs_root) / f"{report['judge_report_id']}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    return report


# ---------------------------------------------------------------------------
# Path helpers — surface relative paths for the ledger row
# ---------------------------------------------------------------------------


def _vulnerability_card_path(
    card: ModelVulnerabilityCard, outputs_root: Path
) -> str:
    return f"outputs/model_vulnerabilities/{card.model_vulnerability_id}.json"


def _fix_manifest_path(defensive_fix_id: str) -> str:
    return f"outputs/defensive_fixes/{defensive_fix_id}.json"


def _judge_report_path(judge_report_id: str) -> str:
    return f"outputs/reports/{judge_report_id}.json"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def execute_one_round(
    run_state: RunState,
    round_id: int,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
    data_dir: Path = DEFAULT_DATA_DIR,
    round_config_path: Path = DEFAULT_ROUND_CONFIG_PATH,
) -> RoundState:
    """Run one deterministic round end-to-end.

    Side effects (all under ``outputs_root``):
      * persists ``ModelVulnerabilityRecord``s under
        ``model_vulnerabilities/``.
      * persists ``DefensiveFixManifest``s under ``defensive_fixes/``
        (via ``propose_fixes``).
      * persists candidate threshold YAML under ``decision_thresholds/``
        and/or candidate model artifacts under ``baseline_models/``
        (via the family-specific applier in ``apply_fix``).
      * persists a ``JudgeReport`` under ``reports/``.
      * persists a ``RoundState`` under ``runs/<run_id>.round_<NN>.json``.
      * appends one ``LedgerRecord`` to ``ledgers/<run_id>.jsonl``.

    Returns the ``RoundState``. The caller advances the next round's
    ``RunState`` from this state's ``model_version_after`` /
    ``threshold_version_after``.
    """
    round_entry = _load_round_entry(round_id, round_config_path)

    search_methods = list(round_entry.get("search_methods") or [])
    allowed_family_ids = list(round_entry.get("allowed_family_ids") or [])
    allowed_fix_types = list(round_entry.get("defensive_fix_types_allowed") or [])
    max_score_queries = int(round_entry.get("max_score_queries", 0))

    # 2. Red-team search with carry-forward versions
    search_result = run_search(
        run_id=run_state.run_id,
        round_id=round_id,
        search_methods=search_methods,
        max_score_queries=max_score_queries,
        allowed_family_ids=allowed_family_ids,
        seed=run_state.seed,
        data_dir=data_dir,
        outputs_root=outputs_root,
        round_config_path=round_config_path,
        current_model_version=run_state.current_model_version,
        current_threshold_version=run_state.current_threshold_version,
    )

    # 3. Package + persist vulnerability records (the round engine
    # bypasses the /red-team/search route and persists directly).
    cards = package_cards(
        candidates=search_result.candidates,
        round_id=round_id,
        random_baseline=search_result.by_method.get("random"),
    )
    found_ids = list(search_result.found_adaptive_set_event_ids)
    persist_cards_as_records(
        cards,
        run_id=run_state.run_id,
        found_adaptive_set_event_ids=found_ids,
        outputs_root=outputs_root,
    )

    # 4. Propose fixes (only when there are vulnerabilities to act on)
    fix_candidates: list[DefensiveFixCandidate] = []
    if cards and allowed_fix_types:
        fix_candidates = propose_fixes(
            run_id=run_state.run_id,
            round_id=round_id,
            model_vulnerability_ids=[c.model_vulnerability_id for c in cards],
            allowed_fix_types=allowed_fix_types,
            outputs_root=outputs_root,
            round_config_path=round_config_path,
            current_threshold_version=run_state.current_threshold_version,
        )

    # 5. Deterministic top-K selection
    selected = _select_candidates(
        fix_candidates,
        cards,
        seed=run_state.seed,
        round_id=round_id,
        k=MAX_CANDIDATES_PER_ROUND,
    )

    # 6+7+8. Apply selected candidate, derive metrics
    accepted_fix_id: str | None = None
    judge_report_id: str | None = None
    fix_paths: list[str] = []

    if selected:
        cand = selected[0]
        outcome = apply_fix(
            defensive_fix_id=cand.defensive_fix_id,
            outputs_root=outputs_root,
            data_dir=data_dir,
            current_model_version=run_state.current_model_version,
            current_threshold_version=run_state.current_threshold_version,
            found_adaptive_set_event_ids=found_ids,
        )
        applied = bool(outcome.applied)
        if applied:
            new_model_version = outcome.candidate_model_version
            new_threshold_version = outcome.candidate_threshold_version
            accepted_fix_id = cand.defensive_fix_id
        else:
            new_model_version = run_state.current_model_version
            new_threshold_version = run_state.current_threshold_version
        judge_report_id = outcome.judge_report_id
        fix_paths.append(_fix_manifest_path(cand.defensive_fix_id))

        report = _load_judge_report(judge_report_id, outputs_root=outputs_root)
        miss_b, miss_a, recall_b, recall_a = _metrics_from_report(
            report, applied=applied
        )
    else:
        # 8. No candidate → baseline-vs-self judge call so the round_state
        # carries deterministic before==after metrics.
        report = _run_baseline_self_judge(
            run_state=run_state,
            round_id=round_id,
            found_adaptive_set_event_ids=found_ids,
            outputs_root=outputs_root,
            data_dir=data_dir,
        )
        judge_report_id = report["judge_report_id"]
        new_model_version = run_state.current_model_version
        new_threshold_version = run_state.current_threshold_version
        miss_b, miss_a, recall_b, recall_a = _metrics_from_report(
            report, applied=False
        )

    # 9. Build RoundState, persist, append ledger row
    card_paths = [
        _vulnerability_card_path(c, outputs_root) for c in cards
    ]

    # Component 6: deterministic, closed-enum transcript summary +
    # in-process safety scan against the production rules. The flag
    # surfaces on the RoundState; the persisted run + ledger reflect it.
    selected_fix_id = selected[0].defensive_fix_id if selected else None
    transcript_summary, safety_scan_passed = build_round_transcript_summary(
        round_id=round_id,
        n_cards=len(cards),
        n_fixes=len(fix_candidates),
        selected_fix_id=selected_fix_id,
        accepted_fix_id=accepted_fix_id,
        model_version_after=new_model_version,
        threshold_version_after=new_threshold_version,
    )

    round_state = RoundState(
        run_id=run_state.run_id,
        round_id=round_id,
        status="completed",
        model_version_before=run_state.current_model_version,
        threshold_version_before=run_state.current_threshold_version,
        model_version_after=new_model_version,
        threshold_version_after=new_threshold_version,
        model_miss_rate_before=round(miss_b, 4),
        model_miss_rate_after=round(miss_a, 4),
        recall_at_fixed_action_rate_before=round(recall_b, 4),
        recall_at_fixed_action_rate_after=round(recall_a, 4),
        safety_scan_passed=safety_scan_passed,
        accepted_fix_id=accepted_fix_id,
        judge_report_id=judge_report_id,
        transcript_summary=transcript_summary,
        model_vulnerability_card_paths=card_paths,
        defensive_fix_paths=fix_paths,
    )
    persist_round_state(round_state, outputs_root=outputs_root)

    # Ledger row uses the public field names from
    # ``app/web/lib/types.ts.LedgerRecord``.
    ledger_row: LedgerRecord = {
        "run_id": run_state.run_id,
        "round_id": round_id,
        "seed": run_state.seed,
        "demo_mode": run_state.demo_mode,
        "model_version_before": run_state.current_model_version,
        "decision_threshold_version_before": run_state.current_threshold_version,
        "model_version_after": new_model_version,
        "decision_threshold_version_after": new_threshold_version,
        "agent_roster_version": DEFAULT_AGENT_ROSTER_VERSION,
        "safety_scan_passed": safety_scan_passed,
        "judge_report_path": (
            _judge_report_path(judge_report_id) if judge_report_id else ""
        ),
        # First card (if any) goes on the public ledger row; the full
        # list is in ``RoundState.model_vulnerability_card_paths``.
        "model_vulnerability_card_path": card_paths[0] if card_paths else "",
    }
    append_ledger_record(ledger_row, outputs_root=outputs_root)

    return round_state


__all__ = [
    "MAX_CANDIDATES_PER_ROUND",
    "execute_one_round",
    "reset_caches",
]
