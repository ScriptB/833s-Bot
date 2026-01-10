from __future__ import annotations

import asyncio
import json
from typing import Any

import discord
from discord import ui
from discord.ui import Button, Select, TextInput
from discord.ext import commands

from ..services.discord_safety import safe_defer
from ..utils import safe_followup, safe_response, get_confirmation, error_embed, success_embed
from ..constants import LONG_TIMEOUT_SECONDS, COLORS


class OverhaulSetupView(ui.View):
    """Interactive UI for configuring and executing a full server overhaul."""

    def __init__(self, cog: commands.Cog, guild: discord.Guild) -> None:
        super().__init__(timeout=LONG_TIMEOUT_SECONDS)
        self.cog = cog
        self.guild = guild
        self.config: dict[str, Any] = {
            "server_name": guild.name,
            "verification_level": "high",
            "default_notifications": "only_mentions",
            "content_filter": "all_members",
            "roles": [
                {"name": "Verified", "color": "green", "hoist": False, "mentionable": False},
                {"name": "Member", "color": "dark_green", "hoist": False, "mentionable": False},
                {"name": "Bronze", "color": "blurple", "hoist": True, "mentionable": False},
                {"name": "Silver", "color": "greyple", "hoist": True, "mentionable": False},
                {"name": "Gold", "color": "gold", "hoist": True, "mentionable": False},
                {"name": "Platinum", "color": "dark_purple", "hoist": True, "mentionable": False},
                {"name": "Diamond", "color": "dark_blue", "hoist": True, "mentionable": False},
                {"name": "Pet Pings", "color": "orange", "hoist": False, "mentionable": True},
                {"name": "Announce Pings", "color": "red", "hoist": False, "mentionable": True},
                {"name": "Giveaway Pings", "color": "purple", "hoist": False, "mentionable": True},
                {"name": "Event Pings", "color": "yellow", "hoist": False, "mentionable": True},
                {"name": "Muted", "color": "dark_grey", "hoist": False, "mentionable": False},
            ],
            "categories": [
                {"name": "Start Here", "channels": ["rules", "verify", "introductions"]},
                {"name": "Community", "channels": ["general", "media", "bot-commands"]},
                {"name": "Support", "channels": ["help"]},
                {"name": "Events", "channels": ["events", "giveaways"]},
                {"name": "Staff", "channels": ["staff-chat", "mod-logs"]},  # Removed trailing comma
            ]
        }
        self.message: discord.Message | None = None

    # --- UI Elements ---------------------------------------------------------

    @ui.button(label="Server Settings", style=discord.ButtonStyle.secondary)
    async def server_settings(self, interaction: discord.Interaction, button: Button) -> None:
        await safe_defer(interaction, ephemeral=True, thinking=True)
        modal = ServerSettingsModal(self.config)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.saved:
            await safe_followup(interaction, "✅ Server settings saved.", ephemeral=True)

    @ui.button(label="Roles", style=discord.ButtonStyle.secondary)
    async def edit_roles(self, interaction: discord.Interaction, button: Button) -> None:
        await safe_defer(interaction, ephemeral=True, thinking=True)
        view = RoleListView(self.config)
        embed = discord.Embed(title="Role Configuration", description="Edit or delete roles below.")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ui.button(label="Categories & Channels", style=discord.ButtonStyle.secondary)
    async def edit_categories(self, interaction: discord.Interaction, button: Button) -> None:
        await safe_defer(interaction, ephemeral=True, thinking=True)
        view = CategoryListView(self.config)
        embed = discord.Embed(title="Categories & Channels", description="Edit structure below.")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ui.button(label="Preview", style=discord.ButtonStyle.secondary)
    async def preview(self, interaction: discord.Interaction, button: Button) -> None:
        await safe_defer(interaction, ephemeral=True, thinking=True)
        lines = ["**Server Settings**"]
        lines.append(f"- Name: {self.config['server_name']}")
        lines.append(f"- Verification: {self.config['verification_level']}")
        lines.append(f"- Notifications: {self.config['default_notifications']}")
        lines.append(f"- Content filter: {self.config['content_filter']}")
        lines.append("\n**Roles**")
        for r in self.config["roles"]:
            lines.append(f"- {r['name']} (color: {r['color']}, hoist: {r['hoist']}, mentionable: {r['mentionable']})")
        lines.append("\n**Categories**")
        for cat in self.config["categories"]:
            lines.append(f"- {cat['name']}: {', '.join(cat['channels'])}")
        await safe_followup(interaction, "\n".join(lines), ephemeral=True)

    @ui.button(label="Execute Overhaul", style=discord.ButtonStyle.danger)
    async def execute(self, interaction: discord.Interaction, button: Button) -> None:
        await safe_defer(interaction, ephemeral=True, thinking=True)
        # Validate config before proceeding
        if not self.config["roles"]:
            await safe_followup(interaction, "❌ No roles configured. Add roles before executing.", ephemeral=True)
            return
        if not self.config["categories"]:
            await safe_followup(interaction, "❌ No categories configured. Add categories before executing.", ephemeral=True)
            return
        modal = ConfirmModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.confirmed:
            await safe_followup(interaction, "❌ Overhaul cancelled.", ephemeral=True)
            return
        # Disable all buttons to prevent double-run
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)
        # Run the overhaul
        from .overhaul_executor import OverhaulExecutor
        executor = OverhaulExecutor(self.cog, self.guild, self.config)
        result = await executor.run()
        await safe_followup(interaction, result, ephemeral=True)

    # -------------------------------------------------------------------------

    async def on_timeout(self) -> None:
        if self.message:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)


