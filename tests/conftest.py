"""Pytest fixtures for Phase 2 / 3 / 4 tests.

Path bootstrap is handled by ``[tool.pytest.ini_options].pythonpath`` in
``pyproject.toml`` (which puts ``src/`` and the repo root on sys.path).
This conftest only owns shared fixtures.
"""
from __future__ import annotations

import random
import shutil
from pathlib import Path
from typing import Any

import pytest

from atlas.synthetic.accounts import generate_accounts
from atlas.synthetic.customers import generate_customers
from atlas.synthetic.devices import generate_devices
from atlas.synthetic.events import (
    generate_login_sessions,
    generate_security_events,
    generate_transfer_events,
)
from atlas.synthetic.features import FeatureVector, recompute_feature_vectors
from atlas.synthetic.graph import generate_graph_edges
from atlas.synthetic.labels import generate_label_generation_records
from atlas.synthetic.recipients import (
    generate_external_accounts,
    generate_recipients,
)
from atlas.synthetic.splits import build_splits

DEFAULT_TEST_SEED = 42
DEFAULT_TEST_COUNT = 60


def _build(seed: int, customer_count: int) -> dict[str, Any]:
    rng = random.Random(seed)
    customers = generate_customers(rng, customer_count, seed)
    accounts = generate_accounts(rng, customers)
    devices = generate_devices(rng, customers)
    recipients = generate_recipients(rng, customer_count)
    external_accounts = generate_external_accounts(rng, customers)
    graph_edges = generate_graph_edges(rng, customers, devices, recipients)
    login_sessions = generate_login_sessions(rng, customers, devices)
    security_events = generate_security_events(rng, customers, login_sessions)
    transfer_events = generate_transfer_events(
        rng, customers, accounts, devices, graph_edges
    )
    label_records = generate_label_generation_records(
        rng, transfer_events, customers, devices, recipients, security_events
    )
    splits = build_splits(
        rng,
        customers,
        accounts,
        devices,
        recipients,
        external_accounts,
        graph_edges,
        login_sessions,
        security_events,
        transfer_events,
        label_records,
    )
    return {
        "seed": seed,
        "customer_count": customer_count,
        "customers": customers,
        "accounts": accounts,
        "devices": devices,
        "recipients": recipients,
        "external_accounts": external_accounts,
        "graph_edges": graph_edges,
        "login_sessions": login_sessions,
        "security_events": security_events,
        "transfer_events": transfer_events,
        "label_records": label_records,
        "splits": splits,
    }


@pytest.fixture(scope="session")
def dataset() -> dict[str, Any]:
    return _build(DEFAULT_TEST_SEED, DEFAULT_TEST_COUNT)


@pytest.fixture(scope="session")
def dataset_alt_seed() -> dict[str, Any]:
    return _build(99, DEFAULT_TEST_COUNT)


@pytest.fixture
def build_dataset():
    return _build


@pytest.fixture(scope="session")
def features_global(dataset) -> list[FeatureVector]:
    return recompute_feature_vectors(
        transfer_events=dataset["transfer_events"],
        customers=dataset["customers"],
        devices=dataset["devices"],
        graph_edges=dataset["graph_edges"],
        login_sessions=dataset["login_sessions"],
        security_events=dataset["security_events"],
    )


@pytest.fixture(scope="session")
def features_per_partition(dataset) -> dict[str, list[FeatureVector]]:
    out: dict[str, list[FeatureVector]] = {}
    for pname, p in dataset["splits"].partitions.items():
        out[pname] = recompute_feature_vectors(
            transfer_events=p.transfer_events,
            customers=p.customers,
            devices=p.devices,
            graph_edges=p.graph_edges,
            login_sessions=p.login_sessions,
            security_events=p.security_events,
        )
    return out


# ---------------------------------------------------------------------------
# Phase 4 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def trained_baseline_dir(tmp_path_factory) -> Path:
    """Train the Phase 4 baseline once per test session into a tmp dir.

    Layout: ``<tmp_outputs_root>/baseline_models/baseline_v1/{model.joblib,calibration.json,...}``.

    The full ``baseline_models/baseline_v1`` nesting matches the
    production layout under ``outputs/baseline_models/baseline_v1/`` so
    Phase 7's blue-team appliers (which write candidates to
    ``<outputs_root>/baseline_models/<defensive_fix_id>/``) and the
    judge's ``BASELINE_MODELS_ROOT`` resolve to the same parent directory.

    Returns the leaf directory containing the four artifacts so Phase 4
    tests can pass it directly to ``load_baseline_bundle``.
    """
    from atlas.model.train import train_baseline_model

    outputs_root = tmp_path_factory.mktemp("phase4_outputs")
    out = outputs_root / "baseline_models" / "baseline_v1"
    out.mkdir(parents=True)
    train_baseline_model(seed=DEFAULT_TEST_SEED, output_dir=out)
    return out


