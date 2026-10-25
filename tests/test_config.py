"""Tests for the JSON config store."""

import json

import pytest

from dellog.config import ConfigError, ConfigStore, GuildConfig


def test_defaults_are_sane():
    config = GuildConfig()
    assert config.log_channel_id is None
    assert config.log_deletes is True
    assert config.log_edits is True
    assert config.ignore_bots is True
    assert config.include_attachments is True
    assert config.ignored_channel_ids == set()


def test_round_trip(tmp_path):
    path = tmp_path / "dellog.json"
    store = ConfigStore(path)
    config = store.get(123)
    config.log_channel_id = 999
    config.ignored_channel_ids = {11, 22}
    config.log_edits = False
    store.save()

    reloaded = ConfigStore(path)
    again = reloaded.get(123)
    assert again.log_channel_id == 999
    assert again.ignored_channel_ids == {11, 22}
    assert again.log_edits is False
    assert again.log_deletes is True  # untouched default survives


def test_save_leaves_no_temp_files(tmp_path):
    path = tmp_path / "dellog.json"
    store = ConfigStore(path)
    store.get(1).log_channel_id = 5
    store.save()
    store.get(2).log_channel_id = 6
    store.save()
    leftovers = [p for p in tmp_path.iterdir() if p.name != "dellog.json"]
    assert leftovers == []


def test_save_overwrites_previous_file(tmp_path):
    path = tmp_path / "dellog.json"
    path.write_text('{"1": {"log_channel_id": 1}}', encoding="utf-8")
    store = ConfigStore(path)
    store.get(1).log_channel_id = 42
    store.save()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["1"]["log_channel_id"] == 42


def test_corrupt_file_raises(tmp_path):
    path = tmp_path / "dellog.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        ConfigStore(path)


def test_non_object_file_raises(tmp_path):
    path = tmp_path / "dellog.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ConfigError):
        ConfigStore(path)


def test_one_bad_guild_entry_does_not_kill_the_rest(tmp_path):
    path = tmp_path / "dellog.json"
    path.write_text(
        json.dumps({"1": {"log_channel_id": 10}, "2": "garbage"}),
        encoding="utf-8",
    )
    store = ConfigStore(path)
    assert store.get(1).log_channel_id == 10


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "dellog.json"
    path.write_text(
        json.dumps({"7": {"log_channel_id": 3, "future_option": True}}),
        encoding="utf-8",
    )
    store = ConfigStore(path)
    assert store.get(7).log_channel_id == 3
