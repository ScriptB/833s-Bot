from __future__ import annotations

import re
from typing import Iterable, Optional, TypeVar

import discord

T = TypeVar("T")


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_discord_name(name: str) -> str:
    """Normalize a Discord object name for fuzzy matching.

    Examples:
    - "📜 rules" -> "rules"
    - "🛂 VERIFY GATE" -> "verify-gate"
    - "general_chat" -> "general-chat"
    """
    s = (name or "").strip().lower()
    # Replace whitespace/underscores with separators, then remove other punctuation.
    s = s.replace("_", " ")
    s = _NON_ALNUM_RE.sub(" ", s)
    parts = [p for p in s.split() if p]
    if not parts:
        return ""
    # Strip leading tokens that are commonly emoji names or short markers
    # e.g. "snake" in "🐍 snake-care" should remain; emoji itself becomes empty.
    # Since emoji are removed by the regex, this is mostly about leftover markers.
    normalized = "-".join(parts)
    return normalized


def _best_name_match(candidates: Iterable[T], target: str, *, attr: str = "name") -> Optional[T]:
    t_norm = normalize_discord_name(target)
    if not t_norm:
        return None
    best: Optional[T] = None
    for c in candidates:
        name = getattr(c, attr, "") or ""
        if normalize_discord_name(name) == t_norm:
            return c
        # Fallback: allow suffix match for emoji-prefixed names that normalize extra tokens
        if normalize_discord_name(name).endswith(t_norm):
            best = best or c
    return best


def find_text_channel(guild: discord.Guild, target: str) -> Optional[discord.TextChannel]:
    # Exact first
    ch = discord.utils.get(guild.text_channels, name=target)
    if ch:
        return ch
    return _best_name_match(guild.text_channels, target)


def find_voice_channel(guild: discord.Guild, target: str) -> Optional[discord.VoiceChannel]:
    vc = discord.utils.get(guild.voice_channels, name=target)
    if vc:
        return vc
    return _best_name_match(guild.voice_channels, target)


def find_category(guild: discord.Guild, target: str) -> Optional[discord.CategoryChannel]:
    cat = discord.utils.get(guild.categories, name=target)
    if cat:
        return cat
    return _best_name_match(guild.categories, target)


def find_role(guild: discord.Guild, target: str) -> Optional[discord.Role]:
    role = discord.utils.get(guild.roles, name=target)
    if role:
        return role
    return _best_name_match(guild.roles, target)
