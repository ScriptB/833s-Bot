from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.reaction_roles import ReactionRoleView


class ReactionRolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self._loaded = False

    async def _load_views(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        for g in self.bot.guilds:  # type: ignore[attr-defined]
            panels = await self.bot.rr_store.list_panels(g.id)  # type: ignore[attr-defined]
            for channel_id, message_id in panels:
                data = await self.bot.rr_store.get_panel(g.id, int(message_id))  # type: ignore[attr-defined]
                if not data:
                    continue
                panel, options = data
                _ch, title, description, max_values = panel
                view = ReactionRoleView(
                    g.id,
                    int(message_id),
                    [(int(r), str(l), (str(e) if e else None)) for (r, l, e) in options],
                    int(max_values),
                )
                self.bot.add_view(view, message_id=int(message_id))  # type: ignore[attr-defined]

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._load_views()

    async def _load_overhaul_views(self) -> None:
        """Load persistent reaction roles panels created by the overhaul system."""
        for g in self.bot.guilds:  # type: ignore[attr-defined]
            try:
                # Find reaction-roles channel
                channel = discord.utils.get(g.text_channels, name="reaction-roles")
                if not channel:
                    continue
                # Find the panel message
                panels = await self.bot.rr_store.list_panels(g.id)  # type: ignore[attr-defined]
                for channel_id, message_id in panels:
                    if channel_id != channel.id:
                        continue
                    data = await self.bot.rr_store.get_panel(g.id, int(message_id))  # type: ignore[attr-defined]
                    if not data:
                        continue
                    panel, options = data
                    _ch, title, description, max_values = panel
                    # Check if this is an overhaul panel (has our standard title)
                    if title == "Self-Assignable Roles":
                        # Reattach our persistent view
                        from ..ui.reaction_roles import ReactionRolesView
                        view = ReactionRolesView(g, {})
                        self.bot.add_view(view, message_id=int(message_id))  # type: ignore[attr-defined]
                        self.bot.logger.info(f"Reattached overhaul reaction roles panel in {g.name}")
                        break
            except Exception as e:
                self.bot.logger.warning(f"Failed to load overhaul views for {g.name}: {e}")

    @app_commands.command(name="rr_panel_create", description="Create a reaction-role select panel.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def rr_panel_create(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        max_values: app_commands.Range[int, 1, 25] = 1,
        channel: discord.TextChannel | None = None,
    ) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = channel or interaction.channel  # type: ignore
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("❌ Invalid channel.", ephemeral=True)
            return

        embed = discord.Embed(title=title, description=description)
        msg = await channel.send(embed=embed)  # empty panel until options added
        await self.bot.rr_store.create_panel(interaction.guild.id, channel.id, msg.id, title, description, int(max_values))  # type: ignore[attr-defined]
        await interaction.followup.send(f"✅ Panel created: {msg.jump_url}", ephemeral=True)

    @app_commands.command(name="rr_option_add", description="Add a role option to a reaction-role panel.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def rr_option_add(self, interaction: discord.Interaction, message_id: str, role: discord.Role, label: str, emoji: str | None = None) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        mid = int(message_id)
        data = await self.bot.rr_store.get_panel(interaction.guild.id, mid)  # type: ignore[attr-defined]
        if not data:
            await interaction.followup.send("❌ Panel not found.", ephemeral=True)
            return
        panel, options = data
        channel_id, title, description, max_values = panel

        await self.bot.rr_store.add_option(interaction.guild.id, mid, role.id, label, emoji)  # type: ignore[attr-defined]
        data2 = await self.bot.rr_store.get_panel(interaction.guild.id, mid)  # type: ignore[attr-defined]
        panel2, options2 = data2

        channel = interaction.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("❌ Channel missing.", ephemeral=True)
            return
        try:
            msg = await channel.fetch_message(mid)
        except discord.HTTPException:
            await interaction.followup.send("❌ Message missing.", ephemeral=True)
            return

        view = ReactionRoleView(interaction.guild.id, mid, [(int(r), str(l), (str(e) if e else None)) for (r, l, e) in options2], int(panel2[3]))
        self.bot.add_view(view, message_id=mid)  # type: ignore[attr-defined]
        embed = discord.Embed(title=title, description=description)
        await msg.edit(embed=embed, view=view)

        await interaction.followup.send("✅ Panel updated.", ephemeral=True)

    @app_commands.command(name="rr_option_remove", description="Remove a role option from a reaction-role panel.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def rr_option_remove(self, interaction: discord.Interaction, message_id: str, role: discord.Role) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.bot.rr_store.remove_option(interaction.guild.id, int(message_id), role.id)  # type: ignore[attr-defined]
        await interaction.followup.send("✅ Option removed.", ephemeral=True)
