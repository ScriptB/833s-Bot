from __future__ import annotations

import asyncio
import time
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

import discord
from discord import app_commands
from discord.ext import commands
import logging

from guardian.services.api_wrapper import safe_send_message, safe_create_channel, safe_create_category, safe_create_role
from guardian.observability import observability, log_command_execution
from guardian.security.permissions import admin_command
from guardian.constants import COLORS

log = logging.getLogger("guardian.overhaul")


class OverhaulPhase(Enum):
    """Overhaul execution phases."""
    VALIDATION = "validation"
    SNAPSHOT = "snapshot"
    DELETION = "deletion"
    REBUILDING = "rebuilding"
    CONTENT = "content"
    FINALIZATION = "finalization"


@dataclass
class OverhaulConfig:
    """Configuration for overhaul operations."""
    preserve_bot_roles: bool = True
    preserve_managed_roles: bool = True
    preserve_integrations: bool = True
    create_backup: bool = True
    dry_run: bool = False
    batch_size: int = 5
    delay_between_operations: float = 0.5


@dataclass
class OverhaulResult:
    """Result of overhaul operation."""
    success: bool
    phase: str
    deleted: Dict[str, int]
    created: Dict[str, int]
    errors: List[str]
    warnings: List[str]
    duration_ms: float
    guild_id: int
    user_id: int


