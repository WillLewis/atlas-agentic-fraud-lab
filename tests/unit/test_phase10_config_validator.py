"""Phase 10 config-validator unit tests.

Validates the four validators against:
  * the real ``config/demo.yaml`` / ``.mcp.json`` /
    ``config/safety.yaml`` / ``config/model_quality_matrix.yaml`` —
    all should pass cleanly,
  * synthetic invalid dicts — each should fail with a specific issue.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from atlas.safety.config_validator import (
    validate_demo_config,
    validate_mcp_config,
    validate_model_quality_matrix,
    validate_safety_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# validate_demo_config
# ---------------------------------------------------------------------------


def test_demo_config_real_passes():
    cfg = yaml.safe_load((REPO_ROOT / "config" / "demo.yaml").read_text())
    assert validate_demo_config(cfg) == []


def test_demo_config_real_institution_label_fails():
    cfg = {
        "demo_mode": "public",
        "institution_label": "JPMorgan Chase",
        "model_label": "x",
        "disclaimer": "x",
        "api": {"base_url": "http://127.0.0.1:8000"},
    }
    issues = validate_demo_config(cfg)
    assert any("real-institution" in i.lower() for i in issues)


def test_demo_config_invalid_mode_fails():
    cfg = {
        "demo_mode": "production",
        "institution_label": "RetailBank-X",
        "model_label": "x",
        "disclaimer": "x",
        "api": {"base_url": "http://127.0.0.1:8000"},
    }
    issues = validate_demo_config(cfg)
    assert any("demo_mode" in i for i in issues)


def test_demo_config_non_local_base_url_fails():
    cfg = {
        "demo_mode": "public",
        "institution_label": "RetailBank-X",
        "model_label": "x",
        "disclaimer": "x",
        "api": {"base_url": "https://api.example.com"},
    }
    issues = validate_demo_config(cfg)
    assert any("base_url" in i for i in issues)


def test_demo_config_missing_disclaimer_fails():
    cfg = {
        "demo_mode": "public",
        "institution_label": "RetailBank-X",
        "model_label": "x",
        "disclaimer": "",
        "api": {"base_url": "http://127.0.0.1:8000"},
    }
    issues = validate_demo_config(cfg)
    assert any("disclaimer" in i for i in issues)


# ---------------------------------------------------------------------------
# validate_mcp_config
# ---------------------------------------------------------------------------


def test_mcp_config_real_passes():
    cfg = json.loads((REPO_ROOT / ".mcp.json").read_text())
    assert validate_mcp_config(cfg) == []


def test_mcp_config_non_local_url_fails():
    cfg = {
        "mcpServers": {
            "x": {"env": {"ATLAS_API_BASE_URL": "https://api.example.com"}},
        },
    }
    issues = validate_mcp_config(cfg)
    assert any("ATLAS_API_BASE_URL" in i for i in issues)


def test_mcp_config_missing_env_is_ok():
    """Missing env block is fine — wrapper falls back to local default."""
    cfg = {"mcpServers": {"x": {"command": "python"}}}
    assert validate_mcp_config(cfg) == []


def test_mcp_config_non_dict_servers_fails():
    cfg = {"mcpServers": "not-an-object"}
    issues = validate_mcp_config(cfg)
    assert any("mcpServers" in i for i in issues)


# ---------------------------------------------------------------------------
# validate_safety_config
# ---------------------------------------------------------------------------


def test_safety_config_real_passes():
    cfg = yaml.safe_load((REPO_ROOT / "config" / "safety.yaml").read_text())
    assert validate_safety_config(cfg) == []


def test_safety_config_missing_rules_fails():
    cfg = {
        "mode": "public",
        "default_paths": [],
        "ignore_globs": [],
        "text_extensions": [],
    }
    issues = validate_safety_config(cfg)
    assert any("rules" in i for i in issues)


def test_safety_config_invalid_severity_fails():
    cfg = {
        "mode": "public",
        "default_paths": [],
        "ignore_globs": [],
        "text_extensions": [],
        "rules": [
            {"id": "x", "severity": "fatal", "patterns": ["a"]},
        ],
    }
    issues = validate_safety_config(cfg)
    assert any("severity" in i for i in issues)


def test_safety_config_bad_regex_fails():
    cfg = {
        "mode": "public",
        "default_paths": [],
        "ignore_globs": [],
        "text_extensions": [],
        "rules": [
            {"id": "x", "severity": "error", "patterns": ["[unbalanced"]},
        ],
    }
    issues = validate_safety_config(cfg)
    assert any("not a valid regex" in i for i in issues)


# ---------------------------------------------------------------------------
# validate_model_quality_matrix
# ---------------------------------------------------------------------------


def test_model_quality_matrix_real_passes():
    cfg = yaml.safe_load(
        (REPO_ROOT / "config" / "model_quality_matrix.yaml").read_text()
    )
    assert validate_model_quality_matrix(cfg) == []


def test_model_quality_matrix_invalid_tier_fails():
    cfg = {
        "model_quality_matrix_version": "v1",
        "tiers": {
            "frontier": {"public_safe_label": "Frontier"},
            "compact": {"public_safe_label": "Compact"},
        },
        "expose_concrete_model_names": False,
        "runs": [
            {"red_team_tier": "premium", "bank_defense_tier": "frontier"},
        ],
    }
    issues = validate_model_quality_matrix(cfg)
    assert any("red_team_tier" in i for i in issues)


def test_model_quality_matrix_expose_must_be_bool():
    cfg = {
        "model_quality_matrix_version": "v1",
        "tiers": {
            "frontier": {"public_safe_label": "Frontier"},
            "compact": {"public_safe_label": "Compact"},
        },
        "expose_concrete_model_names": "yes",
        "runs": [],
    }
    issues = validate_model_quality_matrix(cfg)
    assert any("expose_concrete_model_names" in i for i in issues)


def test_model_quality_matrix_missing_tier_label_fails():
    cfg = {
        "model_quality_matrix_version": "v1",
        "tiers": {
            "frontier": {"public_safe_label": "Frontier"},
            "compact": {},  # missing public_safe_label
        },
        "expose_concrete_model_names": False,
        "runs": [],
    }
    issues = validate_model_quality_matrix(cfg)
    assert any("public_safe_label" in i for i in issues)
