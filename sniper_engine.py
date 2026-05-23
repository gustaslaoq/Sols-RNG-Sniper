from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import shutil
import threading
import time
from collections import deque, OrderedDict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Any

import aiohttp
import psutil

logger = logging.getLogger("sniper_engine")

try:
    from slaoq_sniper_v2.app_info import APP_VERSION
except Exception:
    APP_VERSION = "2.0.1"


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


DISCORD_GATEWAY_URL  = "wss://gateway.discord.gg/?v=10&encoding=json"
LINK_RESOLVE_TIMEOUT = aiohttp.ClientTimeout(total=6, connect=3)
HTTP_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=8, connect=3)
WEBHOOK_LOGO_URL     = "https://cdn.discordapp.com/attachments/1341185707615719495/1481822728020295760/S7nWcFz.png"
ROBLOX_PROCESS_NAMES = {"RobloxPlayerBeta.exe", "RobloxPlayer.exe", "Windows10Universal.exe",
                        "RobloxPlayer", "Roblox"}

LOCAL_APP_DATA = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
ROBLOX_LOG_PATH = LOCAL_APP_DATA / "Roblox" / "logs"
LOG_TAIL_BYTES       = 131072


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

BIOME_IGNORE = frozenset([
    "SOL'S RNG", "ROBLOX", "RO BLOX",
])


PATTERNS = _Patterns()


def play_sound(freq: int = 1000, duration_ms: int = 200, filepath: str = "") -> None:
    if filepath and Path(filepath).exists():
        try:
            import ctypes

            fp = str(Path(filepath).resolve())
            alias = f"snipersound_{int(time.monotonic())}"
            cmd_open = f'open "{fp}" type mpegvideo alias {alias}'
            cmd_play = f"play {alias}"
            ctypes.windll.winmm.mciSendStringW(cmd_open, None, 0, None)
            ctypes.windll.winmm.mciSendStringW(cmd_play, None, 0, None)
        except Exception:
            pass
        return
    try:
        import winsound

        winsound.Beep(max(37, min(32767, freq)), max(1, duration_ms))
    except Exception:
        pass


def get_app_dir() -> Path:
    base = LOCAL_APP_DATA / "SlaoqSniper"
    base.mkdir(parents=True, exist_ok=True)
    return base

def get_config_path() -> Path:
    return get_app_dir() / "config.json"

def get_log_path() -> Path:
    p = get_app_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p / "sniper.log"

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
    priority:            int       = 0
    bypass_cooldown:     bool      = False
    sound_alert_path:    str       = ""
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
            return True
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


def _default_channels() -> list:
    return [
        ChannelConfig(
            guild_id="1186570213077041233",
            channel_id="1282542323590496277",
            name="Sol's RNG > #1282542323590496277",
            enabled=True,
        ),
        ChannelConfig(
            guild_id="1186570213077041233",
            channel_id="1282543762425516083",
            name="Sol's RNG > #1282543762425516083",
            enabled=True,
        ),
    ]


