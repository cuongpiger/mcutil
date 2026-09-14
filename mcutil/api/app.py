from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel

from . import account, binance, db, transaction, vnstock


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


class DepositRequest(BaseModel):
    amount: float


class DepositResponse(BaseModel):
    id: int
    account_id: int
    amount: float
    type: str
    created_at: datetime


@app.post(
    "/accounts/{account_id}/deposits",
    response_model=DepositResponse,
    status_code=201,
)
async def deposit(account_id: int, payload: DepositRequest):
    """Credit money to an account and record the deposit."""
    if payload.amount <= 0:
        raise HTTPException(
            status_code=422, detail="Deposit amount must be positive."
        )
    async with db.async_session() as session:
        recorded = await transaction.deposit(
            session, account_id, payload.amount
        )
        if recorded is None:
            raise HTTPException(status_code=404, detail="Account not found.")
        await session.commit()
    return DepositResponse(
        id=recorded.id,
        account_id=recorded.account_id,
        amount=recorded.amount,
        type=recorded.type.value,
        created_at=recorded.created_at,
    )
