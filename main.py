from __future__ import annotations
#
import sys
import subprocess
import os
import platform
import threading
import asyncio
import traceback
import datetime
import json
import time
import importlib
import importlib.util
import urllib.request
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Optional, Any

REQUIRED_LIBS = ["PySide6", "psutil", "keyboard", "aiohttp"]

def _install(package: str):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print(f"Failed to install {package}. Run: pip install {package}")

for _lib in REQUIRED_LIBS:
    try:
        __import__(_lib)
    except ImportError:
        print(f"Installing missing dependency: {_lib}…")
        _install(_lib)
        try:
            __import__(_lib)
        except ImportError:
            print(f"Critical: could not load {_lib}. Exiting.")
            sys.exit(1)

from PySide6.QtCore import (
    Qt, QSize, QPoint, QRect, Signal, QTimer, QObject, QEvent,
    QPropertyAnimation, QEasingCurve, QAbstractAnimation, QKeyCombination,
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QIcon, QPixmap, QCursor, QMouseEvent,
    QKeySequence, QShortcut, QPalette, QFont, QKeyEvent, QBrush, QImage,
    QLinearGradient, QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QTextEdit,
    QLineEdit, QCheckBox, QScrollArea, QSizePolicy, QSizeGrip,
    QSpinBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QFileDialog, QSplitter, QInputDialog, QMessageBox, QGridLayout,
    QProgressBar, QComboBox, QSystemTrayIcon, QMenu, QGraphicsOpacityEffect,
)
import aiohttp

try:
    from sniper_engine import (
        SniperEngine, SniperConfig, SnipeProfile, WebhookConfig,
        EngineStatus, LogEntry, LogLevel, ChannelConfig,
        _default_global_profile,
    )
except ImportError:
    print("Warning: sniper_engine not found. Running in UI-mock mode.")
    class LogLevel:
        INFO = 0; SUCCESS = 1; WARN = 2; ERROR = 3; DEBUG = 4; SNIPE = 5
    class LogEntry:
        def __init__(self, level, msg):
            self.level = level; self.message = msg
            self.ts = "00:00"; self.dev_only = False
    class EngineStatus:
        IDLE = 0; CONNECTING = 1; CONNECTED = 2; SNIPING = 3; ERROR = 4; STOPPED = 5
    class SnipeProfile:
        def __init__(self, name="Profile"):
            self.name = name; self.enabled = True; self.locked = False
            self.trigger_keywords = []; self.blacklist_keywords = []
            self.verify_biome_name = ""; self.kill_on_wrong_biome = False
            self.use_regex = False
        def compile(self): pass
    class ChannelConfig:
        def __init__(self, g, c, n): self.guild_id = g; self.channel_id = c
        self.name = n; self.enabled = True
    class WebhookConfig:
        url = ""; enabled = False; on_snipe = True; on_biome = True
        on_start = False; on_stop = False; ping_type = "none"; ping_target = ""
        def to_dict(self): return {}
    class SniperConfig:
        def __init__(self):
            self.token = ""; self.monitored_channels = []
            self.profiles = [SnipeProfile("Global")]; self.auto_join_enabled = True
            self.close_roblox_before_join = False; self.auto_join_delay_ms = 0
            self.anti_bait_enabled = True; self.dev_mode = False
            self.log_to_file = False; self.log_tail_bytes = 4096
            self.hotkey_toggle_key = ""; self.hotkey_toggle_en = False
            self.hotkey_pause_key = ""; self.hotkey_pause_en = False
            self.hotkey_pause_dur = 60; self.theme = "dark"
            self.webhook = WebhookConfig()
        @staticmethod
        def load(): return SniperConfig()
        def save(self): pass
        def ensure_global(self): pass
    class SniperEngine:
        snipe_count = 0; ping_ms = 0.0; uptime_seconds = 0.0
        def __init__(self, c): pass
        async def start(self): pass
        async def stop(self): pass
        def reload_config(self, c): pass
    def _default_global_profile(): return SnipeProfile("Global")

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

def _get_app_dir() -> Path:
    """Unified app data directory — LOCALAPPDATA/SlaoqSniper."""
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA", os.getenv("APPDATA", ""))) / "SlaoqSniper"
    else:
        base = Path.home() / ".config" / "slaoq-sniper"
    base.mkdir(parents=True, exist_ok=True)
    return base

def _trim_crash_logs(crash_dir: Path, keep: int = 50):
    """Keep only the <keep> most-recent crash logs; delete older ones."""
    try:
        logs = sorted(crash_dir.glob("crash_log_*.txt"), key=lambda p: p.stat().st_mtime)
        for old in logs[:-keep]:
            try:
                old.unlink()
            except OSError:
                pass
    except Exception:
        pass

def _setup_crash_reporter():
    def _handler(exc_type, exc_value, exc_tb):
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        stamp  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        crash_dir = _get_app_dir() / "crash_logs"
        try:
            crash_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        log_path = crash_dir / f"crash_log_{stamp}.txt"
        try:
            log_path.write_text(
                f"Slaoq's Sniper — Crash Report\n"
                f"Time: {datetime.datetime.now().isoformat()}\n"
                f"{'=' * 60}\n{tb_str}",
                encoding="utf-8",
            )
            _trim_crash_logs(crash_dir, keep=50)
        except Exception:
            pass
        print(f"[CRASH] Report saved to {log_path}")
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _handler

_setup_crash_reporter()


APP_NAME      = "SLAOQ'S SOL'S RNG SNIPER"
APP_VERSION   = "1.0"
GITHUB_REPO   = "gustaslaoq/Sols-RNG-Sniper"
EXE_NAME      = "SlaoqSniper"
_UPDATE_TRIGGERED = False
WIN_W         = 1200
WIN_H         = 800
WIN_MIN_W     = 760
WIN_MIN_H     = 520
SIDEBAR_MIN   = 70
SIDEBAR_MAX   = 260
SIDEBAR_RATIO = 0.20
SIDEBAR_SM    = 58
SIDEBAR_LG    = 220
TITLEBAR_H    = 38
RESIZE_M      = 6

def resource_path(relative_path: str) -> str:
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.abspath(".")
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.abspath(".")
    assets_path = os.path.join(exe_dir, "assets", relative_path)
    if os.path.exists(assets_path):
        return assets_path
    bundled = os.path.join(base, "assets", relative_path)
    if os.path.exists(bundled):
        return bundled
    return os.path.join(base, relative_path)

LOGO_PATH = Path(resource_path("logo.png"))
ICO_PATH  = Path(resource_path("app.ico"))

REASON_DELETED_LINK = "message_deleted"
REASON_INVALID_LINK = "invalid_link"
REASON_FAKE_SERVER  = "fake_server"
REASON_MOD_ACTION   = "moderation_action"
REASON_MANUAL       = "manual"


class BlacklistEntry:
    __slots__ = ("user_id", "username", "reason", "count", "last_event", "expires_at")

    def __init__(self, user_id: str, username: str, reason: str,
                 count: int = 1, last_event: float = 0.0, expires_at: float = 0.0):
        self.user_id    = user_id
        self.username   = username
        self.reason     = reason
        self.count      = count
        self.last_event = last_event or time.time()   # Bug 2 fix: use wall clock for persistence
        self.expires_at = expires_at

    def to_dict(self) -> dict:
        return {"username": self.username, "reason": self.reason,
                "count": self.count, "last_event": self.last_event,
                "expires_at": self.expires_at}

    @classmethod
    def from_dict(cls, user_id: str, d: dict) -> "BlacklistEntry":
        return cls(user_id=user_id, username=d.get("username", "unknown"),
                   reason=d.get("reason", REASON_MANUAL), count=d.get("count", 1),
                   last_event=d.get("last_event", time.monotonic()),
                   expires_at=d.get("expires_at", 0.0))

    def is_expired(self) -> bool:
        return self.expires_at > 0.0 and time.time() > self.expires_at


class BlacklistManager:
    def __init__(self, path: Path, default_ttl_hours: float = 0.0):
        self._path     = path
        self._ttl_secs = default_ttl_hours * 3600 if default_ttl_hours > 0 else 0.0
        self._lock     = Lock()
        self._entries: dict[str, BlacklistEntry] = {}
        self._load()

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as fh:
                raw = json.load(fh)
            for uid, data in raw.items():
                e = BlacklistEntry.from_dict(uid, data)
                if not e.is_expired():
                    self._entries[uid] = e
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {uid: e.to_dict() for uid, e in self._entries.items()}
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def add(self, user_id: str, username: str, reason: str = REASON_MANUAL,
            ttl_hours: float = 0.0):
        eff = (ttl_hours * 3600) if ttl_hours > 0 else self._ttl_secs
        exp = (time.time() + eff) if eff > 0 else 0.0
        with self._lock:
            if user_id in self._entries:
                e = self._entries[user_id]
                e.count += 1; e.reason = reason
                e.last_event = time.time(); e.expires_at = exp
            else:
                self._entries[user_id] = BlacklistEntry(
                    user_id=user_id, username=username, reason=reason, expires_at=exp)
            self._save()

    def remove(self, user_id: str) -> bool:
        with self._lock:
            if user_id in self._entries:
                del self._entries[user_id]; self._save(); return True
        return False

    def is_blacklisted(self, user_id: str) -> bool:
        with self._lock:
            e = self._entries.get(user_id)
            if e is None: return False
            if e.is_expired():
                del self._entries[user_id]; self._save(); return False
            return True

    def get_entry(self, user_id: str) -> Optional[BlacklistEntry]:
        with self._lock:
            e = self._entries.get(user_id)
            if e and e.is_expired():
                del self._entries[user_id]; self._save(); return None
            return e

    def all_entries(self) -> list:
        now = time.time()  
        with self._lock:
            expired = [uid for uid, e in self._entries.items()
                       if e.expires_at > 0 and now > e.expires_at]
            for uid in expired:
                del self._entries[uid]
            if expired: self._save()
            return list(self._entries.values())

    def clear(self):
        with self._lock:
            self._entries.clear(); self._save()

    def count(self) -> int:
        return len(self.all_entries())


class CooldownConfig:
    def __init__(self, guild_ttl: float = 30.0, profile_ttl: float = 0.0,
                 link_ttl: float = 10.0):
        self.guild_ttl   = guild_ttl
        self.profile_ttl = profile_ttl
        self.link_ttl    = link_ttl

    def to_dict(self) -> dict:
        return {"guild_ttl": self.guild_ttl, "profile_ttl": self.profile_ttl,
                "link_ttl": self.link_ttl}

    @classmethod
    def from_dict(cls, d: dict) -> "CooldownConfig":
        return cls(guild_ttl=d.get("guild_ttl", 30.0),
                   profile_ttl=d.get("profile_ttl", 0.0),
                   link_ttl=d.get("link_ttl", 10.0))


class CooldownManager:
    def __init__(self, config: Optional[CooldownConfig] = None):
        self._cfg   = config or CooldownConfig()
        self._state: dict[str, float] = {}
        self._lock  = Lock()

    def update_config(self, config: CooldownConfig):
        with self._lock: self._cfg = config

    def check(self, guild_id: str, profile_name: str, uri: str,
              bypass: bool = False) -> tuple:
        if bypass: return False, ""
        now = time.monotonic()
        with self._lock:
            cfg = self._cfg
            if cfg.guild_ttl > 0:
                k = f"guild:{guild_id}"
                if k in self._state and now < self._state[k]:
                    return True, f"guild cooldown ({self._state[k]-now:.1f}s left)"
            if cfg.profile_ttl > 0:
                k = f"profile:{profile_name}"
                if k in self._state and now < self._state[k]:
                    return True, f"profile cooldown ({self._state[k]-now:.1f}s left)"
            if cfg.link_ttl > 0:
                k = f"link:{uri.rstrip('/').lower()}"
                if k in self._state and now < self._state[k]:
                    return True, f"link cooldown ({self._state[k]-now:.1f}s left)"
        return False, ""

    def mark(self, guild_id: str, profile_name: str, uri: str):
        now = time.monotonic()
        with self._lock:
            cfg = self._cfg
            if cfg.guild_ttl   > 0: self._state[f"guild:{guild_id}"]   = now + cfg.guild_ttl
            if cfg.profile_ttl > 0: self._state[f"profile:{profile_name}"] = now + cfg.profile_ttl
            if cfg.link_ttl    > 0: self._state[f"link:{uri.rstrip('/').lower()}"] = now + cfg.link_ttl

    def purge_expired(self):
        now = time.monotonic()
        with self._lock:
            expired = [k for k, exp in self._state.items() if now >= exp]
            for k in expired: del self._state[k]

    def reset(self):
        with self._lock: self._state.clear()

    def active_count(self) -> int:
        now = time.monotonic()
        with self._lock: return sum(1 for exp in self._state.values() if now < exp)


class SnipeHistoryManager:
    MAX_ENTRIES = 500

    def __init__(self, path: Path):
        self._path    = path
        self._lock    = Lock()
        self._entries: list = []
        self._load()

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as fh:
                self._entries = json.load(fh)
            if not isinstance(self._entries, list):
                self._entries = []
        except (FileNotFoundError, json.JSONDecodeError):
            self._entries = []

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._entries[-self.MAX_ENTRIES:], fh, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def record(self, snipe_data: dict) -> str:
        """Record a snipe and return its unique snipe_id for later biome update."""
        snipe_id = snipe_data.get("uri", "") + "|" + snipe_data.get("timestamp_iso", "")
        entry = {
            "snipe_id":          snipe_id,
            "timestamp":         snipe_data.get("timestamp_iso", datetime.datetime.now().isoformat()),
            "profile":           snipe_data.get("profile", "?"),
            "author":            snipe_data.get("author", "?"),
            "author_id":         snipe_data.get("author_id", ""),
            "author_display":    snipe_data.get("author_display", ""),
            "author_avatar_url": snipe_data.get("author_avatar_url", ""),
            "keyword":           snipe_data.get("keyword", ""),
            "roblox_web_url":    snipe_data.get("roblox_web_url", ""),
            "uri":               snipe_data.get("uri", ""),
            "jump_url":          snipe_data.get("jump_url", ""),
            "raw_message":       snipe_data.get("raw_message", "")[:500],
            "biome_verified":    None,   # filled later by on_biome callback
        }
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self.MAX_ENTRIES:
                self._entries = self._entries[-self.MAX_ENTRIES:]
            self._save()
        return snipe_id

    def update_biome_by_id(self, snipe_id: str, verified: bool):
        """Bug 6 fix: target the specific snipe entry by ID, not always the last one."""
        with self._lock:
            for entry in reversed(self._entries):
                if entry.get("snipe_id") == snipe_id:
                    entry["biome_verified"] = verified
                    self._save()
                    return
            if self._entries:
                self._entries[-1]["biome_verified"] = verified
                self._save()

    def update_last_biome(self, verified: bool):
        """Legacy shim — prefer update_biome_by_id when snipe_id is available."""
        with self._lock:
            if self._entries:
                self._entries[-1]["biome_verified"] = verified
                self._save()

    def all_entries(self) -> list:
        with self._lock:
            return list(reversed(self._entries))   # newest first

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._save()


_PLUGIN_REQUIRED = ("PLUGIN_NAME", "PLUGIN_ICON", "PLUGIN_DESCRIPTION")


class PluginRecord:
    def __init__(self, module, path: Path):
        self.module  = module
        self.path    = path
        self.enabled = True
        self.error:  Optional[str] = None

    @property
    def name(self)        -> str: return getattr(self.module, "PLUGIN_NAME",        self.path.stem)
    @property
    def icon(self)        -> str: return getattr(self.module, "PLUGIN_ICON",        "bell")
    @property
    def description(self) -> str: return getattr(self.module, "PLUGIN_DESCRIPTION", "")
    @property
    def version(self)     -> str: return getattr(self.module, "PLUGIN_VERSION",     "1.0")
    @property
    def author(self)      -> str: return getattr(self.module, "PLUGIN_AUTHOR",      "")

    def call(self, fn_name: str, *args, **kwargs) -> Any:
        if not self.enabled or self.module is None: return None
        fn = getattr(self.module, fn_name, None)
        if not callable(fn): return None
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            print(f"[Plugin:{self.name}] Error in {fn_name}(): {exc}")
            return None

    def get_setting(self, key: str, default=None):
        settings = getattr(self.module, "PLUGIN_SETTINGS", {})
        return settings.get(key, default)

    def set_setting(self, key: str, value):
        if not hasattr(self.module, "PLUGIN_SETTINGS"):
            self.module.PLUGIN_SETTINGS = {}
        self.module.PLUGIN_SETTINGS[key] = value


