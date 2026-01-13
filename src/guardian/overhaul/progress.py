from __future__ import annotations

import time
from typing import Optional, Dict
import discord
import logging

from ..interfaces import ProgressReporter as ProgressReporterProtocol, validate_progress_reporter

log = logging.getLogger("guardian.progress")


class ProgressReporter:
    """Unified progress reporter for overhaul operations."""
    
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.user = interaction.user
        self.client = interaction.client
        self.guild_id = interaction.guild.id if interaction.guild else None
        
        # Validate interface compliance at runtime
        validate_progress_reporter(self)
        
        # DM state
        self.dm_channel: Optional[discord.DMChannel] = None
        self.status_message: Optional[discord.Message] = None
        self.dm_failed = False
        
        # Timing
        self.start_time = time.time()
        self.last_update = 0
        self.update_interval = 2.0  # Update at most every 2 seconds
        
        # Current state
        self.current_phase = "Initializing"
        self.current_done = 0
        self.current_total = 0
        self.current_detail = ""
        self.current_counts: Optional[Dict] = None
        self.current_errors = 0
        self.last_phase = ""
    
    async def init(self) -> None:
        """Ensure DM message exists (send once)."""
        if not self.dm_failed:
            try:
                self.dm_channel = await self.user.create_dm()
                content = self._format_message()
                self.status_message = await self.dm_channel.send(content)
                self.last_update = time.time()
            except discord.Forbidden:
                log.warning(f"Cannot DM user {self.user.id}, falling back to interaction edits")
                self.dm_failed = True
                # Fallback: edit the original interaction response
                try:
                    await self.interaction.response.edit_message(content=self._format_message())
                except discord.NotFound:
                    # Interaction already responded, send new followup
                    await self.interaction.followup.send(content=self._format_message(), ephemeral=True)
            except Exception as e:
                log.error(f"Failed to send initial DM: {e}")
                self.dm_failed = True
    
    async def update(self, phase: str, done: int, total: int, detail: str = "", *, counts: Optional[Dict] = None, errors: int = 0) -> None:
        """Edit the same DM message (debounced)."""
        # Update current state
        self.current_phase = phase
        self.current_done = done
        self.current_total = total
        self.current_detail = detail
        self.current_counts = counts
        self.current_errors = errors
        
        # Check if we should update (debounce logic)
        current_time = time.time()
        should_update = (
            self.last_phase != phase or  # Phase changed
            done == total or            # Phase complete
            current_time - self.last_update >= self.update_interval  # Time elapsed
        )
        
        if should_update:
            await self._update_message()
            self.last_update = current_time
            self.last_phase = phase
    
    async def finalize(self, ok: bool, summary: str) -> None:
        """Edit DM message with final summary (no debounce)."""
        if ok:
            self.current_phase = "Complete"
        else:
            self.current_phase = "Failed"
        
        self.current_detail = summary
        self.current_done = self.current_total  # Mark as complete
        
        # Force update without debounce
        await self._update_message()
    
    async def fail(self, summary: str) -> None:
        """Calls finalize(False, summary)."""
        await self.finalize(False, summary)
    
    def _format_message(self) -> str:
        """Format progress message."""
        elapsed = int(time.time() - self.start_time)
        minutes = elapsed // 60
        seconds = elapsed % 60
        
        content = (
            f"**Overhaul Progress**\n"
            f"Phase: {self.current_phase} ({self.current_done}/{self.current_total})\n"
            f"{self.current_detail}"
        )
        
        # Add counts if available
        if self.current_counts:
            content += f"\nDeleted: ch={self.current_counts.get('deleted_channels', 0)} cat={self.current_counts.get('deleted_categories', 0)} roles={self.current_counts.get('deleted_roles', 0)} skipped={self.current_counts.get('skipped', 0)}"
            content += f"\nCreated: cat={self.current_counts.get('created_categories', 0)} ch={self.current_counts.get('created_channels', 0)} roles={self.current_counts.get('created_roles', 0)}"
        
        if self.current_errors > 0:
            content += f"\nErrors: {self.current_errors}"
        
        content += f"\nElapsed: {minutes:02d}:{seconds:02d}"
        
        # Truncate to 1900 chars
        if len(content) > 1900:
            content = content[:1897] + "..."
        
        return content
    
    async def _update_message(self) -> None:
        """Update the appropriate message (DM or interaction)."""
        content = self._format_message()
        
        if self.dm_failed:
            # Update interaction response instead
            try:
                await self.interaction.response.edit_message(content=content)
            except discord.NotFound:
                # Interaction already responded, send new followup
                await self.interaction.followup.send(content=content, ephemeral=True)
            except Exception as e:
                log.error(f"Failed to update interaction: {e}")
        elif self.status_message:
            # Update DM message
            try:
                await self.status_message.edit(content=content)
            except Exception as e:
                log.error(f"Failed to update DM: {e}")
        else:
            # No message exists yet, try to init
            await self.init()
