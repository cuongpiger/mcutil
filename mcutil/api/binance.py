import httpx

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"

_client: httpx.AsyncClient | None = None


class InvalidSymbolError(Exception):
    """Binance responded 400 with code -1121 (symbol does not exist)."""


class BinanceUnavailableError(Exception):
    """Binance is unreachable, timed out, or returned a 5xx response."""


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient()
    return _client


async def get_price(symbol: str) -> dict:
    """Fetch the current price for *symbol* from Binance.

    Returns ``{"symbol": <str>, "price": <str>}``.
    """
    client = await _get_client()
    try:
        resp = await client.get(BINANCE_TICKER_URL, params={"symbol": symbol})
    except httpx.HTTPError as exc:
        raise BinanceUnavailableError(str(exc)) from exc

    if resp.status_code == 400:
        body = resp.json()
        if body.get("code") == -1121:
            raise InvalidSymbolError(body.get("msg", "Invalid symbol."))

    if resp.status_code >= 500:
        raise BinanceUnavailableError(
            f"Binance returned {resp.status_code}"
        )

    resp.raise_for_status()
    return resp.json()


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
