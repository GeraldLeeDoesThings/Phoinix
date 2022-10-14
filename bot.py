import asyncio
import bs4
from const import *
import datetime
import discord
import re
import requests
import secrets
import threading
from typing import *
from utils import *


class PhoinixBot(discord.Bot):
    def __init__(self, *, intents: discord.Intents, **options: Any):
        self.PEBE = None  # type: discord.Guild
        self.target_channel_id = None
        # Maps Message ID -> (Emoji -> Role ID)
        self.reaction_bindings = (
            {}
        )  # type: Mapping[int, Mapping[discord.PartialEmoji, int]]
        super().__init__(intents=intents, **options)

    async def delete_recruitment_post_and_related(self, rpost: discord.Message):
        times = extract_hammertime_timestamps(rpost.content)
        if len(times) == 0:
            # No timestamps, just delete the post
            await rpost.delete()
        else:
            # Has timestamps, delete the authors messages from those days
            for timestamp in times:
                await rpost.channel.purge(
                    before=timestamp + HALF_DAY,
                    after=timestamp - HALF_DAY,
                    reason="Recruitment post cleanup",
                )

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
                    "Please ensure messages in this channel mention at least one of"
                    " DRS/BA Learners/Reclears. Your message will be deleted in 30"
                    " seconds.",
                    delete_after=30,
                )
            )
            asyncio.create_task(m.delete(delay=30))

    async def fetch_member(self, id: int) -> Optional[discord.Member]:
        try:
            return await self.PEBE.fetch_member(id)
        except discord.Forbidden:
            print("Insufficient permission to read members! Please fix :(")
        except discord.NotFound:
            print(f"User with ID {id} could not be found! Did they leave?")
        except discord.HTTPException:
            pass
        return None

    async def compute_reaction_bindings(self):
        messages = self.PEBE.get_channel(CHANNEL_ID_MAP["roles"]).history()
        self.reaction_bindings = {}
        async for message in messages:
            try:
                author = await self.PEBE.fetch_member(message.author.id)
                if author.get_role(ROLE_ID_MAP["Admin"]) is not None:
                    self.reaction_bindings[message.id] = {}
                    for emoji, role_id in extract_react_bindings(message.content):
                        self.reaction_bindings[message.id][emoji] = role_id
                        try:
                            await message.add_reaction(emoji)
                        except:
                            pass  # Nobody cares if this fails
            except discord.NotFound:
                print(
                    "Whoever posted the role react message is gone! Someone repost it!"
                )

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
                await self.fetch_member(m.author.id),
                [ROLE_ID_MAP["BA Learning"], ROLE_ID_MAP["BA Reclear"]],
            )

        async for message in drs_messages:
            # Same thing here
            m = message  # type: discord.Message
            await validate_message_tags(
                m,
                await self.fetch_member(m.author.id),
                [ROLE_ID_MAP["DRS Learning"], ROLE_ID_MAP["DRS Reclear"]],
            )

    async def on_ready(self):
        print("Nya")
        self.PEBE = self.get_guild(1028110201968132116)
        print(self.PEBE)
        await self.delete_untagged_messages()
        await self.compute_reaction_bindings()
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
        elif id == CHANNEL_ID_MAP["roles"]:
            await self.compute_reaction_bindings()

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if payload.channel_id == CHANNEL_ID_MAP["roles"]:
            await self.compute_reaction_bindings()

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.user.id:
            return
        message_bindings = self.reaction_bindings.get(payload.message_id, None)
        if message_bindings is not None:
            role_id = message_bindings.get(payload.emoji, None)
            if role_id is not None:
                await payload.member.add_roles(
                    discord.Object(role_id), reason="Reaction"
                )

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.user.id:
            return
        message_bindings = self.reaction_bindings.get(payload.message_id, None)
        if message_bindings is not None:
            role_id = message_bindings.get(payload.emoji, None)
            if role_id is not None:
                try:
                    member = await self.PEBE.fetch_member(payload.user_id)
                    await member.remove_roles(
                        discord.Object(role_id), reason="Reaction"
                    )
                except discord.NotFound:
                    pass
                except discord.HTTPException:
                    pass

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


intents = discord.Intents.all()

bot = PhoinixBot(intents=intents)
# Maps User ID (Discord) -> (Token, Character ID (FFXIV))
verification_map = {}  # type: Dict[int, Tuple[str, int]]


