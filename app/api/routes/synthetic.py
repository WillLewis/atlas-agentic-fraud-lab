"""GET /synthetic/sample route.

Reads ONLY the global readable Phase 2/3 artifacts:

  data/synthetic/entities/customers.json        (train+val+clean)
  data/synthetic/events/transfer_events.json    (train+val+clean)
  data/synthetic/features/{train,validation,clean_holdout}.json

Never reads ``holdouts/locked/*`` or ``holdouts/drifted/labels/*``. The
``.claude/settings.json`` deny rules also gate those at the OS layer; this
route's logic enforces it at the application layer too.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.adapters import (  # noqa: E402
    customer_to_api_view,
    transfer_event_to_event_record,
)
from app.api.schemas.synthetic import (  # noqa: E402
    CustomerSchema,
    EventRecordSchema,
    FeatureVectorSchema,
    SyntheticSampleResponse,
)

DATA_DIR = REPO_ROOT / "data" / "synthetic"
SAMPLE_LIMIT_MIN = 1
SAMPLE_LIMIT_MAX = 100
SAMPLE_LIMIT_DEFAULT = 10

# Allowed feature partition files. Locked + drifted feature artifacts live
# under holdouts/*/ and are never loaded here.
GLOBAL_FEATURE_FILES = ("train.json", "validation.json", "clean_holdout.json")

router = APIRouter()


def _load_json(path: Path) -> list:
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Phase 2/3 artifact not found at {path.relative_to(REPO_ROOT)}. "
                f"Run `make seed` to generate the synthetic dataset."
            ),
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@router.get("/synthetic/sample", response_model=SyntheticSampleResponse)
def get_synthetic_sample(
    limit: int = Query(SAMPLE_LIMIT_DEFAULT, ge=SAMPLE_LIMIT_MIN, le=SAMPLE_LIMIT_MAX),
) -> SyntheticSampleResponse:
    customers = _load_json(DATA_DIR / "entities" / "customers.json")
    transfers = _load_json(DATA_DIR / "events" / "transfer_events.json")

    feature_records: list[dict] = []
    for fname in GLOBAL_FEATURE_FILES:
        feature_records.extend(_load_json(DATA_DIR / "features" / fname))

    # Sample the first `limit` transfer events; pair with matching features
    # and customers. Walking in insertion order keeps the response
    # deterministic given the on-disk dataset.
    sampled_transfers = transfers[:limit]
    sampled_event_ids = {t["transfer_event_id"] for t in sampled_transfers}
    sampled_customer_ids = {t["customer_id"] for t in sampled_transfers}

    sampled_features = [
        f for f in feature_records if f["event_id"] in sampled_event_ids
    ]
    sampled_customers = [
        c for c in customers if c["customer_id"] in sampled_customer_ids
    ]

    events = [
        EventRecordSchema(**transfer_event_to_event_record(t))
        for t in sampled_transfers
    ]
    return SyntheticSampleResponse(
        customers=[CustomerSchema(**customer_to_api_view(c)) for c in sampled_customers],
        events=events,
        features=[FeatureVectorSchema(**f) for f in sampled_features],
    )