@dataclass
class WebhookConfig:
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
    monitored_channels:      list          = field(default_factory=_default_channels)
    profiles:                list          = field(default_factory=_default_profiles)
    auto_join_enabled:       bool          = True
    auto_join_delay_ms:      int           = 0
    pause_after_snipe_s:     int           = 0
    close_roblox_before_join: bool          = False
    biome_leave_action:      str           = "none"
    anti_bait_enabled:       bool          = True
    link_resolve_enabled:    bool          = True
    log_tail_bytes:          int           = LOG_TAIL_BYTES
    dev_mode:                bool          = False
    log_to_file:             bool          = False
    theme:                   str           = "dark"
    webhook:                 WebhookConfig = field(default_factory=WebhookConfig)
    cooldown_guild_ttl:      float         = 30.0
    cooldown_profile_ttl:    float         = 0.0
    cooldown_link_ttl:       float         = 10.0
    sound_alert_enabled:     bool          = False
    sound_alert_freq:        int           = 1000
    sound_alert_dur_ms:      int           = 200
    delete_watch_seconds:    int           = 0
    extra_tokens:            list          = field(default_factory=list)
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

        config_path = Path(self.config_path)
        tmp_path    = config_path.with_suffix(".json.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            shutil.move(str(tmp_path), str(config_path))
        except Exception:
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

            if "close_roblox_after_join" in raw and "close_roblox_before_join" not in raw:
                raw["close_roblox_before_join"] = raw.pop("close_roblox_after_join")
            else:
                raw.pop("close_roblox_after_join", None)

            valid_fields = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            cfg = cls(**valid_fields)
            cfg.monitored_channels  = channels
            cfg.profiles            = profiles
            cfg.webhook             = WebhookConfig.from_dict(webhook_raw)
            cfg.config_path         = path
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


@dataclass
class LogEntry:
    level:    LogLevel
    message:  str
    ts:       str  = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S.%f")[:-3])
    dev_only: bool = False



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
    def has_active_logs() -> bool:
        if not ROBLOX_LOG_PATH.exists():
            return False
        try:
            logs = list(ROBLOX_LOG_PATH.glob("*.log"))
            if not logs:
                return False
            now = time.time()
            for p in logs:
                try:
                    mtime = p.stat().st_mtime
                    if now - mtime < 30:
                        return True
                except OSError:
                    continue
        except Exception:
            pass
        return False

    @staticmethod
    def open_roblox_link(uri: str):
        try:
            os.startfile(uri)
            logger.info("Opened Roblox URI: %s", uri[:80])
        except Exception as exc:
            logger.error("Failed to open Roblox link %r: %s", uri[:80], exc)



class RobloxLogReader:

    _HOVER_IGNORE = BIOME_IGNORE | frozenset([""])

    def __init__(self, tail_bytes: int = LOG_TAIL_BYTES):
        self.tail_bytes           = tail_bytes
        self._launch_time: float  = 0.0
        self._session_log: Optional[Path] = None
        self._seek_pos: dict      = {}   # Path → int (last read position)
        self._read_buf: dict      = {}   # Path → str (rolling text buffer)
        self._last_known_biome: Optional[str] = None


    def mark_launch(self):
        self._launch_time = time.time()
        self._session_log = None
        self._seek_pos.clear()
        self._read_buf.clear()
        self._last_known_biome = None
        self._launch_log_offset: dict = {}
        if ROBLOX_LOG_PATH.exists():
            for p in ROBLOX_LOG_PATH.glob("*.log"):
                try:
                    self._launch_log_offset[p] = p.stat().st_size
                except OSError:
                    pass

    def reset_session(self):
        self._launch_time = 0.0
        self._session_log = None
        self._seek_pos.clear()
        self._read_buf.clear()
        self._last_known_biome = None


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

    def _parse_biome_from_line(self, line: str) -> Optional[str]:
        if "BloxstrapRPC" not in line or "SetRichPresence" not in line:
            return None
        if "Sol's RNG" not in line and "Sol\\'s RNG" not in line:
            return None
        
        if '"largeImage":{"hoverText":"' in line:
            try:
                biome = line.split('"largeImage":{"hoverText":"')[1].split('"')[0].strip().upper()
                if biome and biome not in self._HOVER_IGNORE:
                    return biome
            except (IndexError, AttributeError):
                pass
        
        if "largeImage" in line and "hoverText" in line:
            m = re.search(r'"largeImage"\s*:\s*\{[^}]*"hoverText"\s*:\s*"([^"]+)"', line, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip().upper()
                if candidate not in self._HOVER_IGNORE:
                    return candidate
        
        return None


    def _scan_buffer(self, text: str) -> Optional[str]:
        last_biome: Optional[str] = None
        for line in text.splitlines():
            found = self._parse_biome_from_line(line)
            if found:
                last_biome = found
        return last_biome


    def _ingest_new_bytes(self, path: Path) -> bool:
        try:
            size = path.stat().st_size
        except OSError:
            return False

        last_pos = self._seek_pos.get(path, 0)

        if last_pos == 0 and size > 0:
            launch_offset = getattr(self, "_launch_log_offset", {}).get(path, 0)
            start = max(launch_offset, size - self.tail_bytes)
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


    def _read_biome_from(self, path: Path) -> Optional[str]:
        had_new = self._ingest_new_bytes(path)
        if had_new:
            buf   = self._read_buf.get(path, "")
            found = self._scan_buffer(buf)
            if found:
                self._last_known_biome = found
        return self._last_known_biome


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
                    self._session_log = newer
                    self._seek_pos[newer] = 0
                    self._read_buf[newer] = ""
                    if hasattr(self, "_launch_log_offset"):
                        self._launch_log_offset.pop(old, None)
                    path = newer
        except Exception:
            pass

        self._session_log = path
        return self._read_biome_from(path)


    def wait_for_biome(self, timeout: float = 75.0, poll: float = 1.0) -> Optional[str]:
        launch_time = self._launch_time
        end = time.time() + timeout

        while time.time() < end:
            if not ROBLOX_LOG_PATH.exists():
                time.sleep(poll)
                continue
            
            best_log = None
            best_mtime = 0
            
            try:
                for p in ROBLOX_LOG_PATH.glob("*.log"):
                    try:
                        mtime = p.stat().st_mtime
                        if mtime > best_mtime:
                            best_mtime = mtime
                            best_log = p
                    except OSError:
                        continue
            except Exception:
                pass
            
            if best_log and best_mtime >= launch_time - 2:
                self._session_log = best_log
                self._seek_pos[best_log] = 0
                self._read_buf[best_log] = ""
                if hasattr(self, "_launch_log_offset"):
                    self._launch_log_offset[best_log] = 0
                
                biome = self.get_current_biome()
                if biome:
                    self._last_known_biome = biome
                    return biome
            
            time.sleep(poll)

        return None

    def debug_biome_detection(self) -> str:
        path = self._session_log or self._find_session_log()
        if not path:
            return f"No log file. _session_log={self._session_log}, _last_known={self._last_known_biome}"
        
        self._ingest_new_bytes(path)
        buf = self._read_buf.get(path, "")
        found = self._scan_buffer(buf)
        
        return f"log={path.name}, buf_len={len(buf)}, found={found}, last_known={self._last_known_biome}"

class LinkResolver:
    _CACHE_MAX = 512   # LRU cache — 512 resolved URLs

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
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

_URL_STRIP_RE = re.compile(
    r'https?://\S+|roblox://\S+', re.IGNORECASE)

def _strip_urls(text: str) -> str:
    return _URL_STRIP_RE.sub(" ", text).strip()


class ProfileFilter:
    def __init__(self, config: SniperConfig):
        self._cfg = config

    def _sorted_non_global(self) -> list:
        return sorted(
            (p for p in self._cfg.profiles if not p.locked and p.enabled),
            key=lambda p: p.priority,
        )

    def _global_blocked(self, clean: str):
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


    def evaluate(self, text: str) -> Optional[SnipeProfile]:
        profile, _ = self._match_profile(_strip_urls(text))
        return profile

    def evaluate_detailed(self, text: str) -> tuple:
        return self._match_profile(_strip_urls(text))

    def rebuild(self):
        for p in self._cfg.profiles:
            p.compile()

class DiscordGateway:
    def __init__(self, token: str, on_message: Callable, on_log: Callable,
                 on_status: Callable, config: SniperConfig,
                 on_message_delete: Callable = None,
                 label: str = "primary",
                 poll_fallback: bool = False):
        self.token      = token
        self.on_message = on_message
        self.on_log     = on_log
        self.on_status  = on_status
        self.config     = config
        self.on_message_delete = on_message_delete
        self.label = label
        self.poll_fallback = poll_fallback

        self._ws:                 Optional[aiohttp.ClientWebSocketResponse] = None
        self._session:            Optional[aiohttp.ClientSession]           = None
        self._heartbeat_task:     Optional[asyncio.Task]                    = None
        self._poll_task:          Optional[asyncio.Task]                    = None
        self._sequence:           Optional[int]                             = None
        self._session_id:         Optional[str]                             = None
        self._resume_gateway_url: str                                       = DISCORD_GATEWAY_URL
        self._ping_ms:            float                                     = 0.0
        self._running:            bool                                      = False
        self._last_hb:            float                                     = 0.0
        self._event_tasks:        set[asyncio.Task]                         = set()
        self._poll_seen:          dict[str, str]                             = {}

    @property
    def ping_ms(self) -> float:
        return self._ping_ms

    async def connect(self):
        self._running = True
        self.on_status(EngineStatus.CONNECTING)
        self.on_log(LogEntry(LogLevel.INFO, f"Connecting to Discord Gateway ({self.label})…"))
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
            if self.poll_fallback:
                self._poll_task = asyncio.create_task(self._poll_loop(), name=f"{self.label}_poll")
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

    async def _poll_loop(self):
        await asyncio.sleep(3.0)
        while self._running and self._session and not self._session.closed:
            channels = [c.channel_id for c in self.config.monitored_channels if c.enabled and c.channel_id]
            for channel_id in channels:
                try:
                    await self._poll_channel(channel_id)
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    self.on_log(LogEntry(
                        LogLevel.DEBUG,
                        f"[EXTRA] Poll failed for channel {channel_id}: {exc}",
                    ))
            await asyncio.sleep(2.0)

    async def _poll_channel(self, channel_id: str):
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=3"
        async with self._session.get(url) as response:
            if response.status in {401, 403, 404}:
                return
            if response.status == 429:
                retry_after = 2.0
                try:
                    body = await response.json()
                    retry_after = float(body.get("retry_after", retry_after))
                except Exception:
                    pass
                await asyncio.sleep(min(max(retry_after, 1.0), 8.0))
                return
            if response.status != 200:
                return
            messages = await response.json()

        if not isinstance(messages, list) or not messages:
            return
        latest_id = str(messages[0].get("id", ""))
        previous_id = self._poll_seen.get(channel_id)
        self._poll_seen[channel_id] = latest_id
        if previous_id is None:
            return

        fresh = []
        for message in messages:
            msg_id = str(message.get("id", ""))
            if not msg_id or msg_id == previous_id:
                break
            fresh.append(message)

        for message in reversed(fresh):
            self.on_log(LogEntry(
                LogLevel.DEBUG,
                f"[EXTRA] Polled message from channel {channel_id}",
            ))
            await self._on_message(message)

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
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(interval))
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
                self._spawn_event_task(self._on_message(d), "message_create")
            elif t == "MESSAGE_UPDATE":
                self._spawn_event_task(self._on_message(d, is_update=True), "message_update")
            elif t == "MESSAGE_DELETE":
                self._spawn_event_task(self._on_message_delete(d), "message_delete")

        elif op == 7:
            self.on_log(LogEntry(LogLevel.WARN, "Reconnect requested by server."))
            if self._ws and not self._ws.closed:
                await self._ws.close()

        elif op == 9:
            self.on_log(LogEntry(LogLevel.WARN, "Session invalidated. Reconnecting…"))
            self._session_id = None
            self._sequence   = None
            await asyncio.sleep(2)
            if self._ws and not self._ws.closed:
                await self._ws.close()

    async def _identify(self):
        await self._ws.send_json({"op": 2, "d": {
            "token": self.token,
            "properties": {"os": "windows", "browser": "Discord Client", "device": ""},
            "presence": {"status": "online", "afk": False},
        }})

    async def _resume(self):
        await self._ws.send_json({"op": 6, "d": {
            "token":      self.token,
            "session_id": self._session_id,
            "seq":        self._sequence,
        }})

    async def _heartbeat_loop(self, interval: float):
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

    def _spawn_event_task(self, coro, name: str) -> None:
        task = asyncio.create_task(coro, name=name)
        self._event_tasks.add(task)
        task.add_done_callback(self._on_event_task_done)

    def _on_event_task_done(self, task: asyncio.Task) -> None:
        self._event_tasks.discard(task)
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc:
            try:
                self.on_log(LogEntry(LogLevel.ERROR, f"Discord event task failed: {exc}"))
            except Exception:
                logger.exception("Discord event task failed: %s", exc)

    async def _on_message(self, data: dict, is_update: bool = False):
        ch      = str(data.get("channel_id") or "").strip()
        guild   = str(data.get("guild_id") or "").strip()
        msg_id  = str(data.get("id") or "").strip()
        content = data.get("content",    "")
        author  = data.get("author") or {}

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

        component_parts = []
        component_buttons = []
        for component in data.get("components", []):
            if not isinstance(component, dict):
                continue
            for item in component.get("components", []):
                if not isinstance(item, dict):
                    continue
                if item.get("type") == 2:
                    btn_label = item.get("label", "")
                    btn_url = item.get("url", "")
                    if btn_label:
                        component_parts.append(btn_label)
                        component_buttons.append((btn_label, btn_url))
                    if btn_url:
                        component_parts.append(btn_url)

        full_content = f"{content} {' '.join(embed_parts)} {' '.join(component_parts)}".strip()
        astr         = author.get("username", "?")
        author_id    = author.get("id", "").strip()
        avatar_hash  = author.get("avatar", "")
        if author_id and avatar_hash:
            author_avatar_url = (
                f"https://cdn.discordapp.com/avatars/{author_id}/{avatar_hash}.png?size=128"
            )
        else:
            author_avatar_url = ""
        author_display = (
            author.get("display_name") or author.get("global_name") or astr
        )

        monitored = any(
            c.channel_id == ch and c.enabled for c in self.config.monitored_channels)

        if not monitored:
            return

        await self.on_message(
            guild, ch, msg_id, content, astr, full_content,
            author_id=author_id,
            author_avatar_url=author_avatar_url,
            author_display=author_display,
            buttons=component_buttons if component_buttons else None,
            is_update=is_update,
        )

    async def _on_message_delete(self, data: dict):
        ch      = str(data.get("channel_id") or "").strip()
        msg_id  = str(data.get("id") or "").strip()
        guild   = str(data.get("guild_id") or "").strip()
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
        if self._poll_task:
            self._poll_task.cancel()
        for task in list(self._event_tasks):
            task.cancel()
        if self._event_tasks:
            await asyncio.gather(*self._event_tasks, return_exceptions=True)
            self._event_tasks.clear()
        if self._ws and not self._ws.closed:
            await self._ws.close()

    async def _cleanup(self):
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        if self._session and not self._session.closed:
            await self._session.close()

class SniperEngine:
    _SERVER_DEDUP_TTL  = 10.0
    _MSG_DEDUP_SIZE    = 200

    def __init__(
        self,
        config:    SniperConfig,
        blacklist: Any = None,   # BlacklistManager instance (injected from main.py)
        cooldown:  Any = None,   # CooldownManager  instance (injected from main.py)
    ):
        self.config = config

        self._gateway:  Optional[DiscordGateway] = None
        self._extra_gateways: dict[str, DiscordGateway] = {}
        self._resolver: Optional[LinkResolver]   = None
        self._filter:   Optional[ProfileFilter]  = None

        self._session:  Optional[aiohttp.ClientSession] = None
        self._tasks:    list                            = []
        self._running:  bool                            = False
        self._paused:   bool                            = False
        self._start_ts: float                           = 0.0
        self._paused_total: float                       = 0.0
        self._pause_started_at: float                   = 0.0
        self._auto_pause_task: Optional[asyncio.Task]   = None

        self._log_reader  = RobloxLogReader(config.log_tail_bytes)
        self._snipe_count = 0

        self.metrics: dict = {
            "messages_scanned":  0,
            "links_detected":    0,
            "snipes_successful": 0,
        }

        self._seen_msg_ids: deque = deque(maxlen=self._MSG_DEDUP_SIZE)
        self._pending_updates: dict = {}
        self._recent_servers: dict = {}
        self._deleted_msg_ids: deque = deque(maxlen=1000)
        self._delete_watch_targets: dict[str, tuple[float, str, str, float]] = {}

        self.blacklist = blacklist
        self.cooldown  = cooldown

        self._file_logger: Optional[logging.Logger] = None
        if config.log_to_file:
            self._setup_file_logger()

        self.on_log:              Callable = lambda e: None
        self.on_status:           Callable = lambda s: None
        self.on_snipe:            Callable = lambda data: None
        self.on_biome:            Callable = lambda exp, det, ok: None
        self.on_ping_update:      Callable = lambda p: None
        self.on_paused:           Callable = lambda v: None
        self.on_delete_blacklist: Callable = lambda uid, name: None


    @property
    def snipe_count(self) -> int:
        return self._snipe_count

    @property
    def ping_ms(self) -> float:
        return self._gateway.ping_ms if self._gateway else 0.0

    @property
    def uptime_seconds(self) -> float:
        if not self._running or not self._start_ts:
            return 0.0
        now = self._pause_started_at if self._paused and self._pause_started_at else time.monotonic()
        return max(0.0, now - self._start_ts - self._paused_total)

    def set_paused(self, paused: bool, log_message: str = ""):
        if paused == self._paused:
            return
        now = time.monotonic()
        if paused:
            self._paused = True
            self._pause_started_at = now
        else:
            self._paused = False
            if self._pause_started_at:
                self._paused_total += max(0.0, now - self._pause_started_at)
            self._pause_started_at = 0.0
            task = self._auto_pause_task
            if task and not task.done():
                try:
                    current = asyncio.current_task()
                except RuntimeError:
                    current = None
                if current is not task:
                    task.cancel()
                    self._auto_pause_task = None
        try:
            self.on_paused(self._paused)
        except Exception:
            pass
        if log_message:
            self._log(LogLevel.INFO, log_message)

    def _setup_file_logger(self):
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

    def _purge_expired_caches(self):
        now = time.monotonic()
        for d in (self._recent_servers,):
            expired = [k for k, exp in d.items() if now >= exp]
            for k in expired:
                del d[k]
        expired_deletes = [mid for mid, (deadline, *_rest) in self._delete_watch_targets.items() if now >= deadline]
        for mid in expired_deletes:
            self._delete_watch_targets.pop(mid, None)

    def _track_task(self, coro, name: str) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._tasks.append(task)
        task.add_done_callback(self._on_tracked_task_done)
        return task

    def _webhook_enabled_for(self, event: str) -> bool:
        webhook = getattr(self.config, "webhook", None)
        if not webhook or not webhook.enabled or not webhook.url.strip():
            return False
        return {
            "start": webhook.on_start,
            "stop": webhook.on_stop,
            "snipe": webhook.on_snipe,
            "biome": webhook.on_biome,
        }.get(event, False)

    @staticmethod
    def _discord_timestamp(dt: datetime) -> str:
        ts = int(dt.timestamp())
        return f"<t:{ts}:F> (<t:{ts}:R>)"

    @staticmethod
    def _discord_code_block(value: str, limit: int = 900) -> str:
        clean = str(value).replace("```", "'''")[:limit]
        return f"```{clean}```"

    def _webhook_ping_content(self) -> str:
        webhook = self.config.webhook
        target = webhook.ping_target.strip()
        if not target:
            return ""
        if target.startswith("<@"):
            return target
        if webhook.ping_type == "role":
            return f"<@&{target}>"
        if webhook.ping_type == "user":
            return f"<@{target}>"
        return target

    def _build_webhook_payload(self, event: str, **kwargs) -> dict | None:
        now = datetime.now(timezone.utc)
        ts_label = self._discord_timestamp(now)
        embed = {
            "color": 0xFFFFFF,
            "footer": {
                "text": f"Slaoq's Sniper v{APP_VERSION}",
                "icon_url": WEBHOOK_LOGO_URL,
            },
            "timestamp": now.isoformat(),
        }

        if event == "start":
            embed["title"] = ts_label
            embed["description"] = "> # Sniper Started"

        elif event == "stop":
            embed["title"] = ts_label
            embed["description"] = "> # Sniper Stopped"
            embed["color"] = 0x666666

        elif event == "snipe":
            profile_name = str(kwargs.get("profile") or "Unknown")
            verify_biome = str(kwargs.get("verify_biome_name") or "").strip().upper()
            author_display = str(kwargs.get("author_display") or kwargs.get("author") or "Unknown")
            author_name = str(kwargs.get("author") or author_display)
            author_avatar = str(kwargs.get("author_avatar_url") or "")
            raw_message = str(kwargs.get("raw_message") or "")
            roblox_web_url = str(kwargs.get("roblox_web_url") or kwargs.get("link") or "")
            jump_url = str(kwargs.get("jump_url") or "")
            keyword = str(kwargs.get("keyword") or "")
            buttons = kwargs.get("buttons") or []
            relative_ts = f"<t:{int(now.timestamp())}:R>"
            author_tag = f"@{author_name}" if author_name != author_display else f"@{author_display}"

            embed["author"] = {
                "name": f"Author: {author_display} ({author_tag})",
                "icon_url": author_avatar or WEBHOOK_LOGO_URL,
            }
            snipe_label = f"{verify_biome} Biome Sniped" if verify_biome else "Sniped"
            desc_lines = [f"> # {snipe_label} - {relative_ts}", ""]
            if roblox_web_url and not roblox_web_url.lower().startswith("roblox://"):
                desc_lines.append(f"## [Join Private Server Link]({roblox_web_url})")
            elif jump_url:
                desc_lines.append(f"[Jump to Original Message]({jump_url})")
            embed["description"] = "\n".join(desc_lines)
            embed["fields"] = [
                {"name": "Keyword Detected", "value": f'`"{keyword}"`' if keyword else "-", "inline": True},
                {"name": "Profile", "value": f"` {profile_name.upper()} `", "inline": True},
            ]
            if raw_message:
                embed["fields"].append({
                    "name": "Message Content",
                    "value": self._discord_code_block(raw_message),
                    "inline": False,
                })
            button_lines = []
            for button in buttons:
                if not isinstance(button, (list, tuple)) or len(button) < 2:
                    continue
                label, url = button[0], button[1]
                if label and url:
                    button_lines.append(f"**[{label}]({url})**")
            if button_lines:
                embed["fields"].append({
                    "name": "Buttons",
                    "value": "\n".join(button_lines),
                    "inline": False,
                })

        elif event == "biome":
            expected = str(kwargs.get("expected") or "Unknown")
            detected = str(kwargs.get("detected") or "Unknown")
            matched = bool(kwargs.get("match"))
            icon = "✅" if matched else "❌"
            embed["title"] = ts_label
            embed["description"] = (
                f"> ## {icon} Biome Verification - {'Match' if matched else 'Mismatch'}\n"
                f"**Expected:** `{expected}`\n"
                f"**Detected:** `{detected}`"
            )
            embed["color"] = 0xFFFFFF if matched else 0x444444

        else:
            return None

        payload = {
            "content": self._webhook_ping_content(),
            "embeds": [embed],
        }
        if payload["content"]:
            payload["allowed_mentions"] = {"parse": ["roles", "users"]}
        return payload

    async def _send_webhook(self, event: str, **kwargs) -> None:
        if not self._webhook_enabled_for(event):
            return
        webhook = self.config.webhook
        payload = self._build_webhook_payload(event, **kwargs)
        if not payload:
            return

        session = self._session
        owns_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession(timeout=HTTP_REQUEST_TIMEOUT)
            owns_session = True
        try:
            async with session.post(webhook.url, json=payload) as response:
                if response.status == 429:
                    retry_after = 1.0
                    try:
                        retry_after = float((await response.json()).get("retry_after", retry_after))
                    except Exception:
                        pass
                    await asyncio.sleep(max(0.2, min(retry_after, 8.0)))
                    async with session.post(webhook.url, json=payload) as retry_response:
                        if retry_response.status not in {200, 204}:
                            body = await retry_response.text()
                            self._log(LogLevel.WARN, f"[WEBHOOK] {event} retry failed: HTTP {retry_response.status} {body[:120]}")
                            return
                    self._log(LogLevel.INFO, f"[WEBHOOK] {event} notification sent.")
                    return
                if response.status not in {200, 204}:
                    body = await response.text()
                    self._log(LogLevel.WARN, f"[WEBHOOK] {event} failed: HTTP {response.status} {body[:120]}")
                    return
            self._log(LogLevel.INFO, f"[WEBHOOK] {event} notification sent.")
        except Exception as exc:
            self._log(LogLevel.WARN, f"[WEBHOOK] {event} failed: {exc}")
        finally:
            if owns_session:
                await session.close()

    def _on_tracked_task_done(self, task: asyncio.Task) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc:
            self._log(LogLevel.ERROR, f"[ENGINE] Background task failed: {exc}")


    async def start(self):
        if self._running:
            return
        self._running  = True
        self._paused   = False
        self._start_ts = time.monotonic()
        self._paused_total = 0.0
        self._pause_started_at = 0.0
        self._auto_pause_task = None
        self._set_status(EngineStatus.CONNECTING)

        connector     = aiohttp.TCPConnector(
            limit=50, ttl_dns_cache=300, use_dns_cache=True, keepalive_timeout=60)
        self._session = aiohttp.ClientSession(connector=connector, timeout=HTTP_REQUEST_TIMEOUT)
        self._resolver = LinkResolver(self._session)
        self._filter   = ProfileFilter(self.config)

        self._log(LogLevel.INFO, "[ENGINE] Sniper starting…")

        self._tasks = [
            asyncio.create_task(self._run_gateway(),      name="gateway"),
            asyncio.create_task(self._ping_updater(),     name="ping"),
            asyncio.create_task(self._log_monitor_loop(), name="log_monitor"),
        ]
        self._track_task(
            self._send_webhook("start"),
            "webhook_start",
        )

        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        finally:
            if self._session and not self._session.closed:
                await self._session.close()

    async def stop(self):
        if not self._running:
            return
        self._running = False
        self._paused  = False
        self._log(LogLevel.INFO, "[ENGINE] Stopping sniper…")
        await self._send_webhook("stop")

        if self.cooldown:
            self.cooldown.reset()

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
        if self._gateway:
            self._gateway.config = config
        for gateway in self._extra_gateways.values():
            gateway.config = config
        if self._filter:
            self._filter = ProfileFilter(config)
        if config.log_to_file and self._file_logger is None:
            self._setup_file_logger()
        elif not config.log_to_file:
            self._file_logger = None
        if self.cooldown and hasattr(self.cooldown, "update_config"):
            class _CD:
                pass
            cd = _CD()
            cd.guild_ttl   = getattr(config, "cooldown_guild_ttl",   30.0)
            cd.profile_ttl = getattr(config, "cooldown_profile_ttl",  0.0)
            cd.link_ttl    = getattr(config, "cooldown_link_ttl",    10.0)
            self.cooldown.update_config(cd)
        if self._running:
            self._sync_extra_gateways()

    def _sync_extra_gateways(self) -> None:
        desired = {
            token.strip()
            for token in getattr(self.config, "extra_tokens", [])
            if token.strip() and token.strip() != self.config.token
        }
        for token, gateway in list(self._extra_gateways.items()):
            if token not in desired:
                self._track_task(gateway.disconnect(), "gateway_extra_disconnect")
        for token in desired:
            if token not in self._extra_gateways:
                self._track_task(self._run_extra_gateway(token), "gateway_extra")

    async def _run_gateway(self):
        if not self.config.token:
            self._log(LogLevel.ERROR, "[ENGINE] Discord token not configured")
            self._set_status(EngineStatus.ERROR)
            self._running = False
            return

        self._gateway = DiscordGateway(
            token=self.config.token,
            on_message=self._on_discord_message,
            on_log=self.on_log,
            on_status=self._set_status,
            config=self.config,
            on_message_delete=self._on_discord_message_delete,
            label="primary",
        )

        self._sync_extra_gateways()

        await self._gateway.connect()

    async def _run_extra_gateway(self, token: str):
        if token in self._extra_gateways:
            return

        def extra_status(status):
            value = getattr(status, "value", str(status))
            if value == EngineStatus.CONNECTED.value:
                self._log(LogLevel.SUCCESS, "[ENGINE] Extra token gateway connected.")

        gw = DiscordGateway(
            token=token,
            on_message=self._on_discord_message,
            on_log=self.on_log,
            on_status=extra_status,
            config=self.config,
            on_message_delete=self._on_discord_message_delete,
            label="extra",
            poll_fallback=True,
        )
        self._extra_gateways[token] = gw
        self._log(LogLevel.INFO, "[ENGINE] Extra token gateway connecting.")
        try:
            await gw.connect()
        finally:
            self._extra_gateways.pop(token, None)

    async def _ping_updater(self):
        while self._running:
            await asyncio.sleep(2)
            if self._gateway:
                try:
                    self.on_ping_update(self._gateway.ping_ms)
                except Exception:
                    pass
            self._purge_expired_caches()
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

    async def _on_discord_message(self, guild_id: str, channel_id: str,
                                  msg_id: str, content: str, author: str, full: str,
                                  author_id: str = "", author_avatar_url: str = "",
                                  author_display: str = "", buttons: list = None,
                                  is_update: bool = False):
        if self._paused:
            return

        now = time.monotonic()

        expired = [mid for mid, ts in self._pending_updates.items()
                  if now - ts > 60]
        for mid in expired:
            del self._pending_updates[mid]

        if msg_id and msg_id in self._seen_msg_ids and not is_update:
            self._log(LogLevel.DEBUG,
                f"[DEDUP] Message ID already processed — skip", dev_only=True)
            return
        if not is_update and msg_id:
            self._seen_msg_ids.append(msg_id)

        self.metrics["messages_scanned"] += 1
        self._log(LogLevel.DEBUG,
            f"[MSG{'_UPDATE' if is_update else ''}] Processing from {author}: {content[:60]}",
            dev_only=True)

        if is_update and msg_id in self._pending_updates:
            del self._pending_updates[msg_id]

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
            if not is_update and msg_id:
                self._pending_updates[msg_id] = time.monotonic()
            return

        self._log(LogLevel.DEBUG,
            f"[FILTER] Profile '{profile.name}' matched — scanning for link", dev_only=True)

        link = self._resolver.extract_roblox_link(full)
        if not link:
            self._log(LogLevel.INFO,
                f"[FILTER] Profile '{profile.name}' matched but no Roblox link found — "
                f"{author}: {content[:60]}")
            if not is_update and msg_id:
                self._pending_updates[msg_id] = time.monotonic()
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
                return
            self.cooldown.mark(guild_id, profile.name, uri)

        self._snipe_count += 1
        self.metrics["snipes_successful"] += 1

        watch_s = getattr(self.config, "delete_watch_seconds", 0)
        if watch_s > 0 and author_id and msg_id:
            self._arm_delete_watch(author_id, author_display or author, msg_id, watch_s)

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

        jump_url = ""
        if guild_id and channel_id and msg_id:
            jump_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{msg_id}"

        if place_id and place_id != "0" and code:
            roblox_web_url = (
                f"https://www.roblox.com/games/{place_id}/"
                f"?privateServerLinkCode={code}"
            )
        elif place_id == "0" and code:
            roblox_web_url = f"https://www.roblox.com/share?code={code}&type=Server"
        else:
            roblox_web_url = ""
        if self.config.auto_join_enabled:
            if self.config.auto_join_delay_ms:
                self._log(LogLevel.DEBUG,
                    f"[JOIN] Waiting {self.config.auto_join_delay_ms}ms before joining…",
                    dev_only=True)
                await asyncio.sleep(self.config.auto_join_delay_ms / 1000)

            roblox_running   = ProcessManager.is_roblox_running()
            has_logs = ProcessManager.has_active_logs()
            in_game = has_logs if roblox_running else False
            force_close      = self.config.close_roblox_before_join
            self._log(LogLevel.DEBUG,
                f"[JOIN] roblox_running={roblox_running}, in_game={in_game}, "
                f"force_close={force_close}",
                dev_only=True)

            if roblox_running:
                self._log(LogLevel.INFO,
                    "[JOIN] Roblox already open — joining directly…")
                self._log_reader.mark_launch()
                ProcessManager.open_roblox_link(uri)

            else:
                self._log(LogLevel.INFO, "[JOIN] Roblox not running — launching…")
                self._log_reader.mark_launch()
                ProcessManager.open_roblox_link(uri)

        else:
            self._log(LogLevel.DEBUG, "[JOIN] auto_join_enabled=False — skipping join",
                dev_only=True)


        if profile.verify_biome_name and self.config.anti_bait_enabled:
            self._log(LogLevel.INFO,
                f"[ANTI-BAIT] Starting biome verification for '{profile.verify_biome_name.upper()}'…")
            self._track_task(self._verify_biome(profile, uri), "verify_biome")
        else:
            self._log(LogLevel.DEBUG,
                f"[JOIN] No biome verification (verify_biome_name='{profile.verify_biome_name}', "
                f"anti_bait={self.config.anti_bait_enabled})", dev_only=True)

        snd_path   = getattr(profile, "sound_alert_path", "") if profile else ""
        sound_enabled = getattr(self.config, "sound_alert_enabled", False)
        if sound_enabled or snd_path:
            self._log(LogLevel.DEBUG, "[ENGINE] Sound alert firing…", dev_only=True)
            freq       = getattr(self.config, "sound_alert_freq",   1000)
            dur        = getattr(self.config, "sound_alert_dur_ms",  200)
            threading.Thread(
                target=lambda: play_sound(freq, dur, snd_path),
                daemon=True, name="SoundAlert").start()

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
            "buttons":           buttons if buttons else [],
        }

        try:
            self.on_snipe(snipe_data)
        except Exception:
            pass
        self._track_task(
            self._send_webhook("snipe", **snipe_data),
            "webhook_snipe",
        )

        pause_s = self.config.pause_after_snipe_s
        if pause_s > 0:
            if self._auto_pause_task and not self._auto_pause_task.done():
                self._auto_pause_task.cancel()
            task = self._track_task(self._pause_after_snipe(pause_s), "pause_after_snipe")
            self._auto_pause_task = task

    async def _pause_after_snipe(self, pause_s: int):
        self.set_paused(True, f"[ENGINE] Auto-paused for {pause_s}s after snipe…")
        try:
            await asyncio.sleep(pause_s)
        except asyncio.CancelledError:
            return
        finally:
            if self._auto_pause_task is asyncio.current_task():
                self._auto_pause_task = None
        if self._running and self._paused:
            self.set_paused(False, "[ENGINE] Auto-pause ended — resuming scan.")

    def _arm_delete_watch(self, author_id: str, author_name: str, msg_id: str, watch_s: float) -> None:
        self._delete_watch_targets[msg_id] = (
            time.monotonic() + watch_s,
            author_id,
            author_name,
            watch_s,
        )
        self._log(LogLevel.DEBUG, f"[BLACKLIST] Watching message delete for {watch_s:.0f}s", dev_only=True)
        if msg_id in self._deleted_msg_ids:
            self._handle_watched_delete(msg_id)
            return
        self._track_task(self._delete_watch_timeout(msg_id, watch_s), "delete_watch")

    async def _delete_watch_timeout(self, msg_id: str, watch_s: float):
        await asyncio.sleep(watch_s)
        self._delete_watch_targets.pop(msg_id, None)

    def _handle_watched_delete(self, msg_id: str) -> bool:
        target = self._delete_watch_targets.pop(msg_id, None)
        if not target:
            return False
        _deadline, author_id, author_name, watch_s = target
        if self.blacklist:
            self.blacklist.add(author_id, author_name, reason="message_deleted")
            self._log(LogLevel.WARN,
                f"[BLACKLIST] Auto-blacklisted {author_name} ({author_id})"
                f" — deleted snipe message within {watch_s:.0f}s")
        try:
            self.on_delete_blacklist(author_id, author_name)
        except Exception:
            pass
        return True

    async def _on_discord_message_delete(self, guild_id: str, channel_id: str, msg_id: str):
        if msg_id:
            if self._handle_watched_delete(msg_id):
                return
            self._deleted_msg_ids.append(msg_id)

    async def _verify_biome(self, profile: SnipeProfile, uri: str):
        if not profile.verify_biome_name:
            return
        loop  = asyncio.get_running_loop()
        expected = profile.verify_biome_name.upper()
        self._log(LogLevel.INFO,
            f"[ANTI-BAIT] Waiting for biome in log… (expected: {expected}, timeout: 75s)")
        
        log_path = self._log_reader._session_log or self._log_reader._find_session_log()
        if log_path:
            self._log(LogLevel.DEBUG,
                f"[ANTI-BAIT] Using log file: {log_path.name}", dev_only=True)
        else:
            self._log(LogLevel.WARN,
                "[ANTI-BAIT] No log file found!")
        
        debug_info = self._log_reader.debug_biome_detection()
        self._log(LogLevel.DEBUG,
            f"[ANTI-BAIT] Debug: {debug_info}", dev_only=True)
        
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
                self._track_task(self._biome_watcher(expected, action), "biome_watcher")
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
                    try:
                        await loop.run_in_executor(
                            None, lambda: self._execute_biome_leave("home", force_restart=True))
                    except Exception as exc:
                        self._log(LogLevel.ERROR,
                            f"[ANTI-BAIT] Failed to return to home: {exc}")
                elif action == "kill":
                    self._log(LogLevel.WARN, "[ANTI-BAIT] Killing Roblox…")
                    ProcessManager.kill_roblox()
                else:
                    self._log(LogLevel.WARN, "[ANTI-BAIT] Killing Roblox…")
                    ProcessManager.kill_roblox()

        try:
            self.on_biome(expected, detected, matched)
        except Exception:
            pass
        self._track_task(
            self._send_webhook(
                "biome",
                expected=expected,
                detected=detected,
                match=matched,
            ),
            "webhook_biome",
        )

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

    def _execute_biome_leave(self, action: str, force_restart: bool = False):
        if action == "kill":
            ProcessManager.kill_roblox()
            return
        elif action == "home":
            killed = False
            roblox_running = ProcessManager.is_roblox_running()
            has_logs = ProcessManager.has_active_logs()
            in_game = has_logs
            
            if force_restart and roblox_running:
                killed = ProcessManager.kill_roblox_and_wait(timeout=5.0)
                if not killed and ProcessManager.is_roblox_running():
                    ProcessManager.kill_roblox()
                    time.sleep(1.0)
                self._log_reader.mark_launch()
                try:
                    os.startfile("roblox://")
                except Exception:
                    pass
                self._log(LogLevel.INFO, "[BIOME WATCHER] Roblox was restarted and returned to home.")
            elif not roblox_running:
                self._log_reader.mark_launch()
                try:
                    os.startfile("roblox://")
                except Exception:
                    pass
                self._log(LogLevel.INFO, "[BIOME WATCHER] Roblox was closed — relaunched to home.")
            elif in_game:
                killed = ProcessManager.kill_roblox_and_wait(timeout=5.0)
                time.sleep(1.5)
                self._log_reader.mark_launch()
                try:
                    os.startfile("roblox://")
                except Exception:
                    pass
                self._log(LogLevel.INFO, "[BIOME WATCHER] Roblox was in game — closed and relaunched to home.")
            else:
                self._log_reader.mark_launch()
                self._log(LogLevel.INFO, "[BIOME WATCHER] Roblox already on home page.")
        
