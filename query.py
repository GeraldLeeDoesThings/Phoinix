from sqlalchemy.orm import Session

from const import MAX_SEARCH_VALUES
from models import User
from secrets import token_urlsafe
from sqlalchemy import select
from typing import Optional, Tuple
from utils import extract_name_server, lodestone_search


def commit_user(session: Session, user: User):
    session.merge(user)
    session.commit()


def get_by_discord_id(session: Session, discord_id: int) -> Optional[User]:
    select_statement = select(User).where(
        discord_id == User.discord_id
    )
    return session.execute(select_statement).first()


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


def get_user_ffxiv_name_server(session: Session, discord_id: int) -> Optional[Tuple[str, str]]:
    user = get_by_discord_id(session, discord_id)
    if user is None or user.ffxiv_id is None:
        return None

    if user.ffxiv_name is None or user.ffxiv_server is None:
        name_server_pair = extract_name_server(user.ffxiv_id)
        if name_server_pair is None:
            return None
        name, server = name_server_pair
        user.ffxiv_name = name
        user.ffxiv_server = server
        commit_user(session, user)
        return name, server
    else:
        return user.ffxiv_name, user.ffxiv_server


def register_user(
    session: Session,
    discord_id: int,
    ffxiv_name: str,
    ffxiv_server: str,
    ffxiv_id: Optional[int] = None,
    force: bool = False,
) -> bool:
    user = User(
        discord_id=discord_id,
        ffxiv_name=ffxiv_name,
        ffxiv_server=ffxiv_server,
        valid=False,
        token=get_user_token(session, discord_id),
    )

    if not force:
        user.ffxiv_id = ffxiv_id
        if ffxiv_id is None:
            search = lodestone_search(ffxiv_name, ffxiv_server)
            if search is None:
                return False
            user.ffxiv_id = search["id"]

    commit_user(session, user)
    return True
