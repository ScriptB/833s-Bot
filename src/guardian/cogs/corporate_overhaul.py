"""
Corporate Overhaul Cog (Deprecated)

This cog is kept for compatibility but the overhaul command has been moved
to the new dedicated overhaul system.
"""

from __future__ import annotations

import logging
from discord.ext import commands

log = logging.getLogger("guardian.corporate_overhaul")


class CorporateOverhaulCog(commands.Cog):
    """Deprecated corporate overhaul cog - functionality moved to new overhaul system."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        log.info("CorporateOverhaulCog loaded (deprecated - use new overhaul cog)")
