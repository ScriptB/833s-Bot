from __future__ import annotations

import asyncio
from typing import Iterable

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.overhaul_authoritative import AuthoritativeOverhaulExecutor
from ..utils import safe_embed, permission_overwrite, get_confirmation
from ..constants import DEFAULT_TIMEOUT_SECONDS, COLORS
from ..security.auth import root_only


class SetupAutoConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    # Note: Overhaul command moved to corporate_overhaul.py to avoid duplication
    # Use /overhaul command for authoritative server restructuring
