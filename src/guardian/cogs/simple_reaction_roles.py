from __future__ import annotations

import discord
from discord import app_commands, ui
from discord.ext import commands
import logging
import time

from ..services.simple_reaction_roles_store import SimpleReactionRolesStore
from ..services.panel_store import PanelStore
from ..security.permissions import admin_command
from ..utils import info_embed, error_embed, success_embed

log = logging.getLogger("guardian.reaction_roles")

# Constants
REACTION_ROLES_CHANNEL = "reaction-roles"


class ManagerView(ui.View):
    """Simple admin manager UI with proper error handling."""
    
    def __init__(self, cog: 'SimpleReactionRolesCog'):
        super().__init__(timeout=300)  # 5 minutes
        self.cog = cog
        self.message = None
        self.user = None  # Track the user who opened this view

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact with the view."""
        if self.user and interaction.user.id != self.user.id:
            await interaction.response.send_message("You cannot interact with this management panel.", ephemeral=True)
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item) -> None:
        """Handle view errors gracefully."""
        log.error(f"ManagerView error: {error}", exc_info=True)
        try:
            if interaction.response.is_done():
                await interaction.followup.send("❌ An error occurred. Please try again.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ An error occurred. Please try again.", ephemeral=True)
        except:
            pass  # If we can't even send an error message, just log it

    async def on_timeout(self) -> None:
        """Handle view timeout by disabling all components."""
        # Disable all components
        for child in self.children:
            child.disabled = True
        
        # Update the message if it exists
        if self.message:
            try:
                await self.message.edit(
                    content="🔐 Management panel timed out.", 
                    view=self,  # Show disabled buttons
                    embed=None
                )
            except:
                pass
        self.stop()

    @ui.button(label="Add Roles", style=discord.ButtonStyle.primary, custom_id="rr_add", row=0)
    async def add_roles(self, interaction: discord.Interaction, button: ui.Button):
        """Add roles to reaction roles."""
        try:
            await interaction.response.defer(ephemeral=True)
            log.info(f"Add roles opened: guild={interaction.guild.id}, user={interaction.user.id}")
            
            guild = interaction.guild
            available_roles = [r for r in guild.roles if not r.is_default() and not r.managed and r.position < guild.me.top_role.position]
            
            # Filter out protected roles
            protected_names = ["owner", "admin", "administrator", "moderator", "mod", "support", "helper", "verified", "member", "guardian bot", "guardian services"]
            available_roles = [r for r in available_roles if r.name.lower() not in protected_names]
            
            if not available_roles:
                await interaction.followup.send("❌ No available roles to add.", ephemeral=True)
                return

            # Create role select
            select = ui.RoleSelect(
                placeholder="Select roles to add...",
                max_values=min(25, len(available_roles))
            )
            
            for role in sorted(available_roles, key=lambda r: r.position)[:25]:
                select.add_option(
                    label=role.name,
                    value=str(role.id),
                    description=f"Position: {role.position}"
                )

            # Create group select
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
                        await confirm_interaction.followup.send("❌ No roles selected.", ephemeral=True)
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
                        valid_role_ids = [r.id for r in valid_roles]
                        errors = await self.cog.store.add_many(guild.id, valid_role_ids, group_key)
                        
                        if errors:
                            skipped.extend(errors)
                    
                    log.info(f"Roles added: added={len(valid_roles)}, skipped={len(skipped)}, group={group_key}")
                    
                    # Send result
                    embed = success_embed(f"✅ Added {len(valid_roles)} roles to {group_key}.")
                    if valid_roles:
                        embed.add_field(name="Added", value="\n".join([r.name for r in valid_roles[:10]]), inline=False)
                    if skipped:
                        embed.add_field(name="Skipped", value="\n".join(skipped[:5]), inline=False)
                    
                    await confirm_interaction.followup.send(embed=embed, ephemeral=True)
                    
                except Exception as e:
                    log.error(f"Add roles confirm error: {e}")
                    await confirm_interaction.followup.send("❌ Operation failed. Please try again.", ephemeral=True)

            confirm_btn.callback = confirm_callback
            
            # Create view
            view = ui.View(timeout=120)
            view.add_item(select)
            view.add_item(group_select)
            view.add_item(confirm_btn)
            
            await interaction.followup.send("Select roles and group to add:", view=view, ephemeral=True)
            
        except Exception as e:
            log.error(f"Add roles error: {e}")
            await interaction.followup.send("❌ Failed to open role selection.", ephemeral=True)

    @ui.button(label="Remove Roles", style=discord.ButtonStyle.danger, custom_id="rr_remove", row=0)
    async def remove_roles(self, interaction: discord.Interaction, button: ui.Button):
        """Remove roles from reaction roles."""
        try:
            await interaction.response.defer(ephemeral=True)
            log.info(f"Remove roles opened: guild={interaction.guild.id}, user={interaction.user.id}")
            
            guild = interaction.guild
            all_roles = await self.cog.store.list_all(guild.id)
            
            if not all_roles:
                await interaction.followup.send("❌ No roles configured to remove.", ephemeral=True)
                return

            # Create select with all configured roles
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
                        await confirm_interaction.followup.send("❌ No roles selected.", ephemeral=True)
                        return

                    role_ids = [int(rid) for rid in select.values]
                    errors = await self.cog.store.remove_many(guild.id, role_ids)
                    
                    removed = len(role_ids) - len(errors)
                    log.info(f"Roles removed: removed={removed}, errors={len(errors)}")
                    
                    embed = success_embed(f"✅ Removed {removed} roles from reaction roles.")
                    if errors:
                        embed.add_field(name="Errors", value="\n".join(errors), inline=False)
                    
                    await confirm_interaction.followup.send(embed=embed, ephemeral=True)
                    
                except Exception as e:
                    log.error(f"Remove roles confirm error: {e}")
                    await confirm_interaction.followup.send("❌ Operation failed. Please try again.", ephemeral=True)

            confirm_btn.callback = confirm_callback
            
            # Create view
            view = ui.View(timeout=120)
            view.add_item(select)
            view.add_item(confirm_btn)
            
            await interaction.followup.send("Select roles to remove:", view=view, ephemeral=True)
            
        except Exception as e:
            log.error(f"Remove roles error: {e}")
            await interaction.followup.send("❌ Failed to open role removal.", ephemeral=True)

    @ui.button(label="Publish Panel", style=discord.ButtonStyle.success, custom_id="rr_publish", row=1)
    async def publish_panel(self, interaction: discord.Interaction, button: ui.Button):
        """Publish the member panel."""
        try:
            await interaction.response.defer(ephemeral=True)
            log.info(f"Publish panel called: guild={interaction.guild.id}, user={interaction.user.id}")
            await self.cog.publish_panel(interaction)
        except Exception as e:
            log.error(f"Publish panel error: {e}")
            await interaction.followup.send("❌ Failed to publish panel.", ephemeral=True)

    @ui.button(label="Close", style=discord.ButtonStyle.secondary, custom_id="rr_close", row=1)
    async def close(self, interaction: discord.Interaction, button: ui.Button):
        """Close management UI."""
        try:
            await interaction.response.edit_message(content="🔐 Management panel closed.", view=None, embed=None)
            self.stop()
        except Exception as e:
            log.error(f"Close panel error: {e}")


class MemberView(ui.View):
    """Simple member panel for role selection with proper persistence."""
    
    def __init__(self, cog: 'SimpleReactionRolesCog', guild_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure interaction is from the correct guild."""
        if interaction.guild_id != self.guild_id:
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item) -> None:
        """Handle member view errors gracefully."""
        log.error(f"MemberView error: {error}", exc_info=True)
        try:
            if interaction.response.is_done():
                await interaction.followup.send("❌ Failed to update roles. Please try again.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to update roles. Please try again.", ephemeral=True)
        except:
            pass

    async def refresh_view(self):
        """Refresh view with current roles using persistent custom IDs."""
        self.clear_items()
        
        guild = self.cog.bot.get_guild(self.guild_id)
        if not guild:
            return

        all_roles = await self.cog.store.list_all(self.guild_id)
        
        if not all_roles:
            return

        # Create select menus for each group with proper custom IDs
        for group_key, role_ids in all_roles.items():
            if not role_ids:
                continue
            
            # Check group size limit
            if len(role_ids) > 25:
                return  # Block publish if group exceeds 25 roles
            
            select = ui.Select(
                placeholder=f"Select {group_key.title()} roles...",
                custom_id=f"guardian:rr:member:{group_key}",  # Proper persistent custom ID
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
                    if ':' in custom_id:
                        group_key = custom_id.split(':')[-1]
                    else:
                        await interaction.response.send_message("❌ Invalid interaction.", ephemeral=True)
                        return
                    
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
                    await interaction.followup.send("❌ I don't have permission to manage your roles.", ephemeral=True)
                except Exception as e:
                    log.error(f"Member role selection error: {e}", exc_info=True)
                    await interaction.followup.send("❌ Failed to update roles. Please try again.", ephemeral=True)
            
            select.callback = select_callback
            self.add_item(select)


class SimpleReactionRolesCog(commands.Cog):
    """Simple, fast, reliable reaction roles system."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = None
        self.panel_store = None

    async def cog_load(self):
        """Initialize stores and register persistent views."""
        settings = self.bot.settings
        self.store = SimpleReactionRolesStore(settings.sqlite_path)
        self.panel_store = PanelStore(settings.sqlite_path)
        
        await self.store.init()
        
        log.info("SimpleReactionRolesCog loaded successfully")

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
                await self.publish_panel(interaction)
            elif action == "list":
                await self.list_roles(interaction)
            elif action == "clear_user":
                await self.clear_user_roles(interaction)
            else:
                await interaction.followup.send(
                    f"❌ Unknown action: {action}. Available: manage, publish, list, clear_user",
                    ephemeral=True
                )
        except Exception as e:
            log.error(f"Reaction roles command error: {e}")
            await interaction.followup.send("❌ Command failed. Please try again.", ephemeral=True)

    async def open_manager(self, interaction: discord.Interaction):
        """Open admin manager UI with proper user tracking."""
        try:
            if not interaction.guild:
                await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
                return

            # Check permissions
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.followup.send("❌ You need 'Manage Roles' permission to use this command.", ephemeral=True)
                return

            # Get status
            configured_count = await self.store.get_configured_count(interaction.guild.id)
            
            # Check panel status
            panel_status = "Missing"
            last_publish = "Never"
            try:
                panel = await self.panel_store.get_by_key("reaction_roles_panel")
                if panel and panel.message_id:
                    channel = self.bot.get_channel(panel.channel_id)
                    if channel:
                        try:
                            await channel.fetch_message(panel.message_id)
                            panel_status = "Deployed"
                            last_publish = f"<t:{int(panel.updated_at.timestamp())}>"
                        except:
                            panel_status = "Missing"
            except:
                pass

            # Create embed
            embed = info_embed("🔧 Reaction Roles Management")
            embed.description = "Use the buttons below to manage reaction roles."
            
            embed.add_field(name="Configured Roles", value=str(configured_count))
            embed.add_field(name="Panel Status", value=panel_status)
            embed.add_field(name="Last Publish", value=last_publish)

            # Create and send view
            view = ManagerView(self)
            view.user = interaction.user  # Track the user who opened this view
            message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            view.message = message
            
            log.info(f"Manager view sent: guild={interaction.guild.id}, user={interaction.user.id}")
            
        except Exception as e:
            log.error(f"Open manager error: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to open manager.", ephemeral=True)

    async def publish_panel(self, interaction: discord.Interaction):
        """Deploy or update the member panel."""
        try:
            if not interaction.guild:
                await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
                return

            guild = interaction.guild
            
            # Check if any roles are configured
            all_roles = await self.store.list_all(guild.id)
            if not all_roles:
                await interaction.followup.send("❌ No roles configured yet.", ephemeral=True)
                return

            # Check group size limits
            for group_key, role_ids in all_roles.items():
                if len(role_ids) > 25:
                    await interaction.followup.send(
                        f"❌ Group '{group_key}' exceeds 25 roles. Split into another group or reduce.",
                        ephemeral=True
                    )
                    return

            # Find or create reaction-roles channel
            channel = discord.utils.get(guild.text_channels, name=REACTION_ROLES_CHANNEL)
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
                        REACTION_ROLES_CHANNEL,
                        overwrites=overwrites,
                        reason="Reaction roles channel"
                    )
                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ I don't have permission to create channels. Please create a #reaction-roles channel manually.",
                        ephemeral=True
                    )
                    return

            # Create member panel view with proper guild_id
            view = MemberView(self, guild.id)
            await view.refresh_view()

            # Create embed
            embed = discord.Embed(
                title="🎭 Choose Your Roles",
                description="Select your roles from the menus below.",
                color=discord.Color.blue()
            )

            # Check if panel already exists
            panel = await self.panel_store.get_by_key("reaction_roles_panel")
            if panel and panel.message_id:
                try:
                    # Try to edit existing message
                    message = await channel.fetch_message(panel.message_id)
                    await message.edit(embed=embed, view=view)
                    await interaction.followup.send(
                        f"✅ Updated reaction roles panel in {channel.mention}",
                        ephemeral=True
                    )
                    log.info(f"Panel updated: guild={guild.id}, message_id={panel.message_id}")
                except discord.NotFound:
                    # Message not found, create new one
                    message = await channel.send(embed=embed, view=view)
                    await self.panel_store.upsert(
                        "reaction_roles_panel",
                        guild.id,
                        channel.id,
                        message.id
                    )
                    await interaction.followup.send(
                        f"✅ Created new reaction roles panel in {channel.mention}",
                        ephemeral=True
                    )
                    log.info(f"Panel created: guild={guild.id}, message_id={message.id}")
            else:
                # Create new panel
                message = await channel.send(embed=embed, view=view)
                await self.panel_store.upsert(
                    "reaction_roles_panel",
                    guild.id,
                    channel.id,
                    message.id
                )
                await interaction.followup.send(
                    f"✅ Created reaction roles panel in {channel.mention}",
                    ephemeral=True
                )
                log.info(f"Panel created: guild={guild.id}, message_id={message.id}")

        except Exception as e:
            log.error(f"Publish panel error: {e}")
            await interaction.followup.send("❌ Failed to publish panel.", ephemeral=True)

    async def list_roles(self, interaction: discord.Interaction):
        """List all configured roles."""
        try:
            if not interaction.guild:
                await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
                return

            all_roles = await self.store.list_all(interaction.guild.id)
            if not all_roles:
                await interaction.followup.send("❌ No roles configured yet.", ephemeral=True)
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
            
        except Exception as e:
            log.error(f"List roles error: {e}")
            await interaction.followup.send("❌ Failed to list roles.", ephemeral=True)

    async def clear_user_roles(self, interaction: discord.Interaction):
        """Clear reaction roles from a member."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not interaction.guild:
                await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
                return

            # For now, clear from command user
            member = interaction.user
            all_roles = await self.store.list_all(interaction.guild.id)
            
            if not all_roles:
                await interaction.followup.send("❌ No reaction roles configured.", ephemeral=True)
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
                
        except Exception as e:
            log.error(f"Clear user roles error: {e}")
            await interaction.followup.send("❌ Failed to clear roles.", ephemeral=True)

    async def cog_unload(self):
        """Clean up when cog is unloaded."""
        log.info("SimpleReactionRolesCog unloaded")


async def setup(bot: commands.Bot):
    """Setup the reaction roles cog."""
    await bot.add_cog(SimpleReactionRolesCog(bot))
    log.info("Simple reaction roles cog loaded")
