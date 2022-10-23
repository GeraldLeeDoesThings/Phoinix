import asyncio
import bs4
from const import *
import datetime
import discord
import json
import re
import requests
import secrets
import threading
from typing import *
from utils import *

# Maps User ID (Discord) -> (Token, Character ID (FFXIV))
verification_map = {}  # type: Dict[int, Dict[str, Union[bool, int, str]]]


def known_discord_id(id: int) -> bool:
    return verification_map.get(id, None) is not None


def get_user_token(id: int) -> str:
    if known_discord_id(id):
        return verification_map[id]["token"]
    else:
        return secrets.token_urlsafe(8)


def get_user_ffxiv_id(id: int) -> Optional[int]:
    if known_discord_id(id):
        return verification_map[id]["id"]
    return None


def get_user_ffxiv_name_server(id: int) -> Optional[Tuple[str, str]]:
    if known_discord_id(id):
        maybe_name = verification_map[id]["name"]
        if maybe_name is None:
            name, server = extract_name_server(verification_map[id]["id"])
            verification_map[id]["name"] = name
            verification_map[id]["server"] = server
            return name, server
        else:
            return verification_map[id]["name"], verification_map[id]["server"]
    return None


def register_user(did: int, name: str, server: str) -> bool:
    search = lodestone_search(name, server)
    if search is None:
        return False
    search["valid"] = False
    search["token"] = get_user_token(did)
    verification_map[did] = search
    return True


class PhoinixBot(discord.Bot):
    def __init__(self, *, intents: discord.Intents, **options: Any):
        self.PEBE = None  # type: discord.Guild
        self.target_channel_id = None
        # Maps Message ID -> (Emoji -> Role ID)
        self.reaction_bindings = (
            {}
        )  # type: Mapping[int, Mapping[discord.PartialEmoji, int]]
        self.verification_view_added = False
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
        message_sets = [
            self.PEBE.get_channel(CHANNEL_ID_MAP["roles"]).history(),
            self.PEBE.get_channel(CHANNEL_ID_MAP["rules"]).history(),
        ]
        self.reaction_bindings = {}
        for messages in message_sets:
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
                        "Whoever posted the role react message is gone! Someone"
                        " repost it!"
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
        if not self.verification_view_added:
            print("Adding verification view")
            self.add_view(VerificationView())
            self.verification_view_added = True
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
        elif id == 975557259893555271:
            print(message.content)

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
        elif command.startswith("save"):
            with open("verification_map.json", "w") as dumpfile:
                json.dump(verification_map, dumpfile, indent=4)

    async def impersonate(self, channel_id, message):
        maybe_channel = self.get_channel(channel_id)
        if maybe_channel is not None:
            await maybe_channel.send(message)


class VerificationModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Register Character Data")

        self.add_item(discord.ui.InputText(label="Full Character Name"))
        self.add_item(discord.ui.InputText(label="Character Server"))

    async def callback(self, interaction: discord.Interaction):
        name = self.children[0].value
        server = self.children[1].value.split(" ")[0]
        fakedefer = await interaction.response.send_message(
            "Searching...", ephemeral=True
        )  # type: discord.Interaction
        if register_user(
            interaction.user.id,
            name,
            server,
        ):
            await fakedefer.edit_original_response(
                content=(
                    f"Character found! Add `{get_user_token(interaction.user.id)}` to"
                    " your character profile on the Lodestone, then click the Verify"
                    " button. Your character profile can be found here:"
                    " https://na.finalfantasyxiv.com/lodestone/my/setting/profile/"
                ),
            )
            return
        await fakedefer.edit_original_response(
            content=(
                f"Could not find character with:\nName: {name}\nServer:"
                f" {server}\n\nEnsure that the name and server are correct. Name should"
                " be first and last (ex Lerald Gee), and server should only include"
                " the server (ex Famfrit)."
            ),
        )


