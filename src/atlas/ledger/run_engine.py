"""Phase 8 three-round lifecycle driver.

``execute_run`` builds an initial ``RunState``, loops
``execute_one_round`` for rounds 1..max_rounds, carries the accepted
model + threshold versions forward between rounds, and marks the run
``completed``. The result is a deterministic, byte-identical artifact
set: ``outputs/runs/<run_id>.json`` (final RunState),
``outputs/runs/<run_id>.round_NN.json`` (per-round RoundStates), and
``outputs/ledgers/<run_id>.jsonl`` (one row per completed round).

Carry-forward semantics:

  * Round 1 starts at ``baseline_v1`` + ``thresholds_v1``.
  * If the judge ACCEPTS a candidate, the round's
    ``model_version_after`` / ``threshold_version_after`` reflect the
    candidate versions. The next round's ``current_*_version`` is set
    from those.
  * If the judge REJECTS or no candidate is selected, the round's
    ``*_after`` == ``*_before`` and the next round inherits the
    unchanged versions.

This module is pure orchestration. All side effects flow through the
ledger primitives (component 2) and ``execute_one_round`` (component 4).
No HTTP self-calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from atlas.blue_team.strategy_agent import DEFAULT_ROUND_CONFIG_PATH
from atlas.ledger.ledger import (
    DEFAULT_BASELINE_MODEL_VERSION,
    DEFAULT_BASELINE_THRESHOLD_VERSION,
    DEFAULT_OUTPUTS_ROOT,
    RunState,
    make_run_id,
    persist_run_state,
    read_dataset_reference_now_utc,
)
from atlas.ledger.round_engine import execute_one_round
from atlas.model.loader import DEFAULT_DATA_DIR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Phase 8 default. The OpenAPI ``RunCreateRequest.max_rounds`` schema
# enforces minimum 1 / maximum 5; the round engine default matches the
# Bible §18 Phase 8 acceptance criterion of three rounds.
DEFAULT_MAX_ROUNDS: Final[int] = 3


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def execute_run(
    *,
    seed: int,
    run_label: str = "",
    demo_mode: str = "public",
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
    data_dir: Path = DEFAULT_DATA_DIR,
    round_config_path: Path = DEFAULT_ROUND_CONFIG_PATH,
) -> RunState:
    """Run the deterministic Phase 8 three-round lifecycle.

    Same ``(seed, run_label, demo_mode, max_rounds, dataset, code)`` →
    byte-identical run + ledger + per-round artifacts.

    Args:
        seed: master seed (drives ``run_id`` derivation + per-round
              search RNG).
        run_label: optional human-readable label folded into ``run_id``.
        demo_mode: ``"public"`` | ``"internal"``.
        max_rounds: number of rounds to execute (1–5, Phase 8 default 3).
        outputs_root: artifact root.
        data_dir: synthetic dataset root.
        round_config_path: path to ``config/round_config.yaml``.

    Returns:
        The final ``RunState`` with ``status="completed"``,
        ``current_round=max_rounds``, and ``current_*_version`` reflecting
        the last round's accepted carry-forward.

    Raises:
        ValueError: ``max_rounds < 1``.
        FileNotFoundError: missing dataset manifest.
        Other Phase 4–7 errors propagate from ``execute_one_round``.
    """
    if max_rounds < 1:
        raise ValueError(f"max_rounds must be >= 1; got {max_rounds}")

    # 1. Build initial RunState.
    run_id = make_run_id(seed=seed, run_label=run_label, demo_mode=demo_mode)
    created_at_utc = read_dataset_reference_now_utc(data_dir)

    run_state = RunState(
        run_id=run_id,
        seed=seed,
        demo_mode=demo_mode,
        status="running",
        created_at_utc=created_at_utc,
        current_round=0,
        current_model_version=DEFAULT_BASELINE_MODEL_VERSION,
        current_threshold_version=DEFAULT_BASELINE_THRESHOLD_VERSION,
        run_label=run_label,
        max_rounds=max_rounds,
    )
    persist_run_state(run_state, outputs_root=outputs_root)

    # 2. Loop rounds 1..max_rounds, carrying versions forward.
    for round_id in range(1, max_rounds + 1):
        round_state = execute_one_round(
            run_state,
            round_id,
            outputs_root=outputs_root,
            data_dir=data_dir,
            round_config_path=round_config_path,
        )

        # 3. Build the next round's RunState.
        # Carry-forward: when judge accepts, ``round_state.model_version_after``
        # already reflects the candidate version. When rejected (or no
        # candidate), ``*_after`` == ``*_before`` so the next round
        # inherits unchanged.
        run_state = RunState(
            run_id=run_state.run_id,
            seed=run_state.seed,
            demo_mode=run_state.demo_mode,
            status="running",
            created_at_utc=run_state.created_at_utc,
            current_round=round_id,
            current_model_version=round_state.model_version_after,
            current_threshold_version=round_state.threshold_version_after,
            run_label=run_state.run_label,
            max_rounds=run_state.max_rounds,
        )

    # 4. Mark completed.
    final_state = RunState(
        run_id=run_state.run_id,
        seed=run_state.seed,
        demo_mode=run_state.demo_mode,
        status="completed",
        created_at_utc=run_state.created_at_utc,
        current_round=max_rounds,
        current_model_version=run_state.current_model_version,
        current_threshold_version=run_state.current_threshold_version,
        run_label=run_state.run_label,
        max_rounds=run_state.max_rounds,
    )

    # 5. Persist final RunState (overwrites the initial one with the
    # completed state).
    persist_run_state(final_state, outputs_root=outputs_root)

    return final_state


__all__ = [
    "DEFAULT_MAX_ROUNDS",
    "execute_run",
]
