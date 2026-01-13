from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
import discord
import logging

from .rate_limiter import RateLimiter
from .progress import ProgressReporter
from ..interfaces import has_required_guild_perms, sanitize_user_text, OperationSnapshot

log = logging.getLogger("guardian.overhaul_engine")


@dataclass
class ValidationResult:
    ok: bool
    missing: List[str]
    reason: str


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
        bot_member = guild.me
        
        # Use interface helper for permission checking
        has_perms, missing = has_required_guild_perms(bot_member)
        
        if has_perms:
            return ValidationResult(ok=True, missing=[], reason="All permissions OK")
        else:
            return ValidationResult(
                ok=False,
                missing=missing,
                reason=f"Missing permissions: {', '.join(missing)}"
            )
        
        # Check bot role hierarchy
        if bot_member.roles:
            bot_top_role = max(bot_member.roles, key=lambda r: r.position)
            roles_above_bot = [r for r in guild.roles if r.position > bot_top_role.position and r.name != "@everyone"]
            if roles_above_bot:
                return ValidationResult(
                    ok=False,
                    missing=["role_hierarchy"],
                    reason=f"Cannot delete roles above bot: {', '.join(r.name for r in roles_above_bot[:5])}"
                )
        
        # Check guild size
        if guild.member_count > 10000:
            return ValidationResult(
                ok=False,
                missing=["guild_size"],
                reason=f"Large guild ({guild.member_count} members) - overhaul may take significant time"
            )
        
        return ValidationResult(ok=True, missing=[], reason="All validations passed")
    
    async def snapshot(self, guild: discord.Guild) -> OperationSnapshot:
        """Take snapshot before destructive operations."""
        return OperationSnapshot(guild)
    
    async def delete_all(self, guild: discord.Guild, reporter: ProgressReporter) -> DeleteResult:
        """Phase A: Delete all channels, categories, and eligible roles."""
        channels_deleted = 0
        categories_deleted = 0
        roles_deleted = 0
        skipped = []
        
        # Delete channels first (must be done before categories)
        channels = [c for c in guild.channels if not isinstance(c, discord.CategoryChannel)]
        await reporter.update("Deleting Channels", 0, len(channels), "Starting channel deletion")
        
        for i, channel in enumerate(channels):
            try:
                await self.rate_limiter.execute(channel.delete, reason="Server overhaul")
                channels_deleted += 1
                await reporter.update("Deleting Channels", i + 1, len(channels), f"Deleted #{channel.name}", counts=self._get_counts())
            except discord.Forbidden:
                skipped.append(f"Channel #{channel.name} (no permission)")
                await reporter.update("Deleting Channels", i + 1, len(channels), f"Skipped #{channel.name} (no permission)", counts=self._get_counts())
            except discord.NotFound:
                await reporter.update("Deleting Channels", i + 1, len(channels), f"Skipped #{channel.name} (already deleted)", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Deleting Channels", i + 1, len(channels), f"Error deleting #{channel.name}", counts=self._get_counts(), errors=1)
        
        # Delete categories
        categories = guild.categories
        await reporter.update("Deleting Categories", 0, len(categories), "Starting category deletion")
        
        for i, category in enumerate(categories):
            try:
                await self.rate_limiter.execute(category.delete, reason="Server overhaul")
                categories_deleted += 1
                await reporter.update("Deleting Categories", i + 1, len(categories), f"Deleted category {category.name}", counts=self._get_counts())
            except discord.Forbidden:
                skipped.append(f"Category {category.name} (no permission)")
                await reporter.update("Deleting Categories", i + 1, len(categories), f"Skipped {category.name} (no permission)", counts=self._get_counts())
            except discord.NotFound:
                await reporter.update("Deleting Categories", i + 1, len(categories), f"Skipped {category.name} (already deleted)", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Deleting Categories", i + 1, len(categories), f"Error deleting category {category.name}", counts=self._get_counts(), errors=1)
        
        # Delete eligible roles
        bot_top_role = max(guild.me.roles, key=lambda r: r.position) if guild.me.roles else None
        eligible_roles = [
            r for r in guild.roles 
            if r.name != "@everyone" 
            and not r.managed 
            and (not bot_top_role or r.position < bot_top_role.position)
        ]
        
        await reporter.update("Deleting Roles", 0, len(eligible_roles), "Starting role deletion")
        
        for i, role in enumerate(eligible_roles):
            try:
                await self.rate_limiter.execute(role.delete, reason="Server overhaul")
                roles_deleted += 1
                await reporter.update("Deleting Roles", i + 1, len(eligible_roles), f"Deleted role @{role.name}", counts=self._get_counts())
            except discord.Forbidden:
                skipped.append(f"Role @{role.name} (no permission)")
                await reporter.update("Deleting Roles", i + 1, len(eligible_roles), f"Skipped @{role.name} (no permission)", counts=self._get_counts())
            except discord.NotFound:
                await reporter.update("Deleting Roles", i + 1, len(eligible_roles), f"Skipped @{role.name} (already deleted)", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Deleting Roles", i + 1, len(eligible_roles), f"Error deleting role @{role.name}", counts=self._get_counts(), errors=1)
        
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
        await reporter.update("Creating Roles", 0, 11, "Starting role creation")
        roles = await self._create_roles(guild, reporter)
        roles_created = len(roles)
        
        # Create categories
        await reporter.update("Creating Categories", 0, 8, "Starting category creation")
        categories = await self._create_categories(guild, reporter)
        categories_created = len(categories)
        
        # Create channels
        await reporter.update("Creating Channels", 0, 28, "Starting channel creation")
        channels = await self._create_channels(guild, categories, roles, reporter)
        channels_created = len(channels)
        
        return RebuildResult(
            categories_created=categories_created,
            channels_created=channels_created,
            roles_created=roles_created,
            errors=errors
        )
    
    async def _create_roles(self, guild: discord.Guild, reporter: ProgressReporter) -> List[discord.Role]:
        """Create the canonical role hierarchy."""
        role_configs = [
            # System Roles
            ("Verified", discord.Color.green(), 1),
            
            # Game Roles
            ("Roblox", discord.Color.red(), 2),
            ("Minecraft", discord.Color.dark_green(), 2),
            ("ARK", discord.Color.dark_orange(), 2),
            ("FPS", discord.Color.dark_red(), 2),
            
            # Interest Roles
            ("Coding", discord.Color.blue(), 3),
            ("Snakes", discord.Color.dark_purple(), 3),
            
            # Staff Roles
            ("Support", discord.Color.gold(), 4),
            ("Moderator", discord.Color.purple(), 5),
            ("Admin", discord.Color.red(), 6),
            ("Owner", discord.Color.dark_grey(), 7)
        ]
        
        roles = []
        for i, (name, color, position) in enumerate(role_configs):
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
                await reporter.update("Creating Roles", i + 1, 11, f"Created role @{name}", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Creating Roles", i + 1, 11, f"Error creating role @{name}", counts=self._get_counts(), errors=1)
        
        return roles
    
    async def _create_categories(self, guild: discord.Guild, reporter: ProgressReporter) -> List[discord.CategoryChannel]:
        """Create canonical category structure."""
        category_names = [
            "🔐 VERIFY GATE",
            "📢 START", 
            "💬 GENERAL",
            "🎛️ REACTION-ROLES",
            "🧩 GAME SPACES",
            "🧩 INTEREST SPACES",
            "🎫 SUPPORT",
            "🛡️ STAFF"
        ]
        
        categories = []
        for i, name in enumerate(category_names):
            try:
                category = await self.rate_limiter.execute(
                    guild.create_category,
                    name,
                    reason="Server overhaul"
                )
                categories.append(category)
                await reporter.update("Creating Categories", i + 1, 8, f"Created category {name}", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Creating Categories", i + 1, 8, f"Error creating category {name}", counts=self._get_counts(), errors=1)
        
        return categories
    
    async def _create_channels(self, guild: discord.Guild, categories: List[discord.CategoryChannel], 
                            roles: List[discord.Role], reporter: ProgressReporter) -> List[discord.TextChannel]:
        """Create channels within categories."""
        channels = []
        
        # Channel configurations: (name, category_name, overwrites)
        channel_configs = [
            # 🔐 VERIFY GATE
            ("verify", "🔐 VERIFY GATE", None),
            
            # 📢 START
            ("welcome", "📢 START", None),
            ("rules", "📢 START", None),
            ("announcements", "📢 START", None),
            ("server-info", "📢 START", None),
            
            # 💬 GENERAL
            ("general-chat", "💬 GENERAL", None),
            ("media", "💬 GENERAL", None),
            ("introductions", "💬 GENERAL", None),
            ("off-topic", "💬 GENERAL", None),
            
            # 🎛️ REACTION-ROLES
            ("reaction-roles", "🎛️ REACTION-ROLES", None),
            ("role-info", "🎛️ REACTION-ROLES", None),
            
            # 🧩 GAME SPACES - ROBLOX
            ("roblox-chat", "🧩 GAME SPACES", None),
            ("bee-swarm", "🧩 GAME SPACES", None),
            ("trading", "🧩 GAME SPACES", None),
            
            # 🧩 GAME SPACES - MINECRAFT
            ("mc-chat", "🧩 GAME SPACES", None),
            ("servers", "🧩 GAME SPACES", None),
            ("builds", "🧩 GAME SPACES", None),
            
            # 🧩 GAME SPACES - ARK
            ("ark-chat", "🧩 GAME SPACES", None),
            ("maps", "🧩 GAME SPACES", None),
            ("breeding", "🧩 GAME SPACES", None),
            
            # 🧩 GAME SPACES - FPS
            ("fps-chat", "🧩 GAME SPACES", None),
            ("loadouts", "🧩 GAME SPACES", None),
            
            # 🧩 INTEREST SPACES - CODING
            ("coding-chat", "🧩 INTEREST SPACES", None),
            ("projects", "🧩 INTEREST SPACES", None),
            ("resources", "🧩 INTEREST SPACES", None),
            
            # 🧩 INTEREST SPACES - SNAKES
            ("snakes-chat", "🧩 INTEREST SPACES", None),
            ("pet-media", "🧩 INTEREST SPACES", None),
            ("care-guides", "🧩 INTEREST SPACES", None),
            
            # 🎫 SUPPORT
            ("tickets", "🎫 SUPPORT", None),
            ("suggestions", "🎫 SUPPORT", None),
            
            # 🛡️ STAFF
            ("staff-chat", "🛡️ STAFF", None),
            ("reports", "🛡️ STAFF", None),
            ("bot-logs", "🛡️ STAFF", None),
            ("case-files", "🛡️ STAFF", None),
        ]
        
        for i, (name, category_name, overwrites) in enumerate(channel_configs):
            category = discord.utils.get(categories, name=category_name)
            if not category:
                await reporter.update("Creating Channels", i + 1, 28, f"Skipped #{name} (category not found)", counts=self._get_counts())
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
                await reporter.update("Creating Channels", i + 1, 28, f"Created #{name}", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Creating Channels", i + 1, 28, f"Error creating #{name}", counts=self._get_counts(), errors=1)
        
        return channels
    
    async def post_content(self, guild: discord.Guild, reporter: ProgressReporter) -> ContentResult:
        """Phase C: Post prepared content to channels."""
        posts_created = 0
        errors = []
        
        # Content definitions
        content_posts = [
            ("verify", self._get_verify_content()),
            ("welcome", self._get_welcome_content()),
            ("rules", self._get_rules_content()),
            ("announcements", self._get_announcements_content()),
            ("server-info", self._get_server_info_content()),
            ("reaction-roles", self._get_reaction_roles_content()),
            ("role-info", self._get_role_info_content()),
            ("tickets", self._get_tickets_content()),
            ("suggestions", self._get_suggestions_content())
        ]
        
        await reporter.update("Posting Content", 0, len(content_posts), "Starting content posting")
        
        for i, (channel_name, content) in enumerate(content_posts):
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if not channel:
                await reporter.update("Posting Content", i + 1, len(content_posts), f"Skipped #{channel_name} (not found)", counts=self._get_counts())
                continue
            
            try:
                await self.rate_limiter.execute(channel.send, **content)
                posts_created += 1
                await reporter.update("Posting Content", i + 1, len(content_posts), f"Posted content to #{channel_name}", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Posting Content", i + 1, len(content_posts), f"Error posting to #{channel_name}", counts=self._get_counts(), errors=1)
        
        return ContentResult(posts_created=posts_created, errors=errors)
    
    def _get_verify_content(self) -> Dict[str, Any]:
        """Get verify channel content."""
        from ..cogs.verify_panel import VerifyView
        
        embed = discord.Embed(
            title=sanitize_user_text("🔐 Verification Gate"),
            description=sanitize_user_text(
                "Welcome.\n"
                "This server is role-locked. You will not see anything until you verify.\n\n"
                "Click button below to:\n"
                "- Confirm you are human\n"
                "- Accept rules\n"
                "- Enter live server\n\n"
                "Once verified:\n"
                "- The gate disappears\n"
                "- You get access to public areas\n"
                "- You can pick your game and interest roles\n\n"
                "If button does nothing, refresh Discord or rejoin.\n\n"
                "Verification is required to use this server."
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Verification is required to access server channels")
        
        view = VerifyView()
        
        return {
            "content": sanitize_user_text("🔐 Verification Gate"),
            "embed": embed,
            "view": view
        }
    
    def _get_tickets_content(self) -> Dict[str, Any]:
        """Get tickets channel content."""
        return {
            "content": sanitize_user_text("🎫 Support System"),
            "embed": discord.Embed(
                title=sanitize_user_text("🎫 Support System"),
                description=sanitize_user_text(
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
            "content": sanitize_user_text(
                "📋 Server Information\n\n"
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
            "content": sanitize_user_text("📜 Server Rules"),
            "embed": discord.Embed(
                title=sanitize_user_text("📜 Server Rules"),
                description=sanitize_user_text(
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
            "content": sanitize_user_text(
                "📢 Announcements\n\n"
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
            "content": sanitize_user_text("💡 Suggestions"),
            "embed": discord.Embed(
                title=sanitize_user_text("💡 Suggestions"),
                description=sanitize_user_text(
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
    
    def _get_welcome_content(self) -> Dict[str, Any]:
        """Get welcome channel content."""
        return {
            "content": sanitize_user_text("👋 Welcome to the Server!"),
            "embed": discord.Embed(
                title=sanitize_user_text("👋 Welcome!"),
                description=sanitize_user_text(
                    "Welcome to our community!\n\n"
                    "Please read the rules in #rules and check #announcements for updates.\n\n"
                    "Once you're ready, head to #reaction-roles to pick your interests.\n\n"
                    "Enjoy your stay!"
                ),
                color=discord.Color.green()
            )
        }
    
    def _get_reaction_roles_content(self) -> Dict[str, Any]:
        """Get reaction-roles channel content."""
        return {
            "content": sanitize_user_text("🎯 Reaction Roles"),
            "embed": discord.Embed(
                title=sanitize_user_text("🎯 Choose Your Roles"),
                description=sanitize_user_text(
                    "React to this message to get access to specific channels!\n\n"
                    "🎮 **Game Roles:**\n"
                    "- 🟥 Roblox\n"
                    "- 🟩 Minecraft\n"
                    "- 🟧 ARK\n"
                    "- 🔴 FPS\n\n"
                    "💻 **Interest Roles:**\n"
                    "- 💠 Coding\n"
                    "- 🐍 Snakes\n\n"
                    "Check #role-info for more details about each role."
                ),
                color=discord.Color.blue()
            )
        }
    
    def _get_role_info_content(self) -> Dict[str, Any]:
        """Get role-info channel content."""
        return {
            "content": sanitize_user_text("📋 Role Information"),
            "embed": discord.Embed(
                title=sanitize_user_text("📋 Role Details"),
                description=sanitize_user_text(
                    "**Game Roles:**\n"
                    "- **Roblox:** Access to Roblox chat, bee swarm, trading\n"
                    "- **Minecraft:** Access to MC chat, servers, builds\n"
                    "- **ARK:** Access to ARK chat, maps, breeding\n"
                    "- **FPS:** Access to FPS chat and loadouts\n\n"
                    "**Interest Roles:**\n"
                    "- **Coding:** Access to coding chat, projects, resources\n"
                    "- **Snakes:** Access to snakes chat, pet media, care guides\n\n"
                    "React in #reaction-roles to get these roles!"
                ),
                color=discord.Color.gold()
            )
        }
    
    def _get_counts(self) -> Dict[str, int]:
        """Get current operation counts for progress reporting."""
        # This is a simplified version - in a real implementation,
        # you'd track these counts properly across operations
        return {
            "deleted_channels": 0,
            "deleted_categories": 0,
            "deleted_roles": 0,
            "created_categories": 0,
            "created_channels": 0,
            "created_roles": 0,
            "skipped": 0
        }
