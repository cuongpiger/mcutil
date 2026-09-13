import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from mcutil.api import db
from mcutil.api.account import Account, Sex, create_account


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def test_sex_enum_members():
    assert [s.value for s in Sex] == ["male", "female", "other"]


def test_sex_is_a_str_enum():
    assert Sex.female == "female"


@pytest.mark.asyncio
async def test_create_account_returns_persisted_account(session):
    acct = await create_account(session, "Alice", Sex.female, 5000.0)
    await session.commit()

    assert acct.id == 1
    assert acct.name == "Alice"
    assert acct.sex is Sex.female
    assert acct.balance == 5000.0


@pytest.mark.asyncio
async def test_create_account_assigns_increasing_ids(session):
    first = await create_account(session, "Alice", Sex.female, 1.0)
    second = await create_account(session, "Bob", Sex.male, 2.0)
    await session.commit()

    assert second.id > first.id


@pytest.mark.asyncio
async def test_account_is_readable_after_commit(session):
    acct = await create_account(session, "Carol", Sex.other, 42.5)
    await session.commit()

    fetched = await session.get(Account, acct.id)
    assert fetched.name == "Carol"
    assert fetched.sex is Sex.other
    assert fetched.balance == 42.5
