from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import discord.ui
import datetime

from ..security.auth import is_root_actor
from ..utils import safe_embed


class RootManagementCog(commands.Cog):
    """Root operator management commands."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
    
    async def _check_root_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has root-level permissions."""
        if not await is_root_actor(self.bot, interaction):
            await interaction.response.send_message(
                "❌ This command requires root-level access.",
                ephemeral=True
            )
            return False
        return True
    
    @app_commands.command(
        name="root_request",
        description="Request to add a user as a root operator (Root only)"
    )
    @app_commands.describe(
        user="The user to request as root operator"
    )
    async def root_request(self, interaction: discord.Interaction, user: discord.User) -> None:
        """Request to add a user as a root operator."""
        
        if not await self._check_root_permission(interaction):
            return
        
        if user.bot:
            await interaction.response.send_message(
                "❌ Cannot add bots as root operators.",
                ephemeral=True
            )
            return
        
        try:
            request_id = await self.bot.root_store.request_add_root(user.id, interaction.user.id)
            
            await interaction.response.send_message(
                f"✅ Root request created for {user.mention} (Request ID: {request_id}).\n"
                "A root operator must approve this request.",
                ephemeral=True
            )
            
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Failed to create request: {e}",
                ephemeral=True
            )
        except Exception as e:
            self.bot.log.error(f"Error creating root request: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while creating the request.",
                ephemeral=True
            )
    
    @app_commands.command(
        name="root_approve",
        description="Approve a pending root request (Root only)"
    )
    @app_commands.describe(
        request_id="The request ID to approve"
    )
    async def root_approve(self, interaction: discord.Interaction, request_id: int) -> None:
        """Approve a pending root request."""
        
        if not await self._check_root_permission(interaction):
            return
        
        try:
            success = await self.bot.root_store.approve_request(request_id, interaction.user.id)
            
            if success:
                await interaction.response.send_message(
                    f"✅ Root request {request_id} approved successfully.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ Root request {request_id} could not be approved (user may already be root).",
                    ephemeral=True
                )
                
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Failed to approve request: {e}",
                ephemeral=True
            )
        except Exception as e:
            self.bot.log.error(f"Error approving root request: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while approving the request.",
                ephemeral=True
            )
    
    @app_commands.command(
        name="root_reject",
        description="Reject a pending root request (Root only)"
    )
    @app_commands.describe(
        request_id="The request ID to reject"
    )
    async def root_reject(self, interaction: discord.Interaction, request_id: int) -> None:
        """Reject a pending root request."""
        
        if not await self._check_root_permission(interaction):
            return
        
        try:
            await self.bot.root_store.reject_request(request_id, interaction.user.id)
            
            await interaction.response.send_message(
                f"✅ Root request {request_id} rejected.",
                ephemeral=True
            )
                
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Failed to reject request: {e}",
                ephemeral=True
            )
        except Exception as e:
            self.bot.log.error(f"Error rejecting root request: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while rejecting the request.",
                ephemeral=True
            )
    
    @app_commands.command(
        name="root_remove",
        description="Remove a user from root operators (Root only)"
    )
    @app_commands.describe(
        user="The user to remove from root operators"
    )
    async def root_remove(self, interaction: discord.Interaction, user: discord.User) -> None:
        """Remove a user from root operators."""
        
        if not await self._check_root_permission(interaction):
            return
        
        # Cannot remove guild owners or bot owners
        if interaction.guild and user.id == interaction.guild.owner_id:
            await interaction.response.send_message(
                "❌ Cannot remove guild owners from root operators.",
                ephemeral=True
            )
            return
        
        if await self.bot.root_store.is_bot_owner(self.bot, user.id):
            await interaction.response.send_message(
                "❌ Cannot remove bot application owners from root operators.",
                ephemeral=True
            )
            return
        
        try:
            success = await self.bot.root_store.remove_root(user.id)
            
            if success:
                await interaction.response.send_message(
                    f"✅ {user.mention} removed from root operators.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ {user.mention} is not a root operator.",
                    ephemeral=True
                )
                
        except Exception as e:
            self.bot.log.error(f"Error removing root: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while removing the root operator.",
                ephemeral=True
            )
    
    @app_commands.command(
        name="root_list",
        description="List all root operators (Root only)"
    )
    async def root_list(self, interaction: discord.Interaction) -> None:
        """List all root operators."""
        
        if not await self._check_root_permission(interaction):
            return
        
        try:
            roots = await self.bot.root_store.list_roots()
            pending = await self.bot.root_store.list_pending_requests()
            
            embed = safe_embed(
                title="🔐 Root Operators",
                color=discord.Color.blue()
            )
            
            if roots:
                root_list = []
                for root in roots:
                    user = self.bot.get_user(root.user_id)
                    name = user.name if user else f"Unknown User ({root.user_id})"
                    added_by_user = self.bot.get_user(root.added_by)
                    added_by = added_by_user.name if added_by_user else f"Unknown ({root.added_by})"
                    root_list.append(f"• {name} (added by {added_by} on {root.added_at.strftime('%Y-%m-%d')})")
                
                embed.add_field(
                    name=f"Active Root Operators ({len(roots)})",
                    value="\n".join(root_list),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Active Root Operators",
                    value="No root operators found.",
                    inline=False
                )
            
            if pending:
                pending_list = []
                for request in pending:
                    target_user = self.bot.get_user(request.target_id)
                    target_name = target_user.name if target_user else f"Unknown User ({request.target_id})"
                    requester_user = self.bot.get_user(request.requester_id)
                    requester_name = requester_user.name if requester_user else f"Unknown ({request.requester_id})"
                    pending_list.append(f"• {target_name} (requested by {requester_name} on {request.requested_at.strftime('%Y-%m-%d')}) - ID: {request.request_id}")
                
                embed.add_field(
                    name=f"Pending Requests ({len(pending)})",
                    value="\n".join(pending_list),
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.bot.log.error(f"Error listing roots: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while listing root operators.",
                ephemeral=True
            )
