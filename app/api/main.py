"""FastAPI entry point for the local-only Project Atlas service.

Phase 4 surface (components 5 + 6):

  GET  /health
  GET  /config/demo
  GET  /schema
  GET  /decision-thresholds
  GET  /synthetic/sample
  POST /score
  POST /batch-score

Phase 5 surface (component 1 stub — body lands in component 6):

  POST /judge/evaluate-fix

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
from app.api.routes.judge import router as judge_router  # noqa: E402
from app.api.routes.schema import router as schema_router  # noqa: E402
from app.api.routes.scoring import router as scoring_router  # noqa: E402
from app.api.routes.synthetic import router as synthetic_router  # noqa: E402

app = FastAPI(
    title="Project Atlas — local API",
    description=(
        "Synthetic, public-safe local-only FastAPI service. "
        "Phase 4 surface: read-only metadata + scoring."
    ),
    version="0.4.0",
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
