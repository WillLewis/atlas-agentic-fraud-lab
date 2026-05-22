"""Decision-threshold overlay + deterministic reason codes (Phase 4).

Maps a calibrated score plus ``FeatureVector`` context to a
``DecisionPolicyResult`` carrying:

  * ``decision_action``  ∈ ``{accept, challenge, alert, decline}``
  * ``decision_band``    — band label from
                           ``config/decision_thresholds.yaml.decision_bands``
  * ``threshold_version`` — from
                           ``config/decision_thresholds.yaml.decision_threshold_version``
  * ``reason_codes``      — ordered subset of
                           ``config/decision_thresholds.yaml.allowed_reason_codes``

Phase 4 invariants:
  * Thresholds + band labels read from
    ``config/decision_thresholds.yaml`` — never hard-coded.
  * Reason codes derived deterministically from the feature vector and
    the safe config. No free-form text, no LLM calls.
  * Action set is exactly four values. There is NO ``review`` action,
    despite ``manual_review_rate_limit_pct`` existing in config (that's
    a friction limit, not an action).
  * Same ``(score, feature_vector, config)`` → identical
    ``DecisionPolicyResult``. Reason codes preserve config-allow-list
    order, so output is byte-stable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

from atlas.synthetic.features import FeatureVector

# ---------------------------------------------------------------------------
# Path conventions + decision-action allow-list
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_THRESHOLDS_CONFIG_PATH: Final[Path] = (
    REPO_ROOT / "config" / "decision_thresholds.yaml"
)
DEFAULT_OUTPUTS_ROOT: Final[Path] = REPO_ROOT / "outputs"
DECISION_THRESHOLDS_SUBDIR: Final[str] = "decision_thresholds"
DEFAULT_DECISION_THRESHOLDS_OUTPUT_DIR: Final[Path] = (
    DEFAULT_OUTPUTS_ROOT / DECISION_THRESHOLDS_SUBDIR
)

# Phase 4 decision-action allow-list. NO 'review'.
DECISION_ACTIONS: Final[tuple[str, ...]] = ("accept", "challenge", "alert", "decline")

# ---------------------------------------------------------------------------
# Reason-code triggering thresholds
#
# Each `allowed_reason_codes` entry in config maps to ONE deterministic
# condition on the FeatureVector (or score). These are tunables; tests
# pin them so policy behavior is reproducible across runs.
# ---------------------------------------------------------------------------

REASON_CODE_THRESHOLDS: Final[dict[str, float]] = {
    # device_count_72h >= this → recent_activity_change
    "device_count_72h_min": 2,
    # entity_graph_risk_score >= this → entity_graph_risk
    "entity_graph_risk_score_min": 0.7,
    # current_device_tenure_days <= this → device_novelty
    "current_device_tenure_days_max": 7,
    # password_recovery_count_72h >= this → security_recovery_recent
    "password_recovery_count_72h_min": 1,
    # cash_movement_velocity_score >= this → cash_movement_velocity_high
    "cash_movement_velocity_score_min": 0.7,
    # recipient_tenure_days <= this → new_recipient_low_tenure
    "recipient_tenure_days_max": 7,
    # shared_device_degree >= this → shared_device_high_degree
    "shared_device_degree_min": 5,
    # shared_recipient_degree >= this → shared_recipient_high_degree
    "shared_recipient_degree_min": 5,
    # |score - threshold| <= this → score_boundary_cluster
    "score_boundary_band": 0.05,
}

# Tiny epsilon added to the score_boundary_cluster comparison so float
# noise from arithmetic like 0.79 - 0.74 = 0.05000000000000004 doesn't
# flip the boundary check. Still deterministic.
SCORE_BOUNDARY_FLOAT_TOLERANCE: Final[float] = 1e-9

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionPolicyConfig:
    """Materialized view of ``config/decision_thresholds.yaml`` for the
    Phase 4 decision overlay.

    Loaded once at API startup via ``load_decision_policy_config``;
    threaded into every ``apply_decision_policy`` call.
    """

    threshold_version: str
    decline_score_threshold: float
    alert_score_threshold: float
    challenge_score_threshold: float
    # Per-action band labels (e.g. "accept" -> "accept_threshold_band").
    decision_bands: dict[str, str]
    # The full allow-list. Order is preserved from the YAML and used as
    # the canonical reason-code emission order.
    allowed_reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class DecisionPolicyResult:
    """Pure-function output of ``apply_decision_policy``.

    Maps directly into the OpenAPI ``ScoreResponse`` shape: the route
    handler in component 6 will compose ``event_id`` + ``model_version``
    around this result.
    """

    score: float
    decision_action: str
    decision_band: str
    threshold_version: str
    reason_codes: tuple[str, ...]


class UnknownThresholdVersionError(ValueError):
    """Raised when a requested threshold version has no backing YAML file."""


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def load_decision_policy_config(
    path: Path = DEFAULT_THRESHOLDS_CONFIG_PATH,
) -> DecisionPolicyConfig:
    """Read ``config/decision_thresholds.yaml`` and materialize a typed view.

    Translates the persisted-config field name
    ``decision_threshold_version`` to the API's ``threshold_version`` at
    this boundary so the route handler can pass the result through to
    ``ScoreResponse`` without further translation.

    Validates that all four ``decision_bands`` keys exist and that
    ``allowed_reason_codes`` is non-empty.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"decision-thresholds config not found at {path}. "
            "Phase 4 requires config/decision_thresholds.yaml to exist."
        )
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    threshold_version = raw.get("decision_threshold_version")
    if not isinstance(threshold_version, str) or not threshold_version:
        raise ValueError(
            "decision_threshold_version must be a non-empty string in "
            f"{path}"
        )

    thresholds = raw.get("decision_thresholds") or {}
    decline = float(thresholds["decline_score_threshold"])
    alert = float(thresholds["alert_score_threshold"])
    challenge = float(thresholds["challenge_score_threshold"])
    if not (0.0 <= challenge <= alert <= decline <= 1.0):
        raise ValueError(
            f"decision-thresholds must satisfy "
            f"0 <= challenge ({challenge}) <= alert ({alert}) "
            f"<= decline ({decline}) <= 1"
        )

    bands_raw = raw.get("decision_bands") or {}
    decision_bands: dict[str, str] = {}
    for action, band_key in (
        ("accept", "accept_band"),
        ("challenge", "challenge_band"),
        ("alert", "alert_band"),
        ("decline", "decline_band"),
    ):
        band_label = bands_raw.get(band_key)
        if not isinstance(band_label, str) or not band_label:
            raise ValueError(
                f"decision_bands.{band_key} must be a non-empty string in {path}"
            )
        decision_bands[action] = band_label

    allowed = raw.get("allowed_reason_codes") or []
    if not allowed or not all(isinstance(rc, str) and rc for rc in allowed):
        raise ValueError(
            f"allowed_reason_codes must be a non-empty list of strings in {path}"
        )

    return DecisionPolicyConfig(
        threshold_version=threshold_version,
        decline_score_threshold=decline,
        alert_score_threshold=alert,
        challenge_score_threshold=challenge,
        decision_bands=decision_bands,
        allowed_reason_codes=tuple(allowed),
    )


