from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import logging

from ..ui.persistent import GUARDIAN_V1

log = logging.getLogger("guardian.verify_panel")


class VerifyView(discord.ui.View):
    """Persistent verification view with stable custom_id."""
    
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view
    
    @discord.ui.button(
        label="✅ Verify", 
        style=discord.ButtonStyle.success, 
        custom_id=f"{GUARDIAN_V1}:verify:accept"
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Handle verification with stateless logic."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        
        guild = interaction.guild
        member = interaction.user
        
        # Get verification role
        verify_role = discord.utils.get(guild.roles, name="Verified")
        if not verify_role:
            await interaction.response.send_message(
                "❌ Verification role not found. Contact server admin.",
                ephemeral=True
            )
            return
        
        # Check if already verified
        if verify_role in member.roles:
            await interaction.response.send_message(
                "✅ You are already verified!",
                ephemeral=True
            )
            return
        
        # Assign verification role
        try:
            await member.add_roles(verify_role, reason="User verified")
            await interaction.response.send_message(
                "✅ You have been verified! Welcome to the server.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing permissions to assign roles.",
                ephemeral=True
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ API error during verification.",
                ephemeral=True
            )


class VerifyPanelCog(commands.Cog):
    """Cog for managing persistent verification panels."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def cog_load(self) -> None:
        """Initialize panel registry renderer."""
        # Register renderer with panel registry
        self.bot.panel_registry.register_renderer("verify_panel", self._render_verify_panel)
        log.info("Registered verify_panel renderer")
    
    async def _render_verify_panel(self, guild: discord.Guild):
        """Render verification panel embed and view."""
        embed = discord.Embed(
            title="🔐 Verification Required",
            description="Click the button below to verify and gain access to the server.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Verification is required to access server channels")
        
        view = VerifyView()
        return embed, view
    
    @app_commands.command(name="verifypanel", description="Deploy verification panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def verifypanel(self, interaction: discord.Interaction) -> None:
        """Deploy verification panel."""
        await self._deploy_verify_panel(interaction)
    
    async def _deploy_verify_panel(self, interaction: discord.Interaction) -> None:
        """Deploy a persistent verification panel using panel registry."""
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        
        # Check if verification role exists
        verify_role = discord.utils.get(guild.roles, name="Verified")
        if not verify_role:
            await interaction.followup.send(
                "❌ 'Verified' role not found. Please create it first.",
                ephemeral=True
            )
            return
        
        # Deploy using panel registry
        message = await self.bot.panel_registry.deploy_panel("verify_panel", guild)
        
        if message:
            await interaction.followup.send(
                f"✅ Verification panel deployed successfully.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ Failed to deploy verification panel. Check logs for details.",
                ephemeral=True
            )


# Setup function for adding cog
async def setup(bot: commands.Bot) -> None:
    """Add the verification panel cog to the bot."""
    await bot.add_cog(VerifyPanelCog(bot))
