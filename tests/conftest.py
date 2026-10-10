"""Session database built from the deterministic synthetic generator."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / ".pytest_data"
os.environ["DATA_DIR"] = str(TEST_DATA)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATA / 'harbour.db'}"
os.environ["APP_ENV"] = "test"
os.environ["DEMO_PASSWORD"] = "Harbour-Demo-2026"

from app.config import reset_settings  # noqa: E402
from app.database import get_session_factory, reset_engine  # noqa: E402

reset_settings()
reset_engine()


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    TEST_DATA.mkdir(parents=True, exist_ok=True)
    db_path = TEST_DATA / "harbour.db"
    if db_path.exists():
        db_path.unlink()
    from scripts.bootstrap import bootstrap

    bootstrap(include_generics=False, rebuild=True)
    yield
    reset_engine()


@pytest.fixture()
def db(seeded_database):
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
