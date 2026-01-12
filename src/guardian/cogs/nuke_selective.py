"""Selective Nuke Command Cog - BOT OWNER ONLY"""
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import string
import logging
import io
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

class SelectiveNukeCog(commands.Cog):
    """Selective nuke commands for bot owner only"""
    
    def __init__(self, bot):
        self.bot = bot
        self._confirmation_cache = {}  # {(guild_id, user_id): (code, expires)}
    
    def _is_bot_owner(self, user: discord.User) -> bool:
        """Check if user is bot owner"""
        return user.id == self.bot.owner_id
    
    def _generate_confirmation_code(self) -> str:
        """Generate 6-character confirmation code"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    def _store_confirmation_code(self, guild_id: int, user_id: int, code: str):
        """Store confirmation code with 5-minute expiry"""
        expires = datetime.utcnow() + timedelta(minutes=5)
        self._confirmation_cache[(guild_id, user_id)] = (code, expires)
    
    def _verify_confirmation_code(self, guild_id: int, user_id: int, code: str) -> bool:
        """Verify confirmation code"""
        key = (guild_id, user_id)
        if key not in self._confirmation_cache:
            return False
        
        stored_code, expires = self._confirmation_cache[key]
        if datetime.utcnow() > expires:
            del self._confirmation_cache[key]
            return False
        
        return stored_code.upper() == code.upper()
    
    def _cleanup_expired_codes(self):
        """Clean up expired confirmation codes"""
        now = datetime.utcnow()
        expired_keys = [
            key for key, (_, expires) in self._confirmation_cache.items()
            if now > expires
        ]
        for key in expired_keys:
            del self._confirmation_cache[key]
    
    @app_commands.command(name="nuke", description="Selective category/channel deletion (BOT OWNER ONLY)")
    @app_commands.describe(
        categories="Comma-separated category names or IDs",
        channels="Comma-separated channel IDs", 
        reason="Reason for deletion (optional)",
        confirm="Set to true to execute, false to preview only",
        code="Confirmation code (required when confirm=true)"
    )
    async def nuke(
        self, 
        interaction: discord.Interaction,
        categories: str = "",
        channels: str = "",
        reason: str = "",
        confirm: bool = False,
        code: str = ""
    ):
        """Selective nuke command"""
        
        # Bot owner check
        if not self._is_bot_owner(interaction.user):
            await interaction.response.send_message("This command is restricted to the bot owner only.", ephemeral=True)
            return
        
        # Parse inputs
        category_names_or_ids = [item.strip() for item in categories.split(",") if item.strip()] if categories else []
        channel_ids = [item.strip() for item in channels.split(",") if item.strip()] if channels else []
        
        if not category_names_or_ids and not channel_ids:
            await interaction.response.send_message("You must specify at least one category or channel to delete.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild = interaction.guild
            if not guild:
                await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
                return
            
            # Find targets
            categories_to_delete = []
            channels_to_delete = []
            
            # Process categories
            for item in category_names_or_ids:
                if item.isdigit():
                    # Treat as ID
                    category = guild.get_channel(int(item))
                    if category and isinstance(category, discord.CategoryChannel):
                        categories_to_delete.append(category)
                else:
                    # Treat as name (exact match first, then case-insensitive)
                    found = None
                    for cat in guild.categories:
                        if cat.name == item:
                            found = cat
                            break
                    if not found:
                        for cat in guild.categories:
                            if cat.name.lower() == item.lower():
                                found = cat
                                break
                    if found:
                        categories_to_delete.append(found)
            
            # Process channels
            for channel_id in channel_ids:
                if channel_id.isdigit():
                    channel = guild.get_channel(int(channel_id))
                    if channel:
                        channels_to_delete.append(channel)
            
            if not categories_to_delete and not channels_to_delete:
                await interaction.followup.send("No valid categories or channels found.", ephemeral=True)
                return
            
            # Collect all channels that will be deleted (including category children)
            all_channels_to_delete = set(channels_to_delete)
            for category in categories_to_delete:
                for channel in category.channels:
                    all_channels_to_delete.add(channel)
            
            # Safety checks
            warnings = []
            
            # Check for channels being used
            execution_channel = interaction.channel
            if execution_channel in all_channels_to_delete:
                warnings.append("⚠️ Cannot delete the channel this command is running in")
            
            # Check for managed/system channels
            for channel in all_channels_to_delete:
                if channel.managed:
                    warnings.append(f"⚠️ {channel.mention} is a managed channel and may not be deletable")
            
            # Handle confirmation logic
            if confirm:
                # Verify confirmation code if provided
                if not code:
                    await interaction.followup.send("Confirmation code is required when confirm=true.", ephemeral=True)
                    return
                
                if not self._verify_confirmation_code(guild.id, interaction.user.id, code):
                    await interaction.followup.send("Invalid or expired confirmation code.", ephemeral=True)
                    return
                
                # Execute nuke
                await self._execute_nuke(interaction, categories_to_delete, channels_to_delete, all_channels_to_delete, reason)
            else:
                # Show preview
                await self._show_preview(interaction, categories_to_delete, channels_to_delete, all_channels_to_delete, warnings, categories, channels)
        
        except Exception as e:
            log.exception("Error in nuke command")
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
    
    async def _show_preview(self, interaction, categories_to_delete, channels_to_delete, all_channels_to_delete, warnings, categories_param, channels_param):
        """Show nuke preview"""
        plan_lines = [
            "📋 **NUKE PREVIEW**",
            "",
            f"**Categories to delete:** {len(categories_to_delete)}",
            f"**Channels to delete:** {len(all_channels_to_delete)}",
            ""
        ]
        
        if categories_to_delete:
            plan_lines.append("**Categories:**")
            for cat in categories_to_delete:
                plan_lines.append(f"• {cat.name} (ID: {cat.id}) - {len(cat.channels)} channels")
            plan_lines.append("")
        
        if channels_to_delete:
            plan_lines.append("**Individual Channels:**")
            for ch in channels_to_delete:
                plan_lines.append(f"• {ch.name} (ID: {ch.id}) - {ch.type}")
            plan_lines.append("")
        
        if warnings:
            plan_lines.append("**⚠️ Warnings:**")
            plan_lines.extend(warnings)
            plan_lines.append("")
        
        # Generate confirmation code for next step
        confirmation_code = self._generate_confirmation_code()
        self._store_confirmation_code(interaction.guild.id, interaction.user.id, confirmation_code)
        
        plan_lines.extend([
            "**🔒 CONFIRMATION REQUIRED**",
            f"Your confirmation code: **{confirmation_code}**",
            "This code expires in 5 minutes.",
            "",
            f"To execute the nuke, run:",
            f"`/nuke categories:{categories_param} channels:{channels_param} confirm:true code:{confirmation_code}`"
        ])
        
        plan_text = "\n".join(plan_lines)
        if len(plan_text) > 1900:
            # Send as file if too long
            await interaction.followup.send(file=discord.File(
                fp=io.BytesIO(plan_text.encode()),
                filename="nuke_plan.txt"
            ), ephemeral=True)
        else:
            await interaction.followup.send(plan_text, ephemeral=True)
    
    async def _execute_nuke(self, interaction, categories_to_delete, channels_to_delete, all_channels_to_delete, reason):
        """Execute the nuke operation"""
        await interaction.followup.send("🔥 **NUKE EXECUTION STARTED**", ephemeral=True)
        
        deleted_categories = 0
        deleted_channels = 0
        failures = []
        
        # Use semaphore for rate limiting
        semaphore = asyncio.Semaphore(1)  # One at a time to avoid rate limits
        
        async def delete_with_semaphore(item):
            async with semaphore:
                await asyncio.sleep(random.uniform(0.25, 0.75))  # Jitter
                try:
                    if isinstance(item, discord.CategoryChannel):
                        await item.delete(reason=reason)
                        return "category", item.id
                    else:
                        await item.delete(reason=reason)
                        return "channel", item.id
                except discord.Forbidden:
                    return "error", f"Forbidden: {item.id}"
                except discord.NotFound:
                    return "error", f"Not found: {item.id}"
                except discord.HTTPException as e:
                    return "error", f"HTTP error: {item.id} - {str(e)}"
                except Exception as e:
                    return "error", f"Unexpected: {item.id} - {str(e)}"
        
        # Execute deletions
        tasks = []
        for item in categories_to_delete + channels_to_delete:
            tasks.append(delete_with_semaphore(item))
        
        results = await asyncio.gather(tasks, return_exceptions=True)
        
        # Process results
        for result in results:
            if isinstance(result, Exception):
                failures.append(f"Task exception: {str(result)}")
            else:
                item_type, item_id = result
                if item_type == "category":
                    deleted_categories += 1
                elif item_type == "channel":
                    deleted_channels += 1
                else:
                    failures.append(item_id)
        
        # Send final report
        report_lines = [
            "🏁️ **NUKE COMPLETE**",
            "",
            f"✅ Deleted categories: {deleted_categories}",
            f"✅ Deleted channels: {deleted_channels}",
            f"❌ Failures: {len(failures)}"
        ]
        
        if failures:
            report_lines.append("")
            report_lines.append("**Failed items:**")
            report_lines.extend(failures[:10])  # Limit to first 10
            if len(failures) > 10:
                report_lines.append(f"... and {len(failures) - 10} more")
        
        report_text = "\n".join(report_lines)
        if len(report_text) > 1900:
            await interaction.followup.send(
                content="🏁️ **NUKE COMPLETE** (see attached file for details)",
                file=discord.File(
                    fp=io.BytesIO(report_text.encode()),
                    filename="nuke_report.txt"
                ),
                ephemeral=True
            )
        else:
            await interaction.followup.send(report_text, ephemeral=True)
        
        log.info(f"Nuke executed by {interaction.user} in {interaction.guild}: {deleted_categories} categories, {deleted_channels} channels, {len(failures)} failures")
    
    @nuke.error
    async def nuke_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        """Error handler for nuke command"""
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"This command is on cooldown. Try again in {error.retry_after:.2f} seconds.", ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)


async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(SelectiveNukeCog(bot))
    log.info("SelectiveNukeCog loaded")
