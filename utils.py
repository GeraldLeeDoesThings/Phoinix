from __future__ import annotations

import asyncio

from httpx import Response

from lodestone import make_request
from secrets import token_urlsafe
from sqlalchemy.orm import Session

import bs4
from const import *
import datetime
import discord
import globals
import json
from models import User
import nltk
import re
import types
from typing import *

from query import get_user_token, commit_user, get_by_discord_id

if TYPE_CHECKING:
    from bot import PhoinixBot


with open("secrets/xivapikey") as key:
    xivapikey = key.read()

MAX_RATE = 10
CALLS_REMAINING = MAX_RATE
CALL_LOCK = asyncio.Lock()
HAS_CALLS = asyncio.Condition(CALL_LOCK)


async def consume_limited_call():
    global CALLS_REMAINING, HAS_CALLS
    async with HAS_CALLS:
        while CALLS_REMAINING == 0:
            await HAS_CALLS.wait()
        CALLS_REMAINING -= 1


def delayed(delay_secs: float):
    def delayed_deco(func):
        async def delayed_wrapper(*args, **kwargs):
            await asyncio.sleep(delay_secs)
            if asyncio.iscoroutinefunction(func):
                await func(*args, **kwargs)
            else:
                func(*args, **kwargs)

        return delayed_wrapper

    return delayed_deco


def extract_hammertime_timestamps(content: str) -> List[datetime.datetime]:
    return [
        datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc)
        for stamp in set(int(val) for val in re.findall("<t:(\d+):\w>", content))
    ]


def generate_hammertime_timestamp(dtime: datetime.datetime) -> str:
    return f"<t:{int(dtime.timestamp())}:R>"


def generate_hammertime_timestamp_detailed(dtime: datetime.datetime) -> str:
    return f"<t:{int(dtime.timestamp())}:F> ({generate_hammertime_timestamp(dtime)})"


async def validate_message_tags(
    m: discord.Message, member: Optional[discord.Member], role_ids: List[int]
):
    if member is None:
        print(f"FUCKED ID: {m.author.id}")
    else:
        for role in member.roles:
            if role.id in [
                ROLE_ID_MAP["Admin"],
                ROLE_ID_MAP["Moderator"],
                ROLE_ID_MAP["Bots"],
            ]:
                return

    if member.bot:
        return

    bad_message = True
    for role_mention in m.role_mentions:
        if role_mention.id in role_ids:
            bad_message = False
            break
    if bad_message:
        schedule_task(
            m.reply(
                "Please ensure messages in this channel mention at least one of DRS/BA"
                " Learners/Reclears. Your message will be deleted in 30 seconds.",
                delete_after=30,
            )
        )
        schedule_task(m.delete(delay=30))


def extract_react_bindings(content: str) -> List[Tuple[discord.PartialEmoji, int]]:
    return [
        (discord.PartialEmoji.from_str(binding[0]), int(binding[1]))
        for binding in re.findall("\s*(\S+?)\s+=[a-zA-z* ]*<@&(\d+)>", content)
    ]


async def lodestone_search(
    name: str,
    server: str,
) -> Optional[Dict[str, Union[str, int]]]:
    page = 1
    numPages = 1

    while page <= min(numPages, 5):
        request = await make_request(
            LODESTONE_BASE_URL, params={"q": "\"" + name + "\"", "page": page, "worldname": server}
        )
        result = bs4.BeautifulSoup(
            request.content.decode(),
            "html.parser",
        )
        numPagesHTML = result.find("li", "btn__pager__current")

        if numPagesHTML is not None:
            numPagesMatch = re.match(r"Page \d+ of (\d+)", numPagesHTML.text)
            if numPagesMatch is not None:
                numPages = int(numPagesMatch[1])

        for player in result.find_all("a", "entry__link"):
            found_name, found_server, _, _ = list(player.stripped_strings)  # type: str
            found_id = player["href"].split("/")[-2]
            if found_name == name and found_server.startswith(server):
                return {
                    "id": int(found_id),
                    "name": found_name,
                    "server": found_server,
                }
        page += 1

    return None


async def extract_name_server(
    character_id: int, req: Optional[Response] = None
) -> Optional[Tuple[str, str]]:
    request = req if req is not None else await make_request(f"{LODESTONE_BASE_URL}{character_id}")
    if request.status_code == 404:
        return None
    result = bs4.BeautifulSoup(
        request.content.decode(),
        "html.parser",
    )
    name = result.find("p", "frame__chara__name")
    if name is None:
        print(f"Got strange response from Lodestone: {request.content}")
        return None
    else:
        name = name.text

    server = result.find("p", "frame__chara__world")
    if server is None:
        print(f"Got strange response from Lodestone: {request.content}")
        return None
    else:
        server = server.text
    return name, server


