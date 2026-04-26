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


def should_scan(path: str) -> bool:
    return path in RELEVANT_EXACT or path.startswith(RELEVANT_PREFIXES) or path.endswith(RELEVANT_SUFFIXES)


def block(reason: str) -> int:
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def changed_paths(root: Path) -> list[str]:
    result = subprocess.run(["git", "diff", "--name-only", "HEAD", "--"], cwd=root, text=True, capture_output=True)
    if result.returncode != 0:
        return []
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip() and should_scan(line.strip())})


def main() -> int:
    # Prevent infinite Stop-hook loops. If this hook already blocked once
    # this turn, Claude Code re-fires Stop with stop_hook_active=true.
    # Letting it through here lets Claude actually exit.
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    if payload.get("stop_hook_active"):
        return 0

    root = project_root()
    paths = changed_paths(root)
    if not paths:
        return 0
    scanner = root / "scripts" / "safety_scan.py"
    if not scanner.exists():
        return block("Relevant pending changes exist, but scripts/safety_scan.py does not exist yet. Create it and rerun before ending the session.")
    cmd = [sys.executable, str(scanner), "--paths", *paths]
    result = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
    if result.returncode != 0:
        details = (result.stdout + "\n" + result.stderr).strip()
        return block("Pending safety scan failed for: " + ", ".join(paths) + ("\n" + details if details else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
