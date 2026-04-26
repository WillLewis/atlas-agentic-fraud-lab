"""Phase 6 red-team synthetic search.

This package owns the deterministic, local search over synthetic event
histories that surfaces accepted high-risk synthetic events and packages
them as public-safe ``ModelVulnerabilityCard``s.

Module map (component-by-component fill order):

  * ``atlas.red_team.fraud_scenario_agent``        — round-level orchestrator.
                                                     Reads ``config/round_config.yaml``,
                                                     calls the allocator, dispatches
                                                     to enabled search methods,
                                                     emits the deterministic
                                                     ``found_adaptive_set_event_ids``.
  * ``atlas.red_team.scoring_query_allocator``     — splits ``max_score_queries``
                                                     across (method, family_id) pairs.
  * ``atlas.red_team.random_search``               — deterministic random-mutation
                                                     baseline.
  * ``atlas.red_team.evolutionary_search``         — deterministic adaptive loop;
                                                     beats random on at least one
                                                     seeded family (Bible §18 Phase 6).
  * ``atlas.red_team.graph_probe``                 — graph-relationship-driven search
                                                     prioritizing shared-device /
                                                     shared-recipient cohorts.
  * ``atlas.red_team.mutations``                   — pure-function mutators on
                                                     copies of synthetic history
                                                     records (added in component 2).
  * ``atlas.red_team.model_vulnerability_packager`` — turns aggregated search
                                                     output into public-safe
                                                     ``ModelVulnerabilityCard``s.

Phase 6 contracts:

  * **Synthetic histories only.** All mutations operate on records that
    already carry safe synthetic ID prefixes (``cust_``, ``tx_``, ``dev_``,
    ``recip_``, ``edge_``, ``cand_``). No real institutions, real customer
    IDs, or operational fraud guidance.
  * **No direct engineered-feature mutation.** Every candidate path
    mutates synthetic histories and then recomputes features via
    ``atlas.synthetic.features.recompute_feature_vectors``.
  * **No label leakage into scoring inputs.** Regenerated labels validate
    whether a candidate is a valid high-risk synthetic event; they never
    enter the scorer's input matrix. Phase 4's column projector enforces
    this structurally.
  * **No locked / drifted-label access.** Phase 6 reads only globally-
    readable artifacts under ``data/synthetic/{entities,events,graph,
    labels,features,splits}/``.
  * **Deterministic.** Same ``(seed, dataset, round_config, query_budget)``
    → byte-identical search output.
  * **Score-query budget honored.** ``max_score_queries`` from
    ``config/round_config.yaml`` is the hard cap across enabled methods.
  * **Round-driven, not hard-coded.** Allowed families, search methods,
    and budget come from ``config/round_config.yaml``. The 7-family
    canonical registry comes from
    ``config/synthetic_schema.yaml.model_vulnerability_families``.
    ``project_atlas_sample_data.json`` is illustrative only; this package
    does not read it.
  * **Judge metric formulas not duplicated.** ``model_miss_rate``,
    ``synthetic_loss_allowed`` etc. live in ``atlas.judge.metrics`` and
    are imported here.
  * **`found_adaptive_set` is a runtime search output**, not a persisted
    Phase 2/3 partition.
"""

__all__: list[str] = []
