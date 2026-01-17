from __future__ import annotations

import discord
from discord import app_commands, ui
from discord.ext import commands
import logging
import re

from ..services.reaction_roles_store_new import ReactionRolesStore
from ..services.panel_store import PanelStore
from ..security.permissions import admin_command
from ..utils import info_embed, error_embed, success_embed

log = logging.getLogger("guardian.reaction_roles")

# Constants
# Default channel name for the member panel. Use settings.REACTION_ROLES_CHANNEL_NAME to override.
REACTION_ROLES_CHANNEL = "choose-your-games"


def _normalize_name(name: str) -> str:
    """Normalize channel/role names for fuzzy matching (strip emojis/punct/spacing)."""
    import re as _re
    n = name.lower().strip()
    # Drop leading emoji-like chars and punctuation
    n = _re.sub(r"^[^a-z0-9]+", "", n)
    n = _re.sub(r"[^a-z0-9]+", "", n)
    return n


def find_text_channel_fuzzy(guild: discord.Guild, target: str) -> discord.TextChannel | None:
    want = _normalize_name(target)
    # exact name
    ch = discord.utils.get(guild.text_channels, name=target)
    if ch:
        return ch
    # normalized match
    for c in guild.text_channels:
        if _normalize_name(c.name) == want:
            return c
    return None


