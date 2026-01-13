from __future__ import annotations

import asyncio
import time
from typing import Optional, List
import discord
import logging

log = logging.getLogger("guardian.progress")


class ProgressReporter:
    """Unified progress reporter for overhaul operations."""
    
    def __init__(self, user: discord.User, client: discord.Client, guild_id: int):
        self.user = user
        self.client = client
        self.guild_id = guild_id
        self.dm_channel: Optional[discord.DMChannel] = None
        self.status_message: Optional[discord.Message] = None
        self.start_time = time.time()
        self.last_update = 0
        self.update_interval = 2.0  # Update at most every 2 seconds
        
        # Tracking
        self.current_phase = "Initializing"
        self.current_step = 0
        self.total_steps = 0
        self.last_action = ""
        self.deleted_channels = 0
        self.deleted_categories = 0
        self.deleted_roles = 0
        self.created_channels = 0
        self.created_categories = 0
        self.created_roles = 0
        self.skipped_count = 0
        self.error_count = 0
        self.errors: List[str] = []
        self.last_phase = ""
    
    async def init(self) -> None:
        """Send initial DM message."""
        try:
            self.dm_channel = await self.user.create_dm()
            content = self._format_message()
            self.status_message = await self.dm_channel.send(content)
            self.last_update = time.time()
        except Exception as e:
            log.error(f"Failed to send initial DM: {e}")
    
    async def phase(self, title: str, total_steps: Optional[int] = None) -> None:
        """Start a new phase."""
        self.current_phase = title
        self.current_step = 0
        if total_steps is not None:
            self.total_steps = total_steps
        self.last_action = f"Starting {title}"
        await self._update_if_needed()
    
    async def step(self, text: str, advance: int = 0) -> None:
        """Report a step completion."""
        self.current_step += advance
        self.last_action = text
        await self._update_if_needed()
    
    async def finalize(self, summary: str) -> None:
        """Finalize with success message."""
        self.current_phase = "Complete"
        self.last_action = summary
        await self._update_if_needed(force=True)
    
    async def fail(self, summary: str) -> None:
        """Finalize with failure message."""
        self.current_phase = "Failed"
        self.last_action = f"FAILED: {summary}"
        await self._update_if_needed(force=True)
    
    def _format_message(self) -> str:
        """Format progress message."""
        elapsed = int(time.time() - self.start_time)
        minutes = elapsed // 60
        seconds = elapsed % 60
        
        content = (
            f"**Overhaul Progress**\n"
            f"Phase: {self.current_phase}\n"
            f"Step: {self.current_step}/{self.total_steps}\n"
            f"Last: {self.last_action}\n"
            f"Deleted: ch={self.deleted_channels} cat={self.deleted_categories} roles={self.deleted_roles} (skipped={self.skipped_count})\n"
            f"Created: cat={self.created_categories} ch={self.created_channels} roles={self.created_roles}\n"
            f"Errors: {self.error_count}\n"
            f"Elapsed: {minutes:02d}:{seconds:02d}"
        )
        
        # Truncate to 1900 chars
        if len(content) > 1900:
            content = content[:1897] + "..."
        
        return content
    
    async def _update_if_needed(self, force: bool = False) -> None:
        """Update status message if enough time passed or phase changed."""
        current_time = time.time()
        
        # Always update if forced, phase changed, or enough time passed
        if (force or 
            self.current_phase != self.last_phase or
            current_time - self.last_update >= self.update_interval):
            
            try:
                content = self._format_message()
                if self.status_message:
                    await self.status_message.edit(content=content)
                else:
                    await self.init()
                self.last_update = current_time
                self.last_phase = self.current_phase
            except Exception as e:
                log.error(f"Failed to update DM: {e}")
    
    # Tracking methods
    def track_deleted(self, channels: int = 0, categories: int = 0, roles: int = 0):
        """Track deletion counts."""
        self.deleted_channels += channels
        self.deleted_categories += categories
        self.deleted_roles += roles
    
    def track_created(self, channels: int = 0, categories: int = 0, roles: int = 0):
        """Track creation counts."""
        self.created_channels += channels
        self.created_categories += categories
        self.created_roles += roles
    
    def track_skip(self):
        """Track a skipped item."""
        self.skipped_count += 1
    
    def track_error(self, error: str):
        """Track an error."""
        self.error_count += 1
        self.errors.append(error)
