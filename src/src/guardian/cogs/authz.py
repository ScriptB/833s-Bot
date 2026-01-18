from __future__ import annotations

import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..permissions import require_root
from ..security.capabilities import resolve_capabilities

log = logging.getLogger("guardian.cogs.authz")


class AuthzCog(commands.Cog):
    """Authorization diagnostics.

    Read-only tools to inspect effective capabilities. No mutation.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="authz_explain", description="Explain a member's effective capabilities (root only).")
    @require_root()
    async def authz_explain(self, interaction: discord.Interaction, member: discord.Member):
        res = await resolve_capabilities(bot=interaction.client, member=member)

        # Keep payload small and deterministic.
        data = {
            "guild_id": res.guild_id,
            "user_id": res.user_id,
            "config_revision": res.revision,
            "sources": list(res.sources),
            "capabilities": sorted(res.capabilities),
        }

        body = json.dumps(data, indent=2, ensure_ascii=False)
        if len(body) > 1800:
            body = body[:1800] + "\n...truncated"
        await interaction.response.send_message(f"```json\n{body}\n```", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AuthzCog(bot))
