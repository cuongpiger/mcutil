# Design Spec: Deposit Money to Account API

**Ticket:** [cuongpiger/mcutil#24](https://github.com/cuongpiger/mcutil/issues/24)  
**Date:** 2026-09-14  
**Status:** Draft

## Summary

Add a FastAPI endpoint that allows depositing money into an existing account. The deposit validates the amount (must be positive), updates the account balance, and records a transaction row for auditing. No UI work is required.

## Requirements (from ticket)

- Provide an API endpoint/flow for depositing money to an account.
- Validate deposit amount (positive number).
- Update the account balance after a successful deposit.
- Record the deposit transaction/history for auditing.
- Return clear success and error responses/messages.
- Relevant API tests are added for success and failure cases.
- No UI work is required.

## Approach

**New `transaction.py` module** — A new `mcutil/api/transaction.py` file holds the `Transaction` model, `TransactionType` enum, and a `deposit()` function. This mirrors the existing convention where `account.py` owns the `Account` model and its data-access functions. Route handlers and Pydantic models live in `app.py` as before.

### Why not the alternatives

- **Extending `account.py`** would make that module responsible for two concerns (account management and transaction auditing). As more operations are added, it grows unfocused.
- **A service layer** (`service.py` coordinating between `account.py` and `transaction.py`) introduces a pattern the codebase doesn't have and doesn't need at this size.

## Data Model

### `TransactionType` enum

```python
class TransactionType(str, enum.Enum):
    deposit = "deposit"
```

Extensible — future values like `withdrawal` and `transfer` can be added without schema changes (SQLite enum stored as string).

### `Transaction` model

```python
class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    type: Mapped[TransactionType] = mapped_column(SAEnum(TransactionType), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
```

- `account_id` — foreign key to `accounts.id`, ensures referential integrity.
- `amount` — the deposited amount, stored as-is for the audit record.
- `type` — enum starting with `deposit` only; extensible.
- `created_at` — UTC timestamp for the audit trail. `datetime.utcnow` is used as the SQLAlchemy column default (callable, evaluated at insert time).

### `deposit()` function

```python
async def deposit(session: AsyncSession, account_id: int, amount: float) -> Transaction | None:
    account = await session.get(Account, account_id)
    if account is None:
        return None
    account.balance += amount
    tx = Transaction(account_id=account_id, amount=amount, type=TransactionType.deposit)
    session.add(tx)
    await session.flush()
    return tx
```

- Returns `None` when the account doesn't exist — the caller decides the HTTP response.
- Updates `account.balance` in place; SQLAlchemy tracks the dirty attribute.
- Flushes so `tx.id` and `tx.created_at` are populated before returning.
- Leaves committing to the caller — same convention as `create_account`.

## API Endpoint

### Route

```
POST /accounts/{account_id}/deposits
```

RESTful nested resource path under the account.

### Request body

```python
class DepositRequest(BaseModel):
    amount: float
```

### Response body (201 Created)

```python
class DepositResponse(BaseModel):
    id: int
    account_id: int
    amount: float
    type: str
    created_at: datetime
```

### Route handler

```python
@app.post("/accounts/{account_id}/deposits", response_model=DepositResponse, status_code=201)
async def deposit(account_id: int, payload: DepositRequest):
    if payload.amount <= 0:
        raise HTTPException(status_code=422, detail="Deposit amount must be positive.")
    async with db.async_session() as session:
        tx = await transaction.deposit(session, account_id, payload.amount)
        if tx is None:
            raise HTTPException(status_code=404, detail="Account not found.")
        await session.commit()
    return DepositResponse(
        id=tx.id,
        account_id=tx.account_id,
        amount=tx.amount,
        type=tx.type.value,
        created_at=tx.created_at,
    )
```

## Error Handling

| Error case | Status | Detail |
|---|---|---|
| Amount ≤ 0 | 422 | `"Deposit amount must be positive."` |
| Amount non-numeric / missing field | 422 | Pydantic default validation error |
| Account not found | 404 | `"Account not found."` |
| Non-integer `account_id` in path | 422 | FastAPI path validation |

## Testing

### Unit tests — `tests/test_transaction.py`

Uses the same in-memory SQLite fixture pattern as `tests/test_account.py`:

- `test_deposit_updates_account_balance` — balance increases by deposited amount.
- `test_deposit_creates_transaction_record` — a `Transaction` row exists with correct fields.
- `test_deposit_returns_none_for_missing_account` — returns `None` for a non-existent account ID.
- `test_deposit_recorded_type_is_deposit` — the transaction type is `TransactionType.deposit`.
- `test_deposit_recorded_amount_matches_input` — the stored amount equals the input.

### API tests — in `tests/test_api.py`

Uses the existing `account_client` fixture (in-memory DB patched into `db.engine` / `db.async_session`):

- `test_deposit_success` — 201, correct response body fields, account balance reflects the deposit.
- `test_deposit_invalid_amount_zero` — 422, detail `"Deposit amount must be positive."`.
- `test_deposit_invalid_amount_negative` — 422, same detail.
- `test_deposit_missing_amount_field` — 422, Pydantic validation error.
- `test_deposit_non_numeric_amount` — 422, Pydantic validation error.
- `test_deposit_account_not_found` — 404, detail `"Account not found."`.
- `test_deposit_non_integer_account_id` — 422, path validation.

## Documentation

Update `README.md` with a `### Deposits` section under `### Account management`, showing a curl example and the expected JSON response — matching the style of the existing account creation and retrieval docs.

## Files Changed

| File | Change |
|---|---|
| `mcutil/api/transaction.py` | **New** — `Transaction` model, `TransactionType` enum, `deposit()` function |
| `mcutil/api/app.py` | Add `DepositRequest`, `DepositResponse` models and `POST /accounts/{account_id}/deposits` route |
| `tests/test_transaction.py` | **New** — unit tests for `deposit()` |
| `tests/test_api.py` | Add API tests for the deposit endpoint |
| `README.md` | Add `### Deposits` section |

## Out of Scope

- Withdrawals, transfers, or any other transaction types (the `TransactionType` enum is extensible but only `deposit` is implemented).
- UI work.
- Authentication or authorization.
- Pagination or listing of transactions.
- Currency/format validation beyond "positive number."
