"""Phase 8 deterministic transcript summary + final-report builder.

Closed-enum templates only. Public-safe by construction. Each generated
string is explicitly safety-scanned via the production
``scripts/safety_scan.py`` rules in-process; the pass/fail flag is
recorded on ``RoundState.safety_scan_passed``.

The default ``make safety-scan`` walk ignores ``outputs/**`` (per
``config/safety.yaml`` ignore_globs), so this in-process scan IS the
safety check for the persisted ledger / round / replay text. The
templates pass the scan rules cleanly; tests verify both the clean
case and the regression case (banned phrase → flag flips False).

No raw LLM transcripts; no free-form prose path.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final, Sequence

# ---------------------------------------------------------------------------
# Path conventions
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
SAFETY_CONFIG_PATH: Final[Path] = REPO_ROOT / "config" / "safety.yaml"
SCRIPTS_DIR: Final[Path] = REPO_ROOT / "scripts"

# Stable section labels per round. Surfaced in transcript summaries +
# the final report so card timelines stay byte-stable.
ROUND_LABELS: Final[dict[int, str]] = {
    0: "Baseline",
    1: "Round 1",
    2: "Round 2",
    3: "Round 3",
}

# Cached compiled rules — populated lazily on first scan call. Reset
# via ``reset_caches()`` for tests.
_RULES_CACHE: list = []


def reset_caches() -> None:
    """Test-only — drop the cached safety rules."""
    _RULES_CACHE.clear()


# ---------------------------------------------------------------------------
# In-process safety scan
# ---------------------------------------------------------------------------


def _get_rules() -> list:
    if _RULES_CACHE:
        return _RULES_CACHE
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from safety_scan import compile_rules, load_config  # type: ignore[import-not-found]

    cfg = load_config(SAFETY_CONFIG_PATH)
    rules = compile_rules(cfg)
    _RULES_CACHE.extend(rules)
    return _RULES_CACHE


def safety_scan_text(text: str) -> bool:
    """Run ``scripts/safety_scan.py`` rules in-process against ``text``.

    Returns ``True`` when NO rule's pattern matches (regardless of
    severity). Phase 8 templates are designed to pass cleanly; any
    match represents a regression that the test suite must surface.
    """
    if not text:
        return True
    rules = _get_rules()
    for rule in rules:
        for pattern in rule.patterns:
            if pattern.search(text):
                return False
    return True


# ---------------------------------------------------------------------------
# Round transcript summary
# ---------------------------------------------------------------------------


def build_round_transcript_summary(
    *,
    round_id: int,
    n_cards: int,
    n_fixes: int,
    selected_fix_id: str | None,
    accepted_fix_id: str | None,
    model_version_after: str,
    threshold_version_after: str,
) -> tuple[str, bool]:
    """Render a deterministic, public-safe round transcript.

    Closed-enum verdict tokens (``accepted`` / ``rejected`` /
    ``no_candidate``) so the surface area for unsafe text is zero —
    every token is a structural literal.

    Returns ``(summary_text, safety_scan_passed)``.
    """
    if accepted_fix_id is not None:
        verdict = "accepted"
        fix_id_token = accepted_fix_id
    elif selected_fix_id is not None:
        verdict = "rejected"
        fix_id_token = selected_fix_id
    else:
        verdict = "no_candidate"
        fix_id_token = "none"

    summary = (
        f"Round {round_id}: "
        f"red-team surfaced {n_cards} model_vulnerability cards; "
        f"bank-defense proposed {n_fixes} candidate(s); "
        f"judge {verdict} the selected candidate {fix_id_token}. "
        f"Carry-forward: model={model_version_after}, "
        f"threshold={threshold_version_after}."
    )
    return summary, safety_scan_text(summary)


# ---------------------------------------------------------------------------
# Final-report summary
# ---------------------------------------------------------------------------


def build_final_report_summary(
    *,
    run_id: str,
    total_rounds: int,
    accepted_count: int,
    miss_rate_trend: Sequence[float],
    final_model_version: str,
    final_threshold_version: str,
) -> tuple[str, bool]:
    """Render a deterministic, public-safe final-report summary.

    The trend is a sequence of per-round ``model_miss_rate_after``
    values; the template renders them as a fixed-precision arrow
    chain so the output is byte-stable across runs.

    Returns ``(summary_text, safety_scan_passed)``.
    """
    if miss_rate_trend:
        trend_str = " → ".join(f"{float(v):.4f}" for v in miss_rate_trend)
    else:
        trend_str = "(no rounds)"

    summary = (
        f"Run {run_id}: {total_rounds} rounds completed; "
        f"{accepted_count} accepted defensive fix(es); "
        f"model_miss_rate trend: {trend_str}; "
        f"final model={final_model_version}, "
        f"threshold={final_threshold_version}."
    )
    return summary, safety_scan_text(summary)


__all__ = [
    "ROUND_LABELS",
    "build_final_report_summary",
    "build_round_transcript_summary",
    "reset_caches",
    "safety_scan_text",
]
