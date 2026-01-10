from __future__ import annotations

import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from ..services.schema import canonical_schema
from ..services.schema_builder import SchemaBuilder


class CorporateOverhaulCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
