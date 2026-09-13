# Account Model and Create-Account API

**Ticket:** [cuongpiger/mcutil#14](https://github.com/cuongpiger/mcutil/issues/14)

## Summary

Add an `Account` model (name, sex, balance) persisted in a SQLite database via `aiosqlite`, and expose a `POST /accounts` endpoint to create new accounts. This is the first persistence feature in the app; the design adds a lightweight async database layer that follows the existing module-separation conventions.

## Background

The `mcutil` FastAPI app is currently stateless — it fetches crypto and Vietnamese stock prices from external APIs. Each external service has its own module (`binance.py`, `vnstock.py`) with an async data-access function, and `app.py` defines the routes that call those functions. The app uses an `asynccontextmanager` lifespan for startup/shutdown of shared resources (HTTP clients).

The ticket requests a new `Account` model with three fields and a "create account" API. Accounts will be persisted in SQLite. The scope is limited to the create endpoint — read endpoints (list/get) are explicitly out of scope for this iteration.

## Design

### Architecture

Two new modules plus a modification to the existing app module, mirroring the established pattern:

| File | Role |
|---|---|
| `mcutil/api/database.py` | Manages the `aiosqlite` connection lifecycle: `init_db()` creates the `accounts` table, `get_db()` returns the shared connection, `close_db()` closes it. |
| `mcutil/api/accounts.py` | `Account` Pydantic models (request + response) and the `create_account()` async data-access function. |
| `mcutil/api/app.py` (modified) | New `POST /accounts` route. `lifespan` calls `init_db()` on startup and `close_db()` on shutdown. |

The SQLite database file is `data.db` in the working directory (where `uvicorn mcutil.api.app:app` runs).

### Data Model

**SQLite table `accounts`:**

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `name` | TEXT | NOT NULL |
| `sex` | TEXT | NOT NULL — `'male'`, `'female'`, or `'other'` |
| `balance` | REAL | NOT NULL — current equity (float) |

**Pydantic models (`accounts.py`):**

```python
from enum import Enum
from pydantic import BaseModel

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
```

`AccountCreate` is the request body model; `AccountResponse` is the response model that includes the database-assigned `id`.

### API Endpoint

```
POST /accounts
Content-Type: application/json

Request body:
{
  "name": "John",
  "sex": "male",
  "balance": 1000.0
}

Response 201 Created:
{
  "id": 1,
  "name": "John",
  "sex": "male",
  "balance": 1000.0
}
```

- **201 Created** on success — the created account with its generated `id`.
- **422 Unprocessable Entity** if the body fails Pydantic validation (missing field, invalid `sex` value, non-numeric `balance`). This is automatic FastAPI behavior, no custom error handling needed.
- No 404 or 502 cases — this is a local database operation, not an external API call.

### Database Lifecycle

The existing `lifespan` context manager in `app.py` is extended to manage the database connection alongside the existing HTTP clients:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    yield
    await database.close_db()
    await binance.close_client()
    await vnstock.close_client()
```

`init_db()` executes `CREATE TABLE IF NOT EXISTS accounts (...)`. `close_db()` closes the `aiosqlite` connection. Both are idempotent and safe to call on every startup/shutdown.

### Data Access Function

`accounts.py` exports `create_account(account: AccountCreate) -> AccountResponse` which:

1. Gets the DB connection from `database.get_db()`.
2. Executes `INSERT INTO accounts (name, sex, balance) VALUES (?, ?, ?)` with the account fields.
3. Retrieves the generated `id` via `cursor.lastrowid`.
4. Returns an `AccountResponse` with all four fields.

### Dependencies

Add `aiosqlite>=0.20` to `requirements.txt`.

## Testing

Follow the existing test pattern in `tests/test_api.py`: `TestClient` with the app (lifespan creates the DB), no monkeypatching needed for the local DB. Tests run against a real SQLite file.

An autouse fixture will delete the `data.db` file after each test to ensure isolation. The `TestClient` context manager triggers `lifespan` startup (which calls `init_db()` → `CREATE TABLE IF NOT EXISTS`), so each test starts with a fresh database.

Test cases:

| Test | Input | Expected |
|---|---|---|
| `test_create_account_success` | `{"name": "John", "sex": "male", "balance": 1000.0}` | 201, response has `id`, `name`, `sex`, `balance` matching input |
| `test_create_account_invalid_sex` | `{"name": "Jane", "sex": "unknown", "balance": 500.0}` | 422 |
| `test_create_account_missing_field` | `{"name": "Bob", "sex": "male"}` (no `balance`) | 422 |
| `test_create_account_negative_balance` | `{"name": "Alice", "sex": "female", "balance": -50.0}` | 201 — negative balances are accepted (the ticket does not require rejecting them) |

## Out of Scope

- `GET /accounts` (list all) and `GET /accounts/{id}` (fetch one) endpoints.
- Update or delete operations.
- Migrations framework — the single `CREATE TABLE IF NOT EXISTS` is sufficient.
- Input validation beyond what Pydantic provides (e.g., name length limits, balance range checks).
