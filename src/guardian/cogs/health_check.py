from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import logging
import time
from typing import Optional

from guardian.permissions import require_verified, validate_command_permissions, list_commands_by_tier

log = logging.getLogger("guardian.health_check")


class HealthCheckCog(commands.Cog):
    """Health check and diagnostics cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="health",
        description="Display bot health status and system information"
    )
    @require_verified()
    async def health(self, interaction: discord.Interaction):
        """Display comprehensive health status."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Check basic bot status
            bot_status = "✅ Online" if self.bot.is_ready() else "⚠️ Not Ready"
            
            # Count loaded cogs
            loaded_cogs = len(self.bot.cogs)
            
            # Count registered commands
            commands = list(self.bot.tree.get_commands())
            command_count = len(commands)
            
            # Check persistent views
            view_count = 0
            if hasattr(self.bot, '_persistent_views_stats'):
                stats = self.bot._persistent_views_stats
                view_count = stats['succeeded']
            elif hasattr(self.bot, 'persistent_views'):
                view_count = len(self.bot.persistent_views)
            
            # Check activity manager
            activity_status = "❌ Not Available"
            last_activity_time = "Unknown"
            activity_cog = self.bot.get_cog('ActivityCog')
            if activity_cog and hasattr(activity_cog, 'activity_manager'):
                activity_status = "✅ Available"
                if hasattr(activity_cog.activity_manager, '_last_activity_update'):
                    last_activity_time = time.strftime('%Y-%m-%d %H:%M:%S', 
                                                time.localtime(activity_cog.activity_manager._last_activity_update))
            
            # Check critical cogs
            critical_cogs = {
                'VerifyPanelCog': self.bot.get_cog('VerifyPanelCog') is not None,
                'RolePanelCog': self.bot.get_cog('RolePanelCog') is not None,
                'ActivityCog': self.bot.get_cog('ActivityCog') is not None,
                'TicketSystemCog': self.bot.get_cog('TicketSystemCog') is not None,
                'RoleAssignmentCog': self.bot.get_cog('RoleAssignmentCog') is not None,
                'HealthCheckCog': self.bot.get_cog('HealthCheckCog') is not None,
            }
            
            # Check critical commands
            critical_commands = {
                'verifypanel': any(cmd.name == 'verifypanel' for cmd in commands),
                'rolepanel': any(cmd.name == 'rolepanel' for cmd in commands),
                'activity': any(cmd.name == 'activity' for cmd in commands),
                'setup': any(cmd.name == 'setup' for cmd in commands),
            }
            
            # Create embed
            embed = discord.Embed(
                title="🏥 Guardian Bot Health Status",
                color=discord.Color.green() if self.bot.is_ready() else discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            
            # Basic status
            embed.add_field(
                name="🤖 Bot Status",
                value=f"**Status:** {bot_status}\n**Uptime:** {self._get_uptime()}",
                inline=False
            )
            
            # System counts
            embed.add_field(
                name="📊 System Overview",
                value=f"**Loaded Cogs:** {loaded_cogs}\n**Commands:** {command_count}\n**Persistent Views:** {view_count}",
                inline=False
            )
            
            # Activity manager status
            embed.add_field(
                name="🎯 Activity Manager",
                value=f"**Status:** {activity_status}\n**Last Update:** {last_activity_time}",
                inline=False
            )
            
            # Critical cogs status
            cog_status = []
            for cog_name, is_loaded in critical_cogs.items():
                status = "✅" if is_loaded else "❌"
                cog_status.append(f"{status} {cog_name}")
            
            embed.add_field(
                name="🔧 Critical Cogs",
                value="\n".join(cog_status),
                inline=False
            )
            
            # Critical commands status
            cmd_status = []
            for cmd_name, is_available in critical_commands.items():
                status = "✅" if is_available else "❌"
                cmd_status.append(f"{status} /{cmd_name}")
            
            embed.add_field(
                name="⚡ Critical Commands",
                value="\n".join(cmd_status),
                inline=False
            )
            
            # Permission validation
            validation_status = "✅" if validate_command_permissions() else "❌"
            embed.add_field(
                name="🔐 Permission Validation",
                value=f"{validation_status} Command permissions mapped",
                inline=False
            )
            
            # Command tier summary (only show to admins)
            if interaction.user.guild_permissions.administrator:
                tier_commands = list_commands_by_tier()
                tier_info = []
                for tier, commands in tier_commands.items():
                    tier_names = {
                        1: "Verified",
                        3: "Staff", 
                        4: "Admin",
                        5: "Owner",
                        6: "Root"
                    }
                    tier_name = tier_names.get(tier, f"Tier {tier}")
                    tier_info.append(f"**{tier_name}**: {len(commands)} commands")
                
                embed.add_field(
                    name="📊 Command Tiers",
                    value="\n".join(tier_info),
                    inline=False
                )
            
            # Overall health
            all_critical_loaded = all(critical_cogs.values())
            all_critical_commands = all(critical_commands.values())
            
            if all_critical_loaded and all_critical_commands:
                embed.color = discord.Color.green()
                embed.set_footer(text="🎉 All systems operational")
            else:
                embed.color = discord.Color.orange()
                embed.set_footer(text="⚠️ Some systems may be degraded")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            log.error(f"Health check failed: {e}")
            await interaction.followup.send(
                "❌ Health check failed. Check logs for details.",
                ephemeral=True
            )
    
    def _get_uptime(self) -> str:
        """Get formatted bot uptime."""
        if hasattr(self.bot, 'launch_time'):
            uptime = time.time() - self.bot.launch_time
            days = int(uptime // 86400)
            hours = int((uptime % 86400) // 3600)
            minutes = int((uptime % 3600) // 60)
            
            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
        else:
            return "Unknown"
    
    async def cog_load(self):
        """Set launch time when cog loads."""
        self.bot.launch_time = time.time()
        log.info("Health check cog loaded")


# Setup function
async def setup(bot: commands.Bot):
    """Setup the health check cog."""
    await bot.add_cog(HealthCheckCog(bot))
    log.info("Health check cog loaded")
