from __future__ import annotations

import asyncio
import time
from typing import Optional, Dict, Any
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
        self.skipped_count = 0
        self.error_count = 0
        self.errors: List[str] = []
    
    async def start(self, phase: str, total_steps: int = 0) -> None:
        """Start a new phase."""
        self.current_phase = phase
        self.current_step = 0
        self.total_steps = total_steps
        self.last_action = f"Starting {phase}"
        await self._update_status()
    
    async def step(self, action: str, increment: int = 1) -> None:
        """Report a step completion."""
        self.current_step += increment
        self.last_action = action
        await self._update_status()
    
    async def skip(self, reason: str) -> None:
        """Report a skipped item."""
        self.skipped_count += 1
        self.last_action = f"Skipped: {reason}"
        await self._update_status()
    
    async def error(self, error_msg: str, details: List[str] = None) -> None:
        """Report an error."""
        self.error_count += 1
        self.errors.append(error_msg)
        if details:
            self.errors.extend(details[:20])  # Limit to prevent spam
        self.last_action = f"Error: {error_msg}"
        await self._update_status()
    
    async def success(self, message: str) -> None:
        """Report success completion."""
        self.last_action = f"✅ {message}"
        await self._update_status()
    
    async def _update_status(self) -> None:
        """Update the status message if enough time has passed."""
        current_time = time.time()
        if current_time - self.last_update < self.update_interval and self.status_message:
            return
        
        self.last_update = current_time
        
        # Ensure DM channel exists
        if not self.dm_channel:
            try:
                self.dm_channel = await self.user.create_dm()
            except discord.Forbidden:
                log.error(f"Cannot DM user {self.user.id} for progress updates")
                return
        
        # Build status content
        elapsed = int(current_time - self.start_time)
        progress = f"{self.current_step}/{self.total_steps}" if self.total_steps > 0 else "In Progress"
        
        content = (
            f"🔧 **Server Overhaul Progress**\n\n"
            f"**Phase:** {self.current_phase}\n"
            f"**Progress:** {progress}\n"
            f"**Current:** {self.last_action}\n"
            f"**Elapsed:** {elapsed}s\n"
            f"**Skipped:** {self.skipped_count} | **Errors:** {self.error_count}"
        )
        
        # Respect Discord character limits
        if len(content) > 1900:
            content = content[:1870] + "...\n\n*(Content trimmed for length)*"
        
        try:
            if self.status_message:
                await self.status_message.edit(content=content)
            else:
                self.status_message = await self.dm_channel.send(content)
        except discord.Forbidden:
            log.error(f"Cannot edit DM message for user {self.user.id}")
        except discord.HTTPException as e:
            log.error(f"Failed to update progress DM: {e}")
    
    async def finalize(self, results: Dict[str, Any]) -> None:
        """Send final report."""
        elapsed = int(time.time() - self.start_time)
        
        # Build summary
        summary_parts = [
            "🎉 **Overhaul Complete**",
            f"**Total Time:** {elapsed}s",
            f"**Errors:** {self.error_count}",
            f"**Skipped:** {self.skipped_count}"
        ]
        
        # Add phase-specific results
        if 'deletion' in results:
            del_result = results['deletion']
            summary_parts.append(f"**Deleted:** {del_result.channels_deleted} channels, {del_result.roles_deleted} roles")
        
        if 'rebuild' in results:
            rebuild_result = results['rebuild']
            summary_parts.append(f"**Created:** {rebuild_result.categories_created} categories, {rebuild_result.channels_created} channels, {rebuild_result.roles_created} roles")
        
        if 'content' in results:
            content_result = results['content']
            summary_parts.append(f"**Posts:** {content_result.posts_created}")
        
        content = "\n".join(summary_parts)
        
        # Add errors if any
        if self.errors:
            error_text = "\n".join(f"• {err}" for err in self.errors[:10])
            if len(self.errors) > 10:
                error_text += f"\n• ... and {len(self.errors) - 10} more"
            content += f"\n\n**Errors:**\n{error_text}"
        
        try:
            if self.status_message:
                await self.status_message.edit(content=content)
            else:
                await self.dm_channel.send(content)
        except Exception as e:
            log.error(f"Failed to send final report: {e}")
