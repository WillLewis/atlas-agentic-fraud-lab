"""Pytest fixtures for Phase 2 tests.

Path bootstrap is handled by ``[tool.pytest.ini_options].pythonpath`` in
``pyproject.toml`` (which puts ``src/`` and the repo root on sys.path).
This conftest only owns shared fixtures.
"""
from __future__ import annotations

import random
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
from atlas.synthetic.graph import generate_graph_edges
from atlas.synthetic.labels import generate_label_generation_records
from atlas.synthetic.recipients import (
    generate_external_accounts,
    generate_recipients,
)
from atlas.synthetic.splits import build_splits

DEFAULT_TEST_SEED = 42
DEFAULT_TEST_COUNT = 60  # >= 5-way split minimum, fast to build


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
    """Default Phase-2 dataset built once per test session.

    seed=42, customer_count=60. The 5-way split yields 36/6/6/6/6.
    """
    return _build(DEFAULT_TEST_SEED, DEFAULT_TEST_COUNT)


@pytest.fixture(scope="session")
def dataset_alt_seed() -> dict[str, Any]:
    """Same shape, different seed. Used to assert seed-dependence."""
    return _build(99, DEFAULT_TEST_COUNT)


@pytest.fixture
def build_dataset():
    """Factory for tests that need an ad-hoc dataset at custom (seed, count)."""
    return _build
