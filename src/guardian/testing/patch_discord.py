from __future__ import annotations

import inspect
from functools import wraps
from typing import Any

import discord

from .dryrun import is_dry_run

# Store original methods
_original_methods = {}
_side_effects_log: list[dict[str, Any]] = []

def _log_side_effect(method_name: str, args: tuple, kwargs: dict) -> None:
    """Log a side effect that was intercepted."""
    # Sanitize args for logging
    sanitized_args = []
    for arg in args:
        if hasattr(arg, 'id'):
            sanitized_args.append(f"<{type(arg).__name__} id={arg.id}>")
        else:
            sanitized_args.append(repr(arg))
    
    sanitized_kwargs = {}
    for key, value in kwargs.items():
        if hasattr(value, 'id'):
            sanitized_kwargs[key] = f"<{type(value).__name__} id={value.id}>"
        else:
            sanitized_kwargs[key] = repr(value)
    
    _side_effects_log.append({
        'method': method_name,
        'args': sanitized_args,
        'kwargs': sanitized_kwargs
    })

def _validate_signature(original_func, args: tuple, kwargs: dict) -> None:
    """Validate that args/kwargs match the original function signature."""
    try:
        sig = inspect.signature(original_func)
        sig.bind_partial(*args, **kwargs)  # Use bind_partial to allow partial binding
    except TypeError as e:
        raise TypeError(f"Invalid arguments for {original_func.__name__}: {e}") from e

def _create_noop_method(original_func: Any, method_name: str) -> Any:
    """Create a no-op version of a method that validates arguments and logs side effects."""
    
    @wraps(original_func)
    async def async_noop(*args, **kwargs):
        if not is_dry_run():
            return await original_func(*args, **kwargs)
        
        # Validate signature
        _validate_signature(original_func, args, kwargs)
        
        # Log the side effect
        _log_side_effect(method_name, args, kwargs)
        
        # Return dummy objects for create_* methods
        if method_name.startswith('create_'):
            return _create_dummy_object(method_name)
        
        return None
    
    @wraps(original_func)
    def sync_noop(*args, **kwargs):
        if not is_dry_run():
            return original_func(*args, **kwargs)
        
        # Validate signature
        _validate_signature(original_func, args, kwargs)
        
        # Log the side effect
        _log_side_effect(method_name, args, kwargs)
        
        # Return dummy objects for create_* methods
        if method_name.startswith('create_'):
            return _create_dummy_object(method_name)
        
        return None
    
    return async_noop if inspect.iscoroutinefunction(original_func) else sync_noop

def _create_dummy_object(method_name: str) -> Any:
    """Create a dummy object for create_* methods."""
    if 'channel' in method_name.lower():
        return FakeTextChannel(id=999999, name="dummy_channel")
    elif 'role' in method_name.lower():
        return FakeRole(id=999999, name="dummy_role")
    elif 'category' in method_name.lower():
        return FakeCategory(id=999999, name="dummy_category")
    else:
        return None

def get_side_effects_log() -> list[dict[str, Any]]:
    """Get the current side effects log."""
    return _side_effects_log.copy()

def clear_side_effects_log() -> None:
    """Clear the side effects log."""
    _side_effects_log.clear()

def patch_discord_methods() -> None:
    """Patch Discord methods to intercept side effects during dry runs."""
    if _original_methods:
        return  # Already patched
    
    # Guild methods
    _original_methods['Guild.edit'] = discord.Guild.edit
    discord.Guild.edit = _create_noop_method(_original_methods['Guild.edit'], 'Guild.edit')
    
    _original_methods['Guild.create_text_channel'] = discord.Guild.create_text_channel
    discord.Guild.create_text_channel = _create_noop_method(
        _original_methods['Guild.create_text_channel'], 'Guild.create_text_channel'
    )
    
    _original_methods['Guild.create_voice_channel'] = discord.Guild.create_voice_channel
    discord.Guild.create_voice_channel = _create_noop_method(
        _original_methods['Guild.create_voice_channel'], 'Guild.create_voice_channel'
    )
    
    _original_methods['Guild.create_category'] = discord.Guild.create_category
    discord.Guild.create_category = _create_noop_method(
        _original_methods['Guild.create_category'], 'Guild.create_category'
    )
    
    _original_methods['Guild.create_role'] = discord.Guild.create_role
    discord.Guild.create_role = _create_noop_method(
        _original_methods['Guild.create_role'], 'Guild.create_role'
    )
    
    # Channel methods
    _original_methods['abc.GuildChannel.delete'] = discord.abc.GuildChannel.delete
    discord.abc.GuildChannel.delete = _create_noop_method(
        _original_methods['abc.GuildChannel.delete'], 'abc.GuildChannel.delete'
    )
    
    _original_methods['abc.GuildChannel.edit'] = discord.abc.GuildChannel.edit
    discord.abc.GuildChannel.edit = _create_noop_method(
        _original_methods['abc.GuildChannel.edit'], 'abc.GuildChannel.edit'
    )
    
    _original_methods['abc.GuildChannel.set_permissions'] = discord.abc.GuildChannel.set_permissions
    discord.abc.GuildChannel.set_permissions = _create_noop_method(
        _original_methods['abc.GuildChannel.set_permissions'], 'abc.GuildChannel.set_permissions'
    )
    
    # Member methods
    _original_methods['Member.add_roles'] = discord.Member.add_roles
    discord.Member.add_roles = _create_noop_method(
        _original_methods['Member.add_roles'], 'Member.add_roles'
    )
    
    _original_methods['Member.remove_roles'] = discord.Member.remove_roles
    discord.Member.remove_roles = _create_noop_method(
        _original_methods['Member.remove_roles'], 'Member.remove_roles'
    )
    
    _original_methods['Member.edit'] = discord.Member.edit
    discord.Member.edit = _create_noop_method(
        _original_methods['Member.edit'], 'Member.edit'
    )
    
    # Role methods
    _original_methods['Role.edit'] = discord.Role.edit
    discord.Role.edit = _create_noop_method(
        _original_methods['Role.edit'], 'Role.edit'
    )
    
    # Message methods
    _original_methods['Message.delete'] = discord.Message.delete
    discord.Message.delete = _create_noop_method(
        _original_methods['Message.delete'], 'Message.delete'
    )
    
    _original_methods['Message.edit'] = discord.Message.edit
    discord.Message.edit = _create_noop_method(
        _original_methods['Message.edit'], 'Message.edit'
    )

def restore_discord_methods() -> None:
    """Restore original Discord methods."""
    for method_path, original_method in _original_methods.items():
        module_path, method_name = method_path.rsplit('.', 1)
        module = discord
        for part in module_path.split('.'):
            if part != 'discord':
                module = getattr(module, part)
        setattr(module, method_name, original_method)
    
    _original_methods.clear()

# Fake classes for dummy objects
class FakeTextChannel:
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name
        self.mention = f"#{name}"

class FakeRole:
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name
        self.mention = f"@{name}"

class FakeCategory:
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name
