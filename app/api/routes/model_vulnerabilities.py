"""Phase 9 per-run artifact-retrieval routes — thin wrappers over
``atlas.ledger`` readers.

Routes (matches OpenAPI lines 288–410):

  GET /runs/{run_id}/model-vulnerabilities
      → { model_vulnerabilities: ModelVulnerabilityRecord[] }
  GET /runs/{run_id}/judge-reports/{judge_report_id}
      → JudgeReport-shaped dict

Both routes:
  * verify the parent ``RunState`` exists (404 otherwise),
  * filter persisted artifacts by ``run_id`` (vulnerability records) or
    by id-with-ownership-check (judge reports),
  * return the records / report verbatim.

The vulnerability listing returns ``[]`` when no records exist for the
run yet — a freshly-created run before any red-team search.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from atlas.ledger.ledger import (  # noqa: E402
    MissingJudgeReportError,
    MissingRunError,
    load_judge_report,
    load_run_model_vulnerability_records,
    load_run_state,
)

router = APIRouter()


OUTPUTS_ROOT: Path = REPO_ROOT / "outputs"


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/model-vulnerabilities
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}/model-vulnerabilities")
def get_run_model_vulnerabilities(run_id: str) -> dict:
    try:
        load_run_state(run_id, outputs_root=OUTPUTS_ROOT)
    except MissingRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    records = load_run_model_vulnerability_records(
        run_id, outputs_root=OUTPUTS_ROOT,
    )
    return {"model_vulnerabilities": records}


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/judge-reports/{judge_report_id}
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}/judge-reports/{judge_report_id}")
def get_run_judge_report(run_id: str, judge_report_id: str) -> dict:
    """Load a judge report and verify it belongs to ``run_id``.

    Mismatched ownership → 404 (not 403) so the route doesn't reveal
    whether a report exists for a different run.
    """
    try:
        load_run_state(run_id, outputs_root=OUTPUTS_ROOT)
    except MissingRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        report = load_judge_report(judge_report_id, outputs_root=OUTPUTS_ROOT)
    except MissingJudgeReportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if report.get("run_id") != run_id:
        raise HTTPException(
            status_code=404,
            detail=(
                f"judge report {judge_report_id!r} does not belong to "
                f"run {run_id!r}."
            ),
        )
    return report
