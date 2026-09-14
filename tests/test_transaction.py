from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from mcutil.api import db
from mcutil.api.account import Sex, create_account
from mcutil.api.transaction import Transaction, TransactionType, deposit


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


def test_transaction_type_enum_members():
    assert [t.value for t in TransactionType] == ["deposit"]


def test_transaction_type_is_a_str_enum():
    assert TransactionType.deposit == "deposit"


@pytest.mark.asyncio
async def test_deposit_updates_account_balance(session):
    acct = await create_account(session, "Alice", Sex.female, 5000.0)
    await session.commit()

    await deposit(session, acct.id, 250.0)
    await session.commit()

    assert acct.balance == 5250.0


@pytest.mark.asyncio
async def test_deposit_creates_transaction_record(session):
    acct = await create_account(session, "Alice", Sex.female, 5000.0)
    await session.commit()

    tx = await deposit(session, acct.id, 250.0)
    await session.commit()

    rows = (await session.execute(select(Transaction))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == tx.id
    assert rows[0].account_id == acct.id


@pytest.mark.asyncio
async def test_deposit_returns_none_for_missing_account(session):
    assert await deposit(session, 999, 250.0) is None


@pytest.mark.asyncio
async def test_deposit_recorded_type_is_deposit(session):
    acct = await create_account(session, "Alice", Sex.female, 5000.0)
    await session.commit()

    tx = await deposit(session, acct.id, 250.0)
    await session.commit()

    assert tx.type is TransactionType.deposit


@pytest.mark.asyncio
async def test_deposit_recorded_amount_matches_input(session):
    acct = await create_account(session, "Alice", Sex.female, 5000.0)
    await session.commit()

    tx = await deposit(session, acct.id, 250.0)
    await session.commit()

    assert tx.amount == 250.0


@pytest.mark.asyncio
async def test_deposit_populates_id_and_created_at(session):
    acct = await create_account(session, "Alice", Sex.female, 5000.0)
    await session.commit()

    tx = await deposit(session, acct.id, 250.0)

    assert tx.id is not None
    assert isinstance(tx.created_at, datetime)


@pytest.mark.asyncio
async def test_deposit_does_not_touch_other_accounts(session):
    first = await create_account(session, "Alice", Sex.female, 1000.0)
    second = await create_account(session, "Bob", Sex.male, 2000.0)
    await session.commit()

    await deposit(session, second.id, 500.0)
    await session.commit()

    assert first.balance == 1000.0
    assert second.balance == 2500.0


@pytest.mark.asyncio
async def test_deposit_twice_accumulates(session):
    acct = await create_account(session, "Alice", Sex.female, 100.0)
    await session.commit()

    await deposit(session, acct.id, 50.0)
    await deposit(session, acct.id, 25.0)
    await session.commit()

    assert acct.balance == 175.0
    rows = (await session.execute(select(Transaction))).scalars().all()
    assert len(rows) == 2
