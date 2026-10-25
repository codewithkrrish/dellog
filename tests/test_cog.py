"""Tests for the cog's decision logic and listeners.

No real bot, no gateway: messages and channels are simple stand-ins with
the same attributes the cog reads.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from dellog.cog import DelLog, format_status, should_log, snapshot_from_message
from dellog.config import ConfigStore, GuildConfig


# -- helpers --------------------------------------------------------------


def make_message(**overrides):
    base = dict(
        guild=SimpleNamespace(id=1),
        channel=SimpleNamespace(id=10, name="general"),
        author=SimpleNamespace(
            id=42,
            display_name="SomeUser",
            bot=False,
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        ),
        content="hello",
        attachments=[],
        created_at=None,
        jump_url="https://discord.com/jump",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_cog(tmp_path, channel=None):
    store = ConfigStore(tmp_path / "dellog.json")
    bot = SimpleNamespace(get_channel=lambda cid: channel)
    cog = DelLog(bot, store=store)
    return cog, store


def enable_logging(store):
    store.get(1).log_channel_id = 99


# -- should_log -----------------------------------------------------------


def test_should_log_happy_path():
    config = GuildConfig(log_channel_id=99)
    assert should_log(
        config, "delete", is_bot=False, channel_id=10, author_id=42
    )


def test_no_log_channel_means_no_logging():
    config = GuildConfig(log_channel_id=None)
    assert not should_log(
        config, "delete", is_bot=False, channel_id=10, author_id=42
    )


def test_toggles_are_respected():
    config = GuildConfig(log_channel_id=99, log_deletes=False)
    assert not should_log(
        config, "delete", is_bot=False, channel_id=10, author_id=42
    )
    assert should_log(
        config, "edit", is_bot=False, channel_id=10, author_id=42
    )
    config.log_edits = False
    assert not should_log(
        config, "edit", is_bot=False, channel_id=10, author_id=42
    )


def test_bots_ignored_by_default_but_not_when_disabled():
    config = GuildConfig(log_channel_id=99)
    assert not should_log(
        config, "delete", is_bot=True, channel_id=10, author_id=42
    )
    config.ignore_bots = False
    assert should_log(
        config, "delete", is_bot=True, channel_id=10, author_id=42
    )


def test_ignored_channel_and_user():
    config = GuildConfig(
        log_channel_id=99, ignored_channel_ids={10}, ignored_user_ids={7}
    )
    assert not should_log(
        config, "delete", is_bot=False, channel_id=10, author_id=42
    )
    assert not should_log(
        config, "delete", is_bot=False, channel_id=11, author_id=7
    )
    assert should_log(
        config, "delete", is_bot=False, channel_id=11, author_id=42
    )


# -- snapshot conversion ---------------------------------------------------


def test_snapshot_copies_fields():
    message = make_message(content="hi", attachments=[SimpleNamespace(url="u1")])
    snap = snapshot_from_message(message)
    assert snap.content == "hi"
    assert snap.author_id == 42
    assert snap.channel_name == "general"
    assert snap.attachment_urls == ["u1"]
    assert snap.author_avatar_url == "https://example.com/a.png"


# -- listeners ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_listener_sends_embed(tmp_path):
    channel = AsyncMock()
    cog, store = make_cog(tmp_path, channel=channel)
    enable_logging(store)
    await cog.on_message_delete(make_message(content="gone"))
    channel.send.assert_awaited_once()
    embed = channel.send.call_args.kwargs["embed"]
    assert embed.title == "Message deleted"
    assert "gone" in embed.fields[0].value


@pytest.mark.asyncio
async def test_delete_listener_skips_dm(tmp_path):
    channel = AsyncMock()
    cog, store = make_cog(tmp_path, channel=channel)
    enable_logging(store)
    await cog.on_message_delete(make_message(guild=None))
    channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_listener_skips_ignored_channel(tmp_path):
    channel = AsyncMock()
    cog, store = make_cog(tmp_path, channel=channel)
    enable_logging(store)
    store.get(1).ignored_channel_ids.add(10)
    await cog.on_message_delete(make_message())
    channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_listener_skips_bot_messages(tmp_path):
    channel = AsyncMock()
    cog, store = make_cog(tmp_path, channel=channel)
    enable_logging(store)
    bot_author = SimpleNamespace(
        id=43, display_name="Bot", bot=True,
        display_avatar=SimpleNamespace(url="https://example.com/b.png"),
    )
    await cog.on_message_delete(make_message(author=bot_author))
    channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_listener_skips_unchanged_content(tmp_path):
    channel = AsyncMock()
    cog, store = make_cog(tmp_path, channel=channel)
    enable_logging(store)
    before = make_message(content="same")
    after = make_message(content="same")
    await cog.on_message_edit(before, after)
    channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_listener_logs_real_change(tmp_path):
    channel = AsyncMock()
    cog, store = make_cog(tmp_path, channel=channel)
    enable_logging(store)
    await cog.on_message_edit(
        make_message(content="before"), make_message(content="after")
    )
    channel.send.assert_awaited_once()
    embed = channel.send.call_args.kwargs["embed"]
    assert embed.title == "Message edited"


@pytest.mark.asyncio
async def test_bulk_delete_sends_summary(tmp_path):
    channel = AsyncMock()
    cog, store = make_cog(tmp_path, channel=channel)
    enable_logging(store)
    await cog.on_bulk_message_delete([make_message() for _ in range(5)])
    channel.send.assert_awaited_once()
    embed = channel.send.call_args.kwargs["embed"]
    assert "5 messages deleted" in embed.description


@pytest.mark.asyncio
async def test_send_failure_does_not_raise(tmp_path):
    response = Mock()
    response.status = 403
    channel = AsyncMock()
    channel.send.side_effect = discord.Forbidden(response, "no perms")
    cog, store = make_cog(tmp_path, channel=channel)
    enable_logging(store)
    # Must not raise: a logging cog never takes the host bot down.
    await cog.on_message_delete(make_message())


@pytest.mark.asyncio
async def test_missing_log_channel_is_a_noop(tmp_path):
    cog, store = make_cog(tmp_path, channel=None)
    enable_logging(store)
    await cog.on_message_delete(make_message())  # get_channel -> None


# -- status formatting -------------------------------------------------------


def test_format_status_shows_everything():
    config = GuildConfig(
        log_channel_id=99, log_edits=False, ignored_channel_ids={10, 20}
    )
    text = format_status(config)
    assert "<#99>" in text
    assert "Edited messages: off" in text
    assert "<#10>" in text and "<#20>" in text


def test_format_status_without_log_channel():
    assert "not set" in format_status(GuildConfig())
