from __future__ import annotations

import discord


class ReactionRoleSelect(discord.ui.Select):
    def __init__(self, guild_id: int, message_id: int, options: list[tuple[int, str, str | None]], max_values: int):
        self.guild_id = guild_id
        self.message_id = message_id
        select_options = [
            discord.SelectOption(label=label, value=str(role_id), emoji=emoji)
            for role_id, label, emoji in options
        ]
        super().__init__(
            placeholder="Choose roles...",
            min_values=0,
            max_values=max_values,
            options=select_options[:25],
            custom_id=f"rr:{guild_id}:{message_id}",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        member = interaction.user
        selected = {int(v) for v in self.values}
        panel_role_ids = [int(opt.value) for opt in self.options]

        to_add = []
        to_remove = []
        for rid in panel_role_ids:
            role = interaction.guild.get_role(rid)
            if not role:
                continue
            if rid in selected and role not in member.roles:
                to_add.append(role)
            if rid not in selected and role in member.roles:
                to_remove.append(role)

        try:
            if to_remove:
                await member.remove_roles(*to_remove, reason="Reaction role panel update")
            if to_add:
                await member.add_roles(*to_add, reason="Reaction role panel update")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Missing permissions to manage roles.", ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.response.send_message("❌ API error updating roles.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Roles updated.", ephemeral=True)


class ReactionRoleView(discord.ui.View):
    def __init__(self, guild_id: int, message_id: int, options: list[tuple[int, str, str | None]], max_values: int):
        super().__init__(timeout=None)
        self.add_item(ReactionRoleSelect(guild_id, message_id, options, max_values))
