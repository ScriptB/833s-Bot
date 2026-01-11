"""
Progress Reporting for Overhaul Operations

Handles debounced DM updates with fallbacks.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import discord

log = logging.getLogger("guardian.overhaul.progress")


class ProgressReporter:
    """Debounced progress reporter for overhaul operations."""
    
    def __init__(self, update_interval: float = 2.0):
        self.update_interval = update_interval
        self.last_update = 0
        self.pending_update = None
        self.dm_message = None
        self.dm_user = None
        self.interaction = None
        self._update_task = None
        self._cancel_event = asyncio.Event()
    
    def set_user(self, user: discord.User):
        """Set the user for progress DMs."""
        self.dm_user = user
    
    def set_interaction(self, interaction: discord.Interaction):
        """Set the interaction for fallback updates."""
        self.interaction = interaction
    
    async def schedule_update(self, message: str):
        """Schedule a debounced progress update."""
        self.pending_update = message
        now = time.time()
        
        # Update immediately if it's been long enough or if no task running
        if now - self.last_update >= self.update_interval or self._update_task is None:
            await self._send_pending()
        elif self._update_task is None:
            self._update_task = asyncio.create_task(self._update_loop())
    
    async def _update_loop(self):
        """Background task for debounced updates."""
        while not self._cancel_event.is_set():
            await asyncio.sleep(self.update_interval)
            if self.pending_update:
                await self._send_pending()
            if self._cancel_event.is_set():
                break
    
    async def _send_pending(self):
        """Send pending update via DM or fallback."""
        if not self.pending_update:
            return
        
        content = f"🏰 **Server Overhaul Progress**\n\n{self.pending_update}"
        
        # Ensure content is under Discord limit
        if len(content) > 1900:
            content = content[:1900] + "\n\n... (truncated)"
        
        # Try DM first
        if self.dm_user:
            try:
                if self.dm_message:
                    await self.dm_message.edit(content=content)
                else:
                    self.dm_message = await self.dm_user.send(content)
                
                self.last_update = time.time()
                self.pending_update = None
                return
                
            except discord.Forbidden:
                log.warning("User has DMs disabled, falling back to interaction updates")
            except Exception as e:
                log.error(f"Failed to send DM progress update: {e}")
        
        # Fallback to ephemeral interaction message
        if self.interaction:
            try:
                await self.interaction.followup.send(content, ephemeral=True)
                self.last_update = time.time()
                self.pending_update = None
                
            except discord.NotFound:
                log.warning("Interaction expired for progress update")
            except discord.Forbidden:
                log.warning("Missing permissions for interaction progress update")
            except Exception as e:
                log.error(f"Failed to send interaction progress update: {e}")
    
    def cancel(self):
        """Cancel progress tracking."""
        self._cancel_event.set()
        if self._update_task:
            self._update_task.cancel()
