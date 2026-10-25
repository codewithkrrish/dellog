"""Per-guild configuration for dellog, stored as JSON on disk.

The store is deliberately boring: one JSON file, one dict per guild, writes
go through a temp file plus rename so a crash mid-save can't corrupt the
whole config. If the file is corrupt we raise instead of silently wiping
someone's setup — the cog catches that, logs it, and starts fresh.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    """Raised when the config file exists but can't be read or parsed."""


@dataclass
class GuildConfig:
    """What one server wants logged, and where."""

    log_channel_id: int | None = None
    ignored_channel_ids: set[int] = field(default_factory=set)
    ignored_user_ids: set[int] = field(default_factory=set)
    log_deletes: bool = True
    log_edits: bool = True
    ignore_bots: bool = True
    include_attachments: bool = True

    def to_dict(self) -> dict:
        return {
            "log_channel_id": self.log_channel_id,
            "ignored_channel_ids": sorted(self.ignored_channel_ids),
            "ignored_user_ids": sorted(self.ignored_user_ids),
            "log_deletes": self.log_deletes,
            "log_edits": self.log_edits,
            "ignore_bots": self.ignore_bots,
            "include_attachments": self.include_attachments,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GuildConfig":
        # Unknown keys are ignored on purpose: older/newer versions of this
        # file shouldn't crash each other.
        return cls(
            log_channel_id=data.get("log_channel_id"),
            ignored_channel_ids=set(data.get("ignored_channel_ids", [])),
            ignored_user_ids=set(data.get("ignored_user_ids", [])),
            log_deletes=data.get("log_deletes", True),
            log_edits=data.get("log_edits", True),
            ignore_bots=data.get("ignore_bots", True),
            include_attachments=data.get("include_attachments", True),
        )


class ConfigStore:
    """Loads and saves guild configs from a single JSON file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._configs: dict[int, GuildConfig] = {}
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"Config file {self.path} is not valid JSON: {exc}"
            ) from exc
        except OSError as exc:
            raise ConfigError(f"Could not read config file {self.path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"Config file {self.path} must hold a JSON object")
        for guild_id, data in raw.items():
            try:
                self._configs[int(guild_id)] = GuildConfig.from_dict(data)
            except (TypeError, ValueError, AttributeError):
                # One bad guild entry shouldn't take down every other server.
                continue

    def get(self, guild_id: int) -> GuildConfig:
        """Return the config for a guild, creating a default one if needed."""
        return self._configs.setdefault(guild_id, GuildConfig())

    def save(self) -> None:
        """Write all configs atomically (temp file + rename)."""
        payload = {
            str(guild_id): config.to_dict()
            for guild_id, config in self._configs.items()
        }
        text = json.dumps(payload, indent=2, sort_keys=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=self.path.name + ".", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
