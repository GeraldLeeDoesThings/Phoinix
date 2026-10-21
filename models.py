from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "Users"

    discord_id = Column(Integer, primary_key=True, unique=True, nullable=False, index=True)
    ffxiv_id = Column(Integer, nullable=True, index=True)
    ffxiv_name = Column(String(64), nullable=True, index=True)
    ffxiv_server = Column(String(32), nullable=True, index=True)
    valid = Column(Boolean, default=False, nullable=False, index=True)
    token = Column(String(16), nullable=True, index=True)
