import asyncio
from const import *
import datetime
import discord
import discord.app_commands as app_commands
import re
import requests
import threading
from typing import *
from utils import *


class PhoinixBot(discord.Client):
    def __init__(self, *, intents: discord.Intents, **options: Any):
        self.target_channel_id = None
        super().__init__(intents=intents, **options)

    async def validate_message_tags(self, m: discord.Message, role_ids: List[int]):

        member = await self.PEBE.fetch_member(m.author.id)
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

    def fetch_member(self, id: int) -> Optional[discord.Member]:
        try:
            return await self.PEBE.fetch_member(id)
        except discord.Forbidden:
            print("Insufficient permission to read members! Please fix :(")
        except discord.NotFound:
            print(f"User with ID {id} could not be found! Did they leave?")
        except discord.HTTPException:
            pass
        return None

    async def delete_untagged_messages(self):
        ba = self.get_channel(CHANNEL_ID_MAP["ba-recruiting"])
        drs = self.get_channel(CHANNEL_ID_MAP["drs-recruiting"])

        ba_messages = ba.history(limit=100, after=GRACE_TIME)
        drs_messages = drs.history(limit=100, after=GRACE_TIME)

        async for message in ba_messages:
            # This is dumb and only here for autocomplete
            m = message  # type: discord.Message
            await validate_message_tags(
                m,
                self.fetch_member(m.author.id),
                [ROLE_ID_MAP["BA Learning"], ROLE_ID_MAP["BA Reclear"]],
            )

        async for message in drs_messages:
            # Same thing here
            m = message  # type: discord.Message
            await validate_message_tags(
                m,
                self.fetch_member(m.author.id),
                [ROLE_ID_MAP["DRS Learning"], ROLE_ID_MAP["DRS Reclear"]],
            )

    async def on_ready(self):
        print("Nya")
        self.PEBE = self.get_guild(1028110201968132116)
        print(self.PEBE)
        await self.delete_untagged_messages()
        self.aloop = asyncio.get_running_loop()

    async def on_message(self, message: discord.Message):
        id = message.channel.id
        if id == CHANNEL_ID_MAP["ba-recruiting"]:
            await self.validate_message_tags(
                message, [ROLE_ID_MAP["BA Learning"], ROLE_ID_MAP["BA Reclear"]]
            )
        elif id == CHANNEL_ID_MAP["drs-recruiting"]:
            await self.validate_message_tags(
                message, [ROLE_ID_MAP["DRS Learning"], ROLE_ID_MAP["DRS Reclear"]]
            )
        elif id == CHANNEL_ID_MAP["command"]:
            await self.parse_console_command(message.content)

    async def parse_console_command(self, command):
        if command.startswith("send"):
            await self.impersonate(self.target_channel_id, command[5:])
        elif command.startswith("join"):
            try:
                self.target_channel_id = int(command[5:])
            except:
                pass

    async def impersonate(self, channel_id, message):
        maybe_channel = self.get_channel(channel_id)
        if maybe_channel is not None:
            await maybe_channel.send(message)


intents = discord.Intents.default()
intents.message_content = True

bot = PhoinixBot(intents=intents)

with open("token", "r") as token:
    bot.run(token.read())
