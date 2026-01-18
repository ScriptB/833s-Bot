from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Optional


EventType = Literal[
    "message_create",
    "member_join",
    "member_update",
]


@dataclass(frozen=True)
class ModEvent:
    """Normalized event passed through the moderation pipeline."""

    guild_id: int
    event_type: EventType
    created_at: datetime
    # Actor / subject
    user_id: int
    channel_id: Optional[int] = None
    message_id: Optional[int] = None
    content: Optional[str] = None
    # Extra structured metadata
    meta: dict[str, Any] | None = None


ActionType = Literal[
    "warn",
    "timeout",
    "kick",
    "ban",
    "tempban",
    "delete_message",
    "lock_channel",
    "slowmode",
    "quarantine",
    "notify_dm",
    "notify_channel",
    "create_ticket",
]


@dataclass(frozen=True)
class ModAction:
    action_type: ActionType
    params: dict[str, Any]


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    rule_name: str
    priority: int
    reason: str
    actions: list[ModAction]
    stop: bool = False


@dataclass(frozen=True)
class ModDecision:
    correlation_id: str
    event: ModEvent
    hits: list[RuleHit]
    # Derived:
    actions: list[ModAction]


@dataclass(frozen=True)
class ExecuteResult:
    correlation_id: str
    ok: bool
    attempted: int
    executed: int
    skipped_idempotent: int
    failed: int
    errors: list[str]
