from __future__ import annotations

import time
import discord
from discord import app_commands
from discord.ext import commands

from ..services.schema import canonical_schema
from ..services.schema_builder import SchemaBuilder
from ..security.auth import root_only


class RebuildCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.guild_only()
    @root_only()
    @app_commands.command(
        name="guardian_rebuild",
        description="Wipe channels/roles (bounded) and rebuild from canonical schema. (Root only)",
    )
    async def guardian_rebuild(self, interaction: discord.Interaction, confirm: bool = False) -> None:
        assert interaction.guild is not None
        guild = interaction.guild
        if not confirm:
            await interaction.response.send_message(
                "Refused: this command deletes channels and roles. Re-run with confirm=true to proceed.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        bot_member = guild.me or guild.get_member(self.bot.user.id)  # type: ignore[attr-defined]
        if not bot_member or not (bot_member.guild_permissions.manage_channels and bot_member.guild_permissions.manage_roles):
            await interaction.followup.send("Missing permissions: Manage Channels + Manage Roles.", ephemeral=True)
            return

        # Snapshot pre-state
        pre = {
            "guild_id": guild.id,
            "captured_at": int(time.time()),
            "roles": [{"id": r.id, "name": r.name, "managed": r.managed, "position": r.position} for r in guild.roles],
            "channels": [{"id": c.id, "name": c.name, "type": str(c.type)} for c in guild.channels],
        }
        try:
            await self.bot.snapshot_store.put(guild.id, "pre_rebuild", pre)  # type: ignore[attr-defined]
        except Exception:
            pass

        top_pos = bot_member.top_role.position

        # Delete channels
        for ch in list(guild.channels):
            try:
                await ch.delete(reason="833s Guardian rebuild wipe")
            except Exception:
                continue

        # Delete roles
        for r in sorted(guild.roles, key=lambda x: x.position, reverse=True):
            if r.is_default() or r.managed or r.position >= top_pos:
                continue
            try:
                await r.delete(reason="833s Guardian rebuild wipe")
            except Exception:
                continue

        schema = canonical_schema()
        builder = SchemaBuilder(self.bot)
        roles = await builder.ensure_roles(guild, schema)
        created = await builder.ensure_categories_channels(guild, schema, roles)

        # Level sync
        try:
            cfg = await self.bot.levels_config_store.get(guild.id)  # type: ignore[attr-defined]
            await self.bot.levels_config_store.upsert(  # type: ignore[attr-defined]
                type(cfg)(
                    guild_id=guild.id,
                    enabled=True,
                    announce=True,
                    xp_min=cfg.xp_min,
                    xp_max=cfg.xp_max,
                    cooldown_seconds=cfg.cooldown_seconds,
                    daily_cap=cfg.daily_cap,
                    ignore_channels_json=cfg.ignore_channels_json,
                )
            )
            for lvl, role_name in schema.level_role_map:
                rr = roles.get(role_name)
                if rr:
                    await self.bot.level_rewards_store.add(guild.id, int(lvl), rr.id)  # type: ignore[attr-defined]
        except Exception:
            pass

        payload = builder.snapshot_payload(schema, roles, created)
        try:
            await self.bot.snapshot_store.put(guild.id, "post_rebuild", payload)  # type: ignore[attr-defined]
        except Exception:
            pass

        await interaction.followup.send("Rebuild complete.", ephemeral=True)

    @app_commands.guild_only()
    @root_only()
    @app_commands.command(name="guardian_validate", description="Drift validation + auto-correct against canonical schema. (Root only)")
    async def guardian_validate(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        schema = canonical_schema()
        builder = SchemaBuilder(self.bot)
        roles = await builder.ensure_roles(interaction.guild, schema)
        await builder.ensure_categories_channels(interaction.guild, schema, roles)

        await interaction.followup.send("Validation applied.", ephemeral=True)
