# Account Model and Create Account API Implementation Plan

> **For agentic workers:** Execute this plan one task at a time with executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `Account` model (name, sex, balance) persisted in SQLite and a `POST /accounts` endpoint that creates accounts.

**Architecture:** Database infrastructure (engine, session factory, lifecycle) lives in a new `mcutil/api/db.py`. The `Account` ORM model and its creation function live in a new `mcutil/api/account.py`. The endpoint plus its Pydantic request/response models are added to the existing `mcutil/api/app.py`, matching how `binance` and `vnstock` are already wired into that file.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 async ORM, aiosqlite, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-account-model-and-create-account-api-design.md`

## Global Constraints

- New dependencies are exactly `sqlalchemy[asyncio]>=2.0` and `aiosqlite>=0.20`, appended to `requirements.txt`. Do not add any other dependency.
- Production database URL is exactly `sqlite+aiosqlite:///./accounts.db`.
- `Sex` enum values are exactly `male`, `female`, `other` (lowercase).
- `Sex` MUST subclass `str` as well as `enum.Enum` (`class Sex(str, enum.Enum)`) so the same enum serves both SQLAlchemy column typing and Pydantic request validation, and so JSON responses serialise as plain strings.
- The session factory MUST be constructed with `expire_on_commit=False`. Without it, reading `account.id` after `session.commit()` triggers a lazy refresh outside the session and raises.
- Scope is create-only. Do NOT add GET, PUT, PATCH, or DELETE endpoints, authentication, or validation beyond Pydantic defaults.
- Follow the existing file style in this repo: standard-library imports first, then third-party, then relative `from . import ...`; module-level constants in UPPER_CASE; docstrings on public async functions.
- Run tests with `python3 -m pytest`.

## Environment Setup

The sandbox may not have the project dependencies installed. Before Task 1, run:

```bash
cd /sandbox/repo && pip install -r requirements-dev.txt
```

Verify the pre-existing suite is green before changing anything — it should report **11 passed**:

```bash
cd /sandbox/repo && python3 -m pytest tests/test_api.py -q
```

If this fails with `The starlette.testclient module requires the httpx2 package`, it means `httpx` is missing; the `pip install` above fixes it. This is an environment gap, not a code defect.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `requirements.txt` | Modify | Declare the two new dependencies |
| `mcutil/api/db.py` | Create | Async engine, `Base`, session factory, `init_db()`, `close_engine()` |
| `mcutil/api/account.py` | Create | `Sex` enum, `Account` ORM model, `create_account()` |
| `mcutil/api/app.py` | Modify | `AccountCreate`/`AccountResponse` models, `POST /accounts`, lifespan wiring |
| `tests/test_api.py` | Modify | Account endpoint tests + in-memory DB fixture |
| `README.md` | Modify | Document the new endpoint |

---

### Task 1: Database infrastructure and dependencies

**Files:**
- Modify: `requirements.txt`
- Create: `mcutil/api/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `db.Base` — `DeclarativeBase` subclass that ORM models inherit from
  - `db.engine` — module-level `AsyncEngine`
  - `db.async_session` — module-level `async_sessionmaker[AsyncSession]`, built with `expire_on_commit=False`
  - `async def db.init_db() -> None`
  - `async def db.close_engine() -> None`
  - `db.DATABASE_URL: str`

- [ ] **Step 1: Add the dependencies**

Append these two lines to `requirements.txt` so the full file reads:

```
fastapi>=0.110
uvicorn[standard]>=0.29
httpx>=0.27
sqlalchemy[asyncio]>=2.0
aiosqlite>=0.20
```

- [ ] **Step 2: Install them**

Run: `cd /sandbox/repo && pip install -r requirements-dev.txt`
Expected: completes successfully, installing `sqlalchemy` and `aiosqlite`.

- [ ] **Step 3: Write the failing test**

Create `tests/test_db.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from mcutil.api import db


def test_database_url_points_at_sqlite_file():
    assert db.DATABASE_URL == "sqlite+aiosqlite:///./accounts.db"


def test_engine_is_async_engine():
    assert isinstance(db.engine, AsyncEngine)


def test_session_factory_does_not_expire_on_commit():
    assert db.async_session.kw["expire_on_commit"] is False
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_db.py -v`
Expected: FAIL at import with `ImportError: cannot import name 'db' from 'mcutil.api'`.

- [ ] **Step 5: Write the implementation**

Create `mcutil/api/db.py`:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "sqlite+aiosqlite:///./accounts.db"


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create any tables that do not yet exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine() -> None:
    """Dispose of the engine and its connection pool."""
    await engine.dispose()
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_db.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 7: Confirm nothing regressed**

Run: `cd /sandbox/repo && python3 -m pytest -q`
Expected: 14 passed (11 pre-existing + 3 new).

- [ ] **Step 8: Commit**

```bash
cd /sandbox/repo
git add requirements.txt mcutil/api/db.py tests/test_db.py
git commit -m "feat: add async SQLAlchemy database infrastructure

