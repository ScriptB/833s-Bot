from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..base_cog import BaseCog
from ..moderation.action_engine import ActionEngine
from ..moderation.models import ModEvent
from ..moderation.pipeline import ModerationPipeline
from ..moderation.config_schema import default_config, validate_config
from ..services.moderation_config_store import ModerationConfigStore
from ..services.moderation_audit_store import ModerationAuditStore


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


class ModerationSystemCog(BaseCog):
    """Moderation + AutoMod governance system.

    - Event-driven pipeline for messages
    - Versioned config (draft/published) with validation
    - Deterministic rule evaluation
    - Safe action execution with idempotency
    """

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        self.bot: commands.Bot = bot

    async def cog_load(self) -> None:
        # Stores are attached on the bot instance in bot.py
        self.modcfg: ModerationConfigStore = getattr(self.bot, "moderation_config_store")
        self.modaudit: ModerationAuditStore = getattr(self.bot, "moderation_audit_store")
        self.pipeline: ModerationPipeline = getattr(self.bot, "moderation_pipeline")
        self.action_engine: ActionEngine = getattr(self.bot, "moderation_action_engine")

        # Register the /mod command group on the app command tree.
        try:
            self.bot.tree.add_command(self.mod)
        except Exception:
            # Tree may already contain it due to hot reload.
            pass

    async def cog_unload(self) -> None:
        try:
            self.bot.tree.remove_command(self.mod.name, type=self.mod.type)  # type: ignore[attr-defined]
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        if message.author.bot:
            return
        # Only process normal messages
        if not isinstance(message.author, discord.Member):
            return

        try:
            await self.modcfg.ensure_guild(message.guild.id, created_at_iso=_now_iso(), created_by_user_id=None)
        except Exception:
            # If config init fails, do nothing (fail closed, but don't crash bot)
            return

        # Gather lightweight metadata
        meta = {
            "mention_count": len(message.mentions) + len(message.role_mentions),
        }
        event = ModEvent(
            guild_id=message.guild.id,
            event_type="message_create",
            created_at=datetime.utcnow(),
            user_id=message.author.id,
            channel_id=message.channel.id,
            message_id=message.id,
            content=message.content,
            meta=meta,
        )

        # Apply rule engine
        decision = await self.pipeline.decide(event, member_role_ids=[r.id for r in message.author.roles])
        if not decision.actions:
            return

        # Execute actions
        await self.action_engine.execute(decision)

    # -------------------- Commands: Config change management --------------------

    mod = app_commands.Group(name="mod", description="Moderation governance")

    @mod.command(name="config_show", description="Show moderation config (draft or published)")
    @app_commands.describe(which="draft or published")
    async def config_show(self, interaction: discord.Interaction, which: str = "published") -> None:
        if interaction.guild is None:
            await interaction.response.send_message("ERR_NO_GUILD", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        await self.modcfg.ensure_guild(interaction.guild.id, created_at_iso=_now_iso(), created_by_user_id=interaction.user.id)
        if which.lower() == "draft":
            rev, doc = await self.modcfg.get_draft(interaction.guild.id)
        else:
            rev, doc = await self.modcfg.get_published(interaction.guild.id)

        txt = json.dumps(doc, indent=2, ensure_ascii=False)
        if len(txt) > 1900:
            txt = txt[:1900] + "\n... (truncated)"
        await interaction.edit_original_response(content=f"{which.lower()} r{rev}\n```json\n{txt}\n```")

    @mod.command(name="config_reset", description="Reset draft config to defaults")
    async def config_reset(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("ERR_NO_GUILD", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("ERR_PERM_MANAGE_GUILD", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        await self.modcfg.ensure_guild(interaction.guild.id, created_at_iso=_now_iso(), created_by_user_id=interaction.user.id)
        new_rev = await self.modcfg.save_draft(
            interaction.guild.id,
            default_config(),
            created_at_iso=_now_iso(),
            created_by_user_id=interaction.user.id,
        )
        await interaction.edit_original_response(content=f"Draft reset to defaults (r{new_rev}).")

    @mod.command(name="config_publish", description="Publish the current draft moderation config")
    async def config_publish(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("ERR_NO_GUILD", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("ERR_PERM_MANAGE_GUILD", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        await self.modcfg.ensure_guild(interaction.guild.id, created_at_iso=_now_iso(), created_by_user_id=interaction.user.id)
        rev = await self.modcfg.publish(interaction.guild.id, published_by_user_id=interaction.user.id)
        # Invalidate compiled ruleset cache
        self.pipeline.cache.invalidate(interaction.guild.id)
        await interaction.edit_original_response(content=f"Published moderation config revision r{rev}.")

    @mod.command(name="config_validate", description="Validate current draft config")
    async def config_validate(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("ERR_NO_GUILD", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.modcfg.ensure_guild(interaction.guild.id, created_at_iso=_now_iso(), created_by_user_id=interaction.user.id)
        rev, doc = await self.modcfg.get_draft(interaction.guild.id)
        issues = validate_config(doc)
        if not issues:
            await interaction.edit_original_response(content=f"Draft r{rev} is valid.")
            return
        lines = [f"{i.path}: {i.message}" for i in issues[:20]]
        await interaction.edit_original_response(content=f"Draft r{rev} invalid:\n" + "\n".join(lines))

    @mod.command(name="test_event", description="Simulate a message event and show which rules would trigger")
    @app_commands.describe(content="message content to test", mention_count="number of mentions")
    async def test_event(self, interaction: discord.Interaction, content: str, mention_count: int = 0) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("ERR_NO_GUILD", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.modcfg.ensure_guild(interaction.guild.id, created_at_iso=_now_iso(), created_by_user_id=interaction.user.id)

        event = ModEvent(
            guild_id=interaction.guild.id,
            event_type="message_create",
            created_at=datetime.utcnow(),
            user_id=interaction.user.id,
            channel_id=None,
            message_id=None,
            content=content,
            meta={"mention_count": int(mention_count)},
        )
        decision = await self.pipeline.decide(event, member_role_ids=[r.id for r in getattr(interaction.user, "roles", [])])
        if not decision.hits:
            await interaction.edit_original_response(content="No rules matched.")
            return
        out = []
        for h in decision.hits:
            out.append(f"- {h.rule_id} (p{h.priority}) reason={h.reason} actions={[a.action_type for a in h.actions]}")
            if h.stop:
                out.append("  stop=true")
        await interaction.edit_original_response(content="\n".join(out)[:1900])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationSystemCog(bot))
