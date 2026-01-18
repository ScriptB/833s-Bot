from __future__ import annotations

import discord
from typing import Dict, Any, Optional, Callable, List
import logging
from dataclasses import dataclass
from datetime import datetime

from .api_wrapper import safe_send_message, safe_edit_message, APIResult
from ..interfaces import validate_panel_store, has_required_guild_perms, sanitize_user_text

log = logging.getLogger("guardian.enhanced_panel_registry")


@dataclass
class PanelConfig:
    """Configuration for a persistent panel."""
    panel_key: str
    channel_name: str
    custom_id: str
    timeout: Optional[float] = None  # None for persistent
    required_permissions: List[str] = None
    
    def __post_init__(self):
        if self.required_permissions is None:
            self.required_permissions = ["send_messages", "embed_links"]


class EnhancedPanelRegistry:
    """Enhanced panel registry with commercial-grade persistence."""
    
    def __init__(self, bot: discord.Client, panel_store):
        self.bot = bot
        self.panel_store = panel_store
        self._renderers: Dict[str, Callable] = {}
        self._panel_configs: Dict[str, PanelConfig] = {}
        
        # Validate interface compliance
        validate_panel_store(panel_store)
        
        # Register standard panel configurations
        self._register_standard_configs()
    
    def _register_standard_configs(self):
        """Register standard panel configurations with stable custom_ids."""
        self._panel_configs.update({
            "verify_panel": PanelConfig(
                panel_key="verify_panel",
                channel_name="verify",
                custom_id="guardian_verify_panel_v1",
                timeout=None,  # Persistent
                required_permissions=["send_messages", "embed_links"]
            ),
            "ticket_panel": PanelConfig(
                panel_key="ticket_panel",
                channel_name="support-start", 
                custom_id="guardian_ticket_panel_v1",
                timeout=None,  # Persistent
                required_permissions=["send_messages", "embed_links"]
            ),
            "reaction_roles_panel": PanelConfig(
                panel_key="reaction_roles_panel",
                channel_name="reaction-roles",
                custom_id="guardian_reaction_roles_v1",
                timeout=None,  # Persistent
                required_permissions=["send_messages", "embed_links"]
            )
        })
    
    def register_renderer(self, panel_key: str, renderer: Callable) -> None:
        """Register a render function for a panel type."""
        if panel_key not in self._panel_configs:
            log.warning(f"Registering renderer for unknown panel: {panel_key}")
        
        self._renderers[panel_key] = renderer
        log.info(f"Registered renderer for panel: {panel_key}")
    
    def register_panel_config(self, config: PanelConfig) -> None:
        """Register a custom panel configuration."""
        self._panel_configs[config.panel_key] = config
        log.info(f"Registered panel config: {config.panel_key}")
    
    async def render_panel(self, panel_key: str, guild: discord.Guild) -> tuple[discord.Embed, discord.ui.View]:
        """Render a panel using its registered renderer."""
        if panel_key not in self._renderers:
            raise ValueError(f"No renderer registered for panel: {panel_key}")
        
        renderer = self._renderers[panel_key]
        embed, view = await renderer(guild)
        
        # Ensure view has stable custom_id and timeout
        if hasattr(view, 'custom_id'):
            view.custom_id = self._panel_configs[panel_key].custom_id
        
        view.timeout = self._panel_configs[panel_key].timeout
        
        return embed, view
    
    async def deploy_panel(self, panel_key: str, guild: discord.Guild, 
                          target_channel: Optional[discord.TextChannel] = None) -> Optional[discord.Message]:
        """Deploy a panel to a channel and store the record."""
        if panel_key not in self._panel_configs:
            log.error(f"Unknown panel key: {panel_key}")
            return None
        
        config = self._panel_configs[panel_key]
        
        try:
            # Check permissions
            has_perms, missing = has_required_guild_perms(guild.me)
            if not has_perms:
                log.warning(f"Missing permissions for panel deploy {panel_key} in guild {guild.id}: {missing}")
                return None
            
            # Find target channel
            if target_channel is None:
                target_channel = discord.utils.get(guild.text_channels, name=config.channel_name)
                if target_channel is None:
                    log.warning(f"Channel '{config.channel_name}' not found for panel {panel_key} in guild {guild.id}")
                    return None
            
            # Check if panel already exists
            existing_record = await self.panel_store.get(guild.id, panel_key)
            if existing_record:
                try:
                    # Try to fetch existing message
                    existing_message = await self._fetch_message_safely(guild, existing_record.channel_id, existing_record.message_id)
                    if existing_message:
                        # Update existing panel
                        embed, view = await self.render_panel(panel_key, guild)
                        result = await safe_edit_message(
                            existing_message,
                            embed=embed,
                            view=view
                        )
                        
                        if result.success:
                            log.info(f"Updated existing panel {panel_key} in guild {guild.id}")
                            return result.data
                        else:
                            log.warning(f"Failed to update panel {panel_key}: {result.error}")
                    else:
                        # Message not found, remove record and continue
                        await self.panel_store.delete(guild.id, panel_key)
                        log.info(f"Cleaned up stale panel record for {panel_key} in guild {guild.id}")
                except Exception as e:
                    log.warning(f"Error checking existing panel {panel_key}: {e}")
            
            # Deploy new panel
            embed, view = await self.render_panel(panel_key, guild)
            
            result = await safe_send_message(
                target_channel,
                embed=embed,
                view=view
            )
            
            if result.success:
                message = result.data
                
                # Store panel record
                await self.panel_store.upsert(
                    guild_id=guild.id,
                    panel_key=panel_key,
                    channel_id=target_channel.id,
                    message_id=message.id,
                    schema_version=1,
                    last_deployed_at=datetime.utcnow()
                )
                
                log.info(f"Deployed panel {panel_key} in guild {guild.id} to channel {target_channel.id}")
                return message
            else:
                log.error(f"Failed to deploy panel {panel_key}: {result.error}")
                return None
                
        except Exception as e:
            log.exception(f"Error deploying panel {panel_key} in guild {guild.id}: {e}")
            return None
    
    async def _fetch_message_safely(self, guild: discord.Guild, channel_id: int, message_id: int) -> Optional[discord.Message]:
        """Safely fetch a message with proper error handling."""
        try:
            channel = guild.get_channel(channel_id)
            if channel is None:
                log.debug(f"Channel {channel_id} not found in guild {guild.id}")
                return None
            
            if not isinstance(channel, discord.TextChannel):
                log.debug(f"Channel {channel_id} is not a text channel in guild {guild.id}")
                return None
            
            return await channel.fetch_message(message_id)
            
        except discord.NotFound:
            log.debug(f"Message {message_id} not found in channel {channel_id} for guild {guild.id}")
            return None
        except discord.Forbidden:
            log.debug(f"No permission to fetch message {message_id} in channel {channel_id} for guild {guild.id}")
            return None
        except Exception as e:
            log.warning(f"Unexpected error fetching message {message_id}: {e}")
            return None
    
    async def repair_panel(self, panel_key: str, guild: discord.Guild) -> bool:
        """Repair a single panel if it's missing or broken."""
        try:
            # Get panel record
            record = await self.panel_store.get(guild.id, panel_key)
            
            if record:
                # Check if message still exists
                message = await self._fetch_message_safely(guild, record.channel_id, record.message_id)
                if message is None:
                    # Message missing, redeploy
                    log.info(f"Repairing missing panel {panel_key} in guild {guild.id}")
                    result = await self.deploy_panel(panel_key, guild)
                    return result is not None
                else:
                    # Message exists, check if it has components
                    if not message.components:
                        log.info(f"Repairing broken panel {panel_key} (no components) in guild {guild.id}")
                        embed, view = await self.render_panel(panel_key, guild)
                        edit_result = await safe_edit_message(message, embed=embed, view=view)
                        return edit_result.success
                    else:
                        log.debug(f"Panel {panel_key} appears healthy in guild {guild.id}")
                        return True
            else:
                # No record, deploy new panel
                log.info(f"Deploying missing panel {panel_key} in guild {guild.id}")
                result = await self.deploy_panel(panel_key, guild)
                return result is not None
                
        except Exception as e:
            log.exception(f"Error repairing panel {panel_key} in guild {guild.id}: {e}")
            return False
    
    async def repair_all_guild_panels(self, guild: discord.Guild) -> Dict[str, bool]:
        """Repair all panels for a guild."""
        results = {}
        
        for panel_key in self._panel_configs.keys():
            results[panel_key] = await self.repair_panel(panel_key, guild)
        
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)
        
        log.info(f"Panel repair completed for guild {guild.id}: {success_count}/{total_count} successful")
        return results
    
    async def repair_all_guilds_on_startup(self) -> Dict[int, Dict[str, bool]]:
        """Repair all panels across all guilds on startup."""
        all_results = {}
        
        for guild in self.bot.guilds:
            try:
                guild_results = await self.repair_all_guild_panels(guild)
                all_results[guild.id] = guild_results
            except Exception as e:
                log.error(f"Failed to repair panels for guild {guild.id}: {e}")
                all_results[guild.id] = {}
        
        return all_results
    
    def get_persistent_views(self) -> List[discord.ui.View]:
        """Get all persistent views that should be registered on startup."""
        views = []
        
        for panel_key, config in self._panel_configs.items():
            if config.timeout is None:  # Persistent view
                if panel_key in self._renderers:
                    # Create a dummy guild to get the view structure
                    # We'll register the view class, not an instance
                    try:
                        renderer = self._renderers[panel_key]
                        # This should return a view we can register
                        # For now, we'll let the cogs handle view registration
                        log.debug(f"Panel {panel_key} should have persistent view registered")
                    except Exception as e:
                        log.warning(f"Error getting persistent view for {panel_key}: {e}")
        
        return views
    
    async def remove_panel(self, panel_key: str, guild: discord.Guild) -> bool:
        """Remove a panel from a guild."""
        try:
            # Get panel record
            record = await self.panel_store.get(guild.id, panel_key)
            if record is None:
                log.debug(f"No panel record found for {panel_key} in guild {guild.id}")
                return True
            
            # Try to delete the message
            message = await self._fetch_message_safely(guild, record.channel_id, record.message_id)
            if message:
                try:
                    await message.delete()
                    log.info(f"Deleted panel message for {panel_key} in guild {guild.id}")
                except discord.Forbidden:
                    log.warning(f"No permission to delete panel message for {panel_key} in guild {guild.id}")
                except Exception as e:
                    log.warning(f"Error deleting panel message for {panel_key}: {e}")
            
            # Remove from store
            await self.panel_store.delete(guild.id, panel_key)
            log.info(f"Removed panel record for {panel_key} in guild {guild.id}")
            return True
            
        except Exception as e:
            log.exception(f"Error removing panel {panel_key} in guild {guild.id}: {e}")
            return False
    
    def get_panel_status(self, guild: discord.Guild) -> Dict[str, Dict[str, Any]]:
        """Get status of all panels for a guild."""
        status = {}
        
        for panel_key, config in self._panel_configs.items():
            panel_status = {
                "configured": panel_key in self._renderers,
                "channel_name": config.channel_name,
                "custom_id": config.custom_id,
                "channel_exists": False,
                "message_exists": False,
                "has_components": False
            }
            
            # Check if channel exists
            channel = discord.utils.get(guild.text_channels, name=config.channel_name)
            if channel:
                panel_status["channel_exists"] = True
                panel_status["channel_id"] = channel.id
            
            status[panel_key] = panel_status
        
        return status
