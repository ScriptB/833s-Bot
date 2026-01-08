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

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="guardian_overhaul", description="FULL WIPE (channels/roles) then rebuild 833s corporate template.")
    @app_commands.checks.has_permissions(administrator=True)
    async def guardian_overhaul(self, interaction: discord.Interaction, confirm: str) -> None:
        assert interaction.guild is not None
        guild = interaction.guild

        # Hard safety gate: must match exact phrase
        expected = f"DELETE {guild.name}"
        if confirm.strip() != expected:
            await interaction.response.send_message(f"Confirmation must be exactly: `{expected}`", ephemeral=True)
            return

        # Acknowledge immediately. Note: interaction tokens are time-limited; do not rely on followups
        # after long-running operations.
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Best-effort initial status message for the invoker.
        try:
            await interaction.edit_original_response(content="Overhaul started. Progress will be posted in #bot-ops.")
        except (discord.NotFound, discord.HTTPException):
            pass

        schema = canonical_schema()
        builder = SchemaBuilder(self.bot)
        status = getattr(self.bot, "status_reporter", None)
        if status:
            await status.start(guild, total=60, phase="Overhaul: preparing")

        ok = False
        try:
            if status:
                await status.update(guild, 1, "Overhaul: nuking server (channels/categories/roles)")
            await builder.nuke_guild(guild, status=status)

            # Small pause for consistency
            await asyncio.sleep(2.0)

            if status:
                await status.update(guild, 10, "Overhaul: rebuilding roles")
            roles = await builder.ensure_roles(guild, schema, status=status)

            if status:
                await status.update(guild, 25, "Overhaul: rebuilding categories/channels/permissions")
            await builder.ensure_categories_channels(guild, schema, roles, status=status)

            # Sync level roles with leveling system (existing cog)
            try:
                lvl = getattr(self.bot, "leveling_service", None)
                if lvl:
                    await lvl.ensure_level_roles(guild, schema.level_role_map)  # type: ignore[attr-defined]
            except Exception:
                pass

            # Post pinned bootstrap messages (rules/help/intros)
            try:
                bs = getattr(self.bot, "channel_bootstrapper", None)
                if bs:
                    await bs.ensure_first_posts(guild)  # type: ignore[attr-defined]
            except Exception:
                pass

            ok = True
            if status:
                await status.finish(guild, True, "Overhaul complete.")
            # Best-effort completion message; ignore if the interaction token expired.
            try:
                await interaction.edit_original_response(content="Overhaul complete.")
            except (discord.NotFound, discord.HTTPException):
                pass

        except Exception as e:
            if status:
                await status.finish(guild, False, f"{type(e).__name__}: {e}")
            # Best-effort failure message; ignore if the interaction token expired.
            try:
                await interaction.edit_original_response(content=f"Overhaul failed: {type(e).__name__}")
            except (discord.NotFound, discord.HTTPException):
                pass