@pytest.fixture
def api_client(trained_baseline_dir: Path, monkeypatch):
    """FastAPI TestClient with the baseline pointed at the session tmp dir.

    Patches ``atlas.model.scorer.DEFAULT_OUTPUT_DIR`` so the scoring routes'
    lazy ``load_baseline_bundle()`` reads from the test artifacts. Also
    patches ``atlas.judge.evaluate.BASELINE_MODELS_ROOT`` so Phase 5's
    version-keyed lookup (``BASELINE_MODELS_ROOT / "baseline_v1"``)
    resolves to the same artifact dir. Resets all cached state per test.
    """
    from fastapi.testclient import TestClient

    import atlas.judge.evaluate as evaluate_mod
    import atlas.model.scorer as scorer_mod
    from app.api.main import app
    import app.api.routes.defensive_fixes as defensive_fixes_mod
    import app.api.routes.red_team as red_team_mod
    from app.api.routes.defensive_fixes import (
        reset_caches as reset_defensive_fixes_caches,
    )
    from app.api.routes.judge import reset_caches as reset_judge_caches
    from app.api.routes.red_team import reset_caches as reset_red_team_caches
    from app.api.routes.scoring import reset_caches as reset_scoring_caches

    # trained_baseline_dir = <outputs_root>/baseline_models/baseline_v1
    # → outputs_root  = trained_baseline_dir.parent.parent
    # → baseline_models_root = trained_baseline_dir.parent
    outputs_root = trained_baseline_dir.parent.parent
    baseline_models_root = trained_baseline_dir.parent

    monkeypatch.setattr(scorer_mod, "DEFAULT_OUTPUT_DIR", trained_baseline_dir)
    monkeypatch.setattr(evaluate_mod, "BASELINE_MODELS_ROOT", baseline_models_root)
    monkeypatch.setattr(
        evaluate_mod, "ALTERNATE_THRESHOLDS_ROOT",
        outputs_root / "decision_thresholds",
    )
    monkeypatch.setattr(defensive_fixes_mod, "OUTPUTS_ROOT", outputs_root)
    monkeypatch.setattr(red_team_mod, "OUTPUTS_ROOT", outputs_root)

    # Phase 9 routes (component 3+4) — point at the hermetic outputs tree
    # so tests don't touch the real ``outputs/`` directory.
    import app.api.routes.model_vulnerabilities as mv_mod  # noqa: E402
    import app.api.routes.replay as replay_mod  # noqa: E402
    import app.api.routes.rounds as rounds_mod  # noqa: E402
    import app.api.routes.runs as runs_mod  # noqa: E402

    monkeypatch.setattr(runs_mod, "OUTPUTS_ROOT", outputs_root)
    monkeypatch.setattr(rounds_mod, "OUTPUTS_ROOT", outputs_root)
    monkeypatch.setattr(replay_mod, "OUTPUTS_ROOT", outputs_root)
    monkeypatch.setattr(mv_mod, "OUTPUTS_ROOT", outputs_root)

    # ``trained_baseline_dir`` is session-scoped, so the same
    # ``outputs_root`` is shared across tests. Phase 4–7 tests don't
    # touch the Phase 9 subdirs, but POST /runs / POST /rounds/run
    # would otherwise leak persisted run/round/ledger files into later
    # tests' views. Clear them before yielding (and after, for tidiness).
    def _clear_phase9_dirs() -> None:
        for sub in (
            "runs",
            "ledgers",
            "demo_replays",
            "model_vulnerabilities",
            "defensive_fixes",
            "reports",
        ):
            d = outputs_root / sub
            if d.exists():
                shutil.rmtree(d)

    _clear_phase9_dirs()
    reset_scoring_caches()
    reset_judge_caches()
    reset_red_team_caches()
    reset_defensive_fixes_caches()
    with TestClient(app) as client:
        yield client
    _clear_phase9_dirs()
    reset_scoring_caches()
    reset_judge_caches()
    reset_red_team_caches()
    reset_defensive_fixes_caches()