class PluginLoader:
    def __init__(self, plugins_dir: Path):
        self._dir        = plugins_dir
        self._plugins:   list[PluginRecord] = []
        self._state_path = _get_app_dir() / "plugin_states.json"

    def _load_states(self) -> dict:
        try:
            with open(self._state_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_states(self):
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            states = {rec.name: rec.enabled for rec in self._plugins}
            with open(self._state_path, "w", encoding="utf-8") as fh:
                json.dump(states, fh, indent=2)
        except Exception:
            pass

    def discover(self) -> int:
        self._plugins.clear()
        if not self._dir.exists():
            try: self._dir.mkdir(parents=True, exist_ok=True)
            except Exception: return 0
        saved_states = self._load_states()
        loaded = 0
        for py_file in sorted(self._dir.glob("*.py")):
            if py_file.name.startswith("_"): continue
            rec = self._load_file(py_file)
            if rec:
                if rec.name in saved_states:
                    rec.enabled = saved_states[rec.name]
                elif py_file.stem == "example_plugin":
                    rec.enabled = False
                self._plugins.append(rec); loaded += 1
        return loaded

    def _load_file(self, path: Path) -> Optional[PluginRecord]:
        mod_name = f"_plugin_{path.stem}"
        try:
            spec   = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None: return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            return PluginRecord(module, path)
        except Exception as exc:
            rec = PluginRecord.__new__(PluginRecord)
            rec.path = path; rec.module = None
            rec.enabled = False; rec.error = str(exc)
            return rec

    def init_all(self, engine: Any, ui: Any):
        for rec in self._plugins:
            rec.call("init", engine, ui)

    def broadcast(self, event: str, *args, **kwargs):
        for rec in self._plugins:
            rec.call(event, *args, **kwargs)

    def plugins(self) -> list:
        return list(self._plugins)

    def get(self, name: str) -> Optional[PluginRecord]:
        return next((p for p in self._plugins if p.name == name), None)

    def set_enabled(self, name: str, enabled: bool):
        rec = self.get(name)
        if rec:
            rec.enabled = enabled
            self._save_states()


ASSETS: dict[str, str] = {
    "logo.png": "https://cdn.discordapp.com/attachments/1341185707615719495/1481822728020295760/S7nWcFz.png",
    "app.ico":  "",   # leave empty to skip
}


class AssetManager:
    def __init__(self, assets_dir: Path, asset_map: Optional[dict] = None,
                 download_timeout: int = 15):
        self._dir     = assets_dir
        self._map     = asset_map if asset_map is not None else dict(ASSETS)
        self._timeout = download_timeout
        self._dir.mkdir(parents=True, exist_ok=True)

    def missing(self) -> list[str]:
        return [n for n, url in self._map.items()
                if url and not (self._dir / n).exists()]

    def ensure_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name, url in self._map.items():
            if not url: continue
            dest = self._dir / name
            if dest.exists(): results[name] = True; continue
            results[name] = self._download(name, url, dest)
        return results

    def _download(self, name: str, url: str, dest: Path) -> bool:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SniperApp/Assets"})
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = resp.read()
            tmp = dest.with_suffix(".tmp"); tmp.write_bytes(data); tmp.replace(dest)
            return True
        except Exception:
            return False

    def path(self, name: str) -> Path: return self._dir / name
    def exists(self, name: str) -> bool: return (self._dir / name).exists()


class WebhookSender:
    _DEDUP_TTL = 5.0   # seconds — skip identical events within this window

    def __init__(self, session, config: WebhookConfig):
        self.session  = session
        self.config   = config
        self.logo_url = (
            "https://cdn.discordapp.com/attachments/1341185707615719495/"
            "1481822728020295760/S7nWcFz.png?ex=69b4b675&is=69b364f5"
            "&hm=d28e16d184224726d9167a1f9d2e653c3b4522e9f5402f00187c0d65dd80d68b"
            "&animated=true"
        )
        self._sent: dict = {}   # {dedup_key: expiry_monotonic}

    def _dedup_key(self, event_type: str, **kwargs) -> str:
        if event_type == "snipe":
            return f"snipe:{kwargs.get('profile','')}:{kwargs.get('link','')}"
        if event_type == "biome":
            return f"biome:{kwargs.get('expected','')}:{kwargs.get('detected','')}"
        return event_type

    def _is_duplicate(self, key: str) -> bool:
        now = time.monotonic()
        expired = [k for k, exp in self._sent.items() if now >= exp]
        for k in expired:
            del self._sent[k]
        if key in self._sent:
            return True
        self._sent[key] = now + self._DEDUP_TTL
        return False

    def _ping_content(self) -> str:
        t = self.config.ping_type
        if t == "role" and self.config.ping_target:
            return f"<@&{self.config.ping_target}>"
        if t == "user" and self.config.ping_target:
            return f"<@{self.config.ping_target}>"
        return ""

    @staticmethod
    def _discord_timestamp(dt: "datetime.datetime") -> str:
        ts = int(dt.timestamp())
        return f"<t:{ts}:F> (<t:{ts}:R>)"

    async def send(self, event_type: str, **kwargs):
        if not self.config.enabled or not self.config.url:
            return

        # Dedup check
        dedup_key = self._dedup_key(event_type, **kwargs)
        if self._is_duplicate(dedup_key):
            return

        now      = datetime.datetime.now(datetime.timezone.utc)
        ts_iso   = now.isoformat()
        ts_label = self._discord_timestamp(now)

        embed: dict = {
            "color": 0xFFFFFF,
            "footer": {
                "text":     f"Slaoq's Sniper v{APP_VERSION}",
                "icon_url": self.logo_url,
            },
            "timestamp": ts_iso,
        }

        content    = self._ping_content()
        components = []

        if event_type == "start":
            if not self.config.on_start:
                return
            embed["title"]       = ts_label
            embed["description"] = "> # Sniper Started"
            embed["color"]       = 0xFFFFFF

        elif event_type == "stop":
            if not self.config.on_stop:
                return
            embed["title"]       = ts_label
            embed["description"] = "> # Sniper Stopped"
            embed["color"]       = 0x666666

        elif event_type == "test":
            embed["title"]       = ts_label
            embed["description"] = "> # Webhook Test"
            embed["color"]       = 0xAAAAAA

        elif event_type == "snipe":
            if not self.config.on_snipe:
                return
            profile_name     = kwargs.get("profile", "Unknown")
            verify_biome     = (kwargs.get("verify_biome_name") or "").strip().upper()
            author_display   = kwargs.get("author_display") or kwargs.get("author", "Unknown")
            author_name      = kwargs.get("author", author_display)
            author_avatar    = kwargs.get("author_avatar_url", "")
            raw_msg          = kwargs.get("raw_message", "")
            roblox_web_url   = kwargs.get("roblox_web_url", kwargs.get("link", ""))
            jump_url         = kwargs.get("jump_url", "")
            keyword          = kwargs.get("keyword", "")
            ts_unix          = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

            author_tag = f"@{author_name}" if author_name != author_display else f"@{author_display}"
            embed["author"] = {
                "name":     f"Author: {author_display} ({author_tag})",
                "icon_url": author_avatar if author_avatar else self.logo_url,
            }

            if verify_biome:
                snipe_label = f"{verify_biome} Biome Sniped"
            else:
                snipe_label = "Sniped"

            desc_lines = [f"> # {snipe_label} — <t:{ts_unix}:R>", ""]
            if roblox_web_url and not roblox_web_url.startswith("roblox://"):
                desc_lines.append(f"## [Join Private Server Link]({roblox_web_url})")
            elif jump_url:
                desc_lines.append(f"[Jump to Original Message]({jump_url})")
            embed["description"] = "\n".join(desc_lines)
            embed["color"]       = 0xFFFFFF

            kw_val      = f'`"{keyword}"`' if keyword else "—"
            profile_val = f"` {profile_name.upper()} `"
            embed["fields"] = [
                {"name": "Keyword Detected", "value": kw_val,      "inline": True},
                {"name": "Profile",          "value": profile_val, "inline": True},
            ]
            if raw_msg:
                embed["fields"].append({
                    "name":   "Message Content",
                    "value":  f"```{raw_msg[:900]}```",
                    "inline": False,
                })

        elif event_type == "biome":
            if not self.config.on_biome:
                return
            expected = kwargs.get("expected", "Unknown")
            detected = kwargs.get("detected", "Unknown")
            is_match = kwargs.get("match", False)
            icon     = "✅" if is_match else "❌"
            embed["title"]       = ts_label
            embed["description"] = (
                f"> ## {icon} Biome Verification — {'Match' if is_match else 'Mismatch'}\n"
                f"**Expected:** `{expected}`\n**Detected:** `{detected}`"
            )
            embed["color"] = 0xFFFFFF if is_match else 0x444444

        elif event_type == "blacklist_deleted":
            uid      = kwargs.get("user_id", "?")
            uname    = kwargs.get("username", "?")
            embed["description"] = f"**{uid} (@{uname})** has been blacklisted for deleting their message."
            embed["color"]       = 0xc0392b

        else:
            return

        payload: dict = {
            "content":    content,
            "embeds":     [embed],
        }
        if components:
            payload["components"] = components

        try:
            async with self.session.post(
                self.config.url, json=payload,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 429:
                    try:
                        retry = float((await resp.json()).get("retry_after", 1))
                    except Exception:
                        retry = 1.0
                    await asyncio.sleep(retry)
                    async with self.session.post(
                        self.config.url, json=payload,
                        timeout=aiohttp.ClientTimeout(total=8),
                    ) as resp2:
                        if resp2.status not in (200, 204):
                            print(f"Webhook retry failed: {resp2.status}")
                elif resp.status not in (200, 204):
                    print(f"Webhook failed: {resp.status}")
        except Exception as exc:
            print(f"Webhook error: {exc}")


THEMES = {
    "dark": {
        "bg":      "#000000", "surface": "#080808", "card":    "#101010",
        "card2":   "#0c0c0c", "border":  "#1c1c1c", "border2": "#252525",
        "text":    "#d8d8d8", "muted":   "#999999", "dim":     "#666666",
        "white":   "#ffffff", "green":   "#00ff88", "green2":  "#00cc66",
        "red":     "#c0392b", "red2":    "#e74c3c", "yellow":  "#ffcc00",
        "orange":  "#ff8800", "purple":  "#aa66ff", "sel":     "#1a1a1a",
        "notif_red_bg":     "rgba(180,60,60,0.15)",
        "notif_red_border": "rgba(200,80,80,0.5)",
        "notif_yellow_bg":  "rgba(180,160,60,0.15)",
        "notif_yellow_border": "rgba(200,180,80,0.5)",
    },
    "oled": {
        "bg":      "#000000", "surface": "#000000", "card":    "#080808",
        "card2":   "#030303", "border":  "#111111", "border2": "#1a1a1a",
        "text":    "#e8e8e8", "muted":   "#888888", "dim":     "#555555",
        "white":   "#ffffff", "green":   "#00ff88", "green2":  "#00cc66",
        "red":     "#c0392b", "red2":    "#e74c3c", "yellow":  "#ffcc00",
        "orange":  "#ff8800", "purple":  "#aa66ff", "sel":     "#0d0d0d",
        "notif_red_bg":     "rgba(180,60,60,0.15)",
        "notif_red_border": "rgba(200,80,80,0.5)",
        "notif_yellow_bg":  "rgba(180,160,60,0.15)",
        "notif_yellow_border": "rgba(200,180,80,0.5)",
    },
    "light": {
        "bg":      "#f9f8f6", "surface": "#f3f2ef", "card":    "#ffffff",
        "card2":   "#faf9f7", "border":  "#e4e2dd", "border2": "#d5d2cc",
        "text":    "#1c1b19", "muted":   "#7a7771", "dim":     "#a8a49f",
        "white":   "#1c1b19",
        "green":   "#1a7a4a", "green2":  "#1d9057",
        "red":     "#b83228", "red2":    "#d43f32",
        "yellow":  "#a87d00", "orange":  "#b85e00",
        "purple":  "#6c44bb",
        "sel":     "#ede9e3",
        "notif_red_bg":     "rgba(184,50,40,0.08)",
        "notif_red_border": "rgba(184,50,40,0.28)",
        "notif_yellow_bg":  "rgba(168,125,0,0.08)",
        "notif_yellow_border": "rgba(168,125,0,0.28)",
    },
}

C: dict = dict(THEMES["dark"])

def apply_theme(name: str):
    palette = THEMES.get(name, THEMES["dark"])
    C.clear()
    C.update(palette)

def make_qss() -> str:
    return f"""
* {{
    font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', Arial, sans-serif;
    font-size: 12px; color: {C['text']};
    background-color: transparent; outline: none;
}}
QToolTip {{
    background-color: {C['card']}; color: {C['text']};
    border: 1px solid {C['border2']}; border-radius: 4px;
    padding: 6px 10px; font-size: 11px;
}}
#Root {{
    background-color: {C['bg']}; border: 1px solid {C['border2']};
    border-radius: 12px;
}}
#TitleBar {{
    background-color: {C['bg']}; border-bottom: 1px solid {C['border']};
    border-top-left-radius: 12px; border-top-right-radius: 12px;
    min-height: {TITLEBAR_H}px; max-height: {TITLEBAR_H}px;
}}
#AppTitle  {{ color: {C['white']}; font-size: 10px; font-weight: 700; letter-spacing: 3px; }}
#AppVersion {{ color: {C['dim']};  font-size: 9px;  letter-spacing: 1px; }}
#WinBtn {{
    background-color: transparent; color: {C['muted']}; border: none;
    border-radius: 0px; min-width: 46px; max-width: 46px;
    min-height: {TITLEBAR_H}px; max-height: {TITLEBAR_H}px;
    font-size: 14px; font-family: 'Segoe UI Symbol', 'Segoe UI', Arial, sans-serif;
}}
#WinBtn:hover {{ background-color: {C['sel']}; color: {C['white']}; }}
#Sidebar {{
    background-color: {C['bg']};
    border-right: 1px solid {C['border']};
}}
#SidebarName {{ color: {C['white']}; font-weight: 800; letter-spacing: 2px; }}
#SidebarSub  {{ color: {C['muted']}; letter-spacing: 2px; }}
#SidebarLogo {{ background-color: transparent; border: none; }}
#NavBtn {{
    background-color: transparent; color: {C['muted']}; border: none;
    border-radius: 6px; padding: 6px 10px; text-align: left;
    font-weight: 800; min-height: 32px; max-height: 32px;
}}
#NavBtn:hover            {{ color: {C['text']}; background-color: transparent; }}
#NavBtn[active="true"]   {{ background-color: transparent; color: {C['white']}; }}
#ContentArea {{ background-color: {C['surface']}; }}
#MetricCard {{
    background-color: {C['card']}; border: 1px solid {C['border']};
    border-radius: 10px;
}}
#MetricCard:hover {{
    background-color: {C['card2']}; border: 1px solid {C['border2']};
}}
#CardLabel  {{ color: {C['muted']}; font-size: 9px; font-weight: 700; letter-spacing: 2px; }}
#CardValue  {{ color: {C['white']}; font-size: 24px; font-weight: 800; letter-spacing: -1.5px; }}
#CardUnit   {{ color: {C['dim']};   font-size: 11px; }}
#BadgeON   {{ background-color: rgba(0,204,102,0.10); color: {C['green2']};
              border: 1px solid rgba(0,204,102,0.25); border-radius: 9px;
              padding: 2px 10px; font-size: 9px; font-weight: 700; letter-spacing: 1px; }}
#BadgeOFF  {{ background-color: rgba(255,68,68,0.10);  color: {C['red2']};
              border: 1px solid rgba(255,68,68,0.25);  border-radius: 9px;
              padding: 2px 10px; font-size: 9px; font-weight: 700; letter-spacing: 1px; }}
#BadgeIDLE {{ background-color: rgba(255,204,0,0.07);  color: {C['yellow']};
              border: 1px solid rgba(255,204,0,0.18);  border-radius: 9px;
              padding: 2px 10px; font-size: 9px; font-weight: 700; letter-spacing: 1px; }}
#PageTitle {{ color: {C['white']};  font-size: 19px; font-weight: 800; letter-spacing: -0.5px; }}
#PageSub   {{ color: {C['muted']};  font-size: 11px; }}
#SecTitle  {{ color: {C['muted']};  font-size: 9px;  font-weight: 700; letter-spacing: 2px; }}
#GrpLabel  {{ color: {C['muted']};  font-size: 11px; font-weight: 700; letter-spacing: 2px; margin-bottom: 2px; }}
#FieldLbl  {{ color: {C['text']};   font-size: 12px; }}
#FieldHint {{ color: #888888;        font-size: 10px; font-style: italic; }}
#ProfileName {{ color: {C['white']}; font-size: 13px; font-weight: 700; letter-spacing: 0.3px; }}
#LockedNote  {{
    color: {C['muted']}; font-size: 10px; font-style: italic;
    padding: 4px 8px; background-color: {C['card2']};
    border: 1px solid {C['border']}; border-radius: 5px;
}}
QLineEdit {{
    background-color: {C['card']}; border: 1px solid {C['border2']};
    border-radius: 6px; padding: 9px 12px;
    color: {C['text']}; font-size: 12px; min-height: 18px;
    selection-background-color: {C['sel']};
}}
QLineEdit:focus    {{ border: 1px solid {C['border2']}; }}
QLineEdit:disabled {{ color: {C['dim']}; background-color: {C['card2']}; }}
QTextEdit {{
    background-color: {C['card']}; border: 1px solid {C['border2']};
    border-radius: 6px; padding: 9px 12px;
    color: {C['text']}; font-size: 12px;
    selection-background-color: {C['sel']};
}}
QTextEdit:focus {{ border: 1px solid {C['border2']}; }}
QCheckBox {{
    color: {C['muted']}; font-size: 12px; spacing: 8px; min-height: 24px;
}}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {C['border2']}; background-color: {C['card']};
}}
QCheckBox::indicator:checked {{
    background-color: {C['white']}; border: 1px solid {C['white']};
}}
QCheckBox:hover   {{ color: #aaaaaa; }}
QCheckBox:checked {{ color: {C['text']}; }}
QSpinBox {{
    background-color: {C['card']}; border: 1px solid {C['border2']};
    border-radius: 6px; padding: 9px 12px;
    color: {C['text']}; font-size: 12px; min-width: 60px; min-height: 18px;
}}
QSpinBox:focus {{ border: 1px solid {C['border2']}; }}
QSpinBox::up-button, QSpinBox::down-button {{ background: transparent; border: none; width: 16px; }}
QSpinBox::up-arrow,  QSpinBox::down-arrow  {{ image: none; width: 0; }}
QComboBox {{
    background-color: {C['card']}; border: 1px solid {C['border2']};
    border-radius: 6px; padding: 6px 12px;
    color: {C['text']}; font-size: 12px; min-height: 18px;
}}
QComboBox:focus {{ border: 1px solid {C['border2']}; }}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {C['card']}; color: {C['text']};
    border: 1px solid {C['border2']}; selection-background-color: {C['sel']};
}}
#PrimaryBtn {{
    background-color: {C['white']}; color: #000;
    border: none; border-radius: 7px;
    padding: 9px 22px; font-size: 12px; font-weight: 700;
    min-width: 80px; min-height: 34px;
}}
#PrimaryBtn:hover    {{ background-color: #e8e8e8; }}
#PrimaryBtn:pressed  {{ background-color: #cccccc; }}
#PrimaryBtn:disabled {{ background-color: #181818; color: {C['dim']}; }}
#DangerBtn {{
    background-color: transparent; color: {C['red2']};
    border: 1px solid rgba(231,76,60,0.22); border-radius: 7px;
    padding: 9px 22px; font-size: 12px; font-weight: 600;
    min-width: 80px; min-height: 34px;
}}
#DangerBtn:hover {{
    background-color: rgba(231,76,60,0.06);
    border: 1px solid rgba(231,76,60,0.5);
}}
#PauseBtn {{
    background-color: transparent; color: {C['yellow']};
    border: 1px solid rgba(255,204,0,0.22); border-radius: 7px;
    padding: 9px 22px; font-size: 12px; font-weight: 600;
    min-width: 80px; min-height: 34px;
}}
#PauseBtn:hover {{
    background-color: rgba(255,204,0,0.06);
    border: 1px solid rgba(255,204,0,0.5);
}}
#PauseBtn:disabled {{ opacity: 0.35; }}
#GhostBtn {{
    background-color: transparent; color: {C['muted']};
    border: 1px solid {C['border']}; border-radius: 6px;
    padding: 6px 14px; font-size: 11px; min-height: 28px;
}}
#GhostBtn:hover {{ color: #aaaaaa; border: 1px solid #333; background-color: {C['card2']}; }}
#SmallBtn {{
    background-color: {C['card']}; color: {C['muted']};
    border: 1px solid {C['border']}; border-radius: 5px;
    padding: 5px 12px; font-size: 11px; min-height: 26px;
}}
#SmallBtn:hover {{ color: {C['white']}; border: 1px solid {C['border2']}; background-color: {C['sel']}; }}
#SmallDangerBtn {{
    background-color: transparent; color: {C['red2']};
    border: 1px solid rgba(231,76,60,0.2); border-radius: 5px;
    padding: 5px 12px; font-size: 11px; min-height: 26px;
}}
#SmallDangerBtn:hover {{
    background-color: rgba(231,76,60,0.06); border: 1px solid rgba(231,76,60,0.5);
}}
#LogConsole {{
    background-color: {C['card']}; color: {C['green']};
    border: 1px solid {C['border']}; border-radius: 8px;
    font-family: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 11px; selection-background-color: #1a1a1a; padding: 8px;
}}
#SettCard {{
    background-color: {C['card2']}; border: 1px solid {C['border']};
    border-radius: 9px; margin-top: 4px;
}}
#ProfileEditor  {{ background-color: {C['card2']}; border: 1px solid {C['border']}; border-radius: 9px; }}
#ProfileListWidget {{
    background-color: {C['card2']}; border: 1px solid {C['border']};
    border-right: none; border-top-left-radius: 6px; border-bottom-left-radius: 6px;
}}
#ProfileListWidget::item {{
    padding: 8px 10px; border-bottom: 1px solid {C['border']};
    color: {C['muted']};
}}
#ProfileListWidget::item:selected {{
    background-color: {C['sel']}; color: {C['white']};
}}
#HDivider {{ background-color: transparent; max-height: 1px; }}
#VDivider {{ background-color: {C['border']}; max-width: 1px; }}
#ChannelRow {{
    background-color: {C['card2']}; border-bottom: 1px solid {C['border']};
}}
#ChannelRow:hover {{ background-color: {C['sel']}; }}
#ChDeleteBtn {{
    background-color: transparent; border: none; border-radius: 4px;
    padding: 2px;
}}
#ChDeleteBtn:hover {{ background-color: rgba(231,76,60,0.12); }}
QScrollBar:vertical {{
    background: transparent; width: 6px; border: none; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['border2']}; border-radius: 3px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #3a3a3a; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 6px; border: none; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {C['border2']}; border-radius: 3px; min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QProgressBar {{
    background-color: {C['card']}; border: 1px solid {C['border2']};
    border-radius: 4px; height: 6px; text-align: center;
}}
QProgressBar::chunk {{
    background-color: {C['white']}; border-radius: 4px;
}}
"""

# SVG ICON LIBRARY

SVG = {
    # Navigation / sidebar
    "home":          '<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    "settings":      '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>',
    "logs":          '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>',
    "bell":          '<path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/>',
    "clock":         '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "zap":           '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "webhook":       '<path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
    "lock":          '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>',

    # Window controls
    "minimize":      '<line x1="5" y1="12" x2="19" y2="12"/>',
    "maximize":      '<rect x="3" y="3" width="18" height="18" rx="2"/>',
    "restore":       '<path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/>',
    "close":         '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',

    # Playback
    "play":          '<polygon points="5 3 19 12 5 21 5 3"/>',
    "stop":          '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>',
    "pause":         '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>',
    "skip-forward":  '<polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/>',
    "skip-back":     '<polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/>',
    "repeat":        '<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 014-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 01-4 4H3"/>',
    "volume":        '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 010 14.14"/><path d="M15.54 8.46a5 5 0 010 7.07"/>',
    "volume-x":      '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/>',
    "music":         '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',

    # Files & I/O
    "export":        '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    "import":        '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "upload":        '<polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3"/>',
    "download":      '<polyline points="8 17 12 21 16 17"/><line x1="12" y1="21" x2="12" y2="3"/>',
    "file":          '<path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"/><polyline points="13 2 13 9 20 9"/>',
    "file-text":     '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>',
    "file-plus":     '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/>',
    "folder":        '<path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>',
    "folder-open":   '<path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2v1"/><polyline points="2 10 22 10"/>',
    "archive":       '<polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>',
    "clipboard":     '<path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>',
    "trash":         '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/>',

    # Network / comms
    "wifi":          '<path d="M5 12.55a11 11 0 0114.08 0"/><path d="M1.42 9a16 16 0 0121.16 0"/><path d="M8.53 16.11a6 6 0 016.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>',
    "wifi-off":      '<line x1="1" y1="1" x2="23" y2="23"/><path d="M16.72 11.06A10.94 10.94 0 0119 12.55"/><path d="M5 12.55a11 11 0 015.17-2.39"/><path d="M10.71 5.05A16 16 0 0122.56 9"/><path d="M1.42 9a15.91 15.91 0 014.7-2.88"/><path d="M8.53 16.11a6 6 0 016.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>',
    "link":          '<path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>',
    "link-off":      '<path d="M9.88 9.88a3 3 0 104.24 4.24"/><path d="M10.73 5.08A10 10 0 0119.27 3a10 10 0 012.31 14.15"/><path d="M6.19 6.19A10 10 0 003 13a10 10 0 0014.31 8.49"/><line x1="1" y1="1" x2="23" y2="23"/>',
    "globe":         '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>',
    "server":        '<rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>',
    "cloud":         '<path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z"/>',
    "cloud-upload":  '<polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3"/>',
    "cloud-download":'<polyline points="8 17 12 21 16 17"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.88 18.09A5 5 0 0018 9h-1.26A8 8 0 103 16.29"/>',
    "rss":           '<path d="M4 11a9 9 0 019 9"/><path d="M4 4a16 16 0 0116 16"/><circle cx="5" cy="19" r="1"/>',
    "send":          '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
    "share":         '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>',

    # Status / feedback
    "check":         '<polyline points="20 6 9 17 4 12"/>',
    "check-circle":  '<path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    "x-circle":      '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
    "alert-circle":  '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    "alert-triangle":'<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "info":          '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    "help":          '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "loader":        '<line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/>',
    "shield":        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "shield-check":  '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',

    # User / social 
    "user":          '<path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "users":         '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/>',
    "user-plus":     '<path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/>',
    "user-minus":    '<path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="23" y1="11" x2="17" y2="11"/>',
    "user-x":        '<path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="18" y1="8" x2="23" y2="13"/><line x1="23" y1="8" x2="18" y2="13"/>',
    "message":       '<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>',
    "message-circle":'<path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"/>',

    # Tools / actions
    "refresh":       '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>',
    "edit":          '<path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>',
    "edit-2":        '<path d="M17 3a2.828 2.828 0 114 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>',
    "copy":          '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>',
    "scissors":      '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>',
    "search":        '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "filter":        '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "sliders":       '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
    "terminal":      '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
    "code":          '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    "cpu":           '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
    "database":      '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
    "key":           '<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>',
    "target":        '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "crosshair":     '<circle cx="12" cy="12" r="10"/><line x1="22" y1="12" x2="18" y2="12"/><line x1="6" y1="12" x2="2" y2="12"/><line x1="12" y1="6" x2="12" y2="2"/><line x1="12" y1="22" x2="12" y2="18"/>',
    "toggle-left":   '<rect x="1" y="5" width="22" height="14" rx="7" ry="7"/><circle cx="8" cy="12" r="3"/>',
    "toggle-right":  '<rect x="1" y="5" width="22" height="14" rx="7" ry="7"/><circle cx="16" cy="12" r="3"/>',
    "power":         '<path d="M18.36 6.64a9 9 0 11-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/>',
    "activity":      '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "bar-chart":     '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "pie-chart":     '<path d="M21.21 15.89A10 10 0 118 2.83"/><path d="M22 12A10 10 0 0012 2v10z"/>',
    "trending-up":   '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
    "eye":           '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    "eye-off":       '<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>',
    "tag":           '<path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>',
    "hash":          '<line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/>',

    # ─ Arrows / chevrons
    "chevron-left":  '<polyline points="15 18 9 12 15 6"/>',
    "chevron-right": '<polyline points="9 18 15 12 9 6"/>',
    "chevron-up":    '<polyline points="18 15 12 9 6 15"/>',
    "chevron-down":  '<polyline points="6 9 12 15 18 9"/>',
    "arrow-up":      '<line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>',
    "arrow-down":    '<line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/>',
    "arrow-left":    '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    "arrow-right":   '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    "move":          '<polyline points="5 9 2 12 5 15"/><polyline points="9 5 12 2 15 5"/><polyline points="15 19 12 22 9 19"/><polyline points="19 9 22 12 19 15"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="12" y1="2" x2="12" y2="22"/>',

    # Misc 
    "plus":          '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "minus":         '<line x1="5" y1="12" x2="19" y2="12"/>',
    "x":             '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "star":          '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    "heart":         '<path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/>',
    "bookmark":      '<path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>',
    "grid":          '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    "list":          '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
    "package":       '<line x1="16.5" y1="9.4" x2="7.55" y2="4.24"/><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 001 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
    "box":           '<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 001 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>',
    "tool":          '<path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>',
    "feather":       '<path d="M20.24 12.24a6 6 0 00-8.49-8.49L5 10.5V19h8.5z"/><line x1="16" y1="8" x2="2" y2="22"/><line x1="17.5" y1="15" x2="9" y2="15"/>',
    "award":         '<circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/>',
    "flag":          '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
    "map-pin":       '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>',
}

def _svg_icon(key: str, color: str = "#555555", sz: int = 16) -> QIcon:
    body = SVG.get(key, SVG["home"])
    svg  = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    px = QPixmap(sz, sz)
    px.fill(Qt.GlobalColor.transparent)
    try:
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtCore import QByteArray
        r = QSvgRenderer(QByteArray(svg.encode()))
        p = QPainter(px)
        r.render(p)
        p.end()
    except ImportError:
        pass
    return QIcon(px)

# EDGE RESIZE

class Edge:
    NONE = 0; L = 1; R = 2; T = 4; B = 8
    TL = L | T; TR = R | T; BL = L | B; BR = R | B
    _C = {
        L:  Qt.CursorShape.SizeHorCursor,  R:  Qt.CursorShape.SizeHorCursor,
        T:  Qt.CursorShape.SizeVerCursor,  B:  Qt.CursorShape.SizeVerCursor,
        TL: Qt.CursorShape.SizeFDiagCursor, BR: Qt.CursorShape.SizeFDiagCursor,
        TR: Qt.CursorShape.SizeBDiagCursor, BL: Qt.CursorShape.SizeBDiagCursor,
    }

    @classmethod
    def detect(cls, p: QPoint, w: int, h: int, m: int = RESIZE_M) -> int:
        x, y, e = p.x(), p.y(), cls.NONE
        if x <= m:       e |= cls.L
        elif x >= w - m: e |= cls.R
        if y <= m:       e |= cls.T
        elif y >= h - m: e |= cls.B
        return e

    @classmethod
    def cursor(cls, e: int) -> Qt.CursorShape:
        return cls._C.get(e, Qt.CursorShape.ArrowCursor)

# MICRO HELPERS

def create_taskbar_icon() -> QIcon:
    sz = 256
    if LOGO_PATH.exists():
        logo_pix = QPixmap(str(LOGO_PATH))
    else:
        logo_pix = QPixmap(sz, sz)
        logo_pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(logo_pix)
        p.setPen(QPen(QColor(C["white"]), 4))
        p.drawEllipse(20, 20, sz - 40, sz - 40)
        p.end()

    pad      = int(sz * 0.13)
    logo_s   = logo_pix.scaled(
        sz - pad * 2, sz - pad * 2,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation)
    bg = QPixmap(sz, sz)
    bg.fill(Qt.GlobalColor.transparent)
    pt = QPainter(bg)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    radius = sz * 0.22
    pt.setBrush(QColor("#000000"))
    pt.setPen(QPen(QColor("#ffffff"), sz * 0.012))
    pt.drawRoundedRect(QRect(0, 0, sz, sz), radius, radius)
    ox = (sz - logo_s.width())  // 2
    oy = (sz - logo_s.height()) // 2
    pt.drawPixmap(ox, oy, logo_s)
    pt.end()
    return QIcon(bg)

def get_tray_icon_img() -> QImage:
    if LOGO_PATH.exists():
        return QImage(str(LOGO_PATH)).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return QImage()

def lbl(text: str, obj: str = "", css: str = "") -> QLabel:
    w = QLabel(text)
    if obj: w.setObjectName(obj)
    if css: w.setStyleSheet(css)
    return w

class _GradientHDivider(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("HDivider")
        self.setFixedHeight(1)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w = self.width()
        col = QColor(C.get("border", "#1c1c1c"))
        g = QLinearGradient(0, 0, w, 0)
        g.setColorAt(0.0,  QColor(col.red(), col.green(), col.blue(), 0))
        g.setColorAt(0.25, QColor(col.red(), col.green(), col.blue(), 180))
        g.setColorAt(0.5,  QColor(col.red(), col.green(), col.blue(), 220))
        g.setColorAt(0.75, QColor(col.red(), col.green(), col.blue(), 180))
        g.setColorAt(1.0,  QColor(col.red(), col.green(), col.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRect(0, 0, w, 1)
        p.end()


def hdiv() -> _GradientHDivider:
    return _GradientHDivider()

def vdiv() -> QFrame:
    d = QFrame()
    d.setObjectName("VDivider")
    d.setFrameShape(QFrame.Shape.VLine)
    return d

class HelpIcon(QLabel):
    def __init__(self, tooltip_text: str, parent=None):
        super().__init__(parent)
        self._tip_text = tooltip_text
        icon = _svg_icon("help", C["dim"], 15)
        self.setPixmap(icon.pixmap(15, 15))
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.setFixedSize(20, 20)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("padding: 0px; margin: 0px;")
        self.setToolTip(tooltip_text)

    def enterEvent(self, event):
        from PySide6.QtWidgets import QToolTip
        QToolTip.showText(
            self.mapToGlobal(QPoint(self.width() + 4, self.height() // 2)),
            self._tip_text,
        )
        super().enterEvent(event)

# ENGINE BRIDGE

class Bridge(QObject):
    sig_log              = Signal(object)
    sig_status           = Signal(object)
    sig_snipe            = Signal(dict)
    sig_biome            = Signal(str, str, bool)
    sig_ping             = Signal(float)
    sig_paused           = Signal(bool)
    sig_delete_blacklist = Signal(str, str)   # uid, username

    def __init__(self, cfg: SniperConfig):
        super().__init__()

        app_dir = _get_app_dir()

        bl   = BlacklistManager(app_dir / "blacklist.json")
        hist = SnipeHistoryManager(app_dir / "snipe_history.json")

        cd_cfg = CooldownConfig(
            guild_ttl   = getattr(cfg, "cooldown_guild_ttl",   30.0),
            profile_ttl = getattr(cfg, "cooldown_profile_ttl",  0.0),
            link_ttl    = getattr(cfg, "cooldown_link_ttl",    10.0),
        )
        cd = CooldownManager(cd_cfg)

        if getattr(sys, "frozen", False):
            _base_dir = Path(os.path.dirname(sys.executable))
        else:
            _base_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        plugins_dir = _base_dir / "plugins"

        pl = PluginLoader(plugins_dir)
        pl.discover()

        self.engine  = SniperEngine(cfg, blacklist=bl, cooldown=cd, plugins=pl)
        self.history = hist
        self.blacklist_mgr = bl
        self._cfg    = cfg

        self._thread: Optional[threading.Thread]          = None
        self._loop:   Optional[asyncio.AbstractEventLoop] = None
        self._webhook_session: Optional[aiohttp.ClientSession] = None
        self._last_snipe_id: str = ""

        self.engine.on_log    = self.sig_log.emit
        self.engine.on_status = self.sig_status.emit
        self.engine.on_paused = self.sig_paused.emit
        self.engine.on_ping_update = self.sig_ping.emit

        def _on_snipe(data: dict):
            snipe_id = hist.record(data)
            self._last_snipe_id = snipe_id
            self.sig_snipe.emit(data)
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._send_snipe_webhook(data), self._loop)

        def _on_biome(exp: str, det: str, ok: bool):
            snipe_id = getattr(self, "_last_snipe_id", "")
            if snipe_id:
                hist.update_biome_by_id(snipe_id, ok)
            else:
                hist.update_last_biome(ok)
            self.sig_biome.emit(exp, det, ok)
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._send_biome_webhook(exp, det, ok), self._loop)

        def _on_delete_blacklist(uid: str, username: str):
            self.sig_delete_blacklist.emit(uid, username)
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._send_delete_blacklist_webhook(uid, username), self._loop)

        self.engine.on_snipe            = _on_snipe
        self.engine.on_biome            = _on_biome
        self.engine.on_delete_blacklist = _on_delete_blacklist

    async def _get_webhook_session(self) -> aiohttp.ClientSession:
        if self._webhook_session is None or self._webhook_session.closed:
            self._webhook_session = aiohttp.ClientSession()
        return self._webhook_session

    async def _send_lifecycle_webhook(self, event_type: str):
        try:
            sess   = await self._get_webhook_session()
            sender = WebhookSender(sess, self._cfg.webhook)
            await sender.send(event_type)
        except Exception:
            pass

    async def _send_snipe_webhook(self, data: dict):
        try:
            sess   = await self._get_webhook_session()
            sender = WebhookSender(sess, self._cfg.webhook)
            await sender.send("snipe", **data)
        except Exception:
            pass

    async def _send_biome_webhook(self, exp: str, det: str, ok: bool):
        try:
            sess   = await self._get_webhook_session()
            sender = WebhookSender(sess, self._cfg.webhook)
            await sender.send("biome", expected=exp, detected=det, match=ok)
        except Exception:
            pass

    async def _send_delete_blacklist_webhook(self, uid: str, username: str):
        try:
            sess   = await self._get_webhook_session()
            sender = WebhookSender(sess, self._cfg.webhook)
            await sender.send("blacklist_deleted", user_id=uid, username=username)
        except Exception:
            pass

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self.engine.start())
            finally:
                self._loop.close()

        self._thread = threading.Thread(target=_run, daemon=True, name="SnipeEngine")
        self._thread.start()

    def stop(self):
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.engine.stop(), self._loop)
            if self._webhook_session and not self._webhook_session.closed:
                asyncio.run_coroutine_threadsafe(
                    self._webhook_session.close(), self._loop)
        if self._thread:
            threading.Thread(
                target=self._thread.join, args=(4.0,),
                daemon=True, name="EngineJoin").start()

    def reload(self, cfg: SniperConfig):
        self._cfg = cfg   # keep local ref in sync so webhook sends use the new config
        self.engine.reload_config(cfg)

    def pause(self):
        self.engine._paused = True

    def resume(self):
        self.engine._paused = False

    @property
    def snipe_count(self) -> int:    return self.engine.snipe_count
    @property
    def ping_ms(self) -> float:      return self.engine.ping_ms
    @property
    def uptime_seconds(self) -> float: return self.engine.uptime_seconds

# REUSABLE WIDGETS

class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._hover   = False
        self.setFixedSize(36, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, v: bool):
        if v != self._checked:
            self._checked = v
            self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)

    def enterEvent(self, e):
        self._hover = True;  self.update(); super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False; self.update(); super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H, r = self.width(), self.height(), self.height() / 2
        if self._checked:
            track_col  = QColor(C["white"])
            border_col = QColor(C["white"])
            knob_col   = QColor(C["bg"])
            knob_x     = W - H + 2
        else:
            track_col  = QColor("#1c1c1c") if not self._hover else QColor("#252525")
            border_col = QColor(C["border2"])
            knob_col   = QColor(C["muted"])
            knob_x     = 2
        p.setBrush(track_col)
        p.setPen(QPen(border_col, 1))
        p.drawRoundedRect(0, 0, W, H, r, r)
        p.setBrush(knob_col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(knob_x, 2, H - 4, H - 4)
        p.end()


class PropagatingListWidget(QListWidget):
    def wheelEvent(self, e):
        bar   = self.verticalScrollBar()
        delta = e.angleDelta().y()
        at_top    = bar.value() == bar.minimum()
        at_bottom = bar.value() == bar.maximum()
        empty     = bar.minimum() == bar.maximum()

        can_scroll_up   = not at_top  and delta > 0
        can_scroll_down = not at_bottom and delta < 0

        if empty or (not can_scroll_up and not can_scroll_down):
            e.ignore()
        else:
            super().wheelEvent(e)


class SmoothScrollArea(QScrollArea):
    HOVER_MS   = 900    # ms the mouse must dwell over a child before it "owns" scroll
    STEP_PX    = 80     # pixels per scroll notch
    EASE       = 0.20   # easing factor per frame (higher = snappier)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target      = 0.0
        self._anim_timer  = QTimer(self)
        self._anim_timer.setInterval(12)
        self._anim_timer.timeout.connect(self._tick)

        self._hover_child  = None  
        self._hover_start  = 0.0   
        self.setMouseTracking(True)

    def _tick(self):
        bar  = self.verticalScrollBar()
        diff = self._target - bar.value()
        if abs(diff) < 0.8:
            bar.setValue(int(round(self._target)))
            self._anim_timer.stop()
            return
        bar.setValue(int(round(bar.value() + diff * self.EASE)))

    def _scrollable_child_at(self, pos) -> Optional["QWidget"]:
        child = self.widget()
        if not child:
            return None
        inner_pos = child.mapFrom(self, pos)
        w = child.childAt(inner_pos)
        from PySide6.QtWidgets import QAbstractScrollArea
        while w is not None and w is not self and w is not child:
            if isinstance(w, QAbstractScrollArea):
                sb = w.verticalScrollBar()
                if sb and sb.minimum() < sb.maximum():
                    return w
            w = w.parent()
        return None

    def mouseMoveEvent(self, e):
        pos   = e.position().toPoint()
        child = self._scrollable_child_at(pos)
        if child is not self._hover_child:
            self._hover_child = child
            self._hover_start = time.monotonic()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._hover_child = None
        self._hover_start = 0.0
        super().leaveEvent(e)

    def wheelEvent(self, e):
        bar = self.verticalScrollBar()
        if bar.minimum() == bar.maximum():
            e.ignore()
            return

        if (self._hover_child is not None
                and time.monotonic() - self._hover_start >= self.HOVER_MS / 1000.0):
            child = self._hover_child
            sb    = child.verticalScrollBar()
            delta = e.angleDelta().y()
            at_top = sb.value() == sb.minimum()
            at_bot = sb.value() == sb.maximum()
            if (delta > 0 and not at_top) or (delta < 0 and not at_bot):
                e.ignore()
                return

        steps = e.angleDelta().y() / 120.0
        self._target = max(float(bar.minimum()),
                           min(float(bar.maximum()),
                               self._target - steps * self.STEP_PX))
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        e.accept()


class EdgeCursorFilter(QObject):
    def __init__(self, window):
        super().__init__(window)
        self._win = window

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove and not self._win.isMaximized():
            try:
                gp   = event.globalPosition().toPoint()
                lp   = self._win.mapFromGlobal(gp)
                edge = Edge.detect(lp, self._win.width(), self._win.height())
                self._win.setCursor(QCursor(
                    Edge.cursor(edge) if edge != Edge.NONE else Qt.CursorShape.ArrowCursor))
            except Exception:
                pass
        return False


class ChannelItemRow(QFrame):
    delete_requested = Signal()
    changed          = Signal()

    def __init__(self, ch: "ChannelConfig", channel_label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ChannelRow")
        self._ch    = ch
        self._label = channel_label   # just the "#channel" part
        self.setMouseTracking(True)
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(32, 5, 10, 5); lay.setSpacing(10)  # 32px left indent

        self._toggle = ToggleSwitch(self._ch.enabled)
        self._toggle.toggled.connect(self._on_toggle)
        lay.addWidget(self._toggle)

        col = C["text"] if self._ch.enabled else C["muted"]
        self._name_lbl = QLabel(self._label)
        self._name_lbl.setStyleSheet(
            f"color: {col}; font-size: 12px; background: transparent;")
        self._id_lbl = QLabel(f"#{self._ch.channel_id}")
        self._id_lbl.setStyleSheet(
            f"color: {C['dim']}; font-size: 10px; background: transparent;")
        info = QVBoxLayout(); info.setSpacing(0)
        info.addWidget(self._name_lbl); info.addWidget(self._id_lbl)
        lay.addLayout(info); lay.addStretch()

        self._del_btn = QPushButton()
        self._del_btn.setObjectName("ChDeleteBtn")
        self._del_btn.setIcon(_svg_icon("trash", C["red2"], 13))
        self._del_btn.setIconSize(QSize(13, 13))
        self._del_btn.setFixedSize(26, 26)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setVisible(False)
        self._del_btn.clicked.connect(self.delete_requested.emit)
        lay.addWidget(self._del_btn)

    def _on_toggle(self, v: bool):
        self._ch.enabled = v
        col = C["text"] if v else C["muted"]
        self._name_lbl.setStyleSheet(
            f"color: {col}; font-size: 12px; background: transparent;")
        self.changed.emit()

    def enterEvent(self, e):  self._del_btn.setVisible(True);  super().enterEvent(e)
    def leaveEvent(self, e):  self._del_btn.setVisible(False); super().leaveEvent(e)


class ServerGroupHeader(QFrame):
    def __init__(self, guild_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ChannelRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 2); lay.setSpacing(6)
        icon_lbl = QLabel("⌗")
        icon_lbl.setStyleSheet(f"color: {C['muted']}; font-size: 11px; background: transparent;")
        lay.addWidget(icon_lbl)
        name_lbl = QLabel(guild_name)
        name_lbl.setStyleSheet(
            f"color: {C['white']}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;")
        lay.addWidget(name_lbl); lay.addStretch()


class ChannelRow(ChannelItemRow):
    def __init__(self, ch: "ChannelConfig", parent=None):

        name = ch.name or ""
        if "›" in name:
            channel_label = name.split("›", 1)[1].strip()
        else:
            channel_label = name
        super().__init__(ch, channel_label, parent)


class StatusBadge(QLabel):
    _MAP = {
        "on":   ("CONNECTED",    "BadgeON"),
        "off":  ("DISCONNECTED", "BadgeOFF"),
        "idle": ("IDLE",         "BadgeIDLE"),
        "err":  ("ERROR",        "BadgeOFF"),
    }
    def __init__(self, s: str = "idle"):
        super().__init__()
        self.set_state(s)

    def set_state(self, s: str):
        txt, obj = self._MAP.get(s, ("—", "BadgeIDLE"))
        self.setText(txt); self.setObjectName(obj)
        self.style().unpolish(self); self.style().polish(self)


class MetricCard(QFrame):
    _BASE_H  = 86
    _HOVER_H = 92   

    def __init__(self, label: str, value: str = "—", unit: str = ""):
        super().__init__()
        self.setObjectName("MetricCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(self._BASE_H)
        self.setMaximumHeight(self._BASE_H)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 10, 16, 10); lay.setSpacing(3)
        self._v = lbl(value, "CardValue")
        lay.addWidget(lbl(label.upper(), "CardLabel"))
        row = QHBoxLayout(); row.setSpacing(5)
        row.addWidget(self._v)
        row.addWidget(lbl(unit, "CardUnit"), alignment=Qt.AlignmentFlag.AlignBottom)
        row.addStretch()
        lay.addLayout(row)

        # height animation
        self._h_anim = QPropertyAnimation(self, b"maximumHeight")
        self._h_anim.setDuration(130)
        self._h_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._h_anim2 = QPropertyAnimation(self, b"minimumHeight")
        self._h_anim2.setDuration(130)
        self._h_anim2.setEasingCurve(QEasingCurve.Type.OutCubic)

        # counter animation state
        self._counter_from:  float = 0.0
        self._counter_to:    float = 0.0
        self._counter_t:     float = 1.0   # 1.0 = settled
        self._counter_timer  = QTimer(self)
        self._counter_timer.setInterval(16)
        self._counter_timer.timeout.connect(self._tick_counter)
        self._raw_value: str = value   # last set string (non-numeric pass-through)

    def set_value(self, v: str):
        self._raw_value = v
        # Try numeric counter animation for integer/float strings
        try:
            new_num = float(v)
            try:
                cur_num = float(self._v.text().replace("—", "0"))
            except ValueError:
                cur_num = 0.0
            if cur_num != new_num and v != "—":
                self._counter_from = cur_num
                self._counter_to   = new_num
                self._counter_t    = 0.0
                self._counter_timer.start()
                return
        except ValueError:
            pass
        self._counter_timer.stop()
        self._v.setText(v)

    def _tick_counter(self):
        self._counter_t = min(1.0, self._counter_t + 0.06)
        # ease-out cubic
        t = 1.0 - (1.0 - self._counter_t) ** 3
        current = self._counter_from + (self._counter_to - self._counter_from) * t
        # Format: int if target is int-like
        if self._counter_to == int(self._counter_to):
            self._v.setText(str(int(round(current))))
        else:
            self._v.setText(f"{current:.1f}")
        if self._counter_t >= 1.0:
            self._v.setText(self._raw_value)
            self._counter_timer.stop()

    def set_card_height(self, h: int):
        self._h_anim.stop(); self._h_anim2.stop()
        self.setMinimumHeight(h); self.setMaximumHeight(h)

    def _animate_to(self, h: int):
        cur = self.minimumHeight()
        for anim, prop in ((self._h_anim, b"maximumHeight"), (self._h_anim2, b"minimumHeight")):
            anim.stop()
            anim.setStartValue(cur)
            anim.setEndValue(h)
            anim.start()

    def enterEvent(self, event):
        self._animate_to(self._HOVER_H)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_to(self._BASE_H)
        super().leaveEvent(event)


class _GlowLogoLabel(QLabel):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h   = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        gr     = min(w, h) * 0.68
        rg = QRadialGradient(cx, cy, gr)
        rg.setColorAt(0.0,  QColor(255, 255, 255, 26))
        rg.setColorAt(0.4,  QColor(255, 255, 255, 13))
        rg.setColorAt(0.75, QColor(255, 255, 255, 4))
        rg.setColorAt(1.0,  QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rg)
        p.drawEllipse(int(cx - gr), int(cy - gr), int(gr * 2), int(gr * 2))
        p.end()
        super().paintEvent(event)


class NavButton(QPushButton):
    def __init__(self, key: str, text: str):
        super().__init__()
        self.setObjectName("NavBtn")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setProperty("active", False)
        self._text      = text
        self._ic        = _svg_icon(key)
        self._ic_act    = _svg_icon(key, "#ffffff")
        self._wide      = False
        self._active    = False
        self._hovered   = False

        # _active_t: 0.0 = fully inactive, 1.0 = fully active (animated)
        self._active_t  = 0.0
        # _hover_t:  0.0 = not hovered, 1.0 = hovered (only when inactive)
        self._hover_t   = 0.0

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(8)
        self._anim_timer.timeout.connect(self._tick_anim)

        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._apply()
        self.set_style(font_size=11, icon_size=18)

    def set_active(self, v: bool):
        self._active = v
        self.setProperty("active", v)
        self.style().unpolish(self); self.style().polish(self)
        if v:
            self._hover_t  = 0.0   # clear any hover state
            self._hovered  = False
        self._anim_timer.start()

    def set_hovered(self, hovered: bool):
        if self._active:
            return
        self._hovered = hovered
        self._anim_timer.start()

    def _tick_anim(self):
        settled_a = False
        settled_h = False

        # Active fade
        target_a = 1.0 if self._active else 0.0
        diff_a   = target_a - self._active_t
        if abs(diff_a) < 0.015:
            self._active_t = target_a
            settled_a = True
        else:
            self._active_t += diff_a * 0.18

        # Hover fade — slower and smoother
        target_h = (1.0 if self._hovered else 0.0) if not self._active else 0.0
        diff_h   = target_h - self._hover_t
        if abs(diff_h) < 0.015:
            self._hover_t = target_h
            settled_h = True
        else:
            self._hover_t += diff_h * 0.09   # gentle easing

        if settled_a and settled_h:
            self._anim_timer.stop()

        self._apply_sizes()

    def show_text(self, wide: bool):
        if wide != self._wide:
            self._wide = wide; self._apply()

    def set_style(self, font_size: int, icon_size: int):
        self._base_font = font_size
        self._base_icon = icon_size
        self._apply_sizes()

    def _apply_sizes(self):
        base_f = getattr(self, "_base_font", 11)
        base_i = getattr(self, "_base_icon", 18)
        at = self._active_t
        ht = self._hover_t

        # inactive: #505050  →  hover: #e0e0e0  →  active: #ffffff
        inactive_v = 0x50
        hover_v    = 0xe0
        active_v   = 0xff

        base_v  = int(inactive_v + ht * (hover_v - inactive_v))
        final_v = int(base_v + at * (active_v - base_v))
        color   = f"#{final_v:02x}{final_v:02x}{final_v:02x}"

        # Subtle size change: max +0.8px font on hover, +1.0px on active
        f_size = base_f + at * 1.0 + ht * 0.8
        i_size = base_i + int(at * 2) + int(ht * 1)
        # Very gentle forward nudge: max 3px
        ml     = int(ht * 3)

        self.setStyleSheet(
            f"font-size: {f_size:.1f}px; font-weight: 800; color: {color};"
            f" padding-left: {ml}px;"
        )
        self.setIcon(self._ic_act if self._active else self._ic)
        self.setIconSize(QSize(i_size, i_size))

    def _apply(self):
        if self._wide:
            self.setText(f"   {self._text}"); self.setToolTip("")
            self.setMinimumWidth(SIDEBAR_LG - 16); self.setMaximumWidth(SIDEBAR_LG - 16)
        else:
            self.setText(""); self.setToolTip(self._text)
            self.setMinimumWidth(40); self.setMaximumWidth(40)



class KeySequenceEdit(QLineEdit):
    keySequenceChanged = Signal(str)

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setPlaceholderText("Click & Press Key")

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return
        combination = QKeyCombination(event.modifiers(), Qt.Key(key))
        sequence    = QKeySequence(combination)
        self.setText(sequence.toString(QKeySequence.SequenceFormat.PortableText))
        self.keySequenceChanged.emit(self.text())

    def mousePressEvent(self, event):
        self.setFocus(); self.selectAll()

# LOADING

class _SplashBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value   = 0.0
        self._total   = 1
        self._shimmer = 0.0   # 0→1 running shimmer position
        self.setFixedHeight(8)
        self.setStyleSheet("background: transparent;")

        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(16)
        self._shimmer_timer.timeout.connect(self._tick_shimmer)

    def _tick_shimmer(self):
        self._shimmer = (self._shimmer + 0.012) % 1.0
        self.update()

    def set_progress(self, value: float, total: int):
        self._value = value
        self._total = total
        if value > 0 and not self._shimmer_timer.isActive():
            self._shimmer_timer.start()
        self.update()

    def stop_shimmer(self):
        self._shimmer_timer.stop()

    def paintEvent(self, event):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w  = self.width()
        h  = self.height()
        r  = h // 2   # fully rounded caps
        pct    = min(self._value, self._total) / max(1, self._total)
        filled = int(w * pct)

        p.setPen(Qt.PenStyle.NoPen)

        # track
        p.setBrush(QColor("#1a1a1a"))
        p.drawRoundedRect(0, 0, w, h, r, r)

        if filled > 0:
            # subtle glow behind bar
            glow_c = QColor(255, 255, 255, 14)
            p.setBrush(glow_c)
            p.drawRoundedRect(0, -2, filled, h + 4, r + 2, r + 2)

            # bar fill gradient
            grad = QLinearGradient(0, 0, filled, 0)
            grad.setColorAt(0.0, QColor("#c0c0c0"))
            grad.setColorAt(1.0, QColor("#ffffff"))
            p.setBrush(grad)
            p.drawRoundedRect(0, 0, filled, h, r, r)

            # shimmer: a bright travelling highlight
            if filled > 20:
                sw    = max(40, filled // 3)
                sx    = int((self._shimmer * (filled + sw)) - sw)
                sg    = QLinearGradient(sx, 0, sx + sw, 0)
                sg.setColorAt(0.0,  QColor(255, 255, 255, 0))
                sg.setColorAt(0.4,  QColor(255, 255, 255, 55))
                sg.setColorAt(0.6,  QColor(255, 255, 255, 55))
                sg.setColorAt(1.0,  QColor(255, 255, 255, 0))
                p.setBrush(sg)
                p.setClipRect(0, 0, filled, h)
                p.drawRoundedRect(sx, 0, sw, h, r, r)
                p.setClipping(False)

        p.end()


class SplashScreen(QWidget):
    finished       = Signal()
    _update_result = Signal(bool, str)

    _TASKS = [
        "Initializing runtime environment...",
        "Checking for updates...",
        "Loading profiles and configuration...",
        "Preparing snipe engine...",
        "Ready.",
    ]

    # window
    _W = 520
    _H = 320

    # logo
    _LOGO_SZ   = 88
    _LOGO_GAP  = 3           # gap between logo right edge and "SLAOQ" left edge
    _LOGO_Y    = 96          # top-y of logo row

    # subtitle
    _SUB_RISE  = 20          # px the subtitle rises during animation

    # bar
    _BAR_Y     = 270
    _BAR_PAD   = 52

    # speeds (increment per 16 ms frame)
    _FADE_IN_SPD   = 0.038   # ~420 ms
    _SLIDE_SPD     = 0.013   # ~1250 ms
    _BRAND_SPD     = 0.022   # ~730 ms 
    _SUB_SPD       = 0.018   # ~890 ms
    _BOTTOM_SPD    = 0.028   # ~570 ms
    _FADE_OUT_SPD  = 0.048   # ~330 ms

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self._W, self._H)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center().x() - self._W // 2,
                  screen.center().y() - self._H // 2)

        self._opacity      = 0.0
        self._phase        = 0
        self._logo_t       = 0.0
        self._logo_scale   = 0.65
        self._brand_t      = 0.0
        self._sub_t        = 0.0
        self._bottom_alpha = 0.0
        self._bar_value    = 0.0
        self._bar_target   = 0.0
        self._task_idx     = 0

        # computed in _build
        self._logo_cx_start = self._W // 2
        self._logo_cx_end   = 0
        self._brand_x_end   = 0
        self._brand_y       = 0
        self._sub_y_start   = 0
        self._sub_y_end     = 0

        self._update_result.connect(self._on_check_done)
        self._build()

    def _build(self):
        W, H = self._W, self._H
        sz   = self._LOGO_SZ
        gap  = self._LOGO_GAP
        ly   = self._LOGO_Y

        # background card
        self._root = QWidget(self)
        self._root.setObjectName("SplashRoot")
        self._root.setGeometry(0, 0, W, H)
        self._root.setStyleSheet(
            "QWidget#SplashRoot{"
            "background-color:#000000;"
            "border:1px solid #181818;"
            "border-radius:20px;}")

        self._glow = _SplashGlowWidget(self, sz, gap, ly)
        self._glow.setGeometry(0, 0, W, H)
        self._glow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._glow.hide()

        # logo
        self._logo_lbl = QLabel(self._root)
        self._logo_lbl.setFixedSize(sz, sz)
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_lbl.setStyleSheet("background:transparent;")
        self._logo_px_orig = None
        if LOGO_PATH.exists():
            px = QPixmap(str(LOGO_PATH)).scaled(
                sz, sz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._logo_px_orig = px
            self._logo_lbl.setPixmap(px)
        self._logo_eff = QGraphicsOpacityEffect(self._logo_lbl)
        self._logo_eff.setOpacity(0.0)
        self._logo_lbl.setGraphicsEffect(self._logo_eff)
        self._logo_lbl.move(self._logo_cx_start - sz // 2, ly)

        self._brand_lbl = QLabel("SLAOQ", self._root)
        self._brand_lbl.setStyleSheet(
            "color:#ffffff;font-size:34px;font-weight:800;"
            "letter-spacing:4px;background:transparent;")
        self._brand_lbl.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._brand_lbl.adjustSize()
        bw = self._brand_lbl.width()
        bh = self._brand_lbl.height()

        # centre the [logo + gap + brand] group in the window
        group_w = sz + gap + bw
        gx      = (W - group_w) // 2
        self._logo_cx_end  = gx + sz // 2
        self._brand_x_end  = gx + sz + gap
        self._brand_y      = ly + (sz - bh) // 2

        self._brand_lbl.move(self._brand_x_end, self._brand_y)
        self._brand_eff = QGraphicsOpacityEffect(self._brand_lbl)
        self._brand_eff.setOpacity(0.0)
        self._brand_lbl.setGraphicsEffect(self._brand_eff)

        self._glow.set_positions(
            logo_cx=self._logo_cx_end, logo_y=ly, logo_sz=sz,
            brand_x=self._brand_x_end, brand_y=self._brand_y,
            brand_w=bw, brand_h=bh)

        # subtitle
        self._sub_y_end   = ly + sz + 10   # closer to logo row
        self._sub_y_start = self._sub_y_end + self._SUB_RISE

        self._sub_lbl = _ShimmerLabel("SOL'S RNG SNIPER", self._root)
        self._sub_lbl.setFixedWidth(W)
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._sub_lbl.move(0, self._sub_y_start)

        self._sub_eff = QGraphicsOpacityEffect(self._sub_lbl)
        self._sub_eff.setOpacity(0.0)
        self._sub_lbl.setGraphicsEffect(self._sub_eff)

        pad   = self._BAR_PAD
        bar_w = W - pad * 2

        self._bottom_container = QWidget(self._root)
        self._bottom_container.setGeometry(0, self._BAR_Y - 8, W, 48)
        self._bottom_container.setStyleSheet("background:transparent;")

        self._bar_w = _SplashBarWidget(self._bottom_container)
        self._bar_w.setGeometry(pad, 6, bar_w, 8)

        self._task_lbl = QLabel(self._TASKS[0], self._bottom_container)
        self._task_lbl.setGeometry(pad, 20, bar_w, 16)
        self._task_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._task_lbl.setStyleSheet(
            "color:#383838;font-size:10px;letter-spacing:0.3px;background:transparent;")

        self._bottom_eff = QGraphicsOpacityEffect(self._bottom_container)
        self._bottom_eff.setOpacity(0.0)
        self._bottom_container.setGraphicsEffect(self._bottom_eff)

        # timers
        self._master_timer = QTimer(self)
        self._master_timer.setInterval(16)
        self._master_timer.timeout.connect(self._tick)

        self._step_timer = QTimer(self)
        self._step_timer.setInterval(680)
        self._step_timer.timeout.connect(self._step)


    @staticmethod
    def _ease_out_expo(t):
        return 1.0 if t >= 1.0 else 1.0 - pow(2.0, -10.0 * t)

    @staticmethod
    def _ease_out_quint(t):
        return 1.0 - (1.0 - t) ** 5

    @staticmethod
    def _ease_in_out_sine(t):
        import math
        return -(math.cos(math.pi * t) - 1.0) / 2.0

    def _set_logo_scale(self, scale: float, cx: float):
        """Resize logo label to simulate zoom, centered at cx, LOGO_Y."""
        sz = self._LOGO_SZ
        new_sz = max(4, int(sz * scale))
        self._logo_lbl.setFixedSize(new_sz, new_sz)
        if self._logo_px_orig:
            scaled_px = self._logo_px_orig.scaled(
                new_sz, new_sz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._logo_lbl.setPixmap(scaled_px)
        self._logo_lbl.move(int(cx - new_sz / 2), self._LOGO_Y + (sz - new_sz) // 2)

    def _tick(self):
        if self._opacity < 1.0:
            self._opacity = min(1.0, self._opacity + self._FADE_IN_SPD)
            self.setWindowOpacity(self._opacity)

        if self._phase == 0:
            # Logo zooms in (0.65→1.0) AND slides from center to final pos
            self._logo_t = min(1.0, self._logo_t + self._SLIDE_SPD)
            e_slide = self._ease_out_expo(self._logo_t)
            e_zoom  = self._ease_out_quint(self._logo_t)
            sz = self._LOGO_SZ

            # slide cx
            cx = self._logo_cx_start + (self._logo_cx_end - self._logo_cx_start) * e_slide
            # zoom scale: 0.65 → 1.0
            scale = 0.65 + e_zoom * 0.35
            self._logo_scale = scale

            # fade in opacity during first 40%
            fade_in = min(1.0, self._logo_t / 0.4)
            self._logo_eff.setOpacity(fade_in)

            self._set_logo_scale(scale, cx)

            # logo glow fades in during second half
            if self._logo_t > 0.5:
                glow_alpha = (self._logo_t - 0.5) / 0.5
                self._glow.set_logo_only(True)
                self._glow.show()
                self._glow.raise_()
                self._glow.set_alpha(glow_alpha)
                self._glow.update()

            if self._logo_t >= 1.0:
                # snap to exact final size and position
                self._set_logo_scale(1.0, self._logo_cx_end)
                self._logo_eff.setOpacity(1.0)
                self._glow.set_logo_only(True)
                self._glow.set_alpha(1.0)
                self._glow.update()
                self._phase = 0.5

        elif self._phase == 0.5:
            # brand slides in
            self._brand_t = min(1.0, self._brand_t + self._BRAND_SPD)
            e = self._ease_out_quint(self._brand_t)
            slide_off = int(22 * (1.0 - e))
            self._brand_lbl.move(self._brand_x_end - slide_off, self._brand_y)
            self._brand_eff.setOpacity(e)
            self._glow.set_logo_only(False)
            self._glow.set_alpha(1.0)
            self._glow.update()

            if self._brand_t >= 1.0:
                self._brand_lbl.move(self._brand_x_end, self._brand_y)
                self._brand_eff.setOpacity(1.0)
                self._phase = 1

        elif self._phase == 1:
            # subtitle rises + shimmer activates when fully visible
            self._sub_t = min(1.0, self._sub_t + self._SUB_SPD)
            e = self._ease_out_quint(self._sub_t)
            y = int(self._sub_y_start + (self._sub_y_end - self._sub_y_start) * e)
            self._sub_lbl.move(0, y)
            opacity = self._ease_in_out_sine(self._sub_t)
            self._sub_eff.setOpacity(opacity)

            if self._sub_t >= 1.0:
                self._sub_lbl.move(0, self._sub_y_end)
                self._sub_eff.setOpacity(1.0)
                # start shimmer on subtitle
                if hasattr(self._sub_lbl, 'start_shimmer'):
                    self._sub_lbl.start_shimmer()
                self._phase = 2
                self._step_timer.start()

        elif self._phase == 2:
            if self._bottom_alpha < 1.0:
                self._bottom_alpha = min(1.0, self._bottom_alpha + self._BOTTOM_SPD)
                self._bottom_eff.setOpacity(self._ease_in_out_sine(self._bottom_alpha))

            diff = self._bar_target - self._bar_value
            if abs(diff) > 0.001:
                self._bar_value += diff * 0.09
                self._bar_w.set_progress(self._bar_value, len(self._TASKS))


    def start(self):
        self.setWindowOpacity(0.0)
        self.show()
        self._launch_update_check()
        self._master_timer.start()

    def _launch_update_check(self):
        sig = self._update_result
        def _worker():
            found, sha = _needs_update()
            sig.emit(found, sha)
        threading.Thread(target=_worker, daemon=True, name="SplashUpdateCheck").start()

    def _on_check_done(self, found: bool, sha: str):
        if found:
            self._task_lbl.setText(f"Update found ({sha}) — launching build...")
            self._bar_target = float(len(self._TASKS))
            QTimer.singleShot(1500, lambda: self._do_update(sha))
        else:
            self._step_timer.start()

    def _step(self):
        self._task_idx += 1
        self._bar_target = float(self._task_idx)
        if self._task_idx < len(self._TASKS):
            self._task_lbl.setText(self._TASKS[self._task_idx])
        if self._task_idx >= len(self._TASKS):
            self._step_timer.stop()
            QTimer.singleShot(800, self._begin_fade_out)

    def _do_update(self, sha: str):
        self._task_lbl.setText("Build pipeline launched — closing app...")
        ok = _launch_bat_update()
        if ok:
            self._quit_for_update()
        else:
            self._task_lbl.setText("build.bat not found — skipping update...")
            self._bar_target = 0.0
            self._bar_value  = 0.0
            self._task_idx   = 1
            QTimer.singleShot(700, lambda: self._step_timer.start())

    def _quit_for_update(self):
        self._step_timer.stop()
        self._master_timer.stop()
        self.close()
        try:
            QApplication.instance().quit()
        except Exception:
            pass
        os._exit(0)

    def _begin_fade_out(self):
        self._step_timer.stop()
        self._bar_w.stop_shimmer()
        self._phase = 3
        self._fade_out_timer = QTimer(self)
        self._fade_out_timer.setInterval(16)
        self._fade_out_timer.timeout.connect(self._tick_fade_out)
        self._fade_out_timer.start()

    def _tick_fade_out(self):
        self._opacity = max(0.0, self._opacity - self._FADE_OUT_SPD)
        self.setWindowOpacity(self._opacity)
        if self._opacity <= 0.0:
            self._fade_out_timer.stop()
            self._master_timer.stop()
            self._step_timer.stop()
            self.close()
            self.finished.emit()


class _ShimmerLabel(QLabel):
    """Subtitle label with a metallic shimmer that travels only over the text glyphs."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent; color: #555555; "
                           "font-size: 12px; font-weight: 700; letter-spacing: 4px;")
        self._shimmer_pos = -0.3
        self._shimmer_on  = False
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def start_shimmer(self):
        self._shimmer_on  = True
        self._shimmer_pos = -0.3
        self._timer.start()

    def _tick(self):
        self._shimmer_pos += 0.007
        if self._shimmer_pos > 1.3:
            self._shimmer_pos = -0.3
        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        # ── 1. Draw text into an ARGB pixmap ─────────────────────────────
        buf = QPixmap(w, h)
        buf.fill(Qt.GlobalColor.transparent)
        bp = QPainter(buf)
        bp.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        bp.setFont(self.font())
        bp.setPen(QColor("#555555"))
        bp.drawText(0, 0, w, h,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    self.text())
        bp.end()

        # ── 2. If shimmer active, stamp the travelling highlight ──────────
        if self._shimmer_on:
            sw = max(50, int(w * 0.32))
            sx = int(self._shimmer_pos * w) - sw // 2

            # Build gradient band into another ARGB pixmap
            shim = QPixmap(w, h)
            shim.fill(Qt.GlobalColor.transparent)
            sp = QPainter(shim)
            g = QLinearGradient(sx, 0, sx + sw, 0)
            g.setColorAt(0.0,  QColor(255, 255, 255, 0))
            g.setColorAt(0.35, QColor(255, 255, 255, 160))
            g.setColorAt(0.5,  QColor(255, 255, 255, 220))
            g.setColorAt(0.65, QColor(255, 255, 255, 160))
            g.setColorAt(1.0,  QColor(255, 255, 255, 0))
            sp.fillRect(0, 0, w, h, g)
            sp.end()

            # Clip shimmer to text glyph pixels only (DestinationIn keeps
            # only the intersection: shimmer alpha × text alpha)
            mp = QPainter(shim)
            mp.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_DestinationIn)
            mp.drawPixmap(0, 0, buf)
            mp.end()

            # Stamp clipped shimmer onto the text buffer
            fp = QPainter(buf)
            fp.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver)
            fp.drawPixmap(0, 0, shim)
            fp.end()

        # ── 3. Blit final buffer to screen ────────────────────────────────
        p = QPainter(self)
        p.drawPixmap(0, 0, buf)
        p.end()


class _SplashGlowWidget(QWidget):

    def __init__(self, parent, sz, gap, ly):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._alpha      = 0.0
        self._logo_only  = True
        self._logo_cx    = 0.0
        self._ly         = float(ly)
        self._lsz        = float(sz)
        self._bx = self._by = self._bw = self._bh = 0.0

    def set_positions(self, logo_cx, logo_y, logo_sz,
                      brand_x, brand_y, brand_w, brand_h):
        self._logo_cx = float(logo_cx)
        self._ly      = float(logo_y)
        self._lsz     = float(logo_sz)
        self._bx      = float(brand_x)
        self._by      = float(brand_y)
        self._bw      = float(brand_w)
        self._bh      = float(brand_h)

    def set_logo_only(self, v: bool):
        self._logo_only = v

    def set_alpha(self, a: float):
        self._alpha = max(0.0, min(1.0, a))

    def paintEvent(self, event):
        if self._alpha <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        a = self._alpha

        # logo glow — true QRadialGradient, no visible circles
        cx   = self._logo_cx
        cy   = self._ly + self._lsz / 2.0
        gr   = self._lsz * 1.05
        rg   = QRadialGradient(cx, cy, gr)
        rg.setColorAt(0.0,  QColor(255, 255, 255, int(36 * a)))
        rg.setColorAt(0.35, QColor(255, 255, 255, int(20 * a)))
        rg.setColorAt(0.65, QColor(255, 255, 255, int(8  * a)))
        rg.setColorAt(1.0,  QColor(255, 255, 255, 0))
        p.setBrush(rg)
        p.drawEllipse(int(cx - gr), int(cy - gr), int(gr * 2), int(gr * 2))

        if not self._logo_only:
            bx, by, bw, bh = self._bx, self._by, self._bw, self._bh
            pad = 26.0
            hg = QLinearGradient(bx - pad, 0, bx + bw + pad, 0)
            hg.setColorAt(0.0,  QColor(0, 0, 0, 0))
            hg.setColorAt(0.12, QColor(255, 255, 255, int(14 * a)))
            hg.setColorAt(0.5,  QColor(255, 255, 255, int(22 * a)))
            hg.setColorAt(0.88, QColor(255, 255, 255, int(14 * a)))
            hg.setColorAt(1.0,  QColor(0, 0, 0, 0))
            p.setBrush(hg)
            p.drawRoundedRect(
                int(bx - pad), int(by - 10),
                int(bw + pad * 2), int(bh + 20), 8, 8)

        p.end()


# AUTO-UPDATER

def _get_exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(os.path.dirname(sys.executable))
    return Path(os.path.dirname(os.path.abspath(__file__)))

def _get_built_sha() -> str:
    sha = getattr(AutoUpdater, "_BUILT_SHA", "")
    if sha:
        return sha
    try:
        return (_get_exe_dir() / "version.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return ""

def _fetch_remote_sha() -> str:
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
        req = urllib.request.Request(url, headers={"User-Agent": "SniperApp/Updater"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read()).get("sha", "")[:7]
    except Exception:
        return ""

def _needs_update() -> tuple:
    if not GITHUB_REPO or not getattr(sys, "frozen", False):
        return False, ""
    remote_sha = _fetch_remote_sha()
    if not remote_sha:
        return False, ""
    built_sha = _get_built_sha()
    if built_sha and remote_sha == built_sha:
        return False, ""
    return True, remote_sha

def _ensure_build_script() -> Optional[Path]:
    exe_dir = _get_exe_dir()
    _system = platform.system()
    if _system == "Windows":
        script = exe_dir / "build.bat"
        remote_name = "build.bat"
    else:
        script = exe_dir / "build.sh"
        remote_name = "build.sh"

    if script.exists():
        return script
    if not GITHUB_REPO:
        return None
    try:
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{remote_name}"
        req = urllib.request.Request(url, headers={"User-Agent": "SniperApp/Updater"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        if _system == "Windows":
            text = raw.decode("utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")
            script.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        else:
            script.write_bytes(raw)
            script.chmod(script.stat().st_mode | 0o111)
        return script
    except Exception as exc:
        print(f"[Updater] Could not fetch {remote_name}: {exc}")
        return None

_ensure_bat = _ensure_build_script


def _launch_bat_update() -> bool:
    global _UPDATE_TRIGGERED
    if _UPDATE_TRIGGERED:
        return False
    _UPDATE_TRIGGERED = True

    script = _ensure_build_script()
    if not script:
        print("[Updater] Build script not available.")
        return False

    if getattr(sys, "frozen", False):
        target = str(sys.executable)
    else:
        ext    = ".exe" if platform.system() == "Windows" else ""
        target = str(_get_exe_dir() / f"{EXE_NAME}{ext}")

    _system = platform.system()

    try:
        if _system == "Windows":
            wrapper_content = (
                "@echo off\r\n"
                "title Slaoq's Sniper \u2014 Auto Update\r\n"
                "color 0F\r\n"
                f"call \"{script}\" --update \"{target}\"\r\n"
                "echo.\r\n"
                "echo  Done. This window will stay open.\r\n"
                "pause >nul\r\n"
            )
            wrapper = _get_exe_dir() / "_update_launcher.bat"
            wrapper.write_bytes(wrapper_content.encode("utf-8"))
            si = subprocess.STARTUPINFO()
            si.dwFlags     = subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 1
            subprocess.Popen(
                ["cmd.exe", "/c", str(wrapper)],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=str(_get_exe_dir()),
                startupinfo=si,
            )

        elif _system == "Darwin":
            apple_script = (
                f'tell application "Terminal" to do script '
                f'"bash \\"{script}\\" --update \\"{target}\\""'
            )
            subprocess.Popen(["osascript", "-e", apple_script])

        else:
            # Linux: try common terminal emulators in priority order
            terminals = [
                ["x-terminal-emulator", "-e"],
                ["gnome-terminal", "--"],
                ["xterm", "-e"],
                ["konsole", "-e"],
                ["xfce4-terminal", "-e"],
            ]
            cmd_str = f'bash "{script}" --update "{target}"; echo "Done — press Enter"; read'
            launched = False
            for term_parts in terminals:
                try:
                    subprocess.Popen(term_parts + ["bash", "-c", cmd_str],
                                     cwd=str(_get_exe_dir()))
                    launched = True
                    break
                except FileNotFoundError:
                    continue
            if not launched:
                # Headless fallback: run directly without a terminal window
                subprocess.Popen(["bash", str(script), "--update", target],
                                  cwd=str(_get_exe_dir()))

        return True
    except Exception as exc:
        print(f"[Updater] Failed to launch update: {exc}")
        return False


class AutoUpdater(QObject):
    update_available = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def check_async(self):
        if not GITHUB_REPO or not getattr(sys, "frozen", False):
            return
        threading.Thread(target=self._check, daemon=True, name="AutoUpdate").start()

    def _check(self):
        found, sha = _needs_update()
        if found:
            self.update_available.emit(sha)

    def rebuild_and_restart(self):
        if _launch_bat_update():
            try:
                QApplication.instance().quit()
            except Exception:
                pass
            sys.exit(0)

# TITLE BAR

class TitleBar(QFrame):
    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self.setObjectName("TitleBar")
        self.setFixedHeight(TITLEBAR_H)
        self._win = win
        self._drag: Optional[QPoint] = None
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 0, 0); lay.setSpacing(6)

        col = QVBoxLayout(); col.setSpacing(1)
        col.addWidget(lbl(APP_NAME,        "AppTitle"))
        col.addWidget(lbl(f"v{APP_VERSION}", "AppVersion"))
        lay.addLayout(col); lay.addStretch()

        self.badge = StatusBadge("idle")
        lay.addWidget(self.badge); lay.addSpacing(12)

        self._btn_min   = self._mkbtn("minimize")
        self._btn_max   = self._mkbtn("maximize")
        self._btn_close = self._mkbtn("close")
        self._btn_min.clicked.connect(self._win.showMinimized)
        self._btn_max.clicked.connect(self._toggle_max)
        self._btn_close.clicked.connect(self._win.close)
        for b in (self._btn_min, self._btn_max, self._btn_close):
            lay.addWidget(b)

    def _mkbtn(self, icon_key: str) -> QPushButton:
        b = QPushButton()
        b.setObjectName("WinBtn")
        b.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setIcon(_svg_icon(icon_key, "#999999", 14))
        b.setIconSize(QSize(14, 14))
        return b

    def _update_max_icon(self):
        key = "restore" if self._win.isMaximized() else "maximize"
        self._btn_max.setIcon(_svg_icon(key, "#999999", 14))

    def _toggle_max(self):
        if self._win.isMaximized(): self._win.showNormal()
        else:                       self._win.showMaximized()
        self._update_max_icon()

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._drag and e.buttons() == Qt.MouseButton.LeftButton:
            if self._win.isMaximized(): self._win.showNormal()
            self._win.move(self._win.pos() + (e.globalPosition().toPoint() - self._drag))
            self._drag = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):  self._drag = None
    def mouseDoubleClickEvent(self, e): self._toggle_max()

# SIDEBAR 

_PAGES = [
    ("home",     "Home"),
    ("settings", "Settings"),
    ("bell",     "Notifications"),
    ("lock",     "Blacklist"),
    ("logs",     "Logs"),
    ("clock",    "History"),
    ("zap",      "Plugins"),
]


class Sidebar(QFrame):
    page_changed = Signal(int)

    # Bar animation phases
    _BAR_IDLE      = 0   # bar fully visible at active pos
    _BAR_SHRINK    = 1   # bar shrinking from both ends toward center
    _BAR_GROW      = 2   # bar growing from center outward at new pos

    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIDEBAR_LG)
        self.setMouseTracking(True)

        self._active_idx: int   = 0
        self._collapsed:  bool  = False

        # ── Hover background — fade out old pos, fade in new pos ───────────
        self._hover_y:       float = -1.0   # current drawn y
        self._hover_next_y:  float = -1.0   # pending y after fade-out
        self._hover_h:       int   = 32
        self._hover_alpha:   float = 0.0
        # phase: 0=idle, 1=fading-out (toward 0), 2=fading-in (toward 1)
        self._hover_phase:   int   = 0

        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(8)
        self._hover_timer.timeout.connect(self._tick_hover_bg)

        # ── White bar (active indicator) with shrink/grow animation ────────
        self._bar_phase:    int   = self._BAR_IDLE
        self._bar_y:        float = -1.0   # current top-y of active btn
        self._bar_target_y: float = -1.0   # next target after transition
        self._bar_h:        int   = 32     # button height
        # bar_scale: 1.0 = full, 0.0 = gone (shrunk to center)
        self._bar_scale:    float = 1.0
        self._bar_alpha:    float = 1.0    # opacity
        self._bar_vel:      float = 0.0    # spring velocity for overshoot

        self._bar_timer = QTimer(self)
        self._bar_timer.setInterval(8)
        self._bar_timer.timeout.connect(self._tick_bar)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 14, 8, 14) 
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._logo = _GlowLogoLabel()
        self._logo.setObjectName("SidebarLogo")
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo.setFixedSize(64, 64) 

        lc = QVBoxLayout()
        lc.setContentsMargins(0, 0, 0, 0)
        lc.setSpacing(4)
        lc.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lc.addWidget(self._logo, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._ln = lbl("SLAOQ'S", "SidebarName")
        self._ln.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ls = lbl("Sol's RNG SNIPER", "SidebarSub")
        self._ls.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ln.setVisible(True)
        self._ls.setVisible(True) 
        lc.addWidget(self._ln)
        lc.addWidget(self._ls)
        
        lay.addLayout(lc)
        lay.addSpacing(12)
        lay.addWidget(hdiv())
        lay.addSpacing(12)

        self._btns: list[NavButton] = []
        for i, (k, t) in enumerate(_PAGES):
            b = NavButton(k, t)
            b.clicked.connect(lambda _, ix=i: self._sel(ix))
            b.installEventFilter(self)
            self._btns.append(b)
            lay.addWidget(b, alignment=Qt.AlignmentFlag.AlignHCenter)
            lay.addSpacing(5)

        lay.addStretch()

        self._toggle_btn = QPushButton()
        self._toggle_btn.setObjectName("GhostBtn")
        self._toggle_btn.setIcon(_svg_icon("chevron-left", C["dim"], 14))
        self._toggle_btn.setIconSize(QSize(14, 14))
        self._toggle_btn.setFixedSize(32, 32)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_collapse)
        lay.addWidget(self._toggle_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self._load_logo()

        self._width_anim = QPropertyAnimation(self, b"minimumWidth")
        self._width_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._width_anim.setDuration(220)
        self._width_anim.finished.connect(self._on_anim_finished)

        self._btns[0].set_active(True)
        self._btns[0]._active_t = 1.0
        self._btns[0]._apply_sizes()
        self._active_idx = 0

    def set_plugins_visible(self, visible: bool):
        if len(self._btns) > 6:
            self._btns[6].setVisible(visible)

    def _on_anim_finished(self):
        self._snap_bar_to(self._active_idx)
        self._snap_hover_to(self._active_idx)

    def showEvent(self, event):
        super().showEvent(event)
        self._snap_bar_to(self._active_idx)
        self._snap_hover_to(self._active_idx)

    def _btn_y(self, idx: int) -> float:
        return float(self._btns[idx].mapTo(self, QPoint(0, 0)).y())

    def _snap_bar_to(self, idx: int):
        if idx < 0 or idx >= len(self._btns):
            return
        self._bar_y        = self._btn_y(idx)
        self._bar_target_y = self._bar_y
        self._bar_h        = self._btns[idx].height()
        self._bar_scale    = 1.0
        self._bar_alpha    = 1.0
        self._bar_phase    = self._BAR_IDLE
        self.update()

    def _snap_hover_to(self, idx: int):
        if idx < 0 or idx >= len(self._btns):
            return
        y = self._btn_y(idx)
        h = self._btns[idx].height()
        self._hover_y     = y
        self._hover_next_y = y
        self._hover_h     = h
        self._hover_alpha = 1.0
        self._hover_phase = 0
        self.update()

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        target_w = SIDEBAR_SM if self._collapsed else SIDEBAR_LG
        
        self._width_anim.setStartValue(self.width())
        self._width_anim.setEndValue(target_w)
        self._width_anim.start()

        anim2 = QPropertyAnimation(self, b"maximumWidth", self)
        anim2.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim2.setDuration(220)
        anim2.setStartValue(self.width())
        anim2.setEndValue(target_w)
        anim2.start()

        icon_key = "chevron-right" if self._collapsed else "chevron-left"
        self._toggle_btn.setIcon(_svg_icon(icon_key, C["dim"], 14))

        wide = not self._collapsed
        self._ln.setVisible(wide)
        self._ls.setVisible(wide)
        
        for b in self._btns:
            b.show_text(wide)
        
        self._adapt_logo(target_w)

    def eventFilter(self, obj, event):
        if obj in self._btns:
            idx = self._btns.index(obj)
            if event.type() == QEvent.Type.HoverEnter:
                QApplication.restoreOverrideCursor()
                QApplication.setOverrideCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                # Animate hover brightness on non-active buttons
                if idx != self._active_idx:
                    self._btns[idx].set_hovered(True)
                # Hover background stays at active — no position change
            elif event.type() == QEvent.Type.HoverLeave:
                QApplication.restoreOverrideCursor()
                if idx != self._active_idx:
                    self._btns[idx].set_hovered(False)
        return False

    # ── Hover background tick — fade out old, fade in new ─────────────────
    def _tick_hover_bg(self):
        SPEED = 0.13

        if self._hover_phase == 1:   # fading OUT
            self._hover_alpha -= SPEED
            if self._hover_alpha <= 0.0:
                self._hover_alpha = 0.0
                # move to new position and start fading in
                self._hover_y     = self._hover_next_y
                self._hover_phase = 2

        elif self._hover_phase == 2:   # fading IN
            self._hover_alpha += SPEED
            if self._hover_alpha >= 1.0:
                self._hover_alpha = 1.0
                self._hover_phase = 0
                self._hover_timer.stop()

        self.update()

    # ── White bar tick — spring physics ───────────────────────────────────
    def _tick_bar(self):
        if self._bar_phase == self._BAR_SHRINK:
            # Ease-in shrink toward 0
            diff = self._bar_scale
            step = max(0.008, diff * 0.10)
            self._bar_scale -= step
            self._bar_scale  = max(0.0, self._bar_scale)
            self._bar_alpha  = max(0.0, self._bar_scale ** 0.7)
            if self._bar_scale <= 0.01:
                self._bar_scale   = 0.0
                self._bar_alpha   = 0.0
                self._bar_y       = self._bar_target_y
                self._bar_phase   = self._BAR_GROW
                # init spring velocity for overshoot
                self._bar_vel     = 0.0

        elif self._bar_phase == self._BAR_GROW:
            # Spring: stiffness k, damping d — gives natural overshoot
            k  = 0.18   # how strongly it pulls toward 1.0
            d  = 0.62   # damping < 1.0 = underdamped (bouncy)
            displacement   = self._bar_scale - 1.0
            spring_force   = -k * displacement
            damping_force  = -d * self._bar_vel
            self._bar_vel += spring_force + damping_force
            self._bar_scale += self._bar_vel
            # alpha follows scale but clamped to visible range
            self._bar_alpha = min(1.0, max(0.0, self._bar_scale ** 0.6))
            # Settle check: close enough and low velocity
            if abs(self._bar_scale - 1.0) < 0.005 and abs(self._bar_vel) < 0.003:
                self._bar_scale = 1.0
                self._bar_alpha = 1.0
                self._bar_vel   = 0.0
                self._bar_phase = self._BAR_IDLE
                self._bar_timer.stop()

        self.update()

    def _start_bar_transition(self, new_idx: int):
        if new_idx < 0 or new_idx >= len(self._btns):
            return
        new_y = self._btn_y(new_idx)
        self._bar_h        = self._btns[new_idx].height()
        self._bar_target_y = new_y

        if self._bar_y < 0:
            # First paint — snap
            self._bar_y    = new_y
            self._bar_scale = 1.0
            self._bar_alpha = 1.0
            self._bar_phase = self._BAR_IDLE
            self.update()
            return

        if self._bar_phase == self._BAR_IDLE:
            self._bar_phase = self._BAR_SHRINK
            self._bar_timer.start()
        elif self._bar_phase == self._BAR_GROW:
            # Mid-grow: restart shrink from current state
            self._bar_phase = self._BAR_SHRINK

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Hover background — fades out old position, fades in new position
        if self._hover_y >= 0 and self._hover_alpha > 0.01:
            c = QColor("#0e0e0e")
            c.setAlphaF(self._hover_alpha)
            p.setBrush(c)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(4, int(self._hover_y),
                              self.width() - 8, self._hover_h, 6, 6)

        # White active bar (shrink/grow from center, rounded) + subtle glow
        if self._bar_y >= 0 and self._bar_alpha > 0.01:
            btn_h  = self._bar_h
            by     = int(self._bar_y)
            bar_h_full = max(16, int(btn_h * 0.55))
            bar_y_center = by + (btn_h - bar_h_full) // 2
            bar_radius = 2

            draw_scale = min(1.4, max(0.0, self._bar_scale))
            scaled_h = max(2, int(bar_h_full * draw_scale))
            offset   = (bar_h_full - scaled_h) // 2
            final_y  = bar_y_center + offset

            a = self._bar_alpha

            # single soft glow layer — wide, very faint
            glow_c = QColor(255, 255, 255, int(28 * a))
            p.setBrush(glow_c)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(-4, final_y - 3, 11, scaled_h + 6, 5, 5)

            # bar itself
            color = QColor(C["white"])
            color.setAlphaF(a)
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(2, final_y, 3, scaled_h, bar_radius, bar_radius)

        p.end()

    def _sel(self, idx: int):
        old_idx = self._active_idx
        # No animation if already on this page
        if idx == old_idx:
            return

        self._active_idx = idx
        for i, b in enumerate(self._btns):
            b.set_active(i == idx)
            if i != idx:
                b.set_hovered(False)

        # Hover background: fade out from old pos, fade in at new pos
        if idx < len(self._btns):
            new_y = self._btn_y(idx)
            self._hover_next_y = new_y
            self._hover_h      = self._btns[idx].height()
            if self._hover_y < 0:
                # First selection — snap directly
                self._hover_y     = new_y
                self._hover_alpha = 1.0
                self._hover_phase = 0
            else:
                # Trigger fade-out → move → fade-in
                self._hover_phase = 1
                self._hover_timer.start()
            self.update()

        # Trigger shrink→grow bar animation
        self._start_bar_transition(idx)
        self.page_changed.emit(idx)

    def adapt(self, w: int):
        target = max(SIDEBAR_MIN, min(SIDEBAR_MAX, int(w * SIDEBAR_RATIO)))
        
        if not self._collapsed:
            if self._width_anim.state() != QAbstractAnimation.State.Running:
                self.setFixedWidth(target)
                self._adapt_logo(target)
        else:
            self._adapt_logo(SIDEBAR_SM)

        wide = not self._collapsed
        
        f_size = max(1, min(20, int(self.width() / 10)))
        if wide:
            self._ln.setStyleSheet(
                f"font-size: {f_size}px; color: {C['white']}; font-weight: 800; letter-spacing: 2px;")
            self._ls.setStyleSheet(
                f"font-size: {max(1, f_size - 3)}px; color: {C['muted']}; letter-spacing: 2px;")

        icon_size = max(18, int(self.width() * 0.22))
        font_size = max(1, int(self.width() * 0.07))
        for b in self._btns:
            b.set_style(font_size, icon_size)
            b.show_text(wide)

        self._ln.setVisible(wide)
        self._ls.setVisible(wide)

    def _load_logo(self):
        if LOGO_PATH.exists():
            raw = QPixmap(str(LOGO_PATH))
            if not raw.isNull():
                self._base_pixmap = raw
                # Carrega no tamanho inicial correto
                self._adapt_logo(self.width())
                return
                
        # Fallback
        px = QPixmap(64, 64)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(C["white"])); pen.setWidth(2); p.setPen(pen)
        cx = cy = 32; r = 20
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        p.drawEllipse(cx - 6, cy - 6, 12, 12)
        p.end()
        self._base_pixmap = px
        self._adapt_logo(self.width())

    def _adapt_logo(self, width):
        if not hasattr(self, '_base_pixmap') or self._base_pixmap.isNull():
            return
        max_w = max(24, min(width - 16, 64))
        scaled = self._base_pixmap.scaled(
            max_w, max_w, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self._logo.setFixedSize(scaled.width(), scaled.height())
        self._logo.setPixmap(scaled)

# PAGE: DASHBOARD

class DashboardPage(QWidget):
    start_requested       = Signal()
    stop_requested        = Signal()
    pause_requested       = Signal()
    hotkey_config_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self._build()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(26, 22, 26, 22); lay.setSpacing(14)
        self._lay = lay  

        # Header
        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(3)
        col.addWidget(lbl("Dashboard", "PageTitle"))
        col.addWidget(lbl("Control & Monitor", "PageSub"))
        hdr.addLayout(col); hdr.addStretch()
        self.badge = StatusBadge("idle"); hdr.addWidget(self.badge)
        lay.addLayout(hdr); lay.addWidget(hdiv())

        # Compact 2×3 metrics grid
        #   Row 1: [Snipes]  [Ping]    [Status]
        #   Row 2: [Roblox]  [Uptime]  [Messages]
        grid = QGridLayout(); grid.setSpacing(8)

        self.c_snipes   = MetricCard("Snipes",       "0")
        self.c_ping     = MetricCard("Ping",          "—",  "ms")
        self.c_status   = MetricCard("Status",        "IDLE")
        self.c_roblox   = MetricCard("Roblox",        "—")
        self.c_uptime   = MetricCard("Uptime",        "—",  "s")
        self.c_messages = MetricCard("Messages",      "0")

        grid.addWidget(self.c_snipes,   0, 0)
        grid.addWidget(self.c_ping,     0, 1)
        grid.addWidget(self.c_status,   0, 2)
        grid.addWidget(self.c_roblox,   1, 0)
        grid.addWidget(self.c_uptime,   1, 1)
        grid.addWidget(self.c_messages, 1, 2)

        for col_idx in range(3):
            grid.setColumnStretch(col_idx, 1)

        lay.addLayout(grid)

        br = QHBoxLayout(); br.setSpacing(10)
        self._s = QPushButton("  Start Sniper")
        self._s.setIcon(_svg_icon("play", "#000000", 16))
        self._s.setObjectName("PrimaryBtn")
        self._s.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._s.setFixedHeight(42); self._s.clicked.connect(self.start_requested.emit)

        self._e = QPushButton("  Stop Sniper")
        self._e.setIcon(_svg_icon("stop", C["red2"], 16))
        self._e.setObjectName("DangerBtn")
        self._e.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._e.setFixedHeight(42); self._e.setEnabled(False)
        self._e.clicked.connect(self.stop_requested.emit)

        self._p = QPushButton("  Pause Sniper")
        self._p.setIcon(_svg_icon("pause", "#ffcc00", 16))
        self._p.setObjectName("PauseBtn")
        self._p.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._p.setFixedHeight(42); self._p.setEnabled(False)
        self._p.clicked.connect(self.pause_requested.emit)

        for btn in (self._s, self._e, self._p):
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        br.addWidget(self._s); br.addWidget(self._e); br.addWidget(self._p)
        br.addStretch()
        lay.addLayout(br)

        lay.addWidget(lbl("RECENT ACTIVITY", "SecTitle"))
        self.mini = QTextEdit(); self.mini.setObjectName("LogConsole")
        self.mini.setReadOnly(True)
        self.mini.setPlaceholderText("Waiting for connection…")
        lay.addWidget(self.mini, 1)

        hk_card = QFrame(); hk_card.setObjectName("SettCard")
        hk_lay  = QVBoxLayout(hk_card); hk_lay.setContentsMargins(12, 12, 12, 12); hk_lay.setSpacing(8)

        hk_hdr = QHBoxLayout()
        hk_hdr.addWidget(lbl("HOTKEY CONFIGURATION", "GrpLabel"))
        hk_hdr.addWidget(HelpIcon(
            "Set keys to control the sniper globally.\n"
            "Toggle: turn on/off.\nPause: temporary stop."))
        hk_hdr.addStretch()
        hk_lay.addLayout(hk_hdr)

        tg_row = QHBoxLayout()
        self._tg_key = KeySequenceEdit(); self._tg_key.setPlaceholderText("Toggle Key")
        self._tg_key.setMaximumWidth(120)
        self._tg_chk = QCheckBox(); self._tg_chk.setChecked(True)
        tg_row.addWidget(lbl("Toggle Sniper:", "FieldLbl"))
        tg_row.addWidget(self._tg_key); tg_row.addWidget(self._tg_chk); tg_row.addStretch()
        hk_lay.addLayout(tg_row)

        ps_row = QHBoxLayout()
        self._ps_key = KeySequenceEdit(); self._ps_key.setPlaceholderText("Pause Key")
        self._ps_key.setMaximumWidth(120)
        self._ps_chk = QCheckBox(); self._ps_chk.setChecked(True)
        self._ps_dur = QSpinBox(); self._ps_dur.setRange(1, 600)
        self._ps_dur.setValue(60); self._ps_dur.setSuffix("s")
        ps_row.addWidget(lbl("Pause Sniper:", "FieldLbl"))
        ps_row.addWidget(self._ps_key); ps_row.addWidget(QLabel("For:"))
        ps_row.addWidget(self._ps_dur); ps_row.addWidget(self._ps_chk); ps_row.addStretch()
        hk_lay.addLayout(ps_row)
        lay.addWidget(hk_card)

        self._notif_frame = QFrame(self)
        self._notif_frame.setObjectName("NotifFrame")
        self._notif_frame.setFixedHeight(46)
        self._notif_frame.setFixedWidth(360)
        self._notif_frame.setVisible(False)
        # position is set dynamically in show_notification / resizeEvent

        self._notif_timer = QTimer(self)
        self._notif_timer.setSingleShot(True); self._notif_timer.setInterval(4000)
        self._notif_timer.timeout.connect(self._hide_notification)

        notif_lay = QHBoxLayout(self._notif_frame)
        notif_lay.setContentsMargins(14, 0, 10, 0); notif_lay.setSpacing(8)

        self._notif_icon_lbl = QLabel("●")
        self._notif_icon_lbl.setFixedWidth(10)
        notif_lay.addWidget(self._notif_icon_lbl)

        self._notif_lbl = lbl("")
        self._notif_lbl.setWordWrap(True)
        notif_lay.addWidget(self._notif_lbl, 1)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self._hide_notification)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {C['muted']}; border: none; font-size: 16px; }}"
            f"QPushButton:hover {{ color: {C['white']}; }}")
        notif_lay.addWidget(close_btn)

        # slide animation
        self._notif_slide = QPropertyAnimation(self._notif_frame, b"pos")
        self._notif_slide.setDuration(280)
        self._notif_slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._notif_fade_eff = QGraphicsOpacityEffect(self._notif_frame)
        self._notif_frame.setGraphicsEffect(self._notif_fade_eff)
        self._notif_fade_eff.setOpacity(0.0)
        self._notif_fade_anim = QPropertyAnimation(self._notif_fade_eff, b"opacity")
        self._notif_fade_anim.setDuration(280)

        QTimer.singleShot(0, self._adapt_to_size)

        self._tg_key.keySequenceChanged.connect(self._emit_config)
        self._tg_chk.toggled.connect(self._emit_config)
        self._ps_key.keySequenceChanged.connect(self._emit_config)
        self._ps_chk.toggled.connect(self._emit_config)
        self._ps_dur.valueChanged.connect(self._emit_config)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adapt_to_size()

    def _adapt_to_size(self):
        w, h = self.width(), self.height()

        pad_h = max(12, min(26, int(w * 0.027)))
        pad_v = max(12, min(22, int(h * 0.028)))
        self._lay.setContentsMargins(pad_h, pad_v, pad_h, pad_v)
        self._lay.setSpacing(max(8, min(14, int(h * 0.018))))

        card_h  = max(64, min(90, int(h * 0.115)))
        hover_h = card_h + 6
        for card in (self.c_snipes, self.c_ping, self.c_status,
                     self.c_roblox, self.c_uptime, self.c_messages):
            card._BASE_H  = card_h
            card._HOVER_H = hover_h
            card.set_card_height(card_h)

        btn_h = max(34, min(42, int(h * 0.065)))
        for btn in (self._s, self._e, self._p):
            btn.setFixedHeight(btn_h)

    def update_engine_metrics(self, metrics: dict):
        """Called by the timer tick to sync engine metrics into the grid cards."""
        msgs = metrics.get("messages_scanned", 0)
        self.c_messages.set_value(str(msgs))

    def update_roblox_status(self, running: bool):
        """Update the Roblox card — called from the tick timer."""
        self.c_roblox.set_value("RUNNING" if running else "CLOSED")

    def _notif_pos_shown(self):
        """Bottom-right corner of this widget, with margin."""
        margin = 16
        w = self._notif_frame.width()
        h = self._notif_frame.height()
        return QPoint(self.width() - w - margin, self.height() - h - margin)

    def _notif_pos_hidden(self):
        p = self._notif_pos_shown()
        return QPoint(p.x() + 40, p.y())  # slide in from right

    def show_notification(self, text: str, level: str = "error"):
        self._notif_lbl.setText(text)
        if level == "error":
            color  = "#ff8a80"
            icon_c = "#ff5252"
            bg     = C["notif_red_bg"]
            border = C["notif_red_border"]
        else:
            color  = "#ffd480"
            icon_c = "#ffcc00"
            bg     = C["notif_yellow_bg"]
            border = C["notif_yellow_border"]
        self._notif_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px;")
        self._notif_icon_lbl.setStyleSheet(f"color: {icon_c}; font-size: 7px;")
        self._notif_frame.setStyleSheet(
            f"#NotifFrame {{ background-color: {bg}; border: 1px solid {border};"
            f" border-radius: 10px; }}")

        self._notif_slide.stop()
        self._notif_fade_anim.stop()

        # place off-screen to the right, then slide in
        self._notif_frame.move(self._notif_pos_hidden())
        self._notif_frame.setVisible(True)
        self._notif_frame.raise_()

        self._notif_slide.setStartValue(self._notif_pos_hidden())
        self._notif_slide.setEndValue(self._notif_pos_shown())
        self._notif_slide.start()

        self._notif_fade_anim.setStartValue(0.0)
        self._notif_fade_anim.setEndValue(1.0)
        self._notif_fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._notif_fade_anim.start()

        self._notif_timer.start()

    def _hide_notification(self):
        self._notif_timer.stop()
        self._notif_slide.stop()
        self._notif_fade_anim.stop()

        self._notif_slide.setStartValue(self._notif_frame.pos())
        self._notif_slide.setEndValue(self._notif_pos_hidden())
        self._notif_slide.start()

        self._notif_fade_anim.setStartValue(1.0)
        self._notif_fade_anim.setEndValue(0.0)
        self._notif_fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._notif_fade_anim.finished.connect(lambda: self._notif_frame.setVisible(False))
        self._notif_fade_anim.start()

    def set_ping(self, ms: float):
        """Update ping card with color-coded value (green/yellow/red)."""
        text = f"{ms:.0f}"
        if ms <= 80:
            color = "#00cc66"   # green — good
        elif ms <= 200:
            color = "#ffcc00"   # yellow — ok
        else:
            color = "#ff5252"   # red — bad
        self.c_ping._v.setStyleSheet(f"color: {color}; font-weight: 800;")
        self.c_ping._raw_value = text
        try:
            cur = float(self.c_ping._v.text().replace("—", "0"))
            if cur != ms:
                self.c_ping._counter_from = cur
                self.c_ping._counter_to   = ms
                self.c_ping._counter_t    = 0.0
                self.c_ping._counter_timer.start()
                return
        except ValueError:
            pass
        self.c_ping._v.setText(text)

    def _emit_config(self):
        self.hotkey_config_changed.emit({
            "toggle_key": self._tg_key.text(),
            "toggle_en":  self._tg_chk.isChecked(),
            "pause_key":  self._ps_key.text(),
            "pause_en":   self._ps_chk.isChecked(),
            "pause_dur":  self._ps_dur.value(),
        })

    def on_start(self):
        self._s.setEnabled(False)
        self._e.setEnabled(True)
        self._p.setEnabled(True)

    def on_stop(self):
        self._s.setEnabled(True)
        self._e.setEnabled(False)
        self._p.setEnabled(False)
        self._p.setText("  Pause Sniper")
        self._p.setIcon(_svg_icon("pause", "#ffcc00", 16))
        self.c_ping.set_value("—")
        self.c_ping._v.setStyleSheet("")
        self.c_uptime.set_value("—")

    def on_pause(self):
        self._p.setText("  Resume Sniper")
        self._p.setIcon(_svg_icon("play", "#ffcc00", 16))

    def on_resume(self):
        self._p.setText("  Pause Sniper")
        self._p.setIcon(_svg_icon("pause", "#ffcc00", 16))

    def append(self, e: LogEntry, dev: bool = False):
        if e.dev_only and not dev:
            return
        clr, tag, bg_rgba = {
            LogLevel.SUCCESS: (C["green2"], "OK",  "rgba(0,204,102,0.10)"),
            LogLevel.ERROR:   (C["red2"],   "ERR", "rgba(231,76,60,0.10)"),
            LogLevel.WARN:    (C["yellow"], "WRN", "rgba(255,204,0,0.08)"),
            LogLevel.DEBUG:   (C["purple"], "DBG", "rgba(170,102,255,0.07)"),
            LogLevel.SNIPE:   (C["orange"], "SNP", "rgba(255,136,0,0.10)"),
        }.get(e.level, (C["green"], "INF", "rgba(0,255,136,0.07)"))
        pill = (f'<span style="background:{bg_rgba};color:{clr};'
                f'font-weight:800;font-size:9px;letter-spacing:1px;'
                f'border-radius:3px;padding:1px 5px;">{tag}</span>')
        html = (f'<span style="color:{C["dim"]};font-size:10px">{e.ts}</span> '
                f'{pill} '
                f'<span style="color:{clr}">{e.message}</span>')
        self.mini.append(html)
        doc = self.mini.document()
        if doc.blockCount() > 2000:
            cursor = self.mini.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(cursor.MoveOperation.Down,
                                cursor.MoveMode.KeepAnchor, doc.blockCount() - 2000)
            cursor.removeSelectedText()
        b = self.mini.verticalScrollBar(); b.setValue(b.maximum())

    def set_hotkey_state(self, cfg: dict):
        for w in (self._tg_key, self._tg_chk, self._ps_key, self._ps_chk, self._ps_dur):
            w.blockSignals(True)
        self._tg_key.setText(cfg.get("toggle_key", ""))
        self._tg_chk.setChecked(cfg.get("toggle_en", True))
        self._ps_key.setText(cfg.get("pause_key",   ""))
        self._ps_chk.setChecked(cfg.get("pause_en",  True))
        self._ps_dur.setValue(cfg.get("pause_dur",  60))
        for w in (self._tg_key, self._tg_chk, self._ps_key, self._ps_chk, self._ps_dur):
            w.blockSignals(False)

# PROFILE EDITOR 

class ProfileEditor(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._profile: Optional[SnipeProfile] = None
        self._build()

    def _build(self):
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(20, 16, 20, 16); self._outer.setSpacing(14)

        self._placeholder = QWidget()
        pl = QVBoxLayout(self._placeholder); pl.addStretch()
        hint = lbl("← Select a profile to edit", "FieldHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(hint); pl.addStretch()
        self._outer.addWidget(self._placeholder)

        self._form = QWidget(); self._form.setVisible(False)
        fl = QVBoxLayout(self._form); fl.setContentsMargins(0, 0, 0, 0); fl.setSpacing(12)

        hdr = QHBoxLayout(); hdr.setSpacing(10)
        self._lbl_name = lbl("", "ProfileName")

        locked_row = QHBoxLayout(); locked_row.setSpacing(5)
        lock_ic = QLabel()
        lock_ic.setPixmap(_svg_icon("lock", C["muted"], 12).pixmap(12, 12))
        lock_ic.setStyleSheet("background: transparent;")
        self._lbl_locked_wrap = QWidget()
        ll = QHBoxLayout(self._lbl_locked_wrap); ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(lock_ic); ll.addWidget(lbl("Built-in — cannot be deleted", "LockedNote"))
        self._lbl_locked_wrap.setVisible(False)

        hdr.addWidget(self._lbl_name); hdr.addWidget(self._lbl_locked_wrap); hdr.addStretch()
        fl.addLayout(hdr); fl.addWidget(hdiv())

        self._chk_enabled = QCheckBox("Profile enabled")
        self._chk_enabled.toggled.connect(self._on_enabled)
        fl.addWidget(self._chk_enabled)

        self._biome_section = QWidget()
        bs_lay = QVBoxLayout(self._biome_section); bs_lay.setContentsMargins(0, 0, 0, 0); bs_lay.setSpacing(6)
        biome_hdr = QHBoxLayout()
        self._lbl_biome = lbl("Expected Biome Name:", "FieldLbl")
        biome_hdr.addWidget(self._lbl_biome)
        biome_hdr.addWidget(HelpIcon(
            "Exact biome name (e.g., GLITCHED).\n"
            "Leave empty for items/events with no biome check."))
        biome_hdr.addStretch()
        bs_lay.addLayout(biome_hdr)
        self._inp_biome = QLineEdit()
        self._inp_biome.setPlaceholderText("Leave empty for Items/Merchant")
        self._inp_biome.textChanged.connect(self._on_biome)
        bs_lay.addWidget(self._inp_biome)
        kill_row = QHBoxLayout()
        zap_lbl  = QLabel()
        zap_lbl.setPixmap(_svg_icon("zap", C["yellow"], 13).pixmap(13, 13))
        zap_lbl.setFixedSize(18, 18); zap_lbl.setStyleSheet("background: transparent;")
        self._lbl_kill_note = lbl("Auto-kill Roblox on wrong biome", "FieldHint")
        kill_row.addWidget(zap_lbl); kill_row.addWidget(self._lbl_kill_note); kill_row.addStretch()
        self._lbl_kill_auto = QWidget(); self._lbl_kill_auto.setLayout(kill_row)
        bs_lay.addWidget(self._lbl_kill_auto)
        fl.addWidget(self._biome_section)

        self._rx_section = QWidget()
        rx_lay = QHBoxLayout(self._rx_section); rx_lay.setContentsMargins(0, 0, 0, 0)
        self._chk_rx = QCheckBox("Use Regex")
        self._chk_rx.toggled.connect(self._on_regex)
        rx_lay.addWidget(self._chk_rx)
        rx_lay.addWidget(HelpIcon("Enable for advanced patterns (e.g., multiple biomes)."))
        rx_lay.addStretch()
        fl.addWidget(self._rx_section)

        fl.addWidget(hdiv())

        tg_hdr = QHBoxLayout()
        tg_hdr.addWidget(lbl("TRIGGER KEYWORDS", "GrpLabel"))
        tg_hdr.addWidget(HelpIcon("Words that trigger the snipe (e.g., 'Mirror')."))
        tg_hdr.addStretch()
        self._trigger_group = QWidget()
        tg_lay = QVBoxLayout(self._trigger_group); tg_lay.setContentsMargins(0, 0, 0, 0)
        tg_lay.addLayout(tg_hdr)
        self._wl = self._kw_widget(tg_lay, is_blacklist=False)
        fl.addWidget(self._trigger_group); fl.addSpacing(6)

        bl_hdr = QHBoxLayout()
        bl_hdr.addWidget(lbl("BLACKLIST KEYWORDS", "GrpLabel"))
        bl_hdr.addWidget(HelpIcon("Ignore messages containing these words."))
        bl_hdr.addStretch()
        fl.addLayout(bl_hdr)
        self._bl = self._kw_widget(fl, is_blacklist=True)

        # Per-profile custom sound
        fl.addWidget(hdiv())
        snd_hdr = QHBoxLayout()
        snd_hdr.addWidget(lbl("CUSTOM SOUND FILE", "GrpLabel"))
        snd_hdr.addWidget(HelpIcon(
            "Play this audio file when this profile snipes.\n"
            "Supports .wav / .mp3 / .ogg — works on Windows, macOS and Linux.\n"
            "Leave empty to use the global beep."))
        snd_hdr.addStretch()
        fl.addLayout(snd_hdr)

        snd_row = QHBoxLayout(); snd_row.setSpacing(6)
        self._snd_path = QLineEdit()
        self._snd_path.setPlaceholderText("Path to audio file (optional)…")
        self._snd_path.setReadOnly(True)
        self._snd_path.setMinimumWidth(180)
        self._snd_path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._snd_path.textChanged.connect(self._on_snd_path)
        snd_row.addWidget(self._snd_path, 1) 

        snd_browse = QPushButton("  Browse…"); snd_browse.setObjectName("SmallBtn")
        snd_browse.setIcon(_svg_icon("folder-open", C["muted"], 14))
        snd_browse.setIconSize(QSize(14, 14))
        snd_browse.setFixedWidth(90)
        snd_browse.setFixedHeight(26)
        snd_browse.clicked.connect(self._browse_sound)
        snd_row.addWidget(snd_browse)

        snd_test = QPushButton("  Test"); snd_test.setObjectName("SmallBtn")
        snd_test.setIcon(_svg_icon("play", C["green2"], 14))
        snd_test.setIconSize(QSize(14, 14))
        snd_test.setFixedWidth(72)
        snd_test.setFixedHeight(26)
        snd_test.setToolTip("Play this sound file")
        snd_test.clicked.connect(self._test_profile_sound)
        snd_row.addWidget(snd_test)

        snd_clear = QPushButton("  Clear"); snd_clear.setObjectName("SmallDangerBtn")
        snd_clear.setIcon(_svg_icon("x", C["red2"], 14))
        snd_clear.setIconSize(QSize(14, 14))
        snd_clear.setFixedWidth(72)
        snd_clear.setFixedHeight(26)
        snd_clear.setToolTip("Remove custom sound — revert to global beep")
        snd_clear.clicked.connect(lambda: self._snd_path.setText(""))
        snd_row.addWidget(snd_clear)

        fl.addLayout(snd_row)

        scroll = SmoothScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._form)
        self._outer.addWidget(scroll)

    def _kw_widget(self, parent_lay: QVBoxLayout, is_blacklist: bool) -> QListWidget:
        lst = QListWidget(); lst.setMinimumHeight(120)
        inp = QLineEdit(); inp.setPlaceholderText("New keyword → Enter")

        def _add():
            t = inp.text().strip()
            if not t: return
            target = self._profile.blacklist_keywords if is_blacklist else self._profile.trigger_keywords
            if t not in target:
                target.append(t); lst.addItem(t); inp.clear()
                if self._profile: self._profile.compile()
                self.changed.emit()

        def _del():
            r = lst.currentRow()
            if r < 0: return
            target = self._profile.blacklist_keywords if is_blacklist else self._profile.trigger_keywords
            if 0 <= r < len(target): target.pop(r); lst.takeItem(r)
            if self._profile: self._profile.compile()
            self.changed.emit()

        inp.returnPressed.connect(_add)
        btn_del = QPushButton("Remove"); btn_del.setObjectName("SmallDangerBtn")
        btn_del.clicked.connect(_del)
        parent_lay.addWidget(lst); parent_lay.addWidget(inp)
        br = QHBoxLayout(); br.addWidget(btn_del); br.addStretch()
        parent_lay.addLayout(br)
        return lst

    def load(self, p: SnipeProfile):
        self._profile = p
        is_global = p.locked

        for w in (self._chk_enabled, self._chk_rx, self._inp_biome, self._snd_path):
            w.blockSignals(True)

        self._placeholder.setVisible(False); self._form.setVisible(True)
        self._lbl_name.setText(p.name)
        self._lbl_locked_wrap.setVisible(is_global)
        self._chk_enabled.setChecked(p.enabled)
        self._inp_biome.setText(p.verify_biome_name)
        self._chk_rx.setChecked(p.use_regex)
        self._update_biome_deps(p.verify_biome_name)
        self._snd_path.setText(getattr(p, "sound_alert_path", ""))

        for w in (self._chk_enabled, self._chk_rx, self._inp_biome, self._snd_path):
            w.blockSignals(False)

        for w in (self._biome_section, self._rx_section, self._trigger_group):
            w.setVisible(not is_global)

        self._wl.clear()
        for k in p.trigger_keywords: self._wl.addItem(k)
        self._bl.clear()
        for k in p.blacklist_keywords: self._bl.addItem(k)
        self._wl.setEnabled(not is_global)

    def _update_biome_deps(self, text: str):
        if not self._profile: return
        has_biome = bool(text.strip())
        self._profile.kill_on_wrong_biome = has_biome
        self._lbl_kill_auto.setVisible(has_biome and not self._profile.locked)

    def _on_snd_path(self, v: str):
        if self._profile:
            self._profile.sound_alert_path = v.strip()
            self.changed.emit()

    def _browse_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Sound File", "",
            "Audio Files (*.wav *.mp3 *.ogg *.flac *.aiff *.aif);;All Files (*)")
        if path:
            self._snd_path.setText(path)

    def _test_profile_sound(self):
        from sniper_engine import play_sound
        path = self._snd_path.text().strip()
        if path:
            threading.Thread(
                target=lambda: play_sound(filepath=path),
                daemon=True, name="ProfileSoundTest").start()
        else:
            threading.Thread(
                target=lambda: play_sound(1000, 200),
                daemon=True, name="ProfileSoundTest").start()

    def clear(self):
        self._profile = None
        self._placeholder.setVisible(True); self._form.setVisible(False)

    def _on_enabled(self, v: bool):
        if self._profile: self._profile.enabled = v; self.changed.emit()

    def _on_biome(self, v: str):
        if self._profile:
            self._profile.verify_biome_name = v.strip()
            self._update_biome_deps(v)
            self.changed.emit()

    def _on_regex(self, v: bool):
        if self._profile:
            self._profile.use_regex = v; self._profile.compile(); self.changed.emit()


# PAGE: SETTINGS

class SettingsPage(QWidget):
    config_saved    = Signal(object)
    _ch_fetch_done  = Signal(str, str, str)

    def __init__(self, cfg: SniperConfig, dev: bool = False):
        super().__init__()
        self._cfg = cfg; self._dev = dev
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(700)
        self._autosave_timer.timeout.connect(self._save)
        self._ch_fetch_done.connect(self._finish_add_ch)
        self._build()
        self._connect_autosave()

    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(26, 22, 26, 16); outer.setSpacing(14)
        hdr   = QHBoxLayout()
        col   = QVBoxLayout(); col.setSpacing(3)
        col.addWidget(lbl("Settings",             "PageTitle"))
        col.addWidget(lbl("Configure the snipe bot", "PageSub"))
        hdr.addLayout(col); hdr.addStretch()
        self._save_lbl = QLabel("")
        self._save_lbl.setStyleSheet(f"color: {C['dim']}; font-size: 10px; padding-right: 4px;")
        hdr.addWidget(self._save_lbl)

        # Export / Import config buttons in header
        _exp_btn = QPushButton("  Export Config"); _exp_btn.setObjectName("SmallBtn")
        _exp_btn.setIcon(_svg_icon("export", C["muted"], 14))
        _exp_btn.setIconSize(QSize(14, 14))
        _exp_btn.setToolTip("Save a copy of your config.json to a chosen location")
        _exp_btn.clicked.connect(self._export_config)
        hdr.addWidget(_exp_btn)

        _imp_btn = QPushButton("  Import Config"); _imp_btn.setObjectName("SmallBtn")
        _imp_btn.setIcon(_svg_icon("import", C["muted"], 14))
        _imp_btn.setIconSize(QSize(14, 14))
        _imp_btn.setToolTip("Load a config.json backup — replaces current settings")
        _imp_btn.clicked.connect(self._import_config)
        hdr.addWidget(_imp_btn)

        outer.addLayout(hdr); outer.addWidget(hdiv())

        scroll = SmoothScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        wrap = QWidget(); wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 2, 6, 10); wl.setSpacing(14)
        wl.addWidget(self._sec_discord())
        wl.addWidget(self._sec_channels())
        wl.addWidget(self._sec_profiles())
        wl.addWidget(self._sec_autojoin())
        wl.addWidget(self._sec_cooldown())
        wl.addWidget(self._sec_sound_alert())
        wl.addWidget(self._sec_extra_tokens())
        wl.addWidget(self._sec_appearance())
        self._dev_sec = self._sec_dev(); self._dev_sec.setVisible(self._dev)
        wl.addWidget(self._dev_sec)
        wl.addStretch()
        scroll.setWidget(wrap); outer.addWidget(scroll)

    def _card(self, title: str) -> tuple:
        c = QFrame(); c.setObjectName("SettCard")
        lay = QVBoxLayout(c); lay.setContentsMargins(16, 12, 16, 14); lay.setSpacing(10)
        lay.addWidget(lbl(title.upper(), "GrpLabel")); lay.addWidget(hdiv())
        return c, lay

    def _sec_discord(self) -> QFrame:
        c, lay = self._card("Discord")
        tok_hdr = QHBoxLayout()
        tok_hdr.addWidget(lbl("User Token", "FieldLbl"))
        tok_hdr.addWidget(HelpIcon(
            "How to get your Token:\n"
            "1. Open Discord (browser or app).\n"
            "2. Press F12 → Network tab.\n"
            "3. Filter by 'science'.\n"
            "4. Find 'Authorization' in headers.\n\n"
            "⚠ Never share your token!"))
        tok_hdr.addStretch()
        lay.addLayout(tok_hdr)
        self._tok = QLineEdit(self._cfg.token)
        self._tok.setEchoMode(QLineEdit.EchoMode.Password)
        self._tok.setPlaceholderText("Paste your Discord Token here")
        lay.addWidget(self._tok)
        chk = QCheckBox("Show token")
        chk.toggled.connect(lambda v: self._tok.setEchoMode(
            QLineEdit.EchoMode.Normal if v else QLineEdit.EchoMode.Password))
        lay.addWidget(chk)
        return c

    def _sec_channels(self) -> QFrame:
        c, lay = self._card("Monitored Channels")
        lay.addWidget(lbl("Channels where the bot listens for snipe links.", "FieldHint"))
        row = QHBoxLayout(); row.setSpacing(8)

        g_v = QVBoxLayout(); g_h = QHBoxLayout()
        g_h.addWidget(lbl("Server ID", "FieldLbl"))
        g_h.addWidget(HelpIcon("Right-click server icon → Copy ID\n(Enable Developer Mode in Discord settings)."))
        g_h.addStretch(); g_v.addLayout(g_h)
        self._cg = QLineEdit(); self._cg.setPlaceholderText("123456789…")
        g_v.addWidget(self._cg); row.addLayout(g_v)

        c_v = QVBoxLayout(); c_h = QHBoxLayout()
        c_h.addWidget(lbl("Channel ID", "FieldLbl"))
        c_h.addWidget(HelpIcon("Right-click channel name → Copy ID."))
        c_h.addStretch(); c_v.addLayout(c_h)
        self._cc = QLineEdit(); self._cc.setPlaceholderText("987654321…")
        c_v.addWidget(self._cc); row.addLayout(c_v)

        lay.addLayout(row)

        ab = QPushButton("+ Add Channel"); ab.setObjectName("SmallBtn")
        ab.clicked.connect(self._add_ch)
        lay.addWidget(ab, alignment=Qt.AlignmentFlag.AlignLeft)

        self._add_ch_status = QLabel("")
        self._add_ch_status.setStyleSheet(f"color: {C['dim']}; font-size: 10px;")
        lay.addWidget(self._add_ch_status)

        self._ch_container_widget = QWidget()
        self._ch_container_widget.setStyleSheet(
            f"background-color: {C['card2']}; border: 1px solid {C['border']}; border-radius: 7px;")
        self._ch_vlay = QVBoxLayout(self._ch_container_widget)
        self._ch_vlay.setContentsMargins(0, 0, 0, 0); self._ch_vlay.setSpacing(0)
        self._ch_rows: list[ChannelRow] = []

        ch_scroll = SmoothScrollArea(); ch_scroll.setWidget(self._ch_container_widget)
        ch_scroll.setWidgetResizable(True); ch_scroll.setMinimumHeight(150)
        ch_scroll.setMaximumHeight(260); ch_scroll.setFrameShape(QFrame.Shape.NoFrame)
        ch_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(ch_scroll)
        self._refresh_ch()
        return c

    def _sec_profiles(self) -> QFrame:
        c, lay = self._card("Snipe Profiles")
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)

        lh = QHBoxLayout()
        lh.addWidget(lbl("Profiles", "FieldLbl"))
        lh.addWidget(HelpIcon(
            "Check to enable. Click to edit keywords.\n"
            "Profiles are evaluated top-to-bottom (drag to reorder priority).\n"
            "Use ↑↓ buttons or drag-and-drop to change priority order."))
        lh.addStretch(); ll.addLayout(lh)

        self._plist = PropagatingListWidget(); self._plist.setObjectName("ProfileListWidget")
        self._plist.setMinimumHeight(400)
        self._plist.currentRowChanged.connect(self._on_profile_select)
        self._plist.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._plist.model().rowsMoved.connect(self._update_profile_order)
        self._plist.itemChanged.connect(self._on_profile_item_changed)
        ll.addWidget(self._plist)

        pbr = QHBoxLayout()
        btn_add = QPushButton("+ New"); btn_add.setObjectName("SmallBtn")
        btn_add.clicked.connect(self._add_profile)
        btn_del = QPushButton("Delete"); btn_del.setObjectName("SmallDangerBtn")
        btn_del.clicked.connect(self._del_profile)

        btn_up   = QPushButton("↑"); btn_up.setObjectName("SmallBtn")
        btn_up.setFixedWidth(30); btn_up.setToolTip("Move profile up (higher priority)")
        btn_up.clicked.connect(self._move_profile_up)
        btn_dn   = QPushButton("↓"); btn_dn.setObjectName("SmallBtn")
        btn_dn.setFixedWidth(30); btn_dn.setToolTip("Move profile down (lower priority)")
        btn_dn.clicked.connect(self._move_profile_down)

        pbr.addWidget(btn_add); pbr.addWidget(btn_del)
        pbr.addStretch()
        pbr.addWidget(btn_up); pbr.addWidget(btn_dn)
        ll.addLayout(pbr)

        self._editor = ProfileEditor(); self._editor.changed.connect(self._on_profile_changed)
        splitter.addWidget(left); splitter.addWidget(self._editor); splitter.setSizes([250, 550])
        lay.addWidget(splitter); lay.addWidget(hdiv())

        self._chk_ab = QCheckBox("Enable anti-bait biome verification")
        self._chk_ab.setChecked(self._cfg.anti_bait_enabled)
        lay.addWidget(self._chk_ab)
        self._refresh_profiles()
        return c

    def _move_profile_up(self):
        row = self._plist.currentRow()
        if row <= 0:
            return
        p = self._cfg.profiles
        if p[row - 1].locked:
            return
        p[row - 1], p[row] = p[row], p[row - 1]
        self._sync_profile_priorities()
        self._refresh_profiles()
        self._plist.setCurrentRow(row - 1)
        self._schedule_save()

    def _move_profile_down(self):
        row = self._plist.currentRow()
        p   = self._cfg.profiles
        if row < 0 or row >= len(p) - 1:
            return
        p[row], p[row + 1] = p[row + 1], p[row]
        self._sync_profile_priorities()
        self._refresh_profiles()
        self._plist.setCurrentRow(row + 1)
        self._schedule_save()

    def _sync_profile_priorities(self):
        """Assign integer priority values matching the current list order."""
        for i, p in enumerate(self._cfg.profiles):
            if not p.locked:
                p.priority = i

    def _sec_autojoin(self) -> QFrame:
        c, lay = self._card("Auto-Join")
        self._chk_aj = QCheckBox("Auto-join on snipe")
        self._chk_aj.setChecked(self._cfg.auto_join_enabled); lay.addWidget(self._chk_aj)
        self._chk_close = QCheckBox("Close Roblox before joining")
        self._chk_close.setChecked(self._cfg.close_roblox_before_join); lay.addWidget(self._chk_close)

        delay_row = QHBoxLayout(); delay_row.addWidget(lbl("Join delay (ms):", "FieldLbl"))
        self._spn = QSpinBox(); self._spn.setRange(0, 5000)
        self._spn.setValue(self._cfg.auto_join_delay_ms)
        delay_row.addWidget(self._spn); delay_row.addStretch(); lay.addLayout(delay_row)

        pause_hdr = QHBoxLayout()
        pause_hdr.addWidget(lbl("Auto-pause after snipe (s):", "FieldLbl"))
        pause_hdr.addWidget(HelpIcon(
            "Pause scanning for this many seconds after a snipe fires.\n"
            "Prevents interrupting gameplay. Set 0 to disable."))
        pause_hdr.addStretch()
        lay.addLayout(pause_hdr)

        pause_row = QHBoxLayout()
        self._spn_pause = QSpinBox(); self._spn_pause.setRange(0, 300)
        self._spn_pause.setValue(getattr(self._cfg, "pause_after_snipe_s", 0))
        self._spn_pause.setSuffix(" s")
        pause_row.addWidget(self._spn_pause); pause_row.addStretch()
        lay.addLayout(pause_row)

        lay.addWidget(hdiv())

        biome_hdr = QHBoxLayout()
        biome_hdr.addWidget(lbl("When biome ends:", "FieldLbl"))
        biome_hdr.addWidget(HelpIcon(
            "After joining a verified biome, the engine monitors it.\n"
            "When the biome changes (ends or switches), this action fires:\n\n"
            "• Do nothing — leave Roblox open as-is\n"
            "• Close Roblox — kill the process immediately\n"
            "• Return to home — close the game and relaunch the Roblox\n"
            "  app to the home page, ready for the next snipe faster"))
        biome_hdr.addStretch()
        lay.addLayout(biome_hdr)

        self._biome_leave_combo = QComboBox()
        self._biome_leave_combo.addItems([
            "Do nothing",
            "Close Roblox",
            "Return to home (faster next snipe)",
        ])
        action_map = {"none": 0, "kill": 1, "home": 2}
        self._biome_leave_combo.setCurrentIndex(
            action_map.get(getattr(self._cfg, "biome_leave_action", "none"), 0))
        self._biome_leave_combo.currentIndexChanged.connect(self._schedule_save)
        lay.addWidget(self._biome_leave_combo)
        return c

    def _sec_cooldown(self) -> QFrame:
        """Cooldown settings card — configures per-guild, per-profile and per-link TTLs."""
        c, lay = self._card("Cooldown")
        lay.addWidget(lbl(
            "Prevents the engine from re-joining from the same source too quickly.\n"
            "Set to 0 to disable that scope.", "FieldHint"))

        def _row(label: str, tooltip: str, attr: str, max_val: int = 300) -> QSpinBox:
            row_w = QHBoxLayout()
            row_w.addWidget(lbl(label, "FieldLbl"))
            row_w.addWidget(HelpIcon(tooltip))
            spn = QSpinBox(); spn.setRange(0, max_val); spn.setSuffix(" s")
            spn.setValue(int(getattr(self._cfg, attr, 0)))
            spn.valueChanged.connect(self._schedule_save)
            row_w.addWidget(spn); row_w.addStretch()
            lay.addLayout(row_w)
            return spn

        self._spn_cd_guild   = _row(
            "Guild cooldown:",
            "Ignore new links from the same Discord server for this many seconds after a snipe.",
            "cooldown_guild_ttl")
        self._spn_cd_profile = _row(
            "Profile cooldown:",
            "Ignore links that match the same profile for this many seconds (0 = disabled).",
            "cooldown_profile_ttl")
        self._spn_cd_link    = _row(
            "Link cooldown:",
            "Ignore the exact same Roblox URI for this many seconds.",
            "cooldown_link_ttl")
        return c

    def _sec_appearance(self) -> QFrame:
        c, lay = self._card("Appearance")
        lay.addWidget(lbl("Theme:", "FieldLbl"))
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Dark", "Light", "OLED"])
        theme_map = {"dark": 0, "light": 1, "oled": 2}
        self._theme_combo.setCurrentIndex(theme_map.get(self._cfg.theme, 0))
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        lay.addWidget(self._theme_combo)
        return c

    def _on_theme_changed(self, idx: int):
        names = ["dark", "light", "oled"]
        self._cfg.theme = names[idx]
        apply_theme(self._cfg.theme)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(make_qss())
        self._schedule_save()

    def _sec_sound_alert(self) -> QFrame:
        c, lay = self._card("Sound Alert")
        lay.addWidget(lbl(
            "Plays a sound when a snipe fires — works on Windows, macOS and Linux.",
            "FieldHint"))
        self._chk_sound = QCheckBox("Enable sound alert on snipe")
        self._chk_sound.setChecked(getattr(self._cfg, "sound_alert_enabled", False))
        self._chk_sound.toggled.connect(self._schedule_save)
        lay.addWidget(self._chk_sound)

        freq_row = QHBoxLayout()
        freq_row.addWidget(lbl("Frequency (Hz):", "FieldLbl"))
        freq_row.addWidget(HelpIcon("Pitch of the global beep. Ignored when a profile uses a custom sound file."))
        self._spn_sound_freq = QSpinBox(); self._spn_sound_freq.setRange(200, 8000)
        self._spn_sound_freq.setValue(getattr(self._cfg, "sound_alert_freq", 1000))
        self._spn_sound_freq.valueChanged.connect(self._schedule_save)
        freq_row.addWidget(self._spn_sound_freq); freq_row.addStretch()
        lay.addLayout(freq_row)

        dur_row = QHBoxLayout()
        dur_row.addWidget(lbl("Duration (ms):", "FieldLbl"))
        self._spn_sound_dur = QSpinBox(); self._spn_sound_dur.setRange(50, 2000)
        self._spn_sound_dur.setSuffix(" ms")
        self._spn_sound_dur.setValue(getattr(self._cfg, "sound_alert_dur_ms", 200))
        self._spn_sound_dur.valueChanged.connect(self._schedule_save)
        dur_row.addWidget(self._spn_sound_dur); dur_row.addStretch()
        lay.addLayout(dur_row)

        lay.addWidget(lbl(
            "Per-profile custom audio files can be set in the Snipe Profiles section.",
            "FieldHint"))

        test_btn = QPushButton("▶ Test Sound"); test_btn.setObjectName("SmallBtn")
        test_btn.clicked.connect(self._test_sound)
        lay.addWidget(test_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        return c

    def _test_sound(self):
        from sniper_engine import play_sound
        freq = self._spn_sound_freq.value()
        dur  = self._spn_sound_dur.value()
        threading.Thread(
            target=lambda: play_sound(freq, dur),
            daemon=True, name="SoundTest").start()

    def _sec_extra_tokens(self) -> QFrame:
        c, lay = self._card("Extra Discord Tokens")
        lay.addWidget(lbl(
            "Add additional Discord account tokens to monitor channels simultaneously.\n"
            "Each extra token runs a secondary gateway in listen-only mode — it receives\n"
            "messages but does not change the displayed connection status.",
            "FieldHint"))
        lay.addWidget(lbl(
            "⚠  Using self-bot tokens may violate Discord ToS. Use at your own risk.",
            "FieldHint"))

        input_row = QHBoxLayout(); input_row.setSpacing(8)
        self._extra_tok_input = QLineEdit()
        self._extra_tok_input.setPlaceholderText("Paste extra token here…")
        self._extra_tok_input.setEchoMode(QLineEdit.EchoMode.Password)
        input_row.addWidget(self._extra_tok_input)
        show_chk = QCheckBox("Show")
        show_chk.toggled.connect(lambda v: self._extra_tok_input.setEchoMode(
            QLineEdit.EchoMode.Normal if v else QLineEdit.EchoMode.Password))
        input_row.addWidget(show_chk)
        add_btn = QPushButton("+ Add"); add_btn.setObjectName("SmallBtn")
        add_btn.setFixedWidth(68)
        add_btn.clicked.connect(self._add_extra_token)
        input_row.addWidget(add_btn)
        lay.addLayout(input_row)

        self._extra_tok_list = QVBoxLayout()
        self._extra_tok_list.setSpacing(4)
        lay.addLayout(self._extra_tok_list)
        self._refresh_extra_tokens()
        return c

    def _add_extra_token(self):
        tok = self._extra_tok_input.text().strip()
        if not tok or len(tok) < 20:
            return
        tokens = list(getattr(self._cfg, "extra_tokens", []))
        if tok not in tokens:
            tokens.append(tok)
            self._cfg.extra_tokens = tokens
            self._cfg.save()
            self._extra_tok_input.clear()
            self._refresh_extra_tokens()
            self.config_saved.emit(self._cfg)

    def _remove_extra_token(self, tok: str):
        tokens = list(getattr(self._cfg, "extra_tokens", []))
        if tok in tokens:
            tokens.remove(tok)
            self._cfg.extra_tokens = tokens
            self._cfg.save()
            self._refresh_extra_tokens()
            self.config_saved.emit(self._cfg)

    def _refresh_extra_tokens(self):
        while self._extra_tok_list.count():
            item = self._extra_tok_list.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        tokens = getattr(self._cfg, "extra_tokens", [])
        if not tokens:
            empty = QLabel("No extra tokens added.")
            empty.setStyleSheet(f"color: {C['dim']}; font-size: 10px;")
            self._extra_tok_list.addWidget(empty)
            return
        for tok in tokens:
            row_w = QWidget()
            row_h = QHBoxLayout(row_w); row_h.setContentsMargins(0, 0, 0, 0); row_h.setSpacing(8)
            masked = f"{tok[:10]}…{tok[-4:]}" if len(tok) > 16 else tok
            tok_lbl = QLabel(masked)
            tok_lbl.setStyleSheet(f"color: {C['muted']}; font-size: 11px; font-family: monospace;")
            row_h.addWidget(tok_lbl); row_h.addStretch()
            del_btn = QPushButton("Remove"); del_btn.setObjectName("SmallBtn")
            del_btn.clicked.connect(lambda _, t=tok: self._remove_extra_token(t))
            row_h.addWidget(del_btn)
            self._extra_tok_list.addWidget(row_w)

    def _sec_dev(self) -> QFrame:
        c, lay = self._card("Dev Mode")
        self._chk_lf = QCheckBox("Log to file")
        self._chk_lf.setChecked(self._cfg.log_to_file); lay.addWidget(self._chk_lf)
        row = QHBoxLayout(); row.addWidget(lbl("Log tail bytes:", "FieldLbl"))
        self._spn_tail = QSpinBox(); self._spn_tail.setRange(1024, 65536)
        self._spn_tail.setValue(self._cfg.log_tail_bytes)
        row.addWidget(self._spn_tail); row.addStretch(); lay.addLayout(row)
        lay.addWidget(lbl("Ctrl+Shift+D to toggle dev mode.", "FieldHint"))
        return c

    def _connect_autosave(self):
        for w in (self._tok, ):
            w.textChanged.connect(self._schedule_save)
        for w in (self._chk_aj, self._chk_close, self._chk_ab, self._chk_lf, self._chk_sound):
            w.toggled.connect(self._schedule_save)
        for w in (self._spn, self._spn_tail, self._spn_pause,
                  self._spn_cd_guild, self._spn_cd_profile, self._spn_cd_link,
                  self._spn_sound_freq, self._spn_sound_dur):
            w.valueChanged.connect(self._schedule_save)

    def _schedule_save(self, *args):
        self._set_save_status("saving"); self._autosave_timer.start()

    def _set_save_status(self, state: str):
        if state == "saving":
            self._save_lbl.setText("● Saving…")
            self._save_lbl.setStyleSheet(f"color: {C['yellow']}; font-size: 10px; padding-right: 4px;")
        else:
            self._save_lbl.setText("Saved.")
            self._save_lbl.setStyleSheet(f"color: {C['green2']}; font-size: 10px; padding-right: 4px;")

    def _add_ch(self):
        g  = self._cg.text().strip()
        ch = self._cc.text().strip()
        if not g or not ch:
            self._add_ch_status.setStyleSheet(f"color: {C['red2']}; font-size: 10px;")
            self._add_ch_status.setText("Both Server ID and Channel ID are required.")
            return
        token = self._tok.text().strip() or self._cfg.token
        self._add_ch_status.setStyleSheet(f"color: {C['yellow']}; font-size: 10px;")
        self._add_ch_status.setText("Fetching channel info…")

        _sig = self._ch_fetch_done

        def _fetch():
            guild_name   = g
            channel_name = ch
            category     = ""
            try:
                import urllib.request as _ur
                headers = {"Authorization": token, "User-Agent": "SniperApp/1.0"}

                def _get(url):
                    req = _ur.Request(url, headers=headers)
                    with _ur.urlopen(req, timeout=6) as r:
                        return json.loads(r.read())

                gdata      = _get(f"https://discord.com/api/v10/guilds/{g}")
                guild_name = gdata.get("name", g)

                channels = _get(f"https://discord.com/api/v10/guilds/{g}/channels")
                cats     = {str(c["id"]): c["name"] for c in channels if c.get("type") == 4}
                for c in channels:
                    if str(c.get("id")) == ch:
                        channel_name = c.get("name", ch)
                        parent_id    = str(c.get("parent_id") or "")
                        category     = cats.get(parent_id, "")
                        break
            except Exception:
                pass

            if category:
                display = f"{guild_name}  ›  {category} / #{channel_name}"
            else:
                display = f"{guild_name}  ›  #{channel_name}"
            _sig.emit(g, ch, display)

        threading.Thread(target=_fetch, daemon=True, name="ChFetch").start()

    def _finish_add_ch(self, guild_id: str, channel_id: str, display: str):
        ch_cfg = ChannelConfig(guild_id=guild_id, channel_id=channel_id, name=display)
        self._cfg.monitored_channels.append(ch_cfg)
        self._refresh_ch()
        self._cg.clear(); self._cc.clear()
        self._add_ch_status.setStyleSheet(f"color: {C['green2']}; font-size: 10px;")
        self._add_ch_status.setText(f"Added: {display}")
        self._schedule_save()

    def _del_ch_at(self, idx: int):
        if 0 <= idx < len(self._cfg.monitored_channels):
            self._cfg.monitored_channels.pop(idx)
            self._refresh_ch(); self._schedule_save()

    def _refresh_ch(self):
        while self._ch_vlay.count():
            item = self._ch_vlay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._ch_rows.clear()

        channels = self._cfg.monitored_channels

        if not channels:
            empty = QLabel("  No channels added yet.")
            empty.setStyleSheet(f"color: {C['dim']}; font-size: 11px; padding: 14px;")
            self._ch_vlay.addWidget(empty)
            self._ch_rows.append(empty)
            self._ch_vlay.addStretch()
            return

        from collections import OrderedDict
        groups: OrderedDict = OrderedDict()
        for i, ch in enumerate(channels):
            gid = ch.guild_id
            if gid not in groups:
                groups[gid] = []
            groups[gid].append((i, ch))

        for guild_id, items in groups.items():
            first_name = items[0][1].name or ""
            if "›" in first_name:
                guild_display = first_name.split("›", 1)[0].strip()
            else:
                guild_display = guild_id

            header = ServerGroupHeader(guild_display)
            self._ch_vlay.addWidget(header)
            self._ch_rows.append(header)

            for (idx, ch) in items:
                if "›" in (ch.name or ""):
                    channel_label = ch.name.split("›", 1)[1].strip()
                else:
                    channel_label = ch.name or f"#{ch.channel_id}"

                row = ChannelItemRow(ch, channel_label)
                row.changed.connect(self._schedule_save)
                row.delete_requested.connect(lambda _i=idx: self._del_ch_at(_i))
                self._ch_vlay.addWidget(row)
                self._ch_rows.append(row)

        self._ch_vlay.addStretch()

    def _refresh_profiles(self):
        self._plist.blockSignals(True); self._plist.clear()
        lock_icon = _svg_icon("lock", C["muted"], 14)
        for p in self._cfg.profiles:
            item = QListWidgetItem(p.name)
            if p.locked:
                item.setIcon(lock_icon)
                item.setForeground(QColor(C["muted"]))
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            else:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if p.enabled else Qt.CheckState.Unchecked)
                item.setForeground(QColor(C["white"] if p.enabled else C["muted"]))
            self._plist.addItem(item)
        self._plist.blockSignals(False)
        if self._plist.count() > 0 and self._plist.currentRow() < 0:
            self._plist.setCurrentRow(0)

    def _on_profile_item_changed(self, item: QListWidgetItem):
        row = self._plist.row(item)
        if 0 <= row < len(self._cfg.profiles):
            p = self._cfg.profiles[row]
            if not p.locked:
                p.enabled = (item.checkState() == Qt.CheckState.Checked)
                self._schedule_save()
                if self._plist.currentRow() == row:
                    self._editor.load(p)

    def _on_profile_select(self, row: int):
        if 0 <= row < len(self._cfg.profiles): self._editor.load(self._cfg.profiles[row])
        else: self._editor.clear()

    def _on_profile_changed(self):
        row = self._plist.currentRow()
        if 0 <= row < len(self._cfg.profiles):
            p = self._cfg.profiles[row]
            self._plist.item(row).setCheckState(
                Qt.CheckState.Checked if p.enabled else Qt.CheckState.Unchecked)
        self._schedule_save()

    def _update_profile_order(self):
        new_order = []
        for i in range(self._plist.count()):
            name = self._plist.item(i).text()
            for p in self._cfg.profiles:
                if p.name == name: new_order.append(p); break
        self._cfg.profiles = new_order; self._schedule_save()

    def _add_profile(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Name:")
        name = name.strip()
        if not ok or not name: return
        if any(p.name == name for p in self._cfg.profiles):
            QMessageBox.warning(self, "Duplicate", "A profile with that name already exists."); return
        p = SnipeProfile(name=name); p.compile()
        self._cfg.profiles.append(p); self._refresh_profiles()
        self._plist.setCurrentRow(len(self._cfg.profiles) - 1)
        self._schedule_save()

    def _del_profile(self):
        row = self._plist.currentRow()
        if row < 0: return
        p = self._cfg.profiles[row]
        if p.locked:
            QMessageBox.information(self, "Locked", "Built-in profiles cannot be deleted."); return
        if QMessageBox.question(self, "Delete", f"Delete '{p.name}'?") == QMessageBox.StandardButton.Yes:
            self._cfg.profiles.pop(row)
            self._editor.clear(); self._refresh_profiles(); self._schedule_save()

    def _save(self):
        self._cfg.token                   = self._tok.text().strip()
        self._cfg.auto_join_enabled       = self._chk_aj.isChecked()
        self._cfg.close_roblox_before_join = self._chk_close.isChecked()
        self._cfg.auto_join_delay_ms      = self._spn.value()
        self._cfg.pause_after_snipe_s     = self._spn_pause.value()
        action_names = ["none", "kill", "home"]
        self._cfg.biome_leave_action      = action_names[self._biome_leave_combo.currentIndex()]
        self._cfg.anti_bait_enabled       = self._chk_ab.isChecked()
        self._cfg.cooldown_guild_ttl      = float(self._spn_cd_guild.value())
        self._cfg.cooldown_profile_ttl    = float(self._spn_cd_profile.value())
        self._cfg.cooldown_link_ttl       = float(self._spn_cd_link.value())
        self._cfg.sound_alert_enabled     = self._chk_sound.isChecked()
        self._cfg.sound_alert_freq        = self._spn_sound_freq.value()
        self._cfg.sound_alert_dur_ms      = self._spn_sound_dur.value()
        if self._dev:
            self._cfg.log_to_file    = self._chk_lf.isChecked()
            self._cfg.log_tail_bytes = self._spn_tail.value()
        self._cfg.ensure_global()
        self._sync_profile_priorities()
        for p in self._cfg.profiles: p.compile()
        self._cfg.save()
        self._set_save_status("saved")
        self.config_saved.emit(self._cfg)

    def _export_config(self):
        """Export current config.json to a user-chosen path."""
        self._save()
        src = Path(self._cfg.config_path)
        if not src.exists():
            QMessageBox.warning(self, "Export Failed", "Config file not found — save first.")
            return
        dst, _ = QFileDialog.getSaveFileName(
            self, "Export Config", "slaoq_sniper_config.json",
            "JSON Files (*.json);;All Files (*)")
        if not dst:
            return
        try:
            import shutil as _sh
            _sh.copy2(str(src), dst)
            QMessageBox.information(self, "Exported",
                f"Config saved to:\n{dst}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def _import_config(self):
        """Import a config.json backup, replacing current settings."""
        src, _ = QFileDialog.getOpenFileName(
            self, "Import Config", "",
            "JSON Files (*.json);;All Files (*)")
        if not src:
            return
        # Validate JSON before applying
        try:
            with open(src, encoding="utf-8") as fh:
                json.load(fh)
        except Exception as exc:
            QMessageBox.critical(self, "Invalid File",
                f"Not a valid JSON file:\n{exc}")
            return
        reply = QMessageBox.question(
            self, "Import Config",
            "This will replace your current settings with the imported file.\n"
            "A backup of the current config will be saved automatically.\n\nContinue?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        # Backup current config before overwriting
        dst = Path(self._cfg.config_path)
        backup = dst.with_suffix(".json.bak")
        try:
            if dst.exists():
                import shutil as _sh
                _sh.copy2(str(dst), str(backup))
        except Exception:
            pass
        try:
            import shutil as _sh
            _sh.copy2(src, str(dst))
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
            return
        # Reload config into memory
        from sniper_engine import SniperConfig as _SC
        new_cfg = _SC.load(str(dst))
        self._cfg = new_cfg
        apply_theme(new_cfg.theme)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(make_qss())
        self.config_saved.emit(new_cfg)
        QMessageBox.information(self, "Imported",
            "Config imported successfully. Backup saved as config.json.bak.\n"
            "Some UI fields may need a restart to reflect fully.")

    def toggle_dev(self, v: bool):
        self._dev = v; self._dev_sec.setVisible(v)

# PAGE: LOGS

class LogsPage(QWidget):
    def __init__(self, dev: bool = False):
        super().__init__()
        self._dev     = dev
        self._paused  = False
        self._cnt     = 0
        self._filter_level: Optional[LogLevel] = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(26, 22, 26, 16); lay.setSpacing(14)

        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(3)
        col.addWidget(lbl("Logs", "PageTitle"))
        hdr.addLayout(col); hdr.addStretch()

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All", "INFO", "SUCCESS", "WARN", "ERROR", "DEBUG", "SNIPE"])
        self._filter_combo.setFixedWidth(90)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        hdr.addWidget(lbl("Filter:", "FieldHint"))
        hdr.addWidget(self._filter_combo)
        hdr.addSpacing(8)

        self._btn_p = QPushButton(" Pause")
        self._btn_p.setIcon(_svg_icon("pause", C["muted"], 14))
        self._btn_p.setObjectName("GhostBtn"); self._btn_p.clicked.connect(self._toggle_pause)
        btn_c = QPushButton("✕ Clear"); btn_c.setObjectName("GhostBtn")
        btn_c.clicked.connect(self._clear)
        hdr.addWidget(self._btn_p); hdr.addWidget(btn_c)
        lay.addLayout(hdr); lay.addWidget(hdiv())

        self._con = QTextEdit(); self._con.setObjectName("LogConsole")
        self._con.setReadOnly(True)
        lay.addWidget(self._con)

        foot = QHBoxLayout()
        self._lc   = lbl("0 entries", "FieldHint")
        self._dbdg = lbl("● DEV MODE", "BadgeON"); self._dbdg.setVisible(self._dev)
        foot.addWidget(self._lc); foot.addStretch(); foot.addWidget(self._dbdg)
        lay.addLayout(foot)

        self._buffer: list[LogEntry] = []

    def _on_filter_changed(self, idx: int):
        mapping = {1: LogLevel.INFO, 2: LogLevel.SUCCESS, 3: LogLevel.WARN,
                   4: LogLevel.ERROR, 5: LogLevel.DEBUG, 6: LogLevel.SNIPE}
        self._filter_level = mapping.get(idx)
        self._replay()

    def _replay(self):
        self._con.clear(); self._cnt = 0
        for e in self._buffer:
            self._render(e)
        self._lc.setText(f"{self._cnt} entries")

    def append(self, e: LogEntry):
        if e.dev_only and not self._dev:
            return
        self._buffer.append(e)
        if len(self._buffer) > 5000:
            self._buffer = self._buffer[-4000:]
        if not self._paused:
            self._render(e)

    def _render(self, e: LogEntry):
        if self._filter_level and e.level != self._filter_level:
            return
        clr, tag, bg_rgba = {
            LogLevel.INFO:    (C["green"],  "INF", "rgba(0,255,136,0.07)"),
            LogLevel.SUCCESS: (C["green2"], "OK",  "rgba(0,204,102,0.10)"),
            LogLevel.WARN:    (C["yellow"], "WRN", "rgba(255,204,0,0.08)"),
            LogLevel.ERROR:   (C["red2"],   "ERR", "rgba(231,76,60,0.10)"),
            LogLevel.DEBUG:   (C["purple"], "DBG", "rgba(170,102,255,0.07)"),
            LogLevel.SNIPE:   (C["orange"], "SNP", "rgba(255,136,0,0.10)"),
        }.get(e.level, (C["green"], "INF", "rgba(0,255,136,0.07)"))
        pill = (f'<span style="background:{bg_rgba};color:{clr};'
                f'font-weight:800;font-size:9px;letter-spacing:1px;'
                f'border-radius:3px;padding:1px 5px;">{tag}</span>')
        html = (f'<span style="color:{C["dim"]};font-size:10px">{e.ts}</span> '
                f'{pill} '
                f'<span style="color:{clr}">{e.message}</span>')
        self._con.append(html)
        self._cnt += 1
        # Enforce 2000-line cap — drop oldest block when over limit
        doc = self._con.document()
        if doc.blockCount() > 2000:
            cursor = self._con.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(cursor.MoveOperation.Down,
                                cursor.MoveMode.KeepAnchor, doc.blockCount() - 2000)
            cursor.removeSelectedText()
        b = self._con.verticalScrollBar()
        if b.value() >= b.maximum() - 40:
            b.setValue(b.maximum())

    def _toggle_pause(self):
        self._paused = not self._paused
        self._btn_p.setText(" Resume" if self._paused else " Pause")
        self._btn_p.setIcon(_svg_icon("play" if self._paused else "pause", C["muted"], 14))
        if not self._paused:
            self._replay()

    def _clear(self):
        self._con.clear(); self._buffer.clear()
        self._cnt = 0; self._lc.setText("0 entries")

    def set_dev(self, v: bool):
        self._dev = v; self._dbdg.setVisible(v)

# PAGE: NOTIFICATIONS

class NotificationsPage(QWidget):
    config_changed = Signal()

    def __init__(self, cfg: SniperConfig):
        super().__init__()
        self._cfg = cfg
        self._build()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(26, 22, 26, 22); lay.setSpacing(18)

        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(3)
        col.addWidget(lbl("Notifications", "PageTitle"))
        col.addWidget(lbl("Desktop alerts & Discord webhook configuration", "PageSub"))
        hdr.addLayout(col); hdr.addStretch()
        lay.addLayout(hdr); lay.addWidget(hdiv())

        scroll = SmoothScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        wrap = QWidget(); wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 2, 6, 10); wl.setSpacing(14)
        wl.addWidget(self._sec_desktop())
        wl.addWidget(self._sec_webhook())
        wl.addStretch()
        scroll.setWidget(wrap); lay.addWidget(scroll)

    def _card(self, title: str) -> tuple:
        c = QFrame(); c.setObjectName("SettCard")
        lay = QVBoxLayout(c); lay.setContentsMargins(16, 12, 16, 14); lay.setSpacing(10)
        lay.addWidget(lbl(title.upper(), "GrpLabel")); lay.addWidget(hdiv())
        return c, lay

    def _sec_desktop(self) -> QFrame:
        c, lay = self._card("Desktop Notifications")
        lay.addWidget(lbl(
            "Show a system notification for the following events:", "FieldHint"))

        self._notif_snipe  = QCheckBox("Snipe detected")
        self._notif_biome  = QCheckBox("Biome verification result")
        self._notif_start  = QCheckBox("Sniper started")
        self._notif_stop   = QCheckBox("Sniper stopped")

        for chk in (self._notif_snipe, self._notif_biome,
                    self._notif_start, self._notif_stop):
            chk.setChecked(True); lay.addWidget(chk)

        lay.addWidget(lbl(
            "Requires system tray support. Notifications may appear differently per OS.",
            "FieldHint"))
        return c

    def _sec_webhook(self) -> QFrame:
        wh = self._cfg.webhook
        c, lay = self._card("Discord Webhook")

        url_hdr = QHBoxLayout()
        url_hdr.addWidget(lbl("Webhook URL", "FieldLbl"))
        url_hdr.addWidget(HelpIcon(
            "Create a webhook in your Discord server:\n"
            "Server Settings → Integrations → Webhooks → New Webhook"))
        url_hdr.addStretch()
        lay.addLayout(url_hdr)

        self._wh_url = QLineEdit(wh.url)
        self._wh_url.setPlaceholderText("https://discord.com/api/webhooks/…")
        self._wh_url.textChanged.connect(self._save_webhook)
        lay.addWidget(self._wh_url)

        self._wh_enabled = QCheckBox("Enable webhooks")
        self._wh_enabled.setChecked(wh.enabled)
        self._wh_enabled.toggled.connect(self._save_webhook)
        lay.addWidget(self._wh_enabled)

        lay.addWidget(hdiv())
        lay.addWidget(lbl("Send webhooks for:", "GrpLabel"))

        self._wh_on_snipe  = QCheckBox("Snipe detected")
        self._wh_on_biome  = QCheckBox("Biome verification")
        self._wh_on_start  = QCheckBox("Sniper started")
        self._wh_on_stop   = QCheckBox("Sniper stopped")
        self._wh_on_snipe.setChecked(wh.on_snipe)
        self._wh_on_biome.setChecked(wh.on_biome)
        self._wh_on_start.setChecked(wh.on_start)
        self._wh_on_stop.setChecked(wh.on_stop)
        for chk in (self._wh_on_snipe, self._wh_on_biome,
                    self._wh_on_start, self._wh_on_stop):
            chk.toggled.connect(self._save_webhook); lay.addWidget(chk)

        lay.addWidget(hdiv())
        lay.addWidget(lbl("Ping type:", "GrpLabel"))
        self._ping_combo = QComboBox()
        self._ping_combo.addItems(["No ping", "Specific Role", "Specific User"])
        ping_map = {"none": 0, "role": 1, "user": 2}
        self._ping_combo.setCurrentIndex(ping_map.get(wh.ping_type, 0))
        self._ping_combo.currentIndexChanged.connect(self._on_ping_type)
        lay.addWidget(self._ping_combo)

        self._ping_target_row = QWidget()
        ptr = QHBoxLayout(self._ping_target_row); ptr.setContentsMargins(0, 0, 0, 0)
        ptr.addWidget(lbl("Role / User ID:", "FieldLbl"))
        self._ping_target = QLineEdit(wh.ping_target)
        self._ping_target.setPlaceholderText("ID here…")
        self._ping_target.textChanged.connect(self._save_webhook)
        ptr.addWidget(self._ping_target)
        lay.addWidget(self._ping_target_row)
        self._ping_target_row.setVisible(wh.ping_type in ("role", "user"))

        lay.addWidget(hdiv())
        test_btn = QPushButton("Send Test Webhook"); test_btn.setObjectName("SmallBtn")
        test_btn.clicked.connect(self._test_webhook)
        lay.addWidget(test_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        return c

    def _on_ping_type(self, idx: int):
        self._ping_target_row.setVisible(idx in (1, 2))
        self._save_webhook()

    def _save_webhook(self):
        ping_names = ["none", "role", "user"]
        wh = self._cfg.webhook
        wh.url         = self._wh_url.text().strip()
        wh.enabled     = self._wh_enabled.isChecked()
        wh.on_snipe    = self._wh_on_snipe.isChecked()
        wh.on_biome    = self._wh_on_biome.isChecked()
        wh.on_start    = self._wh_on_start.isChecked()
        wh.on_stop     = self._wh_on_stop.isChecked()
        wh.ping_type   = ping_names[self._ping_combo.currentIndex()]
        wh.ping_target = self._ping_target.text().strip()
        self._cfg.save()
        self.config_changed.emit()

    def _test_webhook(self):
        wh = self._cfg.webhook
        if not wh.url:
            return

        async def _send():
            async with aiohttp.ClientSession() as sess:
                sender = WebhookSender(sess, wh)
                await sender.send("test")

        def _run():
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_send())
            except Exception as exc:
                print(f"Test webhook error: {exc}")
            finally:
                loop.close()

        threading.Thread(target=_run, daemon=True, name="WebhookTest").start()

# PAGE: BLACKLIST

class BlacklistPage(QWidget):
    _fetch_done     = Signal(str, str)
    config_changed  = Signal()      # emitted when delete-watch seconds changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = None
        self._cfg_ref  = None
        self._fetch_done.connect(self._on_fetch_done)
        self._build()

    def set_manager(self, manager, cfg=None):
        self._manager = manager
        self._cfg_ref  = cfg
        if cfg:
            self._dw_spin.setValue(getattr(cfg, "delete_watch_seconds", 0))
        self.refresh()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 16)
        outer.setSpacing(14)

        # header
        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(3)
        col.addWidget(lbl("Blacklist", "PageTitle"))
        col.addWidget(lbl("Users blocked from triggering snipes.", "PageSub"))
        hdr.addLayout(col); hdr.addStretch()

        refresh_btn = QPushButton("⟳ Refresh")
        refresh_btn.setObjectName("GhostBtn")
        refresh_btn.clicked.connect(self.refresh)
        hdr.addWidget(refresh_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.setObjectName("GhostBtn")
        clear_btn.clicked.connect(self._clear_all)
        hdr.addWidget(clear_btn)

        outer.addLayout(hdr)
        outer.addWidget(hdiv())

        # scrollable list area
        add_card = QFrame(); add_card.setObjectName("SettCard")
        add_lay  = QVBoxLayout(add_card)
        add_lay.setContentsMargins(14, 12, 14, 12); add_lay.setSpacing(8)
        add_lay.addWidget(lbl("ADD USER MANUALLY", "GrpLabel"))

        input_row = QHBoxLayout(); input_row.setSpacing(8)
        self._add_id_input = QLineEdit()
        self._add_id_input.setPlaceholderText("Discord User ID  (e.g. 123456789012345678)")
        self._add_id_input.returnPressed.connect(self._add_manual)
        input_row.addWidget(self._add_id_input)

        add_btn = QPushButton("+ Add")
        add_btn.setObjectName("SmallBtn")
        add_btn.setFixedWidth(68)
        add_btn.clicked.connect(self._add_manual)
        input_row.addWidget(add_btn)
        add_lay.addLayout(input_row)

        self._add_status = QLabel("")
        self._add_status.setStyleSheet(f"color: {C['dim']}; font-size: 10px;")
        add_lay.addWidget(self._add_status)
        outer.addWidget(add_card)

        self._stat_lbl = lbl("0 users blacklisted", "FieldHint")
        outer.addWidget(self._stat_lbl)

        scroll = SmoothScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._wrap = QWidget()
        self._list_lay = QVBoxLayout(self._wrap)
        self._list_lay.setContentsMargins(0, 4, 6, 10)
        self._list_lay.setSpacing(6)
        scroll.setWidget(self._wrap)
        outer.addWidget(scroll, stretch=1)

        self._empty_lbl = QLabel("No blacklisted users.")
        self._empty_lbl.setStyleSheet(
            f"color: {C['dim']}; font-size: 12px; padding: 20px;")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_lay.addWidget(self._empty_lbl)
        self._list_lay.addStretch()
        self._rows: list[QFrame] = []

        # delete-watch config section (below the list)
        outer.addWidget(hdiv())
        cfg_card = QFrame(); cfg_card.setObjectName("SettCard")
        cfg_lay  = QVBoxLayout(cfg_card)
        cfg_lay.setContentsMargins(14, 12, 14, 12); cfg_lay.setSpacing(10)

        dw_hdr = QHBoxLayout()
        dw_hdr.addWidget(lbl("AUTO-BLACKLIST ON MESSAGE DELETE", "GrpLabel"))
        dw_hdr.addWidget(HelpIcon(
            "If a user whose message triggered a snipe deletes that message\n"
            "within the watch window, they are auto-blacklisted.\n\n"
            "Set to 0 to disable. Recommended: 30–60 seconds.\n"
            "A webhook embed is also sent when someone is auto-blacklisted."))
        dw_hdr.addStretch()
        cfg_lay.addLayout(dw_hdr)

        dw_row = QHBoxLayout(); dw_row.setSpacing(10)
        dw_row.addWidget(lbl("Watch window (seconds):", "FieldLbl"))
        self._dw_spin = QSpinBox()
        self._dw_spin.setRange(0, 300)
        self._dw_spin.setValue(0)
        self._dw_spin.setSuffix(" s")
        self._dw_spin.setToolTip("0 = disabled")
        self._dw_spin.valueChanged.connect(self._on_dw_changed)
        dw_row.addWidget(self._dw_spin)
        dw_row.addWidget(lbl("(0 = disabled)", "FieldHint"))
        dw_row.addStretch()
        cfg_lay.addLayout(dw_row)

        cfg_lay.addWidget(lbl(
            "When triggered, an embed is sent to your webhook:\n"
            "  user_id (@username) has been blacklisted for deleting their message.",
            "FieldHint"))

        save_row = QHBoxLayout()
        self._bl_save_lbl = QLabel("")
        self._bl_save_lbl.setStyleSheet(f"color: {C['dim']}; font-size: 10px;")
        save_row.addStretch(); save_row.addWidget(self._bl_save_lbl)
        cfg_lay.addLayout(save_row)
        outer.addWidget(cfg_card)

        self._bl_save_timer = QTimer(self)
        self._bl_save_timer.setSingleShot(True)
        self._bl_save_timer.setInterval(700)
        self._bl_save_timer.timeout.connect(self._do_save)

    def _on_dw_changed(self, val: int):
        if self._cfg_ref:
            self._cfg_ref.delete_watch_seconds = val
            self._bl_save_lbl.setText("● Saving…")
            self._bl_save_lbl.setStyleSheet(f"color: {C['yellow']}; font-size: 10px;")
            self._bl_save_timer.start()

    def _do_save(self):
        if self._cfg_ref:
            self._cfg_ref.save()
            self.config_changed.emit()
        self._bl_save_lbl.setText("Saved.")
        self._bl_save_lbl.setStyleSheet(f"color: {C['green2']}; font-size: 10px;")

    def add_auto_entry(self, uid: str, username: str):
        """Called from MainWindow when engine fires on_delete_blacklist."""
        self.refresh()

    def _add_manual(self):
        uid = self._add_id_input.text().strip()
        if not uid or not uid.isdigit():
            self._add_status.setStyleSheet(f"color: {C['red2']}; font-size: 10px;")
            self._add_status.setText("Enter a valid numeric Discord User ID.")
            return
        if not self._manager:
            self._add_status.setStyleSheet(f"color: {C['red2']}; font-size: 10px;")
            self._add_status.setText("Start the sniper first to enable the blacklist.")
            return
        self._add_status.setStyleSheet(f"color: {C['yellow']}; font-size: 10px;")
        self._add_status.setText("Looking up username…")
        sig = self._fetch_done
        token = (self._cfg_ref.token if self._cfg_ref else "")

        def _fetch():
            username = uid
            try:
                import urllib.request as _ur
                headers = {"Authorization": token, "User-Agent": "SniperApp/1.0"}
                req = _ur.Request(
                    f"https://discord.com/api/v10/users/{uid}", headers=headers)
                with _ur.urlopen(req, timeout=6) as r:
                    data = json.loads(r.read())
                username = data.get("username") or data.get("global_name") or uid
            except Exception:
                pass
            sig.emit(uid, username)

        threading.Thread(target=_fetch, daemon=True, name="BLFetch").start()

    def _on_fetch_done(self, uid: str, username: str):
        if not self._manager:
            return
        self._manager.add(uid, username, reason=REASON_MANUAL)
        self._add_id_input.clear()
        self._add_status.setStyleSheet(f"color: {C['green2']}; font-size: 10px;")
        self._add_status.setText(f"Added: {username} ({uid})")
        self.refresh()

    def refresh(self):
        for row in self._rows:
            self._list_lay.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        if self._manager is None:
            self._stat_lbl.setText("Start the sniper to load the blacklist.")
            self._empty_lbl.setVisible(True)
            return

        entries = self._manager.all_entries()
        self._stat_lbl.setText(f"{len(entries)} user(s) blacklisted")
        self._empty_lbl.setVisible(len(entries) == 0)

        for entry in sorted(entries, key=lambda e: -e.count):
            row = self._make_row(entry)
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)
            self._rows.append(row)

    def _make_row(self, entry) -> QFrame:
        row = QFrame(); row.setObjectName("SettCard")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(14, 10, 14, 10); lay.setSpacing(10)

        col = QVBoxLayout(); col.setSpacing(2)

        display = entry.username if entry.username and entry.username != entry.user_id \
            else "Unknown User"
        name_lbl = QLabel(display)
        name_lbl.setStyleSheet(
            f"color: {C['text']}; font-size: 12px; font-weight: 600;")
        col.addWidget(name_lbl)

        meta_parts = []
        if entry.user_id:
            meta_parts.append(f"ID: {entry.user_id}")
        if entry.reason:
            meta_parts.append(f"Reason: {entry.reason}")
        meta_parts.append(f"Offenses: {entry.count}")
        reason_lbl = QLabel("  ·  ".join(meta_parts))
        reason_lbl.setStyleSheet(f"color: {C['muted']}; font-size: 10px;")
        col.addWidget(reason_lbl)

        lay.addLayout(col); lay.addStretch()

        badge = QLabel(str(entry.count))
        badge.setStyleSheet(
            f"background: {C['red'] if entry.count > 1 else C['border2']}; "
            f"color: {C['text']}; border-radius: 8px; padding: 2px 8px; font-size: 11px;")
        lay.addWidget(badge)

        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName("SmallBtn")
        remove_btn.clicked.connect(lambda _, uid=entry.user_id: self._remove(uid))
        lay.addWidget(remove_btn)

        return row

    def _remove(self, user_id: str):
        if self._manager:
            self._manager.remove(user_id)
        self.refresh()

    def _clear_all(self):
        if self._manager is None:
            return
        if QMessageBox.question(
            self, "Clear Blacklist",
            "Remove ALL blacklisted users?"
        ) == QMessageBox.StandardButton.Yes:
            self._manager.clear()
            self.refresh()


# PAGE: SNIPE HISTORY

class SnipeHistoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: Optional[SnipeHistoryManager] = None
        self._rows: list[QFrame] = []
        self._build()

    def set_history(self, history: "SnipeHistoryManager"):
        self._history = history
        self._dirty   = True   # force rebuild on next showEvent
        self.refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 16)
        lay.setSpacing(14)

        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(3)
        col.addWidget(lbl("Snipe History", "PageTitle"))
        col.addWidget(lbl("All snipes this session and from previous sessions.", "PageSub"))
        hdr.addLayout(col); hdr.addStretch()

        refresh_btn = QPushButton("⟳ Refresh")
        refresh_btn.setObjectName("GhostBtn")
        refresh_btn.clicked.connect(self.refresh)
        hdr.addWidget(refresh_btn)

        clear_btn = QPushButton("Clear History")
        clear_btn.setObjectName("GhostBtn")
        clear_btn.clicked.connect(self._clear)
        hdr.addWidget(clear_btn)

        lay.addLayout(hdr)
        lay.addWidget(hdiv())

        self._stat_lbl = lbl("No snipes recorded yet.", "FieldHint")
        lay.addWidget(self._stat_lbl)

        scroll = SmoothScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._wrap = QWidget()
        self._list_lay = QVBoxLayout(self._wrap)
        self._list_lay.setContentsMargins(0, 4, 6, 10)
        self._list_lay.setSpacing(8)
        scroll.setWidget(self._wrap)
        lay.addWidget(scroll)

        self._empty_lbl = QLabel("No snipes recorded yet.")
        self._empty_lbl.setStyleSheet(
            f"color: {C['dim']}; font-size: 12px; padding: 20px;")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_lay.addWidget(self._empty_lbl)
        self._list_lay.addStretch()

    def add_entry(self, snipe_data: dict):
        """Called in real-time when a new snipe fires.
        Only rebuilds if the page is currently visible to avoid unnecessary work."""
        if not self._history:
            return
        if self.isVisible():
            self._rebuild_list(self._history.all_entries())
        else:
            self._dirty = True   # rebuild lazily on next showEvent

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_dirty", False) and self._history:
            self._dirty = False
            self._rebuild_list(self._history.all_entries())

    def refresh(self):
        if self._history is None:
            return
        self._rebuild_list(self._history.all_entries())

    def _rebuild_list(self, entries: list):
        for row in self._rows:
            self._list_lay.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        count = len(entries)
        self._stat_lbl.setText(
            f"{count} snipe{'s' if count != 1 else ''} recorded" if count else "No snipes recorded yet.")
        self._empty_lbl.setVisible(count == 0)

        for entry in entries:
            row = self._make_row(entry)
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)
            self._rows.append(row)

    def _make_row(self, entry: dict) -> QFrame:
        row = QFrame(); row.setObjectName("SettCard")
        lay = QVBoxLayout(row)
        lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(6)

        top = QHBoxLayout(); top.setSpacing(8)

        profile_lbl = QLabel(entry.get("profile", "?"))
        profile_lbl.setStyleSheet(
            f"color: {C['white']}; font-size: 12px; font-weight: 700; "
            f"background: {C['border2']}; border-radius: 4px; padding: 1px 7px;")
        top.addWidget(profile_lbl)

        if entry.get("keyword"):
            kw_lbl = QLabel(entry["keyword"])
            kw_lbl.setStyleSheet(
                f"color: {C['green2']}; font-size: 10px; font-weight: 600; "
                f"background: rgba(0,204,102,0.08); border-radius: 4px; padding: 1px 6px;")
            top.addWidget(kw_lbl)

        top.addStretch()

        bv = entry.get("biome_verified")
        if bv is True:
            bv_lbl = QLabel("✓ Biome OK")
            bv_lbl.setStyleSheet(f"color: {C['green2']}; font-size: 10px; font-weight: 600;")
            top.addWidget(bv_lbl)
        elif bv is False:
            bv_lbl = QLabel("✗ Wrong Biome")
            bv_lbl.setStyleSheet(f"color: {C['red2']}; font-size: 10px; font-weight: 600;")
            top.addWidget(bv_lbl)

        # timestamp
        ts_raw = entry.get("timestamp", "")
        try:
            dt   = datetime.datetime.fromisoformat(ts_raw)
            ts   = dt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            ts = ts_raw[:19] if ts_raw else "?"
        ts_lbl = QLabel(ts)
        ts_lbl.setStyleSheet(f"color: {C['dim']}; font-size: 10px;")
        top.addWidget(ts_lbl)
        lay.addLayout(top)

        author_display = entry.get("author_display") or entry.get("author", "?")
        author_id      = entry.get("author_id", "")
        author_tag     = f"@{entry.get('author', author_display)}"
        author_line    = f"{author_display} ({author_tag})" if author_display != entry.get("author") else author_tag
        author_lbl = QLabel(author_line)
        author_lbl.setStyleSheet(f"color: {C['muted']}; font-size: 11px;")
        lay.addWidget(author_lbl)

        raw = entry.get("raw_message", "")
        if raw:
            raw_lbl = QLabel(raw[:120] + ("…" if len(raw) > 120 else ""))
            raw_lbl.setStyleSheet(
                f"color: {C['dim']}; font-size: 10px; font-style: italic;")
            raw_lbl.setWordWrap(True)
            lay.addWidget(raw_lbl)

        btns = QHBoxLayout(); btns.setSpacing(6)
        roblox_url = entry.get("roblox_web_url", "")
        jump_url   = entry.get("jump_url", "")
        if roblox_url:
            rb_btn = QPushButton("Open in Roblox")
            rb_btn.setObjectName("SmallBtn")
            rb_btn.clicked.connect(lambda _, u=roblox_url: self._open_url(u))
            btns.addWidget(rb_btn)
        if jump_url:
            jmp_btn = QPushButton("Jump to Message")
            jmp_btn.setObjectName("SmallBtn")
            jmp_btn.clicked.connect(lambda _, u=jump_url: self._open_url(u))
            btns.addWidget(jmp_btn)
        btns.addStretch()
        lay.addLayout(btns)

        return row

    @staticmethod
    def _open_url(url: str):
        import webbrowser
        webbrowser.open(url)

    def _clear(self):
        if self._history is None:
            return
        if QMessageBox.question(
            self, "Clear History", "Remove all snipe history entries?"
        ) == QMessageBox.StandardButton.Yes:
            self._history.clear()
            self.refresh()


# PAGE: PLUGINS

class PluginsPage(QWidget):
    """
    Displays installed plugins and lets users enable/disable them.
    Each plugin card shows its name, description and icon from metadata.
    Plugin configuration sections appear below the plugin list.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loader = None
        self._build()

    def set_loader(self, loader):
        """Inject the PluginLoader instance from the engine."""
        self._loader = loader
        self.refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 16)
        lay.setSpacing(14)

        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(3)
        col.addWidget(lbl("Plugins", "PageTitle"))
        col.addWidget(lbl("External modules that extend sniper functionality.", "PageSub"))
        hdr.addLayout(col); hdr.addStretch()

        refresh_btn = QPushButton("⟳ Reload")
        refresh_btn.setObjectName("GhostBtn")
        refresh_btn.clicked.connect(self._reload)
        hdr.addWidget(refresh_btn)
        lay.addLayout(hdr); lay.addWidget(hdiv())

        self._stat_lbl = lbl("No plugins loaded.", "FieldHint")
        lay.addWidget(self._stat_lbl)

        scroll = SmoothScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._wrap = QWidget()
        self._cards_lay = QVBoxLayout(self._wrap)
        self._cards_lay.setContentsMargins(0, 4, 6, 10)
        self._cards_lay.setSpacing(10)
        scroll.setWidget(self._wrap)
        lay.addWidget(scroll)

        self._empty_lbl = QLabel(
            "No plugins found.\nAdd .py files to the plugins/ folder and click Reload.")
        self._empty_lbl.setStyleSheet(
            f"color: {C['dim']}; font-size: 12px; padding: 20px;")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cards_lay.addWidget(self._empty_lbl)
        self._cards_lay.addStretch()

        self._plugin_widgets: list[QFrame] = []

    def refresh(self):
        for w in self._plugin_widgets:
            self._cards_lay.removeWidget(w); w.deleteLater()
        self._plugin_widgets.clear()

        if self._loader is None:
            self._stat_lbl.setText("Plugin system not available.")
            self._empty_lbl.setVisible(True)
            return

        plugins = self._loader.plugins()
        self._stat_lbl.setText(
            f"{len(plugins)} plugin(s) installed"
            f"  ·  {sum(1 for p in plugins if p.enabled)} enabled")
        self._empty_lbl.setVisible(len(plugins) == 0)

        for rec in plugins:
            card = self._make_card(rec)
            self._cards_lay.insertWidget(self._cards_lay.count() - 1, card)
            self._plugin_widgets.append(card)

    def _make_card(self, rec) -> QFrame:
        card = QFrame(); card.setObjectName("SettCard")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(12)

        icon_key = rec.icon if rec.module else "info"
        icon_lbl = QLabel()
        icon_lbl.setPixmap(_svg_icon(icon_key, C["muted"], 20).pixmap(20, 20))
        icon_lbl.setFixedSize(28, 28)
        lay.addWidget(icon_lbl)

        col = QVBoxLayout(); col.setSpacing(2)
        name_lbl = QLabel(rec.name)
        name_lbl.setStyleSheet(
            f"color: {C['text']}; font-size: 12px; font-weight: 600;")
        desc_lbl = QLabel(rec.description or rec.path.name)
        desc_lbl.setStyleSheet(f"color: {C['muted']}; font-size: 10px;")
        if rec.error:
            err_lbl = QLabel(f"⚠ Error: {rec.error[:80]}")
            err_lbl.setStyleSheet(f"color: {C['red2']}; font-size: 10px;")
            col.addWidget(err_lbl)
        col.addWidget(name_lbl); col.addWidget(desc_lbl)
        lay.addLayout(col); lay.addStretch()

        toggle = ToggleSwitch(rec.enabled)
        toggle.toggled.connect(
            lambda checked, r=rec: self._toggle_plugin(r, checked))
        lay.addWidget(toggle)

        return card

    def _toggle_plugin(self, rec, enabled: bool):
        if self._loader:
            self._loader.set_enabled(rec.name, enabled)

    def _reload(self):
        if self._loader:
            self._loader.discover()
            self.refresh()


# MAIN WINDOW

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._dev  = False
        self._cfg  = SniperConfig.load()
        self._br:  Optional[Bridge] = None
        self._run  = False
        self._re:  int              = Edge.NONE
        self._rp:  Optional[QPoint] = None
        self._rg:  Optional[QRect]  = None

        self._is_paused = False
        self._hotkey_cfg = {"toggle_key": "", "toggle_en": False,
                            "pause_key": "",  "pause_en": False, "pause_dur": 60}
        self._hk_toggle_shortcut: Optional[QShortcut] = None
        self._hk_pause_shortcut:  Optional[QShortcut] = None

        apply_theme(self._cfg.theme)
        QApplication.instance().setStyleSheet(make_qss())

        self._setup(); self._build(); self._connect(); self._shortcuts()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(2000)
        self._updater = AutoUpdater(self)
        self._updater.update_available.connect(self._on_update_available)
        if not _UPDATE_TRIGGERED:
            QTimer.singleShot(3000, self._updater.check_async)

        # System tray for desktop notifications
        self._tray: Optional[QSystemTrayIcon] = None
        self._setup_tray()

        # Pre-load plugins at startup so the Plugins tab works before engine starts
        self._init_plugin_loader()

    def _init_plugin_loader(self):
        if getattr(sys, "frozen", False):
            _base = Path(os.path.dirname(sys.executable))
        else:
            _base = Path(os.path.dirname(os.path.abspath(__file__)))
        plugins_dir = _base / "plugins"
        pl = PluginLoader(plugins_dir)
        pl.discover()
        self._startup_plugin_loader = pl
        self._ppg.set_loader(pl)
        plugins_exist = plugins_dir.exists() and any(
            f for f in plugins_dir.glob("*.py") if not f.name.startswith("_"))
        self._sb.set_plugins_visible(plugins_exist)

    def _setup(self):
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(WIN_W, WIN_H)
        self.setMinimumSize(WIN_MIN_W, WIN_MIN_H)
        self.setMouseTracking(True)

        app_icon = create_taskbar_icon()
        QApplication.instance().setWindowIcon(app_icon)
        self.setWindowIcon(app_icon)

        try:
            if platform.system() == "Windows":
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    f"slaoq.sniper.{APP_VERSION}")
        except Exception:
            pass

        self._edge_filter = EdgeCursorFilter(self)
        QApplication.instance().installEventFilter(self._edge_filter)

    def _build(self):
        root = QWidget(); root.setObjectName("Root"); root.setMouseTracking(True)
        self.setCentralWidget(root)
        v = QVBoxLayout(root); v.setContentsMargins(1, 1, 1, 1); v.setSpacing(0)
        self._tb = TitleBar(self); v.addWidget(self._tb)
        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        self._sb = Sidebar(); body.addWidget(self._sb)
        self._stk = QStackedWidget(); self._stk.setObjectName("ContentArea")

        self._pd  = DashboardPage()
        self._pse = SettingsPage(self._cfg, self._dev)
        self._pn  = NotificationsPage(self._cfg)
        self._pbl = BlacklistPage()
        self._pl  = LogsPage(self._dev)
        self._ppg = PluginsPage()
        self._phi = SnipeHistoryPage()

        for pg in (self._pd, self._pse, self._pn, self._pbl, self._pl, self._phi, self._ppg):
            self._stk.addWidget(pg)

        body.addWidget(self._stk); v.addLayout(body)
        self._grip = QSizeGrip(self); self._grip.setFixedSize(14, 14)

    def _connect(self):
        self._sb.page_changed.connect(self._switch_page)
        self._pd.start_requested.connect(self._start)
        self._pd.stop_requested.connect(self._stop)
        self._pd.pause_requested.connect(self._toggle_manual_pause)
        self._pd.hotkey_config_changed.connect(self._update_hotkeys)
        self._pse.config_saved.connect(self._on_cfg)
        self._pn.config_changed.connect(lambda: self._br.reload(self._cfg) if self._br else None)

        saved_hk = {
            "toggle_key": self._cfg.hotkey_toggle_key,
            "toggle_en":  self._cfg.hotkey_toggle_en,
            "pause_key":  self._cfg.hotkey_pause_key,
            "pause_en":   self._cfg.hotkey_pause_en,
            "pause_dur":  self._cfg.hotkey_pause_dur,
        }
        self._pd.set_hotkey_state(saved_hk)
        self._hotkey_cfg = saved_hk
        self._update_hotkeys(saved_hk)

    def _shortcuts(self):
        sc = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        sc.activated.connect(self._toggle_dev)

    def _on_page_changed(self, idx: int):
        if idx == 3:
            self._pbl.refresh()
        elif idx == 5:
            self._phi.refresh()
        elif idx == 6:
            self._ppg.refresh()

    def _switch_page(self, idx: int):
        """Fade-out current page, switch, fade-in new page — no position changes."""
        if self._stk.currentIndex() == idx:
            return

        current  = self._stk.currentWidget()
        DURATION = 140

        out_eff = QGraphicsOpacityEffect(current)
        current.setGraphicsEffect(out_eff)

        anim_out = QPropertyAnimation(out_eff, b"opacity", current)
        anim_out.setDuration(DURATION)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.0)
        anim_out.setEasingCurve(QEasingCurve.Type.OutQuad)

        def _do_switch():
            current.setGraphicsEffect(None)
            self._stk.setCurrentIndex(idx)
            self._on_page_changed(idx)

            new_page = self._stk.currentWidget()
            in_eff   = QGraphicsOpacityEffect(new_page)
            new_page.setGraphicsEffect(in_eff)
            in_eff.setOpacity(0.0)

            anim_in = QPropertyAnimation(in_eff, b"opacity", new_page)
            anim_in.setDuration(DURATION)
            anim_in.setStartValue(0.0)
            anim_in.setEndValue(1.0)
            anim_in.setEasingCurve(QEasingCurve.Type.OutQuad)
            anim_in.finished.connect(lambda: new_page.setGraphicsEffect(None))
            anim_in.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

        anim_out.finished.connect(_do_switch)
        anim_out.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(create_taskbar_icon(), self)
        menu = QMenu()
        menu.addAction("Show",  self.show)
        menu.addSeparator()
        menu.addAction("Quit",  self.close)
        self._tray.setContextMenu(menu)
        self._tray.show()

    def _tray_notify(self, title: str, message: str, icon=None):
        if self._tray and self._tray.isVisible():
            if icon:
                self._tray.showMessage(title, message, QIcon(QPixmap.fromImage(icon)), 3000)
            else:
                self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def _send_webhook(self, event_type: str, **kwargs):
        if not self._cfg.webhook.enabled or not self._cfg.webhook.url:
            return
        # Prefer Bridge's running loop to avoid spinning up extra threads
        if self._br and self._br._loop and self._br._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._br._send_lifecycle_webhook(event_type), self._br._loop)
            return

        async def _send():
            async with aiohttp.ClientSession() as sess:
                sender = WebhookSender(sess, self._cfg.webhook)
                await sender.send(event_type, **kwargs)

        def _run():
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_send())
            except Exception as exc:
                print(f"Webhook thread error: {exc}")
            finally:
                loop.close()

        threading.Thread(target=_run, daemon=True, name="WebhookSend").start()
            
    def _toggle_dev(self):
        self._dev = not self._dev
        self._pse.toggle_dev(self._dev); self._pl.set_dev(self._dev)
        self._cfg.dev_mode = self._dev
        e = LogEntry(LogLevel.DEBUG if self._dev else LogLevel.INFO,
                     f"[SYSTEM] DEV MODE {'ON' if self._dev else 'disabled'}")
        self._pl.append(e); self._pd.append(e, True)
        if self._br: self._br.engine.config.dev_mode = self._dev

    def _start(self):
        if not self._cfg.token:
            self._pd.show_notification("Error: Discord Token is missing. Go to Settings.", "error")
            return
        if not self._cfg.monitored_channels:
            self._pd.show_notification("Error: No monitored channels added. Go to Settings.", "error")
            return
        if not any(p.enabled for p in self._cfg.profiles):
            self._pd.show_notification(
                "Warning: No profiles enabled — sniper will listen but won't snipe.", "warning")
        if self._run:
            return

        self._br = Bridge(self._cfg)
        self._br.sig_log.connect(self._on_log)
        self._br.sig_status.connect(self._on_st)
        self._br.sig_snipe.connect(self._on_snipe)
        self._br.sig_biome.connect(self._on_biome)
        self._br.sig_ping.connect(self._on_ping)
        self._br.sig_paused.connect(self._on_engine_paused)
        self._br.sig_delete_blacklist.connect(self._on_delete_blacklist)
        self._br.start()
        self._run = True
        self._pd.on_start()

        # Wire subsystem pages to the engine's injected managers
        engine = self._br.engine
        self._pbl.set_manager(engine.blacklist, self._cfg)
        self._phi.set_history(self._br.history)
        # Sync the plugins page to the engine's loader (may differ from startup loader)
        self._ppg.set_loader(engine._plugins)
        self._startup_plugin_loader = engine._plugins
        # Give plugins access to the live UI
        if engine._plugins:
            engine._plugins.init_all(engine=engine, ui=self)

        # Explicit badge: connecting
        self._tb.badge.set_state("idle")
        self._pd.badge.set_state("idle")
        self._pd.c_status.set_value("CONNECTING")

        # Custom Notification
        self._tray_notify("Sniper Started", "Monitoring channels…", get_tray_icon_img())
        self._send_webhook("start")

        if self._is_paused: self._toggle_pause_state()

    def _stop(self, from_close: bool = False):
        was_running = bool(self._br) 
        self._run       = False
        self._is_paused = False
        self._pd.on_stop()
        self._tb.badge.set_state("off")
        self._pd.badge.set_state("off")
        self._pd.c_status.set_value("STOPPED")

        if self._br:
            br = self._br
            self._br = None
            threading.Thread(target=br.stop, daemon=True, name="StopEngine").start()

        if was_running and not from_close:
            self._send_webhook("stop")

    def _on_log(self, e: LogEntry):
        self._pl.append(e)
        if self._is_snipe_log(e):
            self._pd.append(e, self._dev)

    def _on_biome(self, expected: str, detected: str, matched: bool):
        pass

    def _on_engine_paused(self, paused: bool):
        if paused:
            self._tb.badge.set_state("idle")
            self._pd.badge.set_state("idle")
            self._pd.c_status.set_value("AUTO-PAUSED")
            self._pd.on_pause()
            e = LogEntry(LogLevel.WARN, "[ENGINE] Auto-paused after snipe.")
            self._pl.append(e); self._pd.append(e, self._dev)
        else:
            if not self._is_paused:
                self._tb.badge.set_state("on")
                self._pd.badge.set_state("on")
                self._pd.c_status.set_value("ON")
                self._pd.on_resume()
            e = LogEntry(LogLevel.INFO, "[ENGINE] Auto-pause ended — resuming scan.")
            self._pl.append(e); self._pd.append(e, self._dev)

    def _on_st(self, s: EngineStatus):
        m = {
            EngineStatus.IDLE:       "idle",
            EngineStatus.CONNECTING: "idle",
            EngineStatus.CONNECTED:  "on",
            EngineStatus.SNIPING:    "on",
            EngineStatus.ERROR:      "err",
            EngineStatus.STOPPED:    "off",
        }
        st = m.get(s, "idle")
        self._tb.badge.set_state(st)
        self._pd.badge.set_state(st)
        self._pd.c_status.set_value(st.upper())

    def _on_snipe(self, data: dict):
        n = self._br.snipe_count if self._br else 0
        self._pd.c_snipes.set_value(str(n))

        profile_name = data.get("profile", "Unknown")
        title = f"Snipped — {profile_name}"
        msg   = f"Detected in server. ({n} total)"
        self._tray_notify(title, msg, get_tray_icon_img())
        self._phi.add_entry(data)

    def _on_delete_blacklist(self, uid: str, username: str):
        """Auto-blacklist fired by engine delete-watch."""
        self._pbl.add_auto_entry(uid, username)
        e = LogEntry(LogLevel.WARN,
                     f"[BLACKLIST] Auto-blacklisted {username} ({uid}) — deleted snipe message")
        self._pl.append(e); self._pd.append(e, self._dev)

    def _on_ping(self, p: float):
        self._pd.set_ping(p)

    def _on_cfg(self, cfg: SniperConfig):
        self._cfg = cfg
        if self._br: self._br.reload(cfg)

    def _on_update_available(self, sha: str):
        self._pd.show_notification(
            f"New version detected ({sha}) — rebuilding automatically…", "warning")
        e = LogEntry(LogLevel.WARN, f"[UPDATE] New commit ({sha}) — launching build pipeline…")
        self._pl.append(e); self._pd.append(e, self._dev)
        self._stop()
        threading.Thread(target=_launch_bat_update, daemon=False, name="AutoRebuild").start()

    def _is_snipe_log(self, e: LogEntry) -> bool:
        if e.level in (LogLevel.SNIPE, LogLevel.SUCCESS, LogLevel.ERROR, LogLevel.WARN):
            return True
        return any(tag in e.message for tag in ("[SNIPER]", "[FILTER]", "[CONFIG]", "[ANTI-BAIT]"))

    def _tick(self):
        if self._br:
            if self._br.ping_ms > 0:
                self._pd.set_ping(self._br.ping_ms)
            uptime = int(self._br.uptime_seconds)
            self._pd.c_uptime.set_value(str(uptime))
            self._pd.update_engine_metrics(self._br.engine.metrics)
        try:
            from sniper_engine import ProcessManager
            self._pd.update_roblox_status(ProcessManager.is_roblox_running())
        except Exception:
            pass


    def _update_hotkeys(self, cfg: dict):
        self._hotkey_cfg = cfg
        self._cfg.hotkey_toggle_key = cfg.get("toggle_key", "")
        self._cfg.hotkey_toggle_en  = cfg.get("toggle_en", False)
        self._cfg.hotkey_pause_key  = cfg.get("pause_key", "")
        self._cfg.hotkey_pause_en   = cfg.get("pause_en", False)
        self._cfg.hotkey_pause_dur  = cfg.get("pause_dur", 60)
        self._cfg.save()

        for sc in (self._hk_toggle_shortcut, self._hk_pause_shortcut):
            if sc: sc.setEnabled(False)
        self._hk_toggle_shortcut = None
        self._hk_pause_shortcut  = None

        if cfg["toggle_en"] and cfg["toggle_key"]:
            try:
                ks = QKeySequence(cfg["toggle_key"])
                if not ks.isEmpty():
                    self._hk_toggle_shortcut = QShortcut(ks, self)
                    self._hk_toggle_shortcut.activated.connect(self._hk_toggle_action)
            except Exception:
                pass

        if cfg["pause_en"] and cfg["pause_key"]:
            try:
                ks = QKeySequence(cfg["pause_key"])
                if not ks.isEmpty():
                    self._hk_pause_shortcut = QShortcut(ks, self)
                    self._hk_pause_shortcut.activated.connect(self._hk_pause_action)
            except Exception:
                pass

    def _hk_toggle_action(self):
        if self._run: self._stop()
        else:         self._start()

    def _hk_pause_action(self):
        self._toggle_manual_pause()

    def _toggle_pause_state(self):
        self._toggle_manual_pause()

    def _toggle_manual_pause(self):
        if not self._run:
            return
        self._is_paused = not self._is_paused
        if self._is_paused:
            if self._br:
                self._br.pause()
            e = LogEntry(LogLevel.WARN, "[ENGINE] Sniper manually paused.")
            self._pl.append(e); self._pd.append(e, self._dev)
            self._tb.badge.set_state("idle")
            self._pd.badge.set_state("idle")
            self._pd.c_status.set_value("PAUSED")
            self._pd.on_pause()
        else:
            if self._br:
                self._br.resume()
            e = LogEntry(LogLevel.INFO, "[ENGINE] Sniper resumed — scanning.")
            self._pl.append(e); self._pd.append(e, self._dev)
            self._tb.badge.set_state("on")
            self._pd.badge.set_state("on")
            self._pd.c_status.set_value("ON")
            self._pd.on_resume()

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            edge = Edge.detect(e.position().toPoint(), self.width(), self.height())
            if edge != Edge.NONE:
                self._re = edge; self._rp = e.globalPosition().toPoint()
                self._rg = QRect(self.geometry()); e.accept(); return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self.isMaximized():
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor)); return
        pos = self.mapFromGlobal(e.globalPosition().toPoint())
        if not (e.buttons() & Qt.MouseButton.LeftButton):
            edge = Edge.detect(pos, self.width(), self.height())
            self.setCursor(QCursor(
                Edge.cursor(edge) if edge != Edge.NONE else Qt.CursorShape.ArrowCursor))
            return super().mouseMoveEvent(e)
        if self._re != Edge.NONE and self._rp and self._rg:
            gp = e.globalPosition().toPoint()
            dx = gp.x() - self._rp.x(); dy = gp.y() - self._rp.y()
            geo = QRect(self._rg)
            if self._re & Edge.R: geo.setRight(geo.right() + dx)
            if self._re & Edge.B: geo.setBottom(geo.bottom() + dy)
            if self._re & Edge.L: geo.setLeft(geo.left() + dx)
            if self._re & Edge.T: geo.setTop(geo.top() + dy)
            if geo.width()  < WIN_MIN_W: geo.setWidth(WIN_MIN_W)
            if geo.height() < WIN_MIN_H: geo.setHeight(WIN_MIN_H)
            self.setGeometry(geo); e.accept(); return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._re = Edge.NONE; self._rp = None; self._rg = None
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().mouseReleaseEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._sb.adapt(self.width())
        if hasattr(self, "_pd"):
            self._pd._adapt_to_size()
        if hasattr(self, "_grip"):
            self._grip.move(self.width() - 14, self.height() - 14)
        self._tb._update_max_icon()

    def closeEvent(self, e):
        self._stop(from_close=True); self._cfg.save(); e.accept()

