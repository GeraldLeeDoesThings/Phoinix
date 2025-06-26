import globals
import bot
from const import *
import discord
from utils import validate_server


class VerificationModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Register Character Data")

        self.add_item(discord.ui.InputText(label="Full Character Name"))
        self.add_item(discord.ui.InputText(label="Character Server"))

    async def callback(self, interaction: discord.Interaction):
        name = " ".join(
            part.capitalize() for part in self.children[0].value.split(" ")
        ).replace("’", "'")
        server = self.children[1].value.split(" ")[0].capitalize()
        fakedefer = await interaction.response.send_message(
            "Searching...", ephemeral=True
        )  # type: discord.Interaction

        validServer, suggestedServer = validate_server(server)

        if not validServer:
            await fakedefer.edit_original_response(
                content=suggestedServer,
            )
            return

        if await bot.register_user(
            interaction.user.id,
            name,
            server,
        ):
            await fakedefer.edit_original_response(
                content=(
                    f"Registration successful! Add `{bot.get_user_token(interaction.user.id)}`"
                    " to your character profile on the Lodestone, then **click the"
                    " Verify button.** If you cannot copy your token, try copying from"
                    f" {ECHO_TOKEN_URL}{bot.get_user_token(interaction.user.id)}\nYour"
                    " character profile can be found here:"
                    " https://na.finalfantasyxiv.com/lodestone/my/setting/profile/"
                ),
            )
            return
        await fakedefer.edit_original_response(
            content=(
                f"Could not find character with:\nName: {name}\nServer:"
                f" {server}\n\nName should be exact, and include both"
                " first and last (ex 'Lerald Gee' without quotes)."
            ),
        )


class VerificationView(discord.ui.View):
    def __init__(self, bot):
        self.bot = bot
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
        if not bot.known_discord_id(interaction.user.id):
            await response.edit_original_response(
                content=(
                    "You must register first! Click the Register button and follow the"
                    " instructions."
                ),
            )
            return
        if globals.verification_map[interaction.user.id]["valid"]:
            await response.edit_original_response(content="You are already verified!")
            member = await self.bot.fetch_member(interaction.user.id)
            await member.add_roles(discord.Object(ROLE_ID_MAP["Member"]))
            return
        result = bot.full_validate(globals.verification_map[interaction.user.id])
        if type(result) == str:
            await response.edit_original_response(content=result)
        else:
            try:
                globals.verification_map[interaction.user.id] = result
                member = await self.bot.fetch_member(interaction.user.id)
                await member.add_roles(discord.Object(ROLE_ID_MAP["Member"]))
                if ROLE_ID_MAP["Not Verified"] in [role.id for role in member.roles]:
                    await member.remove_roles(
                        discord.Object(ROLE_ID_MAP["Not Verified"])
                    )
                await self.bot.fix_name(member)
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
        await self.verify_clear(
            button,
            interaction,
            ACHIEVEMENT_ID_MAP["BA Clear"],
            MOUNT_ID_MAP["BA Ball"],
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
        await self.verify_clear(
            button,
            interaction,
            ACHIEVEMENT_ID_MAP["DRS Clear"],
            MOUNT_ID_MAP["DRS Dog"],
            ROLE_ID_MAP["Cleared DRS"],
        )

    @discord.ui.button(
        label="Verify FT Clear",
        custom_id="verify_ft",
        style=discord.ButtonStyle.primary,
    )
    async def verify_ft_clear(
            self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await self.verify_clear(
            button,
            interaction,
            ACHIEVEMENT_ID_MAP["FT Clear"],
            MOUNT_ID_MAP["FT Crab"],
            ROLE_ID_MAP["Cleared FT"],
        )

    @discord.ui.string_select(
        placeholder="Add/Remove Enjoyer Roles",
        options=[
            discord.SelectOption(label="FT Enjoyer"),
            discord.SelectOption(label="DRS Enjoyer"),
            discord.SelectOption(label="BA Enjoyer"),
            discord.SelectOption(label="Remove Enjoyer Roles", description="Removes all enjoyer roles"),
        ]
    )
    async def modify_enjoyer_roles(
        self,
        select: discord.ui.Select,
        interaction: discord.Interaction,
    ):
        member = interaction.user
        ffxiv_id = bot.get_user_ffxiv_id(interaction.user.id)
        if ffxiv_id is None:
            await interaction.response.send_message(
                "You must register and verify first!",
                ephemeral=True,
            )
            return

        selection_mappings = {
            "FT Enjoyer": {"needed achievement": "FT Clear 10x", "given role": "FT Enjoyer", "missing msg": "FT Clear"},
            "DRS Enjoyer": {"needed achievement": "DRS Clear 10x", "given role": "DRS Enjoyer", "missing msg": "DRS Clear"},
            "BA Enjoyer": {"needed achievement": "BA Clear 10x", "given role": "BA Enjoyer", "missing msg": "BA Clear"},
        }
        for selection in select.values:
            mapping = selection_mappings.get(selection, None)
            if mapping is not None:
                needed_achievement = ACHIEVEMENT_ID_MAP[mapping["needed achievement"]]
                given_role = ROLE_ID_MAP[mapping["given role"]]

                if bot.user_has_achievement(ffxiv_id, needed_achievement):
                    await member.add_roles(discord.Object(given_role))
                    await interaction.response.send_message(
                        "Role added!",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        f"You must have 10 {mapping['missing msg']}s before you can claim this role!",
                        ephemeral=True,
                    )
            elif selection == "Remove Enjoyer Roles":
                await member.remove_roles(
                    discord.Object(ROLE_ID_MAP["FT Enjoyer"]),
                    discord.Object(ROLE_ID_MAP["DRS Enjoyer"]),
                    discord.Object(ROLE_ID_MAP["BA Enjoyer"]),
                )
                await interaction.response.send_message(
                    "Roles removed!",
                    ephemeral=True,
                )

    async def verify_clear(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
        achievement_id: int,
        mount_id: str,
        role: int,
    ):
        if not bot.known_discord_id(interaction.user.id):
            await interaction.response.send_message(
                "You are not registered! Click the Register button, follow the"
                " instructions, then click the Verify button, then try this button"
                " again.",
                ephemeral=True,
            )
        elif not globals.verification_map[interaction.user.id]["valid"]:
            await interaction.response.send_message(
                "You are not verified! Click the Verify button, then try this button"
                " again.",
                ephemeral=True,
            )
        else:
            response = await interaction.response.send_message(
                "Checking achievements...", ephemeral=True
            )  # type: discord.Interaction
            ffxiv_id = bot.get_user_ffxiv_id(interaction.user.id)
            has = bot.validate_mount(ffxiv_id, mount_id) or bot.user_has_achievement(
                ffxiv_id, achievement_id
            )
            if has is None:
                await response.edit_original_response(
                    content=(
                        "Your achievements are not public, and no mount indicating a clear was found in your mounts!"
                        " Set your achievements to public, then try again."
                    )
                )
            elif has:
                try:
                    member = await self.bot.fetch_member(interaction.user.id)
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
