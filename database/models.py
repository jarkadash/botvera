from sqlalchemy import String, Integer, Text, Float, func, ForeignKey, BigInteger, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncAttrs
from typing import Annotated
import datetime

intpk = Annotated[int, mapped_column(primary_key=True)]


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Users(Base):
    __tablename__ = 'users'
    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class Orders(Base):
    __tablename__ = 'orders'
    id: Mapped[intpk]
    client_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'))
    client_name: Mapped[str]
    support_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'), nullable=True)
    support_name: Mapped[str] = mapped_column(String(100), nullable=True)
    service_id: Mapped[int] = mapped_column(BigInteger)
    service_name: Mapped[str]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    accept_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(100), default='New')
    stars: Mapped[float] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(String(100), nullable=True)


class Media(Base):
    __tablename__ = 'medias'
    id: Mapped[intpk]
    url: Mapped[str]
    description: Mapped[str] = mapped_column(String(100), nullable=True)
    name_cheat: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'), nullable=True)
    username: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

class HistoryMessages(Base):
    __tablename__ = 'history_messages'
    id: Mapped[intpk]
    support_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=True)


class BannedUsers(Base):
    __tablename__ = 'banned_users'
    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'))
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class Services(Base):
    __tablename__ = 'services'
    id: Mapped[intpk]
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    allowed_roles: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class Roles(Base):
    __tablename__ = 'roles'
    id: Mapped[intpk]
    role_name: Mapped[str] = mapped_column(String(100), nullable=False)


class PaymentRates(Base):
    __tablename__ = "payment_rates"
    id: Mapped[intpk]
    support_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), unique=True, nullable=False)
    technical_support: Mapped[int] = mapped_column(default=60)
    payment_support: Mapped[int] = mapped_column(default=30)
    hwid_reset: Mapped[int] = mapped_column(default=30)
    get_key: Mapped[int] = mapped_column(default=100)
    reselling: Mapped[int] = mapped_column(default=30)
    bonus_per_50: Mapped[int] = mapped_column(default=1000)