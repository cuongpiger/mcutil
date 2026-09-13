# GET Account by ID API Implementation Plan

> **For agentic workers:** Execute this plan one task at a time with executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `GET /accounts/{account_id}` endpoint that returns a single account by its primary key, or 404 when no such account exists.

**Architecture:** A `get_account()` data-layer function joins the existing `create_account()` in `mcutil/api/account.py`, wrapping SQLAlchemy's `session.get()` primary-key lookup. The endpoint is added to the existing `mcutil/api/app.py` alongside `POST /accounts`, reusing the `AccountResponse` model that is already defined there. No new files, no new dependencies, no new response models.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 async ORM, aiosqlite, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-get-account-by-id-api-design.md`

## Global Constraints

- No new dependencies. `requirements.txt` and `requirements-dev.txt` are not modified by this plan.
- The path parameter is named `account_id` and typed `int`. Do NOT add a regex `Path(...)` constraint — a bare `int` annotation already makes FastAPI return 422 for non-integer input.
- The 404 detail string is exactly `"Account not found."` (capital A, trailing period).
- Reuse the existing `AccountResponse` model in `mcutil/api/app.py`. Do NOT define a new response model.
- `get_account()` returns `Account | None`. It MUST NOT raise on a missing row, and MUST NOT call `commit()` — HTTP-level concerns stay in `app.py`.
- Scope is read-by-id only. Do NOT add list, update, or delete endpoints, pagination, filtering, authentication, or authorization.
- Follow the existing file style in this repo: standard-library imports first, then third-party, then relative `from . import ...`; docstrings on public async functions.
- Run tests with `python3 -m pytest`.

## Environment Setup

The sandbox may not have the project dependencies installed. Before Task 1, run:

```bash
cd /sandbox/repo && pip install -r requirements-dev.txt
```

Verify the pre-existing suite is green before changing anything — it should report **25 passed**:

```bash
cd /sandbox/repo && python3 -m pytest -q
```

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `mcutil/api/account.py` | Modify | Add `get_account()` beside the existing `create_account()` |
| `mcutil/api/app.py` | Modify | Add the `GET /accounts/{account_id}` route |
| `tests/test_account.py` | Modify | Unit tests for `get_account()` |
| `tests/test_api.py` | Modify | Endpoint tests for `GET /accounts/{account_id}` |
| `README.md` | Modify | Document the new endpoint |

---

### Task 1: `get_account()` data-layer function

**Files:**
- Modify: `mcutil/api/account.py`
- Test: `tests/test_account.py`

