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
# Phase 9 read helpers reuse these subdir names — kept here as the
# single source. The Phase 6/7 writers under
# ``atlas.red_team.model_vulnerability_packager`` /
# ``atlas.blue_team.manifest`` / ``atlas.blue_team.fix_applier`` continue
# to own writes; ledger read helpers only consume.
MODEL_VULNERABILITIES_SUBDIR: Final[str] = "model_vulnerabilities"
DEFENSIVE_FIXES_SUBDIR: Final[str] = "defensive_fixes"
REPORTS_SUBDIR: Final[str] = "reports"

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


class MissingJudgeReportError(FileNotFoundError):
    """``outputs/reports/<judge_report_id>.json`` is absent — surface as
    404 in Phase 9 route handlers."""


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


def model_vulnerabilities_dir(outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> Path:
    return outputs_root / MODEL_VULNERABILITIES_SUBDIR


def defensive_fixes_dir(outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> Path:
    return outputs_root / DEFENSIVE_FIXES_SUBDIR


def reports_dir(outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> Path:
    return outputs_root / REPORTS_SUBDIR


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


# ---------------------------------------------------------------------------
# Phase 9 read helpers — list runs + bulk-load round states + per-run
# vulnerability/fix records + single judge reports. All operate on the
# persisted artifacts from Phase 6/7/8; no business logic lives here.
# ---------------------------------------------------------------------------


_ROUND_STEM_SUFFIX = ".round_"


def list_run_states(
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> list[RunState]:
    """Walk ``outputs/runs/`` and load every ``RunState`` file.

    Filters out the per-round companion files (``<run_id>.round_NN.json``)
    so only the run-level snapshots are returned. Returns an empty list
    when the directory is missing or empty (no error).

    Order: newest run-state file first, with ``run_id`` as a stable
    tie-breaker. ``created_at_utc`` intentionally comes from the dataset
    reference time, so filesystem mtime is the local-dev signal for
    "the run I just generated".
    """
    rdir = runs_dir(outputs_root)
    if not rdir.exists():
        return []
    out: list[RunState] = []
    paths = sorted(
        rdir.glob("*.json"),
        key=lambda p: (-p.stat().st_mtime_ns, p.name),
    )
    for path in paths:
        # Skip per-round companion files (run_xxx.round_01.json).
        if _ROUND_STEM_SUFFIX in path.stem:
            continue
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        try:
            out.append(RunState(**raw))
        except TypeError:
            # Unexpected JSON (e.g. partial write); skip rather than
            # blowing up the listing route.
            continue
    return out


def load_round_states(
    run_id: str, outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> list[RoundState]:
    """Load every persisted ``RoundState`` for a run, ordered by
    ``round_id`` ascending.

    Returns ``[]`` when no round-state companions exist yet (e.g. a
    freshly-created run). Does not raise — callers compose with
    ``load_run_state`` to detect missing runs.
    """
    rdir = runs_dir(outputs_root)
    if not rdir.exists():
        return []
    pattern = f"{run_id}{_ROUND_STEM_SUFFIX}*.json"
    out: list[RoundState] = []
    for path in sorted(rdir.glob(pattern)):
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        out.append(RoundState(**raw))
    out.sort(key=lambda rs: rs.round_id)
    return out


def load_judge_report(
    judge_report_id: str, outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> dict[str, Any]:
    """Load one persisted judge report by id.

    Raises ``MissingJudgeReportError`` if absent so route handlers can
    map the absence uniformly to HTTP 404.
    """
    path = reports_dir(outputs_root) / f"{judge_report_id}.json"
    if not path.exists():
        raise MissingJudgeReportError(
            f"judge report not found at {path}. "
            "Run `make run-rounds` first."
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_run_model_vulnerability_records(
    run_id: str, outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> list[dict[str, Any]]:
    """Load all model-vulnerability records belonging to ``run_id``.

    Filters ``outputs/model_vulnerabilities/*.json`` by the in-record
    ``run_id`` field. Returns ``[]`` when the directory is missing or
    contains no matching records.

    Order: alphabetical by file name (deterministic across machines).
    """
    mdir = model_vulnerabilities_dir(outputs_root)
    if not mdir.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(mdir.glob("*.json")):
        with path.open("r", encoding="utf-8") as fh:
            record = json.load(fh)
        if record.get("run_id") == run_id:
            out.append(record)
    return out


def load_run_defensive_fix_manifests(
    run_id: str, outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> list[dict[str, Any]]:
    """Load all defensive-fix manifests belonging to ``run_id``.

    Filters ``outputs/defensive_fixes/*.json`` by the in-record
    ``run_id`` field. Returns ``[]`` when the directory is missing or
    contains no matching records. Used by ``RoundDetail`` projection in
    Phase 9 component 3 alongside the vulnerability + judge readers.
    """
    fdir = defensive_fixes_dir(outputs_root)
    if not fdir.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(fdir.glob("*.json")):
        with path.open("r", encoding="utf-8") as fh:
            record = json.load(fh)
        if record.get("run_id") == run_id:
            out.append(record)
    return out


__all__ = [
    "DEFAULT_AGENT_ROSTER_VERSION",
    "DEFAULT_BASELINE_MODEL_VERSION",
    "DEFAULT_BASELINE_THRESHOLD_VERSION",
    "DEFAULT_OUTPUTS_ROOT",
    "DEFENSIVE_FIXES_SUBDIR",
    "LEDGERS_SUBDIR",
    "LedgerRecord",
    "MODEL_VULNERABILITIES_SUBDIR",
    "MissingJudgeReportError",
    "MissingLedgerError",
    "MissingRunError",
    "REPORTS_SUBDIR",
    "ROUND_STATUSES",
    "RUNS_SUBDIR",
    "RUN_STATUSES",
    "RoundState",
    "RunState",
    "append_ledger_record",
    "defensive_fixes_dir",
    "ledgers_dir",
    "list_run_states",
    "load_judge_report",
    "load_ledger_records",
    "load_round_state",
    "load_round_states",
    "load_run_defensive_fix_manifests",
    "load_run_model_vulnerability_records",
    "load_run_state",
    "make_run_id",
    "model_vulnerabilities_dir",
    "persist_round_state",
    "persist_run_state",
    "read_dataset_reference_now_utc",
    "reports_dir",
    "round_state_path",
    "runs_dir",
]
