"""Phase 10 MCP wrapper smoke tests.

Verifies:
  * The 2 new Phase 10 tool functions exist and are callable.
  * Each forwards to the expected path/method via httpx.MockTransport.
  * The TOOLS registry includes one entry per exposed function.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from atlas.devtools import mcp_server


def _stub_client(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(base_url="http://127.0.0.1:8000", transport=transport)


def _patch_client(monkeypatch, handler):
    monkeypatch.setattr(mcp_server, "_client", lambda: _stub_client(handler))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_tools_registry_includes_phase10_entries():
    expected = {"run_safety_scan", "get_model_quality_matrix"}
    assert expected.issubset(set(mcp_server.TOOLS))


def test_phase10_tools_callable():
    assert callable(mcp_server.run_safety_scan)
    assert callable(mcp_server.get_model_quality_matrix)


# ---------------------------------------------------------------------------
# run_safety_scan
# ---------------------------------------------------------------------------


def test_run_safety_scan_text_only(monkeypatch):
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"passed": True, "findings": [], "recommended_rewrites": []},
        )

    _patch_client(monkeypatch, handler)
    out = mcp_server.run_safety_scan(demo_mode="public", text="hi")
    assert captured["method"] == "POST"
    assert captured["path"] == "/safety/scan"
    assert captured["body"] == {"demo_mode": "public", "text": "hi"}
    assert out["passed"] is True


def test_run_safety_scan_file_paths_only(monkeypatch):
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"passed": True, "findings": [], "recommended_rewrites": []},
        )

    _patch_client(monkeypatch, handler)
    mcp_server.run_safety_scan(demo_mode="public", file_paths=["x.md"])
    assert captured["body"] == {"demo_mode": "public", "file_paths": ["x.md"]}


def test_run_safety_scan_no_text_no_file_paths(monkeypatch):
    """Empty body — wrapper should NOT include null fields."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"passed": True, "findings": [], "recommended_rewrites": []},
        )

    _patch_client(monkeypatch, handler)
    mcp_server.run_safety_scan(demo_mode="public")
    assert captured["body"] == {"demo_mode": "public"}
    assert "text" not in captured["body"]
    assert "file_paths" not in captured["body"]


# ---------------------------------------------------------------------------
# get_model_quality_matrix
# ---------------------------------------------------------------------------


def test_get_model_quality_matrix_forwards_get(monkeypatch):
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={"matrix_version": "matrix_v1", "cells": [], "caveat": "x"},
        )

    _patch_client(monkeypatch, handler)
    out = mcp_server.get_model_quality_matrix()
    assert seen == {"method": "GET", "path": "/model-quality-matrix"}
    assert out["matrix_version"] == "matrix_v1"
