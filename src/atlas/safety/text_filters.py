"""Phase 10 deterministic text-filter helpers.

Public-safe by construction:
  * ``suggest_rewrites(finding)`` returns a closed-enum list of
    rewrite suggestions keyed on ``rule_id``. Adding a new safety rule
    requires explicitly adding a ``_REWRITES_BY_RULE`` entry — there
    is intentionally no fallback to free-form prose.
  * ``redact(text)`` strips secret-shaped substrings before surface in
    HTTP response bodies. Patterns mirror the secret-detection regex
    families in ``config/safety.yaml`` but are kept narrow + literal
    so the function stays cheap to call inline.

Phase 10 invariant (a)(4): rewrite suggestions and redactions are
deterministic. Same input → same output. No LLM, no randomness.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from atlas.safety.scanner import Finding


# ---------------------------------------------------------------------------
# Rewrite templates — keyed on rule_id. Tuples are immutable so callers
# can't mutate the registry.
# ---------------------------------------------------------------------------


_REWRITES_BY_RULE: Final[dict[str, tuple[str, ...]]] = {
    "real_institution_names": (
        "Use the public-safe institution label `RetailBank-X` instead of a real bank or payment-network name.",
        "Replace concrete brand mentions with the generic mock-bank vocabulary used across the project.",
    ),
    "internal_paths": (
        "Replace cloud-storage / warehouse / internal repo paths with synthetic `outputs/` paths or `data/synthetic/` references.",
    ),
    "warehouse_table_names": (
        "Replace concrete warehouse table identifiers with `synthetic_<purpose>` placeholders.",
    ),
    "secrets_and_tokens": (
        "Remove the secret entirely. If a token shape is illustrative, replace with `<REDACTED>`.",
    ),
    "production_endpoints": (
        "Use the local-only API base URL `http://127.0.0.1:8000` instead of any external endpoint.",
        "Production-shaped URLs leak deployment context; the demo is local-only by design.",
    ),
    "pii_shaped_strings": (
        "Replace PII-shaped strings with synthetic IDs such as `cust_000001`, `acct_000001`, or `dev_000001`.",
    ),
    "unsafe_redteam_phrasing": (
        "Restate at the synthetic feature-space level — describe an `under_ranked_cohort` rather than operational guidance.",
        "Avoid operational fraud language; describe what the synthetic search found, not how to exploit it.",
    ),
    "legacy_terminology_in_public_copy": (
        "Use public-safe terminology: `model_vulnerability`, `defensive_fix`, `decision_threshold`, `action_rate_limit`, `model_miss_rate`, `synthetic_search`, `under_ranked_cohort`.",
    ),
}


def suggest_rewrites(finding: "Finding") -> list[str]:
    """Return public-safe rewrite suggestions for one ``Finding``.

    Rules with no template return ``[]``. Output is deterministic: the
    same ``rule_id`` always returns the same suggestion list (in the
    same order).
    """
    return list(_REWRITES_BY_RULE.get(finding.rule_id, ()))


# ---------------------------------------------------------------------------
# Redaction — narrow secret-shape patterns. The full safety scanner
# uses richer regexes; these are the inline-redaction subset.
# ---------------------------------------------------------------------------


_REDACTION_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    # Token shapes that the safety scanner already flags. Each is a
    # narrow literal so we only redact what we'd flag — never silently
    # alter normal text.
    (re.compile(r"\bsk-[a-z0-9]{20,}\b", re.IGNORECASE), "<REDACTED-TOKEN>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<REDACTED-TOKEN>"),
    (re.compile(r"\bxox[abprs]-[a-z0-9-]{10,}\b", re.IGNORECASE), "<REDACTED-TOKEN>"),
    # PII shapes.
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "<REDACTED-SSN>"),
    (re.compile(r"\b(?:\d[ -]?){15,16}\b"), "<REDACTED-CC>"),
)


def redact(text: str) -> str:
    """Replace secret-shaped + PII-shaped substrings with redaction
    markers. Idempotent: redacting an already-redacted string is a
    no-op.
    """
    out = text
    for pattern, replacement in _REDACTION_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


__all__ = [
    "redact",
    "suggest_rewrites",
]
