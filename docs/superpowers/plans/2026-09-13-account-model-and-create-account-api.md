# Account Model and Create-Account API Implementation Plan

> **For agentic workers:** Execute this plan one task at a time with executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `Account` model (name, sex, balance) persisted in SQLite and expose a `POST /accounts` endpoint that creates accounts.

**Architecture:** Two new modules follow the existing `binance.py`/`vnstock.py` → `app.py` pattern. `mcutil/api/database.py` owns the `aiosqlite` connection lifecycle; `mcutil/api/accounts.py` owns the Pydantic models and the insert. `mcutil/api/app.py` gains a `POST /accounts` route and extends its existing `lifespan` to open and close the database.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, `aiosqlite`, pytest, `pytest-asyncio`, `fastapi.testclient.TestClient`.

## Global Constraints

- New dependency pins: `aiosqlite>=0.20` in `requirements.txt`, `pytest-asyncio>=0.23` in `requirements-dev.txt` — exact strings.
- SQLite database file path: `data.db` in the process working directory.
- Allowed `sex` values, exact lowercase strings: `male`, `female`, `other`.
- `POST /accounts` returns HTTP **201** on success. Validation failures return **422** (FastAPI default; do not write custom handlers).
- Negative balances are **accepted** — do not add a validator rejecting them.
- Read, update, and delete endpoints are out of scope. Do not add them.
- Follow existing codebase style: module-level `async def` data-access functions, module-level private connection global, no ORM, no migrations framework.
- Tests must not require network access.
- Every async test fixture that opens the database must also close it in the same event loop — use `async def` fixtures, never `asyncio.run()` inside a sync fixture.

---

### Task 1: Database connection module

**Files:**
- Create: `mcutil/api/database.py`
- Create: `pytest.ini`
- Modify: `requirements.txt`, `requirements-dev.txt`
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `DB_PATH: str` — module-level constant, value `"data.db"`.
  - `async def init_db() -> None` — opens the shared connection if needed and creates the `accounts` table.
  - `async def get_db() -> aiosqlite.Connection` — returns the shared open connection, opening it if needed.
  - `async def close_db() -> None` — closes the shared connection and resets the module global to `None`.

- [ ] **Step 1: Install dependencies**

The sandbox has neither `pytest` nor `aiosqlite` installed. Install everything now so later steps can run.

Run:
```bash
cd /sandbox/repo && pip install -r requirements.txt -r requirements-dev.txt aiosqlite pytest-asyncio
```

- [ ] **Step 2: Record the new dependencies**

Set `requirements.txt` to exactly:

```
fastapi>=0.110
uvicorn[standard]>=0.29
httpx>=0.27
aiosqlite>=0.20
```

Set `requirements-dev.txt` to exactly:

```
-r requirements.txt
pytest>=8.0
pytest-asyncio>=0.23
```

- [ ] **Step 3: Enable pytest-asyncio auto mode**

Create `pytest.ini` at the repository root with this exact content:

```ini
[pytest]
asyncio_mode = auto
```

Auto mode means `async def` tests and fixtures run without needing an explicit `@pytest.mark.asyncio` decorator on each one.

- [ ] **Step 4: Write the failing test**

Create `tests/test_database.py` with this exact content:

```python
import pytest

from mcutil.api import database


@pytest.fixture(autouse=True)
async def clean_db(tmp_path, monkeypatch):
    """Point the module at a throwaway DB file and close it afterwards."""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    yield
    await database.close_db()


async def test_init_db_creates_accounts_table():
    await database.init_db()
    conn = await database.get_db()
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'"
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "accounts"


async def test_init_db_is_idempotent():
    await database.init_db()
    await database.init_db()
    conn = await database.get_db()
    cursor = await conn.execute("SELECT COUNT(*) FROM accounts")
    row = await cursor.fetchone()
    assert row[0] == 0


async def test_get_db_returns_same_connection():
    await database.init_db()
    first = await database.get_db()
    second = await database.get_db()
    assert first is second


async def test_close_db_allows_reopen():
    await database.init_db()
    await database.close_db()
    await database.init_db()
    conn = await database.get_db()
    cursor = await conn.execute("SELECT COUNT(*) FROM accounts")
    row = await cursor.fetchone()
    assert row[0] == 0
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_database.py -v`
Expected: FAIL — `ImportError: cannot import name 'database' from 'mcutil.api'` (collection error).

