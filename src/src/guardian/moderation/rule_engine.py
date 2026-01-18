from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .config_schema import INVITE_RE
from .models import ModAction, ModDecision, ModEvent, RuleHit


@dataclass(frozen=True)
class CompiledRule:
    id: str
    name: str
    enabled: bool
    priority: int
    event_types: set[str]
    scope: dict[str, list[int]]
    conditions: dict[str, Any]
    actions: list[ModAction]
    stop: bool


@dataclass(frozen=True)
class CompiledRuleset:
    guild_id: int
    revision: int
    fingerprint: str
    guild_settings: dict[str, Any]
    rules: list[CompiledRule]


def _fingerprint(doc: dict[str, Any]) -> str:
    h = hashlib.sha256(repr(doc).encode("utf-8")).hexdigest()
    return h[:16]


def compile_ruleset(guild_id: int, revision: int, doc: dict[str, Any]) -> CompiledRuleset:
    gs = doc.get("guild_settings") or {}
    compiled: list[CompiledRule] = []

    for r in (doc.get("rules") or []):
        if not isinstance(r, dict):
            continue
        actions: list[ModAction] = []
        for a in r.get("actions") or []:
            if isinstance(a, dict) and isinstance(a.get("type"), str):
                actions.append(ModAction(action_type=a["type"], params=dict(a.get("params") or {})))
        compiled.append(
            CompiledRule(
                id=str(r.get("id")),
                name=str(r.get("name")),
                enabled=bool(r.get("enabled", True)),
                priority=int(r.get("priority", 0)),
                event_types=set(str(x) for x in (r.get("event_types") or [])),
                scope={
                    "allow_roles": [int(x) for x in (r.get("scope") or {}).get("allow_roles", []) if isinstance(x, int)],
                    "allow_channels": [int(x) for x in (r.get("scope") or {}).get("allow_channels", []) if isinstance(x, int)],
                    "block_channels": [int(x) for x in (r.get("scope") or {}).get("block_channels", []) if isinstance(x, int)],
                },
                conditions=dict(r.get("conditions") or {}),
                actions=actions,
                stop=bool(r.get("stop", False)),
            )
        )

    compiled.sort(key=lambda x: x.priority, reverse=True)
    return CompiledRuleset(
        guild_id=guild_id,
        revision=revision,
        fingerprint=_fingerprint(doc),
        guild_settings=dict(gs),
        rules=compiled,
    )


def _cond_contains_invite(content: str) -> bool:
    return bool(INVITE_RE.search(content))


def evaluate_ruleset(
    ruleset: CompiledRuleset,
    event: ModEvent,
    *,
    member_role_ids: Optional[list[int]] = None,
) -> list[RuleHit]:
    """Evaluate rules deterministically.

    allowlist precedence:
    - if user has allow_roles: rule is skipped (treated as allow)
    - if channel is allow_channels: rule applies
    - if channel is block_channels: rule is skipped
    """

    hits: list[RuleHit] = []
    member_role_ids = member_role_ids or []

    for rule in ruleset.rules:
        if not rule.enabled:
            continue
        if event.event_type not in rule.event_types:
            continue

        # Scope resolution
        if any(rid in member_role_ids for rid in rule.scope.get("allow_roles", [])):
            continue
        if event.channel_id is not None:
            if event.channel_id in rule.scope.get("block_channels", []):
                continue
            allow_channels = rule.scope.get("allow_channels", [])
            if allow_channels and event.channel_id not in allow_channels:
                # rule is scoped to a subset and this channel isn't in it
                continue

        # Conditions
        content = event.content or ""
        cond = rule.conditions
        reason = None

        mention_gte = cond.get("mention_count_gte")
        if mention_gte is not None:
            try:
                m = int(event.meta.get("mention_count", 0) if event.meta else 0)
                if m < int(mention_gte):
                    continue
                reason = f"mention_count>={mention_gte}"
            except Exception:
                continue

        if cond.get("contains_invite") is True:
            if not _cond_contains_invite(content):
                continue
            reason = "contains_invite"

        regex = cond.get("regex")
        if regex is not None:
            import re

            try:
                if not re.search(str(regex), content, re.I):
                    continue
                reason = "regex"
            except re.error:
                continue

        # Empty conditions means rule would always match; we treat as invalid and skip.
        if not cond:
            continue

        hits.append(
            RuleHit(
                rule_id=rule.id,
                rule_name=rule.name,
                priority=rule.priority,
                reason=reason or "matched",
                actions=rule.actions,
                stop=rule.stop,
            )
        )
        if rule.stop:
            break

    return hits


def collapse_actions(hits: list[RuleHit]) -> list[ModAction]:
    actions: list[ModAction] = []
    for hit in hits:
        actions.extend(hit.actions)
        if hit.stop:
            break
    return actions
