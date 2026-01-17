from __future__ import annotations

import discord
from discord.ext import commands


async def get_application_owner_ids(bot: commands.Bot) -> set[int]:
    """Get the set of application owner IDs (owner + team members)."""
    # Check if we have cached results
    if hasattr(bot, '_cached_owner_ids'):
        return bot._cached_owner_ids
    
    try:
        app_info = await bot.application_info()
        
        owner_ids = set()
        
        if app_info.team:
            # All team members are owners
            for member in app_info.team.members:
                owner_ids.add(member.id)
        else:
            # Single owner
            owner_ids.add(app_info.owner.id)
        
        # Cache the result
        bot._cached_owner_ids = owner_ids
        return owner_ids
        
    except Exception:
        # Fallback to configured owner_id if we can't get app info
        return {getattr(bot, 'owner_id', 0)}


async def is_bot_owner(bot: commands.Bot, user_id: int) -> bool:
    """Check if user is a bot application owner or team member."""
    owner_ids = await get_application_owner_ids(bot)
    return user_id in owner_ids


async def is_root_actor(bot: commands.Bot, ctx: commands.Context | discord.Interaction) -> bool:
    """
    Universal root check for destructive bot commands.
    
    Returns True if:
    - ctx.author is guild owner
    - ctx.author is bot application owner or team member
    - ctx.author is stored root operator
    """
    # Get user from context or interaction
    if isinstance(ctx, commands.Context):
        author = ctx.author
        guild = ctx.guild
    elif isinstance(ctx, discord.Interaction):
        author = ctx.user
        guild = ctx.guild
    else:
        return False
    
    # 1️⃣ Discord-Truth Owners (cannot be faked)
    
    # Guild owner
    if guild and author.id == guild.owner_id:
        return True
    
    # Bot application owner/team
    if await is_bot_owner(bot, author.id):
        return True
    
    # 2️⃣ Root Operators (bot-level, stored in database)
    
    # Check if user is stored root
    if hasattr(bot, 'root_store'):
        try:
            return await bot.root_store.is_root(author.id)
        except Exception:
            # If root store is not available, fall back to configured owner_id
            return author.id == getattr(bot, 'owner_id', 0)
    
    # Fallback to configured owner_id
    return author.id == getattr(bot, 'owner_id', 0)


def root_only():
    """
    Decorator for commands that require root-level access.
    
    This decorator ensures that only root actors can use the command:
    - Guild owners
    - Bot application owners/team members
    - Stored root operators
    """
    async def predicate(ctx: commands.Context | discord.Interaction) -> bool:
        bot = ctx.bot if isinstance(ctx, commands.Context) else ctx.client
        
        is_root = await is_root_actor(bot, ctx)
        
        if not is_root:
            # Send appropriate error message
            if isinstance(ctx, commands.Context):
                await ctx.send("❌ This command requires root-level access.", ephemeral=True)
            else:  # Interaction
                if ctx.response.is_done():
                    await ctx.followup.send("❌ This command requires root-level access.", ephemeral=True)
                else:
                    await ctx.response.send_message("❌ This command requires root-level access.", ephemeral=True)
            return False
        
        return True
    
    return commands.check(predicate)
