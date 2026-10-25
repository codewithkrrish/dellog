"""Embed builders for dellog.

These take plain data (MessageSnapshot), not discord objects, so the
formatting logic is testable without a bot, a gateway, or mocks of half
of discord.py. The cog converts real messages into snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import discord

# Discord caps a single embed field at 1024 characters.
FIELD_LIMIT = 1024
DELETE_COLOR = 0xE74C3C
EDIT_COLOR = 0xE67E22
BULK_COLOR = 0x95A5A6
NO_CONTENT = "(no text content)"


@dataclass
class MessageSnapshot:
    """The parts of a message we actually put in a log embed."""

    author_name: str
    author_id: int
    author_avatar_url: str | None
    channel_id: int
    channel_name: str
    content: str
    attachment_urls: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    jump_url: str | None = None


def truncate(text: str, limit: int = FIELD_LIMIT) -> str:
    """Cut text to Discord's field limit, keeping it obvious it was cut."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _base_embed(snapshot: MessageSnapshot, title: str, color: int) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.set_author(name=f"{snapshot.author_name} ({snapshot.author_id})")
    if snapshot.author_avatar_url:
        embed.set_thumbnail(url=snapshot.author_avatar_url)
    if snapshot.created_at is not None:
        embed.timestamp = snapshot.created_at
    return embed


def _add_common_fields(
    embed: discord.Embed, snapshot: MessageSnapshot, *, include_attachments: bool
) -> None:
    embed.add_field(
        name="Channel", value=f"<#{snapshot.channel_id}>", inline=True
    )
    embed.add_field(
        name="Author", value=f"<@{snapshot.author_id}>", inline=True
    )
    if include_attachments and snapshot.attachment_urls:
        shown = snapshot.attachment_urls[:5]
        embed.add_field(
            name=f"Attachments ({len(snapshot.attachment_urls)})",
            value="\n".join(shown),
            inline=False,
        )


def delete_embed(
    snapshot: MessageSnapshot, *, include_attachments: bool = True
) -> discord.Embed:
    """Embed for a message that was deleted."""
    embed = _base_embed(snapshot, "Message deleted", DELETE_COLOR)
    embed.add_field(
        name="Content",
        value=truncate(snapshot.content) if snapshot.content else NO_CONTENT,
        inline=False,
    )
    _add_common_fields(embed, snapshot, include_attachments=include_attachments)
    return embed


def edit_embed(
    before: MessageSnapshot,
    after: MessageSnapshot,
    *,
    include_attachments: bool = True,
) -> discord.Embed:
    """Embed for a message that was edited (before/after side by side)."""
    embed = _base_embed(before, "Message edited", EDIT_COLOR)
    embed.add_field(
        name="Before",
        value=truncate(before.content) if before.content else NO_CONTENT,
        inline=False,
    )
    embed.add_field(
        name="After",
        value=truncate(after.content) if after.content else NO_CONTENT,
        inline=False,
    )
    if before.jump_url:
        embed.add_field(name="Jump to message", value=before.jump_url, inline=False)
    _add_common_fields(embed, before, include_attachments=include_attachments)
    return embed


def bulk_delete_embed(
    channel_id: int, channel_name: str, count: int
) -> discord.Embed:
    """Summary embed for a bulk delete (individual messages aren't cached)."""
    embed = discord.Embed(
        title="Bulk message delete",
        description=f"{count} message{'s' if count != 1 else ''} deleted "
        f"in <#{channel_id}> (#{channel_name}).",
        color=BULK_COLOR,
    )
    return embed
