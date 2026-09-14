# Deposit Money to Account API Implementation Plan

> **For agentic workers:** Execute this plan one task at a time with executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `POST /accounts/{account_id}/deposits` endpoint that validates a positive amount, increases the account's balance, and records a `Transaction` row for auditing.

**Architecture:** A new `mcutil/api/transaction.py` module owns the `TransactionType` enum, the `Transaction` ORM model, and a `deposit()` data-access function — mirroring how `mcutil/api/account.py` owns `Sex`, `Account`, and its data-access functions. The route handler and its Pydantic request/response models are added to the existing `mcutil/api/app.py`, matching where `POST /accounts` and `GET /accounts/{account_id}` already live. No new dependencies.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 async ORM, aiosqlite, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-14-deposit-money-to-account-api-design.md`

## Global Constraints

- No new dependencies. `requirements.txt` and `requirements-dev.txt` are NOT modified by this plan.
- The route is exactly `POST /accounts/{account_id}/deposits`. The path parameter is named `account_id` and typed `int` — a bare `int` annotation already makes FastAPI return 422 for non-integer input. Do NOT add a regex `Path(...)` constraint.
- The 404 detail string is exactly `"Account not found."` (capital A, trailing period) — identical to the existing `GET /accounts/{account_id}` handler.
- The positive-amount 422 detail string is exactly `"Deposit amount must be positive."` (capital D, trailing period).
- `deposit()` returns `Transaction | None`. It MUST NOT raise on a missing account, and MUST NOT call `commit()` — HTTP-level concerns stay in `app.py`, and committing is the caller's job. This matches `create_account()` and `get_account()`.
- Scope is deposit only. Do NOT add withdrawals, transfers, a transaction-listing endpoint, pagination, authentication, or authorization. `TransactionType` has exactly one member, `deposit`.
- Follow the existing file style in this repo: standard-library imports first, then third-party, then relative `from . import ...` / `from .db import ...`; docstrings on public classes and async functions; max line length 120.
- Run tests with `python3 -m pytest`. `pytest.ini` sets `asyncio_mode = auto`, but existing async tests still carry an explicit `@pytest.mark.asyncio` — keep that convention.

## Environment Setup

The sandbox may not have the project dependencies installed. Before Task 1, run:

```bash
cd /sandbox/repo && pip install -r requirements.txt -r requirements-dev.txt
```

Verify the pre-existing suite is green before changing anything — it should report **32 passed**:

```bash
cd /sandbox/repo && python3 -m pytest -q
```

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `mcutil/api/transaction.py` | Create | `TransactionType` enum, `Transaction` model, `deposit()` data-access function |
| `tests/test_transaction.py` | Create | Unit tests for the model and `deposit()` |
| `mcutil/api/app.py` | Modify | `DepositRequest` / `DepositResponse` models and the `POST /accounts/{account_id}/deposits` route |
| `tests/test_api.py` | Modify | Endpoint tests for the deposit route |
| `README.md` | Modify | Document the new endpoint under `### Account management` |

Task 1 delivers the data layer and is independently testable via `tests/test_transaction.py`. Task 2 delivers the HTTP surface plus its documentation. A reviewer could reject either without rejecting the other.

---

### Task 1: `Transaction` model and `deposit()` data-access function

**Files:**
- Create: `mcutil/api/transaction.py`
- Test: `tests/test_transaction.py` (create)

**Interfaces:**
- Consumes: `Base` from `mcutil/api/db.py`; `Account` and `Sex` from `mcutil/api/account.py`. The `Account` model has columns `id`, `name`, `sex`, `balance`.
- Produces, all imported by Task 2 as `transaction.<name>`:
  - `class TransactionType(str, enum.Enum)` with a single member `deposit = "deposit"`.
  - `class Transaction(Base)`, `__tablename__ = "transactions"`, columns `id: int`, `account_id: int`, `amount: float`, `type: TransactionType`, `created_at: datetime`.
  - `async def deposit(session: AsyncSession, account_id: int, amount: float) -> Transaction | None` — adds `amount` to the account's balance and inserts a `Transaction` row, returning it with `id` and `created_at` populated; returns `None` when no account has that id.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_transaction.py` with exactly this content. The `session` fixture mirrors the one at the top of `tests/test_account.py` — it builds a throwaway in-memory SQLite database and creates every table registered on `db.Base`. Importing both `account` and `transaction` above is what registers the `accounts` and `transactions` tables.

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_transaction.py -q`

Expected: collection error — `ModuleNotFoundError: No module named 'mcutil.api.transaction'`.

- [ ] **Step 3: Write the implementation**

Create `mcutil/api/transaction.py` with exactly this content:

```python
import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer
from sqlalchemy import Enum as SAEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .account import Account
from .db import Base


