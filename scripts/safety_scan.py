#!/usr/bin/env python3
"""Project Atlas safety scanner — thin shim over ``atlas.safety.scanner``.

Phase 10 moved the canonical implementation to
``src/atlas/safety/scanner.py``. This shim preserves the existing
contracts that callers depend on:

  * ``make safety-scan`` — invokes this script as ``python3 scripts/safety_scan.py``.
  * ``.claude/hooks/safety_scan_*.py`` — both run the script as a
    subprocess with ``--paths`` and read text-format stdout.
  * ``src/atlas/ledger/report_builder.py`` — does
    ``from safety_scan import compile_rules, load_config`` after
    inserting ``scripts/`` on ``sys.path``.

CLI flags + stdout text format + exit codes are byte-stable with the
prior implementation. The package is the source of truth; this file
just re-exports + dispatches.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from atlas.safety.scanner import (  # noqa: E402, F401
    DEFAULT_CONFIG,
    MAX_BYTES,
    Finding,
    Rule,
    ScanReport,
    cli_entry,
    compile_rules,
    format_json,
    format_text,
    is_ignored,
    is_text_file,
    iter_candidate_files,
    load_config,
    load_safety_config,
    main,
    parse_args,
    resolve_roots,
    scan_file,
    scan_paths,
    scan_text,
)


if __name__ == "__main__":
    sys.exit(cli_entry(sys.argv[1:]))
