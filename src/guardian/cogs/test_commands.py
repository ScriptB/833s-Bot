"""
test_commands.py

This module intentionally contains no commands.
All dev/test/selftest commands are removed from production builds.
"""

from discord.ext import commands


class TestCommandsCog(commands.Cog):
    """Placeholder cog. No commands are registered."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    # Cog is loadable but does nothing.
    await bot.add_cog(TestCommandsCog(bot))