def _dedup_paths(paths: list[Path]) -> tuple[Path, ...]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return tuple(out)


def resolve_decision_thresholds_path(
    threshold_version: str | None = None,
    *,
    outputs_root: Path | None = DEFAULT_OUTPUTS_ROOT,
    alternate_thresholds_root: Path | None = None,
    template_path: Path = DEFAULT_THRESHOLDS_CONFIG_PATH,
) -> Path:
    """Resolve the YAML file for a decision-threshold version.

    Resolution is intentionally shared by API scoring, red-team search,
    bank-defense proposals, and the judge:

      1. ``outputs_root/decision_thresholds/<version>.yaml`` when an
         ``outputs_root`` is provided.
      2. ``alternate_thresholds_root/<version>.yaml`` when supplied.
      3. ``config/decision_thresholds.yaml`` only when the requested
         version matches that template's own ``decision_threshold_version``.

    This lets fitted ``thresholds_v1.yaml`` artifacts and policy-fix
    candidate thresholds win over the static demo template, while keeping
    a fresh checkout usable before ``make train`` has produced outputs.
    """
    template = load_decision_policy_config(template_path)
    requested = threshold_version or template.threshold_version

    roots: list[Path] = []
    if outputs_root is not None:
        roots.append(outputs_root / DECISION_THRESHOLDS_SUBDIR)
    if alternate_thresholds_root is not None:
        roots.append(alternate_thresholds_root)

    searched: list[Path] = []
    for root in _dedup_paths(roots):
        candidate_path = root / f"{requested}.yaml"
        searched.append(candidate_path)
        if not candidate_path.exists():
            continue
        candidate = load_decision_policy_config(candidate_path)
        if candidate.threshold_version != requested:
            raise UnknownThresholdVersionError(
                f"decision-threshold file {candidate_path} declares "
                f"decision_threshold_version={candidate.threshold_version!r} "
                f"but was requested as {requested!r}."
            )
        return candidate_path

    if requested == template.threshold_version:
        return template_path

    searched_text = ", ".join(str(p) for p in searched) or "<no output roots>"
    raise UnknownThresholdVersionError(
        f"unknown threshold_version {requested!r}; "
        f"not the in-repo {template.threshold_version!r} and no "
        f"candidate file at {searched_text}."
    )


