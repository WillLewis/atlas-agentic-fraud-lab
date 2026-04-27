"""Phase 10 demo bootstrap CLI.

One-command reviewer prep flow. From a fresh local checkout:

    python3 scripts/bootstrap_demo.py        # idempotent — runs only
                                              # missing steps
    python3 scripts/bootstrap_demo.py --check-only
                                              # verify prereqs +
                                              # report missing
                                              # artifacts; do nothing

The script:

  1. Verifies ``python3 >= 3.11`` and ``node >= 18`` (loose floors so
     local dev environments without exact 3.12/20 still pass).
  2. Runs ``make seed`` when ``data/synthetic/manifest.json`` is
     missing.
  3. Runs ``make train`` when the baseline model artifact is missing.
  4. Runs ``make run-rounds`` when ``outputs/runs/`` has no
     ``run_*.json``.
  5. Runs ``make build-replay`` when ``outputs/demo_replays/`` has no
     ``run_*.json``.
  6. Runs ``make safety-scan`` and surfaces any errors.
  7. Prints clear next-steps for ``make demo-api`` + ``make demo-web``.

No API keys required. No external network. Deterministic. Phase 10
acceptance: a reviewer can clone the repo and reach the demo state by
running this single script.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Prerequisite detection
# ---------------------------------------------------------------------------


@dataclass
class _Tool:
    name: str
    cmd: list[str]
    min_major: int
    min_minor: int


_PREREQS: tuple[_Tool, ...] = (
    _Tool("python3", ["python3", "--version"], 3, 11),
    _Tool("node", ["node", "--version"], 18, 0),
)


def _parse_version(text: str) -> tuple[int, int] | None:
    """Extract ``(major, minor)`` from version strings such as
    ``"Python 3.12.4"`` or ``"v20.10.0"``.
    """
    m = re.search(r"(\d+)\.(\d+)", text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def check_prereqs() -> list[str]:
    """Return a list of human-readable issue messages. Empty list = pass."""
    issues: list[str] = []
    for tool in _PREREQS:
        if shutil.which(tool.cmd[0]) is None:
            issues.append(f"{tool.name} not found on PATH.")
            continue
        try:
            out = subprocess.check_output(
                tool.cmd, stderr=subprocess.STDOUT, text=True,
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            issues.append(f"{tool.name} version probe failed: {exc}")
            continue
        ver = _parse_version(out)
        if ver is None:
            issues.append(
                f"{tool.name} version unparsable from output: {out.strip()!r}"
            )
            continue
        major, minor = ver
        if (major, minor) < (tool.min_major, tool.min_minor):
            issues.append(
                f"{tool.name} {major}.{minor} is below required "
                f"{tool.min_major}.{tool.min_minor}."
            )
    return issues


# ---------------------------------------------------------------------------
# Artifact presence checks — drive idempotent step skipping
# ---------------------------------------------------------------------------


def _dataset_seeded(repo: Path) -> bool:
    return (repo / "data" / "synthetic" / "manifest.json").exists()


def _baseline_trained(repo: Path) -> bool:
    return (
        repo / "outputs" / "baseline_models" / "baseline_v1" / "model.joblib"
    ).exists()


def _runs_present(repo: Path) -> bool:
    rdir = repo / "outputs" / "runs"
    if not rdir.exists():
        return False
    # ``run_*.json`` excluding per-round companions.
    for p in rdir.glob("run_*.json"):
        if ".round_" in p.stem:
            continue
        return True
    return False


def _replay_present(repo: Path) -> bool:
    rdir = repo / "outputs" / "demo_replays"
    if not rdir.exists():
        return False
    return any(rdir.glob("run_*.json"))


# ---------------------------------------------------------------------------
# Step orchestration
# ---------------------------------------------------------------------------


@dataclass
class _Step:
    label: str
    is_done: Callable[[Path], bool]
    make_target: str


_STEPS: tuple[_Step, ...] = (
    _Step("seed synthetic dataset", _dataset_seeded, "seed"),
    _Step("train baseline model", _baseline_trained, "train"),
    _Step("run three-round lifecycle", _runs_present, "run-rounds"),
    _Step("build replay payload", _replay_present, "build-replay"),
)


def _run_make(target: str, *, repo: Path) -> int:
    """Invoke ``make <target>`` with live stdout/stderr. Returns the
    target's exit code.
    """
    proc = subprocess.run(
        ["make", target], cwd=repo, check=False,
    )
    return proc.returncode


def run_pipeline(*, repo: Path, check_only: bool) -> int:
    """Execute the bootstrap pipeline. Returns 0 on success, non-zero
    on the first failed step.
    """
    print(f"atlas demo bootstrap — Phase 10")
    print(f"  repo root : {repo}")
    print(f"  mode      : {'check-only' if check_only else 'apply'}")
    print()

    # Step 0 — prereqs.
    prereq_issues = check_prereqs()
    if prereq_issues:
        print("[fail] prerequisite check:")
        for line in prereq_issues:
            print(f"  - {line}")
        return 2
    print("[ok] prerequisites: python3 + node found at acceptable versions")

    # Steps 1..4 — make targets gated by artifact presence.
    for step in _STEPS:
        if step.is_done(repo):
            print(f"[skip] {step.label} (artifacts present)")
            continue
        if check_only:
            print(
                f"[missing] {step.label} — run `make {step.make_target}` "
                "(or re-run without --check-only)"
            )
            continue
        print(f"[run] make {step.make_target}  ({step.label})")
        rc = _run_make(step.make_target, repo=repo)
        if rc != 0:
            print(
                f"[fail] make {step.make_target} exited {rc}. "
                f"Inspect the output above and re-run after the fix."
            )
            return rc
        # Re-check; if still missing, the make target produced nothing.
        if not step.is_done(repo):
            print(
                f"[fail] make {step.make_target} succeeded but the expected "
                f"artifact is still missing. This is a bug — file an issue."
            )
            return 1

    # Step 5 — safety scan over the public-mode tree.
    if check_only:
        print("[skip] safety scan (use --check-only to skip)")
    else:
        print("[run] make safety-scan")
        rc = _run_make("safety-scan", repo=repo)
        if rc != 0:
            print(
                "[fail] safety-scan failed. Phase 10 invariant: public-mode "
                "demo must pass safety scan before reviewer hand-off."
            )
            return rc

    # Step 6 — next steps.
    print()
    print("ready to run the demo:")
    print("  terminal 1:  make demo-api")
    print("  terminal 2:  make demo-web   # http://localhost:3000")
    print()
    print(
        "no API keys required — every surface is synthetic and local-only."
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap the Project Atlas local demo. Verifies "
            "prerequisites, runs `make seed/train/run-rounds/build-"
            "replay/safety-scan` as needed, and prints next steps. "
            "No API keys required."
        )
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help=(
            "Only verify prerequisites and existing artifacts; do not "
            "run any make targets."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repo root (default: this script's parent).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    return run_pipeline(repo=args.repo_root, check_only=args.check_only)


if __name__ == "__main__":
    sys.exit(main())
