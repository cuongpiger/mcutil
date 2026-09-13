from sqlalchemy.ext.asyncio import AsyncEngine

from mcutil.api import db


def test_database_url_points_at_sqlite_file():
    assert db.DATABASE_URL == "sqlite+aiosqlite:///./accounts.db"


def test_engine_is_async_engine():
    assert isinstance(db.engine, AsyncEngine)


def test_session_factory_does_not_expire_on_commit():
    assert db.async_session.kw["expire_on_commit"] is False
