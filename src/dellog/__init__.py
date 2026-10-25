"""dellog — a drop-in discord.py cog that logs deleted and edited messages."""

from .cog import DelLog, setup
from .config import ConfigError, ConfigStore, GuildConfig
from .embeds import MessageSnapshot

__all__ = [
    "DelLog",
    "setup",
    "ConfigError",
    "ConfigStore",
    "GuildConfig",
    "MessageSnapshot",
]

__version__ = "1.0.0"
