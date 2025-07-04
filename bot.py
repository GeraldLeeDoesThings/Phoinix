from datetime import timezone

import globals

import asyncio
import ba_recruiting
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
from urllib.parse import urlparse, urlunparse
from verification import *


def known_discord_id(id: int) -> bool:
    return globals.verification_map.get(id, None) is not None


def get_user_token(id: int) -> str:
    if known_discord_id(id):
        return globals.verification_map[id]["token"]
    else:
        return secrets.token_urlsafe(8)


def get_user_ffxiv_id(id: int) -> Optional[int]:
    if known_discord_id(id):
        return globals.verification_map[id]["id"]
    return None


def get_user_ffxiv_name_server(id: int) -> Optional[Tuple[str, str]]:
    if known_discord_id(id):
        maybe_name = globals.verification_map[id]["name"]
        if maybe_name is None:
            name, server = extract_name_server(globals.verification_map[id]["id"])
            globals.verification_map[id]["name"] = name
            globals.verification_map[id]["server"] = server
            return name, server
        else:
            return (
                globals.verification_map[id]["name"],
                globals.verification_map[id]["server"],
            )
    return None


async def register_user(did: int, name: str, server: str) -> bool:
    search = lodestone_search(name, server)
    if search is None:
        return False
    search["valid"] = False
    search["token"] = get_user_token(did)
    globals.verification_map[did] = search
    return True


async def force_register_user(did: int, fid: int, name: str, server: str):
    globals.verification_map[did] = {
        "id": fid,
        "name": name,
        "server": server,
        "valid": False,
        "token": get_user_token(did),
    }


@delayed(delay_secs=3600)
async def backup_dbs():
    while True:
        with open("data/verification_map.json", "w") as dumpfile:
            json.dump(globals.verification_map, dumpfile, indent=4)
        with open("data/ba_run_post_map.json", "w") as dumpfile:
            to_save = {}
            for key in globals.ba_run_post_map.keys():
                to_save[str(key)] = globals.ba_run_post_map[key].to_dict()
            json.dump(to_save, dumpfile, indent=4)

        await asyncio.sleep(3600)


