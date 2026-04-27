"""Phase 10 text-filter unit tests.

Validates ``atlas.safety.text_filters``:

  * ``suggest_rewrites(finding)`` is deterministic per ``rule_id``;
    unknown rule_id → ``[]``; templates are public-safe (no real
    institution names, no production URLs).
  * ``redact(text)`` redacts SSN / token / CC shapes idempotently.
"""
from __future__ import annotations

from pathlib import Path

from atlas.safety.scanner import Finding
from atlas.safety.text_filters import redact, suggest_rewrites


def _f(rule_id: str) -> Finding:
    return Finding(
        path=Path("<text>"), line_no=1, rule_id=rule_id, severity="error",
        snippet="x",
    )


# ---------------------------------------------------------------------------
# suggest_rewrites
# ---------------------------------------------------------------------------


def test_suggest_rewrites_real_institution_names_has_template():
    out = suggest_rewrites(_f("real_institution_names"))
    assert len(out) >= 1
    assert any("RetailBank-X" in line for line in out)


def test_suggest_rewrites_production_endpoints_has_template():
    out = suggest_rewrites(_f("production_endpoints"))
    assert any("127.0.0.1" in line for line in out)


def test_suggest_rewrites_secrets_and_tokens_has_template():
    out = suggest_rewrites(_f("secrets_and_tokens"))
    assert any("REDACTED" in line.upper() for line in out)


def test_suggest_rewrites_pii_shaped_has_synthetic_id_hint():
    out = suggest_rewrites(_f("pii_shaped_strings"))
    assert any("cust_" in line or "synthetic" in line.lower() for line in out)


def test_suggest_rewrites_legacy_terminology_lists_public_terms():
    out = suggest_rewrites(_f("legacy_terminology_in_public_copy"))
    assert any("model_vulnerability" in line for line in out)
    assert any("decision_threshold" in line for line in out)


def test_suggest_rewrites_unknown_rule_returns_empty():
    assert suggest_rewrites(_f("something_unknown")) == []


def test_suggest_rewrites_deterministic():
    """Two calls with the same finding produce identical output."""
    a = suggest_rewrites(_f("real_institution_names"))
    b = suggest_rewrites(_f("real_institution_names"))
    assert a == b


def test_suggest_rewrites_returns_list_not_tuple():
    """Caller can mutate the returned list without affecting registry."""
    out = suggest_rewrites(_f("real_institution_names"))
    assert isinstance(out, list)
    out.append("mutate")
    again = suggest_rewrites(_f("real_institution_names"))
    assert "mutate" not in again


# ---------------------------------------------------------------------------
# redact
# ---------------------------------------------------------------------------


def test_redact_ssn():
    assert "<REDACTED-SSN>" in redact("ssn 123-45-6789 here")


def test_redact_token_sk():
    out = redact("key sk-abcdef0123456789abcdef0123 here")
    assert "<REDACTED-TOKEN>" in out


def test_redact_token_akia():
    out = redact("aws AKIA1234567890ABCDEF here")
    assert "<REDACTED-TOKEN>" in out


def test_redact_cc_shape():
    out = redact("card 4111 1111 1111 1111 here")
    assert "<REDACTED-CC>" in out


def test_redact_clean_text_unchanged():
    assert redact("just some synthetic text") == "just some synthetic text"


def test_redact_idempotent():
    once = redact("ssn 123-45-6789")
    twice = redact(once)
    assert once == twice
