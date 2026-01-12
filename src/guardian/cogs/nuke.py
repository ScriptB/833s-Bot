"""
Nuke Command Cog

Provides a UI-based command to selectively delete multiple channels and categories.
"""

from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View

from ..security.auth import root_only

log = logging.getLogger("guardian.nuke")


class ChannelSelectView(View):
    """View for selecting channels and categories to delete."""
    
    def __init__(self, guild: discord.Guild, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.guild = guild
        self.selected_channels: set[int] = set()
        self.selected_categories: set[int] = set()
        self.confirmed = False
        
        # Create select menus
        self._create_select_menus()
    
    def _create_select_menus(self):
        """Create channel and category selection menus."""
        # Category select
        categories = []
        for cat in sorted(self.guild.categories, key=lambda c: c.position):
            categories.append(discord.SelectOption(
                label=f"📁 {cat.name}",
                description=f"Category: {cat.name}",
                value=f"cat_{cat.id}"
            ))
        
        if categories:
            self.add_item(Select(
                placeholder="📁 Select categories to delete...",
                options=categories[:25],  # Discord limit
                custom_id="category_select",
                min_values=0,
                max_values=min(25, len(categories))
            ))
        
        # Channel select (excluding those in categories that might be deleted)
        channels = []
        for channel in sorted(self.guild.text_channels + self.guild.voice_channels, key=lambda c: c.position):
            if not channel.category or channel.category.id not in self.selected_categories:
                channel_type = "#️⃣" if isinstance(channel, discord.TextChannel) else "🔊"
                channels.append(discord.SelectOption(
                    label=f"{channel_type} {channel.name}",
                    description=f"Channel: {channel.name}",
                    value=f"chan_{channel.id}"
                ))
        
        if channels:
            self.add_item(Select(
                placeholder="📢 Select channels to delete...",
                options=channels[:25],  # Discord limit
                custom_id="channel_select",
                min_values=0,
                max_values=min(25, len(channels))
            ))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to use this command."""
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ You need **Manage Channels** permission to use this command.",
                ephemeral=True
            )
            return False
        return True
    
    async def on_timeout(self) -> None:
        """Handle view timeout."""
        for item in self.children:
            item.disabled = True
    
    @discord.ui.select(custom_id="category_select", placeholder="Select categories...")
    async def category_select_callback(self, interaction: discord.Interaction, select: Select):
        """Handle category selection."""
        await interaction.response.defer()
        
        # Update selected categories
        self.selected_categories.clear()
        for value in select.values:
            if value.startswith("cat_"):
                self.selected_categories.add(int(value[4:]))
        
        # Refresh channel select to exclude channels in selected categories
        self._refresh_channel_select()
        
        # Update the view
        await interaction.edit_original_response(view=self)
    
    @discord.ui.select(custom_id="channel_select", placeholder="Select channels...")
    async def channel_select_callback(self, interaction: discord.Interaction, select: Select):
        """Handle channel selection."""
        await interaction.response.defer()
        
        # Update selected channels
        self.selected_channels.clear()
        for value in select.values:
            if value.startswith("chan_"):
                self.selected_channels.add(int(value[5:]))
        
        # Update the view
        await interaction.edit_original_response(view=self)
    
    def _refresh_channel_select(self):
        """Refresh channel select menu to exclude channels in selected categories."""
        # Remove existing channel select
        for item in self.children:
            if item.custom_id == "channel_select":
                self.remove_item(item)
                break
        
        # Recreate channel options
        channels = []
        for channel in sorted(self.guild.text_channels + self.guild.voice_channels, key=lambda c: c.position):
            if not channel.category or channel.category.id not in self.selected_categories:
                channel_type = "#️⃣" if isinstance(channel, discord.TextChannel) else "🔊"
                channels.append(discord.SelectOption(
                    label=f"{channel_type} {channel.name}",
                    description=f"Channel: {channel.name}",
                    value=f"chan_{channel.id}"
                ))
        
        if channels:
            self.add_item(Select(
                placeholder="📢 Select channels to delete...",
                options=channels[:25],
                custom_id="channel_select",
                min_values=0,
                max_values=min(25, len(channels))
            ))
    
    @discord.ui.button(label="🗑️ NUKE SELECTED", style=discord.ButtonStyle.danger, row=4)
    async def nuke_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle nuke confirmation."""
        if not self.selected_channels and not self.selected_categories:
            await interaction.response.send_message(
                "❌ Please select at least one channel or category to delete.",
                ephemeral=True
            )
            return
        
        # Create confirmation view
        confirm_view = ConfirmationView(
            self.selected_channels,
            self.selected_categories,
            self.guild
        )
        
        # Count items to delete
        total_items = len(self.selected_channels) + len(self.selected_categories)
        
        embed = discord.Embed(
            title="⚠️ CONFIRM DELETION",
            description=(
                f"You are about to delete **{total_items}** items:\n\n"
                f"📁 **Categories:** {len(self.selected_categories)}\n"
                f"📢 **Channels:** {len(self.selected_channels)}\n\n"
                "**This action CANNOT be undone!**"
            ),
            color=discord.Color.red()
        )
        
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
    
    @discord.ui.button(label="❌ CANCEL", style=discord.ButtonStyle.secondary, row=4)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle cancellation."""
        await interaction.response.send_message(
            "❌ Nuke operation cancelled.",
            ephemeral=True
        )
        self.stop()


class ConfirmationView(View):
    """Confirmation view for nuke operation."""
    
    def __init__(self, channels: set[int], categories: set[int], guild: discord.Guild):
        super().__init__(timeout=60.0)
        self.channels = channels
        self.categories = categories
        self.guild = guild
        self.confirmed = False
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission."""
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ You need **Manage Channels** permission to confirm this action.",
                ephemeral=True
            )
            return False
        return True
    
    @discord.ui.button(label="☢️ YES, DELETE EVERYTHING", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Execute the deletion."""
        if self.confirmed:
            await interaction.response.send_message(
                "❌ This operation has already been confirmed.",
                ephemeral=True
            )
            return
        
        self.confirmed = True
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.response.defer(ephemeral=True)
        
        # Execute deletions
        deleted_count = 0
        failed_count = 0
        errors = []
        
        # Delete categories first (this also deletes channels within them)
        for cat_id in self.categories:
            try:
                category = self.guild.get_channel(cat_id)
                if category:
                    await category.delete(reason="Nuke command execution")
                    deleted_count += 1
                    log.info(f"Deleted category: {category.name}")
            except Exception as e:
                failed_count += 1
                errors.append(f"Category {cat_id}: {e}")
                log.error(f"Failed to delete category {cat_id}: {e}")
        
        # Delete individual channels
        for chan_id in self.channels:
            try:
                channel = self.guild.get_channel(chan_id)
                if channel:
                    await channel.delete(reason="Nuke command execution")
                    deleted_count += 1
                    log.info(f"Deleted channel: {channel.name}")
            except Exception as e:
                failed_count += 1
                errors.append(f"Channel {chan_id}: {e}")
                log.error(f"Failed to delete channel {chan_id}: {e}")
        
        # Send completion message
        embed = discord.Embed(
            title="🗑️ NUKE COMPLETED",
            description=(
                f"✅ **Successfully deleted:** {deleted_count}\n"
                f"❌ **Failed to delete:** {failed_count}"
            ),
            color=discord.Color.green() if failed_count == 0 else discord.Color.orange()
        )
        
        if errors:
            error_text = "\n".join(errors[:5])  # Limit to first 5 errors
            if len(errors) > 5:
                error_text += f"\n... and {len(errors) - 5} more errors"
            embed.add_field(name="Errors", value=f"```{error_text}```", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        self.stop()


class NukeCog(commands.Cog):
    """Nuke command cog for selective channel/category deletion."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
    
    @app_commands.command(
        name="nuke",
        description="Selectively delete multiple channels and categories"
    )
    @root_only()
    async def nuke(self, interaction: discord.Interaction) -> None:
        """Execute nuke command with channel selection UI."""
        
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return
        
        guild = interaction.guild
        
        # Check if user has permission
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ You need **Manage Channels** permission to use this command.",
                ephemeral=True
            )
            return
        
        # Create selection view
        view = ChannelSelectView(guild)
        
        embed = discord.Embed(
            title="🗑️ CHANNEL/CATEGORY NUKE",
            description=(
                "Select the channels and categories you want to delete.\n\n"
                "📁 **Categories** will delete all channels within them\n"
                "📢 **Channels** will be deleted individually\n\n"
                "**This action is permanent and cannot be undone!**"
            ),
            color=discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Setup the nuke cog."""
    await bot.add_cog(NukeCog(bot))