# ENTRY POINT

def _close_other_instances():
    current_pid  = os.getpid()
    current_exe  = os.path.abspath(sys.executable if getattr(sys, "frozen", False)
                                   else os.path.abspath(__file__))
    exe_name     = Path(current_exe).name.lower()
    killed       = 0
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                if proc.pid == current_pid:
                    continue
                proc_name = (proc.info.get("name") or "").lower()
                proc_exe  = (proc.info.get("exe")  or "").lower()
                if proc_name == exe_name or Path(proc_exe).name.lower() == exe_name:
                    proc.kill()
                    proc.wait(timeout=3)
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                pass
    except Exception:
        pass
    return killed


def main():
    _close_other_instances()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Apply default theme before UI is shown
    apply_theme("dark")
    app.setStyleSheet(make_qss())

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,          QColor(C["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText,      QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Base,            QColor(C["card"]))
    pal.setColor(QPalette.ColorRole.Text,            QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Button,          QColor(C["card"]))
    pal.setColor(QPalette.ColorRole.ButtonText,      QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Highlight,       QColor("#2a2a2a"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(C["white"]))
    app.setPalette(pal)

    splash = SplashScreen()

    def _on_splash_done():
        win = MainWindow()
        win.show()

    splash.finished.connect(_on_splash_done)
    splash.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
