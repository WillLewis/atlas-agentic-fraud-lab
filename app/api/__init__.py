"""Local-only FastAPI service for Project Atlas.

The service is local-only by design (see ``PROJECT_ATLAS_BIBLE.md`` §6.1
rule 2 — Local-only services). All routes return synthetic, public-safe
data; none of them call or describe a production scoring endpoint.

Surface (Phases 4–10, all currently mounted in ``app/api/main.py``):

  * Phase 4 — ``GET /health``, ``GET /config/demo``, ``GET /schema``,
              ``GET /decision-thresholds``, ``GET /synthetic/sample``,
              ``POST /score``, ``POST /batch-score``.
  * Phase 5 — ``POST /judge/evaluate-fix``.
  * Phase 6 — ``POST /red-team/search``,
              ``GET /model-vulnerabilities/{model_vulnerability_id}``.
  * Phase 7 — ``POST /defensive-fixes/propose``,
              ``POST /defensive-fixes/apply``.
  * Phase 9 — ``POST /runs``, ``GET /runs``, ``GET /runs/{run_id}``,
              ``GET /runs/{run_id}/rounds``,
              ``GET /runs/{run_id}/rounds/{round_id}``,
              ``POST /rounds/run``,
              ``GET /runs/{run_id}/model-vulnerabilities``,
              ``GET /runs/{run_id}/judge-reports/{judge_report_id}``,
              ``GET /replay/{run_id}``.
  * Phase 10 — ``POST /safety/scan``,
               ``GET /model-quality-matrix``.
"""

__all__: list[str] = []
