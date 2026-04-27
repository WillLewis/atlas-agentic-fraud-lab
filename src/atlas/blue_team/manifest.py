"""Phase 7 model-vulnerability resolver + defensive-fix manifest.

Persistence layer that lets ``POST /defensive-fixes/propose`` and
``POST /defensive-fixes/apply`` resolve ``model_vulnerability_id`` and
``defensive_fix_id`` strings to structured records WITHOUT depending on
the public ``DefensiveFixCandidate.description`` prose.

Two on-disk artifacts (both under the gitignored ``outputs/`` tree):

  * ``outputs/model_vulnerabilities/<model_vulnerability_id>.json`` —
    one ``ModelVulnerabilityRecord`` per Phase 6 card emitted by
    ``POST /red-team/search``.
  * ``outputs/defensive_fixes/<defensive_fix_id>.json`` — one
    ``DefensiveFixManifest`` per proposal made by
    ``POST /defensive-fixes/propose``. Contains the structured apply
    parameters (threshold overrides, training seed, feature transforms)
    needed for deterministic apply.

JSON is emitted with ``sort_keys=True`` + 2-space indent + a trailing
newline so byte-identical-on-repeat is guaranteed.

Both directories are listed in ``.gitignore`` (``outputs/model_vulnerabilities/``
and ``outputs/defensive_fixes/``) — these artifacts are local-only and
never committed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final, TypedDict

from app.api.schemas.fix import ALLOWED_FIX_TYPES
from atlas.red_team.model_vulnerability_packager import ModelVulnerabilityCard

# ---------------------------------------------------------------------------
# Path conventions
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUTS_ROOT: Final[Path] = REPO_ROOT / "outputs"
VULNERABILITY_RECORDS_SUBDIR: Final[str] = "model_vulnerabilities"
FIX_MANIFEST_SUBDIR: Final[str] = "defensive_fixes"


def _vuln_dir(outputs_root: Path) -> Path:
    return outputs_root / VULNERABILITY_RECORDS_SUBDIR


def _manifest_dir(outputs_root: Path) -> Path:
    return outputs_root / FIX_MANIFEST_SUBDIR


# ---------------------------------------------------------------------------
# Errors — mirror Phase 4/5 ``MissingBaselineModelError`` so route handlers
# can map them uniformly to 503 with clear "run X first" hints.
# ---------------------------------------------------------------------------


class MissingVulnerabilityError(FileNotFoundError):
    """Raised when a ``model_vulnerability_id`` has no on-disk record.

    Likely cause: ``POST /red-team/search`` hasn't been run for this
    round, OR the round's outputs were cleaned. Route handlers map this
    to 503 with a "run /red-team/search first" hint.
    """


class MissingManifestError(FileNotFoundError):
    """Raised when a ``defensive_fix_id`` has no on-disk manifest.

    Likely cause: ``POST /defensive-fixes/propose`` hasn't been run for
    this fix, OR the fix's manifest was cleaned. Route handlers map this
    to 503 with a "run /defensive-fixes/propose first" hint.
    """


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class ModelVulnerabilityRecord(TypedDict):
    """Internal representation of one Phase 6 model-vulnerability card.

    Keyed by ``model_vulnerability_id`` (``mv_round{N}_{family_id}``).
    Stores enough Phase 6 context that Phase 7's strategy and family
    appliers can act deterministically without re-running the search.
    """

    model_vulnerability_id: str
    run_id: str
    round_id: int
    family_id: str
    found_adaptive_set_event_ids: list[str]
    model_miss_rate: float
    recommended_defensive_fix_types: list[str]
    summary: str


@dataclass(frozen=True)
class DefensiveFixManifest:
    """Internal manifest carrying the structured apply parameters for one
    defensive-fix candidate.

    Each field is populated only by the family that uses it; the others
    are ``None`` / empty. Component 7's ``apply_fix`` dispatches on
    ``fix_type`` and consumes the matching subset.

    Field summary by family:

      * ``policy_fix``            → ``proposed_threshold_overrides``
                                    (subset of {decline,alert,challenge}_score_threshold).
      * ``model_calibration_fix`` → ``proposed_training_seed`` +
                                    ``proposed_l2_strength``.
      * ``feature_fix``           → ``proposed_feature_transforms``
                                    (closed-enum spec names).
    """

    defensive_fix_id: str
    run_id: str
    round_id: int
    vulnerability_id: str
    fix_type: str
    proposed_threshold_overrides: dict[str, float] = field(default_factory=dict)
    proposed_training_seed: int | None = None
    proposed_l2_strength: float | None = None
    proposed_feature_transforms: tuple[str, ...] = ()
    expected_rate_limit_claim: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Deterministic ID helpers
# ---------------------------------------------------------------------------


def make_defensive_fix_id(
    round_id: int, vulnerability_id: str, fix_type: str
) -> str:
    """``fix_round{N}_{family}_{fix_type}`` form, deterministic.

    Strips the ``mv_round{N}_`` prefix from ``vulnerability_id`` to
    surface the family name directly so fix-IDs are human-readable.
    """
    if fix_type not in ALLOWED_FIX_TYPES:
        raise ValueError(
            f"unknown fix_type {fix_type!r}; expected one of {list(ALLOWED_FIX_TYPES)}"
        )
    family_part = vulnerability_id
    prefix = f"mv_round{round_id}_"
    if family_part.startswith(prefix):
        family_part = family_part[len(prefix):]
    return f"fix_round{round_id}_{family_part}_{fix_type}"


# ---------------------------------------------------------------------------
# Card → record adapter
# ---------------------------------------------------------------------------


def card_to_record(
    card: ModelVulnerabilityCard,
    *,
    run_id: str,
    found_adaptive_set_event_ids: list[str],
) -> ModelVulnerabilityRecord:
    """Convert a Phase 6 card into a persistable internal record.

    ``found_adaptive_set_event_ids`` is the orchestrator-level set
    (Phase 6's ``RedTeamSearchResult.found_adaptive_set_event_ids``).
    Phase 7 strategy/family agents use it as a hint for which events
    contributed to this round's red-team findings.
    """
    return ModelVulnerabilityRecord(
        model_vulnerability_id=card.model_vulnerability_id,
        run_id=run_id,
        round_id=card.round_id,
        family_id=card.family_id,
        found_adaptive_set_event_ids=sorted(found_adaptive_set_event_ids),
        model_miss_rate=card.model_miss_rate,
        recommended_defensive_fix_types=list(card.recommended_defensive_fix_types),
        summary=card.summary,
    )


# ---------------------------------------------------------------------------
# Disk I/O helpers
# ---------------------------------------------------------------------------


def _write_json_deterministic(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def _read_json(path: Path, missing_exc_cls: type[FileNotFoundError]) -> Any:
    if not path.exists():
        raise missing_exc_cls(
            f"Phase 7 artifact not found at {path}. "
            "Run the upstream POST endpoint to materialize it first."
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# ModelVulnerabilityRecord — persist + load + bulk
# ---------------------------------------------------------------------------


def persist_vulnerability_record(
    record: ModelVulnerabilityRecord,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> Path:
    """Write one ``ModelVulnerabilityRecord`` to
    ``outputs/model_vulnerabilities/<id>.json``. Returns the path.
    """
    path = _vuln_dir(outputs_root) / f"{record['model_vulnerability_id']}.json"
    _write_json_deterministic(path, record)
    return path


def persist_cards_as_records(
    cards: list[ModelVulnerabilityCard],
    *,
    run_id: str,
    found_adaptive_set_event_ids: list[str],
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> list[Path]:
    """Bulk: convert Phase 6 cards → records → on-disk JSON.

    Called by the Phase 7 ``POST /red-team/search`` route handler in
    component 8 right after ``package_cards``. Non-Phase-7 callers can
    skip this entirely — Phase 6 search remains pure-in-memory.
    """
    return [
        persist_vulnerability_record(
            card_to_record(
                card,
                run_id=run_id,
                found_adaptive_set_event_ids=found_adaptive_set_event_ids,
            ),
            outputs_root=outputs_root,
        )
        for card in cards
    ]


def load_vulnerability_record(
    model_vulnerability_id: str,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> ModelVulnerabilityRecord:
    """Read one ``ModelVulnerabilityRecord`` by ID.

    Raises ``MissingVulnerabilityError`` if the file is absent.
    """
    path = _vuln_dir(outputs_root) / f"{model_vulnerability_id}.json"
    raw = _read_json(path, MissingVulnerabilityError)
    return raw  # TypedDict is structural; raw dict is fine


# ---------------------------------------------------------------------------
# DefensiveFixManifest — persist + load
# ---------------------------------------------------------------------------


def persist_fix_manifest(
    manifest: DefensiveFixManifest,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> Path:
    """Write one ``DefensiveFixManifest`` to
    ``outputs/defensive_fixes/<defensive_fix_id>.json``. Returns the path.
    """
    path = _manifest_dir(outputs_root) / f"{manifest.defensive_fix_id}.json"
    payload = asdict(manifest)
    # Tuples → lists for JSON. asdict handles nested dicts already.
    payload["proposed_feature_transforms"] = list(payload["proposed_feature_transforms"])
    _write_json_deterministic(path, payload)
    return path


def load_fix_manifest(
    defensive_fix_id: str,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> DefensiveFixManifest:
    """Read one ``DefensiveFixManifest`` by ID.

    Raises ``MissingManifestError`` if the file is absent.
    """
    path = _manifest_dir(outputs_root) / f"{defensive_fix_id}.json"
    raw = _read_json(path, MissingManifestError)
    return DefensiveFixManifest(
        defensive_fix_id=raw["defensive_fix_id"],
        run_id=raw["run_id"],
        round_id=int(raw["round_id"]),
        vulnerability_id=raw["vulnerability_id"],
        fix_type=raw["fix_type"],
        proposed_threshold_overrides=dict(
            raw.get("proposed_threshold_overrides") or {}
        ),
        proposed_training_seed=raw.get("proposed_training_seed"),
        proposed_l2_strength=raw.get("proposed_l2_strength"),
        proposed_feature_transforms=tuple(
            raw.get("proposed_feature_transforms") or ()
        ),
        expected_rate_limit_claim=dict(
            raw.get("expected_rate_limit_claim") or {}
        ),
    )


__all__ = [
    "DEFAULT_OUTPUTS_ROOT",
    "DefensiveFixManifest",
    "MissingManifestError",
    "MissingVulnerabilityError",
    "ModelVulnerabilityRecord",
    "card_to_record",
    "load_fix_manifest",
    "load_vulnerability_record",
    "make_defensive_fix_id",
    "persist_cards_as_records",
    "persist_fix_manifest",
    "persist_vulnerability_record",
]
