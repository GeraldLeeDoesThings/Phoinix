import asyncio
import bs4
from const import *
import datetime
import discord
import globals
import json
import re
import requests
import types
from typing import *

with open("secrets/xivapikey") as key:
    xivapikey = key.read()

MAX_RATE = 10
CALLS_REMAINING = MAX_RATE
CALL_LOCK = asyncio.Lock()
HAS_CALLS = asyncio.Condition(CALL_LOCK)
API_SESSION = requests.Session()
API_SESSION.params["private_key"] = xivapikey


async def consume_limited_call():
    global CALLS_REMAINING, HAS_CALLS
    async with HAS_CALLS:
        while CALLS_REMAINING == 0:
            await HAS_CALLS.wait()
        CALLS_REMAINING -= 1


def extract_hammertime_timestamps(content: str) -> List[datetime.datetime]:
    return [
        datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc)
        for stamp in set(int(val) for val in re.findall("<t:(\d+):\w>", content))
    ]


def generate_hammertime_timestamp(dtime: datetime.datetime) -> str:
    return f"<t:{int(dtime.timestamp())}:R>"


async def validate_message_tags(
    m: discord.Message, member: Optional[discord.Member], role_ids: List[int]
):
    if member is None:
        print(f"FUCKED ID: {m.author.id}")
    else:
        for role in member.roles:
            if role.id in [ROLE_ID_MAP["Admin"], ROLE_ID_MAP["Moderator"]]:
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
    print(content)
    return [
        (discord.PartialEmoji.from_str(binding[0]), int(binding[1]))
        for binding in re.findall("\s*(\S+?)\s+= [a-zA-z ]+ <@&(\d+)>", content)
    ]


async def lodestone_search(
    name: str, server: str
) -> Optional[Dict[str, Union[str, int]]]:
    await consume_limited_call()
    results = API_SESSION.get(
        f"{XIVAPI_BASE_URL}character/search", params={"name": name, "server": server}
    ).json()["Results"]
    for result in results:
        if result["Name"] == name and result["Server"] == server:
            return {
                "id": result["ID"],
                "name": name,
                "server": server,
            }
    return None


def extract_name_server(
    id: int, req: Optional[requests.Response] = None
) -> Optional[Tuple[str, str]]:
    request = req if req is not None else requests.get(f"{LODESTONE_BASE_URL}{id}")
    if request.status_code == 404:
        return None
    result = bs4.BeautifulSoup(
        request.content.decode(),
        "html.parser",
    )
    name = result.find("p", "frame__chara__name").text
    server = result.find("p", "frame__chara__world").text
    return name, server


def full_validate(
    registered_data: Dict[str, Union[bool, int, str]]
) -> Union[str, Dict[str, Union[bool, int, str]]]:
    cid = registered_data["id"]
    name = registered_data["name"]
    server = registered_data["server"]
    token = registered_data["token"]
    resp = requests.get(f"{LODESTONE_BASE_URL}{cid}")
    fname, fserver = extract_name_server(cid, resp)
    if fname != name:
        return (
            f"Name {name} does not match name associated with character with ID {cid},"
            f" {fname}. Try using the Register button again."
        )
    if fserver.split(" ")[0] != server.split(" ")[0]:
        return (
            f"Server {server} does not match server associated with character with ID"
            f" {cid}, {fserver}. Try using the Register button again."
        )
    if not user_has_token_in_profile(cid, token, resp):
        return (
            f"Token, `{token}` (can be copied from {ECHO_TOKEN_URL}{token}), not found"
            f" in character profile at {LODESTONE_BASE_URL}{cid}"
        )
    registered_data["server"] = fserver  # Adds [Datacenter]
    registered_data["valid"] = True
    return registered_data


async def refresh_calls_loop():
    await asyncio.sleep(1)
    global CALLS_REMAINING, HAS_CALLS
    async with HAS_CALLS:
        CALLS_REMAINING = MAX_RATE
        HAS_CALLS.notify(MAX_RATE)
    schedule_task(refresh_calls_loop())


def user_has_token_in_profile(
    ffxiv_id: int, token: str, resp: Optional[requests.Response] = None
) -> bool:
    resp = resp if resp is not None else requests.get(f"{LODESTONE_BASE_URL}{ffxiv_id}")
    profile = bs4.BeautifulSoup(resp.content.decode(), "html.parser",).find_all(
        "div", "character__selfintroduction"
    )[
        0
    ]  # type: bs4.element.Tag

    return token in str(profile)


def user_has_achievement(ffxiv_id: int, achievement_code: int) -> Optional[bool]:
    ACHIEVEMENT_BASE_URL = (
        f"{LODESTONE_BASE_URL}{ffxiv_id}{LODESTONE_ACHIEVEMENT_BASE_URL}"
    )
    req = requests.get(f"{ACHIEVEMENT_BASE_URL}{achievement_code}/")
    if req.status_code == 404:
        return None  # signals hidden achievements
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


def load_verification_map():
    with open("data/verification_map.json", "r") as loadfile:
        str_verification_map = json.load(
            loadfile
        )  # type: Dict[str, Dict[str, Union[bool, int, str]]]
        for key in str_verification_map.keys():
            globals.verification_map[int(key)] = str_verification_map[key]


def load_ba_run_map():
    with open("data/ba_run_post_map.json", "r") as loadfile:
        str_ba_run_post_map = json.load(
            loadfile
        )
        import ba_recruiting
        for key in str_ba_run_post_map.keys():
            globals.ba_run_post_map[int(key)] = ba_recruiting.BARun(**str_ba_run_post_map[key])

