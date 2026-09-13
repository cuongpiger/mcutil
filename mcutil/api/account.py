import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Sex(str, enum.Enum):
    """Account owner's sex."""

    male = "male"
    female = "female"
    other = "other"


class Account(Base):
    """An account owner and their current equity."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    sex: Mapped[Sex] = mapped_column(SAEnum(Sex), nullable=False)
    balance: Mapped[float] = mapped_column(Float, nullable=False)


async def create_account(
    session: AsyncSession, name: str, sex: Sex, balance: float
) -> Account:
    """Insert a new account and return it with its generated ``id``.

    Flushes so the primary key is populated, but leaves committing to the
    caller.
    """
    account = Account(name=name, sex=sex, balance=balance)
    session.add(account)
    await session.flush()
    return account
