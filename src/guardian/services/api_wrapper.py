from __future__ import annotations

import asyncio
import time
import logging
from typing import Any, Callable, Optional, Dict, Union, TypeVar, cast
from functools import wraps
from dataclasses import dataclass

import discord
from discord import HTTPException, Forbidden, NotFound

log = logging.getLogger("guardian.api_wrapper")

T = TypeVar('T')


@dataclass
class APIResult:
    """Result of an API operation with retry information."""
    success: bool
    data: Optional[Any] = None
    error: Optional[Exception] = None
    attempts: int = 0
    total_time: float = 0.0
    retry_after: Optional[float] = None


class APIWrapper:
    """Unified API wrapper for rate-limit handling and retries."""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._error_counts: Dict[str, int] = {}
    
    def _get_backoff_delay(self, attempt: int, retry_after: Optional[float] = None) -> float:
        """Calculate exponential backoff delay with respect to Discord's retry_after."""
        if retry_after is not None:
            # Discord told us exactly how long to wait
            return min(retry_after + 0.1, self.max_delay)  # Add small buffer
        
        # Exponential backoff: base_delay * (2 ** attempt)
        delay = self.base_delay * (2 ** attempt)
        return min(delay, self.max_delay)
    
    def _should_retry(self, error: Exception, attempt: int) -> bool:
        """Determine if an error should trigger a retry."""
        if attempt >= self.max_retries:
            return False
        
        # Always retry on rate limit
        if isinstance(error, discord.HTTPException) and error.status == 429:
            return True
        
        # Retry on transient server errors
        if isinstance(error, discord.HTTPException) and error.status in (500, 502, 503, 504):
            return True
        
        # Don't retry on permission errors or not found
        if isinstance(error, (Forbidden, NotFound)):
            return False
        
        # Retry on timeout errors
        if isinstance(error, asyncio.TimeoutError):
            return True
        
        # Retry on unknown HTTP errors
        if isinstance(error, discord.HTTPException):
            return True
        
        return False
    
    def _log_error(self, operation: str, error: Exception, attempt: int, guild_id: Optional[int] = None):
        """Log errors with appropriate level based on type."""
        error_key = f"{operation}:{type(error).__name__}"
        self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
        
        # Expected operational errors - log as warnings, not errors
        if isinstance(error, (Forbidden, NotFound)):
            log.warning(
                "API operation %s failed (expected): %s (attempt %d) guild=%s",
                operation, str(error), attempt, guild_id
            )
            return
        
        # Rate limits - log as info with retry info
        if isinstance(error, discord.HTTPException) and error.status == 429:
            retry_after = getattr(error, 'retry_after', None)
            log.info(
                "API operation %s rate limited (retry_after=%s) (attempt %d) guild=%s",
                operation, retry_after, attempt, guild_id
            )
            return
        
        # Unexpected errors - log as error with stack trace (but limit spam)
        count = self._error_counts[error_key]
        if count <= 3:  # First 3 times, log full stack trace
            log.exception(
                "API operation %s failed unexpectedly (attempt %d) guild=%s",
                operation, attempt, guild_id
            )
        else:  # After that, just log summary
            log.error(
                "API operation %s failed unexpectedly (count=%d, attempt=%d) guild=%s: %s",
                operation, count, attempt, guild_id, str(error)
            )
    
    async def execute(
        self,
        operation: str,
        func: Callable[..., T],
        *args,
        guild_id: Optional[int] = None,
        user_id: Optional[int] = None,
        **kwargs
    ) -> APIResult:
        """Execute an API operation with retry logic and rate limit handling."""
        start_time = time.time()
        last_error = None
        retry_after = None
        
        for attempt in range(self.max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                
                # Log successful operation
                duration = time.time() - start_time
                log.debug(
                    "API operation %s succeeded (attempt %d, duration=%.2fs) guild=%s user=%s",
                    operation, attempt + 1, duration, guild_id, user_id
                )
                
                return APIResult(
                    success=True,
                    data=result,
                    attempts=attempt + 1,
                    total_time=duration
                )
                
            except Exception as error:
                last_error = error
                
                # Extract retry_after if available
                if isinstance(error, discord.HTTPException) and hasattr(error, 'retry_after'):
                    retry_after = error.retry_after
                
                # Log the error
                self._log_error(operation, error, attempt, guild_id)
                
                # Check if we should retry
                if not self._should_retry(error, attempt):
                    break
                
                # Calculate delay and wait
                delay = self._get_backoff_delay(attempt, retry_after)
                log.debug(
                    "API operation %s retrying in %.2fs (attempt %d/%d) guild=%s",
                    operation, delay, attempt + 1, self.max_retries + 1, guild_id
                )
                
                await asyncio.sleep(delay)
        
        # All attempts failed
        duration = time.time() - start_time
        log.error(
            "API operation %s failed after %d attempts (%.2fs) guild=%s user=%s: %s",
            operation, self.max_retries + 1, duration, guild_id, user_id, str(last_error)
        )
        
        return APIResult(
            success=False,
            error=last_error,
            attempts=self.max_retries + 1,
            total_time=duration,
            retry_after=retry_after
        )
    
    def get_error_summary(self) -> Dict[str, int]:
        """Get a summary of error counts for observability."""
        return dict(self._error_counts)
    
    def reset_error_counts(self):
        """Reset error counts (useful for periodic cleanup)."""
        self._error_counts.clear()


# Global instance for use throughout the bot
api_wrapper = APIWrapper()


def safe_api_operation(operation: str):
    """Decorator for safe API operations with automatic retry."""
    def decorator(func: Callable[..., T]) -> Callable[..., APIResult]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> APIResult:
            # Extract context information if available
            guild_id = None
            user_id = None
            
            # Try to extract guild_id and user_id from common patterns
            for arg in args:
                if isinstance(arg, discord.Guild):
                    guild_id = arg.id
                elif isinstance(arg, discord.Interaction):
                    guild_id = arg.guild.id if arg.guild else None
                    user_id = arg.user.id
                elif isinstance(arg, discord.Member):
                    guild_id = arg.guild.id
                    user_id = arg.id
                elif isinstance(arg, discord.User):
                    user_id = arg.id
            
            for key, value in kwargs.items():
                if isinstance(value, discord.Guild):
                    guild_id = value.id
                elif isinstance(value, discord.Interaction):
                    guild_id = value.guild.id if value.guild else None
                    user_id = value.user.id
                elif isinstance(value, discord.Member):
                    guild_id = value.guild.id
                    user_id = value.id
                elif isinstance(value, discord.User):
                    user_id = value.id
            
            return await api_wrapper.execute(
                operation=operation,
                func=func,
                *args,
                guild_id=guild_id,
                user_id=user_id,
                **kwargs
            )
        
        return wrapper
    return decorator


# Common API operation wrappers
@safe_api_operation("send_message")
async def safe_send_message(channel: discord.abc.Messageable, **kwargs) -> discord.Message:
    """Safely send a message with retry logic."""
    return await channel.send(**kwargs)


@safe_api_operation("edit_message")
async def safe_edit_message(message: discord.Message, **kwargs) -> discord.Message:
    """Safely edit a message with retry logic."""
    return await message.edit(**kwargs)


@safe_api_operation("create_channel")
async def safe_create_channel(guild: discord.Guild, **kwargs) -> discord.abc.GuildChannel:
    """Safely create a channel with retry logic."""
    return await guild.create_channel(**kwargs)


@safe_api_operation("edit_channel")
async def safe_edit_channel(channel: discord.abc.GuildChannel, **kwargs) -> discord.abc.GuildChannel:
    """Safely edit a channel with retry logic."""
    return await channel.edit(**kwargs)


@safe_api_operation("create_role")
async def safe_create_role(guild: discord.Guild, **kwargs) -> discord.Role:
    """Safely create a role with retry logic."""
    return await guild.create_role(**kwargs)


@safe_api_operation("edit_role")
async def safe_edit_role(role: discord.Role, **kwargs) -> discord.Role:
    """Safely edit a role with retry logic."""
    return await role.edit(**kwargs)


@safe_api_operation("add_role")
async def safe_add_role(member: discord.Member, role: discord.Role, **kwargs) -> None:
    """Safely add a role to a member with retry logic."""
    return await member.add_roles(role, **kwargs)


@safe_api_operation("remove_role")
async def safe_remove_role(member: discord.Member, role: discord.Role, **kwargs) -> None:
    """Safely remove a role from a member with retry logic."""
    return await member.remove_roles(role, **kwargs)
