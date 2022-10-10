import asyncio
import datetime
import discord
import discord.app_commands as app_commands
import requests
from typing import *


CHANNEL_ID_MAP = {
    "ba-recruiting": 1029102392601497682,
    "drs-recruiting": 1029102476156215307,
}

ROLE_ID_MAP = {
    "BA Learning": 1029114312624705576,
    "BA Reclear": 1029114561363705936,
    "DRS Learning": 1029114229845917776,
    "DRS Reclear": 1029083391208984597,
    "Admin": 1028878560536035428,
    "Moderator": 1029076383542018108,
}

GRACE_TIME = datetime.datetime.fromisoformat("2022-10-10 23:16:42.262194+00:00")


class PhoinixBot(discord.Client):

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
            asyncio.create_task(m.reply(
                "Please ensure messages in this channel mention at least one of DRS/BA Learners/Reclears. Your message will be deleted in 10 seconds.",
                delete_after=30
            ))
            asyncio.create_task(m.delete(delay=30))

    async def delete_untagged_messages(self):
        ba = self.get_channel(CHANNEL_ID_MAP["ba-recruiting"])
        drs = self.get_channel(CHANNEL_ID_MAP["drs-recruiting"])

        ba_messages = ba.history(limit=100, after=GRACE_TIME)
        drs_messages = drs.history(limit=100, after=GRACE_TIME)

        async for message in ba_messages:
            # This is dumb and only here for autocomplete
            m = message  # type: discord.Message
            await self.validate_message_tags(
                m, [ROLE_ID_MAP["BA Learning"], ROLE_ID_MAP["BA Reclear"]]
            )

        async for message in drs_messages:
            # Same thing here
            m = message  # type: discord.Message
            await self.validate_message_tags(
                m, [ROLE_ID_MAP["DRS Learning"], ROLE_ID_MAP["DRS Reclear"]]
            )


    async def on_ready(self):
        print("Nya")
        self.PEBE = self.get_guild(1028110201968132116)
        print(self.PEBE)
        await self.delete_untagged_messages()

    async def on_message(self, message: discord.Message):
        if message.channel.id == CHANNEL_ID_MAP["ba-recruiting"]:
            await self.validate_message_tags(
                message,
                [ROLE_ID_MAP["BA Learning"], ROLE_ID_MAP["BA Reclear"]]
            )
        elif message.channel.id == CHANNEL_ID_MAP["drs-recruiting"]:
            await self.validate_message_tags(
                message,
                [ROLE_ID_MAP["DRS Learning"], ROLE_ID_MAP["DRS Reclear"]]
            )


intents = discord.Intents.default()
intents.message_content = True

bot = PhoinixBot(intents=intents)
with open("token", "r") as token:
    bot.run(token.read())
