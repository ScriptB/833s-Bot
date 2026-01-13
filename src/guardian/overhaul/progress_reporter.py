from __future__ import annotations

import asyncio
import time
from typing import Optional, List
import discord
import logging

log = logging.getLogger("guardian.progress_reporter")


class ProgressReporter:
    """Handles DM status updates for overhaul progress."""
    
    def __init__(self, bot: discord.Client, user: discord.User):
        self.bot = bot
        self.user = user
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
    
    async def send(self) -> None:
        """Send initial DM message."""
        try:
            self.dm_channel = await self.user.create_dm()
            content = self._format_message()
            self.status_message = await self.dm_channel.send(content)
            self.last_update = time.time()
        except Exception as e:
            log.error(f"Failed to send initial DM: {e}")
    
    async def update(self, phase: str, step: int = None, total: int = None, last_action: str = None) -> None:
        """Update the DM message with current progress."""
        current_time = time.time()
        
        # Update tracking
        self.current_phase = phase
        if step is not None:
            self.current_step = step
        if total is not None:
            self.total_steps = total
        if last_action is not None:
            self.last_action = last_action
        
        # Debounce: only update if enough time passed or phase changed
        if (current_time - self.last_update < self.update_interval and 
            self.status_message and phase == getattr(self, 'last_phase', '')):
            return
        
        try:
            content = self._format_message()
            if self.status_message:
                await self.status_message.edit(content=content)
            else:
                await self.send()
            self.last_update = current_time
            self.last_phase = phase
        except Exception as e:
            log.error(f"Failed to update DM: {e}")
    
    def _format_message(self) -> str:
        """Format the progress message."""
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
    
    async def finalize(self, success: bool = True, final_message: str = None) -> None:
        """Send final status message."""
        if final_message:
            await self.update("Complete", last_action=final_message)
        elif success:
            await self.update("Complete", last_action="Overhaul completed successfully")
        else:
            await self.update("Failed", last_action="Overhaul failed")
    
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
