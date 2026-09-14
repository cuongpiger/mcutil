import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer
from sqlalchemy import Enum as SAEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .account import Account
from .db import Base


class TransactionType(str, enum.Enum):
    """The kind of movement a transaction records."""

    deposit = "deposit"


class Transaction(Base):
    """An audit record of a single movement of money on an account."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


async def deposit(
    session: AsyncSession, account_id: int, amount: float
) -> Transaction | None:
    """Credit *amount* to an account and record the deposit.

    Returns ``None`` if no account has *account_id* — the caller decides what
    a missing account means. Flushes so the returned transaction has its
    generated ``id`` and ``created_at``, but leaves committing to the caller.
    """
    account = await session.get(Account, account_id)
    if account is None:
        return None
    account.balance += amount
    transaction = Transaction(
        account_id=account_id, amount=amount, type=TransactionType.deposit
    )
    session.add(transaction)
    await session.flush()
    return transaction
