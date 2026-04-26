"""Local-only FastAPI service for Project Atlas.

The service is local-only by design (see ``PROJECT_ATLAS_BIBLE.md`` §6.1
rule 2 — Local-only services). All routes return synthetic, public-safe
data; none of them call or describe a production scoring endpoint.

Phase 4 surface (components 5 + 6):

  * ``GET  /health``
  * ``GET  /config/demo``
  * ``GET  /schema``
  * ``GET  /decision-thresholds``
  * ``GET  /synthetic/sample``
  * ``POST /score``
  * ``POST /batch-score``

Out of scope for Phase 4: ``/runs``, ``/rounds/run``, ``/red-team/search``,
``/defensive-fixes/*``, ``/judge/evaluate-fix``, ``/replay/{run_id}``,
``/model-quality-matrix``, ``/safety/scan``. Those land in Phases 5–10.
"""

__all__: list[str] = []
