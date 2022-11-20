from __future__ import annotations

import asyncio
import bot
import globals
from utils import generate_button, schedule_task, wait_and_clear
from const import *
import discord
import itertools
from recruiting import *
import types
from typing import *


class BAGroup(Group):
    def __init__(
        self,
        run: BARun,
        members: List[Union[Dict[str, str], RunMember]],
        leader: Optional[Union[str, int]],
        index: int,
    ):
        super().__init__(members, leader, index)
        self.roles = self.count_roles()
        self.run = run

    def needs(self) -> List[str]:
        need = []
        if self.roles[BA_HEALER] == 0:
            need.append(BA_HEALER)
        if self.roles[BA_BLUE_DPS] + self.roles[BA_MAIN_TANK] == 0:
            need.extend(BA_ANY_TANK)
        return need

    def unreserved_space(self) -> int:
        return 8 - len(self.members) - len(self.needs())

    def add_member(self, member: RunMember):
        self.members.append(member)
        self.roles[member.role] = self.roles.get(member.role, 0) + 1

    def remove_member(self, member: Union[int, RunMember]):
        for i, existing in enumerate(self.members):
            if member == existing:
                self.roles[member.role] -= 1
                del self.members[i]
                break

    def can_add(self, role: str):
        return self.run.can_add(self.index, role)

    def get_index(self, member: Union[int, RunMember]) -> Optional[int]:
        for i, cmem in enumerate(self.members):
            if member == cmem:
                return i
        return None

    def __str__(self):
        return "\n".join(
            f"{BA_ROLE_EMOJI_MAPPING.get(member.role)}{f' {PARTY_LEAD_EMOJI}' if index == self.leader else ''}:"
            f" **{member.name}**"
            for index, member in enumerate(self.members)
        )

    def __contains__(self, item):
        for member in self.members:
            if member == item:
                return True
        return False

    def __iter__(self) -> Iterator[RunMember]:
        return iter(self.members)


