import pytz
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

local_tz = pytz.timezone('Europe/Moscow')

def local_now():
    return datetime.now(local_tz)

class Base(DeclarativeBase):
    created: Mapped[DateTime] = mapped_column(DateTime, default=local_now)
    updated: Mapped[DateTime] = mapped_column(DateTime, default=local_now, onupdate=local_now)


class Category(Base):
    __tablename__ = 'category'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)


class Detail(Base):
    __tablename__ = 'detail'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    number: Mapped[str] = mapped_column(String(6), nullable=False)
    status: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey('category.id'), nullable=False)

    category: Mapped['Category'] = relationship(backref='detail')


class Task(Base):
    __tablename__ = 'tasks'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    description: Mapped[str] = mapped_column(Text)
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    contact_number: Mapped[str] = mapped_column(String, nullable=False)
    group_message_id: Mapped[int] = mapped_column(nullable=True)