# --- Modals -----------------------------------------------------------------

class ServerSettingsModal(ui.Modal, title="Server Settings"):
    server_name = TextInput(label="Server Name", default="833s")
    verification_level = ui.TextInput(
        label="Verification Level",
        placeholder="Enter: none, low, medium, high, highest",
        default="high",
        max_length=10,
    )
    default_notifications = ui.TextInput(
        label="Default Notifications",
        placeholder="Enter: all_messages or only_mentions",
        default="only_mentions",
        max_length=20,
    )
    content_filter = ui.TextInput(
        label="Content Filter",
        placeholder="Enter: disabled, members_without_roles, all_members",
        default="all_members",
        max_length=25,
    )

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(title="Server Settings")
        self.config = config
        self.saved = False
        self.server_name.default = config.get("server_name", "833s")
        self.verification_level.default = config.get("verification_level", "high")
        self.default_notifications.default = config.get("default_notifications", "only_mentions")
        self.content_filter.default = config.get("content_filter", "all_members")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.config["server_name"] = self.server_name.value
        # Validate and convert text inputs to proper values
        vl = self.verification_level.value.strip().lower()
        self.config["verification_level"] = vl if vl in {"none", "low", "medium", "high", "highest"} else "high"
        
        dn = self.default_notifications.value.strip().lower()
        self.config["default_notifications"] = dn if dn in {"all_messages", "only_mentions"} else "only_mentions"
        
        cf = self.content_filter.value.strip().lower()
        self.config["content_filter"] = cf if cf in {"disabled", "members_without_roles", "all_members"} else "all_members"
        
        self.saved = True
        await interaction.response.send_message("Saved.", ephemeral=True)


class ConfirmModal(ui.Modal, title="Confirm Overhaul"):
    confirm = TextInput(label='Type "DELETE EVERYTHING" to confirm', required=True)

    def __init__(self) -> None:
        super().__init__(title="Confirm Overhaul")
        self.confirmed = False

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.confirm.value.strip().upper() == "DELETE EVERYTHING":
            self.confirmed = True
            await interaction.response.send_message("Confirmed. Starting overhaul...", ephemeral=True)
        else:
            await interaction.response.send_message("Confirmation mismatch. Cancelled.", ephemeral=True)


# --- List Views --------------------------------------------------------------

class RoleListView(ui.View):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(timeout=300.0)
        self.config = config
        # Create select with options from config
        self.edit_role_select = ui.Select(
            placeholder="Edit a role",
            options=[discord.SelectOption(label=r["name"], description=r["name"]) for r in config["roles"]]
        )
        self.add_item(self.edit_role_select)
    async def edit_role(self, interaction: discord.Interaction, select: ui.Select) -> None:
        await safe_defer(interaction, ephemeral=True, thinking=True)
        role_name = select.values[0]
        role_cfg = next(r for r in self.config["roles"] if r["name"] == role_name)
        modal = RoleModal(role_cfg)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.saved:
            await safe_followup(interaction, f"✅ Role '{role_name}' updated.", ephemeral=True)

    @ui.button(label="Add Role", style=discord.ButtonStyle.secondary)
    async def add_role(self, interaction: discord.Interaction, button: Button) -> None:
        await safe_defer(interaction, ephemeral=True, thinking=True)
        new_cfg = {"name": "New Role", "color": "default", "hoist": False, "mentionable": False}
        modal = RoleModal(new_cfg)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.saved:
            self.config["roles"].append(new_cfg)
            await safe_followup(interaction, f"✅ Role '{new_cfg['name']}' added.", ephemeral=True)

    @ui.button(label="Delete Role", style=discord.ButtonStyle.secondary)
    async def delete_role(self, interaction: discord.Interaction, button: Button) -> None:
        await safe_defer(interaction, ephemeral=True, thinking=True)
        select = ui.Select(
            placeholder="Select role to delete",
            options=[discord.SelectOption(label=r["name"], description=r["name"]) for r in self.config["roles"]],
        )
        async def callback(i: discord.Interaction, s: ui.Select) -> None:
            name = s.values[0]
            self.config["roles"] = [r for r in self.config["roles"] if r["name"] != name]
            await i.response.send_message(f"✅ Role '{name}' deleted.", ephemeral=True)
            s.view.stop()
        select.callback = callback
        view = ui.View().add_item(select)
        await interaction.response.send_message("Select a role to delete:", view=view, ephemeral=True)


