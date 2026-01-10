from __future__ import annotations

import difflib
import random
from typing import Optional

import discord
from discord.ext import commands


class PrefixCommunityCog(commands.Cog):
    """Non-moderation prefix commands gated by verification and level.

    Prefix commands are convenience shortcuts for community members.
    Slash commands remain the canonical interface; prefix commands are aliases
    that call the same underlying stores/services.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self._vibes: list[str] = [
            "Drop one win from today.",
            "What are you building right now?",
            "Share a song you have on repeat.",
            "If you could add one channel to 833s, what would it be?",
            "Rate today 1-10 and why.",
        ]

        self._help_catalog: dict[str, dict[str, object]] = {
            "vibe": {"category": "Community", "syntax": "!vibe", "desc": "Get a quick community prompt.", "min_level": 0, "verified": True},
            "profile": {"category": "Profile", "syntax": "!profile [@member]", "desc": "Show a public community profile.", "min_level": 0, "verified": True},
            "rank": {"category": "Community", "syntax": "!rank [@member]", "desc": "Show level, XP, reputation, and title.", "min_level": 0, "verified": True},
            "thanks": {"category": "Community", "syntax": "!thanks @member [reason]", "desc": "Give +1 reputation (cooldown).", "min_level": 1, "verified": True},
            "prompt": {"category": "Community", "syntax": "!prompt", "desc": "Show the current community prompt.", "min_level": 0, "verified": True},
            "event": {"category": "Events", "syntax": "!event", "desc": "List active events.", "min_level": 0, "verified": True},
            "help": {"category": "Utility", "syntax": "!help [command]", "desc": "Show prefix help.", "min_level": 0, "verified": False},
        }

    async def _is_verified(self, guild: discord.Guild, member: discord.Member) -> bool:
        cfg = await self.bot.server_config_store.get(guild.id)  # type: ignore[attr-defined]
        role_id = cfg.autorole_id
        if not role_id:
            return True

        return any(r.id == role_id for r in member.roles)

    async def _level(self, guild_id: int, user_id: int) -> int:
        _, _, lvl = await self.bot.levels_store.get(guild_id, user_id)  # type: ignore[attr-defined]
        return int(lvl)

    async def _channel_allowed(self, guild: discord.Guild, channel_id: int) -> bool:
        cfg = await self.bot.server_config_store.get(guild.id)  # type: ignore[attr-defined]
        # If configured, only allow in the bot commands channel.
        if cfg.bot_commands_channel_id:
            return int(channel_id) == int(cfg.bot_commands_channel_id)
        return True

    async def _gate(
        self,
        ctx: commands.Context,
        *,
        min_level: int = 0,
        requires_verified: bool = True,
    ) -> bool:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False
        if not await self._channel_allowed(ctx.guild, ctx.channel.id):  # type: ignore[union-attr]
            try:
                await ctx.reply("Use this in the bot commands channel.")
            except Exception:
                pass
            return False

        if requires_verified:
            ok = await self._is_verified(ctx.guild, ctx.author)
            if not ok:
                try:
                    await ctx.reply("You must be verified to use this command.")
                except Exception:
                    pass
                return False

        lvl = await self._level(ctx.guild.id, ctx.author.id)
        if lvl < min_level:
            try:
                await ctx.reply(f"Requires level {min_level} (you are level {lvl}).")
            except Exception:
                pass
            return False
        return True

    async def _gate_status(
        self,
        ctx: commands.Context,
        *,
        min_level: int = 0,
        requires_verified: bool = True,
    ) -> tuple[bool, str | None]:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return (False, "This command can only be used in a server.")

        if not await self._channel_allowed(ctx.guild, ctx.channel.id):  # type: ignore[union-attr]
            return (False, "Use this in the bot commands channel.")

        if requires_verified:
            ok = await self._is_verified(ctx.guild, ctx.author)
            if not ok:
                return (False, "You must be verified to use this command.")

        lvl = await self._level(ctx.guild.id, ctx.author.id)
        if lvl < min_level:
            return (False, f"Requires level {min_level} (you are level {lvl}).")

        return (True, None)

    @commands.command(name="help")
    @commands.cooldown(2, 10.0, commands.BucketType.user)
    async def help_cmd(self, ctx: commands.Context, *, query: str = "") -> None:
        if not await self._gate(ctx, min_level=0, requires_verified=False):
            return

        q = (query or "").strip().lower()

        if not q:
            categories: dict[str, list[str]] = {}
            for name, meta in self._help_catalog.items():
                cat = str(meta.get("category") or "Utility")
                categories.setdefault(cat, []).append(name)

            emb = discord.Embed(
                title="833s Guardian • Prefix Help",
                description="Use `!help <command>` for details. Slash commands remain primary; use `/help_commands` for the full list.",
            )

            for cat in ["Community", "Profile", "Events", "Fun", "Utility"]:
                cmds = sorted(categories.get(cat, []))
                if not cmds:
                    continue
                lines: list[str] = []
                for cmd in cmds:
                    meta = self._help_catalog.get(cmd, {})
                    min_level = int(meta.get("min_level") or 0)
                    verified = bool(meta.get("verified") or False)
                    ok, reason = await self._gate_status(ctx, min_level=min_level, requires_verified=verified)
                    suffix = ""
                    if not ok:
                        suffix = f" — 🔒 {reason}"
                    elif min_level or verified:
                        req = []
                        if verified:
                            req.append("verified")
                        if min_level:
                            req.append(f"lvl {min_level}+")
                        suffix = f" — ({', '.join(req)})" if req else ""
                    desc = str(meta.get("desc") or "")
                    lines.append(f"`{cmd}` — {desc}{suffix}")
                emb.add_field(name=cat, value="\n".join(lines)[:1024], inline=False)

            try:
                await ctx.reply(embed=emb)
            except Exception:
                pass
            return

        # Normalize aliases/shortcuts
        if q.startswith("!"):
            q = q[1:]

        if q not in self._help_catalog:
            choices = sorted(self._help_catalog.keys())
            matches = difflib.get_close_matches(q, choices, n=3, cutoff=0.55)
            suggestion = (" Did you mean: " + ", ".join(f"`{m}`" for m in matches)) if matches else ""
            try:
                await ctx.reply(f"Unknown command `{q}`.{suggestion}")
            except Exception:
                pass
            return

        meta = self._help_catalog[q]
        min_level = int(meta.get("min_level") or 0)
        verified = bool(meta.get("verified") or False)
        ok, reason = await self._gate_status(ctx, min_level=min_level, requires_verified=verified)

        emb = discord.Embed(title=f"Prefix Help: !{q}")
        emb.add_field(name="Syntax", value=f"`{meta.get('syntax')}`", inline=False)
        emb.add_field(name="Description", value=str(meta.get("desc") or "—")[:900], inline=False)

        req_lines: list[str] = []
        if verified:
            req_lines.append("Verified required")
        if min_level:
            req_lines.append(f"Minimum level: {min_level}")
        if req_lines:
            emb.add_field(name="Requirements", value="\n".join(req_lines), inline=False)

        if not ok and reason:
            emb.add_field(name="Why you can't use it right now", value=reason, inline=False)

        try:
            await ctx.reply(embed=emb)
        except Exception:
            pass

    @commands.command(name="vibe")
    @commands.cooldown(2, 10.0, commands.BucketType.user)
    async def vibe(self, ctx: commands.Context) -> None:
        if not await self._gate(ctx, min_level=0, requires_verified=True):
            return
        await ctx.reply(random.choice(self._vibes))

    @commands.command(name="my_prompt")
    @commands.cooldown(2, 10.0, commands.BucketType.user)
    async def prompt(self, ctx: commands.Context) -> None:
        if not await self._gate(ctx, min_level=0, requires_verified=True):
            return
        if not ctx.guild:
            return
        p = await self.bot.prompts_store.get_current(ctx.guild.id)  # type: ignore[attr-defined]
        if not p:
            await ctx.reply("No prompts yet.")
            return
        await ctx.reply(f"Prompt #{p.prompt_id}: {p.text}")

    @commands.command(name="my_profile")
    @commands.cooldown(2, 10.0, commands.BucketType.user)
    async def profile(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        if not await self._gate(ctx, min_level=0, requires_verified=True):
            return
        if not ctx.guild:
            return
        member = member or ctx.author  # type: ignore[assignment]
        prof = await self.bot.profiles_store.get(ctx.guild.id, member.id)  # type: ignore[attr-defined]
        title_state = await self.bot.titles_store.get(ctx.guild.id, member.id)  # type: ignore[attr-defined]
        rep = await self.bot.reputation_store.get(ctx.guild.id, member.id)  # type: ignore[attr-defined]
        _, xp, lvl = await self.bot.levels_store.get(ctx.guild.id, member.id)  # type: ignore[attr-defined]
        if not prof.is_public and member.id != ctx.author.id:
            await ctx.reply("That profile is private.")
            return
        lines = [f"Profile: {member.display_name}"]
        if title_state.equipped:
            lines.append(f"Title: {title_state.equipped}")
        lines.append(f"Level: {int(lvl)} • XP: {int(xp)} • Rep: {int(rep)}")
        if prof.pronouns:
            lines.append(f"Pronouns: {prof.pronouns}")
        if prof.interests:
            lines.append(f"Interests: {', '.join(prof.interests)}")
        if prof.about:
            lines.append(f"About: {prof.about[:200]}")
        await ctx.reply("\n".join(lines))

    @commands.command(name="rank")
    @commands.cooldown(2, 10.0, commands.BucketType.user)
    async def rank(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        if not await self._gate(ctx, min_level=0, requires_verified=True):
            return
        if not ctx.guild:
            return
        member = member or ctx.author  # type: ignore[assignment]
        title_state = await self.bot.titles_store.get(ctx.guild.id, member.id)  # type: ignore[attr-defined]
        rep = await self.bot.reputation_store.get(ctx.guild.id, member.id)  # type: ignore[attr-defined]
        _, xp, lvl = await self.bot.levels_store.get(ctx.guild.id, member.id)  # type: ignore[attr-defined]
        title = f" • {title_state.equipped}" if title_state.equipped else ""
        await ctx.reply(f"{member.display_name}: Level {int(lvl)} (XP {int(xp)}), Rep {int(rep)}{title}")

    @commands.command(name="my_event")
    @commands.cooldown(2, 10.0, commands.BucketType.user)
    async def event(self, ctx: commands.Context) -> None:
        if not await self._gate(ctx, min_level=0, requires_verified=True):
            return
        if not ctx.guild:
            return
        events = await self.bot.events_store.list_active(ctx.guild.id, 5)  # type: ignore[attr-defined]
        if not events:
            await ctx.reply("No active events.")
            return
        lines = ["Active events:"]
        for e in events:
            lines.append(f"#{e.event_id} • <t:{e.start_ts}:R> • {e.title}")
        await ctx.reply("\n".join(lines))

    @commands.command(name="thanks")
    @commands.cooldown(1, 30.0, commands.BucketType.user)
    async def thanks(self, ctx: commands.Context, member: Optional[discord.Member] = None, *, reason: str = "") -> None:
        if not await self._gate(ctx, min_level=1, requires_verified=True):
            return
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        if member is None or member.bot:
            await ctx.reply("Tag a member to thank.")
            return
        if member.id == ctx.author.id:
            await ctx.reply("You cannot thank yourself.")
            return

        ok, _ = await self.bot.reputation_store.give(ctx.guild.id, ctx.author.id, member.id, 1)  # type: ignore[attr-defined]
        if not ok:
            await ctx.reply("You can use this again later.")
            return
        await ctx.reply(f"Thanks recorded for {member.mention}.")