async def full_validate(
    user: User
) -> User | str:

    if user.ffxiv_id is None:
        return "User has no associated FFXIV character id!"

    response = await make_request(f"{LODESTONE_BASE_URL}{user.ffxiv_id}")
    name_server_pair = await extract_name_server(user.ffxiv_id, response)
    if name_server_pair is None:
        return f"Failed to retrieve name and server for character with ID {user.ffxiv_id}. Try registering again."

    fname, fserver = name_server_pair
    if fname != user.ffxiv_name:
        return (
            f"Name {user.ffxiv_name} does not match name associated with character with ID {user.ffxiv_id},"
            f" {fname}. Try using the Register button again."
        )
    if fserver.split(" ")[0] != user.ffxiv_server.split(" ")[0]:
        return (
            f"Server {user.ffxiv_server} does not match server associated with character with ID"
            f" {user.ffxiv_id}, {fserver}. Try using the Register button again."
        )

    if user.token is None:
        user.token = token_urlsafe(8)

    if not await user_has_token_in_profile(user.ffxiv_id, user.token, response):
        return (
            f"Token, `{user.token}` (can be copied from {ECHO_TOKEN_URL}{user.token}), not found"
            f" in character profile at {LODESTONE_BASE_URL}{user.ffxiv_id}\n Additionally, **ensure your lodestone is not set to private.**"
        )
    user.ffxiv_server = fserver  # Adds [Datacenter]
    user.valid = True
    return user


async def refresh_calls_loop():
    await asyncio.sleep(1)
    global CALLS_REMAINING, HAS_CALLS
    async with HAS_CALLS:
        CALLS_REMAINING = MAX_RATE
        HAS_CALLS.notify(MAX_RATE)
    schedule_task(refresh_calls_loop())


async def user_has_token_in_profile(
    ffxiv_id: int, token: str, resp: Optional[Response] = None
) -> bool:
    resp = resp if resp is not None else await make_request(f"{LODESTONE_BASE_URL}{ffxiv_id}")
    profile = bs4.BeautifulSoup(resp.content.decode(), "html.parser",).find_all(
        "div", "character__selfintroduction"
    )[
        0
    ]  # type: bs4.element.Tag

    return token in str(profile)


async def user_has_achievement(ffxiv_id: int, achievement_code: int) -> Optional[bool]:
    ACHIEVEMENT_BASE_URL = (
        f"{LODESTONE_BASE_URL}{ffxiv_id}{LODESTONE_ACHIEVEMENT_BASE_URL}"
    )
    req = await make_request(f"{ACHIEVEMENT_BASE_URL}{achievement_code}/")
    if req.status_code == 404:
        return None  # signals hidden achievements
    elif len(req.content) == 0:
        print("Weird response from Lodestone")
        raise False
    return (
        len(
            bs4.BeautifulSoup(req.content.decode(), "html.parser").find_all(
                "div",
                "entry__achievement__view entry__achievement__view--complete",
            )
        )
        > 0
    )


async def trigger_later(event: asyncio.Event, delay: float):
    await asyncio.sleep(delay)
    event.set()


async def wait_and_clear(event: asyncio.Event):
    await event.wait()
    event.clear()


def schedule_task(coro):
    task = asyncio.create_task(coro)
    globals.background_tasks.add(task)
    task.add_done_callback(globals.background_tasks.discard)


def generate_button(
    label: str,
    custom_id: str,
    style: discord.ButtonStyle,
    callback: Callable[[discord.ui.Button, discord.Interaction], Awaitable[Any]],
) -> discord.ui.Button:
    button = discord.ui.Button(
        label=label,
        custom_id=custom_id,
        style=style,
    )
    button.callback = types.MethodType(callback, button)
    return button


def load_ba_run_map(bot: PhoinixBot):
    with open("data/ba_run_post_map.json", "r") as loadfile:
        str_ba_run_post_map = json.load(loadfile)
        import ba_recruiting

        for key in str_ba_run_post_map.keys():
            globals.ba_run_post_map[int(key)] = ba_recruiting.BARun(
                bot=bot, **str_ba_run_post_map[key]
            )


def validate_server(server: str) -> (bool, str):
    if server.capitalize() in FFXIV_SERVERS:
        return True, ""
    suggestion, _ = min(
        (
            (tserver, nltk.edit_distance(server.capitalize(), tserver))
            for tserver in FFXIV_SERVERS
        ),
        key=lambda p: p[1],
    )
    return False, f"'{server}' is not a server. Did you mean '{suggestion}'?"


async def validate_mount(ffxiv_id: int, mount_id: str) -> bool:
    req = await make_request(f"{LODESTONE_BASE_URL}{ffxiv_id}/mount/")
    parsed = bs4.BeautifulSoup(req.text, "html.parser")
    return (
        parsed.find(
            "li",
            attrs={
                "class": "mount__list_icon",
                "data-tooltip_href": f"/lodestone/character/{ffxiv_id}/mount/tooltip/{mount_id}",
            },
        )
        is not None
    )


async def get_user_ffxiv_name_server(session: Session, discord_id: int) -> Optional[Tuple[str, str]]:
    user = get_by_discord_id(session, discord_id)
    if user is None or user.ffxiv_id is None:
        return None

    if user.ffxiv_name is None or user.ffxiv_server is None:
        name_server_pair = await extract_name_server(user.ffxiv_id)
        if name_server_pair is None:
            return None
        name, server = name_server_pair
        user.ffxiv_name = name
        user.ffxiv_server = server
        commit_user(session, user)
        return name, server
    else:
        return user.ffxiv_name, user.ffxiv_server


async def register_user(
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
            search = await lodestone_search(ffxiv_name, ffxiv_server)
            if search is None:
                return False
            user.ffxiv_id = search["id"]

    commit_user(session, user)
    return True
