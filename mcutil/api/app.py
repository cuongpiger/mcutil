from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel

from . import account, binance, db, vnstock


class PriceResponse(BaseModel):
    symbol: str
    price: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield
    await binance.close_client()
    await vnstock.close_client()
    await db.close_engine()


app = FastAPI(lifespan=lifespan)

SymbolPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9]{5,20}$")]
VnSymbolPath = Annotated[str, Path(pattern=r"^[A-Za-z]{3,10}$")]


@app.get("/price/{symbol}", response_model=PriceResponse)
async def get_price(symbol: SymbolPath):
    """Fetch the current price for *symbol* from Binance.

    Symbol must be 5–20 alphanumeric characters (e.g. ``BTCUSDT``).
    Lowercase input is uppercased automatically.
    """
    symbol = symbol.upper()
    try:
        data = await binance.get_price(symbol)
    except binance.InvalidSymbolError:
        raise HTTPException(status_code=404, detail="Invalid symbol.")
    except binance.BinanceUnavailableError:
        raise HTTPException(
            status_code=502, detail="Failed to fetch price from Binance."
        )
    return PriceResponse(symbol=data["symbol"], price=data["price"])


@app.get("/vprice/{symbol}", response_model=PriceResponse)
async def get_vn_price(symbol: VnSymbolPath):
    """Fetch the current price for *symbol* from the Vietnamese stock market via TCBS.

    Symbol must be 3–10 alphabetic characters (e.g. ``FPT``, ``HPG``, ``MWG``).
    Lowercase input is uppercased automatically.
    """
    symbol = symbol.upper()
    try:
        data = await vnstock.get_price(symbol)
    except vnstock.InvalidSymbolError:
        raise HTTPException(status_code=404, detail="Invalid symbol.")
    except vnstock.VnStockUnavailableError:
        raise HTTPException(
            status_code=502,
            detail="Failed to fetch price from Vietnamese stock market.",
        )
    return PriceResponse(symbol=data["symbol"], price=data["price"])


class AccountCreate(BaseModel):
    name: str
    sex: account.Sex
    balance: float


class AccountResponse(BaseModel):
    id: int
    name: str
    sex: account.Sex
    balance: float


@app.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(payload: AccountCreate):
    """Create a new account and return it with its generated ``id``."""
    async with db.async_session() as session:
        created = await account.create_account(
            session, payload.name, payload.sex, payload.balance
        )
        await session.commit()
    return AccountResponse(
        id=created.id,
        name=created.name,
        sex=created.sex,
        balance=created.balance,
    )
