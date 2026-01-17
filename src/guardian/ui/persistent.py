"""Persistent view registration.

discord.py requires persistent Views (timeout=None) to be registered on startup so
their callbacks remain available after restarts.

This module intentionally does NOT define placeholder views. All persistent views
are imported from the cogs that implement the callbacks.
"""

from __future__ import annotations

import logging

import discord

log = logging.getLogger("guardian.ui.persistent")


# Stable custom_id namespace
GUARDIAN_V1 = "guardian:v1"


def register_all_views(bot: discord.Client) -> None:
    """Register persistent views with the bot.

    Note: message-specific reattachment (bot.add_view(..., message_id=...)) is
    handled by each cog that owns the panel, because only that cog knows which
    guild/message IDs are relevant.
    """

    results = {
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "failures": [],
    }

    def _try_register(view_name: str, view_factory) -> None:
        results["attempted"] += 1
        try:
            bot.add_view(view_factory())
            results["succeeded"] += 1
            log.info("✅ Registered persistent %s", view_name)
        except Exception as exc:  # noqa: BLE001
            results["failed"] += 1
            msg = f"❌ Failed to register {view_name}: {type(exc).__name__}: {exc}"
            results["failures"].append(msg)
            log.warning(msg)

    # Verification panel
    from ..cogs.verify_panel import VerifyView as VerifyPanelView

    _try_register("VerifyView", VerifyPanelView)

    # Ticket panel
    from ..ui.tickets import TicketCreateView

    # TicketCreateView needs (bot, guild_id). We register a guild_id=0 instance
    # to keep the callbacks live; the cog will reattach per-message with the
    # correct guild_id.
    _try_register("TicketCreateView", lambda: TicketCreateView(bot, 0))

    bot._persistent_views_registered = results["succeeded"] > 0
    bot._persistent_views_stats = results

    log.info(
        "📊 Persistent Views Registration Summary: attempted=%d succeeded=%d failed=%d",
        results["attempted"],
        results["succeeded"],
        results["failed"],
    )
