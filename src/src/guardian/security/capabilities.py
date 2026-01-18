from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import discord

from .auth import get_application_owner_ids

log = logging.getLogger("guardian.security.capabilities")


@dataclass(frozen=True)
class CapabilityResolution:
    guild_id: int
    user_id: int
    revision: Optional[int]
    capabilities: frozenset[str]
    # Minimal explainability that stays stable and machine-readable.
    sources: tuple[str, ...]


def _normalize_caps(items: Any) -> list[str]:
    if items is None:
        return []
    if isinstance(items, str):
        return [items]
    if isinstance(items, list):
        return [x for x in items if isinstance(x, str) and x]
    return []


def _match_any(patterns: frozenset[str], cap: str) -> bool:
    # Exact match is fast path.
    if cap in patterns:
        return True
    # Support wildcard patterns like "moderation.*".
    for p in patterns:
        if "*" in p or "?" in p or "[" in p:
            if fnmatch.fnmatchcase(cap, p):
                return True
    return False


def has_cap(resolution: CapabilityResolution, cap: str) -> bool:
    return _match_any(resolution.capabilities, cap)


async def resolve_capabilities(
    *,
    bot: discord.Client,
    member: discord.Member,
    require_config: bool = False,
) -> CapabilityResolution:
    """Resolve effective capabilities for a member.

    Authority is derived-only:
    - Root actors get "*" (all capabilities).
    - Published moderation config may define an `authz` section:
      - role_capabilities: {"<role_id>": ["cap", ...]}
      - discord_permission_capabilities: {"administrator": ["cap", ...], ...}
    - If config is unavailable and require_config=False, the result is empty.
    """

    guild = member.guild
    guild_id = int(guild.id)
    user_id = int(member.id)

    # Root short-circuit (derived truth only).
    try:
        if int(guild.owner_id) == user_id:
            return CapabilityResolution(guild_id=guild_id, user_id=user_id, revision=None, capabilities=frozenset({"*"}), sources=("guild_owner",))

        owner_ids = await get_application_owner_ids(bot)  # includes team members
        if user_id in owner_ids:
            return CapabilityResolution(guild_id=guild_id, user_id=user_id, revision=None, capabilities=frozenset({"*"}), sources=("app_owner",))

        root_store = getattr(bot, "root_store", None)
        if root_store is not None:
            if await root_store.is_root(user_id):
                return CapabilityResolution(guild_id=guild_id, user_id=user_id, revision=None, capabilities=frozenset({"*"}), sources=("root_store",))
    except Exception:
        # Root resolution failures must not grant privileges.
        pass

    rev: Optional[int] = None
    doc: Optional[Mapping[str, Any]] = None
    sources: list[str] = []

    store = getattr(bot, "moderation_config_store", None)
    if store is not None:
        try:
            rev, doc = await store.get_published(guild_id)
        except Exception as e:
            log.warning("capabilities: failed to read published config for guild %s: %s", guild_id, e)

    if doc is None:
        if require_config:
            return CapabilityResolution(guild_id=guild_id, user_id=user_id, revision=None, capabilities=frozenset(), sources=("no_config",))
        return CapabilityResolution(guild_id=guild_id, user_id=user_id, revision=None, capabilities=frozenset(), sources=())

    authz = doc.get("authz") if isinstance(doc, Mapping) else None
    if not isinstance(authz, Mapping):
        return CapabilityResolution(guild_id=guild_id, user_id=user_id, revision=rev, capabilities=frozenset(), sources=("config_no_authz",))

    cap_set: set[str] = set()

    role_caps = authz.get("role_capabilities")
    if isinstance(role_caps, Mapping):
        # Roles are keyed by role_id (string or int).
        for role in member.roles:
            key_str = str(int(role.id))
            items = role_caps.get(key_str)
            if items is None:
                items = role_caps.get(int(role.id))
            caps = _normalize_caps(items)
            if caps:
                cap_set.update(caps)
                sources.append(f"role:{role.id}")

    perm_caps = authz.get("discord_permission_capabilities")
    if isinstance(perm_caps, Mapping):
        gp = member.guild_permissions
        # Only map a small, stable subset.
        perm_map = {
            "administrator": gp.administrator,
            "manage_guild": gp.manage_guild,
            "manage_roles": gp.manage_roles,
            "manage_channels": gp.manage_channels,
            "manage_messages": gp.manage_messages,
            "kick_members": gp.kick_members,
            "ban_members": gp.ban_members,
            "moderate_members": getattr(gp, "moderate_members", False),
        }
        for pname, enabled in perm_map.items():
            if not enabled:
                continue
            caps = _normalize_caps(perm_caps.get(pname))
            if caps:
                cap_set.update(caps)
                sources.append(f"perm:{pname}")

    # Always include a stable baseline to avoid empty-resolution surprises.
    baseline = _normalize_caps(authz.get("baseline_capabilities"))
    if baseline:
        cap_set.update(baseline)
        sources.append("baseline")

    return CapabilityResolution(
        guild_id=guild_id,
        user_id=user_id,
        revision=rev,
        capabilities=frozenset(cap_set),
        sources=tuple(sorted(set(sources))),
    )
