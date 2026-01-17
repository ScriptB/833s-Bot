from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .constants import ERROR_MESSAGES
from .utils import error_embed, safe_response

log = logging.getLogger("guardian.error_handlers")


class ErrorHandler(commands.Cog):
    """Centralized error handling for the bot."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Handle command errors."""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands
        
        if isinstance(error, commands.MissingPermissions):
            await safe_response(ctx, embed=error_embed(ERROR_MESSAGES["missing_permissions"]))
            return
        
        if isinstance(error, commands.MissingRequiredArgument):
            await safe_response(ctx, embed=error_embed(f"Missing required argument: {error.param}"))
            return
        
        if isinstance(error, commands.BadArgument):
            await safe_response(ctx, embed=error_embed(f"Invalid argument: {error}"))
            return
        
        if isinstance(error, commands.CommandOnCooldown):
            await safe_response(
                ctx, 
                embed=error_embed(f"This command is on cooldown. Try again in {error.retry_after:.1f}s")
            )
            return
        
        if isinstance(error, commands.BotMissingPermissions):
            await safe_response(ctx, embed=error_embed("The bot lacks required permissions to run this command."))
            return
        
        # Log unexpected errors
        log.exception(f"Unexpected error in command {ctx.command}: {error}")
        await safe_response(ctx, embed=error_embed(ERROR_MESSAGES["database_error"]))
    
    @commands.Cog.listener()
    async def on_application_command_error(
        self, 
        interaction: discord.Interaction, 
        error: discord.app_commands.AppCommandError
    ) -> None:
        """Handle application command errors."""
        if isinstance(error, discord.app_commands.MissingPermissions):
            await safe_response(interaction, embed=error_embed(ERROR_MESSAGES["missing_permissions"]))
            return
        
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            await safe_response(
                interaction,
                embed=error_embed(f"This command is on cooldown. Try again in {error.retry_after:.1f}s")
            )
            return
        
        if isinstance(error, discord.app_commands.BotMissingPermissions):
            await safe_response(interaction, embed=error_embed("The bot lacks required permissions to run this command."))
            return
        
        # Log unexpected errors
        log.exception(f"Unexpected error in app command {interaction.command}: {error}")
        await safe_response(interaction, embed=error_embed(ERROR_MESSAGES["database_error"]))


async def setup_error_handlers(bot: commands.Bot) -> None:
    """Setup error handlers for the bot."""
    await bot.add_cog(ErrorHandler(bot))
