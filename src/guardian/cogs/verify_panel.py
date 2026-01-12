from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from ..services.panel_store import PanelStore


class PersistentVerifyView(discord.ui.View):
    """Persistent verification view that survives bot restarts."""
    
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.guild_id = guild_id
    
    @discord.ui.button(
        label="✅ Verify", 
        style=discord.ButtonStyle.success, 
        custom_id="persistent_verify"
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
        self.panel_store: Optional[PanelStore] = None
    
    async def cog_load(self) -> None:
        """Initialize store and register persistent views."""
        # Initialize store
        db_path = getattr(self.bot, 'db_path', 'guardian.db')
        self.panel_store = PanelStore(db_path)
        await self.panel_store.initialize()
        
        # Register persistent views for all existing panels
        await self._restore_panels()
    
    async def _restore_panels(self) -> None:
        """Restore all persistent verification panels on startup."""
        if not self.panel_store:
            return
            
        panels = await self.panel_store.list_panels()
        for panel in panels:
            if panel.panel_key.startswith('verify_panel_'):
                try:
                    # Create and register the view
                    view = PersistentVerifyView(panel.guild_id)
                    self.bot.add_view(view, message_id=panel.message_id)
                    
                    print(f"✅ Restored verify panel {panel.panel_key} in guild {panel.guild_id}")
                except Exception as e:
                    print(f"❌ Failed to restore verify panel {panel.panel_key}: {e}")
    
    @app_commands.command(name="panel", description="Manage persistent UI panels")
    @app_commands.checks.has_permissions(administrator=True)
    async def panel(self, interaction: discord.Interaction) -> None:
        """Panel management command group."""
        await interaction.response.send_message(
            "Use `/panel deploy verify` to deploy verification panel.",
            ephemeral=True
        )
    
    @app_commands.command(name="deploy", description="Deploy a persistent UI panel")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(panel_type="Type of panel to deploy")
    @app_commands.choices(panel_type=[
        app_commands.Choice(name="Roles", value="roles"),
        app_commands.Choice(name="Verify", value="verify")
    ])
    async def panel_deploy(
        self, 
        interaction: discord.Interaction, 
        panel_type: str
    ) -> None:
        """Deploy a persistent UI panel."""
        
        if not interaction.guild:
            await interaction.response.send_message("Guild required.", ephemeral=True)
            return
        
        if panel_type == "verify":
            await self._deploy_verify_panel(interaction)
        else:
            await interaction.response.send_message("Unknown panel type.", ephemeral=True)
    
    async def _deploy_verify_panel(self, interaction: discord.Interaction) -> None:
        """Deploy a persistent verification panel."""
        if not self.panel_store:
            await interaction.response.send_message("Store not initialized.", ephemeral=True)
            return
        
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
        
        # Find or create verification channel
        channel = discord.utils.get(guild.text_channels, name="verify")
        if not channel:
            try:
                channel = await guild.create_text_channel(
                    "verify", 
                    reason="Verification panel channel"
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ Missing permissions to create channels.",
                    ephemeral=True
                )
                return
        
        # Create panel embed
        embed = discord.Embed(
            title="✅ Server Verification",
            description=(
                "Click the button below to verify your account and gain access to the server.\n\n"
                "Verification grants you the **Verified** role and unlocks server features."
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="Verification is persistent - click once per account")
        
        # Create and send view
        view = PersistentVerifyView(guild.id)
        message = await channel.send(embed=embed, view=view)
        
        # Store panel reference
        panel_key = f"verify_panel_main"
        await self.panel_store.upsert_panel(
            panel_key, guild.id, channel.id, message.id
        )
        
        await interaction.followup.send(
            f"✅ Verification panel deployed: {message.jump_url}",
            ephemeral=True
        )


# Setup function for adding cog
async def setup(bot: commands.Bot) -> None:
    """Add the verification panel cog to the bot."""
    await bot.add_cog(VerifyPanelCog(bot))
