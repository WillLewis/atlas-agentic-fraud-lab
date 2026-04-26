"""Synthetic environment generators (Phase 2).

This package owns the deterministic generation of raw entities, events, latent
labels, customer-level splits, and locked / drifted holdout artifacts. It does
NOT compute features (Phase 3 owns ``atlas.synthetic.features``), train a
model, or call any API.

Determinism contract: every generator takes an explicit ``random.Random``
instance and an integer ``seed`` argument. No module-level RNG state. No
``datetime.now()`` — see ``REFERENCE_NOW`` in ``atlas.synthetic.events`` for
the fixed synthetic reference instant.

Synthetic-naming contract: every emitted ID matches one of the synthetic
prefixes listed in ``config/safety.yaml`` (``cust_``, ``acct_``, ``dev_``,
``recip_``, ``extacct_``, ``sess_``, ``sec_``, ``tx_``, ``edge_``,
``label_tx_``). Field names match ``project_atlas_sample_data.json``.
"""

__all__: list[str] = []
