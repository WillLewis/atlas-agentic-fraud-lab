"""Phase 10 public-mode config validators.

Each validator returns a ``list[str]`` of issue messages. Empty list
means "public-safe pass". Used by:

  * ``scripts/bootstrap_demo.py`` — verifies the reviewer's local
    configuration is public-safe before printing the "ready to demo"
    next-steps.
  * Phase 10 ``POST /safety/scan`` — when callers pass a config dict
    via ``file_paths`` referencing a YAML, the route can also surface
    structural issues alongside text-rule findings.
  * Phase 10 tests — `tests/unit/test_phase10_config_validator.py`.

Phase 10 invariant (a)(1): the validators encode local-only +
synthetic + public-safe rules. They never reach out to a network or
take a non-deterministic dependency.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_LOCAL_HOSTS: Final[frozenset[str]] = frozenset(
    {"127.0.0.1", "localhost", "0.0.0.0"}
)


# Cache for the ``real_institution_names`` rule loaded from
# ``config/safety.yaml`` so the validator doesn't have to embed the
# institution-name regex literally (which would itself trip
# ``make safety-scan`` on this file).
_INSTITUTION_PATTERNS_CACHE: list[re.Pattern[str]] | None = None


def _institution_patterns() -> list[re.Pattern[str]]:
    """Return compiled regex patterns from the canonical
    ``real_institution_names`` rule in ``config/safety.yaml``.

    Lazy + cached so the validator is cheap to call repeatedly. The
    indirection avoids embedding the institution-name regex in this
    file — keeping ``make safety-scan`` clean on this module itself.
    """
    global _INSTITUTION_PATTERNS_CACHE
    if _INSTITUTION_PATTERNS_CACHE is not None:
        return _INSTITUTION_PATTERNS_CACHE
    from atlas.safety.scanner import compile_rules, load_config, DEFAULT_CONFIG

    cfg = load_config(DEFAULT_CONFIG)
    rules = compile_rules(cfg)
    for rule in rules:
        if rule.rule_id == "real_institution_names":
            _INSTITUTION_PATTERNS_CACHE = list(rule.patterns)
            return _INSTITUTION_PATTERNS_CACHE
    _INSTITUTION_PATTERNS_CACHE = []
    return _INSTITUTION_PATTERNS_CACHE


def _matches_real_institution(label: str) -> bool:
    return any(p.search(label) for p in _institution_patterns())


def _is_local_url(url: str) -> bool:
    """Returns True iff ``url`` points at a local host. ``url`` may be
    a full ``http(s)://host:port/path`` or a bare ``host:port``.
    """
    if not isinstance(url, str) or not url:
        return False
    # Strip scheme.
    no_scheme = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
    # Take host portion before path or port.
    host = no_scheme.split("/", 1)[0].split(":", 1)[0].lower()
    return host in _LOCAL_HOSTS


# ---------------------------------------------------------------------------
# config/demo.yaml
# ---------------------------------------------------------------------------


def validate_demo_config(cfg: dict[str, Any]) -> list[str]:
    """Validate ``config/demo.yaml`` for public-mode invariants.

    Checks:
      * ``demo_mode`` ∈ ``{public, internal}``.
      * ``institution_label`` exists and does not match a real
        institution-name pattern.
      * ``model_label`` exists.
      * ``disclaimer`` non-empty.
      * ``api.base_url`` resolves to a local host.
    """
    issues: list[str] = []

    mode = cfg.get("demo_mode")
    if mode not in ("public", "internal"):
        issues.append(
            f"demo_mode must be 'public' or 'internal'; got {mode!r}."
        )

    label = cfg.get("institution_label", "")
    if not isinstance(label, str) or not label:
        issues.append("institution_label is required and must be a string.")
    elif _matches_real_institution(label):
        issues.append(
            f"institution_label {label!r} matches a real-institution name; "
            "use a generic synthetic label such as 'RetailBank-X'."
        )

    if not cfg.get("model_label"):
        issues.append("model_label is required.")

    if not cfg.get("disclaimer"):
        issues.append("disclaimer is required.")

    api = cfg.get("api") or {}
    base_url = api.get("base_url") if isinstance(api, dict) else None
    if base_url is None:
        issues.append("api.base_url is required.")
    elif not _is_local_url(str(base_url)):
        issues.append(
            f"api.base_url {base_url!r} must point at a local host "
            "(127.0.0.1, localhost, or 0.0.0.0)."
        )

    return issues


# ---------------------------------------------------------------------------
# .mcp.json
# ---------------------------------------------------------------------------


def validate_mcp_config(cfg: dict[str, Any]) -> list[str]:
    """Validate ``.mcp.json`` for local-only invariants.

    Checks each ``mcpServers.<name>.env.ATLAS_API_BASE_URL`` (when set)
    is a local host. A missing env block is fine — the MCP wrapper
    falls back to the local default.
    """
    issues: list[str] = []
    servers = cfg.get("mcpServers")
    if not isinstance(servers, dict):
        issues.append("mcpServers is required and must be an object.")
        return issues

    for name, server in servers.items():
        if not isinstance(server, dict):
            issues.append(f"mcpServers.{name} must be an object.")
            continue
        env = server.get("env") or {}
        if not isinstance(env, dict):
            issues.append(f"mcpServers.{name}.env must be an object.")
            continue
        base_url = env.get("ATLAS_API_BASE_URL")
        if base_url is None:
            continue
        if not _is_local_url(str(base_url)):
            issues.append(
                f"mcpServers.{name}.env.ATLAS_API_BASE_URL {base_url!r} "
                "must point at a local host."
            )
    return issues


# ---------------------------------------------------------------------------
# config/safety.yaml
# ---------------------------------------------------------------------------


_REQUIRED_SAFETY_KEYS: Final[tuple[str, ...]] = (
    "mode",
    "default_paths",
    "ignore_globs",
    "text_extensions",
    "rules",
)
_ALLOWED_SEVERITIES: Final[frozenset[str]] = frozenset({"error", "warning"})


def validate_safety_config(cfg: dict[str, Any]) -> list[str]:
    """Validate ``config/safety.yaml`` for required structure.

    Checks:
      * required top-level keys present,
      * each rule has ``id``, ``severity`` ∈ ``{error, warning}``, and
        a non-empty ``patterns`` list,
      * each pattern compiles as a regex.
    """
    issues: list[str] = []

    for key in _REQUIRED_SAFETY_KEYS:
        if key not in cfg:
            issues.append(f"required key {key!r} is missing.")

    rules = cfg.get("rules") or []
    if not isinstance(rules, list):
        issues.append("rules must be a list.")
        return issues

    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            issues.append(f"rules[{i}] must be an object.")
            continue
        if not rule.get("id"):
            issues.append(f"rules[{i}].id is required.")
        sev = rule.get("severity", "error")
        if sev not in _ALLOWED_SEVERITIES:
            issues.append(
                f"rules[{i}].severity {sev!r} must be one of "
                f"{sorted(_ALLOWED_SEVERITIES)}."
            )
        patterns = rule.get("patterns") or []
        if not isinstance(patterns, list) or not patterns:
            issues.append(
                f"rules[{i}].patterns must be a non-empty list."
            )
            continue
        for j, raw in enumerate(patterns):
            if not isinstance(raw, str):
                issues.append(
                    f"rules[{i}].patterns[{j}] must be a string."
                )
                continue
            try:
                re.compile(raw)
            except re.error as exc:
                issues.append(
                    f"rules[{i}].patterns[{j}] is not a valid regex: {exc}"
                )

    return issues


# ---------------------------------------------------------------------------
# config/model_quality_matrix.yaml
# ---------------------------------------------------------------------------


_ALLOWED_TIERS: Final[frozenset[str]] = frozenset({"frontier", "compact"})


def validate_model_quality_matrix(cfg: dict[str, Any]) -> list[str]:
    """Validate ``config/model_quality_matrix.yaml`` for public-safe
    invariants.

    Checks:
      * ``model_quality_matrix_version`` is a non-empty string,
      * ``tiers.frontier`` + ``tiers.compact`` exist with
        ``public_safe_label`` strings,
      * ``expose_concrete_model_names`` is a bool,
      * each ``runs[].red_team_tier`` / ``bank_defense_tier`` is in
        ``{frontier, compact}``.
    """
    issues: list[str] = []

    version = cfg.get("model_quality_matrix_version")
    if not isinstance(version, str) or not version:
        issues.append("model_quality_matrix_version must be a non-empty string.")

    tiers = cfg.get("tiers") or {}
    if not isinstance(tiers, dict):
        issues.append("tiers must be an object.")
    else:
        for tier_id in ("frontier", "compact"):
            tier = tiers.get(tier_id)
            if not isinstance(tier, dict):
                issues.append(f"tiers.{tier_id} must be an object.")
                continue
            if not tier.get("public_safe_label"):
                issues.append(
                    f"tiers.{tier_id}.public_safe_label is required."
                )

    expose = cfg.get("expose_concrete_model_names")
    if expose is not None and not isinstance(expose, bool):
        issues.append("expose_concrete_model_names must be a boolean.")

    runs = cfg.get("runs") or []
    if not isinstance(runs, list):
        issues.append("runs must be a list.")
    else:
        for i, run in enumerate(runs):
            if not isinstance(run, dict):
                issues.append(f"runs[{i}] must be an object.")
                continue
            for tier_field in ("red_team_tier", "bank_defense_tier"):
                tier_value = run.get(tier_field)
                if tier_value not in _ALLOWED_TIERS:
                    issues.append(
                        f"runs[{i}].{tier_field} {tier_value!r} must be "
                        f"one of {sorted(_ALLOWED_TIERS)}."
                    )

    return issues


__all__ = [
    "validate_demo_config",
    "validate_mcp_config",
    "validate_model_quality_matrix",
    "validate_safety_config",
]