class PhoinixBot(discord.Bot):
    def __init__(self, *, intents: discord.Intents, **options: Any):
        self.PEBE = None  # type: discord.Guild
        self.target_channel_id = None
        self.target_dm_id = None
        # Maps Message ID -> (Emoji -> Role ID)
        self.reaction_bindings = {}  # type: Dict[int, Dict[discord.PartialEmoji, int]]
        # Maps Guide Name -> (Index -> Message Template)
        self.guide_bindings = {}  # type: Dict[str, Dict[int, discord.Message]]
        self.guide_lock = asyncio.Lock()
        # Maps Message ID -> Moderation Function Event
        self.moderated_messages = {}  # type: Dict[int, asyncio.Event]
        self.first_ready = True
        self.debounce_deletion_notifications = True
        super().__init__(intents=intents, **options)

    async def moderate_message(
        self,
        message: discord.Message,
        check_signal: asyncio.Event,
        default_lifetime: Optional[datetime.timedelta] = None,
        minimum_lifetime: Optional[datetime.timedelta] = None,
        notification_time: Optional[datetime.timedelta] = None,
        do_notifications: bool = True,
    ):
        if default_lifetime is None:
            default_lifetime = DEFAULT_MESSAGE_LIFETIME
        if minimum_lifetime is None:
            minimum_lifetime = MIN_MESSAGE_LIFETIME
        if notification_time is None:
            notification_time = minimum_lifetime

        await message.remove_reaction(DELETING_SOON_EMOJI, self.user)
        await message.add_reaction(MONITORING_EMOJI)
        notified = False
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
            elif (expiration_time - now) < notification_time:
                # Not quite time to delete the message, but less than a day away. Mark the message.
                await message.add_reaction(DELETING_SOON_EMOJI)
                author = message.author  # type: discord.Member
                if not notified:
                    dm_channel = author.dm_channel  # type: Optional[discord.DMChannel]
                    if dm_channel is None:
                        dm_channel = await author.create_dm()
                    try:
                        if (
                            do_notifications
                            and not self.debounce_deletion_notifications
                        ):
                            await dm_channel.send(
                                f"Your message {message.jump_url} will be deleted in"
                                f" {generate_hammertime_timestamp(expiration_time)} unless"
                                f" you react with {DO_NOT_DELETE_EMOJI}\nPlease only"
                                " react if the message should not be deleted."
                            )
                        notified = True
                    except:
                        pass
                schedule_task(
                    trigger_later(check_signal, (expiration_time - now).total_seconds())
                )
                await wait_and_clear(check_signal)
            else:
                # More than a day away, schedule a check for just under a day away from the expiration time
                notified = False
                await message.add_reaction(MONITORING_EMOJI)
                schedule_task(
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

    async def validate_message_tags(self, m: discord.Message, role_ids: Set[int]):
        member = await self.PEBE.fetch_member(m.author.id)
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
            roles = "\n".join(self.PEBE.get_role(role_id).name for role_id in role_ids)
            schedule_task(
                m.reply(
                    "Please ensure messages in this channel mention an appropriate"
                    f" role. Appropriate roles are:\n{roles}\nOtherwise, please talk in"
                    f" {self.PEBE.get_channel(CHANNEL_ID_MAP['general-offtopic']).mention} instead."
                    " Your message will be deleted in 30 seconds.",
                    delete_after=30,
                )
            )
            schedule_task(m.delete(delay=30))

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
        for guide in bindings.values():
            for img in guide.values():
                print(f"Guide URL {img.attachments[0].url}")
        async with self.guide_lock:
            self.guide_bindings = bindings

    async def delete_untagged_messages(self):
        ba = self.get_channel(CHANNEL_ID_MAP["ba-recruiting"])
        drs = self.get_channel(CHANNEL_ID_MAP["drs-recruiting"])
        drs_oce = self.get_channel(CHANNEL_ID_MAP["drs-oce-recruiting"])

        ba_messages = ba.history(limit=100, after=GRACE_TIME)
        drs_messages = drs.history(limit=100, after=GRACE_TIME)
        drs_oce_messages = drs_oce.history(limit=100, after=GRACE_TIME)

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

        async for message in drs_oce_messages:
            # You know the drill
            m = message  # type: discord.Message
            await validate_message_tags(
                m,
                await self.fetch_member(m.author.id),
                [ROLE_ID_MAP["DRS Learning"], ROLE_ID_MAP["DRS Reclear"]],
            )

    @delayed(delay_secs=30)
    def unset_deletion_notification_debounce(self):
        self.debounce_deletion_notifications = False

    async def on_ready(self):
        print("Nya")
        self.PEBE = self.get_guild(1028110201968132116)
        print(self.PEBE)
        await self.delete_untagged_messages()
        await self.compute_reaction_bindings()
        await self.compute_guide_bindings()
        if self.first_ready:
            load_verification_map()
            load_ba_run_map(self)
            print("Adding verification view")
            self.add_view(VerificationView(bot))
            for key in globals.ba_run_post_map.keys():
                run = globals.ba_run_post_map[key]
                self.add_view(
                    ba_recruiting.BARunView(run), message_id=run.roster_embed_id
                )
            schedule_task(refresh_calls_loop())
            for moderated_channel_id in MODERATED_CHANNEL_IDS:
                channel = self.get_channel(
                    moderated_channel_id
                )  # type: discord.TextChannel
                if channel is None:
                    print(
                        f"Failed to fetch history for channel with id: {moderated_channel_id}"
                    )
                    continue
                async for moderated_message in channel.history(after=GRACE_TIME):
                    if moderated_message.author.id != self.user.id:
                        listener_event = asyncio.Event()
                        self.moderated_messages[moderated_message.id] = listener_event
                        schedule_task(
                            self.moderate_message(
                                moderated_message,
                                listener_event,
                                default_lifetime=LIFETIME_MAP.get(
                                    moderated_channel_id, DEFAULT_MESSAGE_LIFETIME
                                ),
                                do_notifications=DO_NOTIFICATIONS_MAP.get(
                                    moderated_channel_id, True
                                ),
                            )
                        )
            self.first_ready = False
            schedule_task(self.unset_deletion_notification_debounce())
            schedule_task(backup_dbs())

    async def handle_fills_channel_message(self, message: discord.Message):
        member = await self.PEBE.fetch_member(message.author.id)
        if member is None:
            print(f"Bad member ID: {message.author.id}")
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

        if ROLE_ID_MAP["FT Fills"] not in map(lambda role: role.id, message.role_mentions):
            await message.delete(reason="Incorrect ping")
        elif datetime.datetime.now(timezone.utc) - message.created_at >= datetime.timedelta(hours=1):
            await message.delete(reason="Message too old")
        else:
            await message.delete(delay=datetime.timedelta(hours=1).total_seconds(), reason="Message too old")

    async def on_message(self, message: discord.Message):
        id = message.channel.id
        if id in REQUIRED_TAGS_MAP:
            await self.validate_message_tags(message, REQUIRED_TAGS_MAP[id])

        if id == CHANNEL_ID_MAP["command"]:
            await self.parse_console_command(message.content)
        elif id == CHANNEL_ID_MAP["roles"]:
            await self.compute_reaction_bindings()
        elif id == 975557259893555271:
            print(message.content)
        elif id == CHANNEL_ID_MAP["na-drs-schedule"]:
            print("Received schedule: ", message.content)
            for embed in message.embeds:
                if "lego steppers" in embed.title.lower():
                    print("Deleting schedule...")
                    schedule_task(message.delete(reason="Not a foray server"))
        elif id == CHANNEL_ID_MAP["ft-fills"]:
            await self.handle_fills_channel_message(message)

        if id in MODERATED_CHANNEL_IDS and message.author.id != self.user.id:
            listener_event = asyncio.Event()
            self.moderated_messages[message.id] = listener_event
            schedule_task(
                self.moderate_message(
                    message,
                    listener_event,
                    default_lifetime=LIFETIME_MAP.get(id, DEFAULT_MESSAGE_LIFETIME),
                    do_notifications=DO_NOTIFICATIONS_MAP.get(id, True),
                )
            )

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

        if (
            payload.channel_id in BA_RECRUITING_CHANNELS
            and payload.message_id in globals.ba_run_post_map
        ):
            chan = self.get_channel(payload.channel_id)  # type: discord.TextChannel
            msg = await chan.fetch_message(payload.message_id)
            run = globals.ba_run_post_map[payload.message_id]
            newtimestamps = extract_hammertime_timestamps(msg.content)
            if len(newtimestamps) > 0:
                run.run_time = max(newtimestamps)
                run.signal.set()

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

        if (
            payload.channel_id in BA_RECRUITING_CHANNELS
            and payload.message_id in globals.ba_run_post_map
        ):
            del globals.ba_run_post_map[payload.message_id]

    async def fix_name(self, member: discord.Member):
        nspair = get_user_ffxiv_name_server(member.id)
        if nspair is not None:
            name, _ = nspair
            first, _ = name.split(" ")  # type: str
            mname = member.display_name
            if mname.startswith(first) or mname.lower().startswith(first.lower()[:3]):
                print(f"Skipping name fix for {mname} with first {first}")
                return
            await member.edit(nick=nspair[:32])

    async def parse_console_command(self, command):
        if command.startswith("send"):
            await self.impersonate(self.target_channel_id, command[5:])
        elif command.startswith("join"):
            try:
                self.target_channel_id = int(command[5:])
            except:
                pass
        elif command.startswith("save"):
            with open("data/verification_map.json", "w") as dumpfile:
                json.dump(globals.verification_map, dumpfile, indent=4)
            with open("data/ba_run_post_map.json", "w") as dumpfile:
                to_save = {}
                for key in globals.ba_run_post_map.keys():
                    to_save[str(key)] = globals.ba_run_post_map[key].to_dict()
                json.dump(to_save, dumpfile, indent=4)
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
                try:
                    await self.fix_name(member)
                except discord.Forbidden:
                    print(
                        f"Could not update {member.display_name}, ask them to fix it"
                        " themself!"
                    )
        elif command.startswith("purge"):
            for member in self.PEBE.members:
                if any(role.id == ROLE_ID_MAP["Not Verified"] for role in member.roles):
                    try:
                        await member.edit(roles=[])
                    except discord.Forbidden:
                        print(f"Tried to purge {member.display_name} but couldn't")
        elif command.startswith("target"):
            try:
                self.target_dm_id = int(command[7:])
            except:
                pass
        elif command.startswith("dm"):
            await self.dm_impersonate(self.target_dm_id, command[3:])

    async def impersonate(self, channel_id, message):
        maybe_channel = self.get_channel(channel_id)
        if maybe_channel is not None:
            await maybe_channel.send(message)

    async def dm_impersonate(self, dm_target_id, message):
        maybe_channel = await self.get_or_fetch_user(
            dm_target_id
        )  # type: Optional[discord.User]
        if maybe_channel is not None:
            await maybe_channel.send(message)


intents = discord.Intents.all()

bot = PhoinixBot(intents=intents)


@bot.slash_command()
async def summonverify(ctx: discord.ApplicationContext):
    if ctx.author.id == 172451187264716800:
        await ctx.channel.send(view=VerificationView(bot))
        await ctx.send_response("Nya :3", ephemeral=True)
    else:
        await ctx.send_response("Only Lerald can run this.", ephemeral=True)


@bot.user_command(name="Get Name/Server", default_member_permissions=discord.Permissions(kick_members=True))
async def whois_user_command(ctx: discord.ApplicationContext, member: discord.Member):
    if known_discord_id(member.id):
        warning = (
            ""
            if globals.verification_map[member.id]["valid"]
            else "WARNING [POTENTIALLY INVALID NAME]: "
        )
        name, server = get_user_ffxiv_name_server(member.id)
        await ctx.response.send_message(f"{warning}{name} @ {server}", ephemeral=True)
    else:
        await ctx.response.send_message("That user is not registered.", ephemeral=True)


@bot.message_command(name="Register as BA Recruiting Post")
async def register_ba_recruiting(
    ctx: discord.ApplicationContext, message: discord.Message
):
    if message.channel.id in BA_RECRUITING_CHANNELS:
        author = message.author  # type: discord.Member
        if message.author.id == ctx.author.id:
            timestamps = extract_hammertime_timestamps(message.content)
            if len(timestamps) == 0:
                await ctx.response.send_message(
                    "Message must have a timestamp, such as one generated from"
                    f" {HAMMERTIME_TIMESTAMP_URL} to be registered as a run.",
                    ephemeral=True,
                )
                return
            elif message.id in globals.ba_run_post_map:
                await ctx.response.send_message(
                    f"That message is already registered as a BA run!", ephemeral=True
                )
                return
            else:
                await ctx.response.send_message("Working...", ephemeral=True)
                roster_message = await message.channel.send(
                    "Building Roster Message...", reference=message.to_reference()
                )

                run = ba_recruiting.BARun(
                    id=message.id,
                    channel_id=message.channel.id,
                    bot=bot,
                    roster_embed_id=roster_message.id,
                    host=globals.verification_map[author.id]["name"],
                    host_id=message.author.id,
                    icon=author.display_avatar.url,
                    password=None,
                    run_time=max(timestamps),
                )

                globals.ba_run_post_map[message.id] = run
                view = ba_recruiting.BARunView(run)
                await roster_message.edit(content="", view=view)
                bot.add_view(view=view, message_id=roster_message.id)
                await run.update_embed()
                await ctx.send_followup("Done!", ephemeral=True)
        else:
            await ctx.response.send_message(
                "Only the author of a message can designate it a recruiting post.",
                ephemeral=True,
            )
    else:
        await ctx.response.send_message(
            "You cannot recruit for BA in this channel.", ephemeral=True
        )


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
    for did in globals.verification_map:
        warning = (
            ""
            if globals.verification_map[did]["valid"]
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
            guide_seq = [
                bot.guide_bindings[name][index].attachments[0].url
                for index in sorted(bot.guide_bindings[name].keys())
            ]

            def build_embed(url: str) -> discord.Embed:
                url = urlunparse(urlparse(url)._replace(query=None))
                print(f"Building embed with url: {url}")
                embed = discord.Embed(url=url)
                embed.set_image(url=url)
                return embed

            for index in range(0, len(guide_seq), 10):
                embeds = [build_embed(url) for url in guide_seq[index : index + 10]]
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


@bot.slash_command(
    description="Registers a user for them",
)
async def forceregister(
    ctx: discord.ApplicationContext,
    user: discord.User,
    ffxiv_id: int,
    ffxiv_name: str,
    ffxiv_server: str,
):
    author = ctx.author  # type: discord.Member
    if ROLE_ID_MAP["Admin"] in set(role.id for role in author.roles):
        await force_register_user(user.id, ffxiv_id, ffxiv_name, ffxiv_server)
        await ctx.respond("Done!", ephemeral=True)
    else:
        await ctx.respond("You must be an admin to use this command.", ephemeral=True)


@bot.slash_command(
    description="Lists some info about the internal state of the bot",
)
async def botinfo(
    ctx: discord.ApplicationContext,
):
    author = ctx.author  # type: discord.Member
    if ROLE_ID_MAP["Admin"] in set(role.id for role in author.roles):
        await ctx.respond(
            f"There are {len(asyncio.all_tasks())} running.\nThere are {len(globals.verification_map)} users registered.\n",
            ephemeral=True,
        )
    else:
        await ctx.respond("You must be an admin to use this command.", ephemeral=True)


if __name__ == "__main__":
    with open("secrets/token", "r") as token:
        bot.run(token.read())
