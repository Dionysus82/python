"""Database engine, sessions and immutable-audit triggers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.models import Base

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None

AUDIT_INSERT_ONLY = """
CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit events are immutable');
END
"""

AUDIT_NO_DELETE = """
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit events are immutable');
END
"""


def _sqlite_connect(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def get_engine(settings: Settings | None = None) -> Engine:
    global _engine, _session_factory
    if _engine is None:
        settings = settings or get_settings()
        url = settings.database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        if url.startswith("sqlite"):
            event.listen(_engine, "connect", _sqlite_connect)
        _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


def session_scope() -> Iterator[Session]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def install_sqlite_guards(engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as connection:
        connection.execute(text(AUDIT_INSERT_ONLY))
        connection.execute(text(AUDIT_NO_DELETE))


def create_schema() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    install_sqlite_guards(engine)


def assert_safe_startup(settings: Settings | None = None) -> None:
    from app.domain.errors import ConfigurationError

    settings = settings or get_settings()
    if settings.is_production_profile and settings.secret_key == "hackathon-only-not-a-secret":
        raise ConfigurationError(
            "The production configuration profile refuses the default hackathon secret. "
            "This prototype is still not a production deployment."
        )
