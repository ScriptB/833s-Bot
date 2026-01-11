from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import discord.ui
import datetime

from ..security.auth import is_bot_owner
from ..utils import safe_embed


class AdminManagementCog(commands.Cog):
    """Bot-owner-only admin role management."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
    
    async def _check_bot_owner(self, interaction: discord.Interaction) -> bool:
        """Check if user is bot owner or team member."""
        if not await is_bot_owner(self.bot, interaction.user.id):
            await interaction.response.send_message(
                "❌ Only bot application owner or team members can use this command.",
                ephemeral=True
            )
            return False
        return True
    
    async def _get_or_create_admin_role(self, guild: discord.Guild) -> discord.Role:
        """Get or create the Admin role with proper permissions."""
        # Try to find existing Admin role
        admin_role = discord.utils.get(guild.roles, name="Admin")
        
        if admin_role is None:
            # Create Admin role with administrator permissions
            admin_role = await guild.create_role(
                name="Admin",
                permissions=discord.Permissions(administrator=True),
                reason="Created by bot owner command",
                color=discord.Color.orange()
            )
        
        return admin_role
    
    async def _check_role_hierarchy(self, guild: discord.Guild, target_role: discord.Role) -> bool:
        """Check if bot can manage the target role."""
        bot_member = guild.me or guild.get_member(self.bot.user.id)  # type: ignore[attr-defined]
        if not bot_member:
            return False
        
        # Bot's highest role must be higher than target role
        bot_top_role = bot_member.top_role
        return bot_top_role.position > target_role.position
    
    async def _log_admin_action(
        self, 
        guild: discord.Guild, 
        action: str, 
        target_user: discord.Member,
        performed_by: discord.User
    ) -> None:
        """Log admin actions to database and mod-logs channel."""
        # Log to database (you can implement this if needed)
        # For now, just log to console
        self.bot.log.info(
            f"Admin action: {action} - User: {target_user} ({target_user.id}) "
            f"by {performed_by} ({performed_by.id}) in {guild.name}"
        )
        
        # Try to log to mod-logs channel
        mod_logs_channel = discord.utils.get(guild.text_channels, name="mod-logs")
        if mod_logs_channel:
            embed = safe_embed(
                title=f"🔐 Admin {action.title()}",
                color=discord.Color.orange() if action == "elevated" else discord.Color.red()
            )
            embed.add_field(name="Target User", value=f"{target_user.mention} ({target_user.id})", inline=False)
            embed.add_field(name="Performed By", value=f"{performed_by.mention} ({performed_by.id})", inline=False)
            embed.add_field(name="Timestamp", value=datetime.datetime.utcnow().isoformat(), inline=False)
            embed.set_footer(text="Bot Owner Action")
            
            try:
                await mod_logs_channel.send(embed=embed)
            except Exception as e:
                self.bot.log.warning(f"Failed to log admin action to mod-logs: {e}")
    
    @app_commands.command(
        name="elevate_admin",
        description="Grant Admin role to a user (Bot owner only)"
    )
    @app_commands.describe(
        user="The user to elevate to Admin",
        confirm="Type 'GRANT_ADMIN <user_id>' to confirm"
    )
    async def elevate_admin(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member,
        confirm: str
    ) -> None:
        """Elevate a user to Admin role (bot owner only)."""
        
        # Must be in a guild
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return
        
        # Check bot owner permission
        if not await self._check_bot_owner(interaction):
            return
        
        # Validate confirmation
        expected_confirm = f"GRANT_ADMIN {user.id}"
        if confirm != expected_confirm:
            await interaction.response.send_message(
                f"❌ Confirmation required. Type exactly: `{expected_confirm}`",
                ephemeral=True
            )
            return
        
        # Validate target
        if user.bot:
            await interaction.response.send_message(
                "❌ Cannot elevate bots to Admin role.",
                ephemeral=True
            )
            return
        
        if user.id == self.bot.user.id:
            await interaction.response.send_message(
                "❌ Cannot elevate the bot itself.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get or create Admin role
            admin_role = await self._get_or_create_admin_role(interaction.guild)
            
            # Check role hierarchy
            if not await self._check_role_hierarchy(interaction.guild, admin_role):
                await interaction.followup.send(
                    "❌ Bot role is not high enough in hierarchy to manage Admin role.",
                    ephemeral=True
                )
                return
            
            # Check if user already has Admin role
            if admin_role in user.roles:
                await interaction.followup.send(
                    f"✅ {user.mention} already has Admin role.",
                    ephemeral=True
                )
                return
            
            # Assign Admin role
            await user.add_roles(admin_role, reason="Elevated by bot owner")
            
            # Log the action
            await self._log_admin_action(
                interaction.guild, 
                "elevated", 
                user, 
                interaction.user
            )
            
            await interaction.followup.send(
                f"✅ Successfully elevated {user.mention} to Admin role.",
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Missing permissions to manage roles.",
                ephemeral=True
            )
        except Exception as e:
            self.bot.log.error(f"Error elevating admin: {e}")
            await interaction.followup.send(
                "❌ An error occurred while elevating user.",
                ephemeral=True
            )
    
    @app_commands.command(
        name="revoke_admin",
        description="Remove Admin role from a user (Bot owner only)"
    )
    @app_commands.describe(
        user="The user to revoke Admin role from",
        confirm="Type 'REVOKE_ADMIN <user_id>' to confirm"
    )
    async def revoke_admin(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member,
        confirm: str
    ) -> None:
        """Revoke Admin role from a user (bot owner only)."""
        
        # Must be in a guild
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return
        
        # Check bot owner permission
        if not await self._check_bot_owner(interaction):
            return
        
        # Validate confirmation
        expected_confirm = f"REVOKE_ADMIN {user.id}"
        if confirm != expected_confirm:
            await interaction.response.send_message(
                f"❌ Confirmation required. Type exactly: `{expected_confirm}`",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Find Admin role
            admin_role = discord.utils.get(interaction.guild.roles, name="Admin")
            
            if not admin_role:
                await interaction.followup.send(
                    "❌ Admin role does not exist in this server.",
                    ephemeral=True
                )
                return
            
            # Check if user has Admin role
            if admin_role not in user.roles:
                await interaction.followup.send(
                    f"❌ {user.mention} does not have Admin role.",
                    ephemeral=True
                )
                return
            
            # Check role hierarchy
            if not await self._check_role_hierarchy(interaction.guild, admin_role):
                await interaction.followup.send(
                    "❌ Bot role is not high enough in hierarchy to manage Admin role.",
                    ephemeral=True
                )
                return
            
            # Remove Admin role
            await user.remove_roles(admin_role, reason="Revoked by bot owner")
            
            # Log the action
            await self._log_admin_action(
                interaction.guild, 
                "revoked", 
                user, 
                interaction.user
            )
            
            await interaction.followup.send(
                f"✅ Successfully revoked Admin role from {user.mention}.",
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Missing permissions to manage roles.",
                ephemeral=True
            )
        except Exception as e:
            self.bot.log.error(f"Error revoking admin: {e}")
            await interaction.followup.send(
                "❌ An error occurred while revoking admin role.",
                ephemeral=True
            )
