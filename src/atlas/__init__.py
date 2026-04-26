"""Project Atlas — synthetic, defensive red/blue fraud-model evaluation arena.

This is the runtime Python package. All public APIs surface as submodules:

- ``atlas.synthetic`` — generators for customers, accounts, devices, recipients,
  external accounts, graph edges, login/security/transfer events, latent labels,
  customer-level splits, and locked / drifted holdouts.
- ``atlas.model`` (Phase 4) — baseline mock scorer, calibration, and decision-
  threshold overlay.
- ``atlas.judge`` (Phase 5) — deterministic metrics, holdout evaluation, and
  defensive-fix acceptance rules.
- ``atlas.red_team`` / ``atlas.blue_team`` (Phases 6–7) — runtime simulation
  agents and search workers invoked by the round engine.
- ``atlas.ledger`` / ``atlas.safety`` / ``atlas.devtools`` — supporting modules.

Synthetic-only by construction. See ``PROJECT_ATLAS_BIBLE.md`` §6.
"""

__all__: list[str] = []
