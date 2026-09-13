# Spec: Account model and create-account API

## Context

The `mcutil` project is a FastAPI service that currently provides stateless
price-fetching endpoints (`/price/{symbol}` from Binance, `/vprice/{symbol}`
from Vietnamese stocks via TCBS). It has no persistence layer — no database,
no ORM, no storage.

Issue #11 asks for:

1. A new `Account` model with fields: `name` (owner name), `sex`
   (male/female/other), `balance` (current equity of the user).
2. A new API endpoint to create accounts.

This spec introduces SQLite-backed persistence using async SQLAlchemy, adds
the `Account` ORM model, and implements a `POST /accounts` endpoint.

## Decisions

- **Database:** SQLite (file-based, no external server required)
- **ORM:** SQLAlchemy 2.0 async (`sqlalchemy[asyncio]` + `aiosqlite`)
- **Rationale:** SQLite is lightweight, persists across restarts, and requires
  no external database server. Async SQLAlchemy is used to stay consistent with
  the project's fully-async architecture (`httpx.AsyncClient`, `async def`
  endpoints).

## New files

| File | Responsibility |
|------|---------------|
| `mcutil/api/database.py` | Async SQLAlchemy engine, session factory, `Base`, `init_db()` / `close_db()` lifecycle functions. |
| `mcutil/api/models.py` | SQLAlchemy ORM model `Account`. |
| `mcutil/api/schemas.py` | Pydantic request (`AccountCreate`) and response (`AccountResponse`) models. |
| `mcutil/api/accounts.py` | Async CRUD function `create_account()` and custom exception `DatabaseError`. |

### Modified files

| File | Changes |
|------|---------|
| `mcutil/api/app.py` | Import `database` and `accounts` modules. Register `POST /accounts` route. Map exceptions to HTTP errors. Call `init_db()` / `close_db()` in lifespan. |
| `requirements.txt` | Add `sqlalchemy[asyncio]>=2.0` and `aiosqlite>=0.20`. |
| `tests/test_api.py` | Add tests for `POST /accounts`. |

### Module dependency flow

```
app.py
 ├── accounts.py   (business logic + exceptions)
 │    ├── models.py   (SQLAlchemy ORM)
 │    └── schemas.py  (Pydantic request/response)
 └── database.py   (engine, session, Base)
```

Each module has one responsibility and can be tested independently. The
endpoint in `app.py` calls into `accounts.py`, which uses `database.py` for
sessions and `models.py` / `schemas.py` for ORM and Pydantic objects
respectively.

## Data Model

### `Account` ORM model (`models.py`)

| Column | SQLAlchemy Type | Python Type | Constraints |
|--------|----------------|-------------|-------------|
| `id` | `mapped_column(Integer, primary_key=True)` | `int` | PK, autoincrement |
| `name` | `mapped_column(String(100))` | `str` | NOT NULL |
| `sex` | `mapped_column(String(10))` | `str` | NOT NULL |
| `balance` | `mapped_column(Numeric(15, 2))` | `Decimal` | NOT NULL, default 0 |
| `created_at` | `mapped_column(DateTime(timezone=True), server_default=func.now())` | `datetime` | NOT NULL |

The `sex` field accepts `"male"`, `"female"`, or `"other"`. This is enforced at
the Pydantic schema layer (via `Literal`) rather than at the database level,
consistent with the project's convention of validating input in the API layer.

## API Endpoint

### `POST /accounts`

Creates a new account record in the database and returns it.

#### Request body (`AccountCreate`)

```json
{
  "name": "Alice",
  "sex": "female",
  "balance": 1000.00
}
```

Validation rules:

| Field | Type | Constraints |
|-------|------|-------------|
| `name` | `str` | `min_length=1`, `max_length=100`, required |
| `sex` | `Literal["male", "female", "other"]` | required |
| `balance` | `Decimal` | `ge=0`, default `0` |

#### Response (`AccountResponse`, HTTP 201)

```json
{
  "id": 1,
  "name": "Alice",
  "sex": "female",
  "balance": "1000.00",
  "created_at": "2026-09-13T12:00:00Z"
}
```

`balance` is returned as a string to preserve decimal precision (Decimal JSON
serialization). `created_at` is an ISO-8601 timestamp string.

#### Error mapping

| Condition | HTTP Status | Detail |
|-----------|-------------|--------|
| Malformed request body (invalid sex, missing name, negative balance) | 422 | Automatic (Pydantic / FastAPI validation) |
| Database unreachable or write fails (`DatabaseError`) | 502 | `"Failed to create account."` |

## Database Connection

### `database.py`

- **`DATABASE_URL`:** Read from the `DATABASE_URL` environment variable. Default
  to `sqlite+aiosqlite:///./mcutil.db` for local development.
- **`async_engine`:** `create_async_engine(DATABASE_URL, echo=False)`.
- **`async_session`:** `async_sessionmaker(async_engine, expire_on_commit=False)`.
- **`class Base(DeclarativeBase): pass`** — shared declarative base. All ORM
  models inherit from this.
- **`async def get_session() -> AsyncSession`** — async generator that yields a
  session. Registered as a FastAPI `Depends` on the endpoint.
- **`async def init_db()`** — runs
  `async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)`.
  Called during lifespan startup.
- **`async def close_db()`** — calls `await engine.dispose()`. Called during
  lifespan teardown.

### Lifespan update in `app.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()
    await binance.close_client()
    await vnstock.close_client()
```

The `init_db()` call creates the `accounts` table if it does not exist. This is
idempotent — running it when the table already exists is a no-op.

## Testing Strategy

Follow the existing test patterns: `TestClient` + `monkeypatch`, no real
network or database calls.

### Approach

Patch `accounts.create_account` so tests do not require a live SQLite instance.
This mirrors how existing tests patch `binance.get_price` and
`vnstock.get_price` — the service-layer function is mocked, and the endpoint's
error mapping is tested through the HTTP layer.

### Test cases

| Test | What it verifies |
|------|-----------------|
| `test_create_account_success` | Valid body → 201, response includes `id`, `name`, `sex`, `balance`, `created_at`. |
| `test_create_account_invalid_sex` | `sex: "unknown"` → 422. |
| `test_create_account_missing_name` | Body without `name` → 422. |
| `test_create_account_negative_balance` | `balance: -100` → 422. |
| `test_create_account_default_balance` | Body without `balance` → 201, balance is `"0.00"`. |
| `test_create_account_db_error` | Patch `create_account` to raise `DatabaseError` → 502. |

## Dependencies

### `requirements.txt` (additions)

```
sqlalchemy[asyncio]>=2.0
aiosqlite>=0.20
```

### `requirements-dev.txt`

No changes — `pytest` is already present.

## Out of Scope

- Read, update, or delete account endpoints (GET/PATCH/DELETE).
- Alembic migrations.
- Authentication / authorization.
- Account listing or pagination.
- Business logic beyond creating a record.
