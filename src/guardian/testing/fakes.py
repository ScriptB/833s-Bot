from __future__ import annotations

from typing import Any

import discord


class FakeMember:
    """Fake Discord Member for testing."""
    
    def __init__(self, id: int = 123456789, name: str = "TestUser", discriminator: str = "0001"):
        self.id = id
        self.name = name
        self.discriminator = discriminator
        self.display_name = name
        self.mention = f"<@{id}>"
        self.avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
        self.joined_at = discord.utils.utcnow()
        self.created_at = discord.utils.utcnow()
        self.guild = None  # Will be set by context
        self.roles = []
        self.permissions = discord.Permissions.all()
    
    def __str__(self):
        return f"{self.name}#{self.discriminator}"
    
    def __repr__(self):
        return f"<FakeMember id={self.id} name={self.name}#{self.discriminator}>"

class FakeUser:
    """Fake Discord User for testing."""
    
    def __init__(self, id: int = 123456789, name: str = "TestUser", discriminator: str = "0001"):
        self.id = id
        self.name = name
        self.discriminator = discriminator
        self.display_name = name
        self.mention = f"<@{id}>"
        self.avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
        self.created_at = discord.utils.utcnow()
    
    def __str__(self):
        return f"{self.name}#{self.discriminator}"
    
    def __repr__(self):
        return f"<FakeUser id={self.id} name={self.name}#{self.discriminator}>"

class FakeTextChannel:
    """Fake Discord TextChannel for testing."""
    
    def __init__(self, id: int = 123456789, name: str = "test-channel"):
        self.id = id
        self.name = name
        self.mention = f"#{name}"
        self.topic = "Test channel topic"
        self.nsfw = False
        self.category_id = None
        self.position = 0
        self.permissions_overwrites = {}
        self.guild = None  # Will be set by context
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"<FakeTextChannel id={self.id} name={self.name}>"

class FakeVoiceChannel:
    """Fake Discord VoiceChannel for testing."""
    
    def __init__(self, id: int = 123456789, name: str = "test-voice"):
        self.id = id
        self.name = name
        self.mention = f"#{name}"
        self.bitrate = 64000
        self.user_limit = 0
        self.category_id = None
        self.position = 0
        self.permissions_overwrites = {}
        self.guild = None  # Will be set by context
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"<FakeVoiceChannel id={self.id} name={self.name}>"

class FakeCategory:
    """Fake Discord CategoryChannel for testing."""
    
    def __init__(self, id: int = 123456789, name: str = "test-category"):
        self.id = id
        self.name = name
        self.mention = f"#{name}"
        self.position = 0
        self.permissions_overwrites = {}
        self.guild = None  # Will be set by context
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"<FakeCategory id={self.id} name={self.name}>"

class FakeRole:
    """Fake Discord Role for testing."""
    
    def __init__(self, id: int = 123456789, name: str = "TestRole"):
        self.id = id
        self.name = name
        self.mention = f"@{name}"
        self.color = discord.Color.blue()
        self.hoist = False
        self.position = 0
        self.permissions = discord.Permissions.none()
        self.managed = False
        self.mentionable = False
        self.guild = None  # Will be set by context
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"<FakeRole id={self.id} name={self.name}>"

class FakeGuild:
    """Fake Discord Guild for testing."""
    
    def __init__(self, id: int = 123456789, name: str = "TestGuild"):
        self.id = id
        self.name = name
        self.owner_id = 987654321
        self.member_count = 100
        self.icon_url = "https://cdn.discordapp.com/embed/avatars/0.png"
        self.description = "Test guild for self-testing"
        self.me = FakeMember(id=111111111, name="BotUser")
        self.system_channel = FakeTextChannel(id=222222222, name="system")
        self.rules_channel = FakeTextChannel(id=333333333, name="rules")
        self.public_updates_channel = FakeTextChannel(id=444444444, name="updates")
        self.text_channels = []
        self.voice_channels = []
        self.categories = []
        self.roles = []
        self.members = []
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"<FakeGuild id={self.id} name={self.name}>"
    
    def get_channel(self, channel_id: int) -> FakeTextChannel | FakeVoiceChannel | FakeCategory | None:
        """Get a channel by ID."""
        for channel in self.text_channels + self.voice_channels + self.categories:
            if channel.id == channel_id:
                return channel
        return None
    
    def get_member(self, member_id: int) -> FakeMember | None:
        """Get a member by ID."""
        for member in self.members:
            if member.id == member_id:
                return member
        return None

