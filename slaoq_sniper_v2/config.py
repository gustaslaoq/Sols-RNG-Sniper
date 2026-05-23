from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from slaoq_sniper_v2.app_paths import config_path
from slaoq_sniper_v2.models import AppConfig, ChannelConfig, SnipeProfile, WebhookConfig


DEFAULT_SOL_RNG_GUILD_ID = "1186570213077041233"
DEFAULT_SOL_RNG_CHANNELS = (
    ("1282542323590496277", "Sol's RNG > #1282542323590496277"),
    ("1282543762425516083", "Sol's RNG > #1282543762425516083"),
)


def default_channels() -> list[ChannelConfig]:
    return [
        ChannelConfig(
            guild_id=DEFAULT_SOL_RNG_GUILD_ID,
            channel_id=channel_id,
            name=name,
            enabled=True,
        )
        for channel_id, name in DEFAULT_SOL_RNG_CHANNELS
    ]


def default_profiles() -> list[SnipeProfile]:
    profiles = [
        SnipeProfile(
            name="Global",
            category="System",
            locked=True,
            enabled=False,
            trigger_keywords=[],
            blacklist_keywords=["ended", "bait", "fake", "over", "closed", "gone"],
            verify_biome_name="",
            kill_on_wrong_biome=False,
        )
    ]

    for name, biome, triggers in (
        ("Dreamspace", "DREAMSPACE", ["dreamspace", "dream space"]),
        ("Cyberspace", "CYBERSPACE", ["cyberspace", "cyber space"]),
        ("Glitched", "GLITCHED", ["glitched", "glitch"]),
    ):
        profiles.append(
            SnipeProfile(
                name=name,
                category="Biomes",
                enabled=False,
                trigger_keywords=triggers,
                verify_biome_name=biome,
                kill_on_wrong_biome=True,
            )
        )

    for name, triggers in (
        ("Mari", ["mari", "mari merchant"]),
        ("Jester", ["jester", "jester merchant"]),
        ("Rin", ["rin", "rin merchant"]),
    ):
        profiles.append(
            SnipeProfile(
                name=name,
                category="Merchants",
                enabled=False,
                trigger_keywords=triggers,
                kill_on_wrong_biome=False,
            )
        )

    for name, triggers in (
        ("Void Coin", ["void coin", "voidcoin", "vc"]),
        ("Oblivion Potion", ["oblivion potion", "oblivion", "obliv"]),
    ):
        profiles.append(
            SnipeProfile(
                name=name,
                category="Items",
                enabled=False,
                trigger_keywords=triggers,
                kill_on_wrong_biome=False,
            )
        )

    return profiles


def default_config() -> AppConfig:
    return AppConfig(
        monitored_channels=default_channels(),
        profiles=default_profiles(),
    )


def profile_category_for_name(name: str) -> str:
    normalized = name.strip().lower()
    if normalized == "global":
        return "System"
    if normalized in {"dreamspace", "cyberspace", "glitched"}:
        return "Biomes"
    if normalized in {"mari", "jester", "rin"}:
        return "Merchants"
    if normalized in {"void coin", "oblivion potion"}:
        return "Items"
    return "Custom"


def normalize_profiles(profiles: list[SnipeProfile]) -> list[SnipeProfile]:
    existing_names = {profile.name.strip().lower() for profile in profiles}
    for profile in profiles:
        if not profile.category or profile.category == "Biomes" and profile.verify_biome_name == "":
            profile.category = profile_category_for_name(profile.name)

    for default in default_profiles():
        key = default.name.strip().lower()
        if key not in existing_names:
            profiles.append(default)
            existing_names.add(key)

    profiles.sort(key=_profile_sort_key)
    return profiles


def _profile_sort_key(profile: SnipeProfile) -> tuple[int, int, str]:
    category_order = {
        "System": 0,
        "Biomes": 1,
        "Merchants": 2,
        "Items": 3,
        "Custom": 4,
    }
    default_order = {
        "global": 0,
        "dreamspace": 1,
        "cyberspace": 2,
        "glitched": 3,
        "mari": 4,
        "jester": 5,
        "rin": 6,
        "void coin": 7,
        "oblivion potion": 8,
    }
    name = profile.name.strip().lower()
    return (category_order.get(profile.category, 9), default_order.get(name, 99), profile.name.lower())


