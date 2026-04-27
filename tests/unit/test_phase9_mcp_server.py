"""Phase 9 MCP wrapper smoke tests.

The wrapper is a thin httpx client over the local FastAPI service. We
verify:
  * The 5 new Phase 9 tool functions exist and are callable.
  * Each forwards to the expected path/method via a mocked transport.
  * The TOOLS registry includes one entry per exposed function (Phase 4
    + 6 + 7 + 9 surfaces aligned).
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from atlas.devtools import mcp_server


def _stub_client(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(base_url="http://127.0.0.1:8000", transport=transport)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_tools_registry_includes_phase9_entries():
    expected = {
        "create_run", "list_runs", "get_run_detail",
        "run_rounds", "get_replay_payload",
    }
    assert expected.issubset(set(mcp_server.TOOLS))


def test_tools_registry_keeps_phase4_6_7_entries():
    expected = {
        "get_decision_thresholds", "get_synthetic_sample",
        "score_event", "batch_score_events",
        "run_red_team_search",
        "propose_defensive_fixes", "apply_defensive_fix",
    }
    assert expected.issubset(set(mcp_server.TOOLS))


def test_tools_registry_method_strings_match_functions():
    """Every TOOLS entry resolves to a real callable."""
    for tool_name in mcp_server.TOOLS:
        assert callable(getattr(mcp_server, tool_name))


# ---------------------------------------------------------------------------
# Phase 9 wrapper forward tests (via httpx MockTransport)
# ---------------------------------------------------------------------------


def _patch_client(monkeypatch, handler):
    monkeypatch.setattr(mcp_server, "_client", lambda: _stub_client(handler))


def test_create_run_forwards_post(monkeypatch):
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={
                "run_id": "run_xxxxxxxx", "seed": 42, "demo_mode": "public",
                "status": "created", "current_round": 0,
                "created_at_utc": "2026-06-01T12:00:00Z",
            },
        )

    _patch_client(monkeypatch, handler)
    out = mcp_server.create_run(seed=42, run_label="alpha", max_rounds=3)
    assert captured["method"] == "POST"
    assert captured["path"] == "/runs"
    assert captured["body"] == {
        "seed": 42, "demo_mode": "public", "max_rounds": 3, "run_label": "alpha",
    }
    assert out["run_id"] == "run_xxxxxxxx"


def test_list_runs_forwards_get(monkeypatch):
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"runs": []})

    _patch_client(monkeypatch, handler)
    assert mcp_server.list_runs() == {"runs": []}
    assert seen == {"method": "GET", "path": "/runs"}


def test_get_run_detail_url_encoded(monkeypatch):
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={
            "run_id": "run_aaaa1234", "seed": 42, "demo_mode": "public",
            "status": "completed", "rounds": [],
        })

    _patch_client(monkeypatch, handler)
    mcp_server.get_run_detail("run_aaaa1234")
    assert seen["path"] == "/runs/run_aaaa1234"


def test_run_rounds_forwards_post(monkeypatch):
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "run_id": "run_x", "completed_rounds": [],
        })

    _patch_client(monkeypatch, handler)
    mcp_server.run_rounds("run_x", start_round=2, round_count=2)
    assert captured["method"] == "POST"
    assert captured["path"] == "/rounds/run"
    assert captured["body"] == {
        "run_id": "run_x", "start_round": 2, "round_count": 2,
    }


def test_get_replay_payload_forwards_get(monkeypatch):
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={
            "run": {}, "five_step_story": [], "charts": {"round_metrics": []},
        })

    _patch_client(monkeypatch, handler)
    out = mcp_server.get_replay_payload("run_replay01")
    assert seen["path"] == "/replay/run_replay01"
    assert sorted(out.keys()) == ["charts", "five_step_story", "run"]


def test_create_run_omits_run_label_when_none(monkeypatch):
    """Optional run_label not sent when caller omits it."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "run_id": "run_x", "seed": 42, "demo_mode": "public",
            "status": "created", "current_round": 0,
        })

    _patch_client(monkeypatch, handler)
    mcp_server.create_run(seed=42)
    assert "run_label" not in captured["body"]
