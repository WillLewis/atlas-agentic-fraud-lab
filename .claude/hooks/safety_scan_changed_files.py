#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

RELEVANT_PREFIXES = (
    "app/web/",
    "data/fixtures/",
    "outputs/",
)
RELEVANT_EXACT = {
    "config/agent_roster.yaml",
    "config/safety.yaml",
    "scripts/safety_scan.py",
}
RELEVANT_SUFFIXES = ("_prompt.py",)


def project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve()


def normalize_path(raw: str, root: Path) -> str | None:
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def should_scan(rel_path: str) -> bool:
    return (
        rel_path in RELEVANT_EXACT
        or rel_path.startswith(RELEVANT_PREFIXES)
        or rel_path.endswith(RELEVANT_SUFFIXES)
    )


def extract_paths(payload: dict, root: Path) -> list[str]:
    tool_input = payload.get("tool_input") or {}
    raw_paths = []
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            raw_paths.append(value)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and isinstance(edit.get("file_path"), str):
                raw_paths.append(edit["file_path"])
    rel_paths = []
    for raw in raw_paths:
        rel = normalize_path(raw, root)
        if rel and should_scan(rel):
            rel_paths.append(rel)
    return sorted(set(rel_paths))


def block(reason: str) -> int:
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def main() -> int:
    root = project_root()
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    paths = extract_paths(payload, root)
    if not paths:
        return 0
    scanner = root / "scripts" / "safety_scan.py"
    if not scanner.exists():
        return block("Relevant files changed, but scripts/safety_scan.py does not exist yet. Create it before editing public copy, fixtures, outputs, agent roster, safety config, or prompt files.")
    cmd = [sys.executable, str(scanner), "--paths", *paths]
    result = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
    if result.returncode != 0:
        details = (result.stdout + "\n" + result.stderr).strip()
        return block("Targeted safety scan failed for changed files: " + ", ".join(paths) + ("\n" + details if details else ""))
    if result.stdout.strip():
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": result.stdout.strip()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