- [ ] **Step 6: Write the implementation**

Create `mcutil/api/database.py` with this exact content:

```python
import aiosqlite

DB_PATH = "data.db"

_connection: aiosqlite.Connection | None = None

CREATE_ACCOUNTS_TABLE = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sex TEXT NOT NULL,
    balance REAL NOT NULL
)
"""


async def get_db() -> aiosqlite.Connection:
    """Return the shared database connection, opening it if necessary."""
    global _connection
    if _connection is None:
        _connection = await aiosqlite.connect(DB_PATH)
    return _connection


async def init_db() -> None:
    """Create the ``accounts`` table if it does not already exist."""
    conn = await get_db()
    await conn.execute(CREATE_ACCOUNTS_TABLE)
    await conn.commit()


async def close_db() -> None:
    """Close the shared database connection."""
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_database.py -v`
Expected: PASS — 4 passed.

- [ ] **Step 8: Confirm the existing suite still passes**

Run: `cd /sandbox/repo && python3 -m pytest -v`
Expected: PASS — the 11 pre-existing price tests plus the 4 new ones, 15 total.

- [ ] **Step 9: Commit**

```bash
cd /sandbox/repo && git add mcutil/api/database.py tests/test_database.py requirements.txt requirements-dev.txt pytest.ini && git commit -m "feat: add aiosqlite database connection module

Accounts need persistence, which the app has not had until now. This adds
the connection lifecycle in its own module so app.py keeps only routing."
```

---

### Task 2: Account models and create_account data access

**Files:**
- Create: `mcutil/api/accounts.py`
- Test: `tests/test_accounts.py`

**Interfaces:**
- Consumes: `database.get_db()`, `database.init_db()`, `database.close_db()`, `database.DB_PATH` from Task 1.
- Produces:
  - `class Sex(str, Enum)` with members `male = "male"`, `female = "female"`, `other = "other"`.
  - `class AccountCreate(BaseModel)` with fields `name: str`, `sex: Sex`, `balance: float`.
  - `class AccountResponse(BaseModel)` with fields `id: int`, `name: str`, `sex: Sex`, `balance: float`.
  - `async def create_account(account: AccountCreate) -> AccountResponse`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_accounts.py` with this exact content:

```python
import pytest

from mcutil.api import accounts, database


@pytest.fixture(autouse=True)
async def fresh_db(tmp_path, monkeypatch):
    """Give each test its own database file."""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    await database.init_db()
    yield
    await database.close_db()


async def test_create_account_returns_generated_id():
    created = await accounts.create_account(
        accounts.AccountCreate(name="John", sex=accounts.Sex.male, balance=1000.0)
    )
    assert created.id == 1
    assert created.name == "John"
    assert created.sex == accounts.Sex.male
    assert created.balance == 1000.0


async def test_create_account_increments_id():
    first = await accounts.create_account(
        accounts.AccountCreate(name="John", sex=accounts.Sex.male, balance=1.0)
    )
    second = await accounts.create_account(
        accounts.AccountCreate(name="Jane", sex=accounts.Sex.female, balance=2.0)
    )
    assert second.id == first.id + 1


async def test_create_account_persists_row():
    await accounts.create_account(
        accounts.AccountCreate(name="Alice", sex=accounts.Sex.other, balance=42.5)
    )
    conn = await database.get_db()
    cursor = await conn.execute("SELECT name, sex, balance FROM accounts")
    row = await cursor.fetchone()
    assert row == ("Alice", "other", 42.5)


