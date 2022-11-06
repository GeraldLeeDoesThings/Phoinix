import asyncio
import bs4
from const import *
import datetime
import discord
import json
import os
import re
import requests
import secrets
import threading
from typing import *
from utils import *
import uuid

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


async def register_user(did: int, name: str, server: str) -> bool:
    search = await lodestone_search(name, server)
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
        self.reaction_bindings = {}  # type: Dict[int, Dict[discord.PartialEmoji, int]]
        # Maps Guide Name -> (Index -> Message Template)
        self.guide_bindings = {}  # type: Dict[str, Dict[int, discord.Message]]
        self.guide_lock = asyncio.Lock()
        # Maps Message ID -> Moderation Function Event
        self.moderated_messages = {}  # type: Dict[int, asyncio.Event]
        self.first_ready = True
        super().__init__(intents=intents, **options)

    async def moderate_message(
        self,
        message: discord.Message,
        check_signal: asyncio.Event,
        default_lifetime: Optional[datetime.timedelta] = None,
        minimum_lifetime: Optional[datetime.timedelta] = None,
    ):
        if default_lifetime is None:
            default_lifetime = DEFAULT_MESSAGE_LIFETIME
        if minimum_lifetime is None:
            minimum_lifetime = MIN_MESSAGE_LIFETIME
        await message.remove_reaction(DELETING_SOON_EMOJI, self.user)
        await message.add_reaction(MONITORING_EMOJI)
        while True:
            try:
                message = await message.channel.fetch_message(message.id)
            except discord.NotFound:
                # Message was deleted, stop moderating it
                return
            except discord.Forbidden:
                print(
                    "Bot Permissions are not set up correctly! Cannot access message"
                    f" in {message.channel.name} with message ID: {message.id} by"
                    f" {message.author.display_name}"
                )
            except discord.HTTPException:
                # Failed to connect, carry on and retry later
                pass
            marked_dnd = False
            for reaction in message.reactions:
                if reaction.emoji == DO_NOT_DELETE_EMOJI and message.author in [
                    user async for user in reaction.users()
                ]:
                    await message.remove_reaction(DELETING_SOON_EMOJI, self.user)
                    marked_dnd = True
                    break
            if marked_dnd:
                # The message is marked do not delete
                await wait_and_clear(check_signal)
                continue
            stamps = [
                stamp + minimum_lifetime
                for stamp in extract_hammertime_timestamps(message.content)
            ]
            now = datetime.datetime.now(datetime.timezone.utc)
            expiration_time = max(stamps + [message.created_at + default_lifetime])
            if now >= expiration_time:
                await message.delete()
            elif (expiration_time - now).days == 0:
                # Not quite time to delete the message, but less than a day away. Mark the message.
                await message.add_reaction(DELETING_SOON_EMOJI)
                author = message.author  # type: discord.Member
                dm_channel = author.dm_channel  # type: Optional[discord.DMChannel]
                if dm_channel is None:
                    dm_channel = await author.create_dm()
                try:
                    await dm_channel.send(
                        f"Your message {message.jump_url} will be deleted in"
                        f" {generate_hammertime_timestamp(expiration_time)} unless you"
                        f" react with {DO_NOT_DELETE_EMOJI}\n"
                        "Please only react if the message should not be deleted."
                    )
                except:
                    pass
                asyncio.create_task(
                    trigger_later(check_signal, (expiration_time - now).total_seconds())
                )
                await wait_and_clear(check_signal)
            else:
                # More than a day away, schedule a check for just under a day away from the expiration time
                await message.add_reaction(MONITORING_EMOJI)
                asyncio.create_task(
                    trigger_later(
                        check_signal,
                        (
                            expiration_time
                            - now
                            - minimum_lifetime
                            + datetime.timedelta(seconds=1)
                        ).total_seconds(),
                    )
                )
                await wait_and_clear(check_signal)

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

    async def compute_guide_bindings(self):
        guides = self.get_channel(CHANNEL_ID_MAP["guides"])  # type: discord.TextChannel
        guide_messages = guides.history()
        bindings = {}  # type: Dict[str, Dict[int, discord.Message]]

        async for message in guide_messages:
            message = message  # type: discord.Message
            firstline = message.content.split("\n")[0]
            form = re.match("(\S+)\s+(\d+)\s*", firstline)
            if form and len(message.attachments) > 0:
                name = form[1]
                seq = int(form[2])
                bindings[name] = bindings.get(name, {}) | {seq: message}
                for reaction in message.reactions:
                    if reaction.emoji == "❎" and reaction.me:
                        await message.remove_reaction(
                            "❎", await self.fetch_member(self.user.id)
                        )
                        break
            else:
                await message.add_reaction("❎")
        async with self.guide_lock:
            self.guide_bindings = bindings

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
        await self.compute_guide_bindings()
        if self.first_ready:
            print("Adding verification view")
            self.add_view(VerificationView())
            asyncio.create_task(refresh_calls_loop())
            for moderated_channel_id in MODERATED_CHANNEL_IDS:
                channel = self.get_channel(
                    moderated_channel_id
                )  # type: discord.TextChannel
                async for moderated_message in channel.history(after=GRACE_TIME):
                    listener_event = asyncio.Event()
                    self.moderated_messages[moderated_message.id] = listener_event
                    asyncio.create_task(
                        self.moderate_message(moderated_message, listener_event)
                    )
            self.first_ready = False

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

        if id in MODERATED_CHANNEL_IDS:
            listener_event = asyncio.Event()
            self.moderated_messages[message.id] = listener_event
            asyncio.create_task(self.moderate_message(message, listener_event))

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if payload.channel_id == CHANNEL_ID_MAP["roles"]:
            await self.compute_reaction_bindings()
        elif payload.channel_id == CHANNEL_ID_MAP["guides"]:
            await self.compute_guide_bindings()

        if (
            payload.channel_id in MODERATED_CHANNEL_IDS
            and payload.message_id in self.moderated_messages
        ):
            self.moderated_messages[payload.message_id].set()

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

        if (
            payload.channel_id in MODERATED_CHANNEL_IDS
            and payload.message_id in self.moderated_messages
        ):
            self.moderated_messages[payload.message_id].set()

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

        if (
            payload.channel_id in MODERATED_CHANNEL_IDS
            and payload.message_id in self.moderated_messages
        ):
            self.moderated_messages[payload.message_id].set()

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.channel_id == CHANNEL_ID_MAP["guides"]:
            await self.compute_guide_bindings()

        if (
            payload.channel_id in MODERATED_CHANNEL_IDS
            and payload.message_id in self.moderated_messages
        ):
            # This has to be done to clear the message moderation coroutine
            self.moderated_messages[payload.message_id].set()
            self.moderated_messages.pop(payload.message_id)

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.display_name != after.display_name:
            await self.fix_name(after)

    async def fix_name(self, member: discord.Member):
        nspair = get_user_ffxiv_name_server(member.id)
        if nspair is not None:
            name, _ = nspair
            first, last = name.split(" ")
            if not (
                first[:3] in member.display_name or last[:3] in member.display_name
            ):
                await member.edit(nick=f"{member.display_name[:26]} [{first[:3]}]")

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
        elif command.startswith("mark"):
            for member in self.PEBE.members:
                roles = [role.id for role in member.roles]
                if len(roles) == 2 and ROLE_ID_MAP["Not Verified"] in roles:
                    await member.remove_roles(
                        discord.Object(ROLE_ID_MAP["Not Verified"])
                    )
                elif (
                    len(roles) > 1
                    and ROLE_ID_MAP["Member"] not in roles
                    and ROLE_ID_MAP["Not Verified"] not in roles
                ):
                    await member.add_roles(discord.Object(ROLE_ID_MAP["Not Verified"]))
        elif command.startswith("shutdown"):
            exit(0)
        elif command.startswith("fixnames"):
            for member in self.PEBE.members:
                await self.fix_name(member)
        elif command.startswith("purge"):
            for member in self.PEBE.members:
                if any(role.id == ROLE_ID_MAP["Not Verified"] for role in member.roles):
                    try:
                        await member.edit(roles=[])
                    except discord.Forbidden:
                        print(f"Tried to purge {member.display_name} but couldn't")

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
        if await register_user(
            interaction.user.id,
            name,
            server,
        ):
            await fakedefer.edit_original_response(
                content=(
                    f"Character found! Add `{get_user_token(interaction.user.id)}` to"
                    " your character profile on the Lodestone, then click the Verify"
                    " button. If you cannot copy your token, try copying from"
                    f" {ECHO_TOKEN_URL}{get_user_token(interaction.user.id)}\nYour"
                    " character profile can be found here:"
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
                if ROLE_ID_MAP["Not Verified"] in [role.id for role in member.roles]:
                    await member.remove_roles(
                        discord.Object(ROLE_ID_MAP["Not Verified"])
                    )
                verification_map[interaction.user.id] = result
                await bot.fix_name(member)
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


@bot.user_command(name="Get Name/Server")
async def whois_user_command(ctx: discord.ApplicationContext, member: discord.Member):
    if known_discord_id(member.id):
        warning = (
            ""
            if verification_map[member.id]["valid"]
            else "WARNING [POTENTIALLY INVALID NAME]: "
        )
        name, server = get_user_ffxiv_name_server(member.id)
        await ctx.response.send_message(f"{warning}{name} @ {server}", ephemeral=True)
    else:
        await ctx.response.send_message("That user is not registered.", ephemeral=True)


@bot.slash_command(
    description="Searches for a user given an in game name and optionally a server"
)
async def search(
    ctx: discord.ApplicationContext, name_regex: str, server: Optional[str] = None
):
    try:
        regex = re.compile(name_regex)
    except re.error:
        await ctx.response.send_message("Bad Regex", ephemeral=True)
        return
    finds = []  # type: List[Tuple[str, str, discord.Member]]
    await ctx.response.defer(ephemeral=True)
    foundcount = 0
    for did in verification_map:
        warning = (
            ""
            if verification_map[did]["valid"]
            else "WARNING [POTENTIALLY INVALID NAME]: "
        )
        if foundcount == MAX_SEARCH_VALUES:
            break
        name, fserver = get_user_ffxiv_name_server(did)
        if regex.search(name) is not None and (server is None or server in fserver):
            fmember = await bot.fetch_member(did)
            if fmember:
                finds.append((warning + name, fserver, fmember))
                foundcount += 1
    if len(finds) == 0:
        await ctx.send_followup("Did not find anyone.", ephemeral=True)
    else:
        foundstring = "Found the following users:\n" + "\n".join(
            f"{fname} @ {fserver} {mem.mention}" for fname, fserver, mem in finds
        )
        if len(foundstring) > 1985:
            foundstring = foundstring[:1985] + "\nand more..."
        await ctx.send_followup(foundstring, ephemeral=True)


@bot.slash_command(
    description="Registers an image to show up in response to the guide command"
)
async def register(
    ctx: discord.ApplicationContext,
    name: str,
    image: discord.Attachment,
    position: int = 0,
):
    member = await bot.fetch_member(ctx.author.id)
    if member is None:
        await ctx.response.send_message("Bwo you are not even in PEBE", ephemeral=True)
    elif (
        member.get_role(ROLE_ID_MAP["BA Lead"])
        or member.get_role(ROLE_ID_MAP["DRS Lead"])
        or member.get_role(ROLE_ID_MAP["Moderator"])
        or member.get_role(ROLE_ID_MAP["Admin"])
    ):
        if re.match("\S+", name):
            name = name.lower()
            await ctx.defer(ephemeral=True)
            async with bot.guide_lock:
                if name in bot.guide_bindings:
                    if position in bot.guide_bindings[name]:
                        achan = bot.get_channel(
                            CHANNEL_ID_MAP["guides-archive"]
                        )  # type: discord.TextChannel
                        await achan.send(
                            file=await bot.guide_bindings[name][position]
                            .attachments[0]
                            .to_file()
                        )
                        await bot.guide_bindings[name][position].delete()
                gchan = bot.get_channel(
                    CHANNEL_ID_MAP["guides"]
                )  # type: discord.TextChannel
                await gchan.send(f"{name} {position}", file=await image.to_file())
            await ctx.send_followup("Done!", ephemeral=True)
            await bot.compute_guide_bindings()
        else:
            await ctx.response.send_message(
                "Name must not contain spaces.", ephemeral=True
            )
    else:
        await ctx.response.send_message(
            "You must have a lead role to register guides.", ephemeral=True
        )


@bot.slash_command(
    description="Get a guide that has been registered with the register command"
)
async def guide(ctx: discord.ApplicationContext, name: str):
    name = name.lower()
    if "@" in name:
        await ctx.respond("SHAME UPON YOU")
        return
    if name in bot.guide_bindings:
        async with bot.guide_lock:
            first_response = True
            guide_seq = [bot.guide_bindings[name][index].attachments[0].url for index in sorted(bot.guide_bindings[name].keys())]
            def build_embed(url: str) -> discord.Embed:
                embed = discord.Embed(url=url)
                embed.set_image(url=url)
                return embed

            for index in range(0, len(guide_seq), 10):
                embeds = [build_embed(url) for url in guide_seq[index:index + 10]]
                if first_response:
                    await ctx.send_response(embeds=embeds)
                    first_response = False
                else:
                    await ctx.send_followup(embeds=embeds)
    else:
        await ctx.send_response(f"No guide exists with the name: {name}")


@bot.slash_command(
    description="Get a list of guides",
)
async def listguides(ctx: discord.ApplicationContext):
    async with bot.guide_lock:
        await ctx.respond(
            "List of guides:\n" + "\n".join(bot.guide_bindings), ephemeral=True
        )


update_verification_map()
with open("verification_map.json", "r") as loadfile:
    str_verification_map = json.load(
        loadfile
    )  # type: Dict[str, Dict[str, Union[bool, int, str]]]
    for key in str_verification_map.keys():
        verification_map[int(key)] = str_verification_map[key]

if __name__ == "__main__":
    with open("token", "r") as token:
        bot.run(token.read())
