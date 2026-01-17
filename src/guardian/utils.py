from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from discord import ui
from discord.ext import commands

from .constants import (
    COLORS,
    MAX_EMBED_DESCRIPTION,
    MAX_EMBED_TITLE,
    MAX_MESSAGE_LENGTH,
    PERMISSION_PRESETS,
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
    content: str | None = None,
    embed: discord.Embed | None = None,
    ephemeral: bool = False,
    **kwargs: Any,
) -> discord.Message | None:
    """Safely follow up an interaction with error handling."""
    try:
        return await interaction.followup.send(
            content=content, embed=embed, ephemeral=ephemeral, **kwargs
        )
    except discord.HTTPException as e:
        log.error(f"Failed to send followup: {e}")
        return None


async def safe_response(
    target: discord.Interaction | commands.Context,
    content: str | None = None,
    embed: discord.Embed | None = None,
    ephemeral: bool = False,
    **kwargs: Any,
) -> bool:
    """Safely respond to an interaction or context with error handling."""
    try:
        if isinstance(target, discord.Interaction):
            await target.response.send_message(
                content=content, embed=embed, ephemeral=ephemeral, **kwargs
            )
        elif isinstance(target, commands.Context):
            await target.reply(content=content, embed=embed, **kwargs)
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
        self.value: bool | None = None
    
    @ui.button(label="Confirm", style=discord.ButtonStyle.success, custom_id="confirmation_confirm")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.value = True
        self.stop()
        await safe_response(interaction, "Confirmed.", ephemeral=True)
    
    @ui.button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="confirmation_cancel")
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.value = False
        self.stop()
        await safe_response(interaction, "Cancelled.", ephemeral=True)


async def get_confirmation(
    interaction: discord.Interaction,
    message: str,
    timeout: float = 60.0,
) -> bool | None:
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


def format_user(user: discord.User | discord.Member) -> str:
    """Format user mention with name."""
    return f"{user.mention} ({user.name}#{user.discriminator})"


def format_channel(channel: discord.abc.GuildChannel) -> str:
    """Format channel mention with name."""
    return f"{channel.mention} ({channel.name})"


def normalize_display_name(name: str) -> str:
    """Normalize Discord display names for fuzzy matching.

    - strips surrounding whitespace
    - removes leading emoji-like prefixes commonly used in role names
    - casefolds for case-insensitive comparison
    """

    # Remove common leading emoji/prefix tokens, e.g. "🐍 Snakes" -> "Snakes"
    n = name.strip()
    # Split on first space and drop the first token if it contains non-alnum characters
    parts = n.split(maxsplit=1)
    if len(parts) == 2:
        head, tail = parts
        if not head.isalnum():
            n = tail
    return n.strip().casefold()


def find_role_fuzzy(guild: discord.Guild, expected_name: str) -> discord.Role | None:
    """Find a role by exact name or emoji-prefixed variant."""

    role = discord.utils.get(guild.roles, name=expected_name)
    if role:
        return role
    target = normalize_display_name(expected_name)
    for r in guild.roles:
        if normalize_display_name(r.name) == target:
            return r
    return None


def find_text_channel_fuzzy(guild: discord.Guild, expected_name: str) -> discord.TextChannel | None:
    """Find a text channel by exact name or emoji-prefixed variant."""

    ch = discord.utils.get(guild.text_channels, name=expected_name)
    if ch:
        return ch
    target = normalize_display_name(expected_name)
    for c in guild.text_channels:
        if normalize_display_name(c.name) == target:
            return c
    return None


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
