# Design: FastAPI Crypto Price Service Init

- **Ticket:** https://github.com/cuongpiger/mcutil/issues/1
- **Date:** 2026-09-12
- **Status:** Approved (pending spec PR)

## Goal

Initialize a FastAPI-based API service inside the `mcutil` repository. The service
exposes one API: given a crypto trading symbol (e.g. `BTCUSDT`, `ETHUSDT`), fetch
the current price from Binance and return it.

## Context

`mcutil` is a small personal utility package, published to PyPI, containing a
single utility (`cprint`). The package has empty `install_requires` and declares
`python_requires='>=3.6'`. The repo has no tests and no CI. The service is new
functionality added to this repo; the existing PyPI utility surface must remain
unchanged.

Verified Binance behavior (2026-09-12):

```
GET https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT
→ 200 {"symbol":"BTCUSDT","price":"77294.00000000"}

GET https://api.binance.com/api/v3/ticker/price?symbol=NOPEUSDT
→ 400 {"code":-1121,"msg":"Invalid symbol."}
```

No authentication is required for this endpoint.

## Architecture

The FastAPI app lives as a subpackage inside the existing `mcutil` package:

```
mcutil/
├── __init__.py          # unchanged: __version__, cprint export
├── printer.py           # unchanged
└── api/
    ├── __init__.py      # empty
    ├── app.py           # FastAPI instance, GET /price/{symbol} endpoint
    └── binance.py       # async Binance client
requirements.txt          # service runtime dependencies
requirements-dev.txt      # test dependencies (pytest)
tests/
└── test_api.py          # endpoint tests
README.md                # gains an "API service" section
```

Run with: `uvicorn mcutil.api.app:app`

## Components

### `mcutil/api/binance.py` — Binance client

One public function:

```python
async def get_price(symbol: str) -> dict
```

- Calls `https://api.binance.com/api/v3/ticker/price?symbol={symbol}` using a
  shared `httpx.AsyncClient` that lives in this module's namespace.
- The client is instantiated and closed by the app's lifespan handler (see
  `app.py`) so connections are reused across requests and shut down cleanly.
- Success: returns `{"symbol": <str>, "price": <str>}` (price stays a string,
  preserving Binance's precision).
- Failure: raises typed exceptions so `app.py` can map them to HTTP responses:
  - `InvalidSymbolError` — Binance responded 400 with code `-1121`.
  - `BinanceUnavailableError` — network error, timeout, or Binance 5xx.

### `mcutil/api/app.py` — FastAPI application

- Creates the `FastAPI` instance with an async-lifespan handler that opens the
  shared `httpx.AsyncClient` on startup and closes it on shutdown.
- One endpoint:

```
GET /price/{symbol}
→ 200 {"symbol": "BTCUSDT", "price": "77294.00000000"}
```

- `symbol` is a path parameter declared with a pattern of `[A-Za-z0-9]{5,20}`
  (letters and digits, either case, 5–20 characters — matches real Binance
  symbols like `BTCUSDT` and `1000SHIBUSDT` while rejecting junk). A pattern
  mismatch produces FastAPI's default 422 validation error.
- The handler uppercases the symbol before passing it to Binance, so
  `/price/btcusdt` works.
- Response model is a Pydantic model (`symbol: str`, `price: str`) so the shape
  is enforced and shows up in OpenAPI docs.

## Data Flow

1. Caller requests `GET /price/BTCUSDT`.
2. Path parameter is validated against the symbol pattern; failure → 422
   (FastAPI validation error).
3. The handler uppercases the symbol and awaits `binance.get_price(symbol)`.
4. On success the symbol/price pair is returned as JSON.
5. On failure the typed exception is mapped to an HTTP error response (below).

## Error Handling

| Case | Response |
|---|---|
| Binance 400 `-1121 Invalid symbol.` | 404 `{"detail": "Invalid symbol."}` |
| Binance unreachable, timeout, or 5xx | 502 `{"detail": "Failed to fetch price from Binance."}` |
| Malformed symbol in path (fails pattern) | 422 (FastAPI default validation error) |

Rationale for 404 on invalid symbol: Binance's 400 describes the *caller's*
resource (the symbol) not existing, not a malformed request to our service —
404 is the semantically correct mapping for our API.

## Dependencies & Packaging

- Service runtime dependencies: `fastapi`, `uvicorn`, `httpx` — declared in a
  new `requirements.txt` (e.g. `fastapi>=0.110`).
- Test dependency: `pytest` — declared in a new `requirements-dev.txt`.
- None of these go into `setup.py` `install_requires`, so `pip install mcutil`
  (the general utility package) does not force FastAPI on library users.
- `setup.py` is otherwise untouched; existing `python_requires='>=3.6'` stays.
  The service itself is developed and tested on Python 3.11.
- `README.md` gains a short "API service" section: install deps, run command,
  example curl.

## Testing

`pytest` + `fastapi.testclient.TestClient` (in-process, no server, no network).
`binance.get_price` is mocked (monkeypatched) in every test — no real network
calls:

1. `GET /price/BTCUSDT` mocked to return a price → 200, body has `symbol` and
   `price` strings.
2. Mocked `InvalidSymbolError` → 404 with `{"detail": "Invalid symbol."}`.
3. Mocked `BinanceUnavailableError` → 502 with the failure detail.
4. Malformed symbol (e.g. `GET /price/xy`) → 422.
5. Lowercase symbol `/price/btcusdt` (mocked success) → 200 (handler
   uppercasing works).

Tests live in `tests/test_api.py` — the repo's first tests directory.

## Out of Scope

- No Dockerfile, CI workflow, or deployment config (ticket asks for the service
  itself; deploy can be a follow-up ticket).
- No caching of prices, no additional Binance endpoints, no websockets.
- No changes to the existing `cprint` utility or published package surface.