class BARun:
    def __init__(
        self,
        id: Union[int, str],
        roster_embed_id: Union[int, str],
        host: str,
        host_id: int,
        icon: str,
        password: Optional[str],
        run_time: Union[datetime.datetime, str],
        groups: Optional[
            List[Dict[str, Union[int, Dict[str, Union[str, int]]]]]
        ] = None,
    ):
        self.id = int(id)
        self.roster_embed_id = int(roster_embed_id)
        self.groups = None if groups is None else [BAGroup(**group) for group in groups]
        self.embed = BAEmbedWrapper(host, icon)
        self.host = host
        self.host_id = host_id
        self.icon = icon
        self.password = password
        self.run_time = (
            datetime.datetime.fromisoformat(run_time)
            if type(run_time) is str
            else run_time
        )
        self.public = False
        self.signal = asyncio.Event()
        if self.groups is None:
            self.groups = [BAGroup(self, [], None, i) for i in range(7)]
        self.password_auto_publish_running = False
        schedule_task(self.password_auto_publish_loop())
        self.message = bot.bot.get_message(self.id)  # type: discord.Message
        self.roster_message = bot.bot.get_message(
            self.roster_embed_id
        )  # type: discord.Message

    def update_embed(self):
        for index, group in self.groups:
            if index < 6:
                self.embed.set_group_text(
                    index, f"Group {index + 1} [{len(group)}/8]", f"{group}"
                )
            else:
                self.embed.set_group_text(
                    index, f"Support Group [{len(group)}/5]", f"{group}"
                )
        self.roster_message.edit(embed=self.embed)

    def valid_single(self, index: int, role: str) -> bool:
        needs = self.groups[index].needs()
        return role in needs or self.groups[index].unreserved_space() > 0

    def pair_unreserved_space(self, index: int) -> int:
        given = self.groups[index]
        paired = self.groups[index + (-1 if index % 2 else 1)]

        return (
            given.unreserved_space()
            + paired.unreserved_space()
            - (given.roles[BA_MAIN_TANK] + paired.roles[BA_MAIN_TANK] == 0)
        )

    def valid_pair(self, index: int, role: str) -> bool:
        given = self.groups[index]
        paired = self.groups[index + (-1 if index % 2 else 1)]

        if (
            given.roles[BA_MAIN_TANK] + paired.roles[BA_MAIN_TANK] == 0
            and role == BA_MAIN_TANK
        ):
            return True
        return self.pair_unreserved_space(index) > 0

    def triple_unreserved_space(self, index: int) -> int:
        midl = self.groups[2]
        midr = self.groups[3]
        mid_burden = int(midl.roles[BA_MAIN_TANK] + midr.roles[BA_MAIN_TANK] == 0)
        if index <= 2:
            return self.pair_unreserved_space(0) + midl.unreserved_space() - mid_burden
        else:
            return self.pair_unreserved_space(3) + midr.unreserved_space() - mid_burden

    def valid_triple(self, index: int, role: str) -> bool:
        if index <= 2:
            trip = self.groups[:3]
        else:
            trip = self.groups[-4:-1]
        if (
            sum(group.roles[BA_PRECEPTOR] for group in trip) == 0
            and role == BA_PRECEPTOR
        ):
            return True
        else:
            return self.triple_unreserved_space(index) > 0

    def full_unreserved_space(self) -> int:
        all_roles = [group.roles for group in self.groups[:6]]
        has_spirit_dart = sum(roles[BA_SPIRIT_DART] for roles in all_roles) > 0
        has_feint = sum(roles[BA_FEINT] for roles in all_roles) > 0
        return (
            self.triple_unreserved_space(0)
            + self.triple_unreserved_space(3)
            - has_spirit_dart
            - has_feint
        )

    def can_add(self, index: int, role: str) -> bool:
        if not self.valid_single(index, role):
            return False
        if not self.valid_pair(index, role):
            return False
        if not self.valid_triple(index, role):
            return False
        all_roles = [group.roles for group in self.groups[:6]]
        has_spirit_dart = sum(roles[BA_SPIRIT_DART] for roles in all_roles) > 0
        has_feint = sum(roles[BA_FEINT] for roles in all_roles) > 0
        if role == BA_SPIRIT_DART and not has_spirit_dart:
            return True
        if role == BA_FEINT and not has_feint:
            return True
        else:
            return self.full_unreserved_space() > 0

    def __eq__(self, other):
        return type(other) is BARun and other.id == self.id

    def to_dict(self):
        return {
            "id": self.id,
            "roster_embed_id": self.roster_embed_id,
            "groups": [group.to_dict() for group in self.groups],
            "host": self.host,
            "host_id": self.host_id,
            "icon": self.icon,
            "password": self.password,
            "run_time": self.run_time.isoformat(),
        }

    async def wake_in(self, secs: float):
        await asyncio.sleep(secs)
        self.signal.set()

    async def password_auto_publish_loop(self):
        if self.password_auto_publish_running:
            return
        try:
            self.password_auto_publish_running = False
            now = datetime.datetime.now(tz=datetime.timezone.utc)
            while now < self.run_time:
                schedule_task(self.wake_in((self.run_time - now).total_seconds()))
                await wait_and_clear(self.signal)
                now = datetime.datetime.now(tz=datetime.timezone.utc)
            await self.ping_run(
                "Password is open to those signed up for this run"
                f" {self.message.jump_url}! Click the button to receive it."
            )
        finally:
            self.password_auto_publish_running = False

    def happening_now(self) -> bool:
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        if now >= self.run_time:
            return True
        elif not self.password_auto_publish_running:
            schedule_task(self.password_auto_publish_loop())
        return False

    def find_group_with(self, member: Union[int, RunMember]) -> Optional[BAGroup]:
        for i, group in enumerate(self.groups):
            if member in group:
                return group
        return None

    async def ping_run(self, message: Optional[str] = None):
        message = "" if message is None else message
        run_members = [await bot.bot.fetch_member(member.id) for member in self]
        await self.message.channel.send(
            message
            + " ".join(
                member.mention if member is not None else "" for member in run_members
            ),
            reference=self.message.to_reference(),
        )

    def __contains__(self, item):
        for group in self.groups:
            if item in group:
                return True
        return False

    def __iter__(self) -> itertools.chain[RunMember]:
        return itertools.chain(*self.groups)


