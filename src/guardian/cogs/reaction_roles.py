from __future__ import annotations

import logging
import asyncio
import uuid
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Select, button, select

from guardian.services.reaction_role_store import ReactionRoleStore, ReactionRolePanel
from guardian.services.server_config_store import ServerConfigStore
from guardian.services.api_wrapper import safe_create_channel, safe_send_message, safe_edit_message
from guardian.security.permissions import admin_command
from guardian.constants import COLORS
from guardian.permissions import require_admin, require_verified, is_verified

log = logging.getLogger("guardian.reaction_roles")


class ReactionRoleSetupView(View):
    """View for reaction role setup process."""
    
    def __init__(self, cog: 'ReactionRoleCog', interaction: discord.Interaction):
        super().__init__(timeout=1800)  # 30 minutes timeout for setup
        self.cog = cog
        self.interaction = interaction
        self.step = 1
        self.setup_data = {
            'title': None,
            'description': None,
            'mode': 'toggle',
            'private_logs': True,
            'roles': [],
            'role_emojis': {}
        }
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the command author can interact."""
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message(
                "❌ You cannot interact with this setup menu.",
                ephemeral=True
            )
            return False
        return True
    
    @button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="rr_setup_cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        """Cancel the setup process."""
        await interaction.response.edit_message(
            content="❌ **Reaction role setup cancelled.**",
            embed=None,
            view=None
        )
        self.stop()
    
    @button(label="Next Step", style=discord.ButtonStyle.primary, custom_id="rr_setup_next")
    async def next_button(self, interaction: discord.Interaction, button: Button):
        """Proceed to next step."""
        if self.step == 1:
            await self._step1_title(interaction)
        elif self.step == 2:
            await self._step2_description(interaction)
        elif self.step == 3:
            await self._step3_mode(interaction)
        elif self.step == 4:
            await self._step4_roles(interaction)
        elif self.step == 5:
            await self._step5_emojis(interaction)
        elif self.step == 6:
            await self._step6_preview(interaction)
    
    async def _step1_title(self, interaction: discord.Interaction):
        """Step 1: Set title."""
        self.step = 2
        
        embed = discord.Embed(
            title="📝 Step 1: Panel Title",
            description="Please provide a title for the reaction role panel.",
            color=COLORS["primary"]
        )
        embed.add_field(
            name="Example",
            value="**Server Roles**\n*Click the buttons below to get your roles!*",
            inline=False
        )
        embed.set_footer(text="Type your title in chat, or click 'Next Step' to use default.")
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Wait for title response
        try:
            def check(msg):
                return msg.author.id == self.interaction.user.id and msg.channel.id == self.interaction.channel.id
            
            msg = await self.cog.bot.wait_for('message', timeout=300.0, check=check)
            self.setup_data['title'] = msg.content[:256]  # Limit length
            await msg.delete()
            
            await self.interaction.edit_original_response(
                content=f"✅ **Title set to:** {self.setup_data['title']}",
                embed=None,
                view=self
            )
        except asyncio.TimeoutError:
            await self.interaction.edit_original_response(
                content="❌ **Setup timed out.**",
                embed=None,
                view=None
            )
            self.stop()
    
    async def _step2_description(self, interaction: discord.Interaction):
        """Step 2: Set description."""
        self.step = 3
        
        embed = discord.Embed(
            title="📝 Step 2: Panel Description",
            description="Please provide a description for the reaction role panel.",
            color=COLORS["primary"]
        )
        embed.add_field(
            name="Example",
            value="Select your desired roles from the buttons below. You can toggle roles on and off at any time.",
            inline=False
        )
        embed.set_footer(text="Type your description in chat, or click 'Next Step' to skip.")
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Wait for description response
        try:
            def check(msg):
                return msg.author.id == self.interaction.user.id and msg.channel.id == self.interaction.channel.id
            
            msg = await self.cog.bot.wait_for('message', timeout=300.0, check=check)
            self.setup_data['description'] = msg.content[:1024]  # Limit length
            await msg.delete()
            
            await self.interaction.edit_original_response(
                content=f"✅ **Description set.**",
                embed=None,
                view=self
            )
        except asyncio.TimeoutError:
            self.setup_data['description'] = "Select your desired roles from the buttons below."
            await self.interaction.edit_original_response(
                content="⏭️ **Using default description.**",
                embed=None,
                view=self
            )
    
    async def _step3_mode(self, interaction: discord.Interaction):
        """Step 3: Set mode."""
        self.step = 4
        
        embed = discord.Embed(
            title="⚙️ Step 3: Panel Mode",
            description="Select how users can interact with this panel:",
            color=COLORS["primary"]
        )
        
        modes = {
            'toggle': '🔄 Toggle - Add/remove roles freely',
            'add_only': '➕ Add Only - Can only add roles',
            'remove_only': '➖ Remove Only - Can only remove roles',
            'exclusive': '⭐ Exclusive - One role at a time'
        }
        
        for mode, desc in modes.items():
            embed.add_field(name=mode.title(), value=desc, inline=False)
        
        embed.set_footer(text="Type your choice, or click 'Next Step' to use 'toggle'.")
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Wait for mode response
        try:
            def check(msg):
                return msg.author.id == self.interaction.user.id and msg.channel.id == self.interaction.channel.id
            
            msg = await self.cog.bot.wait_for('message', timeout=300.0, check=check)
            mode_choice = msg.content.lower().strip()
            if mode_choice in modes:
                self.setup_data['mode'] = mode_choice
            await msg.delete()
            
            await self.interaction.edit_original_response(
                content=f"✅ **Mode set to:** {self.setup_data['mode'].title()}",
                embed=None,
                view=self
            )
        except asyncio.TimeoutError:
            await self.interaction.edit_original_response(
                content="⏭️ **Using default mode: toggle.**",
                embed=None,
                view=self
            )
    
    async def _step4_roles(self, interaction: discord.Interaction):
        """Step 4: Role selection."""
        self.step = 5
        
        # Create role select menu
        roles = [role for role in self.interaction.guild.roles 
                if role.name != "@everyone" and not role.managed and role < self.interaction.guild.me.top_role]
        
        if not roles:
            await interaction.response.edit_message(
                content="❌ **No assignable roles found.** Make sure the bot's role is higher than the roles you want to assign.",
                embed=None,
                view=None
            )
            self.stop()
            return
        
        embed = discord.Embed(
            title="👥 Step 4: Select Roles",
            description="Select the roles you want to include in this panel.",
            color=COLORS["primary"]
        )
        embed.set_footer(text="Select multiple roles, then click 'Next Step'.")
        
        # Create select menu
        select = Select(
            placeholder="Select roles to include...",
            min_values=1,
            max_values=min(25, len(roles)),  # Discord limit
            options=[
                discord.SelectOption(
                    label=role.name,
                    value=str(role.id),
                    description=f"Position: {role.position}"
                )
                for role in roles[:25]  # Discord limit
            ]
        )
        
        async def select_callback(select_interaction: discord.Interaction):
            selected_ids = [int(val) for val in select.values]
            self.setup_data['roles'] = [self.interaction.guild.get_role(rid) for rid in selected_ids]
            
            await select_interaction.response.edit_message(
                content=f"✅ **Selected {len(self.setup_data['roles'])} roles.**",
                embed=None,
                view=self
            )
        
        select.callback = select_callback
        
        view = View()
        view.add_item(select)
        view.add_item(Button(
            label="Next Step",
            style=discord.ButtonStyle.primary,
            custom_id="rr_setup_next"
        ))
        
        # Override the next button for this step
        for item in view.children:
            if item.custom_id == "rr_setup_next":
                item.callback = lambda i: self.next_button(i, item)
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def _step5_emojis(self, interaction: discord.Interaction):
        """Step 5: Assign emojis to roles."""
        self.step = 6
        
        embed = discord.Embed(
            title="😊 Step 5: Assign Emojis",
            description="For each role, provide an emoji. Type them in chat as: `role_name: emoji`",
            color=COLORS["primary"]
        )
        
        role_list = "\n".join([f"• {role.name}" for role in self.setup_data['roles']])
        embed.add_field(name="Roles to assign emojis:", value=role_list, inline=False)
        
        embed.add_field(
            name="Example",
            value="```\nGamer: 🎮\nDeveloper: 💻\nArtist: 🎨\n```",
            inline=False
        )
        
        embed.set_footer(text="Type all assignments, then click 'Next Step'.")
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Wait for emoji assignments
        try:
            def check(msg):
                return msg.author.id == self.interaction.user.id and msg.channel.id == self.interaction.channel.id
            
            collected = {}
            remaining = set(self.setup_data['roles'])
            
            while remaining:
                msg = await self.cog.bot.wait_for('message', timeout=300.0, check=check)
                content = msg.content.strip()
                await msg.delete()
                
                if ':' in content:
                    role_name, emoji = content.split(':', 1)
                    role_name = role_name.strip()
                    emoji = emoji.strip()
                    
                    # Find matching role
                    for role in list(remaining):
                        if role.name.lower() == role_name.lower():
                            collected[role] = emoji
                            remaining.remove(role)
                            break
                
                # Update progress
                if remaining:
                    await self.interaction.edit_original_response(
                        content=f"✅ **Assigned {len(collected)} emojis.**\n\nStill need: {', '.join([r.name for r in remaining])}",
                        embed=None,
                        view=self
                    )
            
            self.setup_data['role_emojis'] = collected
            await self.interaction.edit_original_response(
                content=f"✅ **All emojis assigned!**",
                embed=None,
                view=self
            )
            
        except asyncio.TimeoutError:
            await self.interaction.edit_original_response(
                content="❌ **Setup timed out.**",
                embed=None,
                view=None
            )
            self.stop()
    
    async def _step6_preview(self, interaction: discord.Interaction):
        """Step 6: Preview and confirm."""
        self.step = 7
        
        # Create preview embed
        embed = discord.Embed(
            title=self.setup_data['title'] or "Reaction Roles",
            description=self.setup_data['description'] or "Select your desired roles from the buttons below.",
            color=COLORS["primary"]
        )
        
        # Add role fields with emojis
        for role, emoji in self.setup_data['role_emojis'].items():
            embed.add_field(
                name=f"{emoji} {role.name}",
                value=f"Mode: {self.setup_data['mode'].title()}",
                inline=True
            )
        
        embed.set_footer(text=f"Panel ID: {uuid.uuid4().hex[:8]} | Created by {self.interaction.user.display_name}")
        
        # Create confirmation view
        confirm_view = View()
        
        async def confirm_callback(confirm_interaction: discord.Interaction):
            await self.cog._create_panel(self.interaction, self.setup_data)
            await confirm_interaction.response.edit_message(
                content="✅ **Reaction role panel created successfully!**",
                embed=None,
                view=None
            )
            self.stop()
        
        async def edit_callback(edit_interaction: discord.Interaction):
            await edit_interaction.response.edit_message(
                content="🔄 **Returning to edit mode...**",
                embed=None,
                view=self
            )
            self.step = 1  # Restart from beginning
        
        confirm_view.add_item(Button(
            label="✅ Confirm",
            style=discord.ButtonStyle.success,
            custom_id="rr_confirm"
        ))
        confirm_view.add_item(Button(
            label="✏️ Edit",
            style=discord.ButtonStyle.secondary,
            custom_id="rr_edit"
        ))
        confirm_view.add_item(Button(
            label="❌ Cancel",
            style=discord.ButtonStyle.danger,
            custom_id="rr_cancel"
        ))
        
        # Set callbacks
        for item in confirm_view.children:
            if item.custom_id == "rr_confirm":
                item.callback = confirm_callback
            elif item.custom_id == "rr_edit":
                item.callback = edit_callback
            elif item.custom_id == "rr_cancel":
                item.callback = self.cancel_button
        
        await interaction.response.edit_message(
            content="📋 **Preview your panel:**",
            embed=embed,
            view=confirm_view
        )


class ReactionRolePanelView(View):
    """Persistent view for reaction role panel."""
    
    def __init__(self, panel_id: str, cog: 'ReactionRoleCog'):
        super().__init__(timeout=None)  # Persistent view
        self.panel_id = panel_id
        self.cog = cog
        self.panel = None  # Will be loaded on first interaction
    
    async def _get_panel(self) -> Optional[ReactionRolePanel]:
        """Get panel data."""
        if not self.panel:
            self.panel = await self.cog.reaction_role_store.get(self.panel_id)
        return self.panel
    
    async def _handle_role_action(self, interaction: discord.Interaction, role_id: int):
        """Handle role assignment/removal."""
        # Check if user is verified
        if not await is_verified(interaction):
            await interaction.response.send_message(
                "❌ You must be verified to use reaction roles.",
                ephemeral=True
            )
            return
        
        panel = await self._get_panel()
        if not panel:
            await interaction.response.send_message(
                "❌ This panel is no longer active.",
                ephemeral=True
            )
            return
        
        guild = interaction.guild
        member = interaction.user
        role = guild.get_role(role_id)
        
        if not role:
            await interaction.response.send_message(
                "❌ Role no longer exists.",
                ephemeral=True
            )
            return
        
        try:
            if panel.mode == "toggle":
                if role in member.roles:
                    await member.remove_roles(role)
                    action = "removed"
                else:
                    await member.add_roles(role)
                    action = "added"
            
            elif panel.mode == "add_only":
                if role not in member.roles:
                    await member.add_roles(role)
                    action = "added"
                else:
                    await interaction.response.send_message(
                        "❌ You already have this role.",
                        ephemeral=True
                    )
                    return
            
            elif panel.mode == "remove_only":
                if role in member.roles:
                    await member.remove_roles(role)
                    action = "removed"
                else:
                    await interaction.response.send_message(
                        "❌ You don't have this role.",
                        ephemeral=True
                    )
                    return
            
            elif panel.mode == "exclusive":
                # Remove all other roles from this panel
                panel_role_ids = [opt['role_id'] for opt in panel.options]
                roles_to_remove = [r for r in member.roles if r.id in panel_role_ids and r.id != role_id]
                
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove)
                
                # Add the new role if not already present
                if role not in member.roles:
                    await member.add_roles(role)
                
                action = "set"
            
            # Log the action
            await self.cog._log_action(
                panel, member, role, action, interaction
            )
            
            await interaction.response.send_message(
                f"✅ Role **{role.name}** {action}!",
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to manage roles.",
                ephemeral=True
            )
        except Exception as e:
            log.error(f"Error handling role action: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while managing roles.",
                ephemeral=True
            )


class ReactionRoleCog(commands.Cog):
    """Autonomous reaction role panels system."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reaction_role_store = None
        self.server_config_store = None
    
    async def cog_load(self):
        """Initialize stores and load all panels on startup."""
        # Initialize stores using bot's database path
        settings = self.bot.settings
        self.reaction_role_store = ReactionRoleStore(settings.sqlite_path)
        self.server_config_store = ServerConfigStore(settings.sqlite_path)
        
        # Initialize database schema
        await self.reaction_role_store.init()
        
        # Load all panels
        panels = await self.reaction_role_store.get_all_panels()
        
        for panel in panels:
            try:
                # Create persistent view for each panel
                view = ReactionRolePanelView(panel.panel_id, self)
                self.bot.add_view(view, message_id=panel.message_id)
                log.info(f"Loaded persistent view for panel: {panel.panel_id}")
            except Exception as e:
                log.error(f"Failed to load panel {panel.panel_id}: {e}")
        
        log.info(f"Loaded {len(panels)} reaction role panels")
    
    @app_commands.command(
        name="rr",
        description="Manage reaction role panels"
    )
    @app_commands.describe(
        action="Action to perform"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="create", value="create"),
            app_commands.Choice(name="edit", value="edit"),
            app_commands.Choice(name="delete", value="delete")
        ]
    )
    @require_admin()
    async def rr_command(
        self,
        interaction: discord.Interaction,
        action: str
    ):
        """Main reaction role command."""
        if action == "create":
            await self._start_setup(interaction)
        elif action == "edit":
            # TODO: Implement edit functionality
            await interaction.response.send_message(
                "❌ Edit functionality coming soon.",
                ephemeral=True
            )
        elif action == "delete":
            # TODO: Implement delete functionality
            await interaction.response.send_message(
                "❌ Delete functionality coming soon.",
                ephemeral=True
            )
    
    async def _start_setup(self, interaction: discord.Interaction):
        """Start the reaction role setup process."""
        # Check permissions
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ I need the **Manage Roles** permission to create reaction role panels.",
                ephemeral=True
            )
            return
        
        if not interaction.guild.me.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ I need the **Manage Channels** permission to create log channels.",
                ephemeral=True
            )
            return
        
        # Create setup view
        setup_view = ReactionRoleSetupView(self, interaction)
        
        embed = discord.Embed(
            title="🚀 Reaction Role Panel Setup",
            description="Let's create your reaction role panel! Click 'Next Step' to begin.",
            color=COLORS["primary"]
        )
        embed.add_field(
            name="Setup Process:",
            value="1. Panel Title\n2. Panel Description\n3. Panel Mode\n4. Role Selection\n5. Emoji Assignment\n6. Preview & Confirm",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, view=setup_view, ephemeral=True)
    
    async def _create_panel(self, interaction: discord.Interaction, setup_data: Dict[str, Any]):
        """Create the reaction role panel."""
        # Get or create log channel
        log_channel = await self._get_or_create_log_channel(interaction.guild)
        
        # Create panel data
        panel_id = f"rr_{interaction.guild.id}_{uuid.uuid4().hex[:8]}"
        
        options = []
        for role, emoji in setup_data['role_emojis'].items():
            options.append({
                'role_id': role.id,
                'emoji': emoji,
                'role_name': role.name
            })
        
        panel = ReactionRolePanel(
            panel_id=panel_id,
            guild_id=interaction.guild.id,
            channel_id=interaction.channel.id,
            message_id=0,  # Will be set after message creation
            title=setup_data['title'] or "Reaction Roles",
            description=setup_data['description'] or "Select your desired roles from the buttons below.",
            mode=setup_data['mode'],
            log_channel_id=log_channel.id if log_channel else None,
            created_by=interaction.user.id,
            created_at=datetime.utcnow(),
            options=options
        )
        
        # Create panel embed
        embed = discord.Embed(
            title=panel.title,
            description=panel.description,
            color=COLORS["primary"]
        )
        
        # Add role fields
        for option in panel.options:
            embed.add_field(
                name=f"{option['emoji']} {option['role_name']}",
                value=f"Click to {panel.mode} this role",
                inline=True
            )
        
        embed.set_footer(text=f"Panel ID: {panel.panel_id[:8]} | Mode: {panel.mode.title()}")
        
        # Create persistent view with buttons
        class PanelView(View):
            def __init__(self, cog_ref, panel_ref):
                super().__init__(timeout=None)  # Persistent view
                self.cog_ref = cog_ref
                self.panel_ref = panel_ref
            
            async def handle_role_button(self, interaction: discord.Interaction, role_id: int):
                """Handle role button click."""
                panel_view = ReactionRolePanelView(self.panel_ref.panel_id, self.cog_ref)
                await panel_view._handle_role_action(interaction, role_id)
        
        view = PanelView(self, panel)
        
        for option in panel.options:
            button = Button(
                label=option['role_name'],
                emoji=option['emoji'],
                style=discord.ButtonStyle.secondary,
                custom_id=f"rr:panel:{panel.panel_id}:role:{option['role_id']}"
            )
            
            # Set callback using the view's method with proper closure
            def make_callback(role_id_val):
                async def callback(interaction: discord.Interaction):
                    await view.handle_role_button(interaction, role_id_val)
                return callback
            
            button.callback = make_callback(option['role_id'])
            view.add_item(button)
        
        # Send message
        message = await interaction.channel.send(embed=embed, view=view)
        
        # Update panel with message ID
        panel.message_id = message.id
        await self.reaction_role_store.create(panel)
        
        # Log creation
        if log_channel:
            await self._log_panel_creation(panel, interaction.user, log_channel)
    
    async def _get_or_create_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Get or create the log channel."""
        # Check existing config
        config = await self.server_config_store.get(guild.id)
        
        # Try existing channels
        channel_names = ["guardian-logs", "bot-logs", "guardian-rr-logs"]
        
        for name in channel_names:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel:
                return channel
        
        # Create new channel if we have permission
        if guild.me.guild_permissions.manage_channels:
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(
                        view_channel=False,
                        send_messages=False,
                        read_message_history=False
                    ),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        embed_links=True,
                        read_message_history=True
                    )
                }
                
                # Add staff roles
                for role in guild.roles:
                    if any(perm in role.permissions for perm in ["manage_guild", "administrator"]):
                        overwrites[role] = discord.PermissionOverwrite(
                            view_channel=True,
                            read_message_history=True
                        )
                
                channel = await guild.create_text_channel(
                    "guardian-logs",
                    topic="Audit logs for Guardian (reaction roles, setup, moderation).",
                    overwrites=overwrites
                )
                
                log.info(f"Created log channel: {channel.name} in guild {guild.id}")
                return channel
                
            except Exception as e:
                log.error(f"Failed to create log channel in guild {guild.id}: {e}")
                return None
        
        return None
    
    async def _log_action(self, panel: ReactionRolePanel, user: discord.User, 
                        role: discord.Role, action: str, interaction: discord.Interaction):
        """Log role action to log channel."""
        if not panel.log_channel_id:
            return
        
        log_channel = self.bot.get_channel(panel.log_channel_id)
        if not log_channel:
            return
        
        embed = discord.Embed(
            title="🔄 Role Action",
            color=COLORS["info"],
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=True)
        embed.add_field(name="Role", value=f"{role.mention} ({role.id})", inline=True)
        embed.add_field(name="Action", value=action.title(), inline=True)
        embed.add_field(name="Panel ID", value=panel.panel_id[:8], inline=True)
        embed.add_field(name="Channel", value=f"<#{interaction.channel.id}>", inline=True)
        embed.add_field(name="Result", value="✅ Success", inline=True)
        
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            log.error(f"Failed to log role action: {e}")
    
    async def _log_panel_creation(self, panel: ReactionRolePanel, creator: discord.User, 
                                log_channel: discord.TextChannel):
        """Log panel creation."""
        embed = discord.Embed(
            title="📋 Panel Created",
            color=COLORS["success"],
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="Panel ID", value=panel.panel_id[:8], inline=True)
        embed.add_field(name="Creator", value=f"{creator.mention} ({creator.id})", inline=True)
        embed.add_field(name="Channel", value=f"<#{panel.channel_id}>", inline=True)
        embed.add_field(name="Mode", value=panel.mode.title(), inline=True)
        embed.add_field(name="Roles", value=str(len(panel.options)), inline=True)
        embed.add_field(name="Log Channel", value=f"<#{panel.log_channel_id}>", inline=True)
        
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            log.error(f"Failed to log panel creation: {e}")


async def setup(bot: commands.Bot):
    """Setup the reaction role cog."""
    await bot.add_cog(ReactionRoleCog(bot))
    log.info("Reaction role cog loaded")