class FakeMessage:
    """Fake Discord Message for testing."""
    
    def __init__(self, content: str = "Test message", author: FakeMember | None = None, channel: FakeTextChannel | None = None):
        self.content = content
        self.author = author or FakeMember()
        self.channel = channel or FakeTextChannel()
        self.id = 123456789
        self.created_at = discord.utils.utcnow()
        self.edited_at = None
        self.tts = False
        self.pinned = False
        self.mention_everyone = False
        self.mentions = []
        self.role_mentions = []
        self.channel_mentions = []
    
    def __str__(self):
        return self.content

class FakeContext:
    """Fake Discord Context for testing prefix commands."""
    
    def __init__(self, bot: discord.Client, guild: FakeGuild | None = None, channel: FakeTextChannel | None = None, author: FakeMember | None = None):
        self.bot = bot
        self.guild = guild or FakeGuild()
        self.channel = channel or FakeTextChannel()
        self.author = author or FakeMember()
        self.message = FakeMessage(author=self.author, channel=self.channel)
        self.prefix = "!"
        self.command = None
        self.invoked_with = "test"
        self.invoked_subcommand = None
        self.subcommand_passed = None
        self.args = []
        self.kwargs = {}
        self._sent_messages = []
        self._error = None
    
    async def send(self, content: str = None, **kwargs) -> FakeMessage:
        """Fake send method that logs the message."""
        message = FakeMessage(content=content or "", author=self.bot.user, channel=self.channel)
        self._sent_messages.append({
            'content': content,
            'kwargs': kwargs,
            'message': message
        })
        return message
    
    async def reply(self, content: str = None, **kwargs) -> FakeMessage:
        """Fake reply method that logs the message."""
        return await self.send(content=content, **kwargs)
    
    async def fetch_message(self, message_id: int) -> FakeMessage:
        """Fake fetch_message method."""
        return FakeMessage()
    
    def get_sent_messages(self) -> list[dict[str, Any]]:
        """Get all messages sent through this context."""
        return self._sent_messages.copy()

class FakeInteraction:
    """Fake Discord Interaction for testing app commands."""
    
    def __init__(self, bot: discord.Client, guild: FakeGuild | None = None, channel: FakeTextChannel | None = None, user: FakeUser | None = None):
        self.bot = bot
        self.guild = guild or FakeGuild()
        self.channel = channel or FakeTextChannel()
        self.user = user or FakeUser()
        self.response = FakeInteractionResponse()
        self.data = {}
        self.command = None
        self._sent_messages = []
        self._error = None
    
    @property
    def author(self) -> FakeUser:
        """Alias for user for compatibility."""
        return self.user
    
    async def original_response(self) -> FakeMessage:
        """Fake original_response method."""
        return FakeMessage(author=self.bot.user, channel=self.channel)
    
    def get_sent_messages(self) -> list[dict[str, Any]]:
        """Get all messages sent through this interaction."""
        return self._sent_messages.copy()

class FakeInteractionResponse:
    """Fake Discord InteractionResponse for testing."""
    
    def __init__(self):
        self._responded = False
        self.deferred = False
        self._messages = []
    
    async def send_message(self, content: str = None, **kwargs) -> FakeMessage:
        """Fake send_message method."""
        self._responded = True
        message = FakeMessage(content=content or "")
        self._messages.append({'content': content, 'kwargs': kwargs, 'message': message})
        return message
    
    async def defer(self, ephemeral: bool = False, thinking: bool = False) -> None:
        """Fake defer method."""
        self.deferred = True
    
    def is_done(self) -> bool:
        """Check if response has been sent."""
        return self._responded
    
    def get_messages(self) -> list[dict[str, Any]]:
        """Get all messages sent."""
        return self._messages.copy()
