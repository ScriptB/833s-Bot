from __future__ import annotations

import json
import discord


class LanguageSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="English", value="en"),
            discord.SelectOption(label="Spanish", value="es"),
            discord.SelectOption(label="French", value="fr"),
            discord.SelectOption(label="German", value="de"),
        ]
        super().__init__(placeholder="Language", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: OnboardingView = self.view  # type: ignore
        view.language = self.values[0]
        await interaction.response.send_message("Language saved.", ephemeral=True)


class InterestSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="Gamer", value="Gamer"),
            discord.SelectOption(label="Developer", value="Developer"),
            discord.SelectOption(label="Artist", value="Artist"),
            discord.SelectOption(label="Music", value="Music"),
        ]
        super().__init__(placeholder="Interests (optional)", min_values=0, max_values=4, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: OnboardingView = self.view  # type: ignore
        view.interests = list(self.values)
        await interaction.response.send_message("Interests saved.", ephemeral=True)


class OnboardingView(discord.ui.View):
    """Persistent onboarding view that survives bot restarts."""
    
    def __init__(self, bot, guild_id: int, user_id: int) -> None:
        super().__init__(timeout=None)  # Persistent view
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.language: str | None = None
        self.interests: list[str] = []
        self.add_item(LanguageSelect())
        self.add_item(InterestSelect())

    @discord.ui.button(label="Accept Rules", style=discord.ButtonStyle.success)
    async def accept_rules(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not for you.", ephemeral=True)
            return
        st = await self.bot.onboarding_store.get(self.guild_id, self.user_id)
        if st.step < 1:
            await self.bot.onboarding_store.upsert(type(st)(self.guild_id, self.user_id, 1, st.language, st.interests_json, False))
        await interaction.response.send_message("Rules accepted.", ephemeral=True)

    @discord.ui.button(label="18+ Confirm", style=discord.ButtonStyle.primary)
    async def age_confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not for you.", ephemeral=True)
            return
        st = await self.bot.onboarding_store.get(self.guild_id, self.user_id)
        if st.step < 2:
            await self.bot.onboarding_store.upsert(type(st)(self.guild_id, self.user_id, 2, st.language, st.interests_json, False))
        await interaction.response.send_message("Age confirmed.", ephemeral=True)

    @discord.ui.button(label="Finish", style=discord.ButtonStyle.success)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not for you.", ephemeral=True)
            return

        st = await self.bot.onboarding_store.get(self.guild_id, self.user_id)
        if st.step < 2:
            await interaction.response.send_message("Complete Rules + 18+ first.", ephemeral=True)
            return

        lang = self.language or st.language
        interests_json = json.dumps(self.interests, separators=(",", ":"), ensure_ascii=False)
        await self.bot.onboarding_store.upsert(type(st)(self.guild_id, self.user_id, 3, lang, interests_json, True))

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Guild missing.", ephemeral=True)
            return
        member = guild.get_member(self.user_id)
        if not member:
            await interaction.response.send_message("Member missing.", ephemeral=True)
            return

        quarantine = discord.utils.get(guild.roles, name="Quarantine")
        verified = discord.utils.get(guild.roles, name="Verified Member")
        member_role = discord.utils.get(guild.roles, name="Member")

        try:
            if verified:
                await member.add_roles(verified, reason="Onboarding complete")
            if member_role:
                await member.add_roles(member_role, reason="Onboarding complete")
            if quarantine:
                await member.remove_roles(quarantine, reason="Onboarding complete")
        except discord.HTTPException:
            pass

        for rn in self.interests:
            r = discord.utils.get(guild.roles, name=rn)
            if r:
                try:
                    await member.add_roles(r, reason="Onboarding interests")
                except discord.HTTPException:
                    pass

        await interaction.response.send_message("Onboarding complete. Access granted.", ephemeral=True)
        self.stop()
