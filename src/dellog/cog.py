"""The dellog cog: logs deleted and edited messages to a mod channel.

Design notes:
- Listeners stay thin. Every decision ("should this be logged?") lives in
  `should_log`, and every message-to-data conversion lives in
  `snapshot_from_message`, so both are unit-testable without a bot.
- Slash commands are config-only and need Manage Server. The actual logging
  never depends on them, so a server that never runs a command just gets
  nothing logged until someone runs /dellog setup.
- A send that fails (log channel deleted, missing perms) is swallowed on
  purpose: a logging cog must never take the host bot down with it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from .config import ConfigError, ConfigStore, GuildConfig
from .embeds import (
    MessageSnapshot,
    bulk_delete_embed,
    delete_embed,
    edit_embed,
)

logger = logging.getLogger("dellog")

LogKind = Literal["delete", "edit"]


def should_log(
    config: GuildConfig,
    kind: LogKind,
    *,
    is_bot: bool,
    channel_id: int,
    author_id: int,
) -> bool:
    """Decide whether one event deserves a log entry."""
    if config.log_channel_id is None:
        return False
    if kind == "delete" and not config.log_deletes:
        return False
    if kind == "edit" and not config.log_edits:
        return False
    if is_bot and config.ignore_bots:
        return False
    if channel_id in config.ignored_channel_ids:
        return False
    if author_id in config.ignored_user_ids:
        return False
    return True


def snapshot_from_message(message: discord.Message) -> MessageSnapshot:
    """Pull the loggable fields out of a discord message."""
    author = message.author
    avatar_url = None
    avatar = getattr(author, "display_avatar", None)
    if avatar is not None:
        avatar_url = getattr(avatar, "url", None)
    attachments = [
        getattr(a, "url", str(a)) for a in getattr(message, "attachments", [])
    ]
    return MessageSnapshot(
        author_name=getattr(author, "display_name", str(author)),
        author_id=author.id,
        author_avatar_url=avatar_url,
        channel_id=message.channel.id,
        channel_name=getattr(message.channel, "name", "unknown"),
        content=getattr(message, "content", "") or "",
        attachment_urls=attachments,
        created_at=getattr(message, "created_at", None),
        jump_url=getattr(message, "jump_url", None),
    )


def format_status(config: GuildConfig) -> str:
    """One human-readable summary of a guild's config (for /dellog status)."""
    channel = (
        f"<#{config.log_channel_id}>" if config.log_channel_id else "not set"
    )
    ignored = (
        ", ".join(f"<#{c}>" for c in sorted(config.ignored_channel_ids))
        or "none"
    )
    lines = [
        f"Log channel: {channel}",
        f"Deleted messages: {'on' if config.log_deletes else 'off'}",
        f"Edited messages: {'on' if config.log_edits else 'off'}",
        f"Ignore bots: {'on' if config.ignore_bots else 'off'}",
        f"Attachments: {'on' if config.include_attachments else 'off'}",
        f"Ignored channels: {ignored}",
    ]
    return "\n".join(lines)


