"""Local development tooling.

Phase 4 ships ``atlas.devtools.mcp_server`` — a thin local wrapper over
the FastAPI service. Project-scoped MCP wiring (`.mcp.json`) invokes
``python -m atlas.devtools.mcp_server`` against ``ATLAS_API_BASE_URL``.

The wrapper is local-only by design. It calls the same synthetic API
surface the rest of the demo uses — it does not introduce new endpoints
and it does not touch production systems.
"""

__all__: list[str] = []
