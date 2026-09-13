import pytest
from fastapi.testclient import TestClient

from mcutil.api import binance
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
