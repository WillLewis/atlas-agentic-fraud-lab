"""Phase 8 replay-payload builder.

Builds a public-safe ``ReplayPayload``-shaped JSON file under
``outputs/demo_replays/<run_id>.json``. Field names mirror
``app/web/lib/types.ts`` so Phase 9 can swap the fixture loader in
``app/web/lib/fixtures.ts`` without component rewrites.

Structure (matches OpenAPI ``ReplayPayload`` lines 1107–1119):

    {
      "run":              RunDetail-shaped,
      "five_step_story":  [{step_id, title, cards}, ...],
      "charts":           {"round_metrics": MetricSnapshot[]},
      "round_details":    [RoundDetail-shaped, ...]
    }

Five-step narrative follows Bible §8:

  1. Agents are assigned       — agent roster from config/agent_roster.yaml
  2. Agents are deployed       — synthetic environment counts from
                                 data/synthetic/manifest.json
  3. Round 1                   — red-team + fix + judge cards
  4. Round 2                   — adaptive pressure
  5. Round 3 (final report)    — model_miss_rate trend, accepted-count,
                                 final-report summary

``MetricSnapshot`` field names (Phase 1 web shell types):
  round_id, round_label, kind ∈ {"baseline", "fixed"},
  model_miss_rate, recall_at_fixed_action_rate,
  false_positive_rate_at_fixed_action_rate, synthetic_loss_allowed,
  challenge_rate, alert_rate, decline_rate.

Phase 8 only emits ``"baseline"`` (round 0) and ``"fixed"`` (rounds 1+);
``"interpolated"`` (Phase 1 placeholder) never appears.

Replay payload is derived only from authoritative artifacts:
  * RunState (outputs/runs/<run_id>.json)
  * RoundStates (outputs/runs/<run_id>.round_NN.json)
  * Judge reports (outputs/reports/<judge_report_id>.json)
  * config/agent_roster.yaml (read-only)
  * data/synthetic/manifest.json (read-only)
No invented metrics, no synthesized text outside the closed-enum
templates.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final, Sequence, TypedDict

import yaml

from atlas.blue_team.fix_applier import reports_dir
from atlas.ledger.ledger import (
    DEFAULT_OUTPUTS_ROOT,
    RoundState,
    RunState,
    load_run_defensive_fix_manifests,
    load_run_model_vulnerability_records,
)
from atlas.ledger.report_builder import ROUND_LABELS, build_final_report_summary
from atlas.model.loader import DEFAULT_DATA_DIR

# ---------------------------------------------------------------------------
# Path conventions
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_AGENT_ROSTER_PATH: Final[Path] = REPO_ROOT / "config" / "agent_roster.yaml"
DEMO_REPLAYS_SUBDIR: Final[str] = "demo_replays"

METRIC_SNAPSHOT_KINDS: Final[tuple[str, ...]] = ("baseline", "fixed")


def demo_replays_dir(outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> Path:
    return outputs_root / DEMO_REPLAYS_SUBDIR


class ReplayPayload(TypedDict):
    """Public-safe replay envelope. Mirrors the OpenAPI shape."""

    run: dict
    five_step_story: list[dict]
    charts: dict
    round_details: list[dict]


# ---------------------------------------------------------------------------
# Internal: load judge reports for each round
# ---------------------------------------------------------------------------


def _load_judge_reports(
    round_states: Sequence[RoundState], outputs_root: Path
) -> dict[int, dict[str, Any]]:
    """Map ``round_id → judge_report dict``. Missing reports are
    silently skipped — the chart fields default to 0.0 in that case.
    """
    out: dict[int, dict[str, Any]] = {}
    rdir = reports_dir(outputs_root)
    for rs in round_states:
        if not rs.judge_report_id:
            continue
        path = rdir / f"{rs.judge_report_id}.json"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            out[rs.round_id] = json.load(fh)
    return out


# ---------------------------------------------------------------------------
# MetricSnapshot construction
# ---------------------------------------------------------------------------


def _make_snapshot(
    *,
    round_id: int,
    round_label: str,
    kind: str,
    metric_dict: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build one ``MetricSnapshot`` row.

    Field names mirror ``app/web/lib/types.ts.MetricSnapshot`` exactly.
    Missing metrics default to 0.0 — the web shell tolerates that today
    and Phase 5 judge reports always populate the required fields.
    """
    md = metric_dict or {}
    return {
        "round_id": round_id,
        "round_label": round_label,
        "kind": kind,
        "model_miss_rate": float(md.get("model_miss_rate", 0.0)),
        "recall_at_fixed_action_rate": float(
            md.get("recall_at_fixed_action_rate", 0.0)
        ),
        "false_positive_rate_at_fixed_action_rate": float(
            md.get("false_positive_rate_at_fixed_action_rate", 0.0)
        ),
        "synthetic_loss_allowed": float(md.get("synthetic_loss_allowed", 0.0)),
        "challenge_rate": float(md.get("challenge_rate", 0.0)),
        "alert_rate": float(md.get("alert_rate", 0.0)),
        "decline_rate": float(md.get("decline_rate", 0.0)),
    }


