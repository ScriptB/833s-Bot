from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import discord

from ..interfaces import has_required_guild_perms, sanitize_user_text, validate_panel_store

log = logging.getLogger("guardian.panel_registry")


class PanelRegistry:
    """Registry for managing persistent UI panels with self-healing capabilities."""
    
    def __init__(self, bot: discord.Client, panel_store):
        self.bot = bot
        self.panel_store = panel_store
        self._renderers: dict[str, Callable] = {}
        
        # Validate interface compliance
        validate_panel_store(panel_store)
        self._fallback_channels: dict[str, str] = {
            "verify_panel": "verify",
            "role_panel": "roles", 
            "ticket_panel": "tickets"
        }
    
    def register_renderer(self, panel_key: str, renderer: Callable) -> None:
        """Register a render function for a panel type."""
        self._renderers[panel_key] = renderer
        log.info(f"Registered renderer for panel: {panel_key}")
    
    async def render_panel(self, panel_key: str, guild: discord.Guild) -> tuple[discord.Embed, discord.ui.View]:
        """Render a panel using its registered renderer."""
        if panel_key not in self._renderers:
            raise ValueError(f"No renderer registered for panel: {panel_key}")
        
        renderer = self._renderers[panel_key]
        return await renderer(guild)
    
    async def deploy_panel(self, panel_key: str, guild: discord.Guild, 
                          target_channel: discord.TextChannel | None = None) -> discord.Message | None:
        """Deploy a panel to a channel and store the record."""
        try:
            # Check permissions
            has_perms, missing = has_required_guild_perms(guild.me)
            if not has_perms:
                log.warning(f"Missing permissions for panel deploy {panel_key} in guild {guild.id}: {missing}")
                return None
            
            # Get or find target channel
            if target_channel is None:
                channel_name = self._fallback_channels.get(panel_key, f"{panel_key}")
                target_channel = discord.utils.get(guild.text_channels, name=channel_name)
                
                if not target_channel:
                    log.warning(f"Channel '{channel_name}' not found for panel {panel_key} in guild {guild.id}")
                    return None
            
            # Render panel
            embed, view = await self.render_panel(panel_key, guild)
            
            # Sanitize any user-facing text
            if embed.title:
                embed.title = sanitize_user_text(embed.title)
            if embed.description:
                embed.description = sanitize_user_text(embed.description)
            
            # Send message
            message = await target_channel.send(embed=embed, view=view)
            
            # Store record
            await self.panel_store.upsert(
                guild_id=guild.id,
                panel_key=panel_key,
                channel_id=target_channel.id,
                message_id=message.id,
                schema_version=1
            )
            
            log.info(f"Deployed panel {panel_key} to guild {guild.id}, channel {target_channel.id}, message {message.id}")
            return message
            
        except Exception as e:
            log.error(f"Failed to deploy panel {panel_key} in guild {guild.id}: {e}")
            return None
    
    async def repair_panel(self, guild_id: int, panel_key: str) -> bool:
        """Repair a single panel in a guild."""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                log.warning(f"Guild {guild_id} not found for panel repair")
                return False
            
            # Get stored panel record
            record = await self.panel_store.get(guild_id, panel_key)
            if not record:
                log.info(f"No record found for panel {panel_key} in guild {guild_id}")
                return False
            
            # Try to fetch existing message
            try:
                channel = guild.get_channel(record.channel_id)
                if not isinstance(channel, discord.TextChannel):
                    log.warning(f"Channel {record.channel_id} not found or not text channel for panel {panel_key}")
                    return await self._redeploy_panel(guild_id, panel_key)
                
                message = await channel.fetch_message(record.message_id)
                if not message:
                    log.warning(f"Message {record.message_id} not found for panel {panel_key}")
                    return await self._redeploy_panel(guild_id, panel_key)
                
                # Message exists - update embed and view
                embed, view = await self.render_panel(panel_key, guild)
                await message.edit(embed=embed, view=view, attachments=[])
                
                log.info(f"Repaired panel {panel_key} in guild {guild_id}")
                return True
                
            except discord.NotFound:
                log.warning(f"Panel {panel_key} message not found in guild {guild_id}, attempting redeploy")
                return await self._redeploy_panel(guild_id, panel_key)
            except discord.Forbidden:
                log.error(f"Permission denied accessing panel {panel_key} in guild {guild_id}")
                return False
                
        except Exception as e:
            log.exception(f"Failed to repair panel {panel_key} in guild {guild_id}: {e}")
            return False
    
    async def _redeploy_panel(self, guild_id: int, panel_key: str) -> bool:
        """Redeploy a panel to its fallback channel."""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return False
            
            message = await self.deploy_panel(panel_key, guild)
            return message is not None
            
        except Exception as e:
            log.exception(f"Failed to redeploy panel {panel_key} in guild {guild_id}: {e}")
            return False
    
    async def repair_all_guilds_on_startup(self) -> dict[str, Any]:
        """Repair all panels across all guilds during startup."""
        results = {
            "total_panels": 0,
            "repaired": 0,
            "failed": 0,
            "errors": []
        }
        
        try:
            # Get all panels with error handling
            try:
                all_panels = await self.panel_store.list_all_panels()
                results["total_panels"] = len(all_panels)
            except Exception as e:
                log.error(f"Failed to list panels for repair: {e}")
                results["errors"].append("Database unavailable - skipping panel repair")
                return results
            
            # Group by guild for efficiency
            guild_panels = {}
            for panel in all_panels:
                if panel.guild_id not in guild_panels:
                    guild_panels[panel.guild_id] = []
                guild_panels[panel.guild_id].append(panel)
            
            # Repair each guild's panels with individual error handling
            for guild_id, panels in guild_panels.items():
                try:
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        log.warning(f"Guild {guild_id} not found during startup repair")
                        results["failed"] += len(panels)
                        continue
                    
                    for panel in panels:
                        success = await self.repair_panel(guild_id, panel.panel_key)
                        if success:
                            results["repaired"] += 1
                        else:
                            results["failed"] += 1
                            
                except Exception as e:
                    log.error(f"Failed to repair panels for guild {guild_id}: {e}")
                    results["failed"] += len(panels)
                    results["errors"].append(f"Guild {guild_id} repair failed")
                        
        except Exception as e:
            log.error(f"Critical error during panel repair startup: {e}")
            results["errors"].append("Critical repair failure")
        
        return results
    
    async def force_redeploy_panel(self, guild_id: int, panel_key: str) -> dict[str, Any]:
        """Force redeploy a panel (admin command)."""
        result = {
            "success": False,
            "message": "",
            "old_message_id": None,
            "new_message_id": None
        }
        
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                result["message"] = "Guild not found"
                return result
            
            # Get existing record
            record = await self.panel_store.get(guild_id, panel_key)
            if record:
                result["old_message_id"] = record.message_id
            
            # Deploy new panel
            message = await self.deploy_panel(panel_key, guild)
            if message:
                result["success"] = True
                result["message"] = f"Panel {panel_key} redeployed successfully"
                result["new_message_id"] = message.id
            else:
                result["message"] = f"Failed to deploy panel {panel_key}"
                
        except Exception as e:
            log.exception(f"Force redeploy failed for panel {panel_key} in guild {guild_id}: {e}")
            result["message"] = f"Error: {e}"
        
        return result
