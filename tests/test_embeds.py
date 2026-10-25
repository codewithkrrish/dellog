"""Tests for the log embed builders."""

from dellog.embeds import (
    FIELD_LIMIT,
    MessageSnapshot,
    bulk_delete_embed,
    delete_embed,
    edit_embed,
    truncate,
)


def snap(**overrides):
    base = dict(
        author_name="SomeUser",
        author_id=42,
        author_avatar_url="https://example.com/avatar.png",
        channel_id=10,
        channel_name="general",
        content="hello world",
    )
    base.update(overrides)
    return MessageSnapshot(**base)


def field(embed, name):
    for f in embed.fields:
        if f.name == name:
            return f.value
    raise AssertionError(f"no field named {name!r}")


def test_delete_embed_basics():
    embed = delete_embed(snap())
    assert embed.title == "Message deleted"
    assert field(embed, "Content") == "hello world"
    assert field(embed, "Channel") == "<#10>"
    assert field(embed, "Author") == "<@42>"


def test_delete_embed_empty_content_gets_placeholder():
    embed = delete_embed(snap(content=""))
    assert field(embed, "Content") == "(no text content)"


def test_long_content_is_truncated_to_field_limit():
    long_text = "x" * (FIELD_LIMIT + 500)
    embed = delete_embed(snap(content=long_text))
    value = field(embed, "Content")
    assert len(value) <= FIELD_LIMIT
    assert value.endswith("…")


def test_truncate_leaves_short_text_alone():
    assert truncate("short") == "short"


def test_attachments_listed_up_to_five():
    urls = [f"https://cdn.example/{i}.png" for i in range(7)]
    embed = delete_embed(snap(attachment_urls=urls))
    value = field(embed, "Attachments (7)")
    assert len(value.splitlines()) == 5


def test_attachments_can_be_hidden():
    embed = delete_embed(
        snap(attachment_urls=["https://cdn.example/1.png"]),
        include_attachments=False,
    )
    names = [f.name for f in embed.fields]
    assert not any("Attachments" in n for n in names)


def test_edit_embed_shows_before_and_after():
    embed = edit_embed(snap(content="old text"), snap(content="new text"))
    assert embed.title == "Message edited"
    assert field(embed, "Before") == "old text"
    assert field(embed, "After") == "new text"


def test_edit_embed_includes_jump_link_when_present():
    embed = edit_embed(
        snap(content="a", jump_url="https://discord.com/jump"),
        snap(content="b"),
    )
    assert field(embed, "Jump to message") == "https://discord.com/jump"


def test_bulk_embed_singular_and_plural():
    one = bulk_delete_embed(10, "general", 1)
    assert "1 message deleted" in one.description
    many = bulk_delete_embed(10, "general", 25)
    assert "25 messages deleted" in many.description