def _build_round_metrics(
    round_states: Sequence[RoundState],
    judge_reports: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the ``round_metrics`` chart series.

      * Round 0 (Baseline): take round 1's judge report's ``baseline``
        side. That captures the universe's starting state under
        ``baseline_v1`` / ``thresholds_v1``.
      * Round N (1..max): if the round accepted a candidate, take the
        judge report's ``fixed`` side; otherwise take ``baseline`` (which
        equals the carry-forward state since rejection holds versions).
    """
    out: list[dict[str, Any]] = []

    if round_states:
        first_rid = round_states[0].round_id
        first_report = judge_reports.get(first_rid, {})
        out.append(
            _make_snapshot(
                round_id=0,
                round_label=ROUND_LABELS.get(0, "Baseline"),
                kind="baseline",
                metric_dict=first_report.get("baseline"),
            )
        )

    for rs in round_states:
        report = judge_reports.get(rs.round_id, {})
        if rs.accepted_fix_id:
            metric_dict = report.get("fixed")
        else:
            # No carry-forward; the round's "after" state == "before"
            # state, which is exactly the report's baseline side.
            metric_dict = report.get("baseline")
        out.append(
            _make_snapshot(
                round_id=rs.round_id,
                round_label=ROUND_LABELS.get(
                    rs.round_id, f"Round {rs.round_id}"
                ),
                kind="fixed",
                metric_dict=metric_dict,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Internal: five-step story builders
# ---------------------------------------------------------------------------


# Step titles match Bible §8 narrative structure.
_STEP_TITLES: Final[dict[int, str]] = {
    1: "Agents are assigned",
    2: "Agents are deployed",
    3: "Round 1 — red-team test and bank-defense response",
    4: "Round 2 — adaptive pressure",
    5: "Round 3 — final evaluation report",
}


def _step1_agents_assigned(agent_roster_path: Path) -> dict[str, Any]:
    """Cards drawn from ``config/agent_roster.yaml`` (read-only).

    Public-safe by construction — every card field is a literal value
    from the configuration; no synthesis.
    """
    cards: list[dict[str, Any]] = []
    if agent_roster_path.exists():
        with agent_roster_path.open("r", encoding="utf-8") as fh:
            roster = yaml.safe_load(fh) or {}
        for agent in (roster.get("red_team") or []):
            cards.append(
                {
                    "category": "red_team",
                    "agent_id": agent.get("id", ""),
                    "purpose": agent.get("purpose", ""),
                }
            )
        for agent in (roster.get("bank_defense") or []):
            cards.append(
                {
                    "category": "bank_defense",
                    "agent_id": agent.get("id", ""),
                    "purpose": agent.get("purpose", ""),
                }
            )
        judge = roster.get("deterministic_judge") or {}
        if judge:
            cards.append(
                {
                    "category": "deterministic_judge",
                    "agent_id": judge.get("id", "evaluation_judge"),
                    "purpose": (
                        "Code, not an LLM. Owns metrics, holdout evaluation, "
                        "defensive fix acceptance."
                    ),
                }
            )
    return {"step_id": 1, "title": _STEP_TITLES[1], "cards": cards}


def _step2_environment(data_dir: Path) -> dict[str, Any]:
    """Cards summarizing the synthetic environment (counts only, no PII).

    The manifest's ``counts`` is a nested dict
    (``global``, ``by_partition``, ``feature_vectors_by_partition``).
    Phase 8 surfaces the ``global`` counts since those are the
    Bible §8 "Step 2 environment" headline numbers.
    """
    cards: list[dict[str, Any]] = []
    manifest_path = data_dir / "manifest.json"
    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        counts = manifest.get("counts") or {}
        # Support both flat (legacy) and nested-with-``global`` (current)
        # manifest shapes.
        global_counts = (
            counts.get("global") if isinstance(counts.get("global"), dict) else counts
        )
        for key in sorted(global_counts):
            value = global_counts[key]
            if isinstance(value, (int, float)):
                cards.append(
                    {
                        "category": "environment",
                        "key": key,
                        "value": int(value),
                    }
                )
    return {"step_id": 2, "title": _STEP_TITLES[2], "cards": cards}


def _step_round(
    *,
    step_id: int,
    round_state: RoundState | None,
) -> dict[str, Any]:
    """Per-round step (steps 3, 4, 5).

    Cards are slim summaries of the round_state — public-safe by virtue
    of the structured artifact (transcript_summary already passed the
    in-process safety scan via component 6).
    """
    cards: list[dict[str, Any]] = []
    if round_state is not None:
        cards.append(
            {
                "category": "round_summary",
                "round_id": round_state.round_id,
                "model_version_before": round_state.model_version_before,
                "model_version_after": round_state.model_version_after,
                "threshold_version_before": round_state.threshold_version_before,
                "threshold_version_after": round_state.threshold_version_after,
                "model_miss_rate_before": round_state.model_miss_rate_before,
                "model_miss_rate_after": round_state.model_miss_rate_after,
                "accepted_fix_id": round_state.accepted_fix_id or "",
                "judge_report_id": round_state.judge_report_id or "",
                "transcript_summary": round_state.transcript_summary,
                "safety_scan_passed": round_state.safety_scan_passed,
            }
        )
    return {
        "step_id": step_id,
        "title": _STEP_TITLES.get(step_id, f"Step {step_id}"),
        "cards": cards,
    }


def _step5_final_round_with_report(
    *,
    run_state: RunState,
    round_state: RoundState | None,
    round_states: Sequence[RoundState],
) -> dict[str, Any]:
    """Step 5 = round 3 cards + final-report summary card."""
    cards: list[dict[str, Any]] = []
    if round_state is not None:
        cards.append(
            {
                "category": "round_summary",
                "round_id": round_state.round_id,
                "model_version_before": round_state.model_version_before,
                "model_version_after": round_state.model_version_after,
                "threshold_version_before": round_state.threshold_version_before,
                "threshold_version_after": round_state.threshold_version_after,
                "model_miss_rate_before": round_state.model_miss_rate_before,
                "model_miss_rate_after": round_state.model_miss_rate_after,
                "accepted_fix_id": round_state.accepted_fix_id or "",
                "judge_report_id": round_state.judge_report_id or "",
                "transcript_summary": round_state.transcript_summary,
                "safety_scan_passed": round_state.safety_scan_passed,
            }
        )

    accepted_count = sum(1 for r in round_states if r.accepted_fix_id is not None)
    miss_rate_trend = [r.model_miss_rate_after for r in round_states]
    summary, summary_passed = build_final_report_summary(
        run_id=run_state.run_id,
        total_rounds=len(round_states),
        accepted_count=accepted_count,
        miss_rate_trend=miss_rate_trend,
        final_model_version=run_state.current_model_version,
        final_threshold_version=run_state.current_threshold_version,
    )
    cards.append(
        {
            "category": "final_report",
            "summary": summary,
            "safety_scan_passed": summary_passed,
            "accepted_count": accepted_count,
            "miss_rate_trend": miss_rate_trend,
            "final_model_version": run_state.current_model_version,
            "final_threshold_version": run_state.current_threshold_version,
        }
    )

    return {
        "step_id": 5,
        "title": _STEP_TITLES[5],
        "cards": cards,
    }


# ---------------------------------------------------------------------------
# RunDetail construction
# ---------------------------------------------------------------------------


def _round_summary_dict(rs: RoundState) -> dict[str, Any]:
    """Project a ``RoundState`` to the OpenAPI ``RoundSummary`` shape."""
    return {
        "run_id": rs.run_id,
        "round_id": rs.round_id,
        "status": rs.status,
        "model_version_before": rs.model_version_before,
        "model_version_after": rs.model_version_after,
        "model_miss_rate_before": rs.model_miss_rate_before,
        "model_miss_rate_after": rs.model_miss_rate_after,
        "recall_at_fixed_action_rate_before": rs.recall_at_fixed_action_rate_before,
        "recall_at_fixed_action_rate_after": rs.recall_at_fixed_action_rate_after,
    }


def _build_round_details(
    run_id: str,
    round_states: Sequence[RoundState],
    judge_reports: dict[int, dict[str, Any]],
    outputs_root: Path,
) -> list[dict[str, Any]]:
    """Build static ``RoundDetail`` rows for public replay exports.

    The local API still owns dynamic round-detail routes. This projection
    mirrors those routes so the Cloudflare static build can render the
    same cards without exposing the local mock API.
    """
    model_vulnerabilities = load_run_model_vulnerability_records(
        run_id, outputs_root=outputs_root
    )
    defensive_fixes = load_run_defensive_fix_manifests(
        run_id, outputs_root=outputs_root
    )
    details: list[dict[str, Any]] = []
    for rs in round_states:
        body = _round_summary_dict(rs)
        body["model_vulnerabilities"] = [
            r for r in model_vulnerabilities if r.get("round_id") == rs.round_id
        ]
        body["defensive_fixes"] = [
            r for r in defensive_fixes if r.get("round_id") == rs.round_id
        ]
        report = judge_reports.get(rs.round_id)
        body["judge_reports"] = [report] if report is not None else []
        body["transcript_summary"] = rs.transcript_summary or None
        body["safety_scan_passed"] = rs.safety_scan_passed
        details.append(body)
    return details


def _build_run_detail(
    run_state: RunState,
    round_states: Sequence[RoundState],
    round_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the OpenAPI ``RunDetail`` payload (RunSummary + rounds +
    latest_metrics).
    """
    return {
        "run_id": run_state.run_id,
        "seed": run_state.seed,
        "demo_mode": run_state.demo_mode,
        "status": run_state.status,
        "current_round": run_state.current_round,
        "created_at_utc": run_state.created_at_utc,
        "rounds": [_round_summary_dict(rs) for rs in round_states],
        "latest_metrics": round_metrics[-1] if round_metrics else None,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_replay_payload(
    run_state: RunState,
    round_states: Sequence[RoundState],
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
    data_dir: Path = DEFAULT_DATA_DIR,
    agent_roster_path: Path = DEFAULT_AGENT_ROSTER_PATH,
) -> ReplayPayload:
    """Assemble the public-safe replay payload.

    Side effect: NONE. The caller calls ``persist_replay_payload`` to
    write the JSON.
    """
    judge_reports = _load_judge_reports(round_states, outputs_root)
    round_metrics = _build_round_metrics(round_states, judge_reports)
    round_details = _build_round_details(
        run_state.run_id, round_states, judge_reports, outputs_root
    )

    # Five-step narrative — Bible §8.
    rounds_by_id = {rs.round_id: rs for rs in round_states}
    five_step = [
        _step1_agents_assigned(agent_roster_path),
        _step2_environment(data_dir),
        _step_round(step_id=3, round_state=rounds_by_id.get(1)),
        _step_round(step_id=4, round_state=rounds_by_id.get(2)),
        _step5_final_round_with_report(
            run_state=run_state,
            round_state=rounds_by_id.get(3),
            round_states=round_states,
        ),
    ]

    run_detail = _build_run_detail(run_state, round_states, round_metrics)

    return ReplayPayload(
        run=run_detail,
        five_step_story=five_step,
        charts={"round_metrics": round_metrics},
        round_details=round_details,
    )


def persist_replay_payload(
    payload: ReplayPayload,
    *,
    run_id: str,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> Path:
    """Write the replay JSON. Sorted-key, byte-stable."""
    path = demo_replays_dir(outputs_root) / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    return path


__all__ = [
    "DEMO_REPLAYS_SUBDIR",
    "METRIC_SNAPSHOT_KINDS",
    "ReplayPayload",
    "build_replay_payload",
    "demo_replays_dir",
    "persist_replay_payload",
]