class BAEmbedWrapper:
    def __init__(
        self, author_name: str, icon_url: str, embed: Optional[discord.Embed] = None
    ):
        if embed is None:
            embed = discord.Embed(
                title="BA Run Roster",
                description="Registration can be found below this roster.",
                colour=discord.Colour.teal(),
            )
            embed.add_field(
                name="Requirements",
                value=(
                    "Groups 1, 2, and 3 must have a single preceptor between them,"
                    " likewise for groups 4, 5, 6.\nBetween groups 1 and 2, there must"
                    " be a main tank. Likewise for groups 3 and 4, and for groups 5 and"
                    " 6.\nThere must a be a single spirit dart anywhere. Likewise for"
                    " feint.\nEach group must have at least a main tank OR a blue"
                    " DPS.\nEach group must have a healer."
                ),
            )
            embed.add_field(
                name="Party Leads",
                value=(
                    "Please note that the **FIRST PERSON TO JOIN A PARTY** is by"
                    " default assigned as the party lead. If a party lead was assigned"
                    " in this way, **ANYONE ELSE IN THE PARTY CAN CLAIM PARTY LEAD.**"
                    " If you want to lead a party, claim by clicking the corresponding"
                    " button, even if it has defaulted to you!"
                ),
            )
            for i in range(1, 7):
                embed.add_field(
                    name=f"Group {i} [0/8]",
                    value="",
                    inline=True,
                )
            embed.add_field(name="Support Group", value="")
            embed.set_author(name=author_name, icon_url=icon_url)

        self.embed = embed

    def set_group_text(self, index: int, name: str, value: str):
        if index in range(8):
            self.embed.set_field_at(index + 2, name=name, value=value)


class RoleSelectView(discord.ui.View):
    def __init__(self, group: BAGroup, *items: discord.ui.Item):
        super().__init__(*items)
        self.group = group

    @discord.ui.select(
        placeholder="Select a role.",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label=f"{BA_ROLE_EMOJI_MAPPING[role]} {role}")
            for role in BA_ROLE_EMOJI_MAPPING
        ],
    )
    async def role_select_callback(
        self, select: discord.ui.Select, interaction: discord.Interaction
    ):
        role = select.values[0]
        resp = interaction.response  # type: discord.InteractionResponse
        if interaction.user.id in self.group.run:
            await resp.send_message("You are already in this run!", ephemeral=True)
            return
        if self.group.can_add(role):
            self.group.add_member(
                RunMember(
                    globals.verification_map.get(
                        interaction.user.id, {"name": interaction.user.name}
                    )["name"],
                    role,
                    interaction.user.id,
                )
            )
            await resp.send_message("Successfully added!", ephemeral=True)
            return
        await resp.send_message(
            "You cannot join the group as that role due to party composition"
            " restrictions.",
            ephemeral=True,
        )
        return


class BAPasswordModal(discord.ui.Modal):
    def __init__(self, run: BARun):
        super().__init__(title="Set BA Password")
        self.run = run

        self.add_item(discord.ui.InputText(label="BA Password"))

    async def callback(self, interaction: discord.Interaction):
        resp = interaction.response  # type: discord.InteractionResponse
        self.run.password = self.children[0].value
        await resp.send_message("Password set.", ephemeral=True)


