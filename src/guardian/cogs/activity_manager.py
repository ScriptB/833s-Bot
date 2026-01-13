from __future__ import annotations

import asyncio
import random
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("guardian.activity_manager")


class ActivityType(Enum):
    """Activity types for the bot."""
    PLAYING = "playing"
    WATCHING = "watching"
    LISTENING = "listening"
    STREAMING = "streaming"
    CUSTOM = "custom"


@dataclass
class ActivityConfig:
    """Configuration for a bot activity."""
    name: str
    activity_type: ActivityType
    state: Optional[str] = None  # For custom activities
    url: Optional[str] = None  # For streaming activities
    weight: int = 1  # Weight for random selection (higher = more frequent)
    duration_minutes: int = 5  # How long to display this activity


class ActivityManager:
    """Manages bot activities with cycling and randomization."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._current_activity_index = 0
        self._task: Optional[asyncio.Task] = None
        self._activities: List[ActivityConfig] = []
        self._is_running = False
        
        # Initialize default activities
        self._setup_default_activities()
    
    def _setup_default_activities(self):
        """Set up default activities for the Guardian Bot."""
        self._activities = [
            # Primary activity - Watching for help command
            ActivityConfig(
                name="83ss for /help",
                activity_type=ActivityType.WATCHING,
                weight=3,  # Higher weight - more frequent
                duration_minutes=10
            ),
            
            # Server management activities
            ActivityConfig(
                name="the server",
                activity_type=ActivityType.WATCHING,
                weight=2,
                duration_minutes=8
            ),
            
            ActivityConfig(
                name="for new members",
                activity_type=ActivityType.WATCHING,
                weight=2,
                duration_minutes=6
            ),
            
            # Gaming activities
            ActivityConfig(
                name="with the server setup",
                activity_type=ActivityType.PLAYING,
                weight=2,
                duration_minutes=7
            ),
            
            ActivityConfig(
                name="with roles and permissions",
                activity_type=ActivityType.PLAYING,
                weight=1,
                duration_minutes=5
            ),
            
            ActivityConfig(
                name="Guardian Bot Simulator",
                activity_type=ActivityType.PLAYING,
                weight=1,
                duration_minutes=5
            ),
            
            # Music/Listening activities
            ActivityConfig(
                name="server management tips",
                activity_type=ActivityType.LISTENING,
                weight=1,
                duration_minutes=6
            ),
            
            ActivityConfig(
                name="the community's feedback",
                activity_type=ActivityType.LISTENING,
                weight=2,
                duration_minutes=8
            ),
            
            # Custom status activities
            ActivityConfig(
                name="Guardian Bot",
                activity_type=ActivityType.CUSTOM,
                state="Protecting the server",
                weight=2,
                duration_minutes=10
            ),
            
            ActivityConfig(
                name="Guardian Bot",
                activity_type=ActivityType.CUSTOM,
                state="Ready to assist",
                weight=1,
                duration_minutes=5
            ),
            
            ActivityConfig(
                name="Guardian Bot",
                activity_type=ActivityType.CUSTOM,
                state="Monitoring server health",
                weight=1,
                duration_minutes=7
            ),
            
            ActivityConfig(
                name="Guardian Bot",
                activity_type=ActivityType.CUSTOM,
                state="Keeping the server safe",
                weight=2,
                duration_minutes=8
            )
        ]
    
    def add_activity(self, activity: ActivityConfig):
        """Add a new activity to the rotation."""
        self._activities.append(activity)
        log.info(f"Added activity: {activity.name} ({activity.activity_type.value})")
    
    def remove_activity(self, name: str) -> bool:
        """Remove an activity by name."""
        for i, activity in enumerate(self._activities):
            if activity.name == name:
                del self._activities[i]
                log.info(f"Removed activity: {name}")
                return True
        return False
    
    def get_weighted_random_activity(self) -> ActivityConfig:
        """Get a random activity based on weights."""
        if not self._activities:
            # Fallback activity
            return ActivityConfig(
                name="83ss for /help",
                activity_type=ActivityType.WATCHING
            )
        
        # Calculate total weight
        total_weight = sum(activity.weight for activity in self._activities)
        
        # Select random activity based on weight
        random_weight = random.randint(1, total_weight)
        current_weight = 0
        
        for activity in self._activities:
            current_weight += activity.weight
            if random_weight <= current_weight:
                return activity
        
        # Fallback to first activity
        return self._activities[0]
    
    def get_next_activity(self) -> ActivityConfig:
        """Get the next activity in sequence (or random)."""
        if not self._activities:
            return ActivityConfig(
                name="83ss for /help",
                activity_type=ActivityType.WATCHING
            )
        
        # Use weighted random for variety
        return self.get_weighted_random_activity()
    
    async def set_activity(self, activity: ActivityConfig):
        """Set the bot's activity with proper guardrails."""
        # Validate bot is ready
        if not self.bot:
            log.error("Cannot set activity: bot is None")
            return
        
        if not hasattr(self.bot, 'user') or not self.bot.user:
            log.error("Cannot set activity: bot.user is not available")
            return
        
        # Wait for bot to be ready if needed
        if not self.bot.is_ready():
            try:
                await self.bot.wait_until_ready()
            except Exception as e:
                log.error(f"Failed to wait for bot readiness: {e}")
                return
        
        # Rate limiting - don't spam presence updates
        if hasattr(self, '_last_activity_update'):
            time_since_last = time.time() - self._last_activity_update
            if time_since_last < 5:  # Minimum 5 seconds between updates
                log.debug(f"Skipping activity update - too soon since last update ({time_since_last:.1f}s ago)")
                return
        
        try:
            if activity.activity_type == ActivityType.PLAYING:
                await self.bot.change_presence(
                    activity=discord.Game(name=activity.name)
                )
            
            elif activity.activity_type == ActivityType.WATCHING:
                await self.bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching,
                        name=activity.name
                    )
                )
            
            elif activity.activity_type == ActivityType.LISTENING:
                await self.bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.listening,
                        name=activity.name
                    )
                )
            
            elif activity.activity_type == ActivityType.STREAMING:
                if activity.url:
                    await self.bot.change_presence(
                        activity=discord.Streaming(
                            name=activity.name,
                            url=activity.url
                        )
                    )
                else:
                    # Fallback to playing if no URL provided
                    await self.bot.change_presence(
                        activity=discord.Game(name=activity.name)
                    )
            
            elif activity.activity_type == ActivityType.CUSTOM:
                await self.bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.custom,
                        name=activity.name,
                        state=activity.state or "Ready to assist"
                    )
                )
            
            # Update last activity timestamp
            self._last_activity_update = time.time()
            log.info(f"Set activity: {activity.name} ({activity.activity_type.value})")
            
        except discord.HTTPException as e:
            # Expected Discord API errors
            log.warning(f"Discord API error setting activity {activity.name}: {e}")
        except Exception as e:
            # Unexpected errors - log once per cycle
            if not hasattr(self, '_last_activity_error') or time.time() - self._last_activity_error > 60:
                log.error(f"Failed to set activity {activity.name}: {e}")
                self._last_activity_error = time.time()
            else:
                log.debug(f"Failed to set activity {activity.name} (error already logged)")
    
    async def start_activity_cycling(self):
        """Start the activity cycling system."""
        if self._is_running:
            log.warning("Activity cycling is already running")
            return
        
        self._is_running = True
        self._task = asyncio.create_task(self._activity_cycling_loop())
        log.info("Started activity cycling system")
    
    async def stop_activity_cycling(self):
        """Stop the activity cycling system."""
        if not self._is_running:
            return
        
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        log.info("Stopped activity cycling system")
    
    async def _activity_cycling_loop(self):
        """Main loop for cycling through activities."""
        while self._is_running:
            try:
                # Get next activity
                activity = self.get_next_activity()
                
                # Set the activity
                await self.set_activity(activity)
                
                # Wait for the duration
                await asyncio.sleep(activity.duration_minutes * 60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in activity cycling loop: {e}")
                # Wait a bit before trying again
                await asyncio.sleep(30)
    
    def get_activity_count(self) -> int:
        """Get the number of configured activities."""
        return len(self._activities)
    
    def get_all_activities(self) -> List[Dict[str, Any]]:
        """Get all configured activities as dictionaries."""
        return [
            {
                "name": activity.name,
                "type": activity.activity_type.value,
                "state": activity.state,
                "url": activity.url,
                "weight": activity.weight,
                "duration_minutes": activity.duration_minutes
            }
            for activity in self._activities
        ]


class ActivityCog(commands.Cog):
    """Cog for managing bot activities."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.activity_manager = ActivityManager(bot)
    
    async def cog_load(self):
        """Start activity cycling when cog loads."""
        await self.activity_manager.start_activity_cycling()
        log.info("Activity manager cog loaded and cycling started")
    
    async def cog_unload(self):
        """Stop activity cycling when cog unloads."""
        await self.activity_manager.stop_activity_cycling()
        log.info("Activity manager cog unloaded and cycling stopped")
    
    @app_commands.command(
        name="activity",
        description="Manage bot activities"
    )
    @app_commands.describe(
        action="Action to perform",
        name="Activity name (for add/remove)",
        activity_type="Activity type",
        state="Custom state (for custom activities)",
        weight="Weight for random selection (1-10)",
        duration="Duration in minutes"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="list", value="list"),
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
            app_commands.Choice(name="set", value="set")
        ]
    )
    @app_commands.choices(
        activity_type=[
            app_commands.Choice(name="playing", value="playing"),
            app_commands.Choice(name="watching", value="watching"),
            app_commands.Choice(name="listening", value="listening"),
            app_commands.Choice(name="streaming", value="streaming"),
            app_commands.Choice(name="custom", value="custom")
        ]
    )
    async def activity_command(
        self,
        interaction: discord.Interaction,
        action: str,
        name: Optional[str] = None,
        activity_type: Optional[str] = None,
        state: Optional[str] = None,
        weight: Optional[int] = None,
        duration: Optional[int] = None
    ):
        """Manage bot activities."""
        await interaction.response.defer(ephemeral=True)
        
        if action == "list":
            await self._list_activities(interaction)
        elif action == "add":
            await self._add_activity(interaction, name, activity_type, state, weight, duration)
        elif action == "remove":
            await self._remove_activity(interaction, name)
        elif action == "set":
            await self._set_activity(interaction, name, activity_type, state)
        else:
            await interaction.followup.send("❌ Unknown action", ephemeral=True)
    
    async def _list_activities(self, interaction: discord.Interaction):
        """List all configured activities."""
        activities = self.activity_manager.get_all_activities()
        
        if not activities:
            await interaction.followup.send("No activities configured.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎯 Bot Activities",
            description=f"Total activities: {len(activities)}",
            color=discord.Color.blue()
        )
        
        for i, activity in enumerate(activities, 1):
            activity_type = activity["type"].title()
            duration = activity["duration_minutes"]
            weight = activity["weight"]
            
            value = f"**Type:** {activity_type}\n**Duration:** {duration}m\n**Weight:** {weight}"
            
            if activity["state"]:
                value += f"\n**State:** {activity['state']}"
            
            if activity["url"]:
                value += f"\n**URL:** {activity['url']}"
            
            embed.add_field(
                name=f"{i}. {activity['name']}",
                value=value,
                inline=False
            )
        
        embed.set_footer(text="Activities cycle automatically based on weights")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _add_activity(
        self,
        interaction: discord.Interaction,
        name: Optional[str],
        activity_type_str: Optional[str],
        state: Optional[str],
        weight: Optional[int],
        duration: Optional[int]
    ):
        """Add a new activity."""
        if not name or not activity_type_str:
            await interaction.followup.send("❌ Name and type are required for adding activities.", ephemeral=True)
            return
        
        try:
            activity_type = ActivityType(activity_type_str)
            
            activity = ActivityConfig(
                name=name,
                activity_type=activity_type,
                state=state,
                weight=weight or 1,
                duration_minutes=duration or 5
            )
            
            self.activity_manager.add_activity(activity)
            
            embed = discord.Embed(
                title="✅ Activity Added",
                description=f"Added activity: **{name}** ({activity_type.value})",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send("❌ Invalid activity type.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error adding activity: {str(e)}", ephemeral=True)
    
    async def _remove_activity(self, interaction: discord.Interaction, name: Optional[str]):
        """Remove an activity."""
        if not name:
            await interaction.followup.send("❌ Name is required for removing activities.", ephemeral=True)
            return
        
        if self.activity_manager.remove_activity(name):
            embed = discord.Embed(
                title="✅ Activity Removed",
                description=f"Removed activity: **{name}**",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Activity '{name}' not found.", ephemeral=True)
    
    async def _set_activity(
        self,
        interaction: discord.Interaction,
        name: Optional[str],
        activity_type_str: Optional[str],
        state: Optional[str]
    ):
        """Immediately set a specific activity."""
        if not name or not activity_type_str:
            await interaction.followup.send("❌ Name and type are required for setting activities.", ephemeral=True)
            return
        
        try:
            activity_type = ActivityType(activity_type_str)
            
            activity = ActivityConfig(
                name=name,
                activity_type=activity_type,
                state=state
            )
            
            await self.activity_manager.set_activity(activity)
            
            embed = discord.Embed(
                title="✅ Activity Set",
                description=f"Set activity to: **{name}** ({activity_type.value})",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send("❌ Invalid activity type.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error setting activity: {str(e)}", ephemeral=True)


# Setup function
async def setup(bot: commands.Bot):
    """Setup the activity manager cog."""
    await bot.add_cog(ActivityCog(bot))
    log.info("Activity manager cog loaded")
