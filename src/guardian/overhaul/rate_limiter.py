from __future__ import annotations

import asyncio
import time
from typing import Optional, Dict, Any, List
import discord
import logging

log = logging.getLogger("guardian.rate_limiter")


class RateLimiter:
    """Rate limiter for Discord API calls with 429 handling."""
    
    def __init__(self):
        self._global_lock = asyncio.Lock()
        self._last_global_reset = 0
    
    async def execute(self, coro, *args, **kwargs):
        """Execute a coroutine with rate limit handling."""
        while True:
            try:
                return await coro(*args, **kwargs)
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = float(e.response.headers.get('Retry-After', 1.0))
                    log.warning(f"Rate limited, waiting {retry_after:.2f}s")
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    raise
            except (discord.Forbidden, discord.NotFound) as e:
                # Expected errors, return None for graceful handling
                log.debug(f"Expected API error: {type(e).__name__}: {e}")
                return None
            except Exception as e:
                log.exception(f"Unexpected API error: {e}")
                raise