Accounts need persistence, and the app had no database layer at all.
Keeping engine and session lifecycle in its own module means the
account model does not have to own connection concerns."
```

---

### Task 2: Account model and create_account function

**Files:**
- Create: `mcutil/api/account.py`
- Test: `tests/test_account.py`

**Interfaces:**
- Consumes: `db.Base`, `db.async_session` from Task 1
- Produces:
  - `account.Sex` — `class Sex(str, enum.Enum)` with members `male`, `female`, `other`
  - `account.Account` — ORM model, `__tablename__ = "accounts"`, columns `id: int`, `name: str`, `sex: Sex`, `balance: float`
  - `async def account.create_account(session: AsyncSession, name: str, sex: Sex, balance: float) -> Account` — adds and flushes, returning the instance with `id` populated. Does NOT commit; the caller commits.

- [ ] **Step 1: Write the failing test**

Create `tests/test_account.py`. The `StaticPool` and `check_same_thread` arguments are required — without them, each connection to `sqlite+aiosqlite://` gets its own separate empty database and the inserted row is invisible.

```python
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
```

- [ ] **Step 2: Enable asyncio test support**

These tests use `@pytest.mark.asyncio`, which needs the `pytest-asyncio` plugin. Add it to `requirements-dev.txt` so the file reads:

```
-r requirements.txt
pytest>=8.0
pytest-asyncio>=0.23
```

Then install and register the marker by creating `pytest.ini` at the repository root:

```ini
[pytest]
asyncio_mode = auto
```

Run: `cd /sandbox/repo && pip install -r requirements-dev.txt`

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_account.py -v`
Expected: FAIL at import with `ModuleNotFoundError: No module named 'mcutil.api.account'`.

- [ ] **Step 4: Write the implementation**

Create `mcutil/api/account.py`:

```python
import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Sex(str, enum.Enum):
    """Account owner's sex."""

    male = "male"
    female = "female"
    other = "other"


class Account(Base):
    """An account owner and their current equity."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    sex: Mapped[Sex] = mapped_column(SAEnum(Sex), nullable=False)
    balance: Mapped[float] = mapped_column(Float, nullable=False)


async def create_account(
    session: AsyncSession, name: str, sex: Sex, balance: float
) -> Account:
    """Insert a new account and return it with its generated ``id``.

    Flushes so the primary key is populated, but leaves committing to the
    caller.
    """
    account = Account(name=name, sex=sex, balance=balance)
    session.add(account)
    await session.flush()
    return account
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_account.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 6: Confirm nothing regressed**

Run: `cd /sandbox/repo && python3 -m pytest -q`
Expected: 19 passed.

- [ ] **Step 7: Commit**

```bash
cd /sandbox/repo
git add mcutil/api/account.py tests/test_account.py requirements-dev.txt pytest.ini
git commit -m "feat: add Account model and create_account

Sex subclasses str so one enum definition serves the ORM column, the
Pydantic request model, and JSON serialisation. create_account flushes
rather than commits so the caller controls the transaction boundary."
```

---

### Task 3: POST /accounts endpoint

**Files:**
- Modify: `mcutil/api/app.py` (imports on line 7; lifespan on lines 15-19; append models and route at end of file)
- Test: `tests/test_api.py` (append; add fixture)

**Interfaces:**
- Consumes: `db.async_session`, `db.init_db`, `db.close_engine` from Task 1; `account.Sex`, `account.create_account` from Task 2
- Produces: `POST /accounts` returning HTTP 201 with body `{"id": int, "name": str, "sex": str, "balance": float}`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api.py`. Note the `account_client` fixture patches `db.async_session` so tests hit an in-memory database and never touch `accounts.db`; it must be patched before `TestClient` starts, because the lifespan calls `init_db()` on startup.

```python
# ── Account creation endpoint ───────────────────────────────────────────────


@pytest.fixture
def account_client(monkeypatch):
    """Client backed by a throwaway in-memory database."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from mcutil.api import db

    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(db, "engine", test_engine)
    monkeypatch.setattr(
        db, "async_session", async_sessionmaker(test_engine, expire_on_commit=False)
    )
    with TestClient(app) as c:
        yield c


