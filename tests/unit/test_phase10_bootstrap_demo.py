"""Phase 10 bootstrap-script unit tests.

Validates the prereq-check + artifact-detection logic in
``scripts/bootstrap_demo.py`` without invoking real ``make`` targets.
The full make-pipeline path is exercised manually via ``make bootstrap``
(documented in the README quickstart).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module() -> Any:
    """Load ``scripts/bootstrap_demo.py`` by path so tests work
    regardless of pytest collection order or PYTHONPATH.
    """
    if "bootstrap_demo" in sys.modules:
        return sys.modules["bootstrap_demo"]
    spec = importlib.util.spec_from_file_location(
        "bootstrap_demo", REPO_ROOT / "scripts" / "bootstrap_demo.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bootstrap_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------


def test_parse_version_python_string():
    mod = _load_module()
    assert mod._parse_version("Python 3.12.4") == (3, 12)


def test_parse_version_node_string():
    mod = _load_module()
    assert mod._parse_version("v20.10.0") == (20, 10)


def test_parse_version_unparsable_returns_none():
    mod = _load_module()
    assert mod._parse_version("no-numbers-here") is None


# ---------------------------------------------------------------------------
# Artifact presence detectors
# ---------------------------------------------------------------------------


def test_dataset_seeded_false_when_missing(tmp_path):
    mod = _load_module()
    assert mod._dataset_seeded(tmp_path) is False


def test_dataset_seeded_true_when_manifest_present(tmp_path):
    mod = _load_module()
    syn = tmp_path / "data" / "synthetic"
    syn.mkdir(parents=True)
    (syn / "manifest.json").write_text("{}")
    assert mod._dataset_seeded(tmp_path) is True


def test_baseline_trained_false_when_missing(tmp_path):
    mod = _load_module()
    assert mod._baseline_trained(tmp_path) is False


def test_baseline_trained_true_when_artifact_present(tmp_path):
    mod = _load_module()
    bdir = tmp_path / "outputs" / "baseline_models" / "baseline_v1"
    bdir.mkdir(parents=True)
    (bdir / "model.joblib").write_bytes(b"")
    assert mod._baseline_trained(tmp_path) is True


def test_runs_present_skips_round_companions(tmp_path):
    """``run_xxx.round_NN.json`` alone shouldn't count as 'runs present'."""
    mod = _load_module()
    rdir = tmp_path / "outputs" / "runs"
    rdir.mkdir(parents=True)
    # Only round companion present, no run state file.
    (rdir / "run_x.round_01.json").write_text("{}")
    assert mod._runs_present(tmp_path) is False
    # Adding the run state file flips it true.
    (rdir / "run_x.json").write_text("{}")
    assert mod._runs_present(tmp_path) is True


def test_replay_present_false_when_only_gitkeep(tmp_path):
    mod = _load_module()
    rdir = tmp_path / "outputs" / "demo_replays"
    rdir.mkdir(parents=True)
    (rdir / ".gitkeep").write_text("")
    assert mod._replay_present(tmp_path) is False


def test_replay_present_true_when_run_json_present(tmp_path):
    mod = _load_module()
    rdir = tmp_path / "outputs" / "demo_replays"
    rdir.mkdir(parents=True)
    (rdir / "run_test.json").write_text("{}")
    assert mod._replay_present(tmp_path) is True


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


def test_parse_args_default():
    mod = _load_module()
    ns = mod.parse_args([])
    assert ns.check_only is False
    assert ns.repo_root == mod.REPO_ROOT


def test_parse_args_check_only():
    mod = _load_module()
    ns = mod.parse_args(["--check-only"])
    assert ns.check_only is True


# ---------------------------------------------------------------------------
# run_pipeline — check-only mode reports correctly without running make
# ---------------------------------------------------------------------------


def test_run_pipeline_check_only_with_missing_artifacts(tmp_path, capsys):
    """``--check-only`` against an empty repo reports missing steps but
    does NOT invoke any make targets. Exit 0 (check-only is informational).
    """
    mod = _load_module()
    rc = mod.run_pipeline(repo=tmp_path, check_only=True)
    captured = capsys.readouterr().out
    assert rc == 0
    # Each missing step is surfaced.
    for label in (
        "seed synthetic dataset",
        "train baseline model",
        "run three-round lifecycle",
        "build replay payload",
    ):
        assert label in captured
    # Safety-scan is explicitly skipped in check-only.
    assert "[skip] safety scan" in captured


def test_run_pipeline_check_only_with_all_artifacts_present(tmp_path, capsys):
    """All artifacts present → all steps skipped; exit 0; next-steps printed."""
    mod = _load_module()
    # Plant artifacts.
    syn = tmp_path / "data" / "synthetic"
    syn.mkdir(parents=True)
    (syn / "manifest.json").write_text("{}")
    bdir = tmp_path / "outputs" / "baseline_models" / "baseline_v1"
    bdir.mkdir(parents=True)
    (bdir / "model.joblib").write_bytes(b"")
    rdir = tmp_path / "outputs" / "runs"
    rdir.mkdir(parents=True)
    (rdir / "run_x.json").write_text("{}")
    repdir = tmp_path / "outputs" / "demo_replays"
    repdir.mkdir(parents=True)
    (repdir / "run_x.json").write_text("{}")

    rc = mod.run_pipeline(repo=tmp_path, check_only=True)
    captured = capsys.readouterr().out
    assert rc == 0
    assert captured.count("[skip]") >= 4  # seed/train/run-rounds/build-replay
    assert "make demo-api" in captured
    assert "make demo-web" in captured