class ReactionRolesManagerView(ui.View):
    """Admin management view following Discord.py best practices."""
    
    def __init__(self, cog: 'ReactionRolesCog', author: discord.User):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.cog = cog
        self.author = author
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the command author can interact."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "You cannot interact with this management panel.", 
                ephemeral=True
            )
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item) -> None:
        """Handle view errors gracefully."""
        log.error(f"ReactionRolesManagerView error: {error}", exc_info=True)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ An error occurred. Please try again.", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ An error occurred. Please try again.", 
                    ephemeral=True
                )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to manage your roles.", 
                ephemeral=True
                )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Discord API error. Please try again.", 
                ephemeral=True
                )
        except Exception as e:
            log.error(f"ReactionRolesManagerView error callback: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to handle error.", 
                ephemeral=True
                )

    async def on_timeout(self) -> None:
        """Handle view timeout by disabling all components."""
        for child in self.children:
            child.disabled = True
        
        if self.message:
            try:
                await self.message.edit(
                    content="🔐 Management panel timed out.", 
                    view=self,
                    embed=None
                )
            except Exception:
                pass
        self.stop()

    @ui.button(label="Add Roles", style=discord.ButtonStyle.primary, custom_id="rr:add", row=0)
    async def add_roles(self, interaction: discord.Interaction, button: ui.Button):
        """Add roles to reaction roles configuration."""
        try:
            await interaction.response.defer(ephemeral=True)
            log.info(f"Add roles opened: guild={interaction.guild.id}, user={interaction.user.id}")
            
            guild = interaction.guild
            
            # Get available roles with proper validation
            available_roles = []
            for role in guild.roles:
                if (not role.is_default() and 
                    not role.managed and 
                    role.position < guild.me.top_role.position):
                    
                    # Filter out protected roles
                    protected_names = [
                        "owner", "admin", "administrator", "moderator", "mod", 
                        "support", "helper", "verified", "member", 
                        "guardian bot", "guardian services"
                    ]
                    
                    if role.name.lower() not in protected_names:
                        available_roles.append(role)
            
            if not available_roles:
                await interaction.followup.send(
                    "❌ No available roles to add.", 
                    ephemeral=True
                )
                return

            # Create role select menu
            select = ui.RoleSelect(
                placeholder="Select roles to add...",
                max_values=min(25, len(available_roles))
            )
            
            # Add role options
            for role in sorted(available_roles, key=lambda r: r.position)[:25]:
                select.add_option(
                    label=role.name,
                    value=str(role.id),
                    description=f"Position: {role.position}"
                )

            # Create group selection
            group_select = ui.Select(
                placeholder="Assign to group:",
                options=[
                    discord.SelectOption(label="Games", value="games"),
                    discord.SelectOption(label="Interests", value="interests")
                ]
            )

            # Create confirm button
            confirm_btn = ui.Button(label="Confirm", style=discord.ButtonStyle.success)

            async def confirm_callback(confirm_interaction: discord.Interaction):
                try:
                    await confirm_interaction.response.defer(ephemeral=True)
                    
                    if not select.values:
                        await confirm_interaction.followup.send(
                            "❌ No roles selected.", 
                            ephemeral=True
                        )
                        return

                    group_key = group_select.values[0] if group_select.values else "games"
                    role_ids = [int(rid) for rid in select.values]
                    
                    # Validate roles
                    valid_roles = []
                    skipped = []
                    
                    for role_id in role_ids:
                        role = guild.get_role(role_id)
                        if not role:
                            skipped.append(f"Role {role_id} not found")
                            continue
                        
                        if role.is_default():
                            skipped.append(f"{role.name}: Cannot add @everyone")
                            continue
                        
                        if role.managed:
                            skipped.append(f"{role.name}: Cannot add managed/bot roles")
                            continue
                        
                        if role.position >= guild.me.top_role.position:
                            skipped.append(f"{role.name}: Role is above bot's highest role")
                            continue
                        
                        if role.name.lower() in protected_names:
                            skipped.append(f"{role.name}: Protected system role")
                            continue
                        
                        valid_roles.append(role)

                    # Save to database
                    if valid_roles:
                        result = await self.cog.store.add_roles(guild.id, [r.id for r in valid_roles], group_key)
                        
                        if result["errors"]:
                            skipped.extend(result["errors"])
                    
                    log.info(f"Roles added: added={len(valid_roles)}, skipped={len(skipped)}, group={group_key}")
                    
                    # Send result
                    embed = success_embed(f"✅ Added {len(valid_roles)} roles to {group_key}.")
                    if valid_roles:
                        role_names = [r.name for r in valid_roles[:10]]
                        embed.add_field(name="Added", value="\n".join(role_names), inline=False)
                    if skipped:
                        embed.add_field(name="Skipped", value="\n".join(skipped[:5]), inline=False)
                    
                    await confirm_interaction.followup.send(embed=embed, ephemeral=True)
                    
                except discord.Forbidden:
                    await confirm_interaction.followup.send(
                        "❌ I don't have permission to manage your roles.", 
                        ephemeral=True
                        )
                except discord.HTTPException:
                    await confirm_interaction.followup.send(
                        "❌ Discord API error. Please try again.", 
                        ephemeral=True
                        )
                except Exception as e:
                    log.error(f"Add roles confirm error: {e}", exc_info=True)
                    await confirm_interaction.followup.send(
                        "❌ Operation failed. Please try again.", 
                        ephemeral=True
                        )

            confirm_btn.callback = confirm_callback
            
            # Create view
            view = ui.View(timeout=120)
            view.add_item(select)
            view.add_item(group_select)
            view.add_item(confirm_btn)
            
            await interaction.followup.send(
                "Select roles and group to add:", 
                view=view, 
                ephemeral=True
                )
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to manage your roles.", 
                ephemeral=True
                )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Discord API error. Please try again.", 
                ephemeral=True
                )
        except Exception as e:
            log.error(f"Add roles error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to open role selection.", 
                ephemeral=True
                )

    @ui.button(label="Remove Roles", style=discord.ButtonStyle.danger, custom_id="rr:remove", row=0)
    async def remove_roles(self, interaction: discord.Interaction, button: ui.Button):
        """Remove roles from reaction roles configuration."""
        try:
            await interaction.response.defer(ephemeral=True)
            log.info(f"Remove roles opened: guild={interaction.guild.id}, user={interaction.user.id}")
            
            guild = interaction.guild
            all_roles = await self.cog.store.get_all_roles(guild.id)
            
            if not all_roles:
                await interaction.followup.send(
                    "❌ No roles configured to remove.", 
                    ephemeral=True
                )
                return

            # Create select menu with configured roles
            select = ui.Select(
                placeholder="Select roles to remove...",
                max_values=25
            )
            
            role_count = 0
            for group_key, role_ids in all_roles.items():
                for role_id in role_ids:
                    if role_count >= 25:
                        break
                    role = guild.get_role(role_id)
                    if role:
                        select.add_option(
                            label=f"{role.name} ({group_key})",
                            value=str(role_id),
                            description=f"Group: {group_key}"
                        )
                    role_count += 1
                if role_count >= 25:
                    break

            # Create confirm button
            confirm_btn = ui.Button(label="Confirm Remove", style=discord.ButtonStyle.danger)

            async def confirm_callback(confirm_interaction: discord.Interaction):
                try:
                    await confirm_interaction.response.defer(ephemeral=True)
                    
                    if not select.values:
                        await confirm_interaction.followup.send(
                            "❌ No roles selected.", 
                            ephemeral=True
                        )
                        return

                    role_ids = [int(rid) for rid in select.values]
                    result = await self.cog.store.remove_roles(guild.id, role_ids)
                    
                    log.info(f"Roles removed: removed={len(result['removed'])}, errors={len(result['errors'])}")
                    
                    embed = success_embed(f"✅ Removed {len(result['removed'])} roles from reaction roles.")
                    if result["errors"]:
                        embed.add_field(name="Errors", value="\n".join(result["errors"]), inline=False)
                    
                    await confirm_interaction.followup.send(embed=embed, ephemeral=True)
                    
                except discord.Forbidden:
                    await confirm_interaction.followup.send(
                        "❌ I don't have permission to manage your roles.", 
                        ephemeral=True
                        )
                except discord.HTTPException:
                    await confirm_interaction.followup.send(
                        "❌ Discord API error. Please try again.", 
                        ephemeral=True
                        )
                except Exception as e:
                    log.error(f"Remove roles confirm error: {e}", exc_info=True)
                    await confirm_interaction.followup.send(
                        "❌ Operation failed. Please try again.", 
                        ephemeral=True
                        )

            confirm_btn.callback = confirm_callback
            
            # Create view
            view = ui.View(timeout=120)
            view.add_item(select)
            view.add_item(confirm_btn)
            
            await interaction.followup.send(
                "Select roles to remove:", 
                view=view, 
                ephemeral=True
                )
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to manage your roles.", 
                ephemeral=True
                )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Discord API error. Please try again.", 
                ephemeral=True
                )
        except Exception as e:
            log.error(f"Remove roles error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to open role removal.", 
                ephemeral=True
                )

    @ui.button(label="Publish Panel", style=discord.ButtonStyle.success, custom_id="rr:publish", row=1)
    async def publish_panel(self, interaction: discord.Interaction, button: ui.Button):
        """Publish the member panel."""
        try:
            await interaction.response.defer(ephemeral=True)
            log.info(f"Publish panel called: guild={interaction.guild.id}, user={interaction.user.id}")
            await self.cog.publish_member_panel(interaction)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to manage your roles.", 
                ephemeral=True
                )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Discord API error. Please try again.", 
                ephemeral=True
                )
        except Exception as e:
            log.error(f"Publish panel error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to publish panel.", 
                ephemeral=True
                )

    @ui.button(label="Close", style=discord.ButtonStyle.secondary, custom_id="rr:close", row=1)
    async def close(self, interaction: discord.Interaction, button: ui.Button):
        """Close management UI."""
        try:
            await interaction.response.edit_message(
                content="🔐 Management panel closed.", 
                view=None, 
                embed=None
                )
            self.stop()
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to manage your roles.", 
                ephemeral=True
                )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Discord API error. Please try again.", 
                ephemeral=True
                )
        except Exception as e:
            log.error(f"Close panel error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to close panel.", 
                ephemeral=True
                )


