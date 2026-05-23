from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class ChannelConfig:
    guild_id: str = ""
    channel_id: str = ""
    name: str = "Unnamed"
    enabled: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "ChannelConfig":
        return cls(
            guild_id=str(data.get("guild_id", "")),
            channel_id=str(data.get("channel_id", "")),
            name=str(data.get("name", "Unnamed") or "Unnamed"),
            enabled=bool(data.get("enabled", False)),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SnipeProfile:
    name: str = "Global"
    category: str = "Biomes"
    enabled: bool = False
    locked: bool = False
    use_regex: bool = False
    trigger_keywords: list[str] = field(default_factory=list)
    blacklist_keywords: list[str] = field(default_factory=list)
    verify_biome_name: str = ""
    kill_on_wrong_biome: bool = True
    priority: int = 0
    bypass_cooldown: bool = False
    sound_alert_path: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "SnipeProfile":
        return cls(
            name=str(data.get("name", "Unnamed") or "Unnamed"),
            category=str(data.get("category", "Biomes") or "Biomes"),
            enabled=bool(data.get("enabled", False)),
            locked=bool(data.get("locked", False)),
            use_regex=bool(data.get("use_regex", False)),
            trigger_keywords=list(data.get("trigger_keywords", [])),
            blacklist_keywords=list(data.get("blacklist_keywords", [])),
            verify_biome_name=str(data.get("verify_biome_name", "")),
            kill_on_wrong_biome=bool(data.get("kill_on_wrong_biome", True)),
            priority=int(data.get("priority", 0)),
            bypass_cooldown=bool(data.get("bypass_cooldown", False)),
            sound_alert_path=str(data.get("sound_alert_path", "")),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WebhookConfig:
    url: str = ""
    enabled: bool = False
    on_snipe: bool = True
    on_biome: bool = True
    on_start: bool = False
    on_stop: bool = False
    ping_type: str = "none"
    ping_target: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "WebhookConfig":
        fields = cls.__dataclass_fields__
        return cls(**{key: value for key, value in data.items() if key in fields})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AppConfig:
    token: str = ""
    monitored_channels: list[ChannelConfig] = field(default_factory=list)
    profiles: list[SnipeProfile] = field(default_factory=list)
    auto_join_enabled: bool = True
    auto_join_delay_ms: int = 0
    pause_after_snipe_s: int = 0
    close_roblox_before_join: bool = False
    biome_leave_action: str = "none"
    anti_bait_enabled: bool = True
    link_resolve_enabled: bool = True
    theme: str = "dark"
    dev_mode: bool = False
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    cooldown_guild_ttl: float = 30.0
    cooldown_profile_ttl: float = 0.0
    cooldown_link_ttl: float = 10.0
    sound_alert_enabled: bool = False
    sound_alert_path: str = ""
    sound_alert_freq: int = 1000
    sound_alert_dur_ms: int = 200
    desktop_notifications_enabled: bool = True
    desktop_on_snipe: bool = True
    desktop_on_error: bool = True
    desktop_on_update: bool = True
    delete_watch_seconds: int = 0
    extra_tokens: list[str] = field(default_factory=list)


@dataclass
class BlacklistEntry:
    user_id: str
    username: str = "unknown"
    reason: str = "manual"
    count: int = 1
    last_event: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_dict(cls, user_id: str, data: dict) -> "BlacklistEntry":
        return cls(
            user_id=user_id,
            username=str(data.get("username", "unknown")),
            reason=str(data.get("reason", "manual")),
            count=int(data.get("count", 1)),
            last_event=str(data.get("last_event", "")) or datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "reason": self.reason,
            "count": self.count,
            "last_event": self.last_event,
        }


@dataclass
class SnipeHistoryEntry:
    profile: str
    keyword: str = ""
    author: str = ""
    raw_message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    biome_verified: bool | None = None
    expected_biome: str = ""
    detected_biome: str = ""
    roblox_url: str = ""
    jump_url: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "SnipeHistoryEntry":
        return cls(
            profile=str(data.get("profile", "?")),
            keyword=str(data.get("keyword", "")),
            author=str(data.get("author", data.get("author_display", ""))),
            raw_message=str(data.get("raw_message", "")),
            timestamp=str(data.get("timestamp", data.get("timestamp_iso", ""))) or datetime.now(timezone.utc).isoformat(),
            biome_verified=data.get("biome_verified"),
            expected_biome=str(data.get("expected_biome", data.get("verify_biome_name", ""))),
            detected_biome=str(data.get("detected_biome", "")),
            roblox_url=str(data.get("roblox_url", data.get("roblox_web_url", data.get("uri", "")))),
            jump_url=str(data.get("jump_url", "")),
        )

    def to_dict(self) -> dict:
        return asdict(self)
