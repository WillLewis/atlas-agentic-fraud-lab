"""Phase 10 safety package — public-mode scanner, deterministic rewrite
suggestions, and config validation.

This package becomes the canonical home for the safety scanner that
Phases 0–9 ran out of ``scripts/safety_scan.py``. After Phase 10
component 2:

  * ``atlas.safety.scanner`` owns the scanner logic.
  * ``scripts/safety_scan.py`` is a thin shim over this package; it
    keeps the same CLI flags + stdout format so ``.claude/hooks/`` and
    ``src/atlas/ledger/report_builder.py`` continue to work unchanged.
  * The ``atlas-safety-scan`` console script (declared in
    ``pyproject.toml``) maps to ``atlas.safety.scanner:cli_entry``.

Phase 10 invariants:

  * Synthetic + local-only. No real institutions, no production
    endpoints, no credentials.
  * Deterministic rewrite suggestions only. ``recommended_rewrites``
    are closed-enum templates keyed by ``rule_id``; no LLM rewriting.
  * Public-safe terminology throughout: ``model_vulnerability``,
    ``defensive_fix``, ``decision_threshold``, ``action_rate_limit``,
    ``model_miss_rate``, ``synthetic_search``, ``under_ranked_cohort``.

Component 1 ships skeleton stubs that raise ``NotImplementedError``.
Bodies fill in across components 2–4. The intermediate state never
breaks ``make safety-scan`` because ``scripts/safety_scan.py`` keeps
the existing implementation until component 2 swaps it.
"""