class ReactionRolesMemberView(ui.View):
    """Member panel for role selection with proper persistence."""
    
    def __init__(self, cog: 'ReactionRolesCog', guild_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure interaction is from the correct guild."""
        return interaction.guild_id == self.guild_id

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item) -> None:
        """Handle member view errors gracefully."""
        log.error(f"ReactionRolesMemberView error: {error}", exc_info=True)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ Failed to update roles. Please try again.", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Failed to update roles. Please try again.", 
                    ephemeral=True
                )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to manage your roles.", 
                ephemeral=True
                )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Discord API error. Please try again.", 
                ephemeral=True
                )
        except Exception as e:
            log.error(f"Member role selection error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to update roles. Please try again.", 
                ephemeral=True
                )

    def build_select_menus(self, guild: discord.Guild, all_roles: dict[str, list[int]]) -> bool:
        """Build select menus for role groups. Returns False if any group exceeds 25 roles."""
        self.clear_items()
        
        for group_key, role_ids in all_roles.items():
            if not role_ids:
                continue
            
            # Check group size limit
            if len(role_ids) > 25:
                return False  # Block publish if group exceeds 25 roles
            
            select = ui.Select(
                placeholder=f"Select {group_key.title()} roles...",
                custom_id=f"guardian:rr:member:{group_key}",
                max_values=len(role_ids)
            )
            
            for role_id in role_ids:
                role = guild.get_role(role_id)
                if role:
                    select.add_option(
                        label=role.name,
                        value=str(role_id),
                        emoji=""
                    )
            
            async def select_callback(interaction: discord.Interaction):
                """Handle role selection with proper error handling."""
                try:
                    # Extract group key from custom_id
                    custom_id = interaction.data.get('custom_id', '')
                    match = re.match(r'guardian:rr:member:(.+)', custom_id)
                    if not match:
                        await interaction.response.send_message(
                            "❌ Invalid interaction.", 
                            ephemeral=True
                        )
                        return
                    
                    group_key = match.group(1)
                    await interaction.response.defer(ephemeral=True)
                    
                    if not interaction.data.get('values'):
                        return

                    member = interaction.user
                    selected_role_ids = [int(rid) for rid in interaction.data['values']]
                    
                    # Get current roles in this group
                    current_role_ids = {role.id for role in member.roles}
                    group_role_ids = set(role_ids)
                    
                    # Determine roles to add and remove
                    roles_to_add = [rid for rid in selected_role_ids if rid not in current_role_ids]
                    roles_to_remove = [rid for rid in group_role_ids if rid in current_role_ids and rid not in selected_role_ids]
                    
                    # Apply role changes
                    if roles_to_remove:
                        roles_to_remove_objs = [guild.get_role(rid) for rid in roles_to_remove]
                        roles_to_remove_objs = [r for r in roles_to_remove_objs if r]
                        if roles_to_remove_objs:
                            await member.remove_roles(*roles_to_remove_objs, reason="Reaction role update")
                    
                    if roles_to_add:
                        roles_to_add_objs = [guild.get_role(rid) for rid in roles_to_add]
                        roles_to_add_objs = [r for r in roles_to_add_objs if r]
                        if roles_to_add_objs:
                            await member.add_roles(*roles_to_add_objs, reason="Reaction role update")
                    
                    message = f"✅ Updated your {group_key.title()} roles."
                    if roles_to_add:
                        message += f" Added {len(roles_to_add)}."
                    if roles_to_remove:
                        message += f" Removed {len(roles_to_remove)}."
                    
                    await interaction.followup.send(message, ephemeral=True)
                    
                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ I don't have permission to manage your roles.", 
                        ephemeral=True
                    )
                except discord.HTTPException:
                    await interaction.followup.send(
                        "❌ Discord API error. Please try again.", 
                        ephemeral=True
                    )
                except Exception as e:
                    log.error(f"Member role selection error: {e}", exc_info=True)
                    await interaction.followup.send(
                        "❌ Failed to update roles. Please try again.", 
                        ephemeral=True
                    )
            
            select.callback = select_callback
            self.add_item(select)
        
        return True


class ReactionRolesCog(commands.Cog):
    """Reaction roles system following Discord.py best practices."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = None
        self.panel_store = None

    async def cog_load(self):
        """Initialize stores and register persistent views."""
        # NOTE: This cog must never fail during load.
        # Any exception here prevents the cog (and its slash commands) from registering,
        # which cascades into startup self-check failures.
        settings = self.bot.settings
        self.store = ReactionRolesStore(settings.sqlite_path)
        # Use the bot-wide PanelStore to avoid duplicate table init / cache divergence.
        self.panel_store = getattr(self.bot, "panel_store", PanelStore(settings.sqlite_path))

        await self.store.init()

        # Do NOT register an empty persistent view. Persistent views should be
        # registered with an actual message_id after publishing, or restored on_ready.
        log.info("ReactionRolesCog loaded")

    @commands.Cog.listener()
    async def on_ready(self):
        """Restore persistent member panels after the bot is ready."""
        # Only run once per process.
        if getattr(self, "_rr_ready_ran", False):
            return
        self._rr_ready_ran = True

        if not getattr(self.bot.settings, "reaction_roles_enabled", True):
            log.info("Reaction roles disabled by settings; skipping restoration")
            return

        # Best-effort restoration per guild.
        for guild in list(getattr(self.bot, "guilds", [])):
            try:
                await self._restore_member_panel_for_guild(guild)
            except Exception:
                log.exception("Failed to restore reaction roles panel for guild %s", getattr(guild, "id", None))

    async def _restore_member_panel_for_guild(self, guild: discord.Guild) -> None:
        panel_key = getattr(self.bot.settings, "reaction_roles_panel_key", "reaction_roles_panel")
        rec = await self.panel_store.get(guild.id, panel_key)
        if not rec:
            return

        channel = guild.get_channel(rec["channel_id"]) or self.bot.get_channel(rec["channel_id"])
        if channel is None:
            return

        try:
            msg = await channel.fetch_message(rec["message_id"])
        except Exception:
            return

        all_roles = await self.store.get_all_roles(guild.id)
        if not all_roles:
            return

        view = ReactionRolesMemberView(self, guild.id)
        ok = view.build_select_menus(guild, all_roles)
        if not ok:
            return

        # Register the view for component callbacks to work after restart.
        try:
            self.bot.add_view(view, message_id=msg.id)
            log.info("Restored reaction roles member panel view for guild=%s message=%s", guild.id, msg.id)
        except Exception:
            # Never crash startup.
            log.exception("Failed to register restored view for guild=%s", guild.id)

    @app_commands.command(
        name="reactionroles",
        description="Reaction roles management commands"
    )
    @app_commands.describe(
        action="Choose an action: manage, publish, list, clear_user"
    )
    @admin_command()
    async def reactionroles(
        self, 
        interaction: discord.Interaction, 
        action: str
    ):
        """Main reaction roles command dispatcher."""
        try:
            await interaction.response.defer(ephemeral=True)
            log.info(f"Command called: reactionroles {action}, guild={interaction.guild.id}, user={interaction.user.id}")
            
            if action == "manage":
                await self.open_manager(interaction)
            elif action == "publish":
                await self.publish_member_panel(interaction)
            elif action == "list":
                await self.list_roles(interaction)
            elif action == "clear_user":
                await self.clear_user_roles(interaction)
            else:
                await interaction.followup.send(
                    f"❌ Unknown action: {action}. Available: manage, publish, list, clear_user",
                    ephemeral=True
                )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ You need 'Manage Roles' permission to use this command.", 
                ephemeral=True
                )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Discord API error. Please try again.", 
                ephemeral=True
                )
        except Exception as e:
            log.error(f"Reaction roles command error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Command failed. Please try again.", 
                ephemeral=True
                )

    async def open_manager(self, interaction: discord.Interaction):
        """Open admin manager UI."""
        try:
            if not interaction.guild:
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", 
                    ephemeral=True
                )
                return

            # Check permissions
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.followup.send(
                    "❌ You need 'Manage Roles' permission to use this command.", 
                    ephemeral=True
                )
                return

            # Get status information
            configured_count = await self.store.get_configured_count(interaction.guild.id)
            
            # Check panel status
            panel_status = "Missing"
            last_publish = "Never"
            try:
                panel_key = getattr(self.bot.settings, "reaction_roles_panel_key", "reaction_roles_panel")
                rec = await self.panel_store.get(interaction.guild.id, panel_key)
                if rec and rec.get("message_id"):
                    channel = interaction.guild.get_channel(rec["channel_id"]) or self.bot.get_channel(rec["channel_id"])
                    if channel:
                        try:
                            await channel.fetch_message(rec["message_id"])
                            panel_status = "Deployed"
                            # PanelStore stores last_deployed_at as ISO in db; treat presence as "published".
                            last_publish = "Recorded"
                        except Exception:
                            panel_status = "Missing"
            except Exception:
                # Never block the manager UI on status lookup.
                pass

            # Create embed
            embed = info_embed("🔧 Reaction Roles Management")
            embed.description = "Use the buttons below to manage reaction roles."
            
            embed.add_field(name="Configured Roles", value=str(configured_count))
            embed.add_field(name="Panel Status", value=panel_status)
            embed.add_field(name="Last Publish", value=last_publish)

            # Create and send view
            view = ReactionRolesManagerView(self, interaction.user)
            message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            view.message = message
            
            log.info(f"Manager view sent: guild={interaction.guild.id}, user={interaction.user.id}")
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ You need 'Manage Roles' permission to use this command.", 
                ephemeral=True
                )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Discord API error. Please try again.", 
                ephemeral=True
                )
        except Exception as e:
            log.error(f"Open manager error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to open manager.", 
                ephemeral=True
                )

    async def publish_member_panel(self, interaction: discord.Interaction):
        """Deploy or update the member panel."""
        try:
            if not interaction.guild:
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", 
                    ephemeral=True
                )
                return

            guild = interaction.guild
            
            # Check if any roles are configured
            all_roles = await self.store.get_all_roles(guild.id)
            if not all_roles:
                await interaction.followup.send(
                    "❌ No roles configured yet.", 
                    ephemeral=True
                )
                return

            # Check group size limits
            for group_key, role_ids in all_roles.items():
                if len(role_ids) > 25:
                    await interaction.followup.send(
                        f"❌ Group '{group_key}' exceeds 25 roles. Split into another group or reduce.",
                        ephemeral=True
                    )
                    return

            # Find or create the configured channel for the member panel.
            target_name = getattr(self.bot.settings, "reaction_roles_channel_name", REACTION_ROLES_CHANNEL)
            channel = find_text_channel_fuzzy(guild, target_name)
            if not channel:
                try:
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(
                            read_messages=True,
                            send_messages=False,
                            add_reactions=False
                        )
                    }
                    channel = await guild.create_text_channel(
                        target_name,
                        overwrites=overwrites,
                        reason="Reaction roles channel"
                    )
                except discord.Forbidden:
                    await interaction.followup.send(
                        f"❌ I don't have permission to create channels. Please create a #{target_name} channel manually.",
                        ephemeral=True
                    )
                    return

            # Create member panel view
            view = ReactionRolesMemberView(self, guild.id)
            if not view.build_select_menus(guild, all_roles):
                await interaction.followup.send(
                    "❌ Failed to build role menus. Check group size limits.",
                    ephemeral=True
                )
                return

            # Create embed
            embed = discord.Embed(
                title="🎭 Choose Your Roles",
                description="Select your roles from the menus below.",
                color=discord.Color.blue()
            )

            # Check if panel already exists
            panel_key = getattr(self.bot.settings, "reaction_roles_panel_key", "reaction_roles_panel")
            rec = await self.panel_store.get(guild.id, panel_key)
            if rec and rec.get("message_id"):
                try:
                    # Try to edit existing message
                    message = await channel.fetch_message(rec["message_id"])
                    await message.edit(embed=embed, view=view)
                    await interaction.followup.send(
                        f"✅ Updated reaction roles panel in {channel.mention}",
                        ephemeral=True
                    )
                    # Ensure callbacks persist across restarts
                    try:
                        self.bot.add_view(view, message_id=message.id)
                    except Exception:
                        pass
                    await self.panel_store.upsert(guild.id, panel_key, channel.id, message.id)
                    log.info(f"Panel updated: guild={guild.id}, message_id={message.id}")
                except discord.NotFound:
                    # Message not found, create new one
                    message = await channel.send(embed=embed, view=view)
                    try:
                        self.bot.add_view(view, message_id=message.id)
                    except Exception:
                        pass
                    await self.panel_store.upsert(guild.id, panel_key, channel.id, message.id)
                    await interaction.followup.send(
                        f"✅ Created new reaction roles panel in {channel.mention}",
                        ephemeral=True
                    )
                    log.info(f"Panel created: guild={guild.id}, message_id={message.id}")
            else:
                # Create new panel
                message = await channel.send(embed=embed, view=view)
                try:
                    self.bot.add_view(view, message_id=message.id)
                except Exception:
                    pass
                await self.panel_store.upsert(guild.id, panel_key, channel.id, message.id)
                await interaction.followup.send(
                    f"✅ Created reaction roles panel in {channel.mention}",
                    ephemeral=True
                )
                log.info(f"Panel created: guild={guild.id}, message_id={message.id}")

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to manage your roles.", 
                ephemeral=True
                )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Discord API error. Please try again.", 
                ephemeral=True
                )
        except Exception as e:
            log.error(f"Publish panel error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to publish panel.", 
                ephemeral=True
                )

    async def list_roles(self, interaction: discord.Interaction):
        """List all configured roles."""
        try:
            if not interaction.guild:
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", 
                    ephemeral=True
                )
                return

            all_roles = await self.store.get_all_roles(interaction.guild.id)
            if not all_roles:
                await interaction.followup.send(
                    "❌ No roles configured yet.", 
                    ephemeral=True
                )
                return

            embed = info_embed("📋 Configured Reaction Roles")
            
            for group_key, role_ids in sorted(all_roles.items()):
                if not role_ids:
                    continue
                
                guild = interaction.guild
                role_names = []
                for role_id in role_ids:
                    role = guild.get_role(role_id)
                    if role:
                        role_names.append(role.mention)
                
                if role_names:
                    embed.add_field(
                        name=f"{group_key.title()} ({len(role_names)} roles)",
                        value=" ".join(role_names[:25]),  # Limit display
                        inline=False
                    )

            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ You need 'Manage Roles' permission to use this command.", 
                ephemeral=True
                )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Discord API error. Please try again.", 
                ephemeral=True
                )
        except Exception as e:
            log.error(f"List roles error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to list roles.", 
                ephemeral=True
                )

    async def clear_user_roles(self, interaction: discord.Interaction):
        """Clear reaction roles from a member."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not interaction.guild:
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", 
                    ephemeral=True
                )
                return

            # Clear from command user
            member = interaction.user
            all_roles = await self.store.get_all_roles(interaction.guild.id)
            
            if not all_roles:
                await interaction.followup.send(
                    "❌ No reaction roles configured.", 
                    ephemeral=True
                )
                return

            # Get all configured role IDs
            configured_role_ids = set()
            for role_ids in all_roles.values():
                configured_role_ids.update(role_ids)
            
            roles_to_remove = [role for role in member.roles if role.id in configured_role_ids]
            
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Cleared reaction roles via command")
                await interaction.followup.send(
                    f"✅ Removed {len(roles_to_remove)} reaction roles from you.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ You don't have any reaction roles to remove.",
                    ephemeral=True
                )
                
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to manage your roles.", 
                ephemeral=True
                )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Discord API error. Please try again.", 
                ephemeral=True
                )
        except Exception as e:
            log.error(f"Clear user roles error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to clear roles.", 
                ephemeral=True
                )

    async def cog_unload(self):
        """Clean up when cog is unloaded."""
        log.info("ReactionRolesCog unloaded")


async def setup(bot: commands.Bot):
    """Setup the reaction roles cog."""
    await bot.add_cog(ReactionRolesCog(bot))
    log.info("Reaction roles cog loaded")