async def test_create_account_accepts_negative_balance():
    created = await accounts.create_account(
        accounts.AccountCreate(name="Bob", sex=accounts.Sex.male, balance=-50.0)
    )
    assert created.balance == -50.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_accounts.py -v`
Expected: FAIL — `ImportError: cannot import name 'accounts' from 'mcutil.api'` (collection error).

- [ ] **Step 3: Write the implementation**

Create `mcutil/api/accounts.py` with this exact content:

```python
from enum import Enum

from pydantic import BaseModel

from . import database


class Sex(str, Enum):
    male = "male"
    female = "female"
    other = "other"


class AccountCreate(BaseModel):
    name: str
    sex: Sex
    balance: float


class AccountResponse(BaseModel):
    id: int
    name: str
    sex: Sex
    balance: float


async def create_account(account: AccountCreate) -> AccountResponse:
    """Insert *account* into the database and return it with its new id."""
    conn = await database.get_db()
    cursor = await conn.execute(
        "INSERT INTO accounts (name, sex, balance) VALUES (?, ?, ?)",
        (account.name, account.sex.value, account.balance),
    )
    await conn.commit()
    return AccountResponse(
        id=cursor.lastrowid,
        name=account.name,
        sex=account.sex,
        balance=account.balance,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_accounts.py -v`
Expected: PASS — 4 passed.

- [ ] **Step 5: Confirm the whole suite still passes**

Run: `cd /sandbox/repo && python3 -m pytest -v`
Expected: PASS — 19 tests green.

- [ ] **Step 6: Commit**

```bash
cd /sandbox/repo && git add mcutil/api/accounts.py tests/test_accounts.py && git commit -m "feat: add Account models and create_account data access

Keeps the model and its single insert in one module, mirroring how
binance.py and vnstock.py own their own data access."
```

---

### Task 3: POST /accounts endpoint

**Files:**
- Modify: `mcutil/api/app.py` (import line 8, `lifespan` lines 16-20, new route appended at end)
- Modify: `tests/test_api.py` (import line 4, `client` fixture lines 7-10, new tests appended at end)
- Modify: `README.md`, `.gitignore`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `accounts.AccountCreate`, `accounts.AccountResponse`, `accounts.create_account` from Task 2; `database.init_db`, `database.close_db`, `database.DB_PATH` from Task 1.
- Produces: the `POST /accounts` HTTP route. Nothing later depends on it.

- [ ] **Step 1: Point the existing test client at a throwaway database**

`TestClient(app)` runs the app's `lifespan`, which will call `init_db()` and create `data.db` in the repo root. Redirect that to a temp file so tests leave no artifacts and start empty.

In `tests/test_api.py`, change the import line:

```python
from mcutil.api import binance, vnstock
```

to:

```python
from mcutil.api import binance, database, vnstock
```

and change the `client` fixture from:

```python
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
```

to:

```python
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c
```

The patch must happen before `TestClient` is entered, because entering it triggers `lifespan` startup, which reads `DB_PATH`.

- [ ] **Step 2: Write the failing test**

Append this exact block to the end of `tests/test_api.py`:

```python


# ── Account creation endpoint ───────────────────────────────────────────────


def test_create_account_success(client):
    resp = client.post(
        "/accounts", json={"name": "John", "sex": "male", "balance": 1000.0}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == 1
    assert body["name"] == "John"
    assert body["sex"] == "male"
    assert body["balance"] == 1000.0


def test_create_account_invalid_sex(client):
    resp = client.post(
        "/accounts", json={"name": "Jane", "sex": "unknown", "balance": 500.0}
    )
    assert resp.status_code == 422


def test_create_account_missing_field(client):
    resp = client.post("/accounts", json={"name": "Bob", "sex": "male"})
    assert resp.status_code == 422


def test_create_account_negative_balance(client):
    resp = client.post(
        "/accounts", json={"name": "Alice", "sex": "female", "balance": -50.0}
    )
    assert resp.status_code == 201
    assert resp.json()["balance"] == -50.0
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_api.py -k create_account -v`
Expected: FAIL — all four get 404, because the route does not exist yet.

- [ ] **Step 4: Add the route and wire the lifespan**

In `mcutil/api/app.py`, change the import line:

```python
from . import binance, vnstock
```

to:

```python
from . import accounts, binance, database, vnstock
```

Change `lifespan` from:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await binance.close_client()
    await vnstock.close_client()
```

to:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    yield
    await database.close_db()
    await binance.close_client()
    await vnstock.close_client()
```

Append this route to the end of `mcutil/api/app.py`:

```python


@app.post("/accounts", response_model=accounts.AccountResponse, status_code=201)
async def create_account(account: accounts.AccountCreate):
    """Create a new account.

    ``sex`` must be one of ``male``, ``female``, or ``other``. ``balance`` is
    the owner's current equity and may be negative.
    """
    return await accounts.create_account(account)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_api.py -k create_account -v`
Expected: PASS — 4 passed.

- [ ] **Step 6: Run the full suite**

Run: `cd /sandbox/repo && python3 -m pytest -v`
Expected: PASS — 23 tests green (11 price + 4 database + 4 accounts + 4 API).

- [ ] **Step 7: Ignore the local database file**

Append `data.db` as a new line at the end of `.gitignore`, so a database created by running the app locally is never committed.

- [ ] **Step 8: Document the endpoint**

In `README.md`, change the sentence under `## API service` from:

```markdown
A FastAPI service for fetching current crypto prices from Binance.
```

to:

```markdown
A FastAPI service for fetching current crypto and Vietnamese stock prices, and for managing accounts.
```

Then, inside the existing fenced `bash` block in the `### Usage` section, append these lines after the lowercase-symbol example (do not open a new fence):

```
# Create an account
curl -X POST http://127.0.0.1:8000/accounts \
  -H 'Content-Type: application/json' \
  -d '{"name":"John","sex":"male","balance":1000.0}'
# {"id":1,"name":"John","sex":"male","balance":1000.0}
```

- [ ] **Step 9: Verify the app boots and the endpoint answers**

The test suite uses `TestClient`, which is not quite the same as running under uvicorn. Confirm the real server works.

Run:
```bash
cd /tmp && rm -f data.db && (cd /tmp && python3 -m uvicorn mcutil.api.app:app --port 8123 > /tmp/uvicorn.log 2>&1 &) && sleep 5 && curl -s -X POST http://127.0.0.1:8123/accounts -H 'Content-Type: application/json' -d '{"name":"Smoke","sex":"other","balance":12.5}' ; echo
```

Expected: `{"id":1,"name":"Smoke","sex":"other","balance":12.5}`

If the server fails to start, read `/tmp/uvicorn.log`. Note the server is started from `/tmp` so the smoke-test database lands there, not in the repo — this requires `mcutil` to be importable, which it is because `pip install -r requirements.txt` was run from the repo and the repo root is on the path via the editable working directory. If the import fails, run it with `PYTHONPATH=/sandbox/repo` prefixed.

Stop the server:
```bash
pkill -f 'uvicorn mcutil.api.app:app'
```

- [ ] **Step 10: Confirm no stray files**

Run: `cd /sandbox/repo && git status --porcelain`
Expected: only the files you intend to commit. `data.db` must not appear.

- [ ] **Step 11: Commit**

```bash
cd /sandbox/repo && git add mcutil/api/app.py tests/test_api.py README.md .gitignore && git commit -m "feat: add POST /accounts endpoint

Exposes account creation over HTTP and opens the database alongside the
existing HTTP clients in the app lifespan."
```

---

## Verification

After all three tasks, all of the following must hold. Run them and read the output — do not assume.

1. `cd /sandbox/repo && python3 -m pytest -v` — 23 passed.
2. `cd /sandbox/repo && git status --porcelain` — clean, and `data.db` is not listed.
3. `POST /accounts` with `{"name":"John","sex":"male","balance":1000.0}` returns 201 with an `id` field.
4. `POST /accounts` with `"sex": "unknown"` returns 422.
5. `POST /accounts` with `balance` omitted returns 422.
6. The two pre-existing price endpoints still answer — covered by the 11 pre-existing tests in check 1.
