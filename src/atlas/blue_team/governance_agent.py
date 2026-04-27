"""Phase 7 governance rationale formatter.

Renders a brief, deterministic, public-safe rationale string from a
Phase 5 ``JudgeReport`` + a Phase 7 ``DefensiveFixManifest``. The
rationale points at which §16.7 conditions held / failed — drawn from
the report's ``judge_notes`` itself, not invented.

Closed-enum templates only. NEVER overrides the judge: governance text
mentions a metric VALUE only if that value is present verbatim in the
judge report.

Output shape (one line, deterministic):

  Accepted:
    "fix <id>: judge accepted under §16.7 (clean_holdout_pass=<bool>,
     locked_adaptive_holdout_pass=<bool>, drifted_holdout_pass=<bool>)"

  Rejected:
    "fix <id>: judge rejected — failed §16.7 conditions:
     <comma-separated condition names>"
"""

from __future__ import annotations

import re
from typing import Any, Final

from atlas.blue_team.manifest import DefensiveFixManifest
from atlas.judge.acceptance import ACCEPTANCE_CONDITION_KEYS

# Regex for parsing ``<condition_name>=False`` tokens out of judge_notes.
# The judge_notes format is fixed by Phase 5
# ``atlas.judge.acceptance.apply_acceptance_rule`` — see that module's
# tests for the exact shape.
_FAILED_CONDITION_RE: Final[re.Pattern[str]] = re.compile(r"\b(\w+)=False\b")


def _failed_conditions_from_notes(judge_notes: str) -> list[str]:
    """Extract failing §16.7 condition names from judge_notes.

    Filters to the canonical ``ACCEPTANCE_CONDITION_KEYS`` set so noise
    matches (e.g. ``locked_pass=False`` inside a parenthesized detail)
    don't leak into the public rationale.
    """
    matches = _FAILED_CONDITION_RE.findall(judge_notes)
    canonical = set(ACCEPTANCE_CONDITION_KEYS)
    # Preserve canonical order for byte-stability.
    return [k for k in ACCEPTANCE_CONDITION_KEYS if k in matches and k in canonical]


def format_decision(
    *, judge_report: dict[str, Any], manifest: DefensiveFixManifest
) -> str:
    """Render the governance rationale for one fix-apply outcome.

    ``judge_report`` is the dict-shaped Phase 5 ``JudgeReport``. The
    rationale only references fields that actually appear in the
    report — never invents new metric values.
    """
    accepted = bool(judge_report["accepted_by_judge"])
    fix_id = manifest.defensive_fix_id

    if accepted:
        hg = judge_report.get("holdout_generalization") or {}
        flags = []
        for key in ("clean_holdout_pass", "locked_adaptive_holdout_pass", "drifted_holdout_pass"):
            if key in hg:
                flags.append(f"{key}={bool(hg[key])}")
        if "found_adaptive_set_pass" in hg:
            flags.append(f"found_adaptive_set_pass={bool(hg['found_adaptive_set_pass'])}")
        flag_str = ", ".join(flags) if flags else "no_per_holdout_flags"
        return f"fix {fix_id}: judge accepted under §16.7 ({flag_str})"

    # Rejected — name the failed conditions.
    notes = str(judge_report.get("judge_notes", ""))
    failed = _failed_conditions_from_notes(notes)
    failed_str = ", ".join(failed) if failed else "unspecified"
    return (
        f"fix {fix_id}: judge rejected — "
        f"failed §16.7 conditions: {failed_str}"
    )


__all__ = ["format_decision"]