def test_create_account_success(account_client):
    resp = account_client.post(
        "/accounts",
        json={"name": "Alice", "sex": "female", "balance": 5000.0},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == 1
    assert body["name"] == "Alice"
    assert body["sex"] == "female"
    assert body["balance"] == 5000.0


def test_create_account_invalid_sex(account_client):
    resp = account_client.post(
        "/accounts",
        json={"name": "Alice", "sex": "unknown", "balance": 5000.0},
    )
    assert resp.status_code == 422


def test_create_account_missing_name(account_client):
    resp = account_client.post(
        "/accounts", json={"sex": "female", "balance": 5000.0}
    )
    assert resp.status_code == 422


def test_create_account_missing_balance(account_client):
    resp = account_client.post(
        "/accounts", json={"name": "Alice", "sex": "female"}
    )
    assert resp.status_code == 422


def test_create_account_non_numeric_balance(account_client):
    resp = account_client.post(
        "/accounts",
        json={"name": "Alice", "sex": "female", "balance": "not-a-number"},
    )
    assert resp.status_code == 422


def test_create_account_accepts_sex_other(account_client):
    resp = account_client.post(
        "/accounts", json={"name": "Carol", "sex": "other", "balance": 0.0}
    )
    assert resp.status_code == 201
    assert resp.json()["sex"] == "other"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_api.py -k account -v`
Expected: FAIL — all six return 404, because the route does not exist yet.

- [ ] **Step 3: Wire the new modules into the imports**

In `mcutil/api/app.py`, change line 7 from:

```python
from . import binance, vnstock
```

to:

```python
from . import account, binance, db, vnstock
```

- [ ] **Step 4: Wire the database into the lifespan**

In `mcutil/api/app.py`, replace the existing lifespan (lines 15-19):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await binance.close_client()
    await vnstock.close_client()
```

with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield
    await binance.close_client()
    await vnstock.close_client()
    await db.close_engine()
```

- [ ] **Step 5: Add the request and response models**

Append to the end of `mcutil/api/app.py`:

```python
class AccountCreate(BaseModel):
    name: str
    sex: account.Sex
    balance: float


class AccountResponse(BaseModel):
    id: int
    name: str
    sex: account.Sex
    balance: float
```

- [ ] **Step 6: Add the endpoint**

Append to the end of `mcutil/api/app.py`:

```python
@app.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(payload: AccountCreate):
    """Create a new account and return it with its generated ``id``."""
    async with db.async_session() as session:
        created = await account.create_account(
            session, payload.name, payload.sex, payload.balance
        )
        await session.commit()
    return AccountResponse(
        id=created.id,
        name=created.name,
        sex=created.sex,
        balance=created.balance,
    )
```

- [ ] **Step 7: Run the account tests to verify they pass**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_api.py -k account -v`
Expected: PASS — 6 passed.

- [ ] **Step 8: Run the whole suite**

Run: `cd /sandbox/repo && python3 -m pytest -q`
Expected: 25 passed.

- [ ] **Step 9: Confirm no stray database file was created**

Run: `cd /sandbox/repo && git status --short`
Expected: only the intended source files are listed. If `accounts.db` appears, the fixture failed to patch the engine — fix that before committing, and do not commit the file.

- [ ] **Step 10: Commit**

```bash
cd /sandbox/repo
git add mcutil/api/app.py tests/test_api.py
git commit -m "feat: add POST /accounts endpoint

Creating the account is the one operation issue #18 asks for. Pydantic
reuses the Sex enum, so an unknown value is rejected as a 422 before any
database work happens."
```

---

### Task 4: Ignore the database file and document the endpoint

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Consumes: the `POST /accounts` endpoint from Task 3
- Produces: nothing consumed by later tasks

- [ ] **Step 1: Check whether the database file is already ignored**

Run: `cd /sandbox/repo && grep -n "accounts.db\|\*.db" .gitignore || echo "NOT IGNORED"`

If it prints `NOT IGNORED`, append this to `.gitignore`:

```
# Local SQLite database
*.db
```

If a matching rule already exists, leave `.gitignore` unchanged and move on.

- [ ] **Step 2: Document the endpoint**

In `README.md`, in the `### Usage` section, append after the existing `curl` examples:

````markdown
```bash
# Create an account
curl -X POST http://127.0.0.1:8000/accounts \
  -H 'Content-Type: application/json' \
  -d '{"name": "Alice", "sex": "female", "balance": 5000.0}'
# {"id":1,"name":"Alice","sex":"female","balance":5000.0}
```

`sex` must be one of `male`, `female`, or `other`. Accounts are stored in a
local SQLite database (`accounts.db`), created automatically on first run.
````

- [ ] **Step 3: Verify the documented example actually works**

Start the server:

```bash
cd /sandbox/repo && uvicorn mcutil.api.app:app --port 8000 &
sleep 3
```

Run the documented command exactly as written in the README:

```bash
curl -s -X POST http://127.0.0.1:8000/accounts \
  -H 'Content-Type: application/json' \
  -d '{"name": "Alice", "sex": "female", "balance": 5000.0}'
```

Expected output: `{"id":1,"name":"Alice","sex":"female","balance":5000.0}`

Then stop the server and remove the database file it created:

```bash
kill %1
cd /sandbox/repo && rm -f accounts.db
```

- [ ] **Step 4: Run the whole suite one final time**

Run: `cd /sandbox/repo && python3 -m pytest -q`
Expected: 25 passed.

- [ ] **Step 5: Confirm the working tree holds only intended changes**

Run: `cd /sandbox/repo && git status --short`
Expected: `.gitignore` and `README.md` modified, and no `accounts.db`.

- [ ] **Step 6: Commit**

```bash
cd /sandbox/repo
git add .gitignore README.md
git commit -m "docs: document the create account endpoint

Also ignores the local SQLite file so a development run does not leave
an untracked database in the tree."
```

---

## Verification

After all four tasks, the following must all hold:

- [ ] `cd /sandbox/repo && python3 -m pytest -q` reports **25 passed**
- [ ] `cd /sandbox/repo && git status --short` is empty
- [ ] `accounts.db` is not tracked: `git ls-files accounts.db` prints nothing
- [ ] The README example returns HTTP 201 against a freshly started server
