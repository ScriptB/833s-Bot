from __future__ import annotations

import random
import time
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands


@dataclass(frozen=True)
class EconomyTuning:
    currency_name: str = "Credits"
    daily_base: int = 250
    daily_streak_bonus: int = 25          # per streak day (capped)
    daily_streak_cap_days: int = 14
    daily_cooldown_s: int = 20 * 60 * 60  # 20h

    work_min: int = 30
    work_max: int = 140
    work_cooldown_s: int = 12 * 60        # 12m


def _now() -> int:
    return int(time.time())


def _cooldown_left(last_at: int, cooldown: int) -> int:
    if last_at <= 0:
        return 0
    left = (last_at + cooldown) - _now()
    return max(0, int(left))


def _fmt_time(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


class EconomyCog(commands.Cog):
    """Economy + casino games with anti-spam cooldowns and full ledger."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self.tuning = EconomyTuning()

    @app_commands.command(name="balance", description="Show a user's balance.")
    async def balance(self, interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        target = user or interaction.user  # type: ignore[assignment]
        bal, streak, dlast, wlast, _ = await self.bot.economy_store.get_wallet(interaction.guild.id, target.id)  # type: ignore[attr-defined]

        embed = discord.Embed(title=f"{target.display_name}'s Wallet")
        embed.add_field(name=self.tuning.currency_name, value=f"**{bal:,}**", inline=True)
        embed.add_field(name="Daily streak", value=str(streak), inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="daily", description="Claim your daily reward (streak-based).")
    async def daily(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild_id = interaction.guild.id
        user_id = interaction.user.id  # type: ignore[assignment]

        bal, streak, daily_last_at, *_ = await self.bot.economy_store.get_wallet(guild_id, user_id)  # type: ignore[attr-defined]
        left = _cooldown_left(daily_last_at, self.tuning.daily_cooldown_s)
        if left:
            await interaction.followup.send(f"⏳ Daily available in **{_fmt_time(left)}**.", ephemeral=True)
            return

        # streak update: if last claim within 48h window (cooldown+28h), keep streak; else reset
        if daily_last_at and (_now() - daily_last_at) <= (self.tuning.daily_cooldown_s + 28 * 60 * 60):
            new_streak = min(streak + 1, self.tuning.daily_streak_cap_days)
        else:
            new_streak = 1

        bonus_days = max(0, new_streak - 1)
        streak_bonus = bonus_days * self.tuning.daily_streak_bonus
        reward = self.tuning.daily_base + streak_bonus

        new_bal = await self.bot.economy_store.add(guild_id, user_id, reward, reason="daily", meta=f"streak={new_streak}")  # type: ignore[attr-defined]
        await self.bot.economy_store.set_daily_claim(guild_id, user_id, new_streak=new_streak)  # type: ignore[attr-defined]

        # achievement hooks (best-effort)
        try:
            if new_streak >= 7:
                await self.bot.achievements_store.unlock(guild_id, user_id, "daily_streak_7")  # type: ignore[attr-defined]
            if new_streak >= 14:
                await self.bot.achievements_store.unlock(guild_id, user_id, "daily_streak_14")  # type: ignore[attr-defined]
        except Exception:
            pass

        await interaction.followup.send(
            f"✅ Claimed **{reward:,}** {self.tuning.currency_name}. New balance: **{new_bal:,}**. Streak: **{new_streak}**.",
            ephemeral=True,
        )

    @app_commands.command(name="work", description="Do quick work for a small payout (cooldown).")
    async def work(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild_id = interaction.guild.id
        user_id = interaction.user.id  # type: ignore[assignment]

        bal, streak, daily_last_at, work_last_at, _ = await self.bot.economy_store.get_wallet(guild_id, user_id)  # type: ignore[attr-defined]
        left = _cooldown_left(work_last_at, self.tuning.work_cooldown_s)
        if left:
            await interaction.followup.send(f"⏳ Work available in **{_fmt_time(left)}**.", ephemeral=True)
            return

        amount = random.randint(self.tuning.work_min, self.tuning.work_max)
        new_bal = await self.bot.economy_store.add(guild_id, user_id, amount, reason="work")  # type: ignore[attr-defined]
        await self.bot.economy_store.set_work_claim(guild_id, user_id)  # type: ignore[attr-defined]

        try:
            if new_bal >= 10_000:
                await self.bot.achievements_store.unlock(guild_id, user_id, "wallet_10k")  # type: ignore[attr-defined]
            if new_bal >= 100_000:
                await self.bot.achievements_store.unlock(guild_id, user_id, "wallet_100k")  # type: ignore[attr-defined]
        except Exception:
            pass

        await interaction.followup.send(
            f"💼 You earned **{amount:,}** {self.tuning.currency_name}. Balance: **{new_bal:,}**.",
            ephemeral=True,
        )

    @app_commands.command(name="give", description="Transfer Credits to another member.")
    @app_commands.describe(user="Recipient", amount="Amount to transfer")
    async def give(self, interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, 1_000_000]) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        if user.bot:
            await interaction.followup.send("❌ Can't transfer to bots.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.followup.send("❌ Can't transfer to yourself.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        sender = interaction.user.id  # type: ignore[assignment]
        receiver = user.id

        sender_bal, *_ = await self.bot.economy_store.get_wallet(guild_id, sender)  # type: ignore[attr-defined]
        if sender_bal < amount:
            await interaction.followup.send("❌ Insufficient balance.", ephemeral=True)
            return

        await self.bot.economy_store.add(guild_id, sender, -int(amount), reason="transfer_out", meta=f"to={receiver}")  # type: ignore[attr-defined]
        new_receiver = await self.bot.economy_store.add(guild_id, receiver, int(amount), reason="transfer_in", meta=f"from={sender}")  # type: ignore[attr-defined]
        await interaction.followup.send(f"✅ Sent **{amount:,}** to **{user.display_name}**. Their balance: **{new_receiver:,}**.", ephemeral=True)

    @app_commands.command(name="money_top", description="Leaderboard: richest members.")
    async def money_top(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        rows = await self.bot.economy_store.top_balances(interaction.guild.id, limit=10)  # type: ignore[attr-defined]
        if not rows:
            await interaction.followup.send("No data yet.", ephemeral=True)
            return

        lines = []
        for i, (uid, bal) in enumerate(rows, 1):
            member = interaction.guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            lines.append(f"**{i}.** {name} — **{bal:,}**")
        embed = discord.Embed(title=f"Top {self.tuning.currency_name}", description="\n".join(lines))
        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Casino (simple, fair, fully deterministic odds) ---

    @app_commands.command(name="coinflip", description="Bet on heads/tails.")
    @app_commands.describe(side="heads or tails", bet="Amount to bet")
    async def coinflip(self, interaction: discord.Interaction, side: str, bet: app_commands.Range[int, 1, 250_000]) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        side = side.strip().lower()
        if side not in {"heads", "tails", "h", "t"}:
            await interaction.followup.send("Side must be: heads/tails.", ephemeral=True)
            return
        pick = "heads" if side in {"heads", "h"} else "tails"

        gid = interaction.guild.id
        uid = interaction.user.id  # type: ignore[assignment]
        bal, *_ = await self.bot.economy_store.get_wallet(gid, uid)  # type: ignore[attr-defined]
        if bal < bet:
            await interaction.followup.send("❌ Insufficient balance.", ephemeral=True)
            return

        result = random.choice(["heads", "tails"])
        win = (result == pick)
        payout = int(bet) if win else -int(bet)
        new_bal = await self.bot.economy_store.add(gid, uid, payout, reason="coinflip", meta=f"pick={pick},result={result}")  # type: ignore[attr-defined]

        await interaction.followup.send(
            f"🪙 Result: **{result}**. You picked **{pick}**. {'✅ Won' if win else '❌ Lost'} **{abs(payout):,}**. Balance: **{new_bal:,}**.",
            ephemeral=True,
        )

    @app_commands.command(name="slots", description="Spin slots (simple 3-reel).")
    @app_commands.describe(bet="Amount to bet")
    async def slots(self, interaction: discord.Interaction, bet: app_commands.Range[int, 1, 50_000]) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        gid = interaction.guild.id
        uid = interaction.user.id  # type: ignore[assignment]
        bal, *_ = await self.bot.economy_store.get_wallet(gid, uid)  # type: ignore[attr-defined]
        if bal < bet:
            await interaction.followup.send("❌ Insufficient balance.", ephemeral=True)
            return

        # weights tuned: common to rare
        symbols = ["🍒", "🍋", "🍇", "🔔", "💎"]
        weights = [40, 30, 18, 9, 3]

        reels = random.choices(symbols, weights=weights, k=3)
        a, b, c = reels
        mult = 0
        if a == b == c == "💎":
            mult = 20
        elif a == b == c:
            mult = 8
        elif len({a, b, c}) == 2:
            mult = 2
        else:
            mult = 0

        delta = int(bet) * mult - int(bet)
        new_bal = await self.bot.economy_store.add(gid, uid, delta, reason="slots", meta=f"reels={''.join(reels)},mult={mult}")  # type: ignore[attr-defined]
        await interaction.followup.send(
            f"🎰 {' '.join(reels)} — Multiplier: **x{mult}**. {'✅ Win' if mult else '❌ Loss'} **{abs(delta):,}**. Balance: **{new_bal:,}**.",
            ephemeral=True,
        )
