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
