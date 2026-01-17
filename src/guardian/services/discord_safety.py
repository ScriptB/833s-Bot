from __future__ import annotations

import logging
from typing import Any

import discord


log = logging.getLogger("guardian.discord_safety")


async def safe_defer(interaction: discord.Interaction, *, ephemeral: bool = True, thinking: bool = True) -> bool:
    try:
        if interaction.response.is_done():
            return True
        await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
        return True
    except (discord.NotFound, discord.HTTPException):
        return interaction.response.is_done()
    except Exception:
        log.exception("safe_defer failed")
        return interaction.response.is_done()


async def safe_send(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    ephemeral: bool = True,
    view: discord.ui.View | None = None,
) -> bool:
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(content=content, embed=embed, ephemeral=ephemeral, view=view)
            return True
        await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral, view=view)
        return True
    except (discord.NotFound, discord.HTTPException):
        return False
    except Exception:
        log.exception("safe_send failed")
        return False


async def safe_followup(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    ephemeral: bool = True,
    view: discord.ui.View | None = None,
) -> bool:
    if not interaction.response.is_done():
        await safe_defer(interaction, ephemeral=ephemeral, thinking=False)
    return await safe_send(interaction, content, embed=embed, ephemeral=ephemeral, view=view)


async def safe_edit_message(message: discord.Message, **kwargs: Any) -> bool:
    try:
        await message.edit(**kwargs)
        return True
    except (discord.NotFound, discord.HTTPException):
        return False
    except Exception:
        log.exception("safe_edit_message failed")
        return False


async def safe_delete_message(message: discord.Message) -> bool:
    try:
        await message.delete()
        return True
    except (discord.NotFound, discord.HTTPException):
        return False
    except Exception:
        log.exception("safe_delete_message failed")
        return False
