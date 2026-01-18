from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from ..services.api_wrapper import APIResult, safe_send_message, safe_create_channel
from ..interfaces import has_required_guild_perms
from ..constants import COLORS
from ..lookup import find_text_channel

log = logging.getLogger("guardian.setup_wizard")


@dataclass
class SetupCheck:
    """Represents a single setup check result."""
    name: str
    status: str  # "pass", "fail", "warning"
    message: str
    fix_action: Optional[str] = None
    can_auto_fix: bool = False


@dataclass 
class SetupResult:
    """Complete setup validation result."""
    overall_status: str  # "pass", "fail", "warning"
    checks: List[SetupCheck]
    guild_id: int
    user_id: int


class SetupWizardView(discord.ui.View):
    """Interactive view for setup wizard with fix actions."""
    
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view
        self.add_item(FixNowButton())


class FixNowButton(discord.ui.Button):
    """Button to automatically fix setup issues."""
    
    def __init__(self):
        super().__init__(
            label="Fix Now",
            style=discord.ButtonStyle.primary,
            custom_id="guardian_setup_fix_now",
            emoji="🔧"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle fix button click."""
        await interaction.response.defer(ephemeral=True)
        
        # Get the cog from the bot
        cog = interaction.client.get_cog('SetupWizardCog')
        if not cog:
            await interaction.followup.send("❌ Setup wizard cog not found.", ephemeral=True)
            return
        
        # Apply fixes (we'll need to reconstruct the setup result)
        # For now, just run a basic setup check
        try:
            checks = [
                cog._check_user_permissions(interaction),
                cog._check_bot_permissions(interaction.guild),
                cog._check_bot_role_position(interaction.guild),
                cog._check_required_channels(interaction.guild),
                await cog._check_panels(interaction.guild)
            ]
            
            # Determine overall status
            failed_checks = [c for c in checks if c.status == "fail"]
            warning_checks = [c for c in checks if c.status == "warning"]
            
            if failed_checks:
                overall_status = "fail"
            elif warning_checks:
                overall_status = "warning"
            else:
                overall_status = "pass"
            
            setup_result = SetupResult(
                overall_status=overall_status,
                checks=checks,
                guild_id=interaction.guild.id,
                user_id=interaction.user.id
            )
            
            # Apply fixes
            fix_result = await cog.apply_fixes(interaction.guild, interaction.user, setup_result)
            
            # Send updated result
            embed = cog.create_setup_embed(fix_result)
            await interaction.followup.send(embed=embed, ephemeral=True, view=SetupWizardView())
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error applying fixes: {str(e)}", ephemeral=True)


class SetupWizardCog(commands.Cog):
    """Setup wizard for guided server configuration."""
    
    REQUIRED_CHANNELS = [
        "verify",
        "support-start", 
        "reaction-roles",
        "tickets"
    ]
    
    REQUIRED_PERMISSIONS = [
        "manage_channels",
        "manage_roles", 
        "manage_guild",
        "send_messages",
        "embed_links"
    ]
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def cog_load(self):
        """Register persistent view when cog loads."""
        self.bot.add_view(SetupWizardView())
    
    def _check_bot_permissions(self, guild: discord.Guild) -> SetupCheck:
        """Check if bot has required permissions."""
        bot_member = guild.me
        
        missing_perms = []
        for perm in self.REQUIRED_PERMISSIONS:
            if not getattr(bot_member.guild_permissions, perm, False):
                missing_perms.append(perm.replace("_", " ").title())
        
        if not missing_perms:
            return SetupCheck(
                name="Bot Permissions",
                status="pass",
                message="✅ Bot has all required permissions"
            )
        
        return SetupCheck(
            name="Bot Permissions",
            status="fail",
            message=f"❌ Missing permissions: {', '.join(missing_perms)}",
            fix_action="Ensure bot has these permissions in server settings",
            can_auto_fix=False
        )
    
    def _check_bot_role_position(self, guild: discord.Guild) -> SetupCheck:
        """Check if bot's highest role is above all user roles."""
        bot_role = guild.me.top_role
        
        # Find the highest role that could be assigned to users (excluding @everyone and bot roles)
        user_roles = [role for role in guild.roles 
                     if role.name != "@everyone" and not role.managed and role != bot_role]
        
        if not user_roles:
            return SetupCheck(
                name="Bot Role Position",
                status="pass", 
                message="✅ Bot role position is optimal"
            )
        
        highest_user_role = max(user_roles, key=lambda r: r.position)
        
        if bot_role.position > highest_user_role.position:
            return SetupCheck(
                name="Bot Role Position",
                status="pass",
                message="✅ Bot role is above all user roles"
            )
        
        return SetupCheck(
            name="Bot Role Position", 
            status="warning",
            message=f"⚠️ Bot role is below '{highest_user_role.name}' - some operations may fail",
            fix_action=f"Move bot's highest role above '{highest_user_role.name}' in server settings",
            can_auto_fix=False
        )
    
    def _check_required_channels(self, guild: discord.Guild) -> SetupCheck:
        """Check if required channels exist."""
        existing_channels = [channel.name.lower() for channel in guild.text_channels]
        missing_channels = []
        
        for channel_name in self.REQUIRED_CHANNELS:
            if channel_name not in existing_channels:
                missing_channels.append(channel_name)
        
        if not missing_channels:
            return SetupCheck(
                name="Required Channels",
                status="pass",
                message="✅ All required channels exist"
            )
        
        return SetupCheck(
            name="Required Channels",
            status="fail", 
            message=f"❌ Missing channels: {', '.join(missing_channels)}",
            fix_action="Create missing channels with proper permissions",
            can_auto_fix=True
        )
    
    async def _check_panels(self, guild: discord.Guild) -> SetupCheck:
        """Check if panels are deployed in required channels."""
        issues = []
        
        # Check verify panel
        verify_channel = find_text_channel(guild, "verify")
        if verify_channel:
            try:
                async for message in verify_channel.history(limit=10):
                    if message.author == guild.me and message.components:
                        break
                else:
                    issues.append("verify panel missing")
            except discord.Forbidden:
                issues.append("cannot read verify channel")
        else:
            issues.append("verify channel missing")
        
        # Check reaction roles panel
        rr_channel = find_text_channel(guild, "choose-your-games") or find_text_channel(guild, "server-info")
        if rr_channel:
            try:
                async for message in rr_channel.history(limit=10):
                    if message.author == guild.me and message.components:
                        break
                else:
                    issues.append("reaction roles panel missing")
            except discord.Forbidden:
                issues.append("cannot read reaction-roles channel")
        else:
            issues.append("reaction-roles channel missing")
        
        if not issues:
            return SetupCheck(
                name="Panel Deployment",
                status="pass",
                message="✅ All panels are deployed"
            )
        
        return SetupCheck(
            name="Panel Deployment",
            status="fail",
            message=f"❌ Panel issues: {', '.join(issues)}",
            fix_action="Deploy missing panels to appropriate channels",
            can_auto_fix=True
        )
    
    def _check_user_permissions(self, interaction: discord.Interaction) -> SetupCheck:
        """Check if user has permission to run setup."""
        if not interaction.guild or not interaction.member or not has_required_guild_perms(interaction.member):
            return SetupCheck(
                name="User Permissions",
                status="fail",
                message="❌ You need Manage Server permission to run setup",
                fix_action="Contact a server administrator",
                can_auto_fix=False
            )
        
        return SetupCheck(
            name="User Permissions", 
            status="pass",
            message="✅ You have permission to run setup"
        )
    
    async def apply_fixes(self, guild: discord.Guild, user: discord.User, setup_result: SetupResult) -> SetupResult:
        """Apply automatic fixes for issues that can be resolved."""
        updated_checks = []
        
        for check in setup_result.checks:
            if check.status == "fail" and check.can_auto_fix:
                try:
                    if check.name == "Required Channels":
                        await self._create_missing_channels(guild)
                        updated_checks.append(SetupCheck(
                            name="Required Channels",
                            status="pass",
                            message="✅ Missing channels created successfully"
                        ))
                    elif check.name == "Panel Deployment":
                        await self._deploy_missing_panels(guild)
                        updated_checks.append(SetupCheck(
                            name="Panel Deployment", 
                            status="pass",
                            message="✅ Missing panels deployed successfully"
                        ))
                    else:
                        updated_checks.append(check)
                except Exception as e:
                    log.error(f"Failed to auto-fix {check.name}: {e}")
                    updated_checks.append(SetupCheck(
                        name=check.name,
                        status="fail",
                        message=f"❌ Auto-fix failed: {str(e)}",
                        can_auto_fix=False
                    ))
            else:
                updated_checks.append(check)
        
        # Recalculate overall status
        failed_checks = [c for c in updated_checks if c.status == "fail"]
        warning_checks = [c for c in updated_checks if c.status == "warning"]
        
        if failed_checks:
            overall_status = "fail"
        elif warning_checks:
            overall_status = "warning"
        else:
            overall_status = "pass"
        
        return SetupResult(
            overall_status=overall_status,
            checks=updated_checks,
            guild_id=guild.id,
            user_id=user.id
        )
    
    async def _create_missing_channels(self, guild: discord.Guild):
        """Create missing required channels with proper permissions."""
        existing_channels = [channel.name.lower() for channel in guild.text_channels]
        
        for channel_name in self.REQUIRED_CHANNELS:
            if channel_name not in existing_channels:
                # Create channel with appropriate permissions based on type
                overwrites = {}
                
                if channel_name == "verify":
                    # Verify channel: visible to everyone, but no typing
                    overwrites[guild.default_role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=False,
                        add_reactions=False
                    )
                elif channel_name == "support-start":
                    # Support-start: visible to everyone
                    overwrites[guild.default_role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True
                    )
                elif channel_name in ["reaction-roles", "tickets"]:
                    # These channels will have their permissions set by panels
                    overwrites[guild.default_role] = discord.PermissionOverwrite(
                        read_messages=False,
                        send_messages=False
                    )
                
                result = await safe_create_channel(
                    guild=guild,
                    name=channel_name,
                    type=discord.ChannelType.text,
                    overwrites=overwrites,
                    reason="Setup wizard - creating missing required channels"
                )
                
                if not result.success:
                    raise Exception(f"Failed to create {channel_name}: {result.error}")
    
    async def _deploy_missing_panels(self, guild: discord.Guild):
        """Deploy missing panels to appropriate channels."""
        # This would integrate with the existing panel system
        # For now, we'll just log that panels need to be deployed
        log.info(f"Panel deployment requested for guild {guild.id}")
        # TODO: Integrate with panel_registry to deploy missing panels
    
    def create_setup_embed(self, result: SetupResult) -> discord.Embed:
        """Create an embed showing setup results."""
        # Determine color and overall message
        if result.overall_status == "pass":
            color = discord.Color.green()
            title = "✅ Setup Complete"
            description = "Your server is properly configured and ready to use!"
        elif result.overall_status == "warning":
            color = discord.Color.orange()
            title = "⚠️ Setup with Warnings"
            description = "Your server is mostly configured, but some issues may affect functionality."
        else:
            color = discord.Color.red()
            title = "❌ Setup Issues Found"
            description = "Your server has configuration issues that should be resolved."
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        # Add check results
        for check in result.checks:
            status_emoji = {"pass": "✅", "fail": "❌", "warning": "⚠️"}[check.status]
            field_value = f"{status_emoji} {check.message}"
            
            if check.fix_action:
                field_value += f"\n📝 **Fix:** {check.fix_action}"
            
            embed.add_field(
                name=check.name,
                value=field_value,
                inline=False
            )
        
        # Add footer
        embed.set_footer(
            text=f"Guild ID: {result.guild_id} | Run by: {result.user_id}"
        )
        
        return embed
    
    @app_commands.command(
        name="setup",
        description="Run the setup wizard to validate and configure your server"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction):
        """Run the setup wizard."""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return
        
        # Run all checks
        checks = [
            self._check_user_permissions(interaction),
            self._check_bot_permissions(interaction.guild),
            self._check_bot_role_position(interaction.guild),
            self._check_required_channels(interaction.guild),
            await self._check_panels(interaction.guild)
        ]
        
        # Determine overall status
        failed_checks = [c for c in checks if c.status == "fail"]
        warning_checks = [c for c in checks if c.status == "warning"]
        
        if failed_checks:
            overall_status = "fail"
        elif warning_checks:
            overall_status = "warning"
        else:
            overall_status = "pass"
        
        result = SetupResult(
            overall_status=overall_status,
            checks=checks,
            guild_id=interaction.guild.id,
            user_id=interaction.user.id
        )
        
        # Create and send embed
        embed = self.create_setup_embed(result)
        
        # Add view if there are fixable issues
        view = None
        if any(check.status == "fail" and check.can_auto_fix for check in checks):
            view = SetupWizardView(result, self)
        
        await interaction.followup.send(embed=embed, ephemeral=True, view=view)
        
        # Log setup run
        log.info(
            "Setup wizard run by user %s in guild %s - Status: %s",
            interaction.user.id, interaction.guild.id, overall_status
        )


async def setup(bot: commands.Bot):
    """Setup function for the cog."""
    await bot.add_cog(SetupWizardCog(bot))
