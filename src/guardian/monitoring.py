from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import discord
from discord.ext import commands

from .database import get_database_info
from .services.stats import RuntimeStats

log = logging.getLogger("guardian.monitoring")


@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring."""
    command_count: int = 0
    error_count: int = 0
    avg_response_time: float = 0.0
    total_response_time: float = 0.0
    memory_usage: float = 0.0
    database_size: float = 0.0
    guild_count: int = 0
    user_count: int = 0
    channel_count: int = 0
    
    def update_response_time(self, response_time: float) -> None:
        """Update average response time."""
        self.command_count += 1
        self.total_response_time += response_time
        self.avg_response_time = self.total_response_time / self.command_count
    
    def increment_errors(self) -> None:
        """Increment error count."""
        self.error_count += 1


class PerformanceMonitor:
    """Monitor bot performance and health."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.metrics = PerformanceMetrics()
        self._start_time = time.time()
        self._command_times: Dict[str, List[float]] = {}
    
    async def get_health_status(self) -> discord.Embed:
        """Get current health status."""
        try:
            # Update metrics
            await self._update_metrics()
            
            # Calculate uptime
            uptime = time.time() - self._start_time
            uptime_str = f"{uptime // 86400:.0f}d {(uptime % 86400) // 3600:.0f}h {(uptime % 3600) // 60:.0f}m"
            
            # Determine health status
            health_color = discord.Color.green()
            health_status = "Healthy"
            
            if self.metrics.error_count > 10:
                health_color = discord.Color.red()
                health_status = "Unhealthy"
            elif self.metrics.error_count > 5:
                health_color = discord.Color.orange()
                health_status = "Degraded"
            elif self.metrics.avg_response_time > 2.0:
                health_color = discord.Color.orange()
                health_status = "Slow"
            
            embed = discord.Embed(
                title=f"Bot Health Status: {health_status}",
                color=health_color,
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(name="Uptime", value=uptime_str, inline=True)
            embed.add_field(name="Commands Run", value=str(self.metrics.command_count), inline=True)
            embed.add_field(name="Errors", value=str(self.metrics.error_count), inline=True)
            embed.add_field(name="Avg Response Time", value=f"{self.metrics.avg_response_time:.2f}s", inline=True)
            embed.add_field(name="Guilds", value=str(self.metrics.guild_count), inline=True)
            embed.add_field(name="Users", value=str(self.metrics.user_count), inline=True)
            embed.add_field(name="Database Size", value=f"{self.metrics.database_size:.2f} MB", inline=True)
            embed.add_field(name="Memory Usage", value=f"{self.metrics.memory_usage:.2f} MB", inline=True)
            
            return embed
            
        except Exception as e:
            log.error(f"Failed to get health status: {e}")
            return discord.Embed(
                title="Health Check Failed",
                description="Unable to retrieve health metrics.",
                color=discord.Color.red()
            )
    
    async def _update_metrics(self) -> None:
        """Update performance metrics."""
        try:
            # Update Discord metrics
            self.metrics.guild_count = len(self.bot.guilds)
            self.metrics.user_count = sum(len(guild.members) for guild in self.bot.guilds)
            self.metrics.channel_count = sum(len(guild.channels) for guild in self.bot.guilds)
            
            # Update database metrics
            if hasattr(self.bot, 'settings'):
                db_info = await get_database_info(self.bot.settings.sqlite_path)
                self.metrics.database_size = db_info["size_mb"]
            
            # Update memory usage (simplified)
            import psutil
            process = psutil.Process()
            self.metrics.memory_usage = process.memory_info().rss / 1024 / 1024
            
        except Exception as e:
            log.error(f"Failed to update metrics: {e}")
    
    def record_command(self, command_name: str, response_time: float) -> None:
        """Record a command execution."""
        self.metrics.update_response_time(response_time)
        
        if command_name not in self._command_times:
            self._command_times[command_name] = []
        self._command_times[command_name].append(response_time)
        
        # Keep only last 100 entries per command
        if len(self._command_times[command_name]) > 100:
            self._command_times[command_name] = self._command_times[command_name][-100:]
    
    def record_error(self) -> None:
        """Record an error."""
        self.metrics.increment_errors()
    
    def get_command_stats(self, command_name: str) -> Optional[Dict[str, float]]:
        """Get statistics for a specific command."""
        if command_name not in self._command_times:
            return None
        
        times = self._command_times[command_name]
        if not times:
            return None
        
        return {
            "count": len(times),
            "avg": sum(times) / len(times),
            "min": min(times),
            "max": max(times),
        }


class CommandPerformance(commands.Cog):
    """Cog for monitoring command performance."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.monitor = PerformanceMonitor(bot)
        self._original_before_invoke = bot.before_invoke
        self._original_after_invoke = bot.after_invoke
        self._original_on_command_error = bot.on_command_error
        
        # Hook into bot events
        bot.before_invoke = self._before_invoke
        bot.after_invoke = self._after_invoke
        bot.on_command_error = self._on_command_error
    
    def cog_unload(self) -> None:
        """Restore original bot methods."""
        self.bot.before_invoke = self._original_before_invoke
        self.bot.after_invoke = self._original_after_invoke
        self.bot.on_command_error = self._original_on_command_error
    
    async def _before_invoke(self, ctx: commands.Context) -> None:
        """Called before command invocation."""
        ctx._start_time = time.time()
    
    async def _after_invoke(self, ctx: commands.Context) -> None:
        """Called after command invocation."""
        if hasattr(ctx, '_start_time'):
            response_time = time.time() - ctx._start_time
            self.monitor.record_command(ctx.command.qualified_name, response_time)
    
    async def _on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Called on command error."""
        self.monitor.record_error()
        if self._original_on_command_error:
            await self._original_on_command_error(ctx, error)
    
    @commands.command(name="health")
    @commands.is_owner()
    async def health_check(self, ctx: commands.Context) -> None:
        """Check bot health status."""
        embed = await self.monitor.get_health_status()
        await ctx.send(embed=embed)
    
    @commands.command(name="stats")
    @commands.is_owner()
    async def command_stats(self, ctx: commands.Context, command_name: Optional[str] = None) -> None:
        """Get command performance statistics."""
        if command_name:
            stats = self.monitor.get_command_stats(command_name)
            if stats:
                embed = discord.Embed(
                    title=f"Command Stats: {command_name}",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Count", value=str(stats["count"]), inline=True)
                embed.add_field(name="Avg Time", value=f"{stats['avg']:.2f}s", inline=True)
                embed.add_field(name="Min Time", value=f"{stats['min']:.2f}s", inline=True)
                embed.add_field(name="Max Time", value=f"{stats['max']:.2f}s", inline=True)
                await ctx.send(embed=embed)
            else:
                await ctx.send("No stats found for that command.")
        else:
            embed = discord.Embed(
                title="Overall Command Stats",
                color=discord.Color.blue()
            )
            embed.add_field(name="Total Commands", value=str(self.monitor.metrics.command_count), inline=True)
            embed.add_field(name="Total Errors", value=str(self.monitor.metrics.error_count), inline=True)
            embed.add_field(name="Avg Response Time", value=f"{self.monitor.metrics.avg_response_time:.2f}s", inline=True)
            await ctx.send(embed=embed)