class OverhaulEngine:
    """Production-grade server overhaul engine."""
    
    def __init__(self, bot: commands.Bot, config: OverhaulConfig = None):
        self.bot = bot
        self.config = config or OverhaulConfig()
        self._operation_start = None
    
    async def execute_overhaul(self, interaction: discord.Interaction) -> OverhaulResult:
        """Execute complete server overhaul with proper error handling and progress tracking."""
        start_time = time.time()
        
        if not interaction.guild:
            raise ValueError("Overhaul can only be executed in a server")
        
        guild = interaction.guild
        user = interaction.user
        
        log_command_execution(
            "overhaul",
            user=user,
            guild=guild,
            success=True
        )
        
        try:
            # Phase 1: Validation
            validation_result = await self._validate_guild(guild)
            if not validation_result[0]:
                return OverhaulResult(
                    success=False,
                    phase=OverhaulPhase.VALIDATION,
                    deleted={},
                    created={},
                    errors=validation_result[1],
                    warnings=[],
                    duration_ms=(time.time() - start_time) * 1000,
                    guild_id=guild.id,
                    user_id=user.id
                )
            
            # Phase 2: Snapshot
            snapshot = await self._create_snapshot(guild)
            
            # Phase 3: Deletion (if not dry run)
            if self.config.dry_run:
                deleted = {"channels": 0, "categories": 0, "roles": 0}
                log.info("DRY RUN: Skipping deletion phase")
            else:
                deleted = await self._delete_all_content(guild, snapshot)
            
            # Phase 4: Rebuilding
            created = await self._rebuild_server(guild, snapshot)
            
            # Phase 5: Content posting
            content_result = await self._post_initial_content(guild, created["roles"])
            
            duration_ms = (time.time() - start_time) * 1000
            
            return OverhaulResult(
                success=True,
                phase=OverhaulPhase.FINALIZATION,
                deleted=deleted,
                created=created,
                errors=[],
                warnings=[] if not self.config.dry_run else ["This was a dry run - no actual changes made"],
                duration_ms=duration_ms,
                guild_id=guild.id,
                user_id=user.id
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log.exception(f"Critical error during overhaul: {e}")
            
            return OverhaulResult(
                success=False,
                phase=OverhaulPhase.FINALIZATION,
                deleted={},
                created={},
                errors=[f"Critical error: {str(e)}"],
                warnings=[],
                duration_ms=duration_ms,
                guild_id=guild.id,
                user_id=user.id
            )
    
    async def _validate_guild(self, guild: discord.Guild) -> Tuple[bool, List[str]]:
        """Validate guild for overhaul compatibility."""
        errors = []
        
        # Check bot permissions
        required_perms = [
            "manage_channels",
            "manage_roles", 
            "manage_guild",
            "read_messages",
            "send_messages",
            "embed_links"
        ]
        
        bot_member = guild.me
        missing_perms = [
            perm.replace("_", " ").title()
            for perm in required_perms
            if not getattr(bot_member.guild_permissions, perm, False)
        ]
        
        if missing_perms:
            errors.append(f"Bot missing permissions: {', '.join(missing_perms)}")
        
        # Check bot role hierarchy
        if bot_member.roles:
            bot_top_role = max(bot_member.roles, key=lambda r: r.position)
            owner_role = discord.utils.get(guild.roles, name="Owner")
            if owner_role and bot_top_role.position <= owner_role.position:
                errors.append("Bot role must be above Owner role")
        
        # Check member count
        if guild.member_count < 2:
            errors.append("Server must have at least 2 members for overhaul")
        
        return (len(errors) == 0, errors)
    
    async def _create_snapshot(self, guild: discord.Guild) -> Dict[str, Any]:
        """Create snapshot of current server state."""
        return {
            "guild_id": guild.id,
            "guild_name": guild.name,
            "categories": [
                {
                    "id": cat.id,
                    "name": cat.name,
                    "position": cat.position
                }
                for cat in guild.categories
            ],
            "channels": [
                {
                    "id": ch.id,
                    "name": ch.name,
                    "type": str(ch.type),
                    "category_id": ch.category.id if ch.category else None,
                    "position": ch.position,
                    "nsfw": ch.nsfw,
                    "topic": ch.topic
                }
                for ch in guild.channels
                if not isinstance(ch, discord.CategoryChannel)
            ],
            "roles": [
                {
                    "id": role.id,
                    "name": role.name,
                    "position": role.position,
                    "color": role.color.value,
                    "permissions": role.permissions.value,
                    "managed": role.managed,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable
                }
                for role in guild.roles
            ],
            "timestamp": time.time()
        }
    
    async def _delete_all_content(self, guild: discord.Guild, snapshot: Dict[str, Any]) -> Dict[str, int]:
        """Delete all channels, categories, and eligible roles."""
        deleted = {"channels": 0, "categories": 0, "roles": 0}
        
        # Phase 1: Delete channels first (required before categories)
        channels = [ch for ch in guild.channels if not isinstance(ch, discord.CategoryChannel)]
        
        for i in range(0, len(channels), self.config.batch_size):
            batch = channels[i:i + self.config.batch_size]
            await self._delete_channel_batch(batch, deleted)
            
            if i + self.config.batch_size < len(channels):
                await asyncio.sleep(self.config.delay_between_operations)
        
        # Phase 2: Delete categories
        categories = guild.categories
        for i in range(0, len(categories), self.config.batch_size):
            batch = categories[i:i + self.config.batch_size]
            await self._delete_category_batch(batch, deleted)
            
            if i + self.config.batch_size < len(categories):
                await asyncio.sleep(self.config.delay_between_operations)
        
        # Phase 3: Delete eligible roles
        bot_top_role = max(guild.me.roles, key=lambda r: r.position) if guild.me.roles else None
        
        eligible_roles = [
            role for role in guild.roles
            if (role.name != "@everyone" 
                and not role.managed 
                and (not bot_top_role or role.position < bot_top_role.position)
                and not self._should_preserve_role(role))
        ]
        
        for i in range(0, len(eligible_roles), self.config.batch_size):
            batch = eligible_roles[i:i + self.config.batch_size]
            await self._delete_role_batch(batch, deleted)
            
            if i + self.config.batch_size < len(eligible_roles):
                await asyncio.sleep(self.config.delay_between_operations)
        
        return deleted
    
    def _should_preserve_role(self, role: discord.Role) -> bool:
        """Check if role should be preserved during overhaul."""
        if self.config.preserve_bot_roles and "bot" in role.name.lower():
            return True
        
        if self.config.preserve_managed_roles and role.managed:
            return True
        
        if self.config.preserve_integrations and any(
            integration.name.lower() in role.name.lower()
            for integration in ["MEE6", "Carl-bot", "Dyno", "Nightbot"]
        ):
            return True
        
        return False
    
    async def _delete_channel_batch(self, channels: List[discord.abc.GuildChannel], deleted: Dict[str, int]):
        """Delete a batch of channels with error handling."""
        for channel in channels:
            try:
                result = await safe_send_message(
                    channel,
                    "🔄 This channel will be deleted as part of server overhaul",
                    delete_after=5.0
                )
                # Don't wait for deletion, continue immediately
                await channel.delete(reason="Server overhaul")
                deleted["channels"] += 1
                log.debug(f"Deleted channel: {channel.name}")
                
            except discord.Forbidden:
                log.warning(f"No permission to delete channel: {channel.name}")
            except discord.NotFound:
                log.debug(f"Channel already deleted: {channel.name}")
            except Exception as e:
                log.error(f"Error deleting channel {channel.name}: {e}")
    
    async def _delete_category_batch(self, categories: List[discord.CategoryChannel], deleted: Dict[str, int]):
        """Delete a batch of categories with error handling."""
        for category in categories:
            try:
                await category.delete(reason="Server overhaul")
                deleted["categories"] += 1
                log.debug(f"Deleted category: {category.name}")
                
            except discord.Forbidden:
                log.warning(f"No permission to delete category: {category.name}")
            except discord.NotFound:
                log.debug(f"Category already deleted: {category.name}")
            except Exception as e:
                log.error(f"Error deleting category {category.name}: {e}")
    
    async def _delete_role_batch(self, roles: List[discord.Role], deleted: Dict[str, int]):
        """Delete a batch of roles with error handling."""
        for role in roles:
            try:
                await role.delete(reason="Server overhaul")
                deleted["roles"] += 1
                log.debug(f"Deleted role: {role.name}")
                
            except discord.Forbidden:
                log.warning(f"No permission to delete role: {role.name}")
            except discord.NotFound:
                log.debug(f"Role already deleted: {role.name}")
            except Exception as e:
                log.error(f"Error deleting role {role.name}: {e}")
    
    async def _rebuild_server(self, guild: discord.Guild, snapshot: Dict[str, Any]) -> Dict[str, int]:
        """Rebuild server with proper architecture."""
        created = {"categories": 0, "channels": 0, "roles": 0}
        
        # Phase 1: Create roles first (required for channels)
        roles = await self._create_role_hierarchy(guild)
        created["roles"] = len(roles)
        
        # Phase 2: Create categories
        categories = await self._create_category_structure(guild)
        created["categories"] = len(categories)
        
        # Phase 3: Create channels
        channels = await self._create_channel_structure(guild, categories, roles)
        created["channels"] = len(channels)
        
        return created
    
    async def _create_role_hierarchy(self, guild: discord.Guild) -> List[discord.Role]:
        """Create optimized role hierarchy."""
        role_configs = [
            # Bot Roles (Highest priority)
            ("Guardian Bot", discord.Color.default(), 0, True),
            ("Guardian Services", discord.Color.default(), 1, True),
            
            # Staff Roles
            ("Owner", discord.Color.dark_grey(), 10, True),
            ("Admin", discord.Color.dark_red(), 9, True),
            ("Moderator", discord.Color.purple(), 8, True),
            ("Support", discord.Color.gold(), 7, True),
            
            # System Roles
            ("Verified", discord.Color.green(), 5, False),
            
            # Game Roles (Lower priority, assignable)
            ("Roblox", discord.Color.red(), 3, False),
            ("Minecraft", discord.Color.dark_green(), 3, False),
            ("ARK", discord.Color.orange(), 3, False),
            ("FPS", discord.Color.dark_red(), 3, False),
            
            # Interest Roles
            ("Coding", discord.Color.blue(), 2, False),
            ("Snakes", discord.Color.dark_purple(), 2, False)
        ]
        
        roles = []
        for name, color, position, hoist in role_configs:
            try:
                result = await safe_create_role(
                    guild=guild,
                    name=name,
                    color=color,
                    permissions=self._get_role_permissions(name),
                    hoist=hoist,
                    reason="Server overhaul"
                )
                
                if result.success:
                    roles.append(result.data)
                    log.debug(f"Created role: {name}")
                else:
                    log.error(f"Failed to create role {name}: {result.error}")
                    
            except Exception as e:
                log.error(f"Error creating role {name}: {e}")
        
        return roles
    
    def _get_role_permissions(self, role_name: str) -> discord.Permissions:
        """Get appropriate permissions for role based on name."""
        admin_roles = ["Owner", "Admin", "Moderator", "Support"]
        
        if role_name in admin_roles:
            return discord.Permissions(
                administrator=True,
                manage_channels=True,
                manage_roles=True,
                manage_guild=True,
                kick_members=True,
                ban_members=True,
                manage_messages=True,
                embed_links=True,
                read_messages=True,
                send_messages=True,
                attach_files=True,
                read_message_history=True
            )
        elif role_name == "Verified":
            return discord.Permissions(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True
            )
        else:
            # Game/Interest roles - basic permissions
            return discord.Permissions(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                add_reactions=True
            )
    
    async def _create_category_structure(self, guild: discord.Guild) -> List[discord.CategoryChannel]:
        """Create optimized category structure."""
        category_configs = [
            ("🔐 SECURE", 0),
            ("📢 START", 1),
            ("💬 GENERAL", 2),
            ("🎛️ REACTION-ROLES", 3),
            ("🧩 GAME SPACES", 4),
            ("🧩 INTEREST SPACES", 5),
            ("🎫 SUPPORT", 6),
            ("🛡️ STAFF", 7)
        ]
        
        categories = []
        for name, position in category_configs:
            try:
                result = await safe_create_category(
                    guild=guild,
                    name=name,
                    position=position,
                    reason="Server overhaul"
                )
                
                if result.success:
                    categories.append(result.data)
                    log.debug(f"Created category: {name}")
                else:
                    log.error(f"Failed to create category {name}: {result.error}")
                    
            except Exception as e:
                log.error(f"Error creating category {name}: {e}")
        
        return categories
    
    async def _create_channel_structure(self, guild: discord.Guild, categories: List[discord.CategoryChannel], roles: List[discord.Role]) -> List[discord.abc.GuildChannel]:
        """Create optimized channel structure."""
        channel_configs = [
            # Verification
            ("verify", "🔐 SECURE", discord.ChannelType.text, None),
            
            # Start channels
            ("welcome", "📢 START", discord.ChannelType.text, None),
            ("rules", "📢 START", discord.ChannelType.text, None),
            ("announcements", "📢 START", discord.ChannelType.text, None),
            
            # General channels
            ("general", "💬 GENERAL", discord.ChannelType.text, None),
            ("bot-commands", "💬 GENERAL", discord.ChannelType.text, None),
            
            # Role assignment
            ("reaction-roles", "🎛️ REACTION-ROLES", discord.ChannelType.text, None),
            
            # Support channels
            ("support-start", "🎫 SUPPORT", discord.ChannelType.text, None),
            
            # Staff channels
            ("staff-chat", "🛡️ STAFF", discord.ChannelType.text, None),
            ("staff-commands", "🛡️ STAFF", discord.ChannelType.text, None),
            
            # Game channels (all in GAME SPACES category)
            ("roblox-chat", "🧩 GAME SPACES", discord.ChannelType.text, None),
            ("roblox-voice", "🧩 GAME SPACES", discord.ChannelType.voice, None),
            ("minecraft-chat", "🧩 GAME SPACES", discord.ChannelType.text, None),
            ("minecraft-voice", "🧩 GAME SPACES", discord.ChannelType.voice, None),
            ("ark-chat", "🧩 GAME SPACES", discord.ChannelType.text, None),
            ("ark-voice", "🧩 GAME SPACES", discord.ChannelType.voice, None),
            ("fps-chat", "🧩 GAME SPACES", discord.ChannelType.text, None),
            ("fps-voice", "🧩 GAME SPACES", discord.ChannelType.voice, None),
            
            # Interest channels
            ("coding-chat", "🧩 INTEREST SPACES", discord.ChannelType.text, None),
            ("coding-voice", "🧩 INTEREST SPACES", discord.ChannelType.voice, None),
            ("snakes-chat", "🧩 INTEREST SPACES", discord.ChannelType.text, None),
            ("snakes-voice", "🧩 INTEREST SPACES", discord.ChannelType.voice, None)
        ]
        
        channels = []
        category_lookup = {cat.name: cat for cat in categories}
        
        for name, category_name, channel_type, extra_config in channel_configs:
            try:
                category = category_lookup.get(category_name)
                if not category:
                    log.warning(f"Category {category_name} not found for channel {name}")
                    continue
                
                overwrites = self._get_channel_overwrites(name, roles, extra_config)
                
                result = await safe_create_channel(
                    guild=guild,
                    name=name,
                    channel_type=channel_type,
                    category=category,
                    overwrites=overwrites,
                    reason="Server overhaul"
                )
                
                if result.success:
                    channels.append(result.data)
                    log.debug(f"Created channel: {name}")
                else:
                    log.error(f"Failed to create channel {name}: {result.error}")
                    
            except Exception as e:
                log.error(f"Error creating channel {name}: {e}")
        
        return channels
    
    def _get_channel_overwrites(self, channel_name: str, roles: List[discord.Role], extra_config: Any = None) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Get permission overwrites for a channel."""
        overwrites = {}
        
        # Default overwrites
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            read_messages=False,
            send_messages=False,
            embed_links=False,
            attach_files=False,
            read_message_history=False
        )
        
        # Bot permissions
        bot_role = discord.utils.get(roles, name="Guardian Bot")
        if bot_role:
            overwrites[bot_role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True
            )
        
        # Channel-specific overwrites
        if channel_name.startswith("verify"):
            verified_role = discord.utils.get(roles, name="Verified")
            if verified_role:
                overwrites[verified_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    read_message_history=True
                )
        
        elif channel_name.startswith("staff"):
            staff_roles = [r for r in roles if any(s in r.name.lower() for s in ["admin", "moderator", "support", "owner"])]
            for role in staff_roles:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True
                )
        
        return overwrites
    
    async def _post_initial_content(self, guild: discord.Guild, roles: List[discord.Role]) -> Dict[str, int]:
        """Post initial content to channels."""
        posts_created = 0
        
        # Find verification channel
        verify_channel = discord.utils.get(guild.text_channels, name="verify")
        if verify_channel:
            embed = discord.Embed(
                title="🔐 Verification Required",
                description=(
                    "Welcome to the server! Please verify to access all channels.\n\n"
                    "Use the button below to get the **Verified** role."
                ),
                color=COLORS["primary"]
            )
            
            # This would need a persistent view - for now just send message
            result = await safe_send_message(verify_channel, embed=embed)
            if result.success:
                posts_created += 1
        
        # Find rules channel
        rules_channel = discord.utils.get(guild.text_channels, name="rules")
        if rules_channel:
            embed = discord.Embed(
                title="📜 Server Rules",
                description=(
                    "1. Be respectful to all members\n"
                    "2. No spam or self-promotion\n"
                    "3. Follow Discord's Terms of Service\n"
                    "4. Listen to staff instructions\n"
                    "5. Have fun and enjoy your stay!"
                ),
                color=COLORS["primary"]
            )
            
            result = await safe_send_message(rules_channel, embed=embed)
            if result.success:
                posts_created += 1
        
        return {"posts_created": posts_created}


class OverhaulConfirmationView(discord.ui.View):
    """Persistent confirmation view for overhaul command."""
    
    def __init__(self):
        super().__init__(timeout=300)  # 5 minutes timeout
    
    @discord.ui.button(
        label="Confirm Server Overhaul",
        style=discord.ButtonStyle.danger,
        custom_id="guardian_overhaul_confirm"
    )
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle confirmation button."""
        await interaction.response.defer(ephemeral=True)
        
        # Get the overhaul cog
        cog = interaction.client.get_cog('OverhaulTempCog')
        if not cog:
            await interaction.followup.send("❌ Overhaul system not available.", ephemeral=True)
            return
        
        # Stop this view
        self.stop()
        
        # Execute overhaul
        await interaction.followup.send(
            "🔄 **Starting server overhaul...**\n\n"
            "This will take a few minutes. You'll be notified when complete.",
            ephemeral=True
        )
        
        # Execute the overhaul
        result = await cog.execute_overhaul(interaction)
        
        # Send final result
        if result.success:
            embed = discord.Embed(
                title="✅ Server Overhaul Complete",
                description=(
                    f"**Phase:** {result.phase.title()}\n\n"
                    f"**Deleted:** {result.deleted['channels']} channels, {result.deleted['categories']} categories, {result.deleted['roles']} roles\n"
                    f"**Created:** {result.created['categories']} categories, {result.created['channels']} channels, {result.created['roles']} roles\n"
                    f"**Duration:** {result.duration_ms:.0f}ms"
                ),
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="❌ Server Overhaul Failed",
                description=(
                    f"**Phase:** {result.phase.title()}\n\n"
                    f"**Errors:** {len(result.errors)}\n"
                    f"**Duration:** {result.duration_ms:.0f}ms"
                ),
                color=discord.Color.red()
            )
        
        if result.errors:
            embed.add_field(
                name="Errors",
                value="\n".join(result.errors[:5]),  # Limit to first 5 errors
                inline=False
            )
        
        if result.warnings:
            embed.add_field(
                name="Warnings", 
                value="\n".join(result.warnings),
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="guardian_overhaul_cancel"
    )
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle cancel button."""
        await interaction.response.edit_message(
            content="❌ **Server overhaul cancelled.**",
            embed=None,
            view=None
        )
        self.stop()


class OverhaulCog(commands.Cog):
    """Production-grade server overhaul cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = OverhaulConfig()
    
    async def cog_load(self):
        """Register persistent views when cog loads."""
        self.bot.add_view(OverhaulConfirmationView())
        log.info("Overhaul system views registered")
    
    @app_commands.command(
        name="overhaul",
        description="Complete server overhaul with optimized architecture"
    )
    @admin_command()
    async def overhaul(self, interaction: discord.Interaction):
        """Execute server overhaul with confirmation."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        
        # Create confirmation embed
        embed = discord.Embed(
            title="⚠️ Server Overhaul Confirmation",
            description=(
                "**This will completely rebuild your server structure!**\n\n"
                "**What happens:**\n"
                "• Deletes all channels, categories, and eligible roles\n"
                "• Creates optimized role hierarchy\n"
                "• Creates organized channel structure\n"
                "• Posts verification and rules content\n\n"
                "**⚠️ This action is IRREVERSIBLE!**\n\n"
                "**Preserved:**\n"
                f"• Bot roles (if enabled)\n"
                f"• Managed roles (if enabled)\n"
                f"• Integration roles (if enabled)\n\n"
                "**Duration:** 2-5 minutes depending on server size\n\n"
                "Click **Confirm** to proceed or **Cancel** to abort."
            ),
            color=discord.Color.orange()
        )
        
        embed.add_field(
            name="🔧 Configuration",
            value=(
                f"• Dry Run: {'Yes' if self.config.dry_run else 'No'}\n"
                f"• Batch Size: {self.config.batch_size}\n"
                f"• Preserve Bot Roles: {'Yes' if self.config.preserve_bot_roles else 'No'}\n"
                f"• Preserve Managed Roles: {'Yes' if self.config.preserve_managed_roles else 'No'}"
            ),
            inline=False
        )
        
        embed.set_footer(text="This command replaces temporary overhaul with production-grade system")
        
        await interaction.response.send_message(embed=embed, view=OverhaulConfirmationView(), ephemeral=True)


# Setup function
async def setup(bot: commands.Bot):
    """Setup the overhaul cog."""
    await bot.add_cog(OverhaulCog(bot))
    log.info("Production-grade overhaul cog loaded")