**Interfaces:**
- Consumes: `Account` model and `Sex` enum, both already defined in `mcutil/api/account.py`. The `session` fixture already defined at the top of `tests/test_account.py` provides an `AsyncSession` backed by in-memory SQLite.
- Produces: `async def get_account(session: AsyncSession, account_id: int) -> Account | None` — returns the matching `Account`, or `None` when no row has that id. Task 2 imports this as `account.get_account`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_account.py`:

```python
@pytest.mark.asyncio
async def test_get_account_returns_the_account(session):
    created = await create_account(session, "Alice", Sex.female, 5000.0)
    await session.commit()

    fetched = await get_account(session, created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Alice"
    assert fetched.sex is Sex.female
    assert fetched.balance == 5000.0


@pytest.mark.asyncio
async def test_get_account_returns_none_for_missing_id(session):
    assert await get_account(session, 999) is None


@pytest.mark.asyncio
async def test_get_account_returns_the_requested_account(session):
    first = await create_account(session, "Alice", Sex.female, 1.0)
    second = await create_account(session, "Bob", Sex.male, 2.0)
    await session.commit()

    fetched = await get_account(session, second.id)

    assert fetched.name == "Bob"
    assert fetched.id != first.id
```

Update the import at the top of the same file so `get_account` is in scope. Change:

```python
from mcutil.api.account import Account, Sex, create_account
```

to:

```python
from mcutil.api.account import Account, Sex, create_account, get_account
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_account.py -q`

Expected: collection fails with `ImportError: cannot import name 'get_account' from 'mcutil.api.account'`. That import error is the expected failure — the function does not exist yet.

- [ ] **Step 3: Write the implementation**

Append to `mcutil/api/account.py`, after `create_account`:

```python
async def get_account(
    session: AsyncSession, account_id: int
) -> Account | None:
    """Return the account with *account_id*, or ``None`` if there is none.

    A plain primary-key lookup; the caller decides what a missing row means.
    """
    return await session.get(Account, account_id)
```

No import changes are needed — `AsyncSession` and `Account` are already in scope in this file.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_account.py -q`

Expected: PASS. The file had 5 tests before; it should now report **8 passed**.

- [ ] **Step 5: Run the whole suite to check for regressions**

Run: `cd /sandbox/repo && python3 -m pytest -q`

Expected: **28 passed** (25 pre-existing + 3 new).

- [ ] **Step 6: Commit and push**

```bash
cd /sandbox/repo
git add mcutil/api/account.py tests/test_account.py
git commit -m "feat: add get_account data-layer lookup

Wraps session.get so a missing row is a None return rather than an
exception, leaving the caller to decide what absence means."
git push
```

---

### Task 2: `GET /accounts/{account_id}` endpoint

**Files:**
- Modify: `mcutil/api/app.py`
- Modify: `README.md`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `account.get_account(session, account_id) -> Account | None` from Task 1. Also the existing `AccountResponse` Pydantic model, the `db.async_session` factory, and `HTTPException` — all already present in `mcutil/api/app.py`.
- Produces: `GET /accounts/{account_id}` returning 200 with an `AccountResponse` body, 404 with `{"detail": "Account not found."}` when absent, and 422 for a non-integer id.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api.py`. These use the `account_client` fixture already defined in that file, which backs the app with a throwaway in-memory database:

```python
# ── Account retrieval endpoint ──────────────────────────────────────────────


def test_get_account_success(account_client):
    created = account_client.post(
        "/accounts",
        json={"name": "Alice", "sex": "female", "balance": 5000.0},
    ).json()

    resp = account_client.get(f"/accounts/{created['id']}")

    assert resp.status_code == 200
    assert resp.json() == {
        "id": created["id"],
        "name": "Alice",
        "sex": "female",
        "balance": 5000.0,
    }


def test_get_account_not_found(account_client):
    resp = account_client.get("/accounts/999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Account not found."


def test_get_account_non_integer_id(account_client):
    resp = account_client.get("/accounts/abc")
    assert resp.status_code == 422


def test_get_account_returns_the_requested_account(account_client):
    account_client.post(
        "/accounts", json={"name": "Alice", "sex": "female", "balance": 1.0}
    )
    bob = account_client.post(
        "/accounts", json={"name": "Bob", "sex": "male", "balance": 2.0}
    ).json()

    resp = account_client.get(f"/accounts/{bob['id']}")

    assert resp.status_code == 200
    assert resp.json()["name"] == "Bob"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_api.py -q`

Expected: FAIL. `test_get_account_success` and `test_get_account_returns_the_requested_account` get 404 (no route matches), and `test_get_account_non_integer_id` gets 404 rather than 422. `test_get_account_not_found` may appear to pass by accident — FastAPI's own 404 for an unmatched route has detail `"Not Found"`, so the assertion on the detail string still fails.

- [ ] **Step 3: Write the implementation**

Append to `mcutil/api/app.py`, after the existing `create_account` endpoint:

```python
@app.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(account_id: int):
    """Retrieve a single account by its ``id``."""
    async with db.async_session() as session:
        found = await account.get_account(session, account_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return AccountResponse(
        id=found.id,
        name=found.name,
        sex=found.sex,
        balance=found.balance,
    )
```

No import changes are needed — `HTTPException`, `account`, and `db` are all already imported at the top of this file.

Note the local name `found` rather than `account`: the module `account` is imported at module level, and a local variable of the same name would shadow it and break the `account.get_account` call.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /sandbox/repo && python3 -m pytest tests/test_api.py -q`

Expected: PASS. The file had 20 tests before; it should now report **24 passed**.

- [ ] **Step 5: Document the endpoint in the README**

In `README.md`, find the "Account management" section. After the existing
`POST /accounts` example block, add:

````markdown
Fetch an existing account by its ID:

```bash
curl http://127.0.0.1:8000/accounts/1
# {"id":1,"name":"Alice","sex":"female","balance":5000.0}

# An unknown ID returns 404
curl http://127.0.0.1:8000/accounts/999
# {"detail":"Account not found."}
```
````

- [ ] **Step 6: Run the whole suite to confirm everything is green**

Run: `cd /sandbox/repo && python3 -m pytest -q`

Expected: **32 passed** (25 pre-existing + 3 from Task 1 + 4 from Task 2).

- [ ] **Step 7: Commit and push**

```bash
cd /sandbox/repo
git add mcutil/api/app.py tests/test_api.py README.md
git commit -m "feat: add GET /accounts/{account_id} endpoint

Returns the account as JSON, or 404 when no account has that id. The
int-typed path parameter makes FastAPI reject non-numeric ids with 422
before the handler runs."
git push
```
