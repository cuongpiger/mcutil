import httpx

TCBS_STOCK_INFO_URL = "https://api-price.tcbs.com.vn/stock/info"

_client: httpx.AsyncClient | None = None


class InvalidSymbolError(Exception):
    """TCBS returned no data for the given stock symbol."""


class VnStockUnavailableError(Exception):
    """TCBS is unreachable, timed out, or returned a 5xx response."""


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient()
    return _client


async def get_price(symbol: str) -> dict:
    """Fetch the current price for *symbol* from TCBS.

    Returns ``{"symbol": <str>, "price": <str>}``.
    """
    client = await _get_client()
    try:
        resp = await client.get(
            TCBS_STOCK_INFO_URL, params={"symbol": symbol}
        )
    except httpx.HTTPError as exc:
        raise VnStockUnavailableError(str(exc)) from exc

    if resp.status_code >= 500:
        raise VnStockUnavailableError(
            f"TCBS returned {resp.status_code}"
        )

    resp.raise_for_status()
    body = resp.json()

    price = body.get("lastPrice")
    if price is None or (isinstance(price, (int, float)) and price == 0):
        raise InvalidSymbolError(f"No data for symbol '{symbol}'.")

    # TCBS sometimes returns the price in thousands (e.g. 61.3 → 61300)
    if isinstance(price, (int, float)) and price < 1000:
        price = int(round(price * 1000))

    return {"symbol": symbol, "price": str(price)}


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
