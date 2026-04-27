"""Phase 8 run + round state objects.

Persistence layout (under the gitignored ``outputs/`` tree):

  * ``outputs/runs/<run_id>.json``      — one ``RunDetail``-shaped run
                                          snapshot per run.
  * ``outputs/ledgers/<run_id>.jsonl``  — append-only JSONL of
                                          ``LedgerRecord`` rows, one per
                                          completed round.

``run_id`` is deterministic — derived from a blake2b hash of
``(seed, run_label, demo_mode)`` so two runs with identical inputs
produce identical IDs and byte-identical artifacts.

``created_at_utc`` is sourced from the dataset manifest's
``reference_now_utc`` (NOT wall-clock) so replay artifacts stay
byte-stable across machines and re-runs.

The ``LedgerRecord`` TypedDict mirrors the web shell's
``app/web/lib/types.ts.LedgerRecord`` interface field-for-field so
Phase 9 can swap the fixture loader without renaming.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final, TypedDict

from atlas.model.loader import DEFAULT_DATA_DIR, MissingDatasetError

# ---------------------------------------------------------------------------
# Path conventions
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUTS_ROOT: Final[Path] = REPO_ROOT / "outputs"
RUNS_SUBDIR: Final[str] = "runs"
LEDGERS_SUBDIR: Final[str] = "ledgers"

DEFAULT_BASELINE_MODEL_VERSION: Final[str] = "baseline_v1"
DEFAULT_BASELINE_THRESHOLD_VERSION: Final[str] = "thresholds_v1"
DEFAULT_AGENT_ROSTER_VERSION: Final[str] = "agents_v1"

# Run status enum — matches OpenAPI ``RunSummary.status``.
RUN_STATUSES: Final[tuple[str, ...]] = ("created", "running", "completed", "failed")

# Round status enum.
ROUND_STATUSES: Final[tuple[str, ...]] = ("completed", "failed")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MissingRunError(FileNotFoundError):
    """``outputs/runs/<run_id>.json`` is absent — surface as
    503 / "run ``make run-rounds`` first"."""


class MissingLedgerError(FileNotFoundError):
    """``outputs/ledgers/<run_id>.jsonl`` is absent — surface as
    503 / "run ``make run-rounds`` first"."""


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunState:
    """Maps to the OpenAPI ``RunDetail`` shape (lines 797–807).

    The ``current_*_version`` fields track the carry-forward versions
    the round engine threads into the next round's search + apply.
    """

    run_id: str
    seed: int
    demo_mode: str
    status: str
    created_at_utc: str
    current_round: int
    current_model_version: str
    current_threshold_version: str
    run_label: str = ""
    max_rounds: int = 3


@dataclass(frozen=True)
class RoundState:
    """Maps to the OpenAPI ``RoundSummary`` + ``RoundDetail`` shapes.

    Each completed round produces one of these AND one ``LedgerRecord``.
    """

    run_id: str
    round_id: int
    status: str
    model_version_before: str
    threshold_version_before: str
    model_version_after: str
    threshold_version_after: str
    model_miss_rate_before: float
    model_miss_rate_after: float
    recall_at_fixed_action_rate_before: float
    recall_at_fixed_action_rate_after: float
    safety_scan_passed: bool
    accepted_fix_id: str | None = None
    judge_report_id: str | None = None
    transcript_summary: str = ""
    model_vulnerability_card_paths: list[str] = field(default_factory=list)
    defensive_fix_paths: list[str] = field(default_factory=list)


class LedgerRecord(TypedDict):
    """Mirrors ``app/web/lib/types.ts.LedgerRecord`` field-for-field.

    ``decision_threshold_version_before/after`` is the persisted name
    in BOTH the web types and Bible §15.6; ``RoundState`` uses the
    shorter ``threshold_version_before/after`` for ergonomics, but the
    ledger row uses the public name.
    """

    run_id: str
    round_id: int
    seed: int
    demo_mode: str
    model_version_before: str
    decision_threshold_version_before: str
    model_version_after: str
    decision_threshold_version_after: str
    agent_roster_version: str
    safety_scan_passed: bool
    judge_report_path: str
    model_vulnerability_card_path: str


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def runs_dir(outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> Path:
    return outputs_root / RUNS_SUBDIR


def ledgers_dir(outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> Path:
    return outputs_root / LEDGERS_SUBDIR


# ---------------------------------------------------------------------------
# Deterministic ``run_id``
# ---------------------------------------------------------------------------


def make_run_id(*, seed: int, run_label: str = "", demo_mode: str = "public") -> str:
    """``run_<8hex>`` derived from ``blake2b(seed|run_label|demo_mode)``.

    Same inputs → same id. Hex-only suffix avoids the safety scanner's
    13–16-digit credit-card-shape pattern.
    """
    h = hashlib.blake2b(
        f"{int(seed)}|{run_label}|{demo_mode}".encode("utf-8"),
        digest_size=4,
    ).hexdigest()
    return f"run_{h}"


# ---------------------------------------------------------------------------
# Dataset reference time — replaces wall-clock
# ---------------------------------------------------------------------------


def read_dataset_reference_now_utc(data_dir: Path = DEFAULT_DATA_DIR) -> str:
    """Read ``reference_now_utc`` from ``data/synthetic/manifest.json``.

    Phase 8 invariant: no wall-clock timestamps for run identity or
    replay content. The dataset's reference time is the single source.
    """
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        raise MissingDatasetError(
            f"dataset manifest not found at {manifest_path}. "
            "Run `make seed` first."
        )
    with manifest_path.open("r", encoding="utf-8") as fh:
        doc = json.load(fh)
    ref = doc.get("reference_now_utc")
    if not isinstance(ref, str) or not ref:
        raise ValueError(
            f"manifest.json:reference_now_utc must be a non-empty string; "
            f"got {ref!r}"
        )
    return ref


# ---------------------------------------------------------------------------
# Persist + load — ``RunState``
# ---------------------------------------------------------------------------


def _write_json_deterministic(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def persist_run_state(
    run: RunState, *, outputs_root: Path = DEFAULT_OUTPUTS_ROOT
) -> Path:
    """Write ``outputs/runs/<run_id>.json``. Sorted-key JSON."""
    path = runs_dir(outputs_root) / f"{run.run_id}.json"
    _write_json_deterministic(path, asdict(run))
    return path


def load_run_state(
    run_id: str, *, outputs_root: Path = DEFAULT_OUTPUTS_ROOT
) -> RunState:
    """Load a persisted ``RunState`` by id.

    Raises ``MissingRunError`` if absent.
    """
    path = runs_dir(outputs_root) / f"{run_id}.json"
    if not path.exists():
        raise MissingRunError(
            f"run state not found at {path}. "
            "Run `make run-rounds` first."
        )
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return RunState(**raw)


# ---------------------------------------------------------------------------
# Persist + load — ``RoundState``
# ---------------------------------------------------------------------------


def round_state_path(
    run_id: str, round_id: int, *, outputs_root: Path = DEFAULT_OUTPUTS_ROOT
) -> Path:
    """``outputs/runs/<run_id>.round_<round_id>.json`` — companion to
    ``RunState``. The run JSON carries the ``RoundSummary`` slice; the
    full per-round ``RoundDetail`` lives here.
    """
    return runs_dir(outputs_root) / f"{run_id}.round_{round_id:02d}.json"


def persist_round_state(
    round_state: RoundState, *, outputs_root: Path = DEFAULT_OUTPUTS_ROOT
) -> Path:
    """Write the per-round detail JSON. Sorted-key, byte-stable."""
    path = round_state_path(
        round_state.run_id, round_state.round_id, outputs_root=outputs_root
    )
    _write_json_deterministic(path, asdict(round_state))
    return path


def load_round_state(
    run_id: str, round_id: int, *, outputs_root: Path = DEFAULT_OUTPUTS_ROOT
) -> RoundState:
    """Load a persisted ``RoundState``.

    Raises ``MissingRunError`` if absent (using the same exception so
    route handlers map both run + round absence uniformly to 503).
    """
    path = round_state_path(run_id, round_id, outputs_root=outputs_root)
    if not path.exists():
        raise MissingRunError(
            f"round state not found at {path}. "
            "Run `make run-rounds` first."
        )
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return RoundState(**raw)


# ---------------------------------------------------------------------------
# Append + load — ``LedgerRecord`` JSONL
# ---------------------------------------------------------------------------


def append_ledger_record(
    record: LedgerRecord, *, outputs_root: Path = DEFAULT_OUTPUTS_ROOT
) -> Path:
    """Append one ``LedgerRecord`` to ``outputs/ledgers/<run_id>.jsonl``.

    Each line is a sorted-key JSON object. Identical records produce
    identical lines so re-running with the same seed yields a
    byte-identical ledger file.
    """
    run_id = record["run_id"]
    path = ledgers_dir(outputs_root) / f"{run_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return path


def load_ledger_records(
    run_id: str, *, outputs_root: Path = DEFAULT_OUTPUTS_ROOT
) -> list[LedgerRecord]:
    """Load all ``LedgerRecord`` rows for a run, in append order.

    Raises ``MissingLedgerError`` if the file is absent.
    """
    path = ledgers_dir(outputs_root) / f"{run_id}.jsonl"
    if not path.exists():
        raise MissingLedgerError(
            f"ledger not found at {path}. "
            "Run `make run-rounds` first."
        )
    out: list[LedgerRecord] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


__all__ = [
    "DEFAULT_AGENT_ROSTER_VERSION",
    "DEFAULT_BASELINE_MODEL_VERSION",
    "DEFAULT_BASELINE_THRESHOLD_VERSION",
    "DEFAULT_OUTPUTS_ROOT",
    "LEDGERS_SUBDIR",
    "LedgerRecord",
    "MissingLedgerError",
    "MissingRunError",
    "ROUND_STATUSES",
    "RUNS_SUBDIR",
    "RUN_STATUSES",
    "RoundState",
    "RunState",
    "append_ledger_record",
    "ledgers_dir",
    "load_ledger_records",
    "load_round_state",
    "load_run_state",
    "make_run_id",
    "persist_round_state",
    "persist_run_state",
    "read_dataset_reference_now_utc",
    "round_state_path",
    "runs_dir",
]
