"""
Overhaul Template Specification

Single source of truth for the server structure.
Used by creation, validation, and reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional


class ChannelKind(Enum):
    """Channel type enumeration."""
    TEXT = "text"
    VOICE = "voice"


@dataclass
class ChannelSpec:
    """Channel specification."""
    name: str
    kind: ChannelKind
    read_only: bool = False
    staff_only: bool = False


@dataclass
class CategorySpec:
    """Category specification."""
    name: str
    channels: List[ChannelSpec]
    visibility: Dict[str, bool]  # role_name -> can_view
    position: int


# Canonical emoji template - EXACT names must be used
CANONICAL_TEMPLATE: List[CategorySpec] = [
    CategorySpec(
        name="🛂 VERIFY GATE",
        channels=[
            ChannelSpec("🧩 verify", ChannelKind.TEXT)
        ],
        visibility={"@everyone": True, "Verified": False, "staff": True},
        position=0
    ),
    CategorySpec(
        name="📢 START",
        channels=[
            ChannelSpec("👋 welcome", ChannelKind.TEXT),
            ChannelSpec("📜 rules", ChannelKind.TEXT),
            ChannelSpec("📣 announcements", ChannelKind.TEXT, read_only=True),
            ChannelSpec("ℹ️ server-info", ChannelKind.TEXT)
        ],
        visibility={"@everyone": True},
        position=1
    ),
    CategorySpec(
        name="💬 GENERAL",
        channels=[
            ChannelSpec("💬 general-chat", ChannelKind.TEXT),
            ChannelSpec("🖼️ media", ChannelKind.TEXT),
            ChannelSpec("👋 introductions", ChannelKind.TEXT),
            ChannelSpec("🧃 off-topic", ChannelKind.TEXT),
            ChannelSpec("🔊 general-voice", ChannelKind.VOICE),
            ChannelSpec("🎧 chill-voice", ChannelKind.VOICE)
        ],
        visibility={"@everyone": False, "Verified": True, "Member": True, "staff": True},
        position=2
    ),
    CategorySpec(
        name="🎮 GAME HUB",
        channels=[
            ChannelSpec("🎯 choose-your-games", ChannelKind.TEXT),
            ChannelSpec("📋 game-rules", ChannelKind.TEXT)
        ],
        visibility={"@everyone": False, "Verified": True, "Member": True, "staff": True},
        position=3
    ),
    CategorySpec(
        name="🧩 🎮 ROBLOX",
        channels=[
            ChannelSpec("💬 roblox-chat", ChannelKind.TEXT),
            ChannelSpec("🐝 bee-swarm", ChannelKind.TEXT),
            ChannelSpec("🔁 trading", ChannelKind.TEXT),
            ChannelSpec("🔊 roblox-voice", ChannelKind.VOICE)
        ],
        visibility={"@everyone": False, "Roblox": True, "staff": True},
        position=4
    ),
    CategorySpec(
        name="🧩 ⛏️ MINECRAFT",
        channels=[
            ChannelSpec("💬 mc-chat", ChannelKind.TEXT),
            ChannelSpec("🌍 servers", ChannelKind.TEXT),
            ChannelSpec("🧱 builds", ChannelKind.TEXT),
            ChannelSpec("🔊 mc-voice", ChannelKind.VOICE)
        ],
        visibility={"@everyone": False, "Minecraft": True, "staff": True},
        position=5
    ),
    CategorySpec(
        name="🧩 🦖 ARK",
        channels=[
            ChannelSpec("💬 ark-chat", ChannelKind.TEXT),
            ChannelSpec("🦕 tames", ChannelKind.TEXT),
            ChannelSpec("🥚 breeding", ChannelKind.TEXT),
            ChannelSpec("🔊 ark-voice", ChannelKind.VOICE)
        ],
        visibility={"@everyone": False, "ARK": True, "staff": True},
        position=6
    ),
    CategorySpec(
        name="🧩 🔫 FPS GAMES",
        channels=[
            ChannelSpec("💬 fps-chat", ChannelKind.TEXT),
            ChannelSpec("🎥 clips", ChannelKind.TEXT),
            ChannelSpec("🎯 lfg", ChannelKind.TEXT),
            ChannelSpec("🔊 fps-voice", ChannelKind.VOICE)
        ],
        visibility={"@everyone": False, "FPS": True, "staff": True},
        position=7
    ),
    CategorySpec(
        name="🧩 💻 CODING LAB",
        channels=[
            ChannelSpec("💬 dev-chat", ChannelKind.TEXT),
            ChannelSpec("📂 project-logs", ChannelKind.TEXT),
            ChannelSpec("🧩 snippets", ChannelKind.TEXT),
            ChannelSpec("🐞 bug-reports", ChannelKind.TEXT),
            ChannelSpec("🚀 releases", ChannelKind.TEXT),
            ChannelSpec("🔍 code-review", ChannelKind.TEXT),
            ChannelSpec("🔊 dev-voice", ChannelKind.VOICE)
        ],
        visibility={"@everyone": False, "Coding": True, "staff": True},
        position=8
    ),
    CategorySpec(
        name="🧩 🐍 SNAKES & PETS",
        channels=[
            ChannelSpec("🐍 snake-care", ChannelKind.TEXT),
            ChannelSpec("🥩 feeding-logs", ChannelKind.TEXT),
            ChannelSpec("🏗️ enclosure-builds", ChannelKind.TEXT),
            ChannelSpec("🩺 health-help", ChannelKind.TEXT),
            ChannelSpec("📸 pet-photos", ChannelKind.TEXT),
            ChannelSpec("🩹 vet-advice", ChannelKind.TEXT),
            ChannelSpec("🔊 snake-voice", ChannelKind.VOICE)
        ],
        visibility={"@everyone": False, "Snakes": True, "staff": True},
        position=9
    ),
    CategorySpec(
        name="🆘 SUPPORT",
        channels=[
            ChannelSpec("🆘 help", ChannelKind.TEXT),
            ChannelSpec("🎫 tickets", ChannelKind.TEXT),
            ChannelSpec("📖 faq", ChannelKind.TEXT),
            ChannelSpec("📑 support-logs", ChannelKind.TEXT, staff_only=True)
        ],
        visibility={"@everyone": False, "Verified": True, "Member": True, "staff": True},
        position=10
    ),
    CategorySpec(
        name="🛡️ STAFF",
        channels=[
            ChannelSpec("💬 staff-chat", ChannelKind.TEXT),
            ChannelSpec("📜 mod-logs", ChannelKind.TEXT),
            ChannelSpec("🗂️ case-notes", ChannelKind.TEXT),
            ChannelSpec("⚖️ appeals", ChannelKind.TEXT),
            ChannelSpec("🛠️ admin-console", ChannelKind.TEXT)
        ],
        visibility={"@everyone": False, "Owner": True, "Admin": True, "Moderator": True, "Support": True, "Bots": True},
        position=11
    ),
    CategorySpec(
        name="🔊 VOICE LOUNGE",
        channels=[
            ChannelSpec("🗣️ hangout", ChannelKind.VOICE),
            ChannelSpec("💻 coding-vc", ChannelKind.VOICE),
            ChannelSpec("🔒 private-1", ChannelKind.VOICE),
            ChannelSpec("🔒 private-2", ChannelKind.VOICE)
        ],
        visibility={"@everyone": False, "Verified": True, "Member": True, "staff": True},
        position=12
    )
]

# Role definitions
ROLE_DEFINITIONS = {
    "Owner": {"position": 10, "administrator": True},
    "Admin": {"position": 9, "administrator": True},
    "Moderator": {"position": 8, "permissions": ["kick_members", "ban_members", "manage_channels", "manage_messages"]},
    "Support": {"position": 7, "permissions": ["manage_messages"]},
    "Bots": {"position": 6, "permissions": []},
    "Verified": {"position": 5, "permissions": []},
    "Member": {"position": 4, "permissions": []},
    "Muted": {"position": 1, "permissions": []},
    "Coding": {"position": 3, "permissions": []},
    "Snakes": {"position": 3, "permissions": []},
    "Roblox": {"position": 3, "permissions": []},
    "Minecraft": {"position": 3, "permissions": []},
    "ARK": {"position": 3, "permissions": []},
    "FPS": {"position": 3, "permissions": []},
}

# Staff role list for permission calculations
STAFF_ROLES = ["Owner", "Admin", "Moderator", "Support", "Bots"]

# Bot role ID to preserve
BOT_ROLE_ID = 1458781063185829964
