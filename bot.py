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
        self.add_view(VerificationView())
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
        fakedefer = await interaction.response.send_message("Searching...", ephemeral=True)  # type: discord.Interaction
        if register_user(
            interaction.user.id,
            name,
            server,
        ):
            await fakedefer.response.edit_message(
                content=f"Character found! Add {get_user_token(interaction.user.id)} to your"
                " character profile, then click the Verify button.",
            )
            return
        await fakedefer.response.edit_message(
            content=f"Could not find character with:\nName: {name}\nServer: {server}\n\nEnsure"
            " that the name and server are correct. Name should be first and last (ex"
            " Lerald Gee), and server should only include the server (ex Famfrit).",
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
        if not known_discord_id(interaction.user.id):
            await interaction.response.send_message(
                "You must register first! Click the Register button and follow the"
                " instructions.",
                ephemeral=True,
            )
            return
        if verification_map[interaction.user.id]["valid"]:
            await interaction.response.send_message(
                "You are already verified!", ephemeral=True
            )
            return
        result = full_validate(verification_map[interaction.user.id])
        if type(result) == str:
            await interaction.response.send_message(result, ephemeral=True)
        else:
            try:
                member = await bot.fetch_member(interaction.user.id)
                await member.add_roles(discord.Object(ROLE_ID_MAP["Member"]))
                verification_map[interaction.user.id] = result
                await interaction.response.send_message(
                    "Successfully verified!", ephemeral=True
                )
            except discord.HTTPException:
                print("Adding role failed!")
                await interaction.response.send_message(
                    "Something has gone wrong (not your fault). Click the Verify button"
                    " again, and if errors continue, contact the staff.",
                    ephemeral=True,
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
            has = user_has_achievement(get_user_ffxiv_id(interaction.user.id), id)
            if has is None:
                await interaction.response.send_message(
                    "Your acheivements are not public! Set them to public, then try"
                    " again.",
                    ephemeral=True,
                )
            else:
                if has:
                    try:
                        member = await bot.fetch_member(interaction.user.id)
                        await member.add_roles(discord.Object(role))
                        await interaction.response.send_message(
                            "Role successfully added!", ephemeral=True
                        )
                    except discord.HTTPException:
                        print("Adding role failed!")
                        await interaction.response.send_message(
                            "Something has gone wrong (not your fault). Click the"
                            " Verify button again, and if errors continue, contact the"
                            " staff.",
                            ephemeral=True,
                        )
                else:
                    await interaction.response.send_message(
                        "You do not have an achievement indicating that you have"
                        " cleared!",
                        ephemeral=True,
                    )


intents = discord.Intents.all()

bot = PhoinixBot(intents=intents)


@bot.slash_command(
    description=(
        "Verifies that you have cleared DRS/BA via the Lodestone. Ensure your"
        " achievements are public."
    )
)
@discord.option(
    "char_id",
    description=f"EX: {LODESTONE_BASE_URL}12345678/ would input 12345678",
)
async def verifycharacter(ctx: discord.ApplicationContext, char_id: int):
    did = ctx.author.id
    if known_discord_id(did):
        token = get_user_token(did)
        cid = get_user_ffxiv_id(did)
        if cid == char_id:
            await ctx.send_response(
                f"Add {token} to your Character Profile at"
                " https://na.finalfantasyxiv.com/lodestone/my/setting/profile/\nThen"
                " use the /verify command. Make sure your achievements are public!",
                ephemeral=True,
            )
            return
    token = get_user_token(did)
    ext = extract_name_server(char_id)
    if ext is not None:
        name, server = ext
        verification_map[did] = {
            "name": name,
            "server": server,
            "valid": False,
            "id": char_id,
            "token": token,
        }
        await ctx.send_response(
            f"Add {token} to your Character Profile at"
            " https://na.finalfantasyxiv.com/lodestone/my/setting/profile/\nThen use"
            " the /verify command. Make sure your achievements are public!",
            ephemeral=True,
        )
    else:
        await ctx.send_response(f"Invalid character ID!", ephemeral=True)


async def add_user_roles_from_verification(did: int, cid: int) -> Tuple[bool, str]:
    cleared_drs = user_has_achievement(cid, ACHIEVEMENT_ID_MAP["DRS Clear"])

    if cleared_drs is None:
        return (
            False,
            (
                "Your achievements are not set to public! Set them to public, then try"
                " again!"
            ),
        )

    cleared_ba = user_has_achievement(cid, ACHIEVEMENT_ID_MAP["BA Clear"])

    if cleared_ba is None:
        # This will literally only ever happen if a user changes
        # their achievements to private between the two requests
        return (
            False,
            (
                "Your achievements are not set to public! Set them to public, then try"
                " again!"
            ),
        )

    try:
        member = await bot.PEBE.fetch_member(did)
        roles_to_add = [discord.Object(ROLE_ID_MAP["Member"])]
        if cleared_ba:
            roles_to_add.append(discord.Object(ROLE_ID_MAP["Cleared BA"]))
        if cleared_drs:
            roles_to_add.append(discord.Object(ROLE_ID_MAP["Cleared DRS"]))

        await member.add_roles(discord.Object(ROLE_ID_MAP["Member"]))
        verification_map[did]["valid"] = True
        return (
            True,
            "Verification complete!",
        )

    except discord.NotFound:
        return (False, "Something went wrong. @( ﾟヮﾟ)#1052")
    except discord.HTTPException:
        return (False, "Something went wrong. @( ﾟヮﾟ)#1052")


@bot.slash_command(
    description=(
        "Verifies that you have cleared DRS/BA via the Lodestone. Use after verifying"
        " with an id."
    )
)
async def verify(ctx: discord.ApplicationContext):
    did = ctx.author.id
    if known_discord_id(did):
        await ctx.defer(ephemeral=True)
        token = get_user_token(did)
        cid = get_user_ffxiv_id(did)
        try:
            token_present = user_has_token_in_profile(cid, token)
        except IndexError:
            await ctx.send_followup(
                f"Could not find a character profile at: {LODESTONE_BASE_URL}{cid}",
                ephemeral=True,
            )
            return
        if token_present:
            _, message = await add_user_roles_from_verification(ctx.author.id, cid)
            await ctx.send_followup(message, ephemeral=True)
        else:
            await ctx.send_followup(
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
            " achievements are public, and then call /verify again.",
            ephemeral=True,
        )


@bot.slash_command(
    description=(
        "Verifies that you own a FFXIV account, and additionally checks for clears."
        " Gives the member role."
    )
)
@discord.option(
    "name",
    description=f"Your FFXIV character's full name. Ex: Lerald Gee",
)
@discord.option(
    "server",
    description=f"Your FFXIV character's server name. Ex: Famfrit",
)
async def easyverify(ctx: discord.ApplicationContext, name: str, server: str):
    discord_id = ctx.author.id
    await ctx.defer(ephemeral=True)
    if known_discord_id(discord_id):
        saved_name, saved_server = get_user_ffxiv_name_server(discord_id)
        if saved_name == name and saved_server == server:
            # The user has not changed their name or server, so verify the presence of the token + achievements
            token = get_user_token(discord_id)
            fid = get_user_ffxiv_id(discord_id)
            has_token = user_has_token_in_profile(
                verification_map[discord_id]["id"],
                token,
            )
            if has_token:
                _, message = await add_user_roles_from_verification(discord_id, fid)
                await ctx.send_followup(message, ephemeral=True)
                return
            else:
                await ctx.send_followup(
                    f"Could not find your token, {token}, in your character profile"
                    f" page at {LODESTONE_BASE_URL}{fid}\nIf the link is wrong, check"
                    " the name and server you provided! If the link is correct, ensure"
                    " that the token is present. Copy pasting the entire token is the"
                    " safest way to do this, as some characters look extremely"
                    " similar.",
                    ephemeral=True,
                )
                return

    # Either this is an unverified user, or someone is verifying a different account
    try_find = lodestone_search(name, server)
    if try_find is not None:
        # Found that character on the Lodestone, create a new entry
        try_find["valid"] = False
        try_find["token"] = get_user_token(discord_id)
        verification_map[discord_id] = try_find
        await ctx.send_followup(
            f"Found your character! Add the following text {try_find['token']} to your"
            " character profile at"
            " https://na.finalfantasyxiv.com/lodestone/my/setting/profile/ then call"
            " this command again, EXACTLY as you did this time. DO NOT copy paste the"
            " command, as discord may not process it as a proper command.",
            ephemeral=True,
        )
    else:
        await ctx.send_followup(
            "Could not find that character! Make sure you are using your full name, and"
            " that you have entered it correctly!",
            ephemeral=True,
        )


@bot.slash_command()
async def summonverify(ctx: discord.ApplicationContext):
    if ctx.author.id == 172451187264716800:
        await ctx.channel.send(view=VerificationView())
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
