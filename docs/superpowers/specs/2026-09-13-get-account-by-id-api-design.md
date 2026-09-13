# Spec: GET /accounts/{id} — Retrieve Account by ID

**Ticket:** https://github.com/cuongpiger/mcutil/issues/21
**Date:** 2026-09-13

## Goal

Add a `GET /accounts/{id}` endpoint that retrieves a single account by its
primary key. Returns the account as JSON or 404 if no account exists with
that ID.

## Background

The codebase already has:

- `Account` ORM model (`mcutil/api/account.py`) with `id`, `name`, `sex`,
  `balance` columns.
- `create_account(session, name, sex, balance)` data-layer function.
- `POST /accounts` endpoint and `AccountResponse` Pydantic model in
  `mcutil/api/app.py`.
- `account_client` test fixture (in-memory SQLite via `StaticPool`) in
  `tests/test_api.py`.
- Unit tests in `tests/test_account.py` using an async session fixture.

This feature follows the same patterns.

## Design

### Data layer — `mcutil/api/account.py`

Add a new async function:

```python
async def get_account(session: AsyncSession, account_id: int) -> Account | None:
    """Return the account with *account_id*, or ``None`` if not found."""
    return await session.get(Account, account_id)
```

`session.get` is the simplest async primary-key lookup in SQLAlchemy 2.x.
It returns `None` when the row is absent — no exception to catch.

### API layer — `mcutil/api/app.py`

Add a new route:

```python
@app.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(account_id: int):
    """Retrieve a single account by its ID."""
    async with db.async_session() as session:
        acct = await account.get_account(session, account_id)
    if acct is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return AccountResponse(
        id=acct.id, name=acct.name, sex=acct.sex, balance=acct.balance
    )
```

Key decisions:

- **Path param is `account_id: int`.** FastAPI rejects non-integer values
  with 422 before the handler runs — no manual validation needed.
- **404 on not found.** Standard REST convention. The detail string is
  `"Account not found."`.
- **Reuses `AccountResponse`.** No new response model.
- **No new imports** beyond `HTTPException` which is already imported.

### Tests — `tests/test_api.py`

Add three tests using the existing `account_client` fixture:

1. `test_get_account_success` — POST an account, GET `/accounts/1`, assert
   200 and the full body matches.
2. `test_get_account_not_found` — GET `/accounts/999`, assert 404 and
   `detail == "Account not found."`.
3. `test_get_account_non_integer_id` — GET `/accounts/abc`, assert 422.

### Tests — `tests/test_account.py`

Add one unit test:

1. `test_get_account_returns_none_for_missing_id` — call `get_account`
   with a non-existent ID on a fresh session, assert the result is `None`.

## Out of scope

- Listing all accounts (`GET /accounts`).
- Filtering, pagination, or query parameters.
- Updating or deleting accounts.
- Authentication or authorization.
