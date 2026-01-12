from __future__ import annotations

import asyncio
import logging
from typing import Optional, Any, Union

import discord
from discord import ui

from .constants import (
    MAX_MESSAGE_LENGTH,
    MAX_EMBED_DESCRIPTION,
    MAX_EMBED_TITLE,
    COLORS,
    PERMISSION_PRESETS,
    ERROR_MESSAGES,
    SUCCESS_MESSAGES,
)

log = logging.getLogger("guardian.utils")


def safe_embed(title: str, description: str, color: int = COLORS["default"]) -> discord.Embed:
    """Create an embed with safe length limits."""
    if len(title) > MAX_EMBED_TITLE:
        title = title[:MAX_EMBED_TITLE - 3] + "…"
    if len(description) > MAX_EMBED_DESCRIPTION:
        description = description[:MAX_EMBED_DESCRIPTION - 3] + "…"
    
    return discord.Embed(title=title, description=description, color=color)


def permission_overwrite(preset: str) -> discord.PermissionOverwrite:
    """Create permission overwrites from preset."""
    if preset not in PERMISSION_PRESETS:
        preset = "none"
    
    p = PERMISSION_PRESETS[preset]
    return discord.PermissionOverwrite(
        view_channel=p.view,
        send_messages=p.send,
        read_message_history=p.history,
        add_reactions=p.reactions,
        create_public_threads=p.threads,
        create_private_threads=p.threads,
        send_messages_in_threads=p.send,
    )


async def safe_followup(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    ephemeral: bool = False,
    **kwargs: Any,
) -> Optional[discord.Message]:
    """Safely follow up an interaction with error handling."""
    try:
        return await interaction.followup.send(
            content=content, embed=embed, ephemeral=ephemeral, **kwargs
        )
    except discord.HTTPException as e:
        log.error(f"Failed to send followup: {e}")
        return None


async def safe_response(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    ephemeral: bool = False,
    **kwargs: Any,
) -> bool:
    """Safely respond to an interaction with error handling."""
    try:
        await interaction.response.send_message(
            content=content, embed=embed, ephemeral=ephemeral, **kwargs
        )
        return True
    except discord.HTTPException as e:
        log.error(f"Failed to send response: {e}")
        return False


def error_embed(message: str) -> discord.Embed:
    """Create a standardized error embed."""
    return safe_embed("Error", message, COLORS["error"])


def success_embed(message: str) -> discord.Embed:
    """Create a standardized success embed."""
    return safe_embed("Success", message, COLORS["success"])


def info_embed(message: str) -> discord.Embed:
    """Create a standardized info embed."""
    return safe_embed("Information", message, COLORS["info"])


def warning_embed(message: str) -> discord.Embed:
    """Create a standardized warning embed."""
    return safe_embed("Warning", message, COLORS["warning"])


class ConfirmationView(ui.View):
    """A reusable confirmation view."""
    
    def __init__(self, timeout: float = 60.0) -> None:
        super().__init__(timeout=timeout)  # Keep timeout for temporary confirmations
        self.value: Optional[bool] = None
    
    @ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.value = True
        self.stop()
        await safe_response(interaction, "Confirmed.", ephemeral=True)
    
    @ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.value = False
        self.stop()
        await safe_response(interaction, "Cancelled.", ephemeral=True)


async def get_confirmation(
    interaction: discord.Interaction,
    message: str,
    timeout: float = 60.0,
) -> Optional[bool]:
    """Get user confirmation with a view."""
    view = ConfirmationView(timeout)
    embed = info_embed(message)
    
    await safe_response(interaction, embed=embed, view=view)
    await view.wait()
    
    return view.value


def truncate_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """Truncate text to maximum length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "…"


def format_user(user: Union[discord.User, discord.Member]) -> str:
    """Format user mention with name."""
    return f"{user.mention} ({user.name}#{user.discriminator})"


def format_channel(channel: discord.abc.GuildChannel) -> str:
    """Format channel mention with name."""
    return f"{channel.mention} ({channel.name})"


def format_role(role: discord.Role) -> str:
    """Format role mention with name."""
    return f"{role.mention} ({role.name})"


async def retry_async(
    func,
    max_retries: int = 3,
    delay: float = 1.0,
    exceptions: tuple = (discord.HTTPException,),
) -> Any:
    """Retry an async function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return await func()
        except exceptions as e:
            if attempt == max_retries - 1:
                raise
            wait_time = delay * (2 ** attempt)
            log.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
            await asyncio.sleep(wait_time)
