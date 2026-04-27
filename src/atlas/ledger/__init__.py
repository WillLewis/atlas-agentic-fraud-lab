"""Phase 8 round engine, ledger, and replay.

This package owns the deterministic three-round lifecycle:

    red-team search → vulnerabilities → propose fixes → apply + judge
        → carry forward versions → repeat × 3 → ledger → replay

No HTTP self-calls — the engine calls Phase 6/7 modules directly:

  * ``atlas.red_team.fraud_scenario_agent.run_search``
  * ``atlas.blue_team.strategy_agent.propose_fixes``
  * ``atlas.blue_team.fix_applier.apply_fix``
  * ``atlas.judge.evaluate.evaluate_fix`` (transitively, via fix_applier)

Module map (component-by-component fill order):

  * ``atlas.ledger.ledger``         — ``RunState`` + ``RoundState``
                                      dataclasses; persistence + load
                                      helpers; deterministic ``run_id``
                                      derivation.
  * ``atlas.ledger.report_builder`` — closed-enum transcript summary +
                                      final-report templates.
                                      Public-safe (template-only) text;
                                      explicit safety-scan in-process.
  * ``atlas.ledger.replay``         — ``ReplayPayload`` builder shaped
                                      for the existing
                                      ``app/web/lib/types.ts`` so Phase 9
                                      can swap the fixture loader.

Phase 8 contracts:

  * **Synthetic + local-only.** Bible §6.1.
  * **Deterministic end-to-end.** Same ``(seed, dataset, round_config,
    code)`` → byte-identical run + ledger + replay JSON.
  * **No wall-clock identity.** ``run_id`` derives from a deterministic
    hash of ``(seed, run_label, demo_mode)``. ``created_at_utc`` reads
    the dataset's ``manifest.json:reference_now_utc``.
  * **Round-state version flow explicit.** Round 1 starts at
    ``baseline_v1`` + ``thresholds_v1``. An accepted fix advances both
    versions; a rejected fix carries the previous versions forward.
  * **`found_adaptive_set_event_ids` propagated** from search → judge
    each round.
  * **Per-round explicit safety scan** on transcript summaries; result
    recorded on ``RoundState.safety_scan_passed``. Default
    ``make safety-scan`` walk ignores ``outputs/**`` so this in-process
    scan is the safety check for those artifacts.
  * **Closed-enum transcript text only.** No raw LLM transcripts; no
    free-form prose path.
  * **Replay payload public-safe** + derived only from authoritative
    artifacts. Aligned to ``app/web/lib/types.ts.MetricSnapshot`` field
    names so Phase 9 can wire it without component rewrites.
  * **Preserve Phase 6/7 paths.** ``outputs/{model_vulnerabilities,
    defensive_fixes,reports,decision_thresholds,baseline_models}/``
    stay untouched; this package adds ``outputs/{runs,ledgers,
    demo_replays}/`` around them.
  * **No public route surface.** Phase 9 wraps these objects.
"""

__all__: list[str] = []