def config_to_dict(config: AppConfig) -> dict:
    return {
        "schema_version": 2,
        "token": config.token,
        "monitored_channels": [channel.to_dict() for channel in config.monitored_channels],
        "profiles": [profile.to_dict() for profile in config.profiles],
        "auto_join_enabled": config.auto_join_enabled,
        "auto_join_delay_ms": config.auto_join_delay_ms,
        "pause_after_snipe_s": config.pause_after_snipe_s,
        "close_roblox_before_join": config.close_roblox_before_join,
        "biome_leave_action": config.biome_leave_action,
        "anti_bait_enabled": config.anti_bait_enabled,
        "link_resolve_enabled": config.link_resolve_enabled,
        "theme": config.theme,
        "dev_mode": config.dev_mode,
        "webhook": config.webhook.to_dict(),
        "cooldown": {
            "guild_ttl": config.cooldown_guild_ttl,
            "profile_ttl": config.cooldown_profile_ttl,
            "link_ttl": config.cooldown_link_ttl,
        },
        "sound_alert_enabled": config.sound_alert_enabled,
        "sound_alert_path": config.sound_alert_path,
        "sound_alert_freq": config.sound_alert_freq,
        "sound_alert_dur_ms": config.sound_alert_dur_ms,
        "desktop_notifications_enabled": config.desktop_notifications_enabled,
        "desktop_on_snipe": config.desktop_on_snipe,
        "desktop_on_error": config.desktop_on_error,
        "desktop_on_update": config.desktop_on_update,
        "delete_watch_seconds": config.delete_watch_seconds,
        "extra_tokens": config.extra_tokens,
    }


def config_from_dict(raw: dict) -> AppConfig:
    if is_legacy_v1_config(raw):
        return _config_from_legacy_v1(raw)

    config = default_config()
    config.token = str(raw.get("token", ""))
    channels_raw = raw.get("monitored_channels")
    if isinstance(channels_raw, list):
        config.monitored_channels = [
            ChannelConfig.from_dict(item) for item in channels_raw if isinstance(item, dict)
        ]

    profiles_raw = raw.get("profiles", [])
    if profiles_raw:
        config.profiles = [SnipeProfile.from_dict(item) for item in profiles_raw if isinstance(item, dict)]
    if not config.profiles or config.profiles[0].name != "Global":
        config.profiles.insert(0, default_profiles()[0])
    config.profiles = normalize_profiles(config.profiles)

    config.auto_join_enabled = bool(raw.get("auto_join_enabled", config.auto_join_enabled))
    config.auto_join_delay_ms = int(raw.get("auto_join_delay_ms", config.auto_join_delay_ms))
    config.pause_after_snipe_s = int(raw.get("pause_after_snipe_s", config.pause_after_snipe_s))
    config.close_roblox_before_join = bool(raw.get("close_roblox_before_join", config.close_roblox_before_join))
    config.biome_leave_action = str(raw.get("biome_leave_action", config.biome_leave_action))
    config.anti_bait_enabled = bool(raw.get("anti_bait_enabled", config.anti_bait_enabled))
    config.link_resolve_enabled = bool(raw.get("link_resolve_enabled", config.link_resolve_enabled))
    config.theme = str(raw.get("theme", config.theme))
    config.dev_mode = bool(raw.get("dev_mode", config.dev_mode))
    config.webhook = WebhookConfig.from_dict(raw.get("webhook", {}))

    cooldown = raw.get("cooldown", {})
    config.cooldown_guild_ttl = float(cooldown.get("guild_ttl", config.cooldown_guild_ttl))
    config.cooldown_profile_ttl = float(cooldown.get("profile_ttl", config.cooldown_profile_ttl))
    config.cooldown_link_ttl = float(cooldown.get("link_ttl", config.cooldown_link_ttl))

    config.sound_alert_enabled = bool(raw.get("sound_alert_enabled", config.sound_alert_enabled))
    config.sound_alert_path = str(raw.get("sound_alert_path", config.sound_alert_path))
    config.sound_alert_freq = int(raw.get("sound_alert_freq", config.sound_alert_freq))
    config.sound_alert_dur_ms = int(raw.get("sound_alert_dur_ms", config.sound_alert_dur_ms))
    config.desktop_notifications_enabled = bool(raw.get("desktop_notifications_enabled", config.desktop_notifications_enabled))
    config.desktop_on_snipe = bool(raw.get("desktop_on_snipe", config.desktop_on_snipe))
    config.desktop_on_error = bool(raw.get("desktop_on_error", config.desktop_on_error))
    config.desktop_on_update = bool(raw.get("desktop_on_update", config.desktop_on_update))
    config.delete_watch_seconds = int(raw.get("delete_watch_seconds", config.delete_watch_seconds))
    config.extra_tokens = list(raw.get("extra_tokens", []))
    return config


