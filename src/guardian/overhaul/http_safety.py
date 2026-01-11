"""
HTTP Safety Layer for Overhaul Operations

Provides rate limiting and retry logic for Discord API calls.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Callable, Any, Optional

import discord

log = logging.getLogger("guardian.overhaul.http_safety")


class OverhaulHttpSafety:
    """HTTP safety layer for Discord API operations."""
    
    def __init__(self):
        # Global semaphore for all operations
        self.semaphore = asyncio.Semaphore(1)
        self.last_request_time = 0
    
    async def execute_with_retry(self, coro_func: Callable[[], Any], max_retries: int = 5) -> Any:
        """Execute a coroutine with rate limiting and retry logic."""
        for attempt in range(max_retries):
            try:
                await self.semaphore.acquire()
                try:
                    # Add jittered delay between operations
                    await self._jittered_sleep()
                    
                    # Execute the coroutine
                    result = await coro_func()
                    return result
                    
                finally:
                    self.semaphore.release()
                    
            except discord.HTTPException as e:
                if e.status == 429:
                    # Rate limited - respect retry_after
                    retry_after = float(e.response.headers.get('Retry-After', 1.0))
                    log.warning(f"Rate limited, waiting {retry_after:.1f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    # Other HTTP errors - re-raise
                    raise
                    
            except Exception as e:
                # Non-HTTP errors - retry with exponential backoff
                if attempt == max_retries - 1:
                    log.error(f"Max retries exceeded for operation: {e}")
                    raise
                
                backoff_delay = 0.5 * (2 ** attempt) + random.uniform(0, 0.5)
                log.warning(f"Request failed, retrying in {backoff_delay:.1f}s (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(backoff_delay)
        
        raise Exception("Max retries exceeded")
    
    async def _jittered_sleep(self):
        """Add jittered sleep between destructive operations (0.25-0.75s)."""
        now = time.time()
        min_delay = 0.25
        max_delay = 0.75
        
        if now - self.last_request_time < min_delay:
            delay = random.uniform(min_delay, max_delay)
            await asyncio.sleep(delay)
        
        self.last_request_time = time.time()


# Global safety instance
http_safety = OverhaulHttpSafety()
