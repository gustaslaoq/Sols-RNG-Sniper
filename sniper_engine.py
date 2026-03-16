"""
sniper_engine.py — Slaoq's Sniper | Core Engine  v4.1
------------------------------------------------------
Model layer: Discord gateway, link resolver, log reader, process manager.

Changes from v4.0:
  - Removed dependency on core/ and services/ packages
  - BlacklistManager, CooldownManager and PluginLoader are injected
    from outside (passed via constructor) — no circular imports
  - Project is now two-file: main.py + sniper_engine.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque, OrderedDict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Any

import aiohttp
import psutil

logger = logging.getLogger("sniper_engine")

# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class EngineStatus(Enum):
    IDLE       = "idle"
    CONNECTING = "connecting"
    CONNECTED  = "connected"
    SNIPING    = "sniping"
    ERROR      = "error"
    STOPPED    = "stopped"

class LogLevel(Enum):
    INFO    = "INFO"
    SUCCESS = "SUCCESS"
    WARN    = "WARN"
    ERROR   = "ERROR"
    DEBUG   = "DEBUG"
    SNIPE   = "SNIPE"

# ─────────────────────────────────────────────────────────────────────────────
# NETWORK / PATH CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

DISCORD_GATEWAY_URL  = "wss://gateway.discord.gg/?v=10&encoding=json"
DISCORD_API_BASE     = "https://discord.com/api/v10"
LINK_RESOLVE_TIMEOUT = aiohttp.ClientTimeout(total=6, connect=3)
HTTP_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=8, connect=3)
ROBLOX_PROCESS_NAMES = {"RobloxPlayerBeta.exe", "RobloxPlayer.exe", "Windows10Universal.exe",
                        "RobloxPlayer", "Roblox"}

_PLATFORM = platform.system()
if _PLATFORM == "Windows":
    ROBLOX_LOG_PATH = Path(os.getenv("LOCALAPPDATA", "")) / "Roblox" / "logs"
elif _PLATFORM == "Darwin":
    ROBLOX_LOG_PATH = Path.home() / "Library" / "Logs" / "Roblox"
else:  # Linux (via Wine or native client)
    ROBLOX_LOG_PATH = Path.home() / ".local" / "share" / "roblox" / "logs"
LOG_TAIL_BYTES       = 131072  # 128 KB


# ─────────────────────────────────────────────────────────────────────────────
# PRE-COMPILED REGEX PATTERNS
# ─────────────────────────────────────────────────────────────────────────────

class _Patterns:
    ROBLOX_PRIVATE = re.compile(
        r"https?://(?:www\.)?roblox\.com/games/(\d+)/[^\s]*\?privateServerLinkCode=([\w-]+)",
        re.IGNORECASE)

    ROBLOX_INSTANCE = re.compile(
        r"roblox://experiences/start\?placeId=(\d+)&gameInstanceId=([\w-]+)",
        re.IGNORECASE)

    ROBLOX_LAUNCH = re.compile(
        r"https?://(?:www\.)?roblox\.com/games/start\?placeId=(\d+)&launchData=(\d+)/([a-f0-9\-]+)",
        re.IGNORECASE)

    SHARE_URL = re.compile(
        r"https?://(?:www\.)?roblox\.com/share\?code=([a-f0-9]+)&type=Server",
        re.IGNORECASE)

    SHORT_URL = re.compile(
        r"https?://(?:rb\.gy|bit\.ly|tinyurl\.com|t\.co|discord\.gg|discord\.com/invite|isgd\.it|cutt\.ly)/[\w/-]+",
        re.IGNORECASE)

    # Compiled once — ordered from most specific to fallback
    BIOME_PATTERNS = [
        re.compile(r"'hoverText'\s*:\s*'([^']+)'", re.IGNORECASE),
        re.compile(r'"hoverText"\s*:\s*"([^"]+)"', re.IGNORECASE),
        re.compile(r"'largeImage'\s*:\s*\{[^}]*'hoverText'\s*:\s*'([^']+)'", re.IGNORECASE),
        re.compile(r'"largeImage"\s*:\s*\{[^}]*"hoverText"\s*:\s*"([^"]+)"', re.IGNORECASE),
        re.compile(r'"largeImage"\s*:\s*\{[^}]*\'hoverText\'\s*:\s*\'([^\']+)\'', re.IGNORECASE),
        re.compile(r"'largeImage'\s*:\s*\{[^}]*\"hoverText\"\s*:\s*\"([^\"]+)\"", re.IGNORECASE),
        re.compile(r'hoverText=([^\s,}\]]+)', re.IGNORECASE),
        re.compile(r'hoverText:\s*([^\s,}\]]+)', re.IGNORECASE),
        re.compile(r'hoverText["\']?\s*[:=]\s*["\']([^"\']+)["\']', re.IGNORECASE),
        re.compile(
            r'\b(NORMAL|GLITCHED|DREAMSPACE|CYBERSPACE|NULL|STARLIGHT|HEAVEN|CORRUPTED|ABYSSAL)\b',
            re.IGNORECASE),
    ]

    BIOME_DIRECT = frozenset([
        "NORMAL", "GLITCHED", "DREAMSPACE", "CYBERSPACE",
        "NULL", "STARLIGHT", "HEAVEN", "CORRUPTED", "ABYSSAL",
    ])


PATTERNS = _Patterns()


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-PLATFORM SOUND
# ─────────────────────────────────────────────────────────────────────────────

def play_sound(freq: int = 1000, duration_ms: int = 200, filepath: str = "") -> None:
    """Play a sound alert in a fire-and-forget manner.

    Priority order:
      1. If *filepath* is given and the file exists → play via platform player.
      2. Otherwise → synthesised beep (winsound on Windows, afplay/paplay/aplay on others).
    """
    system = platform.system()

    # ── custom file ──────────────────────────────────────────────────────────
    if filepath and Path(filepath).exists():
        try:
            if system == "Windows":
                import winsound
                winsound.PlaySound(filepath, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif system == "Darwin":
                subprocess.Popen(["afplay", filepath],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                # Try paplay (PulseAudio), then aplay (ALSA), then pacat
                for cmd in (["paplay", filepath], ["aplay", filepath]):
                    try:
                        subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
                        break
                    except FileNotFoundError:
                        continue
        except Exception:
            pass
        return

    # ── synthesised beep ─────────────────────────────────────────────────────
    try:
        if system == "Windows":
            import winsound
            winsound.Beep(max(37, min(32767, freq)), max(1, duration_ms))
        elif system == "Darwin":
            # Generate a raw PCM beep and pipe it to afplay
            import math, struct
            rate    = 44100
            samples = int(rate * duration_ms / 1000)
            data    = b"".join(
                struct.pack("<h", int(32767 * math.sin(2 * math.pi * freq * t / rate)))
                for t in range(samples)
            )
            proc = subprocess.Popen(
                ["afplay", "-f", "AIFF", "-r", str(rate), "-c", "1", "-b", "16", "-"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.stdin.write(data)
            proc.stdin.close()
        else:
            # Linux: try speaker-test beep via paplay with /dev/urandom fallback
            try:
                import math, struct
                rate    = 44100
                samples = int(rate * duration_ms / 1000)
                data    = b"".join(
                    struct.pack("<h", int(32767 * math.sin(2 * math.pi * freq * t / rate)))
                    for t in range(samples)
                )
                proc = subprocess.Popen(
                    ["paplay", "--raw", "--format=s16le",
                     f"--rate={rate}", "--channels=1"],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
                proc.stdin.write(data)
                proc.stdin.close()
            except (FileNotFoundError, OSError):
                subprocess.Popen(
                    ["aplay", "-q", "-f", "S16_LE", "-r", str(rate), "-c", "1", "-"],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL).stdin.write(data)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

def get_app_dir() -> Path:
    """Single canonical app directory — LOCALAPPDATA/SlaoqSniper on Windows."""
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA", "")) / "SlaoqSniper"
    else:
        base = Path.home() / ".config" / "slaoq-sniper"
    base.mkdir(parents=True, exist_ok=True)
    return base

def get_config_path() -> Path:
    return get_app_dir() / "config.json"

def get_log_path() -> Path:
    p = get_app_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p / "sniper.log"

def get_crash_log_dir() -> Path:
    p = get_app_dir() / "crash_logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class ChannelConfig:
    guild_id:   str  = ""
    channel_id: str  = ""
    name:       str  = "Unnamed"
    enabled:    bool = True


@dataclass
class SnipeProfile:
    name:                str       = "Global"
    enabled:             bool      = True
    locked:              bool      = False
    use_regex:           bool      = False
    trigger_keywords:    list      = field(default_factory=list)
    blacklist_keywords:  list      = field(default_factory=list)
    verify_biome_name:   str       = ""
    kill_on_wrong_biome: bool      = True
    priority:            int       = 0       # lower number = evaluated first; 0 = default
    bypass_cooldown:     bool      = False   # priority profiles can skip cooldowns
    sound_alert_path:    str       = ""      # custom audio file per profile (empty = global beep)
    _compiled_triggers:  list      = field(default_factory=list, repr=False, compare=False)
    _compiled_blacklist: list      = field(default_factory=list, repr=False, compare=False)
    _patterns_dirty:     bool      = field(default=True,         repr=False, compare=False)

    def compile(self):
        flag = re.IGNORECASE

        def _make(kws: list) -> list:
            out = []
            for kw in kws:
                if not kw.strip():
                    continue
                try:
                    if self.use_regex:
                        pattern = kw
                    else:
                        escaped = re.escape(kw)
                        pattern = rf"\b{escaped}\b"
                    pat = re.compile(pattern, flag)
                    out.append(pat)
                except re.error as exc:
                    logger.warning("[Profile:%s] Bad pattern %r: %s", self.name, kw, exc)
            return out

        self._compiled_triggers  = _make(self.trigger_keywords)
        self._compiled_blacklist = _make(self.blacklist_keywords)
        self._patterns_dirty = False

    def matches_triggers(self, text: str) -> bool:
        if self._patterns_dirty:
            self.compile()
        if not self._compiled_triggers:
            return True  # empty trigger list → accept everything
        return any(p.search(text) for p in self._compiled_triggers)

    def matches_blacklist(self, text: str) -> bool:
        if self._patterns_dirty:
            self.compile()
        return any(p.search(text) for p in self._compiled_blacklist)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "enabled": self.enabled, "locked": self.locked,
            "use_regex": self.use_regex, "trigger_keywords": self.trigger_keywords,
            "blacklist_keywords": self.blacklist_keywords,
            "verify_biome_name": self.verify_biome_name,
            "kill_on_wrong_biome": self.kill_on_wrong_biome,
            "priority": self.priority,
            "bypass_cooldown": self.bypass_cooldown,
            "sound_alert_path": self.sound_alert_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SnipeProfile":
        p = cls(
            name=d.get("name", "Unnamed"), enabled=d.get("enabled", True),
            locked=d.get("locked", False), use_regex=d.get("use_regex", False),
            trigger_keywords=d.get("trigger_keywords", []),
            blacklist_keywords=d.get("blacklist_keywords", []),
            verify_biome_name=d.get("verify_biome_name", ""),
            kill_on_wrong_biome=d.get("kill_on_wrong_biome", True),
            priority=d.get("priority", 0),
            bypass_cooldown=d.get("bypass_cooldown", False),
            sound_alert_path=d.get("sound_alert_path", ""),
        )
        p.compile()
        return p


def _default_global_profile() -> SnipeProfile:
    p = SnipeProfile(
        name="Global", enabled=True, locked=True,
        trigger_keywords=[],
        blacklist_keywords=["ended", "bait", "fake", "over", "closed", "gone"],
        verify_biome_name="", kill_on_wrong_biome=False,
    )
    p.compile()
    return p


def _default_profiles() -> list:
    profiles = [_default_global_profile()]

    # ── Active biome profiles ─────────────────────────────────────────────
    for name, biome, triggers in [
        ("Glitched",   "GLITCHED",   ["glitch", "glitched"]),
        ("Dreamspace", "DREAMSPACE", ["dreamspace", "dream"]),
        ("Cyberspace", "CYBERSPACE", ["cyber", "cyberspace"]),
    ]:
        p = SnipeProfile(
            name=name, enabled=True, locked=False,
            trigger_keywords=triggers, blacklist_keywords=[],
            verify_biome_name=biome, kill_on_wrong_biome=True,
        )
        p.compile()
        profiles.append(p)

    # ── Merchant item profiles (disabled by default) ──────────────────────
    for name, biome, triggers in [
        ("Void Coin",  "",  ["void", "vc"]),
        ("Jester",     "",  ["jester", "js", "obl", "oblivion", "heavenly", "hp", "obliv"]),
        ("Rin",        "",  ["rin"]),
    ]:
        p = SnipeProfile(
            name=name, enabled=False, locked=False,
            trigger_keywords=triggers, blacklist_keywords=[],
            verify_biome_name=biome, kill_on_wrong_biome=False,
        )
        p.compile()
        profiles.append(p)

    return profiles


@dataclass
class WebhookConfig:
    """Discord webhook configuration for event notifications."""
    url:          str  = ""
    enabled:      bool = False
    on_snipe:     bool = True
    on_biome:     bool = True
    on_start:     bool = False
    on_stop:      bool = False
    ping_type:    str  = "none"
    ping_target:  str  = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WebhookConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SniperConfig:
    token:                   str           = ""
    monitored_channels:      list          = field(default_factory=list)
    profiles:                list          = field(default_factory=_default_profiles)
    auto_join_enabled:       bool          = True
    auto_join_delay_ms:      int           = 0
    pause_after_snipe_s:     int           = 0       # 0 = disabled
    close_roblox_before_join: bool          = False
    biome_leave_action:      str           = "none"  # "none" | "kill" | "home"
    anti_bait_enabled:       bool          = True
    link_resolve_enabled:    bool          = True
    log_tail_bytes:          int           = LOG_TAIL_BYTES
    dev_mode:                bool          = False
    log_to_file:             bool          = False
    theme:                   str           = "dark"
    hotkey_toggle_key:       str           = ""
    hotkey_toggle_en:        bool          = False
    hotkey_pause_key:        str           = ""
    hotkey_pause_en:         bool          = False
    hotkey_pause_dur:        int           = 60
    webhook:                 WebhookConfig = field(default_factory=WebhookConfig)
    # Cooldown config (optional — loaded from "cooldown" key in config.json)
    cooldown_guild_ttl:      float         = 30.0
    cooldown_profile_ttl:    float         = 0.0
    cooldown_link_ttl:       float         = 10.0
    # Sound alert
    sound_alert_enabled:     bool          = False
    sound_alert_freq:        int           = 1000
    sound_alert_dur_ms:      int           = 200
    # Delete-watch auto-blacklist (0 = disabled)
    delete_watch_seconds:    int           = 0
    # Extra Discord tokens (optional, listen-only secondary accounts)
    extra_tokens:            list          = field(default_factory=list)
    # Internal — not serialised
    config_path:             str           = field(default="", repr=False, compare=False)

    def __post_init__(self):
        if not self.config_path:
            self.config_path = str(get_config_path())

    def ensure_global(self):
        if not self.profiles or self.profiles[0].name != "Global":
            self.profiles.insert(0, _default_global_profile())

    def save(self):
        self.ensure_global()
        data = {
            "token":                    self.token,
            "monitored_channels":       [asdict(c) for c in self.monitored_channels],
            "profiles":                 [p.to_dict() for p in self.profiles],
            "auto_join_enabled":        self.auto_join_enabled,
            "auto_join_delay_ms":       self.auto_join_delay_ms,
            "pause_after_snipe_s":      self.pause_after_snipe_s,
            "close_roblox_before_join": self.close_roblox_before_join,
            "biome_leave_action":       self.biome_leave_action,
            "anti_bait_enabled":        self.anti_bait_enabled,
            "link_resolve_enabled":     self.link_resolve_enabled,
            "log_tail_bytes":           self.log_tail_bytes,
            "dev_mode":                 self.dev_mode,
            "log_to_file":              self.log_to_file,
            "theme":                    self.theme,
            "hotkey_toggle_key":        self.hotkey_toggle_key,
            "hotkey_toggle_en":         self.hotkey_toggle_en,
            "hotkey_pause_key":         self.hotkey_pause_key,
            "hotkey_pause_en":          self.hotkey_pause_en,
            "hotkey_pause_dur":         self.hotkey_pause_dur,
            "webhook":                  self.webhook.to_dict(),
            "cooldown": {
                "guild_ttl":   self.cooldown_guild_ttl,
                "profile_ttl": self.cooldown_profile_ttl,
                "link_ttl":    self.cooldown_link_ttl,
            },
            "sound_alert_enabled":  self.sound_alert_enabled,
            "sound_alert_freq":     self.sound_alert_freq,
            "sound_alert_dur_ms":   self.sound_alert_dur_ms,
            "delete_watch_seconds": self.delete_watch_seconds,
            "extra_tokens":         self.extra_tokens,
        }
        # Atomic write: write to a tmp file then rename so a crash never
        # corrupts the live config.json.
        config_path = Path(self.config_path)
        tmp_path    = config_path.with_suffix(".json.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            shutil.move(str(tmp_path), str(config_path))
        except Exception:
            # Clean up orphan tmp file on failure
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    @classmethod
    def load(cls, path: Optional[str] = None) -> "SniperConfig":
        if path is None:
            path = str(get_config_path())
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            cfg = cls()
            cfg.config_path = path
            return cfg
        except json.JSONDecodeError as exc:
            logger.error("config.json is corrupted (%s) — resetting to defaults.", exc)
            cfg = cls()
            cfg.config_path = path
            return cfg

        try:
            channels      = [ChannelConfig(**c) for c in raw.pop("monitored_channels", [])]
            profiles_raw  = raw.pop("profiles", [])
            profiles      = [SnipeProfile.from_dict(d) for d in profiles_raw] if profiles_raw else _default_profiles()
            webhook_raw   = raw.pop("webhook", {})
            cooldown_raw  = raw.pop("cooldown", {})
            raw.pop("CONFIG_PATH", None)  # legacy compat

            # Bug 1 backward-compat: old key was close_roblox_after_join
            if "close_roblox_after_join" in raw and "close_roblox_before_join" not in raw:
                raw["close_roblox_before_join"] = raw.pop("close_roblox_after_join")
            else:
                raw.pop("close_roblox_after_join", None)

            # Only pass fields that exist in the dataclass to avoid TypeError
            valid_fields = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            cfg = cls(**valid_fields)
            cfg.monitored_channels  = channels
            cfg.profiles            = profiles
            cfg.webhook             = WebhookConfig.from_dict(webhook_raw)
            cfg.config_path         = path
            # Load cooldown TTLs from the dedicated "cooldown" sub-dict
            if cooldown_raw:
                cfg.cooldown_guild_ttl   = float(cooldown_raw.get("guild_ttl",   30.0))
                cfg.cooldown_profile_ttl = float(cooldown_raw.get("profile_ttl",  0.0))
                cfg.cooldown_link_ttl    = float(cooldown_raw.get("link_ttl",    10.0))
            cfg.ensure_global()
            return cfg
        except Exception as exc:
            logger.error("Failed to parse config.json (%s) — resetting to defaults.", exc)
            cfg = cls()
            cfg.config_path = path
            return cfg


# ─────────────────────────────────────────────────────────────────────────────
# LOG ENTRY
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LogEntry:
    level:    LogLevel
    message:  str
    ts:       str  = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S.%f")[:-3])
    dev_only: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# PROCESS MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class ProcessManager:
    @staticmethod
    def kill_roblox() -> int:
        killed = 0
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                if proc.info["name"] in ROBLOX_PROCESS_NAMES:
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return killed

    @staticmethod
    def kill_roblox_and_wait(timeout: float = 6.0) -> bool:
        ProcessManager.kill_roblox()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not ProcessManager.is_roblox_running():
                return True
            time.sleep(0.2)
        return not ProcessManager.is_roblox_running()

    @staticmethod
    def is_roblox_running() -> bool:
        for proc in psutil.process_iter(["name"]):
            try:
                if proc.info["name"] in ROBLOX_PROCESS_NAMES:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return False

    @staticmethod
    def is_in_game() -> bool:
        if not ProcessManager.is_roblox_running():
            return False
        try:
            for proc in psutil.process_iter(["name", "cmdline"]):
                try:
                    if proc.info["name"] not in ROBLOX_PROCESS_NAMES:
                        continue
                    cmdline = " ".join(proc.info.get("cmdline") or [])
                    if any(k in cmdline for k in (
                        "placeId=", "gameInstanceId",
                        "privateServerLinkCode", "launchMode=play",
                        "browsertrackerid",
                    )):
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return False

    @staticmethod
    def open_roblox_link(uri: str):
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(uri)
            elif system == "Darwin":
                subprocess.Popen(["open", uri])
            else:
                subprocess.Popen(["xdg-open", uri])
            logger.info("Opened Roblox URI: %s", uri[:80])
        except Exception as exc:
            logger.error("Failed to open Roblox link %r: %s", uri[:80], exc)

    @staticmethod
    def restart_roblox(delay: float = 1.0):
        """Kill all Roblox instances and re-launch the launcher after a short delay."""
        ProcessManager.kill_roblox_and_wait(timeout=6.0)
        time.sleep(delay)
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile("roblox://")
            elif system == "Darwin":
                subprocess.Popen(["open", "roblox://"])
            else:
                subprocess.Popen(["xdg-open", "roblox://"])
        except Exception as exc:
            logger.error("Failed to restart Roblox: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# ROBLOX LOG READER  (session-aware biome detection)
# ─────────────────────────────────────────────────────────────────────────────

class RobloxLogReader:
    """
    Session-aware Roblox log reader — v4.2 fix.

    Parsing strategy (matches the real log format seen in production):

    The Roblox client writes Rich-Presence updates via BloxstrapRPC in one of
    two formats per line:

      [BloxstrapRPC] {"command":"SetRichPresence","data":{...,"largeImage":{"hoverText":"RAINY",...}}}
      -- [BloxstrapRPC] {"command":"SetRichPresence","data":{...}}

    We parse the JSON blob embedded in those lines to extract
    data.largeImage.hoverText — exactly like the reference macro does with
    `check_for_hover_text`.  As a fallback we also accept a bare
    `"hoverText":"<BIOME>"` fragment for older Roblox versions.

    Key fixes vs. original implementation
    ──────────────────────────────────────
    1. _last_known_biome cache  — get_current_biome() always returns the last
       seen biome even when the log has not grown (player on menu / idle).
    2. Incremental read + tail seed — on the very first access of a log file we
       seed the buffer with the last tail_bytes so a biome that was written
       before mark_launch() is still detected immediately.
    3. _scan_buffer separated  — shared parsing logic for both the first-read
       path and the incremental path.
    4. Word-boundary fallback   — BIOME_DIRECT matches are guarded with \\b so
       "normal" inside "abnormal" doesn't produce a false positive.
    5. wait_for_biome pre-scan  — scans immediately before the poll loop so a
       biome already present in the file is returned on the first call.
    6. Poll interval 1 s        — Roblox writes in bursts; 50 ms polling was
       wasting CPU with zero practical benefit.
    """

    # Biome names guarded with word boundaries for the plain-text fallback.
    _BIOME_WORD_RE: dict = {
        b: re.compile(rf"\b{b}\b", re.IGNORECASE)
        for b in PATTERNS.BIOME_DIRECT
    }

    # Ignore these hoverText values — they are UI labels, not biome names.
    _HOVER_IGNORE = frozenset(["SOL'S RNG", "ROBLOX", ""])

    def __init__(self, tail_bytes: int = LOG_TAIL_BYTES):
        self.tail_bytes           = tail_bytes
        self._launch_time: float  = 0.0
        self._session_log: Optional[Path] = None
        self._seek_pos: dict      = {}   # Path → int (last read position)
        self._read_buf: dict      = {}   # Path → str (rolling text buffer)
        self._last_known_biome: Optional[str] = None

    # ─────────────────────────────────────────────

    def mark_launch(self):
        """Call immediately before opening a Roblox URI."""
        self._launch_time = time.time()
        self._session_log = None
        self._seek_pos.clear()
        self._read_buf.clear()
        self._last_known_biome = None

    def reset_session(self):
        self._launch_time = 0.0
        self._session_log = None
        self._seek_pos.clear()
        self._read_buf.clear()
        self._last_known_biome = None

    # ─────────────────────────────────────────────

    def _find_session_log(self) -> Optional[Path]:
        if not ROBLOX_LOG_PATH.exists():
            return None
        logs = list(ROBLOX_LOG_PATH.glob("*.log"))
        if not logs:
            return None
        stat_map = []
        for p in logs:
            try:
                s = p.stat()
                stat_map.append((p, s.st_mtime, s.st_ctime))
            except OSError:
                continue
        if not stat_map:
            return None
        window = self._launch_time - 30
        recent = [(p, mt) for p, mt, ct in stat_map if mt >= window]
        if recent:
            recent.sort(key=lambda x: x[1], reverse=True)
            return recent[0][0]
        stat_map.sort(key=lambda x: x[1], reverse=True)
        return stat_map[0][0]

    # ─────────────────────────────────────────────

    def _parse_biome_from_line(self, line: str) -> Optional[str]:
        """
        Extract the biome name from a single log line.

        Real log format (confirmed from production):
          23:32:52 -- [BloxstrapRPC] {"command":"SetRichPresence","data":{"state":"...",
            "smallImage":{"hoverText":"Sol's RNG","assetId":...},
            "largeImage":{"hoverText":"RAINY","assetId":...}}}

        IMPORTANT: only largeImage.hoverText carries the biome name.
        smallImage.hoverText is always "Sol's RNG" and must not be returned.

        Priority:
          1. BloxstrapRPC full JSON parse → data.largeImage.hoverText only.
          2. Bare regex on "largeImage"…"hoverText" fragment (truncated lines).
          3. Word-boundary biome name fallback.
        """
        # ── 1. BloxstrapRPC full JSON parse ──────────────────────────────────
        # Prefix may be "[BloxstrapRPC]" or "-- [BloxstrapRPC]"
        if "BloxstrapRPC" in line and "SetRichPresence" in line:
            try:
                # Find the JSON object on this line
                json_start = line.find("{")
                if json_start != -1:
                    raw = line[json_start:]
                    # Roblox sometimes escapes inner quotes as \" — fix that
                    # by replacing \" that appear INSIDE already-parsed strings
                    # Actually just try to parse as-is first; json.loads handles \".
                    blob = json.loads(raw)
                    large = blob.get("data", {}).get("largeImage", {})
                    hover = large.get("hoverText", "")
                    if hover:
                        candidate = hover.strip().upper()
                        if candidate not in self._HOVER_IGNORE:
                            return candidate
            except (json.JSONDecodeError, ValueError, AttributeError, KeyError):
                # JSON is truncated on this line — fall through to regex
                pass

        # ── 2. Targeted regex: largeImage section only ────────────────────────
        # Matches: "largeImage":{"hoverText":"BIOME",...}
        # This handles lines where the JSON was cut off before closing braces.
        if "largeImage" in line and "hoverText" in line:
            m = re.search(
                r'"largeImage"\s*:\s*\{[^}]*"hoverText"\s*:\s*"([^"]+)"',
                line, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip().upper()
                if candidate not in self._HOVER_IGNORE:
                    return candidate

        # ── 3. Plain-text word-boundary fallback ─────────────────────────────
        # Only used when there is no BloxstrapRPC/hoverText context on this line
        # to avoid false positives from unrelated log lines.
        if "BloxstrapRPC" not in line and "hoverText" not in line:
            for biome, pat in self._BIOME_WORD_RE.items():
                if pat.search(line):
                    return biome

        return None

    # ─────────────────────────────────────────────

    def _scan_buffer(self, text: str) -> Optional[str]:
        """Scan a text buffer line-by-line and return the *last* biome found."""
        last_biome: Optional[str] = None
        for line in text.splitlines():
            found = self._parse_biome_from_line(line)
            if found:
                last_biome = found
        return last_biome

    # ─────────────────────────────────────────────

    def _ingest_new_bytes(self, path: Path) -> bool:
        """
        Read any bytes appended to *path* since the last call and append them
        to the rolling buffer.  Returns True when new bytes were actually read.

        On the very first access (seek_pos == 0), we seed the buffer with the
        last tail_bytes so a biome already in the file is visible immediately —
        this handles the "player was already in the menu" scenario.
        """
        try:
            size = path.stat().st_size
        except OSError:
            return False

        last_pos = self._seek_pos.get(path, 0)

        if last_pos == 0 and size > 0:
            # First access: seed from the tail of the existing file.
            start = max(0, size - self.tail_bytes)
        else:
            start = last_pos

        if start >= size:
            return False

        try:
            with open(path, "rb") as fh:
                fh.seek(start)
                new_bytes = fh.read()
        except (OSError, IOError):
            return False

        if not new_bytes:
            return False

        self._seek_pos[path] = size
        new_text = new_bytes.decode("utf-8", errors="ignore")
        prev_buf = self._read_buf.get(path, "")
        combined = prev_buf + new_text
        max_len  = self.tail_bytes * 2
        if len(combined) > max_len:
            combined = combined[-max_len:]
        self._read_buf[path] = combined
        return True

    # ─────────────────────────────────────────────

    def _read_biome_from(self, path: Path) -> Optional[str]:
        """
        Ingest new bytes, scan the buffer, update _last_known_biome if
        something new is found, and return the cached value.

        Returning _last_known_biome even when no new bytes have arrived is the
        core fix: the log stops growing once the game loads but the biome read
        earlier is still valid.
        """
        had_new = self._ingest_new_bytes(path)
        if had_new:
            buf   = self._read_buf.get(path, "")
            found = self._scan_buffer(buf)
            if found:
                self._last_known_biome = found
        return self._last_known_biome

    # ─────────────────────────────────────────────

    def get_current_biome(self) -> Optional[str]:
        path = self._session_log or self._find_session_log()
        if not path:
            return self._last_known_biome

        try:
            st        = path.stat()
            idle_secs = time.time() - st.st_mtime
            age_secs  = time.time() - st.st_ctime
            if idle_secs > 120 and age_secs > 120:
                newer = self._find_session_log()
                if newer and newer != self._session_log:
                    old = self._session_log
                    if old:
                        self._seek_pos.pop(old, None)
                        self._read_buf.pop(old, None)
                    # Keep _last_known_biome until the new log overwrites it.
                    self._session_log = newer
                    self._seek_pos[newer] = 0
                    self._read_buf[newer] = ""
                    path = newer
        except Exception:
            pass

        self._session_log = path
        return self._read_biome_from(path)

    # ─────────────────────────────────────────────

    def wait_for_biome(self, timeout: float = 75.0, poll: float = 1.0) -> Optional[str]:
        """
        Poll until a biome is detected or *timeout* seconds elapse.

        Does an immediate full scan before entering the poll loop so a biome
        already present in the log (player already loaded) is returned instantly.
        Poll interval is 1 s — Roblox writes in bursts so 50 ms was pure waste.
        """
        # Immediate scan — catches biomes already in the file.
        path = self._session_log or self._find_session_log()
        if path:
            self._session_log = path
            self._ingest_new_bytes(path)
            buf   = self._read_buf.get(path, "")
            found = self._scan_buffer(buf)
            if found:
                self._last_known_biome = found
                return found

        end = time.time() + timeout
        while time.time() < end:
            time.sleep(poll)
            biome = self.get_current_biome()
            if biome:
                return biome
        return None

# ─────────────────────────────────────────────────────────────────────────────
# LINK RESOLVER
# ─────────────────────────────────────────────────────────────────────────────

class LinkResolver:
    _CACHE_MAX = 512   # LRU cache — 512 resolved URLs

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        # OrderedDict used as LRU: oldest entry at front
        self._cache: "OrderedDict[str, str]" = OrderedDict()

    def _cache_set(self, key: str, value: str):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        while len(self._cache) > self._CACHE_MAX:
            self._cache.popitem(last=False)  # drop oldest

    async def resolve(self, url: str) -> str:
        if url in self._cache:
            self._cache.move_to_end(url)
            return self._cache[url]
        resolved = url
        try:
            async with self._session.head(url, allow_redirects=False,
                                          timeout=LINK_RESOLVE_TIMEOUT) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", url)
                    for _ in range(3):
                        if not PATTERNS.SHORT_URL.match(location):
                            resolved = location
                            break
                        async with self._session.head(
                            location, allow_redirects=False,
                            timeout=LINK_RESOLVE_TIMEOUT
                        ) as r2:
                            location = r2.headers.get("Location", location)
                            resolved = location
                else:
                    resolved = str(resp.url)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            resolved = url
        self._cache_set(url, resolved)
        return resolved

    def extract_roblox_link(self, text: str) -> Optional[tuple]:
        m = PATTERNS.ROBLOX_PRIVATE.search(text)
        if m:
            pid, code = m.groups()
            return pid, code, f"roblox://placeId={pid}&linkCode={code}"

        m = PATTERNS.ROBLOX_INSTANCE.search(text)
        if m:
            pid, job_id = m.groups()
            if len(job_id) == 36 and "-" in job_id:
                uri = f"roblox://experiences/start?placeId={pid}&gameInstanceId={job_id}"
                return pid, job_id, uri

        m = PATTERNS.ROBLOX_LAUNCH.search(text)
        if m:
            pid, rid, sid = m.groups()
            return pid, sid, f"roblox://experiences/start?placeId={rid}&gameInstanceId={sid}"

        m = PATTERNS.SHARE_URL.search(text)
        if m:
            code = m.group(1)
            return "0", code, f"roblox://navigation/share_links?code={code}&type=Server"

        return None


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE FILTER
# ─────────────────────────────────────────────────────────────────────────────

_URL_STRIP_RE = re.compile(
    r'https?://\S+|roblox://\S+', re.IGNORECASE)

def _strip_urls(text: str) -> str:
    return _URL_STRIP_RE.sub(" ", text).strip()


class ProfileFilter:
    def __init__(self, config: SniperConfig):
        self._cfg = config

    # ── shared internal logic ─────────────────────────────────────────────────

    def _sorted_non_global(self) -> list:
        return sorted(
            (p for p in self._cfg.profiles if not p.locked and p.enabled),
            key=lambda p: p.priority,
        )

    def _global_blocked(self, clean: str):
        """Return (blocked: bool, hit_keyword: str)."""
        global_p = next((p for p in self._cfg.profiles if p.locked), None)
        if global_p and global_p.enabled and global_p.matches_blacklist(clean):
            hit = next(
                (m.group(0) for pat in global_p._compiled_blacklist
                 if (m := pat.search(clean))),
                "?",
            )
            return True, hit
        return False, ""

    def _match_profile(self, clean: str) -> tuple:
        """Return (matched_profile_or_None, reject_reason_str)."""
        blocked, kw = self._global_blocked(clean)
        if blocked:
            return None, f"global blacklist keyword '{kw}'"

        for p in self._sorted_non_global():
            if p.matches_blacklist(clean):
                hit = next(
                    (m.group(0) for pat in p._compiled_blacklist
                     if (m := pat.search(clean))),
                    "?",
                )
                return None, f"profile '{p.name}' blacklist keyword '{hit}'"
            if p.matches_triggers(clean):
                return p, ""

        return None, "no profile trigger matched"

    # ── public API ────────────────────────────────────────────────────────────

    def evaluate(self, text: str) -> Optional[SnipeProfile]:
        profile, _ = self._match_profile(_strip_urls(text))
        return profile

    def evaluate_detailed(self, text: str) -> tuple:
        return self._match_profile(_strip_urls(text))

    def rebuild(self):
        for p in self._cfg.profiles:
            p.compile()


# (WebhookSender lives in main.py — engine fires callbacks instead)


# ─────────────────────────────────────────────────────────────────────────────
# DISCORD GATEWAY CLIENT
# ─────────────────────────────────────────────────────────────────────────────

class DiscordGateway:
    def __init__(self, token: str, on_message: Callable, on_log: Callable,
                 on_status: Callable, config: SniperConfig,
                 on_message_delete: Callable = None):
        self.token      = token
        self.on_message = on_message
        self.on_log     = on_log
        self.on_status  = on_status
        self.config     = config
        self.on_message_delete = on_message_delete

        self._ws:                 Optional[aiohttp.ClientWebSocketResponse] = None
        self._session:            Optional[aiohttp.ClientSession]           = None
        self._heartbeat_task:     Optional[asyncio.Task]                    = None
        self._sequence:           Optional[int]                             = None
        self._session_id:         Optional[str]                             = None
        self._resume_gateway_url: str                                       = DISCORD_GATEWAY_URL
        self._ping_ms:            float                                     = 0.0
        self._running:            bool                                      = False
        self._last_hb:            float                                     = 0.0

    @property
    def ping_ms(self) -> float:
        return self._ping_ms

    async def connect(self):
        self._running = True
        self.on_status(EngineStatus.CONNECTING)
        self.on_log(LogEntry(LogLevel.INFO, "Connecting to Discord Gateway…"))
        connector = aiohttp.TCPConnector(
            limit=20, ttl_dns_cache=300, use_dns_cache=True, keepalive_timeout=60)
        self._session = aiohttp.ClientSession(
            connector=connector,
            headers={
                "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
                "Authorization": self.token,
            },
            timeout=HTTP_REQUEST_TIMEOUT)
        try:
            await self._gateway_loop()
        finally:
            await self._cleanup()

    async def _gateway_loop(self):
        retry = 1.0
        while self._running:
            try:
                async with self._session.ws_connect(
                    DISCORD_GATEWAY_URL, heartbeat=None, max_msg_size=0
                ) as ws:
                    self._ws = ws
                    retry    = 1.0
                    await self._handle_events()
            except (aiohttp.ClientError, ConnectionResetError, OSError) as exc:
                self.on_log(LogEntry(LogLevel.WARN,
                    f"Connection lost: {exc}. Retrying in {retry:.0f}s…"))
                self.on_status(EngineStatus.CONNECTING)
                await asyncio.sleep(retry)
                retry = min(retry * 2, 30)
            except asyncio.CancelledError:
                break

    async def _handle_events(self):
        async for msg in self._ws:
            if not self._running:
                break
            if msg.type == aiohttp.WSMsgType.TEXT:
                await self._dispatch(json.loads(msg.data))
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    async def _dispatch(self, payload: dict):
        op = payload.get("op")
        t  = payload.get("t")
        s  = payload.get("s")
        d  = payload.get("d", {})

        if s is not None:
            self._sequence = s

        if op == 10:
            # Bug 5 fix: jitter before first heartbeat per Discord spec
            interval = d.get("heartbeat_interval", 41250) / 1000
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(interval))
            # Bug 4 fix: attempt RESUME if we have a valid session_id + sequence
            if self._session_id and self._sequence is not None:
                await self._resume()
            else:
                await self._identify()

        elif op == 11:
            self._ping_ms = (time.monotonic() - self._last_hb) * 1000

        elif op == 0:
            if t == "READY":
                u = d.get("user", {})
                self._session_id = d.get("session_id")
                self._resume_gateway_url = d.get("resume_gateway_url",
                                                  DISCORD_GATEWAY_URL)
                self.on_status(EngineStatus.CONNECTED)
                self.on_log(LogEntry(LogLevel.SUCCESS,
                    f"Connected as: {u.get('username', '?')}"))
            elif t == "RESUMED":
                self.on_status(EngineStatus.CONNECTED)
                self.on_log(LogEntry(LogLevel.SUCCESS, "Session resumed — no messages lost."))
            elif t == "MESSAGE_CREATE":
                asyncio.create_task(self._on_message(d))
            elif t == "MESSAGE_UPDATE":
                # Some bots edit messages to add the link after posting
                asyncio.create_task(self._on_message(d, is_update=True))
            elif t == "MESSAGE_DELETE":
                asyncio.create_task(self._on_message_delete(d))

        elif op == 7:
            # Reconnect requested — close so _gateway_loop reconnects
            self.on_log(LogEntry(LogLevel.WARN, "Reconnect requested by server."))
            if self._ws and not self._ws.closed:
                await self._ws.close()

        elif op == 9:
            # Invalid session — clear resume state then re-identify
            self.on_log(LogEntry(LogLevel.WARN, "Session invalidated. Reconnecting…"))
            self._session_id = None
            self._sequence   = None
            await asyncio.sleep(2)
            if self._ws and not self._ws.closed:
                await self._ws.close()

    async def _identify(self):
        _os_map = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}
        os_str  = _os_map.get(platform.system(), "linux")
        await self._ws.send_json({"op": 2, "d": {
            "token": self.token,
            "properties": {"os": os_str, "browser": "Discord Client", "device": ""},
            "presence": {"status": "online", "afk": False},
        }})

    async def _resume(self):
        """Bug 4 fix: send RESUME (op 6) to recover missed messages after disconnect."""
        await self._ws.send_json({"op": 6, "d": {
            "token":      self.token,
            "session_id": self._session_id,
            "seq":        self._sequence,
        }})

    async def _heartbeat_loop(self, interval: float):
        # Bug 5 fix: initial jitter — sleep random(0..1) * interval before first beat
        jitter = random.random() * interval
        try:
            await asyncio.sleep(jitter)
        except asyncio.CancelledError:
            return
        while self._running and self._ws and not self._ws.closed:
            try:
                self._last_hb = time.monotonic()
                await self._ws.send_json({"op": 1, "d": self._sequence})
                await asyncio.sleep(interval)
            except (aiohttp.ClientError, asyncio.CancelledError):
                break

    async def _on_message(self, data: dict, is_update: bool = False):
        ch      = data.get("channel_id", "").strip()
        guild   = data.get("guild_id",   "").strip()
        msg_id  = data.get("id",         "").strip()
        content = data.get("content",    "")
        author  = data.get("author",     {})

        embed_parts = []
        for embed in data.get("embeds", []):
            if not isinstance(embed, dict):
                continue
            for key in ("title", "description"):
                if key in embed:
                    embed_parts.append(embed[key])
            for fld in embed.get("fields", []):
                if "value" in fld:
                    embed_parts.append(fld["value"])

        full_content = f"{content} {' '.join(embed_parts)}".strip()
        astr         = author.get("username", "?")
        author_id    = author.get("id", "").strip()
        # Build avatar URL if available
        avatar_hash  = author.get("avatar", "")
        if author_id and avatar_hash:
            author_avatar_url = (
                f"https://cdn.discordapp.com/avatars/{author_id}/{avatar_hash}.png?size=128"
            )
        else:
            author_avatar_url = ""
        # Prefer display_name > global_name > username
        author_display = (
            author.get("display_name") or author.get("global_name") or astr
        )

        monitored = any(
            c.channel_id == ch and c.enabled for c in self.config.monitored_channels)

        if not monitored:
            return

        self.on_log(LogEntry(LogLevel.DEBUG,
            f"[MSG{'_UPDATE' if is_update else ''}] #{ch} | {astr}: {content[:80]}",
            dev_only=True))

        await self.on_message(
            guild, ch, msg_id, content, astr, full_content,
            author_id=author_id,
            author_avatar_url=author_avatar_url,
            author_display=author_display,
        )

    async def _on_message_delete(self, data: dict):
        ch      = data.get("channel_id", "").strip()
        msg_id  = data.get("id",         "").strip()
        guild   = data.get("guild_id",   "").strip()
        monitored = any(
            c.channel_id == ch and c.enabled for c in self.config.monitored_channels)
        if not monitored:
            return
        if self.on_message_delete:
            await self.on_message_delete(guild, ch, msg_id)

    async def disconnect(self):
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()

    async def _cleanup(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ─────────────────────────────────────────────────────────────────────────────
# SNIPER ENGINE  —  orchestrates all subsystems
# ─────────────────────────────────────────────────────────────────────────────

class SniperEngine:

    # TTL constants (seconds)
    _SERVER_DEDUP_TTL  = 10.0   # ignore same server link within 10s
    _PAUSE_AFTER_SNIPE = 0       # overridden from config
    # Message ID dedup buffer capacity
    _MSG_DEDUP_SIZE    = 200

    def __init__(
        self,
        config:    SniperConfig,
        blacklist: Any = None,   # BlacklistManager instance (injected from main.py)
        cooldown:  Any = None,   # CooldownManager  instance (injected from main.py)
        plugins:   Any = None,   # PluginLoader     instance (injected from main.py)
    ):
        self.config = config

        self._gateway:  Optional[DiscordGateway] = None
        self._resolver: Optional[LinkResolver]   = None
        self._filter:   Optional[ProfileFilter]  = None

        self._session:  Optional[aiohttp.ClientSession] = None
        self._tasks:    list                            = []
        self._running:  bool                            = False
        self._paused:   bool                            = False
        self._start_ts: float                           = 0.0

        self._log_reader  = RobloxLogReader(config.log_tail_bytes)
        self._snipe_count = 0

        # ── metrics ───────────────────────────────────────────────────────
        self.metrics: dict = {
            "messages_scanned":  0,
            "links_detected":    0,
            "snipes_successful": 0,
            "webhooks_sent":     0,
        }

        # ── message ID dedup buffer ───────────────────────────────────────
        self._seen_msg_ids: deque = deque(maxlen=self._MSG_DEDUP_SIZE)

        # ── server-URI dedup  {uri: expiry_monotonic} ─────────────────────
        self._recent_servers: dict = {}   # URI → expiry (TTL 10s)

        # ── deleted message IDs observed from MESSAGE_DELETE ──────────────
        # deque gives deterministic eviction order (FIFO) unlike set trimming
        self._deleted_msg_ids: deque = deque(maxlen=1000)

        # ── injected subsystems ───────────────────────────────────────────
        self.blacklist = blacklist   # Optional BlacklistManager
        self.cooldown  = cooldown    # Optional CooldownManager
        self._plugins  = plugins     # Optional PluginLoader

        # ── file logger ───────────────────────────────────────────────────
        self._file_logger: Optional[logging.Logger] = None
        if config.log_to_file:
            self._setup_file_logger()

        # Callbacks set by the Bridge
        self.on_log:              Callable = lambda e: None
        self.on_status:           Callable = lambda s: None
        self.on_snipe:            Callable = lambda data: None
        self.on_biome:            Callable = lambda exp, det, ok: None
        self.on_ping_update:      Callable = lambda p: None
        self.on_paused:           Callable = lambda v: None
        self.on_delete_blacklist: Callable = lambda uid, name: None

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def snipe_count(self) -> int:
        return self._snipe_count

    @property
    def ping_ms(self) -> float:
        return self._gateway.ping_ms if self._gateway else 0.0

    @property
    def uptime_seconds(self) -> float:
        return (time.monotonic() - self._start_ts) if self._running and self._start_ts else 0.0

    def _setup_file_logger(self):
        """Rotating file logger — max 5 MB, single backup."""
        try:
            from logging.handlers import RotatingFileHandler
            log_path = get_log_path()
            fh = RotatingFileHandler(
                log_path, maxBytes=5 * 1024 * 1024, backupCount=1, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            fl = logging.getLogger("sniper_file")
            fl.setLevel(logging.DEBUG)
            fl.addHandler(fh)
            self._file_logger = fl
        except Exception as exc:
            logger.warning("Could not set up file logger: %s", exc)

    def _log(self, level: LogLevel, message: str, dev_only: bool = False):
        try:
            self.on_log(LogEntry(level, message, dev_only=dev_only))
        except Exception:
            pass
        if self._file_logger and not dev_only:
            self._file_logger.info("[%s] %s", level.value, message)

    def _set_status(self, status: EngineStatus):
        try:
            self.on_status(status)
        except Exception:
            pass

    def _prewarm_roblox(self):
        """Open Roblox in the background so it's ready when a snipe fires."""
        if not ProcessManager.is_roblox_running():
            try:
                ProcessManager.open_roblox_link("roblox://")
                self._log(LogLevel.DEBUG, "[ENGINE] Pre-warming Roblox…", dev_only=True)
            except Exception:
                pass

    def _purge_expired_caches(self):
        """Drop expired entries from all TTL caches."""
        now = time.monotonic()
        for d in (self._recent_servers,):
            expired = [k for k, exp in d.items() if now >= exp]
            for k in expired:
                del d[k]

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running  = True
        self._paused   = False
        self._start_ts = time.monotonic()
        self._set_status(EngineStatus.CONNECTING)

        # Persistent session with connection pooling (limit=50)
        connector     = aiohttp.TCPConnector(
            limit=50, ttl_dns_cache=300, use_dns_cache=True, keepalive_timeout=60)
        self._session = aiohttp.ClientSession(connector=connector, timeout=HTTP_REQUEST_TIMEOUT)
        self._resolver = LinkResolver(self._session)
        self._filter   = ProfileFilter(self.config)

        # Initialise plugins — pass self as engine, ui is not available here
        if self._plugins:
            self._plugins.init_all(engine=self, ui=None)

        self._log(LogLevel.INFO, "[ENGINE] Sniper starting…")

        if self._plugins:
            self._plugins.broadcast("on_start", {
                "config": self.config,
            })

        self._tasks = [
            asyncio.create_task(self._run_gateway(),      name="gateway"),
            asyncio.create_task(self._ping_updater(),     name="ping"),
            asyncio.create_task(self._log_monitor_loop(), name="log_monitor"),
        ]

        # Wait for the core tasks to finish (they run until stop() cancels them)
        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass

    async def stop(self):
        if not self._running:
            return
        self._running = False
        self._paused  = False
        self._log(LogLevel.INFO, "[ENGINE] Stopping sniper…")

        # Notify plugins
        if self._plugins:
            self._plugins.broadcast("on_stop")

        # Reset cooldown state on stop
        if self.cooldown:
            self.cooldown.reset()

        # Snapshot the list before cancelling — done_callbacks may mutate it
        tasks_snapshot = list(self._tasks)
        for task in tasks_snapshot:
            task.cancel()

        try:
            await asyncio.gather(*tasks_snapshot, return_exceptions=True)
        except Exception:
            pass

        if self._gateway:
            try:
                await self._gateway.disconnect()
            except Exception:
                pass
            self._gateway = None

        if self._session and not self._session.closed:
            await self._session.close()

        self._set_status(EngineStatus.STOPPED)

    def reload_config(self, config: SniperConfig):
        self.config = config
        if self._filter:
            self._filter = ProfileFilter(config)
        if config.log_to_file and self._file_logger is None:
            self._setup_file_logger()
        elif not config.log_to_file:
            self._file_logger = None
        # Hot-reload cooldown TTLs — no import needed, just update the object
        if self.cooldown and hasattr(self.cooldown, "update_config"):
            # Build a minimal duck-typed config object that matches CooldownConfig
            class _CD:
                pass
            cd = _CD()
            cd.guild_ttl   = getattr(config, "cooldown_guild_ttl",   30.0)
            cd.profile_ttl = getattr(config, "cooldown_profile_ttl",  0.0)
            cd.link_ttl    = getattr(config, "cooldown_link_ttl",    10.0)
            self.cooldown.update_config(cd)

    # ── background tasks ──────────────────────────────────────────────────────

    async def _run_gateway(self):
        if not self.config.token:
            self._log(LogLevel.ERROR, "[ENGINE] Discord token not configured")
            self._set_status(EngineStatus.ERROR)
            return

        self._gateway = DiscordGateway(
            token=self.config.token,
            on_message=self._on_discord_message,
            on_log=self.on_log,
            on_status=self._set_status,
            config=self.config,
            on_message_delete=self._on_discord_message_delete,
        )

        # Extra tokens — each runs a secondary gateway in listen-only mode
        extra_tokens = getattr(self.config, "extra_tokens", [])
        for tok in extra_tokens:
            if tok and tok != self.config.token:
                t = asyncio.create_task(
                    self._run_extra_gateway(tok), name=f"gateway_extra_{tok[:6]}")
                self._tasks.append(t)
                t.add_done_callback(
                    lambda x: self._tasks.remove(x) if x in self._tasks else None)

        await self._gateway.connect()

    async def _run_extra_gateway(self, token: str):
        """Secondary gateway — receive messages only, no status updates."""
        gw = DiscordGateway(
            token=token,
            on_message=self._on_discord_message,
            on_log=self.on_log,
            on_status=lambda s: None,   # suppress status updates from secondaries
            config=self.config,
            on_message_delete=self._on_discord_message_delete,
        )
        self._log(LogLevel.INFO, f"[ENGINE] Extra token connected: {token[:10]}…")
        await gw.connect()

    async def _ping_updater(self):
        while self._running:
            await asyncio.sleep(2)
            if self._gateway:
                try:
                    self.on_ping_update(self._gateway.ping_ms)
                except Exception:
                    pass
            self._purge_expired_caches()
            # Periodically purge expired cooldown entries to keep memory bounded
            if self.cooldown:
                self.cooldown.purge_expired()

    async def _log_monitor_loop(self):
        loop = asyncio.get_running_loop()
        _last_logged_biome: Optional[str] = None
        while self._running:
            await asyncio.sleep(1)
            if not ProcessManager.is_roblox_running():
                _last_logged_biome = None
                continue
            try:
                biome = await loop.run_in_executor(
                    None, self._log_reader.get_current_biome)
            except Exception:
                continue
            if biome and biome != _last_logged_biome:
                self._log(LogLevel.DEBUG, f"[BIOME] Current biome: {biome}", dev_only=True)
                _last_logged_biome = biome

    # ── message handler ───────────────────────────────────────────────────────

    async def _on_discord_message(self, guild_id: str, channel_id: str,
                                  msg_id: str, content: str, author: str, full: str,
                                  author_id: str = "", author_avatar_url: str = "",
                                  author_display: str = ""):
        if self._paused:
            return

        self.metrics["messages_scanned"] += 1
        self._log(LogLevel.DEBUG,
            f"[MSG] Processing from {author}: {content[:60]}", dev_only=True)

        if msg_id and msg_id in self._seen_msg_ids:
            self._log(LogLevel.DEBUG,
                f"[DEDUP] Message ID already processed — skip", dev_only=True)
            return
        if msg_id:
            self._seen_msg_ids.append(msg_id)

        # ── Bug 1 fix: use the real author_id from gateway ────────────────────
        if self.blacklist and author_id and self.blacklist.is_blacklisted(author_id):
            entry = self.blacklist.get_entry(author_id)
            self._log(LogLevel.WARN,
                f"[BLACKLIST] Blocked {author} — reason: {entry.reason if entry else '?'}")
            return
        elif author_id:
            self._log(LogLevel.DEBUG,
                f"[BLACKLIST] {author} ({author_id}) not blacklisted", dev_only=True)

        profile, reject_reason = (
            self._filter.evaluate_detailed(full) if self._filter else (None, "no filter")
        )
        if profile is None:
            has_link = bool(self._resolver.extract_roblox_link(full))
            if has_link:
                self._log(LogLevel.INFO,
                    f"[FILTER] Link detected but blocked — {reject_reason} — "
                    f"{author}: {content[:60]}")
            else:
                self._log(LogLevel.DEBUG,
                    f"[FILTER] Skipped — {reject_reason} — {author}: {content[:60]}",
                    dev_only=True)
            return

        self._log(LogLevel.DEBUG,
            f"[FILTER] Profile '{profile.name}' matched — scanning for link", dev_only=True)

        if self._plugins:
            self._plugins.broadcast("on_message_matched", {
                "profile": profile.name,
                "author":  author,
                "content": content,
                "full":    full,
            })

        link = self._resolver.extract_roblox_link(full)
        if not link:
            self._log(LogLevel.INFO,
                f"[FILTER] Profile '{profile.name}' matched but no Roblox link found — "
                f"{author}: {content[:60]}")
            return

        self.metrics["links_detected"] += 1
        place_id, code, uri = link
        self._log(LogLevel.DEBUG,
            f"[LINK] Extracted → place_id={place_id}, uri={uri[:80]}", dev_only=True)

        now = time.monotonic()
        if uri in self._recent_servers and now < self._recent_servers[uri]:
            remaining = self._recent_servers[uri] - now
            self._log(LogLevel.INFO,
                f"[DEDUP] Same server link posted {remaining:.1f}s ago — skipping")
            return
        self._recent_servers[uri] = now + self._SERVER_DEDUP_TTL

        if self.cooldown:
            blocked, reason = self.cooldown.check(
                guild_id, profile.name, uri,
                bypass=getattr(profile, "bypass_cooldown", False),
            )
            if blocked:
                self._log(LogLevel.INFO, f"[COOLDOWN] Blocked — {reason}")
                if self._plugins:
                    self._plugins.broadcast("on_cooldown_blocked", {
                        "reason":  reason,
                        "profile": profile.name,
                        "uri":     uri,
                    })
                return
            self.cooldown.mark(guild_id, profile.name, uri)

        self._snipe_count += 1
        self.metrics["snipes_successful"] += 1

        # ── Detect which keyword triggered this snipe ─────────────────────────
        keyword_hit = ""
        if profile and profile._compiled_triggers:
            clean_text = _strip_urls(full)
            for pat in profile._compiled_triggers:
                m = pat.search(clean_text)
                if m:
                    keyword_hit = m.group(0)
                    break

        self._log(LogLevel.SNIPE,
            f"[SNIPER] Profile '{profile.name}' — {author}: {content[:80]}")

        # ── Build jump-to-message URL ─────────────────────────────────────────
        jump_url = ""
        if guild_id and channel_id and msg_id:
            jump_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{msg_id}"

        # ── Build the Roblox web URL (share link, not the raw uri scheme) ─────
        if place_id and place_id != "0" and code:
            roblox_web_url = (
                f"https://www.roblox.com/games/{place_id}/"
                f"?privateServerLinkCode={code}"
            )
        elif place_id == "0" and code:
            # Share-link type: reconstruct the original roblox.com/share URL
            roblox_web_url = f"https://www.roblox.com/share?code={code}&type=Server"
        else:
            roblox_web_url = ""

        # ── Optional auto-join — execute first for minimum latency ───────────
        if self.config.auto_join_enabled:
            if self.config.auto_join_delay_ms:
                self._log(LogLevel.DEBUG,
                    f"[JOIN] Waiting {self.config.auto_join_delay_ms}ms before joining…",
                    dev_only=True)
                await asyncio.sleep(self.config.auto_join_delay_ms / 1000)

            roblox_running   = ProcessManager.is_roblox_running()
            in_game          = ProcessManager.is_in_game() if roblox_running else False
            force_close      = self.config.close_roblox_before_join
            self._log(LogLevel.DEBUG,
                f"[JOIN] roblox_running={roblox_running}, in_game={in_game}, "
                f"force_close={force_close}",
                dev_only=True)

            loop = asyncio.get_running_loop()

            if roblox_running and (in_game or force_close):
                reason = "in a game" if in_game else "'Close Roblox before joining' is on"
                self._log(LogLevel.INFO,
                    f"[JOIN] Killing Roblox ({reason})…")
                await loop.run_in_executor(
                    None, lambda: ProcessManager.kill_roblox_and_wait(timeout=5.0))
                await asyncio.sleep(0.4)
                self._log_reader.mark_launch()
                ProcessManager.open_roblox_link(uri)
                self._log(LogLevel.INFO, "[JOIN] Relaunched — joining server…")

            elif roblox_running:
                self._log(LogLevel.INFO,
                    "[JOIN] Roblox is on home page — opening link…")
                self._log_reader.mark_launch()
                ProcessManager.open_roblox_link(uri)

            else:
                self._log(LogLevel.INFO, "[JOIN] Roblox not running — launching…")
                self._log_reader.mark_launch()
                ProcessManager.open_roblox_link(uri)

        else:
            self._log(LogLevel.DEBUG, "[JOIN] auto_join_enabled=False — skipping join",
                dev_only=True)

        # ── Biome verification — runs regardless of auto_join_enabled ────────
        # mark_launch() was already called above if we joined; if auto-join is
        # off the log reader still needs to watch the existing session.
        if profile.verify_biome_name and self.config.anti_bait_enabled:
            self._log(LogLevel.INFO,
                f"[ANTI-BAIT] Starting biome verification for '{profile.verify_biome_name.upper()}'…")
            asyncio.create_task(self._verify_biome(profile, uri))
        else:
            self._log(LogLevel.DEBUG,
                f"[JOIN] No biome verification (verify_biome_name='{profile.verify_biome_name}', "
                f"anti_bait={self.config.anti_bait_enabled})", dev_only=True)

        # ── Sound alert ───────────────────────────────────────────────────────
        if getattr(self.config, "sound_alert_enabled", False):
            self._log(LogLevel.DEBUG, "[ENGINE] Sound alert firing…", dev_only=True)
            freq       = getattr(self.config, "sound_alert_freq",   1000)
            dur        = getattr(self.config, "sound_alert_dur_ms",  200)
            # Per-profile custom sound file takes precedence over global beep
            snd_path   = getattr(profile, "sound_alert_path", "") if profile else ""
            threading.Thread(
                target=lambda: play_sound(freq, dur, snd_path),
                daemon=True, name="SoundAlert").start()

        # ── Build snipe data dict ─────────────────────────────────────────────
        snipe_data = {
            "place_id":          place_id,
            "code":              code,
            "uri":               uri,
            "roblox_web_url":    roblox_web_url,
            "profile":           profile.name,
            "verify_biome_name": profile.verify_biome_name if profile else "",
            "author":            author,
            "author_id":         author_id,
            "author_display":    author_display or author,
            "author_avatar_url": author_avatar_url,
            "keyword":           keyword_hit,
            "raw_message":       content[:1000],
            "link":              uri,
            "jump_url":          jump_url,
            "timestamp_iso":     datetime.now().isoformat(),
        }

        # ── Fire on_snipe callback ────────────────────────────────────────────
        try:
            self.on_snipe(snipe_data)
        except Exception:
            pass

        # ── Broadcast to plugins ──────────────────────────────────────────────
        if self._plugins:
            self._plugins.broadcast("on_snipe", snipe_data)

        # ── Delete-watch: observe if author deletes within watch window ───────
        watch_s = getattr(self.config, "delete_watch_seconds", 0)
        if watch_s > 0 and author_id and msg_id:
            task = asyncio.create_task(
                self._delete_watch(author_id, author_display or author,
                                   msg_id, guild_id, channel_id, watch_s))
            self._tasks.append(task)
            task.add_done_callback(lambda t: self._tasks.remove(t) if t in self._tasks else None)

        # ── Bug 5 fix: Pause-after-snipe as tracked cancellable task ─────────
        pause_s = self.config.pause_after_snipe_s
        if pause_s > 0:
            task = asyncio.create_task(self._pause_after_snipe(pause_s))
            self._tasks.append(task)
            task.add_done_callback(lambda t: self._tasks.remove(t) if t in self._tasks else None)

    async def _pause_after_snipe(self, pause_s: int):
        """Bug 5 fix: auto-pause runs as a tracked task so stop() can cancel it."""
        self._paused = True
        try:
            self.on_paused(True)
        except Exception:
            pass
        self._log(LogLevel.INFO, f"[ENGINE] Auto-paused for {pause_s}s after snipe…")
        try:
            await asyncio.sleep(pause_s)
        except asyncio.CancelledError:
            pass
        finally:
            self._paused = False
        if self._running:
            try:
                self.on_paused(False)
            except Exception:
                pass
            self._log(LogLevel.INFO, "[ENGINE] Auto-pause ended — resuming scan.")

    async def _delete_watch(self, author_id: str, author_name: str,
                            msg_id: str, guild_id: str, channel_id: str,
                            watch_s: float):
        """Watch for message deletion within watch_s seconds and auto-blacklist."""
        deadline = time.monotonic() + watch_s
        while time.monotonic() < deadline and self._running:
            await asyncio.sleep(0.5)
            if msg_id in self._deleted_msg_ids:
                # Remove the found entry from the deque
                try:
                    self._deleted_msg_ids.remove(msg_id)
                except ValueError:
                    pass
                if self.blacklist:
                    self.blacklist.add(author_id, author_name, reason="message_deleted")
                    self._log(LogLevel.WARN,
                        f"[BLACKLIST] Auto-blacklisted {author_name} ({author_id})"
                        f" — deleted snipe message within {watch_s:.0f}s")
                try:
                    self.on_delete_blacklist(author_id, author_name)
                except Exception:
                    pass
                return

    async def _on_discord_message_delete(self, guild_id: str, channel_id: str, msg_id: str):
        """Called by gateway when a MESSAGE_DELETE event fires in a monitored channel."""
        # Bug 7 fix: deque(maxlen=1000) handles eviction automatically — no manual trim needed
        if msg_id:
            self._deleted_msg_ids.append(msg_id)

    async def _verify_biome(self, profile: SnipeProfile, uri: str):
        if not profile.verify_biome_name:
            return
        loop  = asyncio.get_running_loop()
        expected = profile.verify_biome_name.upper()
        self._log(LogLevel.INFO,
            f"[ANTI-BAIT] Waiting for biome in log… (expected: {expected}, timeout: 75s)")
        biome = await loop.run_in_executor(
            None, lambda: self._log_reader.wait_for_biome(75.0))

        if biome is None:
            self._log(LogLevel.WARN,
                "[ANTI-BAIT] Biome verification timed out — no biome detected in log within 75s")
            return

        detected = biome.upper()
        matched  = (detected == expected)

        self._log(LogLevel.INFO,
            f"[ANTI-BAIT] Log biome detected: '{detected}' (expected: '{expected}')")

        if matched:
            self._log(LogLevel.SUCCESS,
                f"[ANTI-BAIT] Biome verified ✓  ({detected})")
            action = self.config.biome_leave_action
            self._log(LogLevel.DEBUG,
                f"[ANTI-BAIT] biome_leave_action = '{action}'", dev_only=True)
            if action != "none":
                asyncio.create_task(self._biome_watcher(expected, action))
            if self._plugins:
                self._plugins.broadcast("on_biome_verified", {
                    "expected": expected,
                    "detected": detected,
                })
        else:
            self._log(LogLevel.WARN,
                f"[ANTI-BAIT] Wrong biome — expected '{expected}', got '{detected}'")
            if profile.kill_on_wrong_biome:
                action = self.config.biome_leave_action
                self._log(LogLevel.DEBUG,
                    f"[ANTI-BAIT] kill_on_wrong_biome=True, biome_leave_action='{action}'",
                    dev_only=True)
                if action == "home":
                    self._log(LogLevel.INFO,
                        "[ANTI-BAIT] Wrong biome — killing Roblox and returning to home…")
                    await loop.run_in_executor(
                        None, lambda: self._execute_biome_leave("home"))
                else:
                    self._log(LogLevel.WARN, "[ANTI-BAIT] Killing Roblox…")
                    ProcessManager.kill_roblox()

        try:
            self.on_biome(expected, detected, matched)
        except Exception:
            pass

    async def _biome_watcher(self, expected_biome: str, action: str):
        self._log(LogLevel.INFO,
            f"[BIOME WATCHER] Monitoring for biome change from '{expected_biome}'…")
        self._log(LogLevel.DEBUG,
            f"[BIOME WATCHER] action='{action}', polling every 3s", dev_only=True)
        loop     = asyncio.get_running_loop()
        interval = 3.0
        stable_count   = 0
        required_stable = 2

        while self._running:
            await asyncio.sleep(interval)

            if not ProcessManager.is_roblox_running():
                self._log(LogLevel.INFO, "[BIOME WATCHER] Roblox closed — watcher stopped.")
                return

            try:
                current = await loop.run_in_executor(
                    None, self._log_reader.get_current_biome)
            except Exception as exc:
                self._log(LogLevel.DEBUG,
                    f"[BIOME WATCHER] get_current_biome error: {exc}", dev_only=True)
                continue

            self._log(LogLevel.DEBUG,
                f"[BIOME WATCHER] Poll: current='{current}' expected='{expected_biome}'",
                dev_only=True)

            if current is None:
                self._log(LogLevel.DEBUG,
                    "[BIOME WATCHER] No biome detected yet (log not updated)", dev_only=True)
                continue

            current_upper = current.upper()
            if current_upper != expected_biome:
                stable_count += 1
                self._log(LogLevel.DEBUG,
                    f"[BIOME WATCHER] Biome changed: '{expected_biome}' → '{current_upper}' "
                    f"({stable_count}/{required_stable})", dev_only=True)
                if stable_count >= required_stable:
                    self._log(LogLevel.INFO,
                        f"[BIOME WATCHER] Biome left '{expected_biome}' (now '{current_upper}') "
                        f"— executing action: {action}")
                    await loop.run_in_executor(None, lambda: self._execute_biome_leave(action))
                    return
            else:
                if stable_count > 0:
                    self._log(LogLevel.DEBUG,
                        f"[BIOME WATCHER] Biome back to expected — resetting stable counter",
                        dev_only=True)
                stable_count = 0

    def _execute_biome_leave(self, action: str):
        self._log(LogLevel.DEBUG,
            f"[BIOME WATCHER] _execute_biome_leave called with action='{action}'",
            dev_only=True)
        if self._plugins:
            self._plugins.broadcast("on_biome_left", {"action": action})
        if action == "kill":
            self._log(LogLevel.INFO, "[BIOME WATCHER] Closing Roblox…")
            ProcessManager.kill_roblox()
        elif action == "home":
            self._log(LogLevel.INFO,
                "[BIOME WATCHER] Returning Roblox to home page — ready for next snipe…")
            killed = ProcessManager.kill_roblox_and_wait(timeout=5.0)
            self._log(LogLevel.DEBUG,
                f"[BIOME WATCHER] kill_roblox_and_wait result={killed}", dev_only=True)
            time.sleep(0.5)
            self._log_reader.mark_launch()   # reset log reader so next snipe reads fresh log
            try:
                if platform.system() == "Windows":
                    os.startfile("roblox://")
                    self._log(LogLevel.DEBUG,
                        "[BIOME WATCHER] os.startfile('roblox://') called", dev_only=True)
                elif platform.system() == "Darwin":
                    subprocess.Popen(["open", "roblox://"])
                else:
                    subprocess.Popen(["xdg-open", "roblox://"])
            except Exception as exc:
                self._log(LogLevel.ERROR, f"[BIOME WATCHER] Failed to relaunch Roblox: {exc}")
        else:
            self._log(LogLevel.DEBUG,
                f"[BIOME WATCHER] Unknown action '{action}' — no-op", dev_only=True)
