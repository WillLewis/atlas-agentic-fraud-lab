"""Phase 10 scanner unit tests.

Validates ``atlas.safety.scanner`` against synthetic strings and tmp
files. The strings deliberately mirror each public-mode rule family:

  * real_institution_names
  * production_endpoints
  * secrets_and_tokens
  * pii_shaped_strings
  * unsafe_redteam_phrasing
  * legacy_terminology_in_public_copy

Plus shape tests for ``Rule`` / ``Finding`` / ``ScanReport`` and
behavior tests for ``scan_text`` / ``scan_paths``.
"""
from __future__ import annotations

from pathlib import Path

from atlas.safety.scanner import (
    Finding,
    Rule,
    ScanReport,
    compile_rules,
    load_config,
    scan_paths,
    scan_text,
)


# ---------------------------------------------------------------------------
# Dataclass shapes
# ---------------------------------------------------------------------------


def test_rule_shape():
    r = Rule(rule_id="x", severity="error", description="d", patterns=[])
    assert r.rule_id == "x"
    assert r.severity == "error"
    assert r.patterns == []


def test_finding_shape():
    f = Finding(
        path=Path("a.md"), line_no=1, rule_id="x", severity="warning",
        snippet="hi",
    )
    assert f.line_no == 1
    assert f.severity == "warning"


def test_scan_report_split_errors_warnings():
    rep = ScanReport(
        findings=[
            Finding(Path("x"), 1, "a", "error", "s"),
            Finding(Path("x"), 2, "b", "warning", "s"),
        ],
        files_scanned=1,
    )
    assert len(rep.errors) == 1
    assert len(rep.warnings) == 1


# ---------------------------------------------------------------------------
# scan_text — one rule family per test
# ---------------------------------------------------------------------------


def test_scan_text_clean_passes():
    rep = scan_text("this is just synthetic content")
    assert rep.errors == []
    assert rep.warnings == []
    assert rep.files_scanned == 1


def test_scan_text_real_institution_name():
    rep = scan_text("we found jpmorgan internal data")
    assert {f.rule_id for f in rep.errors} >= {"real_institution_names"}


def test_scan_text_production_endpoint():
    rep = scan_text("https://api.bank.prod/v1/score is the prod url")
    assert {f.rule_id for f in rep.errors} >= {"production_endpoints"}


def test_scan_text_secret_token():
    rep = scan_text("token=AKIA1234567890ABCDEF here")
    assert {f.rule_id for f in rep.errors} >= {"secrets_and_tokens"}


def test_scan_text_ssn_shape():
    rep = scan_text("contact id 123-45-6789 today")
    assert {f.rule_id for f in rep.errors} >= {"pii_shaped_strings"}


def test_scan_text_unsafe_redteam_phrasing():
    """Match the ``\\bhow to (?:phish|bypass|evade|defeat) ... mfa\\b``
    pattern in ``config/safety.yaml`` rule
    ``unsafe_redteam_phrasing``.
    """
    rep = scan_text("how to bypass mfa quickly")
    assert {f.rule_id for f in rep.errors} >= {"unsafe_redteam_phrasing"}


def test_scan_text_legacy_terminology_warning():
    """Legacy term ``fraud playbook`` emits warning severity from rule
    ``legacy_terminology_in_public_copy``.
    """
    rep = scan_text("our fraud playbook explains the approach")
    rule_ids_warn = {f.rule_id for f in rep.warnings}
    assert "legacy_terminology_in_public_copy" in rule_ids_warn


# ---------------------------------------------------------------------------
# scan_text — synthetic file-shape mode
# ---------------------------------------------------------------------------


def test_scan_text_files_scanned_is_one():
    """``scan_text`` reports ``files_scanned=1`` so callers can
    distinguish "scanned nothing" from "scanned a string".
    """
    rep = scan_text("clean")
    assert rep.files_scanned == 1


def test_scan_text_synthetic_path_label():
    """Each finding's path is the ``<text>`` synthetic label."""
    rep = scan_text("we found jpmorgan internal data")
    for f in rep.findings:
        assert str(f.path) == "<text>"


# ---------------------------------------------------------------------------
# scan_paths
# ---------------------------------------------------------------------------


def test_scan_paths_clean_file(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("this is just synthetic content\n")
    rep = scan_paths([p])
    assert rep.errors == []
    assert rep.files_scanned == 1


def test_scan_paths_dirty_file(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("we found jpmorgan internal data\n")
    rep = scan_paths([p])
    assert {f.rule_id for f in rep.errors} >= {"real_institution_names"}


def test_scan_paths_empty_returns_default_paths_walk():
    """Empty paths list falls back to ``default_paths`` from config."""
    rep = scan_paths([])
    # We don't assert on findings count (the project changes); just
    # confirm the walk happened.
    assert rep.files_scanned > 0


# ---------------------------------------------------------------------------
# compile_rules + load_config
# ---------------------------------------------------------------------------


def test_compile_rules_count_matches_config():
    """All 8 current rules compile cleanly."""
    from atlas.safety.scanner import DEFAULT_CONFIG
    cfg = load_config(DEFAULT_CONFIG)
    rules = compile_rules(cfg)
    rule_ids = {r.rule_id for r in rules}
    expected = {
        "real_institution_names", "internal_paths", "warehouse_table_names",
        "secrets_and_tokens", "production_endpoints", "pii_shaped_strings",
        "unsafe_redteam_phrasing", "legacy_terminology_in_public_copy",
    }
    assert rule_ids == expected


def test_compile_rules_patterns_are_compiled():
    from atlas.safety.scanner import DEFAULT_CONFIG
    cfg = load_config(DEFAULT_CONFIG)
    rules = compile_rules(cfg)
    for r in rules:
        for p in r.patterns:
            # Compiled patterns expose a ``search`` method.
            assert callable(p.search)
