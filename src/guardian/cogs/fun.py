from __future__ import annotations

import random
import discord
from discord import app_commands
from discord.ext import commands


_EIGHTBALL = [
    "Yes.", "No.", "Maybe.", "Ask again later.", "Unclear.", "Highly likely.", "Highly unlikely.",
    "Focus and try again.", "It is certain.", "Don't count on it."
]

_WYR = [
    ("Have unlimited free time", "Have unlimited money"),
    ("Always be 10 minutes late", "Always be 20 minutes early"),
    ("Only play single-player games", "Only play multiplayer games"),
    ("Never use voice chat", "Never use text chat"),
]

_TRIVIA = [
    ("What does HTTP stand for?", ["HyperText Transfer Protocol", "High Transfer Text Program", "Host Transfer Type Protocol"], 0),
    ("Which planet is known as the Red Planet?", ["Venus", "Mars", "Jupiter"], 1),
    ("In Python, what keyword defines a function?", ["func", "def", "fn"], 1),
]


class FunCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.command(name="8ball", description="Ask the magic 8-ball.")
    async def eightball(self, interaction: discord.Interaction, question: str) -> None:
        ans = random.choice(_EIGHTBALL)
        await interaction.response.send_message(f"🎱 **Q:** {question}\n**A:** {ans}", ephemeral=True)

    @app_commands.command(name="roll", description="Roll dice like 2d6, 1d20, 4d8.")
    async def roll(self, interaction: discord.Interaction, dice: str) -> None:
        s = dice.strip().lower()
        if "d" not in s:
            await interaction.response.send_message("Format: XdY (e.g., 2d6).", ephemeral=True)
            return
        left, right = s.split("d", 1)
        try:
            n = int(left) if left else 1
            d = int(right)
        except ValueError:
            await interaction.response.send_message("Format: XdY (e.g., 2d6).", ephemeral=True)
            return
        if n < 1 or n > 50 or d < 2 or d > 1000:
            await interaction.response.send_message("Limits: 1–50 dice, sides 2–1000.", ephemeral=True)
            return
        rolls = [random.randint(1, d) for _ in range(n)]
        total = sum(rolls)
        await interaction.response.send_message(f"🎲 {dice} → {rolls} (total **{total}**)", ephemeral=True)

    @app_commands.command(name="rps", description="Rock-paper-scissors.")
    async def rps(self, interaction: discord.Interaction, choice: str) -> None:
        c = choice.strip().lower()
        if c not in {"rock", "paper", "scissors"}:
            await interaction.response.send_message("Choice: rock/paper/scissors.", ephemeral=True)
            return
        botc = random.choice(["rock", "paper", "scissors"])
        win = (c == "rock" and botc == "scissors") or (c == "paper" and botc == "rock") or (c == "scissors" and botc == "paper")
        draw = (c == botc)
        outcome = "Draw." if draw else ("Win." if win else "Loss.")
        await interaction.response.send_message(f"🪨📄✂️ You: **{c}** | Bot: **{botc}** → {outcome}", ephemeral=True)

    @app_commands.command(name="wyr", description="Would you rather…")
    async def wyr(self, interaction: discord.Interaction) -> None:
        a, b = random.choice(_WYR)
        embed = discord.Embed(title="Would you rather…", description=f"**A)** {a}\n**B)** {b}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="trivia", description="Quick trivia question.")
    async def trivia(self, interaction: discord.Interaction) -> None:
        q, opts, idx = random.choice(_TRIVIA)
        correct = opts[idx]
        embed = discord.Embed(title="Trivia", description=q)
        for i, opt in enumerate(opts, 1):
            embed.add_field(name=f"Option {i}", value=opt, inline=False)
        embed.set_footer(text=f"Answer: {correct}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
