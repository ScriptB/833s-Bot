from __future__ import annotations

"""Persistent UI registration.

In discord.py, component interactions are dispatched to the *registered* View
for a given custom_id. Registering placeholder views (with empty callbacks)
breaks buttons after restarts.

Policy:
- Register only real, stateless persistent views whose callbacks are implemented.
- Views that depend on per-guild dynamic configuration (role menus) are restored
  by their owning cogs via PanelStore message_id rehydration.
"""

import logging
import discord

log = logging.getLogger("guardian.ui.persistent")

# Stable namespace for custom_id
GUARDIAN_V1 = "guardian:v1"


def _import_and_create(module_name: str, class_name: str):
    module = __import__(module_name, fromlist=[class_name])
    view_class = getattr(module, class_name)
    return view_class()


def _validate_persistent_view(view: discord.ui.View) -> None:
    """Validate a view meets discord.py's persistence requirements.

    discord.py requirement: timeout=None and every component has an explicit custom_id.
    """
    if view.timeout is not None:
        raise ValueError("Persistent view must have timeout=None")
    for item in getattr(view, "children", []):
        cid = getattr(item, "custom_id", None)
        if not cid:
            raise ValueError("Persistent view components must have custom_id")
        if len(str(cid)) > 100:
            raise ValueError("custom_id must be <= 100 characters")


def register_all_views(bot: discord.Client) -> None:
    """Register persistent views that must survive restarts.

    Note: dynamic per-guild views (eg. role panels) are restored by the
    PanelStore repair step and by their owning cogs.
    """

    results = {
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "failures": [],
    }

    # Only register views with implemented callbacks.
    views_to_register = [
        ("VerifyPanel.VerifyView", lambda: _import_and_create("guardian.cogs.verify_panel", "VerifyView")),
        ("TicketSystem.TicketView", lambda: _import_and_create("guardian.cogs.ticket_system", "TicketView")),
        ("TicketSystem.TicketControlView", lambda: _import_and_create("guardian.cogs.ticket_system", "TicketControlView")),
    ]

    for name, factory in views_to_register:
        results["attempted"] += 1
        try:
            view = factory()
            _validate_persistent_view(view)
            bot.add_view(view)
            results["succeeded"] += 1
            log.info("✅ Registered persistent view: %s", name)
        except Exception as e:
            results["failed"] += 1
            msg = f"❌ Failed to register {name}: {type(e).__name__}: {e}"
            results["failures"].append(msg)
            log.warning(msg)

    bot._persistent_views_registered = results["failed"] == 0
    bot._persistent_views_stats = results
    log.info(
        "📊 Persistent view registration: %s/%s successful",
        results["succeeded"],
        results["attempted"],
    )
