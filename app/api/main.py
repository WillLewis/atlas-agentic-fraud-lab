"""FastAPI entry point for the local-only Project Atlas service.

Phase 4 surface (components 5 + 6):

  GET  /health
  GET  /config/demo
  GET  /schema
  GET  /decision-thresholds
  GET  /synthetic/sample
  POST /score
  POST /batch-score

Phase 5 surface:

  POST /judge/evaluate-fix

Phase 6 surface:

  POST /red-team/search

Phase 7 surface:

  POST /defensive-fixes/propose
  POST /defensive-fixes/apply

Phase 9 surface:

  POST /runs
  GET  /runs
  GET  /runs/{run_id}
  GET  /runs/{run_id}/rounds
  GET  /runs/{run_id}/rounds/{round_id}
  POST /rounds/run
  GET  /runs/{run_id}/model-vulnerabilities
  GET  /runs/{run_id}/judge-reports/{judge_report_id}
  GET  /replay/{run_id}

Phase 10 surface:

  POST /safety/scan
  GET  /model-quality-matrix

The service binds to ``127.0.0.1:8000`` by default (``Makefile``
``demo-api`` target). Local-only by design.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.routes.config import router as config_router  # noqa: E402
from app.api.routes.decision_thresholds import router as decision_thresholds_router  # noqa: E402
from app.api.routes.defensive_fixes import router as defensive_fixes_router  # noqa: E402
from app.api.routes.judge import router as judge_router  # noqa: E402
from app.api.routes.model_quality import router as model_quality_router  # noqa: E402
from app.api.routes.model_vulnerabilities import router as model_vulnerabilities_router  # noqa: E402
from app.api.routes.red_team import router as red_team_router  # noqa: E402
from app.api.routes.replay import router as replay_router  # noqa: E402
from app.api.routes.rounds import router as rounds_router  # noqa: E402
from app.api.routes.runs import router as runs_router  # noqa: E402
from app.api.routes.safety import router as safety_router  # noqa: E402
from app.api.routes.schema import router as schema_router  # noqa: E402
from app.api.routes.scoring import router as scoring_router  # noqa: E402
from app.api.routes.synthetic import router as synthetic_router  # noqa: E402

app = FastAPI(
    title="Project Atlas — local API",
    description=(
        "Synthetic, public-safe local-only FastAPI service. "
        "Phase 4–10 surface: metadata, scoring, judge, red-team search, "
        "defensive-fix lifecycle, runs/rounds/replay, safety scan, "
        "model-quality matrix."
    ),
    version="0.10.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(config_router)
app.include_router(schema_router)
app.include_router(decision_thresholds_router)
app.include_router(synthetic_router)
app.include_router(scoring_router)
app.include_router(judge_router)
app.include_router(red_team_router)
app.include_router(defensive_fixes_router)
app.include_router(runs_router)
app.include_router(rounds_router)
app.include_router(model_vulnerabilities_router)
app.include_router(replay_router)
app.include_router(safety_router)
app.include_router(model_quality_router)