def resolve_decision_policy_config(
    threshold_version: str | None = None,
    *,
    outputs_root: Path | None = DEFAULT_OUTPUTS_ROOT,
    alternate_thresholds_root: Path | None = None,
    template_path: Path = DEFAULT_THRESHOLDS_CONFIG_PATH,
) -> DecisionPolicyConfig:
    """Resolve and load the effective decision-policy config."""
    path = resolve_decision_thresholds_path(
        threshold_version,
        outputs_root=outputs_root,
        alternate_thresholds_root=alternate_thresholds_root,
        template_path=template_path,
    )
    return load_decision_policy_config(path)


# ---------------------------------------------------------------------------
# Reason-code derivation
# ---------------------------------------------------------------------------


def _derive_reason_codes(
    score: float, fv: FeatureVector, config: DecisionPolicyConfig
) -> tuple[str, ...]:
    """Compute the set of triggered reason codes, then emit in
    config-allow-list order.

    Each reason code maps to ONE deterministic feature condition. Output
    is filtered through ``config.allowed_reason_codes`` so a misconfigured
    code (one missing from the allow-list) is silently dropped — keeping
    the API contract that reason codes are strictly a subset of the
    allow-list.
    """
    t = REASON_CODE_THRESHOLDS
    triggered: set[str] = set()

    if fv["device_count_72h"] >= t["device_count_72h_min"]:
        triggered.add("recent_activity_change")
    if fv["entity_graph_risk_score"] >= t["entity_graph_risk_score_min"]:
        triggered.add("entity_graph_risk")
    if fv["current_device_tenure_days"] <= t["current_device_tenure_days_max"]:
        triggered.add("device_novelty")
    if fv["password_recovery_count_72h"] >= t["password_recovery_count_72h_min"]:
        triggered.add("security_recovery_recent")
    if fv["cash_movement_velocity_score"] >= t["cash_movement_velocity_score_min"]:
        triggered.add("cash_movement_velocity_high")
    if fv["recipient_tenure_days"] <= t["recipient_tenure_days_max"]:
        triggered.add("new_recipient_low_tenure")
    if fv["geo_consistency_flag"] == 0:
        triggered.add("region_change_recent")
    if fv["shared_device_degree"] >= t["shared_device_degree_min"]:
        triggered.add("shared_device_high_degree")
    if fv["shared_recipient_degree"] >= t["shared_recipient_degree_min"]:
        triggered.add("shared_recipient_high_degree")

    # score_boundary_cluster: score within ±band of any decision threshold.
    # The +SCORE_BOUNDARY_FLOAT_TOLERANCE handles IEEE-754 representation
    # noise (e.g. ``0.79 - 0.74 = 0.05000000000000004``) so the boundary
    # remains semantically inclusive without flipping at the float-edge.
    band = t["score_boundary_band"]
    score_thresholds = (
        config.challenge_score_threshold,
        config.alert_score_threshold,
        config.decline_score_threshold,
    )
    if any(
        abs(score - thr) <= band + SCORE_BOUNDARY_FLOAT_TOLERANCE
        for thr in score_thresholds
    ):
        triggered.add("score_boundary_cluster")

    # Filter through the config allow-list AND emit in allow-list order.
    return tuple(rc for rc in config.allowed_reason_codes if rc in triggered)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_decision_policy(
    score: float, feature_vector: FeatureVector, config: DecisionPolicyConfig
) -> DecisionPolicyResult:
    """Apply the decision-threshold overlay + reason codes.

    Args:
        score: Calibrated score in ``[0, 1]`` from
            ``atlas.model.scorer.score_features``.
        feature_vector: The 17-field ``FeatureVector`` used for both
            scoring and reason-code derivation. ``synthetic_truth_label``
            is NOT on this type, so label leakage at decision time is
            structurally impossible.
        config: Loaded ``DecisionPolicyConfig`` (one per process).

    Returns:
        Frozen ``DecisionPolicyResult`` with deterministic action, band,
        threshold_version, and ordered reason_codes.

    Raises:
        ValueError: if ``score`` is outside ``[0, 1]`` or non-finite.
    """
    # Guard: only finite scores in [0, 1] are valid. The calibrator output
    # is bounded by construction, but defensive validation surfaces any
    # upstream bug at the boundary.
    if not (0.0 <= score <= 1.0):
        raise ValueError(f"score must be in [0, 1], got {score!r}")

    if score >= config.decline_score_threshold:
        action = "decline"
    elif score >= config.alert_score_threshold:
        action = "alert"
    elif score >= config.challenge_score_threshold:
        action = "challenge"
    else:
        action = "accept"

    band = config.decision_bands[action]
    reason_codes = _derive_reason_codes(score, feature_vector, config)

    return DecisionPolicyResult(
        score=score,
        decision_action=action,
        decision_band=band,
        threshold_version=config.threshold_version,
        reason_codes=reason_codes,
    )
