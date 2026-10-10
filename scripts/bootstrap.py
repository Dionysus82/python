"""Create the schema, synthetic book, trusted documents and indexes."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings, reset_settings
from app.database import create_schema, get_session_factory, reset_engine
from app.ingestion.store import TrustedDocumentStore
from synthetic_data.build import build_world
from synthetic_data.persist import persist_world


def bootstrap(*, include_generics: bool = True, rebuild: bool = True) -> dict:
    reset_settings()
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if rebuild and settings.database_url.startswith("sqlite:///"):
        raw = settings.database_url.removeprefix("sqlite:///")
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.exists():
            path.unlink()
    reset_engine()
    create_schema()
    world = build_world(settings.demo_password, include_generics=include_generics)
    store = TrustedDocumentStore(settings.object_store_dir)
    session = get_session_factory()()
    try:
        counts = persist_world(session, world, store)
    finally:
        session.close()
    truth_path = settings.data_dir / "ground_truth.json"
    truth_path.write_text(json.dumps(world.truth, indent=2), encoding="utf-8")
    (settings.index_dir).mkdir(parents=True, exist_ok=True)
    (settings.index_dir / "README.txt").write_text(
        "Query-time indexes are built from the authorised subset. "
        "This directory records that the hackathon index path is configured.\n",
        encoding="utf-8",
    )
    return {"ingestion": counts, "truth": world.truth}


if __name__ == "__main__":
    result = bootstrap(include_generics=True, rebuild=True)
    print(json.dumps(result["truth"], indent=2))
    print(result["ingestion"])