class CategoryListView(ui.View):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(timeout=300.0)
        self.config = config
        # Create select with options from config
        self.edit_category_select = ui.Select(
            placeholder="Edit a category",
            options=[discord.SelectOption(label=cat["name"], description=cat["name"]) for cat in config["categories"]]
        )
        self.add_item(self.edit_category_select)
    async def edit_category(self, interaction: discord.Interaction, select: ui.Select) -> None:
        await safe_defer(interaction, ephemeral=True, thinking=True)
        cat_name = select.values[0]
        cat_cfg = next(c for c in self.config["categories"] if c["name"] == cat_name)
        modal = CategoryModal(cat_cfg)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.saved:
            await safe_followup(interaction, f"✅ Category '{cat_name}' updated.", ephemeral=True)

    @ui.button(label="Add Category", style=discord.ButtonStyle.secondary)
    async def add_category(self, interaction: discord.Interaction, button: Button) -> None:
        await safe_defer(interaction, ephemeral=True, thinking=True)
        new_cfg = {"name": "New Category", "channels": []}
        modal = CategoryModal(new_cfg)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.saved:
            self.config["categories"].append(new_cfg)
            await safe_followup(interaction, f"✅ Category '{new_cfg['name']}' added.", ephemeral=True)

    @ui.button(label="Delete Category", style=discord.ButtonStyle.secondary)
    async def delete_category(self, interaction: discord.Interaction, button: Button) -> None:
        await safe_defer(interaction, ephemeral=True, thinking=True)
        select = ui.Select(
            placeholder="Select category to delete",
            options=[discord.SelectOption(label=c["name"], description=c["name"]) for c in self.config["categories"]],
        )
        async def callback(i: discord.Interaction, s: ui.Select) -> None:
            name = s.values[0]
            self.config["categories"] = [c for c in self.config["categories"] if c["name"] != name]
            await i.response.send_message(f"✅ Category '{name}' deleted.", ephemeral=True)
            s.view.stop()
        select.callback = callback
        view = ui.View().add_item(select)
        await interaction.response.send_message("Select a category to delete:", view=view, ephemeral=True)


# --- Modals for editing items ------------------------------------------------

class RoleModal(ui.Modal, title="Edit Role"):
    name = TextInput(label="Name")
    color = Select(
        placeholder="Color",
        options=[
            discord.SelectOption(label="Default", value="default"),
            discord.SelectOption(label="Blue", value="blurple"),
            discord.SelectOption(label="Green", value="green"),
            discord.SelectOption(label="Dark Green", value="dark_green"),
            discord.SelectOption(label="Gold", value="gold"),
            discord.SelectOption(label="Grey", value="greyple"),
            discord.SelectOption(label="Orange", value="orange"),
            discord.SelectOption(label="Purple", value="purple"),
            discord.SelectOption(label="Dark Purple", value="dark_purple"),
            discord.SelectOption(label="Dark Blue", value="dark_blue"),
            discord.SelectOption(label="Red", value="red"),
            discord.SelectOption(label="Dark Grey", value="dark_grey"),
        ],
    )
    hoist = Select(placeholder="Hoist (show separately)", options=[discord.SelectOption(label="No", value="False"), discord.SelectOption(label="Yes", value="True")])
    mentionable = Select(placeholder="Mentionable", options=[discord.SelectOption(label="No", value="False"), discord.SelectOption(label="Yes", value="True")])

    def __init__(self, role_cfg: dict[str, Any]) -> None:
        super().__init__(title="Edit Role")
        self.role_cfg = role_cfg
        self.saved = False
        self.name.default = role_cfg["name"]
        self.color.default = role_cfg["color"]
        self.hoist.default = "True" if role_cfg["hoist"] else "False"
        self.mentionable.default = "True" if role_cfg["mentionable"] else "False"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.role_cfg["name"] = self.name.value
        self.role_cfg["color"] = self.color.values[0]
        self.role_cfg["hoist"] = self.hoist.values[0] == "True"
        self.role_cfg["mentionable"] = self.mentionable.values[0] == "True"
        self.saved = True
        await interaction.response.send_message("Saved.", ephemeral=True)


class CategoryModal(ui.Modal, title="Edit Category"):
    name = TextInput(label="Name")
    channels = TextInput(label="Channels (comma-separated)", style=discord.TextStyle.paragraph)

    def __init__(self, cat_cfg: dict[str, Any]) -> None:
        super().__init__(title="Edit Category")
        self.cat_cfg = cat_cfg
        self.saved = False
        self.name.default = cat_cfg["name"]
        self.channels.default = ", ".join(cat_cfg["channels"])

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.cat_cfg["name"] = self.name.value
        self.cat_cfg["channels"] = [c.strip() for c in self.channels.value.split(",") if c.strip()]
        self.saved = True
        await interaction.response.send_message("Saved.", ephemeral=True)
