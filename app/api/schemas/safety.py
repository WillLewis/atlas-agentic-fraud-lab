"""Pydantic schemas for ``POST /safety/scan`` (Phase 10).

Mirrors the OpenAPI shapes defined in ``project_atlas_openapi.yaml``:

  * ``SafetyScanRequest``   — ``demo_mode``, optional ``text``,
                              optional ``file_paths``.
  * ``SafetyScanResponse``  — ``passed``, ``findings``,
                              ``recommended_rewrites``.

The ``Finding`` shape on the API surface uses ``severity / category /
message / location`` (4 string fields) — distinct from the internal
``atlas.safety.scanner.Finding`` dataclass which has
``path / line_no / rule_id / severity / snippet``. The route layer
projects internal findings into this API shape, redacting ``snippet``
through ``atlas.safety.text_filters.redact`` before surface.

Request schema uses ``extra="forbid"`` so the boundary rejects unknown
fields. Response schema allows extras for forward compatibility.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class SafetyScanRequest(_StrictModel):
    """Mirrors OpenAPI ``SafetyScanRequest``. Either ``text`` or
    ``file_paths`` should be supplied; an empty body still scans
    ``config/safety.yaml``'s ``default_paths`` for symmetry with the
    CLI behavior.
    """

    demo_mode: Literal["public", "internal"]
    text: str | None = None
    file_paths: list[str] | None = None


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class SafetyFinding(BaseModel):
    """API-shape finding. Mirrors OpenAPI
    ``SafetyScanResponse.findings.items``.

    ``location`` is the public-safe pointer (e.g. ``"text"`` for
    in-memory scans, or a redacted file path) — never an absolute
    repo-rooted path.
    """

    model_config = ConfigDict(extra="allow")

    severity: str
    category: str
    message: str
    location: str


class SafetyScanResponse(BaseModel):
    """Mirrors OpenAPI ``SafetyScanResponse``."""

    model_config = ConfigDict(extra="allow")

    passed: bool
    findings: list[SafetyFinding] = Field(default_factory=list)
    recommended_rewrites: list[str] = Field(default_factory=list)


__all__ = [
    "SafetyFinding",
    "SafetyScanRequest",
    "SafetyScanResponse",
]
