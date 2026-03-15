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
import re
import subprocess
import sys
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
ROBLOX_PROCESS_NAMES = {"RobloxPlayerBeta.exe", "RobloxPlayer.exe", "Windows10Universal.exe"}
ROBLOX_LOG_PATH      = Path(os.getenv("LOCALAPPDATA", "")) / "Roblox" / "logs"
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
                    pat = re.compile(kw if self.use_regex else re.escape(kw), flag)
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
    ping_type:    str  = "none"    # "none" | "role" | "user"
    ping_target:  str  = ""        # role/user ID when ping_type is role/user

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
    close_roblox_after_join: bool          = False
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
            "token":                   self.token,
            "monitored_channels":      [asdict(c) for c in self.monitored_channels],
            "profiles":                [p.to_dict() for p in self.profiles],
            "auto_join_enabled":       self.auto_join_enabled,
            "auto_join_delay_ms":      self.auto_join_delay_ms,
            "pause_after_snipe_s":     self.pause_after_snipe_s,
            "close_roblox_after_join": self.close_roblox_after_join,
            "anti_bait_enabled":       self.anti_bait_enabled,
            "link_resolve_enabled":    self.link_resolve_enabled,
            "log_tail_bytes":          self.log_tail_bytes,
            "dev_mode":                self.dev_mode,
            "log_to_file":             self.log_to_file,
            "theme":                   self.theme,
            "hotkey_toggle_key":       self.hotkey_toggle_key,
            "hotkey_toggle_en":        self.hotkey_toggle_en,
            "hotkey_pause_key":        self.hotkey_pause_key,
            "hotkey_pause_en":         self.hotkey_pause_en,
            "hotkey_pause_dur":        self.hotkey_pause_dur,
            "webhook":                 self.webhook.to_dict(),
            "cooldown": {
                "guild_ttl":   self.cooldown_guild_ttl,
                "profile_ttl": self.cooldown_profile_ttl,
                "link_ttl":    self.cooldown_link_ttl,
            },
        }
        with open(self.config_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Optional[str] = None) -> "SniperConfig":
        if path is None:
            path = str(get_config_path())
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            channels      = [ChannelConfig(**c) for c in raw.pop("monitored_channels", [])]
            profiles_raw  = raw.pop("profiles", [])
            profiles      = [SnipeProfile.from_dict(d) for d in profiles_raw] if profiles_raw else _default_profiles()
            webhook_raw   = raw.pop("webhook", {})
            cooldown_raw  = raw.pop("cooldown", {})
            raw.pop("CONFIG_PATH", None)  # legacy compat
            cfg = cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})
            cfg.monitored_channels  = channels
            cfg.profiles            = profiles
            cfg.webhook             = WebhookConfig.from_dict(webhook_raw)
            cfg.config_path         = path
            # Load cooldown TTLs (backwards-compatible: use defaults if key absent)
            if cooldown_raw:
                cfg.cooldown_guild_ttl   = cooldown_raw.get("guild_ttl",   30.0)
                cfg.cooldown_profile_ttl = cooldown_raw.get("profile_ttl",  0.0)
                cfg.cooldown_link_ttl    = cooldown_raw.get("link_ttl",    10.0)
            cfg.ensure_global()
            return cfg
        except (FileNotFoundError, json.JSONDecodeError, TypeError, KeyError):
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
    def open_roblox_link(uri: str):
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(uri)
            elif system == "Darwin":
                subprocess.Popen(["open", uri])
            else:
                subprocess.Popen(["xdg-open", uri])
        except Exception as exc:
            logger.error("Failed to open Roblox link: %s", exc)

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
    Session-aware Roblox log reader with incremental (seek-tracked) reading.

    Instead of re-reading the whole tail on every poll, we track the last
    read byte position per log file and only read newly appended data.
    This significantly reduces I/O on large log files.
    """

    def __init__(self, tail_bytes: int = LOG_TAIL_BYTES):
        self.tail_bytes       = tail_bytes
        self._launch_time:    float         = 0.0
        self._session_log:    Optional[Path] = None
        # ── incremental reading state ─────────────────────────────────────────
        # Maps log path → last byte offset successfully read
        self._seek_pos:       dict[Path, int] = {}
        # Accumulates partial text between reads so biome patterns aren't split
        self._read_buf:       dict[Path, str]  = {}

    def mark_launch(self):
        """Call immediately before opening the Roblox URI."""
        self._launch_time  = time.time()
        self._session_log  = None
        # Reset incremental state for the new session
        self._seek_pos.clear()
        self._read_buf.clear()
        ProcessManager.kill_roblox()
        time.sleep(0.5)

    def reset_session(self):
        self._launch_time  = 0.0
        self._session_log  = None
        self._seek_pos.clear()
        self._read_buf.clear()

    # ── private helpers ───────────────────────────────────────────────────────

    def _find_session_log(self) -> Optional[Path]:
        if not ROBLOX_LOG_PATH.exists():
            return None
        logs = list(ROBLOX_LOG_PATH.glob("*.log"))
        if not logs:
            return None

        candidates = []
        for p in logs:
            try:
                stat = p.stat()
                if stat.st_ctime >= self._launch_time - 2.0:
                    candidates.append((p, stat.st_mtime))
            except OSError:
                continue

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def _read_biome_from(self, path: Path) -> Optional[str]:
        """
        Read only new data appended since the last call (incremental seek).
        Falls back to full tail read on the first call for a given path.
        """
        try:
            size = path.stat().st_size
        except OSError:
            return None

        last_pos = self._seek_pos.get(path, max(0, size - self.tail_bytes))

        if last_pos >= size:
            # File hasn't grown; use accumulated buffer if any
            text = self._read_buf.get(path, "")
        else:
            try:
                with open(path, "rb") as fh:
                    fh.seek(last_pos)
                    new_bytes = fh.read()
                self._seek_pos[path] = size
            except (OSError, IOError):
                return None

            new_text = new_bytes.decode("utf-8", errors="ignore")
            # Keep a rolling window so patterns aren't split across reads
            prev_buf = self._read_buf.get(path, "")
            combined = prev_buf + new_text
            # Cap buffer to avoid unbounded growth
            if len(combined) > self.tail_bytes * 2:
                combined = combined[-(self.tail_bytes * 2):]
            self._read_buf[path] = combined
            text = combined

        for pattern in PATTERNS.BIOME_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                biome = matches[-1].strip().upper()
                if biome and biome.lower() not in ("none", "unknown", ""):
                    return biome

        tail_upper = text.upper()
        for biome in PATTERNS.BIOME_DIRECT:
            if biome in tail_upper:
                return biome

        return None

    # ── public API ────────────────────────────────────────────────────────────

    def get_current_biome(self) -> Optional[str]:
        if self._launch_time == 0:
            return None
        if not ProcessManager.is_roblox_running():
            return None

        if self._session_log is None:
            self._session_log = self._find_session_log()
        if not self._session_log:
            return None

        try:
            if not self._session_log.exists():
                self._session_log = None
                return None
            # Session log older than 60s with no new data is stale
            if time.time() - self._session_log.stat().st_mtime > 60:
                self._session_log = None
                return None
        except OSError:
            return None

        return self._read_biome_from(self._session_log)

    def wait_for_biome(self, timeout: float = 30.0) -> Optional[str]:
        """Blocking wait (run in executor). Returns biome name or None on timeout."""
        start = time.monotonic()
        roblox_seen = False

        while time.monotonic() - start < timeout:
            if not roblox_seen and ProcessManager.is_roblox_running():
                roblox_seen = True

            if not roblox_seen and (time.monotonic() - start) > 15:
                return None

            if roblox_seen:
                biome = self.get_current_biome()
                if biome:
                    return biome

            time.sleep(0.5)

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

class ProfileFilter:
    def __init__(self, config: SniperConfig):
        self._cfg = config

    def evaluate(self, text: str) -> Optional[SnipeProfile]:
        profiles  = self._cfg.profiles
        global_p  = next((p for p in profiles if p.locked), None)

        if global_p and global_p.enabled and global_p.matches_blacklist(text):
            return None

        sorted_profiles = sorted(
            (p for p in profiles if not p.locked and p.enabled),
            key=lambda p: p.priority,
        )

        for p in sorted_profiles:
            if p.matches_blacklist(text):
                continue
            if p.matches_triggers(text):
                return p

        return None

    def evaluate_detailed(self, text: str) -> tuple:
        profiles  = self._cfg.profiles
        global_p  = next((p for p in profiles if p.locked), None)

        if global_p and global_p.enabled and global_p.matches_blacklist(text):
            hit = next(
                (m.group(0) for pat in global_p._compiled_blacklist
                 if (m := pat.search(text))),
                "?"
            )
            return None, f"global blacklist keyword '{hit}'"

        sorted_profiles = sorted(
            (p for p in profiles if not p.locked and p.enabled),
            key=lambda p: p.priority,
        )

        for p in sorted_profiles:
            if p.matches_blacklist(text):
                hit = next(
                    (m.group(0) for pat in p._compiled_blacklist
                     if (m := pat.search(text))),
                    "?"
                )
                return None, f"profile '{p.name}' blacklist keyword '{hit}'"
            if p.matches_triggers(text):
                return p, ""

        return None, "no profile trigger matched"

    def rebuild(self):
        for p in self._cfg.profiles:
            p.compile()


# (WebhookSender lives in main.py — engine fires callbacks instead)


# ─────────────────────────────────────────────────────────────────────────────
# DISCORD GATEWAY CLIENT
# ─────────────────────────────────────────────────────────────────────────────

class DiscordGateway:
    def __init__(self, token: str, on_message: Callable, on_log: Callable,
                 on_status: Callable, config: SniperConfig):
        self.token      = token
        self.on_message = on_message
        self.on_log     = on_log
        self.on_status  = on_status
        self.config     = config

        self._ws:             Optional[aiohttp.ClientWebSocketResponse] = None
        self._session:        Optional[aiohttp.ClientSession]           = None
        self._heartbeat_task: Optional[asyncio.Task]                    = None
        self._sequence:       Optional[int]                             = None
        self._session_id:     Optional[str]                             = None
        self._ping_ms:        float                                     = 0.0
        self._running:        bool                                      = False
        self._last_hb:        float                                     = 0.0

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
            interval = d.get("heartbeat_interval", 41250) / 1000
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))
            await self._identify()

        elif op == 11:
            self._ping_ms = (time.monotonic() - self._last_hb) * 1000

        elif op == 0:
            if t == "READY":
                u = d.get("user", {})
                self._session_id = d.get("session_id")
                self.on_status(EngineStatus.CONNECTED)
                self.on_log(LogEntry(LogLevel.SUCCESS, f"Connected as: {u.get('username', '?')}"))
            elif t == "MESSAGE_CREATE":
                asyncio.create_task(self._on_message(d))

        elif op == 9:
            self.on_log(LogEntry(LogLevel.WARN, "Session invalidated. Reconnecting…"))
            await asyncio.sleep(2)
            if self._ws and not self._ws.closed:
                await self._ws.close()

    async def _identify(self):
        await self._ws.send_json({"op": 2, "d": {
            "token": self.token,
            "properties": {"os": "windows", "browser": "Discord Client", "device": ""},
            "presence": {"status": "online", "afk": False},
        }})

    async def _heartbeat_loop(self, interval: float):
        self._last_hb = time.monotonic()
        while self._running and self._ws and not self._ws.closed:
            try:
                self._last_hb = time.monotonic()
                await self._ws.send_json({"op": 1, "d": self._sequence})
                await asyncio.sleep(interval)
            except (aiohttp.ClientError, asyncio.CancelledError):
                break

    async def _on_message(self, data: dict):
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

        monitored = any(
            c.channel_id == ch and c.enabled for c in self.config.monitored_channels)

        if not monitored:
            known_guilds = {c.guild_id for c in self.config.monitored_channels}
            if guild in known_guilds:
                self.on_log(LogEntry(LogLevel.WARN,
                    f"[CONFIG] Message in known server — channel {ch} is not monitored"))
            else:
                self.on_log(LogEntry(LogLevel.DEBUG,
                    f"[MSG] Ignored — channel {ch} not in monitored list", dev_only=True))
            return

        self.on_log(LogEntry(LogLevel.DEBUG,
            f"[MSG] #{ch} | {astr}: {content[:80]}", dev_only=True))

        await self.on_message(guild, ch, msg_id, content, astr, full_content)

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

        # ── injected subsystems ───────────────────────────────────────────
        self.blacklist = blacklist   # Optional BlacklistManager
        self.cooldown  = cooldown    # Optional CooldownManager
        self._plugins  = plugins     # Optional PluginLoader

        # ── file logger ───────────────────────────────────────────────────
        self._file_logger: Optional[logging.Logger] = None
        if config.log_to_file:
            self._setup_file_logger()

        # Callbacks set by the Bridge
        self.on_log:          Callable = lambda e: None
        self.on_status:       Callable = lambda s: None
        self.on_snipe:        Callable = lambda data: None
        self.on_biome:        Callable = lambda exp, det, ok: None
        self.on_ping_update:  Callable = lambda p: None
        self.on_paused:       Callable = lambda v: None

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

        self._tasks = [
            asyncio.create_task(self._run_gateway(),      name="gateway"),
            asyncio.create_task(self._ping_updater(),     name="ping"),
            asyncio.create_task(self._log_monitor_loop(), name="log_monitor"),
        ]

        try:
            await asyncio.gather(*self._tasks)
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

        for task in self._tasks:
            task.cancel()

        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
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
        )
        await self._gateway.connect()

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
        loop = asyncio.get_event_loop()
        while self._running:
            await asyncio.sleep(1)
            if not ProcessManager.is_roblox_running():
                continue
            try:
                biome = await loop.run_in_executor(
                    None, self._log_reader.get_current_biome)
            except Exception:
                continue
            if biome:
                self._log(LogLevel.DEBUG, f"[BIOME] Current biome: {biome}", dev_only=True)

    # ── message handler ───────────────────────────────────────────────────────

    async def _on_discord_message(self, guild_id: str, channel_id: str,
                                  msg_id: str, content: str, author: str, full: str):
        if self._paused:
            self._log(LogLevel.DEBUG, f"[MSG] Skipped — engine is paused", dev_only=True)
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

        author_id = ""
        if self.blacklist and author_id and self.blacklist.is_blacklisted(author_id):
            entry = self.blacklist.get_entry(author_id)
            self._log(LogLevel.WARN,
                f"[BLACKLIST] Blocked {author} — reason: {entry.reason if entry else '?'}")
            return

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

        link = self._resolver.extract_roblox_link(full)
        if not link:
            self._log(LogLevel.INFO,
                f"[FILTER] Profile '{profile.name}' matched but no Roblox link found — "
                f"{author}: {content[:60]}")
            return

        self.metrics["links_detected"] += 1
        place_id, code, uri = link
        self._log(LogLevel.DEBUG,
            f"[LINK] Extracted URI: {uri[:80]}", dev_only=True)

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
                return
            self.cooldown.mark(guild_id, profile.name, uri)

        self._snipe_count += 1
        self.metrics["snipes_successful"] += 1

        self._log(LogLevel.SNIPE,
            f"[SNIPER] Profile '{profile.name}' — {author}: {content[:80]}")

        # ── 7. Build jump-to-message URL (populated in webhook payload) ───────
        jump_url = ""
        if guild_id and channel_id and msg_id:
            jump_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{msg_id}"

        # ── 8. Optional auto-join — execute first for minimum latency ─────────
        if self.config.auto_join_enabled:
            if self.config.auto_join_delay_ms:
                await asyncio.sleep(self.config.auto_join_delay_ms / 1000)

            self._log_reader.mark_launch()
            ProcessManager.open_roblox_link(uri)

            # Post-join biome verification (non-blocking)
            if profile.verify_biome_name and self.config.anti_bait_enabled:
                asyncio.create_task(self._verify_biome(profile, uri))

        # ── 9. Build snipe data dict ──────────────────────────────────────────
        snipe_data = {
            "place_id":    place_id,
            "code":        code,
            "uri":         uri,
            "profile":     profile.name,
            "author":      author,
            "raw_message": content[:1000],
            "link":        uri,
            "jump_url":    jump_url,
        }

        # ── 10. Fire on_snipe callback ────────────────────────────────────────
        try:
            self.on_snipe(snipe_data)
        except Exception:
            pass

        # ── 11. Broadcast to plugins ──────────────────────────────────────────
        if self._plugins:
            self._plugins.broadcast("on_snipe", snipe_data)

        # ── 12. Pause-after-snipe ─────────────────────────────────────────────
        pause_s = self.config.pause_after_snipe_s
        if pause_s > 0:
            self._paused = True
            try:
                self.on_paused(True)
            except Exception:
                pass
            self._log(LogLevel.INFO,
                f"[ENGINE] Auto-paused for {pause_s}s after snipe…")
            try:
                await asyncio.sleep(pause_s)
            finally:
                self._paused = False
            if self._running:
                try:
                    self.on_paused(False)
                except Exception:
                    pass
                self._log(LogLevel.INFO, "[ENGINE] Auto-pause ended — resuming scan.")

    async def _verify_biome(self, profile: SnipeProfile, uri: str):
        """Wait for Roblox to load and verify the active biome against the profile."""
        loop  = asyncio.get_event_loop()
        biome = await loop.run_in_executor(
            None, lambda: self._log_reader.wait_for_biome(30.0))

        if biome is None:
            self._log(LogLevel.WARN, "[ANTI-BAIT] Biome verification timed out")
            return

        expected = profile.verify_biome_name.upper()
        detected = biome.upper()
        matched  = (detected == expected)

        if matched:
            self._log(LogLevel.SUCCESS,
                f"[ANTI-BAIT] Biome verified ✓  ({detected})")
        else:
            self._log(LogLevel.WARN,
                f"[ANTI-BAIT] Wrong biome — expected '{expected}', got '{detected}'")
            if profile.kill_on_wrong_biome:
                self._log(LogLevel.WARN, "[ANTI-BAIT] Killing Roblox…")
                ProcessManager.kill_roblox()

        try:
            self.on_biome(expected, detected, matched)
        except Exception:
            pass
