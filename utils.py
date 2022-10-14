import asyncio
from const import *
from datetime import datetime
import discord
import re
from typing import *


def extract_hammertime_timestamps(content: str) -> List[datetime]:
    return [
        datetime.fromtimestamp(stamp)
        for stamp in set(int(val) for val in re.findall("<t:(\d+):\w>", content))
    ]


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
        asyncio.create_task(
            m.reply(
                "Please ensure messages in this channel mention at least one of DRS/BA Learners/Reclears. Your message will be deleted in 30 seconds.",
                delete_after=30,
            )
        )
        asyncio.create_task(m.delete(delay=30))


def extract_react_bindings(content: str) -> List[Tuple[discord.PartialEmoji, int]]:
    return [(discord.PartialEmoji.from_str(binding[0]), int(binding[1])) for binding in re.findall("(<a?:[a-zA-Z_]+:\d+>)\s+= [a-zA-z ]+ <@&(\d+)>", content)]
