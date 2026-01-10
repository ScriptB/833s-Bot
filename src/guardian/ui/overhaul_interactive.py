from __future__ import annotations

import asyncio
from typing import Any, Optional

import discord
from discord import ui
from discord.ext import commands

from ..utils import safe_embed, success_embed, error_embed, warning_embed, info_embed
from ..constants import COLORS, DEFAULT_TIMEOUT_SECONDS

class OverhaulInteractiveView(ui.View):
    """Interactive UI for server overhaul customization and confirmation."""
    
    def __init__(self, cog: commands.Cog, guild: discord.Guild) -> None:
        super().__init__(timeout=DEFAULT_TIMEOUT_SECONDS)
        self.cog = cog
        self.guild = guild
        self.config = {
            "server_name": guild.name,
            "verification_level": "high",
            "default_notifications": "only_mentions",
            "content_filter": "all_members",
            "include_leveling": True,
            "include_reaction_roles": True,
            "include_welcome": True,
            "preserve_staff_roles": True,
            "create_vip_lounge": True,
            "create_gaming_category": True,
        }
        self.confirmed = False
        self.message: Optional[discord.Message] = None
        
    async def update_message(self) -> None:
        """Update the interaction message with current config."""
        if not self.message:
            return
            
        embed = self._create_config_embed()
        try:
            await self.message.edit(embed=embed, view=self)
        except:
            pass
    
    def _create_config_embed(self) -> discord.Embed:
        """Create embed showing current configuration."""
        embed = info_embed("⚡ Server Overhaul Configuration")
        embed.description = "Customize your server rebuild below, then confirm to execute."
        
        # Server Settings
        server_text = f"**Name:** {self.config['server_name']}\n"
        server_text += f"**Verification:** {self.config['verification_level'].title()}\n"
        server_text += f"**Filter:** {self.config['content_filter'].title()}"
        embed.add_field(name="🏰 Server Settings", value=server_text, inline=True)
        
        # Features
        features_text = ""
        if self.config['include_leveling']:
            features_text += "✅ Leveling System\n"
        if self.config['include_reaction_roles']:
            features_text += "✅ Reaction Roles\n"
        if self.config['include_welcome']:
            features_text += "✅ Welcome System\n"
        if self.config['create_vip_lounge']:
            features_text += "✅ VIP Lounge\n"
        if self.config['create_gaming_category']:
            features_text += "✅ Gaming Category\n"
            
        if not features_text:
            features_text = "❌ No features selected"
            
        embed.add_field(name="🎯 Features", value=features_text, inline=True)
        
        # Safety
        safety_text = ""
        if self.config['preserve_staff_roles']:
            safety_text += "✅ Preserve Staff Roles\n"
        safety_text += "✅ Backup Recommended\n"
        safety_text += "✅ Confirmation Required"
        
        embed.add_field(name="🛡️ Safety", value=safety_text, inline=True)
        
        # Warning
        if self.confirmed:
            embed.add_field(
                name="⚠️ READY TO EXECUTE",
                value="Click **Execute Overhaul** to start the rebuild. **THIS IS IRREVERSIBLE!**",
                inline=False
            )
        else:
            embed.add_field(
                name="ℹ️ Configuration",
                value="Customize settings below, then click **Confirm Configuration** to proceed.",
                inline=False
            )
        
        embed.set_footer(text="Click buttons to customize • Confirm when ready")
        return embed
    
    @ui.button(label="Server Settings", style=discord.ButtonStyle.secondary, row=0)
    async def server_settings(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Open server settings modal."""
        modal = ServerSettingsModal(self.config)
        await interaction.response.send_modal(modal)
        await modal.wait()
        await self.update_message()
    
    @ui.button(label="Features", style=discord.ButtonStyle.secondary, row=0)
    async def features(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Open features selection modal."""
        modal = FeaturesModal(self.config)
        await interaction.response.send_modal(modal)
        await modal.wait()
        await self.update_message()
    
    @ui.button(label="Safety Options", style=discord.ButtonStyle.secondary, row=1)
    async def safety_options(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Open safety options modal."""
        modal = SafetyModal(self.config)
        await interaction.response.send_modal(modal)
        await modal.wait()
        await self.update_message()
    
    @ui.button(label="Confirm Configuration", style=discord.ButtonStyle.success, row=2)
    async def confirm_config(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Confirm the configuration."""
        if self.confirmed:
            await interaction.response.send_message("Configuration already confirmed!", ephemeral=True)
            return
            
        self.confirmed = True
        await self.update_message()
        await interaction.response.send_message("✅ Configuration confirmed! Click **Execute Overhaul** to start.", ephemeral=True)
    
    @ui.button(label="Execute Overhaul", style=discord.ButtonStyle.danger, row=2)
    async def execute_overhaul(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Execute the overhaul with current configuration."""
        if not self.confirmed:
            await interaction.response.send_message("❌ Please confirm configuration first!", ephemeral=True)
            return
            
        # Disable all buttons
        for child in self.children:
            child.disabled = True
        await self.update_message()
        
        await interaction.response.send_message("🚀 Starting server overhaul...", ephemeral=True)
        
        # Import and execute overhaul
        from .overhaul_executor_v2 import OverhaulExecutorV2
        
        try:
            # Create config based on selections
            final_config = self._build_final_config()
            executor = OverhaulExecutorV2(self.cog, self.guild, final_config)
            executor.progress_user = interaction.user  # Set progress recipient
            
            result = await executor.run()
            
            await interaction.followup.send(
                embed=success_embed(f"✅ {result}"),
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(
                embed=error_embed(f"❌ Overhaul failed: {e}"),
                ephemeral=True
            )
    
    @ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=3)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Cancel the overhaul."""
        self.stop()
        await self.message.edit(
            embed=warning_embed("❌ Server overhaul cancelled."),
            view=None
        )
        await interaction.response.send_message("Overhaul cancelled.", ephemeral=True)
    
    def _build_final_config(self) -> dict[str, Any]:
        """Build final configuration based on selections."""
        config = {
            "server_name": self.config["server_name"],
            "verification_level": self.config["verification_level"],
            "default_notifications": self.config["default_notifications"],
            "content_filter": self.config["content_filter"],
        }
        
        # Add roles based on features
        roles = [
            {"name": "Verified", "color": "green", "hoist": False, "mentionable": False},
            {"name": "Member", "color": "blue", "hoist": False, "mentionable": False},
            {"name": "Muted", "color": "red", "hoist": False, "mentionable": False},
        ]
        
        if self.config["include_leveling"]:
            level_roles = [
                {"name": "Bronze", "color": "brown", "hoist": True, "mentionable": False},
                {"name": "Silver", "color": "greyple", "hoist": True, "mentionable": False},
                {"name": "Gold", "color": "gold", "hoist": True, "mentionable": False},
                {"name": "Platinum", "color": "white", "hoist": True, "mentionable": False},
                {"name": "Diamond", "color": "cyan", "hoist": True, "mentionable": False},
            ]
            roles.extend(level_roles)
        
        if self.config["create_vip_lounge"]:
            roles.append({"name": "VIP", "color": "purple", "hoist": True, "mentionable": True})
        
        config["roles"] = roles
        
        # Add categories based on features
        categories = [
            {
                "name": "📢 INFORMATION",
                "channels": [
                    {"name": "📋-rules", "kind": "text"},
                    {"name": "📢-announcements", "kind": "text"},
                ]
            },
            {
                "name": "💬 GENERAL",
                "channels": [
                    {"name": "💬-general", "kind": "text"},
                    {"name": "🤖-commands", "kind": "text"},
                    {"name": "General", "kind": "voice"},
                ]
            },
            {
                "name": "🔊 VOICE",
                "channels": [
                    {"name": "AFK", "kind": "voice"},
                ]
            }
        ]
        
        if self.config["include_welcome"]:
            categories[0]["channels"].append({"name": "🎉-welcome", "kind": "text"})
        
        if self.config["include_reaction_roles"]:
            categories[1]["channels"].append({"name": "🎭-reaction-roles", "kind": "text"})
        
        if self.config["create_gaming_category"]:
            categories.append({
                "name": "🎮 GAMING",
                "channels": [
                    {"name": "🎮-gaming", "kind": "text"},
                    {"name": "🏆-tournaments", "kind": "text"},
                    {"name": "Gaming", "kind": "voice"},
                ]
            })
        
        if self.config["create_vip_lounge"]:
            categories[2]["channels"].append({"name": "VIP Lounge", "kind": "voice"})
        
        config["categories"] = categories
        
        # Add reaction roles config
        if self.config["include_reaction_roles"]:
            config.update({
                "reaction_roles_channel": "🎭-reaction-roles",
                "reaction_roles_message_title": "🎭 Reaction Roles",
                "reaction_roles_message_description": "React with emojis to get corresponding roles!",
            })
        
        return config


class ServerSettingsModal(ui.Modal, title="Server Settings"):
    """Modal for configuring server settings."""
    
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(timeout=300)
        self.config = config
        
        self.server_name = ui.TextInput(
            label="Server Name",
            placeholder="Enter server name",
            default=config["server_name"],
            required=True,
            max_length=100,
            style=discord.TextStyle.short,
            row=0
        )
        
        self.verification_level = ui.TextInput(
            label="Verification Level",
            placeholder="high",
            default=config["verification_level"],
            required=False,
            max_length=20,
            style=discord.TextStyle.short,
            row=1
        )
        
        self.content_filter = ui.TextInput(
            label="Content Filter",
            placeholder="all_members",
            default=config["content_filter"],
            required=False,
            max_length=20,
            style=discord.TextStyle.short,
            row=2
        )
        
        self.add_item(self.server_name)
        self.add_item(self.verification_level)
        self.add_item(self.content_filter)
    
    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission."""
        self.config["server_name"] = self.server_name.value or self.config["server_name"]
        self.config["verification_level"] = self.verification_level.value or self.config["verification_level"]
        self.config["content_filter"] = self.content_filter.value or self.config["content_filter"]
        
        await interaction.response.send_message("✅ Server settings updated!", ephemeral=True)


class FeaturesModal(ui.Modal, title="Features Selection"):
    """Modal for selecting features."""
    
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(timeout=300)
        self.config = config
        
        self.features_text = ui.TextInput(
            label="Features (comma separated)",
            placeholder="leveling, reaction_roles, welcome, vip_lounge, gaming",
            default=self._get_features_string(),
            required=False,
            max_length=200,
            style=discord.TextStyle.paragraph,
            row=0
        )
        
        self.add_item(self.features_text)
    
    def _get_features_string(self) -> str:
        """Get current features as string."""
        features = []
        if self.config["include_leveling"]:
            features.append("leveling")
        if self.config["include_reaction_roles"]:
            features.append("reaction_roles")
        if self.config["include_welcome"]:
            features.append("welcome")
        if self.config["create_vip_lounge"]:
            features.append("vip_lounge")
        if self.config["create_gaming_category"]:
            features.append("gaming")
        return ", ".join(features)
    
    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission."""
        text = self.features_text.value or ""
        features = [f.strip().lower() for f in text.split(",") if f.strip()]
        
        self.config["include_leveling"] = "leveling" in features
        self.config["include_reaction_roles"] = "reaction_roles" in features
        self.config["include_welcome"] = "welcome" in features
        self.config["create_vip_lounge"] = "vip_lounge" in features
        self.config["create_gaming_category"] = "gaming" in features
        
        await interaction.response.send_message("✅ Features updated!", ephemeral=True)


class SafetyModal(ui.Modal, title="Safety Options"):
    """Modal for configuring safety options."""
    
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(timeout=300)
        self.config = config
        
        self.safety_text = ui.TextInput(
            label="Safety Options (comma separated)",
            placeholder="preserve_staff_roles, backup_required",
            default=self._get_safety_string(),
            required=False,
            max_length=200,
            style=discord.TextStyle.paragraph,
            row=0
        )
        
        self.add_item(self.safety_text)
    
    def _get_safety_string(self) -> str:
        """Get current safety options as string."""
        options = []
        if self.config["preserve_staff_roles"]:
            options.append("preserve_staff_roles")
        options.append("backup_required")  # Always included
        return ", ".join(options)
    
    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission."""
        text = self.safety_text.value or ""
        options = [f.strip().lower() for f in text.split(",") if f.strip()]
        
        self.config["preserve_staff_roles"] = "preserve_staff_roles" in options
        
        await interaction.response.send_message("✅ Safety options updated!", ephemeral=True)