@bot.slash_command(
    description=(
        "Verifies that you have cleared DRS/BA via the Lodestone. Ensure your"
        " acheivements are public."
    )
)
@discord.option(
    "char_id",
    description=f"EX: {LODESTONE_BASE_URL}12345678/ would input 12345678",
)
async def verifycharacter(ctx: discord.ApplicationContext, char_id: int):
    if verification_map.get(ctx.author.id, None) is not None:
        token, _ = verification_map[ctx.author.id]
        await ctx.send_response(
            f"Add {token} to your Character Profile at"
            f" {LODESTONE_BASE_URL}{char_id}/\nThen use the /verify command. Make sure"
            " your acheivements are public!",
            ephemeral=True,
        )
    else:
        token = secrets.token_urlsafe(8)
        verification_map[ctx.author.id] = (token, char_id)
        await ctx.send_response(
            f"Add {token} to your Character Profile at"
            f" {LODESTONE_BASE_URL}{char_id}/\nThen use the /verify command. Make sure"
            " your acheivements are public!",
            ephemeral=True,
        )


@bot.slash_command(
    description=(
        "Verifies that you have cleared DRS/BA via the Lodestone. Use after verifying"
        " with an id."
    )
)
async def verify(ctx: discord.ApplicationContext):
    if verification_map.get(ctx.author.id, None) is not None:
        token, cid = verification_map[ctx.author.id]
        profile = bs4.BeautifulSoup(
            requests.get(f"{LODESTONE_BASE_URL}{cid}").content.decode(), "html.parser"
        ).find_all("div", "character__selfintroduction")[
            0
        ]  # type: bs4.element.Tag

        if token in str(profile.string):
            ACHIEVEMENT_BASE_URL = f"{LODESTONE_BASE_URL}{cid}{LODESTONE_ACHIEVEMENT_BASE_URL}"
            await ctx.defer(ephemeral=True)
            drs_req = requests.get(
                f"{ACHIEVEMENT_BASE_URL}{ACHIEVEMENT_ID_MAP['DRS Clear']}/"
            )
            if drs_req.status_code == 404:
                await ctx.send_followup(
                    "Your achievements are not set to public! Set them to public then"
                    " run /verify again!",
                    ephemeral=True,
                )
                return

            cleared_drs = (
                len(
                    bs4.BeautifulSoup(drs_req.content.decode(), "html.parser").find_all(
                        "div",
                        "entry__achievement__view entry__achievement__view--complete",
                    )
                )
                > 0
            )

            ba_req = requests.get(
                f"{ACHIEVEMENT_BASE_URL}{ACHIEVEMENT_ID_MAP['BA Clear']}/"
            )

            cleared_ba = (
                len(
                    bs4.BeautifulSoup(ba_req.content.decode(), "html.parser").find_all(
                        "div",
                        "entry__achievement__view entry__achievement__view--complete",
                    )
                )
                > 0
            )

            if cleared_drs or cleared_ba:
                try:
                    member = await bot.PEBE.fetch_member(ctx.author.id)

                    roles_to_add = []
                    if cleared_ba:
                        roles_to_add.append(discord.Object(ROLE_ID_MAP["Cleared BA"]))
                    if cleared_drs:
                        roles_to_add.append(discord.Object(ROLE_ID_MAP["Cleared DRS"]))

                    await member.add_roles(*roles_to_add, reason="Verified clear")

                    await ctx.send_followup("Roles added!", ephemeral=True)

                except discord.NotFound:
                    await ctx.send_followup(
                        "Something went wrong. @( ﾟヮﾟ)#1052", ephemeral=True
                    )
                except discord.HTTPException:
                    await ctx.send_followup(
                        "Something went wrong. @( ﾟヮﾟ)#1052", ephemeral=True
                    )
            else:
                await ctx.send_followup(
                    "No roles to add. Go clear DRS or BA then verify again!",
                    ephemeral=True,
                )
        else:
            await ctx.send_response(
                f"Could not find {token} in your character profile. Make sure it is"
                " there, then try again.",
                ephemeral=True,
            )
    else:
        await ctx.send_response(
            "First, find your character on the Lodestone. The link will look something"
            f" like: {LODESTONE_BASE_URL}12345678/\nCopy the 8 digits at the end of the"
            " URL, and use /verifycharacter NUMBERS\nIt will provide you with some"
            " text to put in your Character Profile.\nAfter doing that, make sure your"
            " acheivements are public, and then call /verify again.",
            ephemeral=True,
        )


with open("token", "r") as token:
    bot.run(token.read())
