from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# Discord limits
MAX_MESSAGE_LENGTH: Final[int] = 4000
MAX_EMBED_DESCRIPTION: Final[int] = 4096
MAX_EMBED_TITLE: Final[int] = 256
MAX_FIELD_NAME: Final[int] = 256
MAX_FIELD_VALUE: Final[int] = 1024
MAX_FIELDS_PER_EMBED: Final[int] = 25

# Bot configuration
DEFAULT_TIMEOUT_SECONDS: Final[int] = 300
LONG_TIMEOUT_SECONDS: Final[int] = 600
CACHE_TTL_SECONDS: Final[int] = 120

# Colors (hex values)
COLORS = {
    "default": 0x5865F2,
    "success": 0x57F287,
    "warning": 0xF1C40F,
    "error": 0xED4245,
    "info": 0x3498DB,
    "muted": 0x4F545C,
    "quarantine": 0x2F3136,
}

# Role kinds
ROLE_KINDS = {
    "bot",
    "staff", 
    "system",
    "access",
    "level",
    "ping",
    "interest",
    "platform",
    "timezone",
    "status",
}

# Channel kinds
CHANNEL_KINDS = {
    "text",
    "voice",
}

# Permission presets
@dataclass(frozen=True)
class PermissionPreset:
    view: bool
    send: bool
    history: bool = True
    reactions: bool = True
    threads: bool = True

PERMISSION_PRESETS = {
    "full": PermissionPreset(True, True),
    "read_only": PermissionPreset(True, False),
    "none": PermissionPreset(False, False),
}

# Error messages
ERROR_MESSAGES = {
    "missing_permissions": "You don't have permission to use this command.",
    "invalid_user": "User not found.",
    "invalid_channel": "Channel not found.",
    "database_error": "A database error occurred. Please try again later.",
    "invalid_configuration": "Invalid configuration provided.",
}

# Success messages
SUCCESS_MESSAGES = {
    "operation_completed": "Operation completed successfully.",
    "configuration_saved": "Configuration saved successfully.",
    "data_updated": "Data updated successfully.",
}
