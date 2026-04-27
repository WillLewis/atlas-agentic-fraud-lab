"""Phase 10 ``POST /safety/scan`` route — thin wrapper over the
``atlas.safety.scanner`` package.

The handler:
  * dispatches on the request body (``text`` vs ``file_paths``;
    fall back to ``default_paths`` from ``config/safety.yaml`` when
    neither is supplied — matches CLI default behavior),
  * projects internal ``Finding`` records into the API
    ``SafetyFinding`` shape (``severity``, ``category``, ``message``,
    ``location``), redacting ``snippet`` via
    ``atlas.safety.text_filters.redact`` before surface,
  * aggregates ``recommended_rewrites`` from
    ``atlas.safety.text_filters.suggest_rewrites`` keyed on rule_id,
    deduplicated while preserving order,
  * returns ``passed = (errors == 0)`` — warnings are surfaced but
    do not fail the scan.

Phase 10 invariant (a)(4): rewrite suggestions are deterministic +
template-based. No LLM rewriting path exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.safety import (  # noqa: E402
    SafetyFinding,
    SafetyScanRequest,
    SafetyScanResponse,
)
from atlas.safety.scanner import (  # noqa: E402
    DEFAULT_CONFIG,
    Finding,
    ScanReport,
    scan_paths,
    scan_text,
)
from atlas.safety.text_filters import redact, suggest_rewrites  # noqa: E402

router = APIRouter()


# Module-level config path — tests monkeypatch when they need a
# different rule set.
SAFETY_CONFIG_PATH: Path = DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# Internal projection helpers
# ---------------------------------------------------------------------------


def _redact_path(path: Path) -> str:
    """Return a redacted, repo-relative path string for surface in
    ``location``. Synthetic ``<text>`` paths pass through unchanged.
    """
    raw = str(path)
    if raw == "<text>":
        return "text"
    try:
        rel = str(path.resolve().relative_to(REPO_ROOT))
    except (OSError, ValueError):
        rel = raw
    return redact(rel)


def _finding_to_api_shape(f: Finding) -> SafetyFinding:
    """Project an internal ``Finding`` into the OpenAPI
    ``SafetyFinding`` shape with redacted snippet + path.
    """
    return SafetyFinding(
        severity=f.severity,
        category=f.rule_id,
        message=redact(f.snippet),
        location=f"{_redact_path(f.path)}:{f.line_no}",
    )


def _aggregate_rewrites(findings: list[Finding]) -> list[str]:
    """Aggregate per-finding rewrite suggestions, deduplicated while
    preserving first-seen order so the response is byte-stable for a
    given input.
    """
    seen: set[str] = set()
    out: list[str] = []
    for f in findings:
        for s in suggest_rewrites(f):
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


def _run_scan(req: SafetyScanRequest) -> ScanReport:
    """Dispatch the request body to the scanner. ``text`` wins when
    set; otherwise ``file_paths``; otherwise ``default_paths`` from
    config.
    """
    if req.text is not None:
        return scan_text(
            req.text, config_path=SAFETY_CONFIG_PATH, mode=req.demo_mode,
        )
    return scan_paths(
        req.file_paths or [],
        config_path=SAFETY_CONFIG_PATH,
        mode=req.demo_mode,
    )


# ---------------------------------------------------------------------------
# POST /safety/scan
# ---------------------------------------------------------------------------


@router.post(
    "/safety/scan",
    response_model=SafetyScanResponse,
    response_model_exclude_none=True,
)
def post_safety_scan(req: SafetyScanRequest) -> dict:
    try:
        report = _run_scan(req)
    except FileNotFoundError as exc:
        # config/safety.yaml missing → not a request-shape error.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    findings_api = [_finding_to_api_shape(f) for f in report.findings]
    return {
        "passed": len(report.errors) == 0,
        "findings": [f.model_dump() for f in findings_api],
        "recommended_rewrites": _aggregate_rewrites(report.findings),
    }
