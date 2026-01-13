from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
import discord
import logging

from .rate_limiter import RateLimiter
from .progress_reporter import ProgressReporter

log = logging.getLogger("guardian.overhaul_engine")


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str]


@dataclass
class DeleteResult:
    channels_deleted: int
    categories_deleted: int
    roles_deleted: int
    skipped: List[str]


@dataclass
class RebuildResult:
    categories_created: int
    channels_created: int
    roles_created: int
    errors: List[str]


@dataclass
class ContentResult:
    posts_created: int
    errors: List[str]


class OverhaulEngine:
    """Engine for performing server overhaul operations."""
    
    def __init__(self, bot: discord.Client, rate_limiter: RateLimiter):
        self.bot = bot
        self.rate_limiter = rate_limiter
    
    async def validate(self, guild: discord.Guild) -> ValidationResult:
        """Validate that overhaul can proceed safely."""
        errors = []
        
        # Check bot permissions
        bot_member = guild.me
        required_perms = [
            discord.Permissions.manage_channels,
            discord.Permissions.manage_roles,
            discord.Permissions.manage_guild
        ]
        
        missing_perms = [perm for perm in required_perms if not bot_member.guild_permissions.value & perm.value]
        if missing_perms:
            errors.append(f"Missing permissions: {', '.join(perm.name for perm in missing_perms)}")
        
        # Check bot role hierarchy
        if bot_member.roles:
            bot_top_role = max(bot_member.roles, key=lambda r: r.position)
            roles_above_bot = [r for r in guild.roles if r.position > bot_top_role.position and r.name != "@everyone"]
            if roles_above_bot:
                errors.append(f"Cannot delete roles above bot: {', '.join(r.name for r in roles_above_bot[:5])}")
        
        # Check guild size
        if guild.member_count > 10000:
            errors.append(f"Large guild ({guild.member_count} members) - overhaul may take significant time")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
    
    async def delete_all(self, guild: discord.Guild, reporter: ProgressReporter) -> DeleteResult:
        """Phase A: Delete all channels, categories, and eligible roles."""
        channels_deleted = 0
        categories_deleted = 0
        roles_deleted = 0
        skipped = []
        
        # Delete channels first (must be done before categories)
        channels = [c for c in guild.channels if not isinstance(c, discord.CategoryChannel)]
        await reporter.start("Deleting Channels", len(channels))
        
        for channel in channels:
            try:
                await self.rate_limiter.execute(channel.delete, reason="Server overhaul")
                channels_deleted += 1
                await reporter.step(f"Deleted #{channel.name}")
            except discord.Forbidden:
                skipped.append(f"Channel #{channel.name} (no permission)")
                await reporter.skip(f"#{channel.name} (no permission)")
            except discord.NotFound:
                await reporter.skip(f"#{channel.name} (already deleted)")
            except Exception as e:
                await reporter.error(f"Failed to delete #{channel.name}", [str(e)])
        
        # Delete categories
        categories = guild.categories
        await reporter.start("Deleting Categories", len(categories))
        
        for category in categories:
            try:
                await self.rate_limiter.execute(category.delete, reason="Server overhaul")
                categories_deleted += 1
                await reporter.step(f"Deleted category {category.name}")
            except discord.Forbidden:
                skipped.append(f"Category {category.name} (no permission)")
                await reporter.skip(f"{category.name} (no permission)")
            except discord.NotFound:
                await reporter.skip(f"{category.name} (already deleted)")
            except Exception as e:
                await reporter.error(f"Failed to delete category {category.name}", [str(e)])
        
        # Delete eligible roles
        bot_top_role = max(guild.me.roles, key=lambda r: r.position) if guild.me.roles else None
        eligible_roles = [
            r for r in guild.roles 
            if r.name != "@everyone" 
            and not r.managed 
            and (not bot_top_role or r.position < bot_top_role.position)
        ]
        
        await reporter.start("Deleting Roles", len(eligible_roles))
        
        for role in eligible_roles:
            try:
                await self.rate_limiter.execute(role.delete, reason="Server overhaul")
                roles_deleted += 1
                await reporter.step(f"Deleted role @{role.name}")
            except discord.Forbidden:
                skipped.append(f"Role @{role.name} (no permission)")
                await reporter.skip(f"@{role.name} (no permission)")
            except discord.NotFound:
                await reporter.skip(f"@{role.name} (already deleted)")
            except Exception as e:
                await reporter.error(f"Failed to delete role @{role.name}", [str(e)])
        
        return DeleteResult(
            channels_deleted=channels_deleted,
            categories_deleted=categories_deleted,
            roles_deleted=roles_deleted,
            skipped=skipped
        )
    
    async def rebuild_all(self, guild: discord.Guild, reporter: ProgressReporter) -> RebuildResult:
        """Phase B: Rebuild clean server architecture."""
        categories_created = 0
        channels_created = 0
        roles_created = 0
        errors = []
        
        # Create roles first
        await reporter.start("Creating Roles", 8)
        roles = await self._create_roles(guild, reporter)
        roles_created = len(roles)
        
        # Create categories
        await reporter.start("Creating Categories", 8)
        categories = await self._create_categories(guild, reporter)
        categories_created = len(categories)
        
        # Create channels
        await reporter.start("Creating Channels", 15)
        channels = await self._create_channels(guild, categories, roles, reporter)
        channels_created = len(channels)
        
        return RebuildResult(
            categories_created=categories_created,
            channels_created=channels_created,
            roles_created=roles_created,
            errors=errors
        )
    
    async def _create_roles(self, guild: discord.Guild, reporter: ProgressReporter) -> List[discord.Role]:
        """Create the role hierarchy."""
        role_configs = [
            ("Verified", discord.Color.green(), 1),
            ("Staff", discord.Color.blue(), 2),
            ("Moderator", discord.Color.purple(), 3),
            ("Admin", discord.Color.red(), 4),
            ("Gamer", discord.Color.orange(), 1),
            ("Developer", discord.Color.dark_grey(), 1),
            ("Artist", discord.Color.magenta(), 1),
            ("Music Lover", discord.Color.teal(), 1)
        ]
        
        roles = []
        for name, color, position in role_configs:
            try:
                role = await self.rate_limiter.execute(
                    guild.create_role, 
                    name=name, 
                    color=color, 
                    reason="Server overhaul"
                )
                if position > 1:
                    await self.rate_limiter.execute(role.edit, position=position)
                roles.append(role)
                await reporter.step(f"Created role @{name}")
            except Exception as e:
                await reporter.error(f"Failed to create role @{name}", [str(e)])
        
        return roles
    
    async def _create_categories(self, guild: discord.Guild, reporter: ProgressReporter) -> List[discord.CategoryChannel]:
        """Create the category structure."""
        category_names = [
            "VERIFY GATE",
            "START", 
            "GENERAL",
            "GAME HUB",
            "GAME SPACES",
            "INTEREST SPACES",
            "SUPPORT",
            "STAFF"
        ]
        
        categories = []
        for name in category_names:
            try:
                category = await self.rate_limiter.execute(
                    guild.create_category,
                    name,
                    reason="Server overhaul"
                )
                categories.append(category)
                await reporter.step(f"Created category {name}")
            except Exception as e:
                await reporter.error(f"Failed to create category {name}", [str(e)])
        
        return categories
    
    async def _create_channels(self, guild: discord.Guild, categories: List[discord.CategoryChannel], 
                            roles: List[discord.Role], reporter: ProgressReporter) -> List[discord.TextChannel]:
        """Create channels within categories."""
        channels = []
        
        # Channel configurations: (name, category_name, overwrites)
        channel_configs = [
            # VERIFY GATE
            ("verify", "VERIFY GATE", None),
            
            # START
            ("welcome", "START", None),
            ("rules", "START", None),
            ("announcements", "START", None),
            
            # GENERAL
            ("general", "GENERAL", None),
            ("chat", "GENERAL", None),
            ("memes", "GENERAL", None),
            
            # GAME HUB
            ("choose-your-games", "GAME HUB", None),
            
            # GAME SPACES
            ("gaming-discussion", "GAME SPACES", None),
            ("game-lfg", "GAME SPACES", None),
            
            # INTEREST SPACES
            ("art-showcase", "INTEREST SPACES", None),
            ("music-chat", "INTEREST SPACES", None),
            
            # SUPPORT
            ("tickets", "SUPPORT", None),
            ("server-info", "SUPPORT", None),
            
            # STAFF
            ("staff-chat", "STAFF", None),
            ("mod-logs", "STAFF", None),
        ]
        
        for name, category_name, overwrites in channel_configs:
            category = discord.utils.get(categories, name=category_name)
            if not category:
                await reporter.error(f"Category {category_name} not found for channel {name}")
                continue
            
            try:
                channel = await self.rate_limiter.execute(
                    guild.create_text_channel,
                    name,
                    category=category,
                    reason="Server overhaul",
                    overwrites=overwrites or {}
                )
                channels.append(channel)
                await reporter.step(f"Created #{name}")
            except Exception as e:
                await reporter.error(f"Failed to create #{name}", [str(e)])
        
        return channels
    
    async def post_content(self, guild: discord.Guild, reporter: ProgressReporter) -> ContentResult:
        """Phase C: Post prepared content to channels."""
        posts_created = 0
        errors = []
        
        # Content definitions
        content_posts = [
            ("verify", self._get_verify_content()),
            ("tickets", self._get_tickets_content()),
            ("server-info", self._get_server_info_content()),
            ("rules", self._get_rules_content()),
            ("announcements", self._get_announcements_content()),
            ("suggestions", self._get_suggestions_content())
        ]
        
        await reporter.start("Posting Content", len(content_posts))
        
        for channel_name, content in content_posts:
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if not channel:
                await reporter.skip(f"Channel #{channel_name} not found")
                continue
            
            try:
                await self.rate_limiter.execute(channel.send, **content)
                posts_created += 1
                await reporter.step(f"Posted content to #{channel_name}")
            except Exception as e:
                await reporter.error(f"Failed to post to #{channel_name}", [str(e)])
        
        return ContentResult(posts_created=posts_created, errors=errors)
    
    def _get_verify_content(self) -> Dict[str, Any]:
        """Get verification channel content."""
        return {
            "content": "Verification Gate",
            "embed": discord.Embed(
                title="Verification Gate",
                description=(
                    "Welcome.\n"
                    "This server is role-locked. You will not see anything until you verify.\n\n"
                    "Click the button below to:\n"
                    "- Confirm you are human\n"
                    "- Accept the rules\n"
                    "- Enter the live server\n\n"
                    "Once verified:\n"
                    "- The gate disappears\n"
                    "- You get access to public areas\n"
                    "- You can pick your game and interest roles\n\n"
                    "If the button does nothing, refresh Discord or rejoin.\n\n"
                    "Verification is required to use this server."
                ),
                color=discord.Color.blue()
            )
        }
    
    def _get_tickets_content(self) -> Dict[str, Any]:
        """Get tickets channel content."""
        return {
            "content": "Support System",
            "embed": discord.Embed(
                title="Support System",
                description=(
                    "Need help from staff?\n\n"
                    "Open a ticket using the button below.\n\n"
                    "Tickets are used for:\n"
                    "- Rule issues\n"
                    "- Member problems\n"
                    "- Reports\n"
                    "- Technical problems\n"
                    "- Role or access issues\n\n"
                    "What happens when you open one:\n"
                    "- A private channel is created\n"
                    "- Only you and staff can see it\n"
                    "- Everything stays logged\n\n"
                    "Do not DM staff directly.\n"
                    "Use the ticket system."
                ),
                color=discord.Color.orange()
            )
        }
    
    def _get_server_info_content(self) -> Dict[str, Any]:
        """Get server-info channel content."""
        return {
            "content": (
                "This server runs on 833's Guardian.\n\n"
                "It is built to stay clean, organized, and easy to use.\n\n"
                "**How access works:**\n"
                "After verifying in #verify you can pick roles in #choose-your-games.\n"
                "Each role unlocks its own channels.\n"
                "If you do not choose a role, those channels will not appear for you.\n\n"
                "**Getting help:**\n"
                "Open a ticket in #tickets.\n\n"
                "**Suggestions:**\n"
                "Post ideas in #suggestions.\n\n"
                "**Profiles and levels:**\n"
                "Use !rank to see your level.\n\n"
                "**Rules:**\n"
                "The rules in #rules apply everywhere. No scams, no harassment, no NSFW."
            )
        }
    
    def _get_rules_content(self) -> Dict[str, Any]:
        """Get rules channel content."""
        return {
            "content": "These rules apply everywhere.",
            "embed": discord.Embed(
                title="Server Rules",
                description=(
                    "**1) No harassment**\n"
                    "No bullying, threats, slurs, or targeting.\n\n"
                    "**2) No scams or fraud**\n"
                    "No fake trades, fake links, impersonation, or tricking people.\n\n"
                    "**3) No NSFW**\n"
                    "No sexual content, gore, or explicit material.\n\n"
                    "**4) No illegal activity**\n"
                    "No piracy, malware, or anything illegal.\n\n"
                    "**5) No spam**\n"
                    "No floods, no self-promo without permission, no bot abuse.\n\n"
                    "**6) Respect staff decisions**\n"
                    "If you disagree, open a ticket. Do not argue publicly.\n\n"
                    "Breaking rules removes access to the server."
                ),
                color=discord.Color.red()
            )
        }
    
    def _get_announcements_content(self) -> Dict[str, Any]:
        """Get announcements channel content."""
        return {
            "content": (
                "This channel is used for:\n"
                "- Server updates\n"
                "- System changes\n"
                "- Events\n"
                "- Important notices\n\n"
                "Do not chat here.\n"
                "Everything posted here matters."
            )
        }
    
    def _get_suggestions_content(self) -> Dict[str, Any]:
        """Get suggestions channel content."""
        return {
            "content": "Have an idea?",
            "embed": discord.Embed(
                title="Suggestions",
                description=(
                    "Post it here.\n\n"
                    "Suggestions should be:\n"
                    "- Clear\n"
                    "- Useful\n"
                    "- Realistic\n\n"
                    "Spam or joke suggestions will be removed.\n\n"
                    "Good ideas get reviewed."
                ),
                color=discord.Color.green()
            )
        }
