# Account Model and Create Account API — Design Spec

**Ticket:** [cuongpiger/mcutil#18](https://github.com/cuongpiger/mcutil/issues/18)
**Date:** 2026-09-13
**Status:** Draft

## Summary

Add an `Account` model with fields `name`, `sex`, and `balance`, backed by SQLite via SQLAlchemy async. Expose a `POST /accounts` endpoint to create accounts. No read, update, or delete endpoints in this scope.

## Background

The existing FastAPI app in `mcutil/api/app.py` is stateless — it proxies Binance and TCBS price APIs. There is no database or persistence layer. This feature introduces the first persisted model.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Storage | SQLite | Persistent, no external dependencies, lightweight |
| ORM | SQLAlchemy async (2.0+) | Industry standard, async support, integrates well with FastAPI |
| API scope | Create only | Ticket asks only for account creation |
| File structure | Separate `db.py` + `account.py` | Clean separation of infrastructure from domain logic, matches existing module pattern |

## Architecture

### New files

#### `mcutil/api/db.py` — Database infrastructure

- `engine` — `create_async_engine("sqlite+aiosqlite:///./accounts.db")`
- `async_session` — `async_sessionmaker` bound to the engine
- `Base` — `DeclarativeBase` for ORM models to inherit
- `init_db()` — runs `Base.metadata.create_all` via the engine (called on app startup)
- `close_engine()` — disposes the engine (called on app shutdown)

#### `mcutil/api/account.py` — Account domain

- `Sex` — SQLAlchemy `Enum` with values `male`, `female`, `other`
- `Account(db.Base)` — ORM model:
  - `id: Mapped[int]` — primary key, autoincrement
  - `name: Mapped[str]` — owner name, required
  - `sex: Mapped[Sex]` — enum, required
  - `balance: Mapped[float]` — current equity, required
- `create_account(session: AsyncSession, name: str, sex: Sex, balance: float) -> Account` — creates and adds an `Account` to the session, flushes, and returns the ORM object with the generated `id`

### Modified files

#### `mcutil/api/app.py`

- Import `db` and `account` modules
- `AccountCreate` — Pydantic `BaseModel` for request body:
  - `name: str`
  - `sex: account.Sex` (Pydantic reuses the enum for validation)
  - `balance: float`
- `AccountResponse` — Pydantic `BaseModel` for response:
  - `id: int`
  - `name: str`
  - `sex: account.Sex`
  - `balance: float`
- `POST /accounts` endpoint:
  - Accepts `AccountCreate` body
  - Opens an `AsyncSession` via `db.async_session()`
  - Calls `account.create_account(session, ...)`
  - Commits the session
  - Returns `AccountResponse` with HTTP 201
- Lifespan updated:
  - Startup: `await db.init_db()`
  - Shutdown: `await db.close_engine()` (alongside existing `binance.close_client()` and `vnstock.close_client()`)

### Dependencies

Add to `requirements.txt`:
- `sqlalchemy[asyncio]>=2.0`
- `aiosqlite>=0.20`

## Data Flow

```
Client POST /accounts {"name": "Alice", "sex": "female", "balance": 5000.00}
  → FastAPI validates body against AccountCreate (422 on invalid input)
  → Open async session from db.async_session()
  → account.create_account(session, "Alice", Sex.female, 5000.00)
  → SQLAlchemy inserts row, flushes to get generated id
  → Commit session
  → Return AccountResponse(id=1, name="Alice", sex="female", balance=5000.0)
  → HTTP 201 Created
```

## Error Handling

| Scenario | Status | Mechanism |
|---|---|---|
| Missing required field | 422 | FastAPI/Pydantic automatic validation |
| Invalid `sex` value (not in enum) | 422 | FastAPI/Pydantic automatic validation |
| Wrong field type (e.g. `balance: "abc"`) | 422 | FastAPI/Pydantic automatic validation |
| Database error | 500 | FastAPI default exception handler |

No custom error handling is needed for create-only scope.

## Testing

New tests in `tests/test_api.py` following existing patterns (TestClient, no real network calls):

- `test_create_account_success` — POST `{"name": "Alice", "sex": "female", "balance": 5000.0}`, assert 201, assert response body has correct fields and a generated `id`
- `test_create_account_invalid_sex` — POST with `sex: "unknown"`, assert 422
- `test_create_account_missing_name` — POST without `name`, assert 422
- `test_create_account_missing_balance` — POST without `balance`, assert 422

Tests use an in-memory SQLite database (`sqlite+aiosqlite://`) by overriding the engine in a fixture, keeping tests fast and isolated.

## Out of Scope

- GET /accounts (list or retrieve by id)
- PUT/PATCH /accounts (update)
- DELETE /accounts
- Authentication / authorization
- Input validation beyond Pydantic defaults (e.g. name length limits, balance range)