class TransactionType(str, enum.Enum):
    """The kind of movement a transaction records."""

    deposit = "deposit"


class Transaction(Base):
    """An audit record of a single movement of money on an account."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


async def deposit(
    session: AsyncSession, account_id: int, amount: float
) -> Transaction | None:
    """Credit *amount* to an account and record the deposit.

    Returns ``None`` if no account has *account_id* — the caller decides what
    a missing account means. Flushes so the returned transaction has its
    generated ``id`` and ``created_at``, but leaves committing to the caller.
    """
    account = await session.get(Account, account_id)
    if account is None:
        return None
    account.balance += amount
    transaction = Transaction(
        account_id=account_id, amount=amount, type=TransactionType.deposit
    )
    session.add(transaction)
    await session.flush()
    return transaction
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_transaction.py -q`

Expected: **10 passed**.

- [ ] **Step 5: Run the whole suite to check nothing regressed**

Run: `cd /sandbox/repo && python3 -m pytest -q`

Expected: **42 passed** (32 pre-existing + 10 new).

- [ ] **Step 6: Commit**

```bash
cd /sandbox/repo && git add mcutil/api/transaction.py tests/test_transaction.py && \
git commit -m "feat: add Transaction model and deposit() data-access function

Records each deposit as an auditable row and credits the account balance.
Returns None for a missing account so the HTTP layer owns the 404.

Co-Authored-By: Marcus <noreply@pfm-agent.local>"
```

---

### Task 2: `POST /accounts/{account_id}/deposits` endpoint

**Files:**
- Modify: `mcutil/api/app.py`
- Modify: `tests/test_api.py`
- Modify: `README.md`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: from Task 1, `transaction.deposit(session, account_id, amount) -> Transaction | None` and `Transaction.type` typed `TransactionType` (a `str` enum, so `.value` yields `"deposit"`). Also the existing `db.async_session` session factory and the existing `account_client` fixture in `tests/test_api.py` (defined at line 130), which patches `db.engine` and `db.async_session` to a throwaway in-memory database.
- Produces: the HTTP endpoint. Nothing later in this plan depends on it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api.py`:

```python
def _make_account(client, balance=5000.0):
    """Create an account and return its id."""
    resp = client.post(
        "/accounts",
        json={"name": "Alice", "sex": "female", "balance": balance},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_deposit_success(account_client):
    account_id = _make_account(account_client)

    resp = account_client.post(
        f"/accounts/{account_id}/deposits", json={"amount": 250.0}
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == 1
    assert body["account_id"] == account_id
    assert body["amount"] == 250.0
    assert body["type"] == "deposit"
    assert body["created_at"]


def test_deposit_updates_account_balance(account_client):
    account_id = _make_account(account_client, balance=5000.0)

    account_client.post(
        f"/accounts/{account_id}/deposits", json={"amount": 250.0}
    )

    fetched = account_client.get(f"/accounts/{account_id}")
    assert fetched.json()["balance"] == 5250.0


def test_deposit_invalid_amount_zero(account_client):
    account_id = _make_account(account_client)

    resp = account_client.post(
        f"/accounts/{account_id}/deposits", json={"amount": 0}
    )

    assert resp.status_code == 422
    assert resp.json()["detail"] == "Deposit amount must be positive."


def test_deposit_invalid_amount_negative(account_client):
    account_id = _make_account(account_client)

    resp = account_client.post(
        f"/accounts/{account_id}/deposits", json={"amount": -100.0}
    )

    assert resp.status_code == 422
    assert resp.json()["detail"] == "Deposit amount must be positive."


def test_deposit_rejected_amount_leaves_balance_unchanged(account_client):
    account_id = _make_account(account_client, balance=5000.0)

    account_client.post(
        f"/accounts/{account_id}/deposits", json={"amount": -100.0}
    )

    fetched = account_client.get(f"/accounts/{account_id}")
    assert fetched.json()["balance"] == 5000.0


def test_deposit_missing_amount_field(account_client):
    account_id = _make_account(account_client)

    resp = account_client.post(f"/accounts/{account_id}/deposits", json={})

    assert resp.status_code == 422


def test_deposit_non_numeric_amount(account_client):
    account_id = _make_account(account_client)

    resp = account_client.post(
        f"/accounts/{account_id}/deposits", json={"amount": "lots"}
    )

    assert resp.status_code == 422


def test_deposit_account_not_found(account_client):
    resp = account_client.post("/accounts/999/deposits", json={"amount": 250.0})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Account not found."


def test_deposit_non_integer_account_id(account_client):
    resp = account_client.post(
        "/accounts/abc/deposits", json={"amount": 250.0}
    )

    assert resp.status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_api.py -q -k deposit`

Expected: FAIL — the route does not exist, so the successful cases get 404 with FastAPI's default `"Not Found"` detail rather than the expected 201/422 bodies.

- [ ] **Step 3: Write the implementation**

In `mcutil/api/app.py`, first extend the relative import on line 7 so the new module is in scope. Change:

```python
from . import account, binance, db, vnstock
```

to:

```python
from . import account, binance, db, transaction, vnstock
```

Then add `datetime` to the standard-library imports at the top of the file, on the line immediately after `from contextlib import asynccontextmanager` (alphabetical order, before `from typing import Annotated`):

```python
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated
```

Finally append to the end of `mcutil/api/app.py`, after the existing `get_account` route:

```python
class DepositRequest(BaseModel):
    amount: float


class DepositResponse(BaseModel):
    id: int
    account_id: int
    amount: float
    type: str
    created_at: datetime


@app.post(
    "/accounts/{account_id}/deposits",
    response_model=DepositResponse,
    status_code=201,
)
async def deposit(account_id: int, payload: DepositRequest):
    """Credit money to an account and record the deposit."""
    if payload.amount <= 0:
        raise HTTPException(
            status_code=422, detail="Deposit amount must be positive."
        )
    async with db.async_session() as session:
        recorded = await transaction.deposit(
            session, account_id, payload.amount
        )
        if recorded is None:
            raise HTTPException(status_code=404, detail="Account not found.")
        await session.commit()
    return DepositResponse(
        id=recorded.id,
        account_id=recorded.account_id,
        amount=recorded.amount,
        type=recorded.type.value,
        created_at=recorded.created_at,
    )
```

Note on why this works: `db.async_session` is built with `expire_on_commit=False`, so `recorded`'s attributes are still readable after the `async with` block closes — the same reason the existing `create_account` route can build its response outside the block. Raising the 404 inside the block is fine; the context manager closes the session without committing, so the balance change is discarded.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_api.py -q -k deposit`

Expected: **9 passed**.

- [ ] **Step 5: Run the whole suite**

Run: `cd /sandbox/repo && python3 -m pytest -q`

Expected: **51 passed** (32 pre-existing + 10 from Task 1 + 9 new).

- [ ] **Step 6: Document the endpoint**

In `README.md`, inside the `### Account management` section, append after the existing "Fetch an existing account by its ID" example and before the `### Tests` heading:

````markdown
Deposit money into an account. The amount must be positive; the account's
balance is credited and the deposit is recorded for auditing:

```bash
curl -X POST http://127.0.0.1:8000/accounts/1/deposits \
  -H "Content-Type: application/json" \
  -d '{"amount":250.0}'
# {"id":1,"account_id":1,"amount":250.0,"type":"deposit","created_at":"2026-09-14T03:25:00"}

# A non-positive amount is rejected
curl -X POST http://127.0.0.1:8000/accounts/1/deposits \
  -H "Content-Type: application/json" \
  -d '{"amount":-50.0}'
# {"detail":"Deposit amount must be positive."}

# An unknown account ID returns 404
curl -X POST http://127.0.0.1:8000/accounts/999/deposits \
  -H "Content-Type: application/json" \
  -d '{"amount":250.0}'
# {"detail":"Account not found."}
```
````

- [ ] **Step 7: Commit**

```bash
cd /sandbox/repo && git add mcutil/api/app.py tests/test_api.py README.md && \
git commit -m "feat: add POST /accounts/{account_id}/deposits endpoint

Validates the amount is positive before touching the account, returns the
recorded transaction on success, and documents the endpoint in the README.

Co-Authored-By: Marcus <noreply@pfm-agent.local>"
```