class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Register", custom_id="register", style=discord.ButtonStyle.primary
    )
    async def register(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.send_modal(VerificationModal())

    @discord.ui.button(
        label="Verify", custom_id="verify", style=discord.ButtonStyle.primary
    )
    async def verify(self, button: discord.ui.Button, interaction: discord.Interaction):
        response = await interaction.response.send_message(
            "Verifying...", ephemeral=True
        )  # type: discord.Interaction
        if not known_discord_id(interaction.user.id):
            await response.edit_original_response(
                content=(
                    "You must register first! Click the Register button and follow the"
                    " instructions."
                ),
            )
            return
        if verification_map[interaction.user.id]["valid"]:
            await response.edit_original_response(content="You are already verified!")
            return
        result = full_validate(verification_map[interaction.user.id])
        if type(result) == str:
            await response.edit_original_response(content=result)
        else:
            try:
                member = await bot.fetch_member(interaction.user.id)
                await member.add_roles(discord.Object(ROLE_ID_MAP["Member"]))
                verification_map[interaction.user.id] = result
                await response.edit_original_response(content="Successfully verified!")
            except discord.HTTPException:
                print("Adding role failed!")
                await response.edit_original_response(
                    content=(
                        "Something has gone wrong (not your fault). Click the Verify"
                        " button again, and if errors continue, contact the staff."
                    )
                )

    @discord.ui.button(
        label="Verify BA Clear",
        custom_id="verify_ba",
        style=discord.ButtonStyle.primary,
    )
    async def verify_ba_clear(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await self.verify_achievement(
            button,
            interaction,
            ACHIEVEMENT_ID_MAP["BA Clear"],
            ROLE_ID_MAP["Cleared BA"],
        )

    @discord.ui.button(
        label="Verify DRS Clear",
        custom_id="verify_drs",
        style=discord.ButtonStyle.primary,
    )
    async def verify_drs_clear(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await self.verify_achievement(
            button,
            interaction,
            ACHIEVEMENT_ID_MAP["DRS Clear"],
            ROLE_ID_MAP["Cleared DRS"],
        )

    async def verify_achievement(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
        id: int,
        role: int,
    ):
        if not known_discord_id(interaction.user.id):
            await interaction.response.send_message(
                "You are not registered! Click the Register button, follow the"
                " instructions, then click the Verify button, then try this button"
                " again.",
                ephemeral=True,
            )
        elif not verification_map[interaction.user.id]["valid"]:
            await interaction.response.send_message(
                "You are not verified! Click the Verify button, then try this button"
                " again.",
                ephemeral=True,
            )
        else:
            response = await interaction.response.send_message(
                "Checking achievements...", ephemeral=True
            )  # type: discord.Interaction
            has = user_has_achievement(get_user_ffxiv_id(interaction.user.id), id)
            if has is None:
                await response.edit_original_response(
                    content=(
                        "Your achievements are not public! Set them to public, then try"
                        " again."
                    )
                )
            elif has:
                try:
                    member = await bot.fetch_member(interaction.user.id)
                    await member.add_roles(discord.Object(role))
                    await response.edit_original_response(
                        content="Role successfully added!"
                    )
                except discord.HTTPException:
                    print("Adding role failed!")
                    await response.edit_original_response(
                        content=(
                            "Something has gone wrong (not your fault). Click the"
                            " Verify button again, and if errors continue, contact"
                            " the staff."
                        )
                    )
            else:
                await response.edit_original_response(
                    content=(
                        "You do not have an achievement indicating that you have"
                        " cleared!"
                    )
                )


intents = discord.Intents.all()

bot = PhoinixBot(intents=intents)


@bot.slash_command()
async def summonverify(ctx: discord.ApplicationContext):
    if ctx.author.id == 172451187264716800:
        await ctx.channel.send(view=VerificationView())
        await ctx.send_response("Nya :3", ephemeral=True)
    else:
        await ctx.send_response("Only Lerald can run this.", ephemeral=True)


update_verification_map()
with open("verification_map.json", "r") as loadfile:
    str_verification_map = json.load(
        loadfile
    )  # type: Dict[str, Dict[str, Union[bool, int, str]]]
    for key in str_verification_map.keys():
        verification_map[int(key)] = str_verification_map[key]

with open("token", "r") as token:
    bot.run(token.read())
