#!/usr/bin/env python3
"""Project Atlas safety scanner.

Phase 0 stub. Reads config/safety.yaml and walks the configured paths (or
paths supplied via --paths), checking text files against a set of regex
rules: real institution names, internal paths, warehouse table identifiers,
secret-shaped strings, production endpoint URLs, PII-shaped strings, unsafe
red-team phrasing, and legacy terminology in public copy.

Exits non-zero in public mode if any `error`-severity rule matches. Warnings
do not fail the build but are printed.

This is the runtime entry point invoked by `make safety-scan` and by the
.claude/hooks/ scripts. The full implementation lives in
src/atlas/safety/scanner.py from Phase 10 onward; this stub uses the same
config and rule shape so callers stay stable.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:
    print(
        "safety_scan: pyyaml is required. Install with `pip install pyyaml` "
        "or `make setup`.",
        file=sys.stderr,
    )
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "safety.yaml"
MAX_BYTES = 2_000_000  # skip binary-ish files larger than 2 MB


@dataclass
class Rule:
    rule_id: str
    severity: str
    description: str
    patterns: list[re.Pattern[str]]


@dataclass
class Finding:
    path: Path
    line_no: int
    rule_id: str
    severity: str
    snippet: str


@dataclass
class ScanReport:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        print(f"safety_scan: config not found at {config_path}", file=sys.stderr)
        sys.exit(2)
    with config_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        print(f"safety_scan: {config_path} did not parse as a mapping", file=sys.stderr)
        sys.exit(2)
    return data


def compile_rules(config: dict) -> list[Rule]:
    rules_cfg = config.get("rules", []) or []
    compiled: list[Rule] = []
    for rule in rules_cfg:
        rid = rule.get("id")
        sev = rule.get("severity", "error")
        desc = rule.get("description", "")
        patterns = rule.get("patterns", []) or []
        compiled_patterns: list[re.Pattern[str]] = []
        for raw in patterns:
            try:
                compiled_patterns.append(re.compile(raw, re.IGNORECASE))
            except re.error as exc:
                print(
                    f"safety_scan: invalid regex in rule {rid!r}: {raw!r} ({exc})",
                    file=sys.stderr,
                )
                sys.exit(2)
        compiled.append(Rule(rule_id=rid, severity=sev, description=desc, patterns=compiled_patterns))
    return compiled


def is_ignored(rel_path: str, ignore_globs: Iterable[str]) -> bool:
    for pat in ignore_globs:
        if fnmatch.fnmatch(rel_path, pat):
            return True
    return False


def is_text_file(path: Path, text_extensions: set[str], must_scan: set[str]) -> bool:
    if path.name in must_scan:
        return True
    if path.suffix.lower() in text_extensions:
        return True
    # Files such as ".env.example" have a compound extension.
    if path.name.lower() in text_extensions:
        return True
    return False


def iter_candidate_files(
    roots: list[Path],
    ignore_globs: list[str],
    text_extensions: set[str],
    must_scan: set[str],
) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            try:
                rel = str(root.resolve().relative_to(REPO_ROOT))
            except ValueError:
                rel = str(root)
            if is_ignored(rel, ignore_globs):
                continue
            if not is_text_file(root, text_extensions, must_scan):
                continue
            if root not in seen:
                seen.add(root)
                yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune ignored directories early.
            dirpath_p = Path(dirpath)
            try:
                rel_dir = str(dirpath_p.resolve().relative_to(REPO_ROOT))
            except ValueError:
                rel_dir = dirpath
            if rel_dir != "." and is_ignored(rel_dir + "/", ignore_globs):
                dirnames[:] = []
                continue
            kept_dirs = []
            for d in dirnames:
                sub = dirpath_p / d
                try:
                    rel_sub = str(sub.resolve().relative_to(REPO_ROOT)) + "/"
                except ValueError:
                    rel_sub = str(sub) + "/"
                if not is_ignored(rel_sub, ignore_globs):
                    kept_dirs.append(d)
            dirnames[:] = kept_dirs

            for fname in filenames:
                fpath = dirpath_p / fname
                try:
                    rel_file = str(fpath.resolve().relative_to(REPO_ROOT))
                except ValueError:
                    rel_file = str(fpath)
                if is_ignored(rel_file, ignore_globs):
                    continue
                if not is_text_file(fpath, text_extensions, must_scan):
                    continue
                if fpath in seen:
                    continue
                seen.add(fpath)
                yield fpath


def scan_file(path: Path, rules: list[Rule]) -> list[Finding]:
    findings: list[Finding] = []
    try:
        size = path.stat().st_size
    except OSError:
        return findings
    if size > MAX_BYTES:
        return findings
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line_no, line in enumerate(fh, start=1):
                for rule in rules:
                    for pat in rule.patterns:
                        m = pat.search(line)
                        if m:
                            snippet = line.strip()
                            if len(snippet) > 200:
                                snippet = snippet[:200] + "…"
                            findings.append(
                                Finding(
                                    path=path,
                                    line_no=line_no,
                                    rule_id=rule.rule_id,
                                    severity=rule.severity,
                                    snippet=snippet,
                                )
                            )
                            # One match per rule per line is enough.
                            break
    except OSError as exc:
        print(f"safety_scan: could not read {path}: {exc}", file=sys.stderr)
    return findings


def resolve_roots(arg_paths: list[str], config: dict) -> list[Path]:
    raw = arg_paths or config.get("default_paths", []) or ["."]
    out: list[Path] = []
    for p in raw:
        candidate = Path(p)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        out.append(candidate)
    return out


def format_text(report: ScanReport, mode: str) -> str:
    lines: list[str] = []
    lines.append(f"safety_scan: mode={mode}")
    lines.append(f"safety_scan: files_scanned={report.files_scanned}")
    lines.append(
        f"safety_scan: findings errors={len(report.errors)} warnings={len(report.warnings)}"
    )
    for f in report.findings:
        try:
            rel = f.path.resolve().relative_to(REPO_ROOT)
        except ValueError:
            rel = f.path
        lines.append(
            f"  [{f.severity.upper()}] {rel}:{f.line_no} {f.rule_id} :: {f.snippet}"
        )
    return "\n".join(lines)


def format_json(report: ScanReport, mode: str) -> str:
    payload = {
        "mode": mode,
        "files_scanned": report.files_scanned,
        "errors": len(report.errors),
        "warnings": len(report.warnings),
        "findings": [
            {
                "path": str(f.path),
                "line": f.line_no,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "snippet": f.snippet,
            }
            for f in report.findings
        ],
    }
    return json.dumps(payload, indent=2)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="safety_scan",
        description="Project Atlas public-mode safety scanner.",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Paths to scan. Defaults to config/safety.yaml `default_paths`.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to safety config YAML (default: config/safety.yaml).",
    )
    parser.add_argument(
        "--mode",
        default=None,
        help="Override scanner mode (defaults to config `mode`, typically `public`).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Treat warnings as errors and exit non-zero.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    config = load_config(Path(args.config))
    mode = args.mode or config.get("mode", "public")
    rules = compile_rules(config)
    ignore_globs = list(config.get("ignore_globs", []) or [])
    text_extensions = {
        e.lower() for e in (config.get("text_extensions", []) or [])
    }
    must_scan = set(config.get("must_scan_files", []) or [])

    roots = resolve_roots(args.paths or [], config)
    report = ScanReport()
    for path in iter_candidate_files(roots, ignore_globs, text_extensions, must_scan):
        report.files_scanned += 1
        report.findings.extend(scan_file(path, rules))

    if args.format == "json":
        print(format_json(report, mode))
    else:
        print(format_text(report, mode))

    if report.errors:
        return 1
    if args.fail_on_warning and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