class BARunView(discord.ui.View):
    def __init__(self, run: BARun):
        self.run = run
        items = [
            self.generate_group_select(),
            generate_button(
                label="Set Password",
                custom_id=f"ba-set-pass-{self.run.id}",
                style=discord.ButtonStyle.primary,
                callback=self.set_password,
            ),
            generate_button(
                label="Make Password Public",
                custom_id=f"ba-release-pass-{self.run.id}",
                style=discord.ButtonStyle.primary,
                callback=self.release_password,
            ),
            generate_button(
                label="Leave Run",
                custom_id=f"ba-leave-run-{self.run.id}",
                style=discord.ButtonStyle.primary,
                callback=self.leave_run,
            ),
            generate_button(
                label="Claim Group Leader",
                custom_id=f"ba-claim-group-leader-{self.run.id}",
                style=discord.ButtonStyle.primary,
                callback=self.claim_leader,
            ),
            generate_button(
                label="Relinquish Group Leader",
                custom_id=f"ba-relinquish-group-leader-{self.run.id}",
                style=discord.ButtonStyle.primary,
                callback=self.relinquish_leader,
            ),
            generate_button(
                label="Ping Run",
                custom_id=f"ba-ping-run-{self.run.id}",
                style=discord.ButtonStyle.primary,
                callback=self.ping_run,
            ),
            generate_button(
                label="Get Password",
                custom_id=f"ba-get-password-{self.run.id}",
                style=discord.ButtonStyle.primary,
                callback=self.get_password,
            ),
        ]
        super().__init__(*items)

    def generate_group_select(self) -> discord.ui.Select:
        select = discord.ui.Select(
            custom_id=f"ba-select-group-{self.run.id}",
            placeholder="Choose a group.",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Group 1",
                    description="Try and join the first group.",
                    value="0",
                ),
                discord.SelectOption(
                    label="Group 2",
                    description="Try and join the second group.",
                    value="1",
                ),
                discord.SelectOption(
                    label="Group 3",
                    description="Try and join the third group.",
                    value="2",
                ),
                discord.SelectOption(
                    label="Group 4",
                    description="Try and join the fourth group.",
                    value="3",
                ),
                discord.SelectOption(
                    label="Group 5",
                    description="Try and join the fifth group.",
                    value="4",
                ),
                discord.SelectOption(
                    label="Group 6",
                    description="Try and join the sixth group.",
                    value="5",
                ),
                discord.SelectOption(
                    label="Support Group",
                    description="Try and join the support group.",
                    value="6",
                ),
            ],
        )
        select.callback = types.MethodType(self.group_selection_callback, select)
        return select

    async def group_selection_callback(
        self, select: discord.ui.Select, interaction: discord.Interaction
    ):
        group_index = int(select.values[0])
        resp = interaction.response  # type: discord.InteractionResponse
        await resp.send_message(view=RoleSelectView(self.run.groups[group_index]))

    async def set_password(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        resp = interaction.response  # type: discord.InteractionResponse
        if interaction.user.id == self.run.host_id:
            await resp.send_modal(BAPasswordModal(self.run))
        else:
            await resp.send_message(
                "Only the host can set the password.", ephemeral=True
            )

    async def release_password(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        resp = interaction.response  # type: discord.InteractionResponse
        if interaction.user.id == self.run.host_id:
            if self.run.public:
                await resp.send_message("Password is already public!", ephemeral=True)
            else:
                await resp.send_message("Password is now public.", ephemeral=True)
        else:
            await resp.send_message(
                "Only the host can release the password!", ephemeral=True
            )

    async def leave_run(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        resp = interaction.response  # type: discord.InteractionResponse
        group = self.run.find_group_with(interaction.user.id)
        if group is not None:
            group.remove_member(interaction.user.id)
            await resp.send_message(
                "You have been removed from the run.", ephemeral=True
            )
            return
        await resp.send_message("You are already not in the run!", ephemeral=True)

    async def claim_leader(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        resp = interaction.response  # type: discord.InteractionResponse
        group = self.run.find_group_with(interaction.user.id)
        if group is not None:
            if group.leader is None:
                group.leader = group.get_index(interaction.user.id)
                await resp.send_message(
                    "You have been assigned as group leader!", ephemeral=True
                )
            else:
                await resp.send_message(
                    "Your group already has a leader!", ephemeral=True
                )
        else:
            await resp.send_message("You are not in the run!", ephemeral=True)

    async def relinquish_leader(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        resp = interaction.response  # type: discord.InteractionResponse
        group = self.run.find_group_with(interaction.user.id)
        if group is not None:
            if (
                group.leader == group.get_index(interaction.user.id)
                and group.leader is not None
            ):
                group.leader = None
                await resp.send_message(
                    "You have been assigned as group leader!", ephemeral=True
                )
            else:
                await resp.send_message(
                    "You are already not the group leader, or you have been assigned"
                    " leader by default, and cannot relinquish it.",
                    ephemeral=True,
                )
        else:
            await resp.send_message("You are not in the run!", ephemeral=True)

    async def ping_run(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        resp = interaction.response  # type: discord.InteractionResponse
        if interaction.user.id == self.run.host_id:
            await resp.send_message("Pinging...", ephemeral=True)
            await self.run.ping_run()
        else:
            await resp.send_message(
                "Only the host can ping the whole run!", ephemeral=True
            )

    async def get_password(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        resp = interaction.response  # type: discord.InteractionResponse
        if (
            interaction.user.id == self.run.host_id
            or self.run.public
            or (interaction.user.id in self.run and self.run.happening_now())
        ):
            await resp.send_message(
                f"{self.run.password if self.run.password is not None else 'No password set.'}",
                ephemeral=True,
            )
        else:
            await resp.send_message(
                "The password is not available to you at this time.", ephemeral=True
            )
