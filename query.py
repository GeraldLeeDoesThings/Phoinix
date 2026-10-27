from sqlalchemy.orm import Session

from const import MAX_SEARCH_VALUES
from models import User
from secrets import token_urlsafe
from sqlalchemy import select
from typing import Optional


def commit_user(session: Session, user: User):
    session.merge(user)
    session.commit()


def get_by_discord_id(session: Session, discord_id: int) -> Optional[User]:
    select_statement = select(User).where(
        discord_id == User.discord_id
    )
    return session.execute(select_statement).scalars().first()


def get_by_ffxiv_name(
    session: Session,
    ffxiv_name_pattern: str,
    server_limit: Optional[str] = None
) -> list[User]:
    constraint = User.ffxiv_name.regexp_match(ffxiv_name_pattern)
    if server_limit is not None:
        constraint = constraint and User.ffxiv_server == server_limit
    select_statement = select(User).where(constraint).limit(MAX_SEARCH_VALUES)
    return list(*session.execute(select_statement).all())


def get_user_token(session: Session, discord_id: int) -> str:
    user = get_by_discord_id(session, discord_id)
    if user is None:
        return token_urlsafe(8)
    return user.token


def get_user_ffxiv_id(session: Session, discord_id: int) -> Optional[int]:
    user = get_by_discord_id(session, discord_id)
    if user is None:
        return None
    return user.ffxiv_id
