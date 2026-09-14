import pytest
from fastapi.testclient import TestClient

from mcutil.api import binance, vnstock
from mcutil.api.app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_get_price(monkeypatch):
    """Patch binance.get_price so tests make no real network calls."""

    async def fake(symbol):
        return {"symbol": symbol, "price": "77294.00000000"}

    monkeypatch.setattr(binance, "get_price", fake)
    return monkeypatch


def test_get_price_success(client, mock_get_price):
    resp = client.get("/price/BTCUSDT")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "BTCUSDT"
    assert body["price"] == "77294.00000000"


def test_get_price_invalid_symbol(client, monkeypatch):
    async def raise_invalid(symbol):
        raise binance.InvalidSymbolError("Invalid symbol.")

    monkeypatch.setattr(binance, "get_price", raise_invalid)
    resp = client.get("/price/NOPEUSDT")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Invalid symbol."


def test_get_price_binance_unavailable(client, monkeypatch):
    async def raise_unavailable(symbol):
        raise binance.BinanceUnavailableError("timeout")

    monkeypatch.setattr(binance, "get_price", raise_unavailable)
    resp = client.get("/price/BTCUSDT")
    assert resp.status_code == 502
    assert resp.json()["detail"] == "Failed to fetch price from Binance."


def test_get_price_malformed_symbol(client, mock_get_price):
    resp = client.get("/price/xy")
    assert resp.status_code == 422


def test_get_price_lowercase_symbol(client, mock_get_price):
    resp = client.get("/price/btcusdt")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "BTCUSDT"


# ── Vietnamese stock price endpoint ─────────────────────────────────────────


@pytest.fixture
def mock_vn_get_price(monkeypatch):
    """Patch vnstock.get_price so tests make no real network calls."""

    async def fake(symbol):
        return {"symbol": symbol, "price": "128500"}

    monkeypatch.setattr(vnstock, "get_price", fake)
    return monkeypatch


def test_get_vn_price_success(client, mock_vn_get_price):
    resp = client.get("/vprice/FPT")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "FPT"
    assert body["price"] == "128500"


def test_get_vn_price_invalid_symbol(client, monkeypatch):
    async def raise_invalid(symbol):
        raise vnstock.InvalidSymbolError("No data for symbol 'NOPE'.")

    monkeypatch.setattr(vnstock, "get_price", raise_invalid)
    resp = client.get("/vprice/NOPE")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Invalid symbol."


def test_get_vn_price_unavailable(client, monkeypatch):
    async def raise_unavailable(symbol):
        raise vnstock.VnStockUnavailableError("timeout")

    monkeypatch.setattr(vnstock, "get_price", raise_unavailable)
    resp = client.get("/vprice/FPT")
    assert resp.status_code == 502
    assert resp.json()["detail"] == (
        "Failed to fetch price from Vietnamese stock market."
    )


def test_get_vn_price_malformed_symbol(client, mock_vn_get_price):
    resp = client.get("/vprice/AB")  # too short (< 3 chars)
    assert resp.status_code == 422


def test_get_vn_price_lowercase_symbol(client, mock_vn_get_price):
    resp = client.get("/vprice/fpt")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "FPT"


def test_get_vn_price_numeric_rejected(client, mock_vn_get_price):
    resp = client.get("/vprice/FP1")  # numbers not allowed
    assert resp.status_code == 422


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