def is_legacy_v1_config(raw: dict) -> bool:
    if int(raw.get("schema_version", 0) or 0) >= 2:
        return False
    profiles = raw.get("profiles", [])
    has_uncategorized_profiles = any(isinstance(profile, dict) and "category" not in profile for profile in profiles)
    legacy_keys = {
        "auto_play_enabled",
        "auto_play_fullscreen",
        "hotkey_toggle_key",
        "hotkey_toggle_en",
        "hotkey_pause_key",
        "hotkey_pause_en",
        "hotkey_pause_dur",
        "log_to_file",
        "log_tail_bytes",
    }
    return has_uncategorized_profiles or any(key in raw for key in legacy_keys)


def _config_from_legacy_v1(raw: dict) -> AppConfig:
    config = default_config()
    config.token = str(raw.get("token", ""))
    channels_raw = raw.get("monitored_channels")
    if isinstance(channels_raw, list):
        config.monitored_channels = [
            ChannelConfig.from_dict(item) for item in channels_raw if isinstance(item, dict)
        ]
    config.auto_join_enabled = bool(raw.get("auto_join_enabled", config.auto_join_enabled))
    config.auto_join_delay_ms = int(raw.get("auto_join_delay_ms", config.auto_join_delay_ms))
    config.pause_after_snipe_s = int(raw.get("pause_after_snipe_s", config.pause_after_snipe_s))
    config.close_roblox_before_join = bool(
        raw.get("close_roblox_before_join", raw.get("close_roblox_after_join", config.close_roblox_before_join))
    )
    config.biome_leave_action = str(raw.get("biome_leave_action", config.biome_leave_action))
    config.anti_bait_enabled = bool(raw.get("anti_bait_enabled", config.anti_bait_enabled))
    config.link_resolve_enabled = bool(raw.get("link_resolve_enabled", config.link_resolve_enabled))
    config.theme = str(raw.get("theme", config.theme))
    config.dev_mode = bool(raw.get("dev_mode", config.dev_mode))
    config.webhook = WebhookConfig.from_dict(raw.get("webhook", {}))

    cooldown = raw.get("cooldown", {})
    config.cooldown_guild_ttl = float(cooldown.get("guild_ttl", config.cooldown_guild_ttl))
    config.cooldown_profile_ttl = float(cooldown.get("profile_ttl", config.cooldown_profile_ttl))
    config.cooldown_link_ttl = float(cooldown.get("link_ttl", config.cooldown_link_ttl))

    config.sound_alert_enabled = bool(raw.get("sound_alert_enabled", config.sound_alert_enabled))
    config.sound_alert_path = str(raw.get("sound_alert_path", config.sound_alert_path))
    config.sound_alert_freq = int(raw.get("sound_alert_freq", config.sound_alert_freq))
    config.sound_alert_dur_ms = int(raw.get("sound_alert_dur_ms", config.sound_alert_dur_ms))
    config.desktop_notifications_enabled = bool(raw.get("desktop_notifications_enabled", config.desktop_notifications_enabled))
    config.desktop_on_snipe = bool(raw.get("desktop_on_snipe", config.desktop_on_snipe))
    config.desktop_on_error = bool(raw.get("desktop_on_error", config.desktop_on_error))
    config.desktop_on_update = bool(raw.get("desktop_on_update", config.desktop_on_update))
    config.delete_watch_seconds = int(raw.get("delete_watch_seconds", config.delete_watch_seconds))
    config.extra_tokens = list(raw.get("extra_tokens", []))
    return config


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_path()
        self.config = self.load()

    def load(self) -> AppConfig:
        self._migrate_legacy_config()
        try:
            with self.path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except FileNotFoundError:
            return default_config()
        except json.JSONDecodeError:
            corrupt_path = self.path.with_suffix(".json.corrupt")
            shutil.move(str(self.path), str(corrupt_path))
            return default_config()
        config = config_from_dict(raw)
        if int(raw.get("schema_version", 0) or 0) < 2:
            self.config = config
            self.save()
        return config

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(config_to_dict(self.config), file, indent=2, ensure_ascii=False)
        temp_path.replace(self.path)

    def _migrate_legacy_config(self) -> None:
        if self.path.exists():
            return
        for legacy in _legacy_file_candidates("config.json"):
            if legacy.exists() and legacy.resolve() != self.path.resolve():
                self.path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy, self.path)
                return


def _legacy_file_candidates(filename: str) -> list[Path]:
    candidates = [
        Path.cwd() / filename,
        Path(sys.executable).resolve().parent / filename,
        Path.home() / ".config" / "slaoq-sniper" / filename,
    ]
    return candidates