class DelLog(commands.Cog):
    """Log deleted and edited messages to a configurable channel."""

    dellog = app_commands.Group(
        name="dellog", description="Configure message delete/edit logging"
    )
    ignore = app_commands.Group(
        name="ignore",
        description="Channels to skip when logging",
        parent=dellog,
    )

    def __init__(
        self,
        bot: commands.Bot,
        store: ConfigStore | None = None,
        config_path: str = "dellog.json",
    ) -> None:
        self.bot = bot
        if store is not None:
            self.store = store
        else:
            try:
                self.store = ConfigStore(config_path)
            except ConfigError as exc:
                # Never refuse to start over a bad config file; log it and
                # start empty. The next save overwrites the corrupt file,
                # so the owner can recover just by re-running /dellog setup.
                logger.warning("dellog: %s; starting with an empty config", exc)
                self.store = ConfigStore.__new__(ConfigStore)
                self.store.path = Path(config_path)
                self.store._configs = {}

    # -- listeners ------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        guild = getattr(message, "guild", None)
        if guild is None:
            return  # DMs are not logged, ever.
        config = self.store.get(guild.id)
        if not should_log(
            config,
            "delete",
            is_bot=bool(getattr(message.author, "bot", False)),
            channel_id=message.channel.id,
            author_id=message.author.id,
        ):
            return
        await self._send(
            config,
            delete_embed(
                snapshot_from_message(message),
                include_attachments=config.include_attachments,
            ),
        )

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        guild = getattr(before, "guild", None)
        if guild is None:
            return
        # Embed-only updates (link previews loading, etc.) fire this event
        # with identical text. Logging those would spam the mod channel.
        if before.content == after.content:
            return
        config = self.store.get(guild.id)
        if not should_log(
            config,
            "edit",
            is_bot=bool(getattr(before.author, "bot", False)),
            channel_id=before.channel.id,
            author_id=before.author.id,
        ):
            return
        await self._send(
            config,
            edit_embed(
                snapshot_from_message(before),
                snapshot_from_message(after),
                include_attachments=config.include_attachments,
            ),
        )

    @commands.Cog.listener()
    async def on_bulk_message_delete(
        self, messages: list[discord.Message]
    ) -> None:
        if not messages:
            return
        first = messages[0]
        guild = getattr(first, "guild", None)
        if guild is None:
            return
        config = self.store.get(guild.id)
        if config.log_channel_id is None or not config.log_deletes:
            return
        if first.channel.id in config.ignored_channel_ids:
            return
        await self._send(
            config,
            bulk_delete_embed(
                first.channel.id,
                getattr(first.channel, "name", "unknown"),
                len(messages),
            ),
        )

    async def _send(self, config: GuildConfig, embed: discord.Embed) -> None:
        """Deliver one embed to the log channel, never raising."""
        if config.log_channel_id is None:
            return
        channel = self.bot.get_channel(config.log_channel_id)
        if channel is None:
            return
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("dellog: could not send to log channel: %s", exc)

    # -- slash commands ---------------------------------------------------

    @dellog.command(name="setup", description="Set the channel logs go to")
    @app_commands.describe(channel="The channel deleted/edited messages get logged in")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_command(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        config = self.store.get(interaction.guild_id)  # type: ignore[arg-type]
        config.log_channel_id = channel.id
        self.store.save()
        await interaction.response.send_message(
            f"Logs will now go to {channel.mention}.", ephemeral=True
        )

    @ignore.command(name="add", description="Stop logging one channel")
    @app_commands.describe(channel="Channel to ignore")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ignore_add(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        config = self.store.get(interaction.guild_id)  # type: ignore[arg-type]
        config.ignored_channel_ids.add(channel.id)
        self.store.save()
        await interaction.response.send_message(
            f"Ignoring {channel.mention} from now on.", ephemeral=True
        )

    @ignore.command(name="remove", description="Start logging a channel again")
    @app_commands.describe(channel="Channel to un-ignore")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ignore_remove(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        config = self.store.get(interaction.guild_id)  # type: ignore[arg-type]
        config.ignored_channel_ids.discard(channel.id)
        self.store.save()
        await interaction.response.send_message(
            f"Logging {channel.mention} again.", ephemeral=True
        )

    @dellog.command(name="toggle", description="Turn delete or edit logging on/off")
    @app_commands.describe(kind="Which kind of logging to toggle")
    @app_commands.choices(
        kind=[
            app_commands.Choice(name="deletes", value="delete"),
            app_commands.Choice(name="edits", value="edit"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle(
        self, interaction: discord.Interaction, kind: app_commands.Choice[str]
    ) -> None:
        config = self.store.get(interaction.guild_id)  # type: ignore[arg-type]
        if kind.value == "delete":
            config.log_deletes = not config.log_deletes
            state = config.log_deletes
        else:
            config.log_edits = not config.log_edits
            state = config.log_edits
        self.store.save()
        await interaction.response.send_message(
            f"{kind.name} logging is now {'on' if state else 'off'}.",
            ephemeral=True,
        )

    @dellog.command(name="status", description="Show the current logging setup")
    async def status(self, interaction: discord.Interaction) -> None:
        config = self.store.get(interaction.guild_id)  # type: ignore[arg-type]
        await interaction.response.send_message(
            format_status(config), ephemeral=True
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "You need Manage Server to change logging settings."
        else:
            message = "Something went wrong running that command."
            logger.warning("dellog command error: %s", error)
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Extension entry point: `await bot.load_extension("dellog")`."""
    await bot.add_cog(DelLog(bot))
