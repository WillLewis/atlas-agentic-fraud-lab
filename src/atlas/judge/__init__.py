"""Phase 5 deterministic judge.

This package owns:

- ``atlas.judge.metrics``    — pure-function metric primitives
                               (``model_miss_rate``, ``recall_at_fixed_action_rate``,
                               ``synthetic_loss_allowed``, ...). Bible §16.
- ``atlas.judge.holdouts``   — loads each evaluation set
                               (clean / found_adaptive / locked / drifted)
                               into ``LabeledFeature`` records. Reads
                               locked + drifted artifacts via Python file
                               I/O at runtime (the
                               ``.claude/settings.json`` Read-tool deny
                               applies to my tool calls, not runtime code).
- ``atlas.judge.evaluate``   — ``evaluate_fix(...)`` driver. Loads two
                               ``BaselineModelBundle``s (baseline /
                               candidate), scores each holdout, computes
                               ``MetricSnapshot``s, and assembles a
                               ``JudgeReport``.
- ``atlas.judge.acceptance`` — ``apply_acceptance_rule(...)`` implementing
                               Bible §16.7 conjunction with friction
                               tolerances from
                               ``config/decision_thresholds.yaml``.
                               Produces ``(accepted: bool,
                               judge_notes: str)`` with a deterministic
                               template — no free-form text.

Phase 5 contracts:
  * Judge is code, not an LLM. Bible §13.3.
  * No fit-time leakage. The judge never trains, never refits
    calibration, never invokes any ``sklearn`` ``.fit(...)``. It only
    consumes Phase 4 bundles.
  * No label leakage into scoring inputs. Labels are read for ground-
    truth comparison; they're never passed into ``score_features(...)``.
    Phase 4's column-projection invariant (15-field ``FEATURE_COLUMNS``)
    is preserved.
  * All four evaluation sets honored: ``clean_holdout``,
    ``found_adaptive_set`` (input contract — caller passes event-ids),
    ``locked_adaptive_holdout``, ``drifted_holdout``.
  * Deterministic JSON. Same inputs → byte-identical ``JudgeReport``.
    Floats rounded to 4 decimals at the report-emit boundary, not in
    the math. ``judge_report_id`` derived from
    ``(run_id, round_id, defensive_fix_id)``.
  * Agent text cannot override judge results. ``judge_notes`` is judge-
    generated; the route schema does not declare a ``judge_notes`` field
    on the request body.
"""

__all__: list[str] = []
