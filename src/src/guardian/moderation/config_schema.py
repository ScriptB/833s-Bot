from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


DEFAULT_CONFIG_VERSION = 1


def default_config() -> dict[str, Any]:
    """Default moderation config.

    Document model:
    - guild_settings: global knobs
    - rules: ordered rules (priority + stop/continue)
    """

    return {
        "version": DEFAULT_CONFIG_VERSION,
        "guild_settings": {
            "enabled": True,
            "dm_notify": True,
            "modlog_channel_id": None,
            "quarantine_role_id": None,
        },
        "rules": [
            {
                "id": "spam_mentions",
                "name": "Mention spam",
                "enabled": True,
                "priority": 100,
                "event_types": ["message_create"],
                "scope": {
                    "allow_roles": [],
                    "allow_channels": [],
                    "block_channels": [],
                },
                "conditions": {
                    "mention_count_gte": 6,
                },
                "actions": [
                    {"type": "delete_message", "params": {}},
                    {"type": "timeout", "params": {"minutes": 10}},
                    {"type": "warn", "params": {"reason": "Too many mentions"}},
                ],
                "stop": True,
            },
            {
                "id": "invite_filter",
                "name": "Invite filtering",
                "enabled": True,
                "priority": 90,
                "event_types": ["message_create"],
                "scope": {"allow_roles": [], "allow_channels": [], "block_channels": []},
                "conditions": {
                    "contains_invite": True,
                },
                "actions": [
                    {"type": "delete_message", "params": {}},
                    {"type": "warn", "params": {"reason": "Invite links are not allowed"}},
                ],
                "stop": True,
            },
        ],
    }


INVITE_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9-]+", re.I)


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str


def _is_jsonable(obj: Any) -> bool:
    try:
        json.dumps(obj)
        return True
    except Exception:
        return False


def validate_config(doc: dict[str, Any]) -> list[ValidationIssue]:
    """Validate config. Returns list of issues; empty means valid."""

    issues: list[ValidationIssue] = []
    if not isinstance(doc, dict):
        return [ValidationIssue(path="$", message="Config must be an object")]

    if doc.get("version") != DEFAULT_CONFIG_VERSION:
        issues.append(ValidationIssue(path="$.version", message=f"Unsupported version (expected {DEFAULT_CONFIG_VERSION})"))

    gs = doc.get("guild_settings")
    if not isinstance(gs, dict):
        issues.append(ValidationIssue(path="$.guild_settings", message="guild_settings must be an object"))
    else:
        if not isinstance(gs.get("enabled", True), bool):
            issues.append(ValidationIssue(path="$.guild_settings.enabled", message="enabled must be boolean"))
        if not isinstance(gs.get("dm_notify", True), bool):
            issues.append(ValidationIssue(path="$.guild_settings.dm_notify", message="dm_notify must be boolean"))
        for k in ("modlog_channel_id", "quarantine_role_id"):
            v = gs.get(k)
            if v is not None and not isinstance(v, int):
                issues.append(ValidationIssue(path=f"$.guild_settings.{k}", message="must be integer or null"))

    rules = doc.get("rules")
    if not isinstance(rules, list):
        issues.append(ValidationIssue(path="$.rules", message="rules must be a list"))
        return issues

    seen_ids: set[str] = set()
    for i, r in enumerate(rules):
        pfx = f"$.rules[{i}]"
        if not isinstance(r, dict):
            issues.append(ValidationIssue(path=pfx, message="rule must be an object"))
            continue
        rid = r.get("id")
        if not isinstance(rid, str) or not rid:
            issues.append(ValidationIssue(path=pfx + ".id", message="id must be non-empty string"))
        elif rid in seen_ids:
            issues.append(ValidationIssue(path=pfx + ".id", message="duplicate rule id"))
        else:
            seen_ids.add(rid)

        if not isinstance(r.get("name"), str) or not r.get("name"):
            issues.append(ValidationIssue(path=pfx + ".name", message="name must be non-empty string"))

        if not isinstance(r.get("enabled", True), bool):
            issues.append(ValidationIssue(path=pfx + ".enabled", message="enabled must be boolean"))

        pr = r.get("priority")
        if not isinstance(pr, int):
            issues.append(ValidationIssue(path=pfx + ".priority", message="priority must be integer"))

        ets = r.get("event_types")
        if not isinstance(ets, list) or not all(isinstance(x, str) for x in ets):
            issues.append(ValidationIssue(path=pfx + ".event_types", message="event_types must be list[str]"))

        cond = r.get("conditions")
        if cond is None:
            issues.append(ValidationIssue(path=pfx + ".conditions", message="conditions required"))
        elif not isinstance(cond, dict):
            issues.append(ValidationIssue(path=pfx + ".conditions", message="conditions must be object"))
        else:
            # Regex limit: protect against catastrophic patterns by length and compile test.
            rx = cond.get("regex")
            if rx is not None:
                if not isinstance(rx, str) or len(rx) > 256:
                    issues.append(ValidationIssue(path=pfx + ".conditions.regex", message="regex must be string <=256 chars"))
                else:
                    try:
                        re.compile(rx)
                    except re.error as e:
                        issues.append(ValidationIssue(path=pfx + ".conditions.regex", message=f"invalid regex: {e}"))

        acts = r.get("actions")
        if not isinstance(acts, list) or not acts:
            issues.append(ValidationIssue(path=pfx + ".actions", message="actions must be non-empty list"))
        else:
            for j, a in enumerate(acts):
                ap = f"{pfx}.actions[{j}]"
                if not isinstance(a, dict):
                    issues.append(ValidationIssue(path=ap, message="action must be object"))
                    continue
                if not isinstance(a.get("type"), str) or not a.get("type"):
                    issues.append(ValidationIssue(path=ap + ".type", message="type required"))
                if "params" in a and not isinstance(a.get("params"), dict):
                    issues.append(ValidationIssue(path=ap + ".params", message="params must be object"))

        if not _is_jsonable(r):
            issues.append(ValidationIssue(path=pfx, message="rule must be JSON serializable"))

    if not _is_jsonable(doc):
        issues.append(ValidationIssue(path="$", message="config must be JSON serializable"))
    return issues
