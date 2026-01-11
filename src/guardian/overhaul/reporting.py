"""
Safe Message Reporting for Overhaul Operations

Ensures messages never exceed Discord's 2000 character limit.
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import discord

log = logging.getLogger("guardian.overhaul.reporting")


async def send_safe_message(
    message: discord.Message,
    content: str,
    ephemeral: bool = True,
    filename: str = "overhaul_report.txt"
) -> Optional[discord.Message]:
    """
    Send a message safely, respecting Discord's 2000 character limit.
    
    If content is too long, sends a summary and attaches the full content as a file.
    """
    try:
        if len(content) <= 1900:
            # Send normally
            try:
                return await message.reply(content)
            except discord.NotFound:
                # Message deleted - can't send anything
                log.warning("Message deleted before safe message could be sent")
                return None
        
        # Content is too long - send summary + file
        summary = content[:1900] + "\n\n... (full report attached)"
        
        try:
            # Create file attachment
            file_content = content.encode('utf-8')
            file = discord.File(
                io.BytesIO(file_content),
                filename=filename
            )
            
            try:
                return await message.reply(
                    content=summary,
                    file=file
                )
            except discord.NotFound:
                # Message deleted - can't send anything
                log.warning("Message deleted before file attachment could be sent")
                return None
            
        except Exception as file_error:
            log.warning(f"Failed to attach file, sending truncated message: {file_error}")
            # Fallback to truncated message
            try:
                return await message.reply(summary)
            except discord.NotFound:
                # Message deleted - can't send anything
                log.warning("Message deleted before fallback message could be sent")
                return None
            
    except discord.Forbidden:
        log.warning("Missing permissions to send message")
    except Exception as e:
        log.error(f"Failed to send safe message: {e}")
    
    return None


def truncate_message(content: str, max_length: int = 1900) -> str:
    """
    Truncate a message to fit within Discord's limits.
    """
    if len(content) <= max_length:
        return content
    
    return content[:max_length] + "\n\n... (truncated)"
