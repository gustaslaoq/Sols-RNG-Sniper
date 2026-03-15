from __future__ import annotations

import sys
import subprocess
import os
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
            self.close_roblox_after_join = False; self.auto_join_delay_ms = 0
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
GITHUB_REPO   = "" 
WIN_W         = 1200
WIN_H         = 800
WIN_MIN_W     = 980
WIN_MIN_H     = 600
SIDEBAR_MIN   = 70
SIDEBAR_MAX   = 260
SIDEBAR_RATIO = 0.20
SIDEBAR_SM    = 58
SIDEBAR_LG    = 220
TITLEBAR_H    = 38
RESIZE_M      = 6

def resource_path(relative_path: str) -> str:
    """Resolve path for both dev mode and PyInstaller frozen mode.
    Checks assets/ subfolder first, then falls back to current dir / _MEIPASS."""
    # When frozen by PyInstaller, _MEIPASS is the temp extraction dir
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.abspath(".")
    # Prefer assets/ subfolder next to the exe (so users can replace files)
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.abspath(".")
    assets_path = os.path.join(exe_dir, "assets", relative_path)
    if os.path.exists(assets_path):
        return assets_path
    # Fallback: bundled inside the exe via --add-data assets;assets
    bundled = os.path.join(base, "assets", relative_path)
    if os.path.exists(bundled):
        return bundled
    # Last resort: same folder
    return os.path.join(base, relative_path)

LOGO_PATH = Path(resource_path("logo.png"))
ICO_PATH  = Path(resource_path("app.ico"))


# ── Blacklist ─────────────────────────────────────────────────────────────────

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
        self.last_event = last_event or time.monotonic()
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
        return self.expires_at > 0.0 and time.monotonic() > self.expires_at


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
        exp = (time.monotonic() + eff) if eff > 0 else 0.0
        with self._lock:
            if user_id in self._entries:
                e = self._entries[user_id]
                e.count += 1; e.reason = reason
                e.last_event = time.monotonic(); e.expires_at = exp
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
        now = time.monotonic()
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


# ── Cooldown ──────────────────────────────────────────────────────────────────

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


# ── Plugin Loader ─────────────────────────────────────────────────────────────

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

    def call(self, fn_name: str, *args, **kwargs) -> Any:
        if not self.enabled or self.module is None: return None
        fn = getattr(self.module, fn_name, None)
        if not callable(fn): return None
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            print(f"[Plugin:{self.name}] Error in {fn_name}(): {exc}")
            return None


class PluginLoader:
    def __init__(self, plugins_dir: Path):
        self._dir     = plugins_dir
        self._plugins: list[PluginRecord] = []

    def discover(self) -> int:
        self._plugins.clear()
        if not self._dir.exists():
            try: self._dir.mkdir(parents=True, exist_ok=True)
            except Exception: return 0
        loaded = 0
        for py_file in sorted(self._dir.glob("*.py")):
            if py_file.name.startswith("_"): continue
            rec = self._load_file(py_file)
            if rec:
                self._plugins.append(rec); loaded += 1
        return loaded

    def _load_file(self, path: Path) -> Optional[PluginRecord]:
        mod_name = f"_plugin_{path.stem}"
        try:
            spec   = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None: return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            return PluginRecord(module, path)
        except Exception as exc:
            rec = PluginRecord.__new__(PluginRecord)
            rec.path = path; rec.module = None  # type: ignore[assignment]
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
        if rec: rec.enabled = enabled


# ── Asset Manager ─────────────────────────────────────────────────────────────

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


# ═════════════════════════════════════════════════════════════════════════════


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
        import time as _time
        now = _time.monotonic()
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
            profile_name = kwargs.get("profile", "Unknown")
            author       = kwargs.get("author",  "Unknown")
            raw_msg      = kwargs.get("raw_message", "")
            link         = kwargs.get("link", "")
            jump_url     = kwargs.get("jump_url", "")

            embed["title"] = ts_label
            desc_parts = [f"> # Snipped — {profile_name}"]
            desc_parts.append(f"**Profile:** `{profile_name}`")
            desc_parts.append(f"**Author:** `{author}`")
            desc_parts.append(f"\n**Raw message:**\n```\n{raw_msg[:1000]}\n```")
            if link:
                desc_parts.append(f"**Link:** {link}")
            embed["description"] = "\n".join(desc_parts)
            embed["color"]       = 0xFFFFFF

            if jump_url:
                components = [{
                    "type": 1,
                    "components": [{
                        "type":  2,
                        "label": "Jump to Message",
                        "style": 5,
                        "url":   jump_url,
                    }],
                }]

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
        "bg":      "#f5f5f5", "surface": "#efefef", "card":    "#ffffff",
        "card2":   "#fafafa", "border":  "#e0e0e0", "border2": "#cccccc",
        "text":    "#1a1a1a", "muted":   "#666666", "dim":     "#999999",
        "white":   "#111111", "green":   "#007744", "green2":  "#009955",
        "red":     "#c0392b", "red2":    "#e74c3c", "yellow":  "#cc9900",
        "orange":  "#cc6600", "purple":  "#7744cc", "sel":     "#e8e8e8",
        "notif_red_bg":     "rgba(180,60,60,0.10)",
        "notif_red_border": "rgba(200,80,80,0.4)",
        "notif_yellow_bg":  "rgba(180,160,60,0.10)",
        "notif_yellow_border": "rgba(200,180,80,0.4)",
    },
}

C: dict = dict(THEMES["dark"])

def apply_theme(name: str):
    """Update the global color dict C to the chosen theme."""
    palette = THEMES.get(name, THEMES["dark"])
    C.clear()
    C.update(palette)

def make_qss() -> str:
    """Generate the full application QSS from the current palette C."""
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
#WinBtn:hover {{ background-color: #1e1e1e; color: {C['white']}; }}
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
#NavBtn:hover            {{ color: #aaaaaa; background-color: transparent; }}
#NavBtn[active="true"]   {{ background-color: transparent; color: {C['white']}; padding-left: 10px; }}
#ContentArea {{ background-color: {C['surface']}; }}
#MetricCard {{
    background-color: {C['card']}; border: 1px solid {C['border']};
    border-radius: 10px; min-height: 86px; max-height: 86px;
}}
#CardLabel  {{ color: {C['muted']}; font-size: 9px; font-weight: 700; letter-spacing: 2px; }}
#CardValue  {{ color: {C['white']}; font-size: 24px; font-weight: 800; letter-spacing: -1px; }}
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
    selection-background-color: #2a2a2a;
}}
QLineEdit:focus    {{ border: 1px solid #3a3a3a; }}
QLineEdit:disabled {{ color: {C['dim']}; background-color: {C['card2']}; }}
QTextEdit {{
    background-color: {C['card']}; border: 1px solid {C['border2']};
    border-radius: 6px; padding: 9px 12px;
    color: {C['text']}; font-size: 12px;
    selection-background-color: #2a2a2a;
}}
QTextEdit:focus {{ border: 1px solid #3a3a3a; }}
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
QSpinBox:focus {{ border: 1px solid #3a3a3a; }}
QSpinBox::up-button, QSpinBox::down-button {{ background: transparent; border: none; width: 16px; }}
QSpinBox::up-arrow,  QSpinBox::down-arrow  {{ image: none; width: 0; }}
QComboBox {{
    background-color: {C['card']}; border: 1px solid {C['border2']};
    border-radius: 6px; padding: 6px 12px;
    color: {C['text']}; font-size: 12px; min-height: 18px;
}}
QComboBox:focus {{ border: 1px solid #3a3a3a; }}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {C['card']}; color: {C['text']};
    border: 1px solid {C['border2']}; selection-background-color: {C['sel']};
}}
#PrimaryBtn {{
    background-color: {C['white']}; color: #000;
    border: none; border-radius: 7px;
    padding: 9px 22px; font-size: 12px; font-weight: 700;
    min-width: 120px; min-height: 34px;
}}
#PrimaryBtn:hover    {{ background-color: #e8e8e8; }}
#PrimaryBtn:pressed  {{ background-color: #cccccc; }}
#PrimaryBtn:disabled {{ background-color: #181818; color: {C['dim']}; }}
#DangerBtn {{
    background-color: transparent; color: {C['red2']};
    border: 1px solid rgba(231,76,60,0.22); border-radius: 7px;
    padding: 9px 22px; font-size: 12px; font-weight: 600;
    min-width: 120px; min-height: 34px;
}}
#DangerBtn:hover {{
    background-color: rgba(231,76,60,0.06);
    border: 1px solid rgba(231,76,60,0.5);
}}
#PauseBtn {{
    background-color: transparent; color: {C['yellow']};
    border: 1px solid rgba(255,204,0,0.22); border-radius: 7px;
    padding: 9px 22px; font-size: 12px; font-weight: 600;
    min-width: 120px; min-height: 34px;
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
#SmallBtn:hover {{ color: {C['text']}; border: 1px solid {C['border2']}; background-color: #181818; }}
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
#HDivider {{ background-color: {C['border']}; max-height: 1px; }}
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
    "home":     '<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/>',
    "logs":     '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>',
    "bell":     '<path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/>',
    "play":     '<polygon points="5 3 19 12 5 21 5 3"/>',
    "stop":     '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>',
    "pause":    '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>',
    "minimize": '<line x1="5" y1="12" x2="19" y2="12"/>',
    "maximize": '<rect x="3" y="3" width="18" height="18" rx="2"/>',
    "restore":  '<path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/>',
    "close":    '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "help":     '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "chevron-left":  '<polyline points="15 18 9 12 15 6"/>',
    "chevron-right": '<polyline points="9 18 15 12 9 6"/>',
    "trash":    '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/>',
    "lock":     '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>',
    "check":    '<polyline points="20 6 9 17 4 12"/>',
    "info":     '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    "zap":      '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "webhook":  '<path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
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
    pt.setPen(Qt.PenStyle.NoPen)
    pt.drawRoundedRect(QRect(0, 0, sz, sz), radius, radius)
    ox = (sz - logo_s.width())  // 2
    oy = (sz - logo_s.height()) // 2
    pt.drawPixmap(ox, oy, logo_s)
    pt.end()
    return QIcon(bg)

def get_tray_icon_img() -> QImage:
    """Returns the logo as a QImage for system tray notifications."""
    if LOGO_PATH.exists():
        return QImage(str(LOGO_PATH)).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return QImage()

def lbl(text: str, obj: str = "", css: str = "") -> QLabel:
    w = QLabel(text)
    if obj: w.setObjectName(obj)
    if css: w.setStyleSheet(css)
    return w

def hdiv() -> QFrame:
    d = QFrame()
    d.setObjectName("HDivider")
    d.setFrameShape(QFrame.Shape.HLine)
    return d

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
    sig_log    = Signal(object)
    sig_status = Signal(object)
    sig_snipe  = Signal(dict)
    sig_biome  = Signal(str, str, bool)
    sig_ping   = Signal(float)
    sig_paused = Signal(bool)

    def __init__(self, cfg: SniperConfig):
        super().__init__()

        # ── Build subsystem managers ──────────────────────────────────────
        app_dir = _get_app_dir()

        bl = BlacklistManager(app_dir / "blacklist.json")

        cd_cfg = CooldownConfig(
            guild_ttl   = getattr(cfg, "cooldown_guild_ttl",   30.0),
            profile_ttl = getattr(cfg, "cooldown_profile_ttl",  0.0),
            link_ttl    = getattr(cfg, "cooldown_link_ttl",    10.0),
        )
        cd = CooldownManager(cd_cfg)

        # Plugins folder must be next to the .exe, not relative to CWD.
        # When frozen by PyInstaller sys.executable is the .exe path.
        # When running as a script it falls back to the script's directory.
        if getattr(sys, "frozen", False):
            _base_dir = Path(os.path.dirname(sys.executable))
        else:
            _base_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        plugins_dir = _base_dir / "plugins"

        pl = PluginLoader(plugins_dir)
        pl.discover()

        # ── Build engine with injected managers ───────────────────────────
        self.engine = SniperEngine(cfg, blacklist=bl, cooldown=cd, plugins=pl)

        self._thread: Optional[threading.Thread]          = None
        self._loop:   Optional[asyncio.AbstractEventLoop] = None

        self.engine.on_log         = self.sig_log.emit
        self.engine.on_status      = self.sig_status.emit
        self.engine.on_snipe       = self.sig_snipe.emit
        self.engine.on_biome       = self.sig_biome.emit
        self.engine.on_ping_update = self.sig_ping.emit
        self.engine.on_paused      = self.sig_paused.emit

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
            future = asyncio.run_coroutine_threadsafe(self.engine.stop(), self._loop)
            try:
                future.result(timeout=5.0)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5.0)

    def reload(self, cfg: SniperConfig):
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
        if bar.minimum() == bar.maximum() or (delta > 0 and at_top) or (delta < 0 and at_bottom):
            e.ignore()
        else:
            super().wheelEvent(e)


class SmoothScrollArea(QScrollArea):
    def wheelEvent(self, e):
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() - int(e.angleDelta().y() / 120 * 30))
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


class ChannelRow(QFrame):
    delete_requested = Signal()
    changed          = Signal()

    def __init__(self, ch: "ChannelConfig", parent=None):
        super().__init__(parent)
        self.setObjectName("ChannelRow")
        self._ch = ch
        self.setMouseTracking(True)
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7); lay.setSpacing(10)

        self._toggle = ToggleSwitch(self._ch.enabled)
        self._toggle.toggled.connect(self._on_toggle)
        lay.addWidget(self._toggle)

        info = QVBoxLayout(); info.setSpacing(1)
        col  = C["text"] if self._ch.enabled else C["muted"]
        self._name_lbl = QLabel(self._ch.name or "Unnamed")
        self._name_lbl.setStyleSheet(
            f"color: {col}; font-weight: 600; font-size: 12px; background: transparent;")
        self._id_lbl = QLabel(f"{self._ch.guild_id} / #{self._ch.channel_id}")
        self._id_lbl.setStyleSheet(
            f"color: {C['muted']}; font-size: 10px; background: transparent;")
        info.addWidget(self._name_lbl); info.addWidget(self._id_lbl)
        lay.addLayout(info); lay.addStretch()

        self._del_btn = QPushButton()
        self._del_btn.setObjectName("ChDeleteBtn")
        self._del_btn.setIcon(_svg_icon("trash", C["red2"], 14))
        self._del_btn.setIconSize(QSize(14, 14))
        self._del_btn.setFixedSize(28, 28)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setVisible(False)
        self._del_btn.clicked.connect(self.delete_requested.emit)
        lay.addWidget(self._del_btn)

    def _on_toggle(self, v: bool):
        self._ch.enabled = v
        col = C["text"] if v else C["muted"]
        self._name_lbl.setStyleSheet(
            f"color: {col}; font-weight: 600; font-size: 12px; background: transparent;")
        self.changed.emit()

    def refresh(self):
        self._toggle.blockSignals(True)
        self._toggle.setChecked(self._ch.enabled)
        self._toggle.blockSignals(False)
        col = C["text"] if self._ch.enabled else C["muted"]
        self._name_lbl.setText(self._ch.name or "Unnamed")
        self._name_lbl.setStyleSheet(
            f"color: {col}; font-weight: 600; font-size: 12px; background: transparent;")

    def enterEvent(self, e):  self._del_btn.setVisible(True);  super().enterEvent(e)
    def leaveEvent(self, e):  self._del_btn.setVisible(False); super().leaveEvent(e)


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
    def __init__(self, label: str, value: str = "—", unit: str = ""):
        super().__init__()
        self.setObjectName("MetricCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 10, 16, 10); lay.setSpacing(3)
        self._v = lbl(value, "CardValue")
        lay.addWidget(lbl(label.upper(), "CardLabel"))
        row = QHBoxLayout(); row.setSpacing(5)
        row.addWidget(self._v)
        row.addWidget(lbl(unit, "CardUnit"), alignment=Qt.AlignmentFlag.AlignBottom)
        row.addStretch()
        lay.addLayout(row)

    def set_value(self, v: str):
        self._v.setText(v)


class NavButton(QPushButton):
    def __init__(self, key: str, text: str):
        super().__init__()
        self.setObjectName("NavBtn")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setProperty("active", False)
        self._text = text
        self._ic   = _svg_icon(key)
        self._wide = False
        self._apply()
        self.set_style(font_size=11, icon_size=18)

    def set_active(self, v: bool):
        self.setProperty("active", v)
        self.style().unpolish(self); self.style().polish(self)

    def show_text(self, wide: bool):
        if wide != self._wide:
            self._wide = wide; self._apply()

    def set_style(self, font_size: int, icon_size: int):
        self.setIcon(self._ic); self.setIconSize(QSize(icon_size, icon_size))
        self.setStyleSheet(f"font-size: {font_size}px; font-weight: 800;")

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
        self._value = 0.0
        self._total = 1
        self.setFixedHeight(4)
        self.setStyleSheet("background: transparent;")

    def set_progress(self, value: float, total: int):
        self._value  = value
        self._total  = total
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        filled = int(w * min(self._value, self._total) / max(1, self._total))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#1c1c1c"))
        p.drawRoundedRect(0, 0, w, 4, 2, 2)
        if filled > 0:
            p.setBrush(QColor("#ffffff"))
            p.drawRoundedRect(0, 0, filled, 4, 2, 2)
        p.end()


class SplashScreen(QWidget):
    finished       = Signal()
    _update_result = Signal(bool, str)

    _TASKS = [
        "Initializing runtime environment…",
        "Checking for updates…",
        "Loading profiles and configuration…",
        "Preparing snipe engine…",
        "Ready.",
    ]

    _HERO_H     = 118
    _HERO_Y     = 68
    _SLIDE_DIST = 28
    _BOTTOM_Y   = 232

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(420, 280)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center().x() - 210, screen.center().y() - 140)

        self._opacity      = 0.0
        self._hero_t       = 0.0
        self._bottom_alpha = 0.0
        self._bar_value    = 0.0
        self._bar_target   = 0.0
        self._task_idx     = 0
        self._hero_done    = False

        self._update_result.connect(self._on_check_done)
        self._build()

    def _build(self):
        self._root = QWidget(self)
        self._root.setObjectName("SplashRoot")
        self._root.setGeometry(0, 0, 420, 280)
        self._root.setStyleSheet(
            "QWidget#SplashRoot{"
            "background-color:#000000;"
            "border:1px solid #1c1c1c;"
            "border-radius:16px;}")

        pad     = 40
        inner_w = 420 - pad * 2

        self._hero_w = QWidget(self._root)
        self._hero_w.setGeometry(pad, self._HERO_Y + self._SLIDE_DIST, inner_w, self._HERO_H)
        self._hero_w.setStyleSheet("background:transparent;")
        hl = QVBoxLayout(self._hero_w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)
        hl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        self._logo_lbl = QLabel()
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_lbl.setFixedSize(64, 64)
        self._logo_lbl.setStyleSheet("background:transparent;")
        if LOGO_PATH.exists():
            px = QPixmap(str(LOGO_PATH)).scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._logo_lbl.setPixmap(px)
        hl.addWidget(self._logo_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        self._name_lbl = QLabel(APP_NAME)
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_lbl.setStyleSheet(
            "color:#ffffff;font-size:11px;font-weight:700;"
            "letter-spacing:3px;background:transparent;")
        hl.addWidget(self._name_lbl)

        self._ver_lbl = QLabel(f"v{APP_VERSION}")
        self._ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ver_lbl.setStyleSheet(
            "color:#555555;font-size:10px;letter-spacing:1px;background:transparent;")
        hl.addWidget(self._ver_lbl)

        self._bottom_w = QWidget(self._root)
        self._bottom_w.setGeometry(pad, self._BOTTOM_Y, inner_w, 32)
        self._bottom_w.setStyleSheet("background:transparent;")
        bl = QVBoxLayout(self._bottom_w)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(7)

        self._bar_w = _SplashBarWidget()
        bl.addWidget(self._bar_w)

        self._task_lbl = QLabel(self._TASKS[0])
        self._task_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._task_lbl.setStyleSheet("color:#555555;font-size:10px;background:transparent;")
        bl.addWidget(self._task_lbl)

        self._bottom_eff = QGraphicsOpacityEffect(self._bottom_w)
        self._bottom_eff.setOpacity(0.0)
        self._bottom_w.setGraphicsEffect(self._bottom_eff)

        self._master_timer = QTimer(self)
        self._master_timer.setInterval(16)
        self._master_timer.timeout.connect(self._tick)

        self._step_timer = QTimer(self)
        self._step_timer.setInterval(560)
        self._step_timer.timeout.connect(self._step)

    def start(self):
        self.setWindowOpacity(0.0)
        self.show()
        self._master_timer.start()

    def _tick(self):
        if self._opacity < 1.0:
            self._opacity = min(1.0, self._opacity + 0.065)
            self.setWindowOpacity(self._opacity)

        if self._hero_t < 1.0:
            self._hero_t = min(1.0, self._hero_t + 0.055)
            ease   = 1.0 - self._hero_t
            offset = int(self._SLIDE_DIST * (ease ** 2))
            self._hero_w.move(40, self._HERO_Y + offset)
            if self._hero_t >= 1.0:
                self._hero_w.move(40, self._HERO_Y)
                self._hero_done = True
                self._step_timer.start()

        if self._hero_done and self._bottom_alpha < 1.0:
            self._bottom_alpha = min(1.0, self._bottom_alpha + 0.055)
            self._bottom_eff.setOpacity(self._bottom_alpha)

        if self._hero_done:
            diff = self._bar_target - self._bar_value
            if abs(diff) > 0.003:
                self._bar_value += diff * 0.10
                self._bar_w.set_progress(self._bar_value, len(self._TASKS))

    def _step(self):
        self._task_idx += 1
        self._bar_target = float(self._task_idx)

        if self._task_idx < len(self._TASKS):
            self._task_lbl.setText(self._TASKS[self._task_idx])

        if self._task_idx == 1:
            self._step_timer.stop()
            self._launch_update_check()
            return

        if self._task_idx >= len(self._TASKS):
            self._step_timer.stop()
            QTimer.singleShot(600, self._begin_fade_out)

    def _launch_update_check(self):
        sig = self._update_result

        def _worker():
            found   = False
            new_sha = ""
            if GITHUB_REPO:
                try:
                    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "SniperApp/SplashCheck"})
                    with urllib.request.urlopen(req, timeout=7) as resp:
                        data = json.loads(resp.read())
                    new_sha   = data.get("sha", "")[:7]
                    built_sha = getattr(AutoUpdater, "_BUILT_SHA", "")
                    is_frozen = getattr(sys, "frozen", False)
                    if new_sha and (not is_frozen or new_sha != built_sha):
                        found = True
                except Exception:
                    pass
            sig.emit(found, new_sha)

        threading.Thread(target=_worker, daemon=True, name="SplashUpdateCheck").start()

    def _on_check_done(self, found: bool, sha: str):
        if found:
            self._task_lbl.setText(f"Update available (commit {sha}) — install now?")
            self._bar_target = float(len(self._TASKS))
            self._show_update_prompt(sha)
        else:
            self._step_timer.start()
            self._step()

    def _show_update_prompt(self, sha: str):
        msg = QMessageBox(self)
        msg.setWindowTitle("Update Available")
        msg.setText(
            f"A new version is available (commit {sha}).\n\n"
            "The app will rebuild from source and restart automatically.\n\n"
            "Update now?")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if msg.exec() == QMessageBox.StandardButton.Yes:
            self._task_lbl.setText("Rebuilding executable — please wait…")
            updater = AutoUpdater()
            threading.Thread(
                target=updater.rebuild_and_restart,
                daemon=True, name="SplashRebuild").start()
            QTimer.singleShot(2500, self._begin_fade_out)
        else:
            self._task_lbl.setText("Update skipped — continuing…")
            self._bar_target = 0.0
            self._bar_value  = 0.0
            self._task_idx   = 1
            self._step_timer.start()
            self._step()

    def _begin_fade_out(self):
        self._step_timer.stop()
        self._fade_out_timer = QTimer(self)
        self._fade_out_timer.setInterval(16)
        self._fade_out_timer.timeout.connect(self._tick_fade_out)
        self._fade_out_timer.start()

    def _tick_fade_out(self):
        self._opacity = max(0.0, self._opacity - 0.085)
        self.setWindowOpacity(self._opacity)
        if self._opacity <= 0.0:
            self._fade_out_timer.stop()
            self._master_timer.stop()
            self._step_timer.stop()
            self.close()
            self.finished.emit()

# AUTO-UPDATER

class AutoUpdater(QObject):
    """
    Checks GitHub for new commits on the main branch.
    When an update is found:
      1. Downloads the latest build.bat from the repo
      2. Replaces the local build.bat (if one exists next to the .exe)
      3. Runs build.bat --update <exe_path> which rebuilds and restarts the app

    Works from both frozen .exe (has _BUILT_SHA) and dev source (always checks).
    """
    update_available = Signal(str)   # emits latest commit SHA

    _RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"

    def __init__(self, parent=None):
        super().__init__(parent)
        # Embedded at build time by build.bat stamping step
        self._built_sha: str = getattr(self, "_BUILT_SHA", "")

    @property
    def _is_frozen(self) -> bool:
        return getattr(sys, "frozen", False)

    @property
    def _exe_dir(self) -> Path:
        if self._is_frozen:
            return Path(os.path.dirname(sys.executable))
        return Path(os.path.dirname(os.path.abspath(__file__)))

    def check_async(self):
        if not GITHUB_REPO:
            return
        threading.Thread(target=self._check, daemon=True, name="AutoUpdate").start()

    def _check(self):
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
            req = urllib.request.Request(url, headers={"User-Agent": "SniperApp/AutoUpdater"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            latest_sha = data.get("sha", "")[:7]
            if not latest_sha:
                return
            if self._is_frozen and latest_sha == self._built_sha:
                return
            self.update_available.emit(latest_sha)
        except Exception:
            pass

    def rebuild_and_restart(self):
        """
        1. Download latest build.bat from GitHub
        2. Update local build.bat next to the exe
        3. Run it with --update flag to rebuild and restart
        """
        if not GITHUB_REPO:
            return
        try:
            # Download latest build.bat
            bat_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/build.bat"
            req = urllib.request.Request(bat_url, headers={"User-Agent": "SniperApp/AutoUpdater"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                bat_bytes = resp.read()

            # Always write CRLF (Windows requirement)
            bat_text = bat_bytes.decode("utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")
            bat_crlf = bat_text.replace("\n", "\r\n").encode("utf-8")

            # 1. Update the local build.bat next to the exe (so future manual runs are fresh)
            local_bat = self._exe_dir / "build.bat"
            try:
                local_bat.write_bytes(bat_crlf)
            except Exception:
                pass  # Not critical if we can't update it

            # 2. Write to temp for execution
            temp_dir = Path(os.getenv("TEMP", str(self._exe_dir))) / "SniperUpdate"
            temp_dir.mkdir(parents=True, exist_ok=True)
            run_bat = temp_dir / "update.bat"
            run_bat.write_bytes(bat_crlf)

            current_exe = str(sys.executable)
            subprocess.Popen(
                ["cmd.exe", "/c", str(run_bat), "--update", current_exe],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            QApplication.instance().quit()
            sys.exit(0)
        except Exception as exc:
            print(f"[AutoUpdater] rebuild_and_restart failed: {exc}")

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
    ("logs",     "Logs"),
    ("bell",     "Notifications"),
    ("lock",     "Blacklist"),
    ("zap",      "Plugins"),
]


class Sidebar(QFrame):
    page_changed = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        # COMEÇA EXPANDIDO (SIDEBAR_LG)
        self.setFixedWidth(SIDEBAR_LG)
        self.setMouseTracking(True)

        self._anim_y:     float = -1.0   # hover background y
        self._target_y:   float = -1.0
        self._anim_h:     int   = 32
        self._active_idx: int   = 0
        # Animated white indicator (click, not hover)
        self._act_anim_y: float = -1.0   # white bar y
        self._act_target_y: float = -1.0
        self._act_anim_h: int   = 32
        # ESTADO INICIAL: EXPANDIDO (False = não colapsado)
        self._collapsed:  bool  = False

        self._ind_timer = QTimer(self)
        self._ind_timer.setInterval(12)
        self._ind_timer.timeout.connect(self._tick_indicator)

        self._act_timer = QTimer(self)
        self._act_timer.setInterval(12)
        self._act_timer.timeout.connect(self._tick_act_indicator)

        # --- Layout Principal ---
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 14, 8, 14) 
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- Área da Logo ---
        self._logo = QLabel()
        self._logo.setObjectName("SidebarLogo")
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Tamanho inicial compatível com sidebar expandida
        self._logo.setFixedSize(64, 64) 

        lc = QVBoxLayout()
        lc.setContentsMargins(0, 0, 0, 0)
        lc.setSpacing(4)
        lc.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lc.addWidget(self._logo, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Textos (visíveis no início pois está expandido)
        self._ln = lbl("SLAOQ'S", "SidebarName")
        self._ln.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ls = lbl("Sol's RNG SNIPER", "SidebarSub")
        self._ls.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ln.setVisible(True) # Visível inicialmente
        self._ls.setVisible(True) # Visível inicialmente
        lc.addWidget(self._ln)
        lc.addWidget(self._ls)
        
        lay.addLayout(lc)
        lay.addSpacing(12)
        lay.addWidget(hdiv())
        lay.addSpacing(12)

        # --- Botões de Navegação ---
        self._btns: list[NavButton] = []
        for i, (k, t) in enumerate(_PAGES):
            b = NavButton(k, t)
            b.clicked.connect(lambda _, ix=i: self._sel(ix))
            b.installEventFilter(self)
            self._btns.append(b)
            lay.addWidget(b, alignment=Qt.AlignmentFlag.AlignHCenter)
            lay.addSpacing(2)

        lay.addStretch()

        # --- Botão de Recolher/Expandir ---
        self._toggle_btn = QPushButton()
        self._toggle_btn.setObjectName("GhostBtn")
        # ÍNCONA INICIAL: Como está expandido, mostra seta para ESQUERDA (para poder recolher)
        self._toggle_btn.setIcon(_svg_icon("chevron-left", C["dim"], 14))
        self._toggle_btn.setIconSize(QSize(14, 14))
        self._toggle_btn.setFixedSize(32, 32)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_collapse)
        # Alinhado à direita
        lay.addWidget(self._toggle_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # Inicializa o primeiro botão (Home) e carrega a logo
        self._sel(0)
        self._load_logo()
        
        # Animações
        self._width_anim = QPropertyAnimation(self, b"minimumWidth")
        self._width_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._width_anim.setDuration(220)
        # Conectar o fim da animação para corrigir a posição do indicador
        self._width_anim.finished.connect(self._on_anim_finished)

    def _on_anim_finished(self):
        """Snap both indicators to the active button after sidebar resize."""
        self._move_indicator_to(self._active_idx)
        self._move_act_indicator_to(self._active_idx)

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

        # Lógica do ícone corrigida
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
            if event.type() == QEvent.Type.HoverEnter:
                QApplication.restoreOverrideCursor()
                QApplication.setOverrideCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                self._move_indicator_to(self._btns.index(obj))
            elif event.type() == QEvent.Type.HoverLeave:
                QApplication.restoreOverrideCursor()
                self._move_indicator_to(self._active_idx)
        return False

    def _move_indicator_to(self, idx: int):
        if idx < 0 or idx >= len(self._btns): return
        btn = self._btns[idx]
        self._anim_h = btn.height()
        # Pega a posição REAL do botão
        self._target_y = float(btn.mapTo(self, QPoint(0, 0)).y())
        if self._anim_y < 0:
            self._anim_y = self._target_y
        self._ind_timer.start()

    def _tick_act_indicator(self):
        diff = self._act_target_y - self._act_anim_y
        if abs(diff) < 0.5:
            self._act_anim_y = self._act_target_y
            self._act_timer.stop()
        else:
            self._act_anim_y += diff * 0.22
        self.update()

    def _tick_indicator(self):
        diff = self._target_y - self._anim_y
        if abs(diff) < 0.5:
            self._anim_y = self._target_y
            self._ind_timer.stop()
        else:
            self._anim_y += diff * 0.22
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Animated hover background
        if self._anim_y >= 0:
            p.setBrush(QColor("#0e0e0e"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(4, int(self._anim_y), self.width() - 8, self._anim_h, 6, 6)

        # Animated white bar — follows click, not hover
        if self._act_anim_y >= 0:
            p.setBrush(QColor(C["white"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(4, int(self._act_anim_y) + 4, 2, self._act_anim_h - 8, 1, 1)

        p.end()

    def _move_act_indicator_to(self, idx: int):
        """Animate the white click-bar to button idx."""
        if idx < 0 or idx >= len(self._btns):
            return
        btn = self._btns[idx]
        self._act_anim_h   = btn.height()
        self._act_target_y = float(btn.mapTo(self, QPoint(0, 0)).y())
        if self._act_anim_y < 0:
            self._act_anim_y = self._act_target_y
        self._act_timer.start()

    def _sel(self, idx: int):
        self._active_idx = idx
        for i, b in enumerate(self._btns):
            b.set_active(i == idx)
        self._move_indicator_to(idx)       # hover bg snaps to new active
        self._move_act_indicator_to(idx)   # white bar animates smoothly
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
        # Keep label exactly as big as the scaled image so nothing gets clipped
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

        # Header
        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(3)
        col.addWidget(lbl("Dashboard", "PageTitle"))
        col.addWidget(lbl("Control & Monitor", "PageSub"))
        hdr.addLayout(col); hdr.addStretch()
        self.badge = StatusBadge("idle"); hdr.addWidget(self.badge)
        lay.addLayout(hdr); lay.addWidget(hdiv())

        # ── Compact 2×3 metrics grid ──────────────────────────────────────────
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

        # Control buttons
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

        br.addWidget(self._s); br.addWidget(self._e); br.addWidget(self._p); br.addStretch()
        lay.addLayout(br)

        # Recent activity log
        lay.addWidget(lbl("RECENT ACTIVITY", "SecTitle"))
        self.mini = QTextEdit(); self.mini.setObjectName("LogConsole")
        self.mini.setReadOnly(True)
        self.mini.setPlaceholderText("Waiting for connection…")
        lay.addWidget(self.mini, 1)

        # Hotkey configuration card
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

        # In-app notification bar
        self._notif_frame = QFrame(); self._notif_frame.setObjectName("NotifFrame")
        self._notif_frame.setFixedHeight(40); self._notif_frame.setVisible(False)

        self._notif_timer = QTimer(self)
        self._notif_timer.setSingleShot(True); self._notif_timer.setInterval(4000)
        self._notif_timer.timeout.connect(lambda: self._notif_frame.setVisible(False))

        notif_lay = QHBoxLayout(self._notif_frame)
        notif_lay.setContentsMargins(15, 0, 15, 0)
        self._notif_lbl = lbl("")
        self._notif_lbl.setWordWrap(True)
        notif_lay.addWidget(self._notif_lbl); notif_lay.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(lambda: self._notif_frame.setVisible(False))
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {C['muted']}; border: none; font-size: 16px; }}"
            f"QPushButton:hover {{ color: {C['white']}; }}")
        notif_lay.addWidget(close_btn)
        lay.addWidget(self._notif_frame)

        # Connect hotkey signals
        self._tg_key.keySequenceChanged.connect(self._emit_config)
        self._tg_chk.toggled.connect(self._emit_config)
        self._ps_key.keySequenceChanged.connect(self._emit_config)
        self._ps_chk.toggled.connect(self._emit_config)
        self._ps_dur.valueChanged.connect(self._emit_config)

    def update_engine_metrics(self, metrics: dict):
        """Called by the timer tick to sync engine metrics into the grid cards."""
        msgs = metrics.get("messages_scanned", 0)
        self.c_messages.set_value(str(msgs))

    def update_roblox_status(self, running: bool):
        """Update the Roblox card — called from the tick timer."""
        self.c_roblox.set_value("RUNNING" if running else "CLOSED")

    def show_notification(self, text: str, level: str = "error"):
        self._notif_lbl.setText(text)
        if level == "error":
            color  = "#ff8a80"
            bg     = C["notif_red_bg"]
            border = C["notif_red_border"]
        else:
            color  = "#ffd480"
            bg     = C["notif_yellow_bg"]
            border = C["notif_yellow_border"]
        self._notif_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px;")
        self._notif_frame.setStyleSheet(
            f"#NotifFrame {{ background-color: {bg}; border: 1px solid {border}; border-radius: 8px; }}")
        self._notif_frame.setVisible(True)
        self._notif_timer.start()

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
        clr = {
            LogLevel.SUCCESS: C["green2"], LogLevel.ERROR:  C["red2"],
            LogLevel.WARN:    C["yellow"], LogLevel.DEBUG:  C["purple"],
            LogLevel.SNIPE:   C["orange"],
        }.get(e.level, C["green"])
        html = (f'<span style="color:{C["dim"]}">[{e.ts}]</span> '
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

        biome_hdr = QHBoxLayout()
        self._lbl_biome = lbl("Expected Biome Name:", "FieldLbl")
        biome_hdr.addWidget(self._lbl_biome)
        biome_hdr.addWidget(HelpIcon(
            "Exact biome name (e.g., GLITCHED).\n"
            "Leave empty for items/events with no biome check."))
        biome_hdr.addStretch()
        fl.addLayout(biome_hdr)

        self._inp_biome = QLineEdit()
        self._inp_biome.setPlaceholderText("Leave empty for Items/Merchant")
        self._inp_biome.textChanged.connect(self._on_biome)
        fl.addWidget(self._inp_biome)

        kill_row = QHBoxLayout()
        zap_lbl  = QLabel()
        zap_lbl.setPixmap(_svg_icon("zap", C["yellow"], 13).pixmap(13, 13))
        zap_lbl.setFixedSize(18, 18); zap_lbl.setStyleSheet("background: transparent;")
        self._lbl_kill_note = lbl("Auto-kill Roblox on wrong biome", "FieldHint")
        kill_row.addWidget(zap_lbl); kill_row.addWidget(self._lbl_kill_note); kill_row.addStretch()
        self._lbl_kill_auto = QWidget(); self._lbl_kill_auto.setLayout(kill_row)
        fl.addWidget(self._lbl_kill_auto)

        rx_hdr = QHBoxLayout()
        self._chk_rx = QCheckBox("Use Regex")
        self._chk_rx.toggled.connect(self._on_regex)
        rx_hdr.addWidget(self._chk_rx)
        rx_hdr.addWidget(HelpIcon("Enable for advanced patterns (e.g., multiple biomes)."))
        rx_hdr.addStretch()
        fl.addLayout(rx_hdr)

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

        for w in (self._chk_enabled, self._chk_rx, self._inp_biome):
            w.blockSignals(True)

        self._placeholder.setVisible(False); self._form.setVisible(True)
        self._lbl_name.setText(p.name)
        self._lbl_locked_wrap.setVisible(is_global)
        self._chk_enabled.setChecked(p.enabled)
        self._inp_biome.setText(p.verify_biome_name)
        self._chk_rx.setChecked(p.use_regex)
        self._update_biome_deps(p.verify_biome_name)

        for w in (self._chk_enabled, self._chk_rx, self._inp_biome):
            w.blockSignals(False)

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
    config_saved = Signal(object)

    def __init__(self, cfg: SniperConfig, dev: bool = False):
        super().__init__()
        self._cfg = cfg; self._dev = dev
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(700)
        self._autosave_timer.timeout.connect(self._save)
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
        lay.addWidget(lbl("Channels where the bot listens.", "FieldHint"))
        row = QHBoxLayout()

        g_v = QVBoxLayout(); g_h = QHBoxLayout()
        g_h.addWidget(lbl("Guild ID", "FieldLbl"))
        g_h.addWidget(HelpIcon("Right-click server icon → Copy ID (Developer Mode required)."))
        g_h.addStretch(); g_v.addLayout(g_h)
        self._cg = QLineEdit(); self._cg.setPlaceholderText("123456789…")
        g_v.addWidget(self._cg); row.addLayout(g_v)

        c_v = QVBoxLayout(); c_h = QHBoxLayout()
        c_h.addWidget(lbl("Channel ID", "FieldLbl"))
        c_h.addWidget(HelpIcon("Right-click channel name → Copy ID."))
        c_h.addStretch(); c_v.addLayout(c_h)
        self._cc = QLineEdit(); self._cc.setPlaceholderText("987654321…")
        c_v.addWidget(self._cc); row.addLayout(c_v)

        n_v = QVBoxLayout()
        n_v.addWidget(lbl("Name (Optional)", "FieldLbl"))
        self._cn = QLineEdit(); self._cn.setPlaceholderText("Snipe Server 1")
        n_v.addWidget(self._cn); row.addLayout(n_v)
        lay.addLayout(row)

        ab = QPushButton("+ Add Channel"); ab.setObjectName("SmallBtn")
        ab.clicked.connect(self._add_ch)
        lay.addWidget(ab, alignment=Qt.AlignmentFlag.AlignLeft)

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

        # Priority reorder buttons
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
        # Swap in config list (keep Global locked at index 0)
        p = self._cfg.profiles
        if p[row - 1].locked:
            return
        p[row - 1], p[row] = p[row], p[row - 1]
        # Update priority values to reflect order
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
        self._chk_close.setChecked(self._cfg.close_roblox_after_join); lay.addWidget(self._chk_close)

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
        for w in (self._chk_aj, self._chk_close, self._chk_ab, self._chk_lf):
            w.toggled.connect(self._schedule_save)
        for w in (self._spn, self._spn_tail, self._spn_pause):
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
        g  = self._cg.text().strip(); ch = self._cc.text().strip()
        n  = self._cn.text().strip() or "Unnamed"
        if g and ch:
            self._cfg.monitored_channels.append(ChannelConfig(g, ch, n))
            self._refresh_ch()
            for w in (self._cg, self._cc, self._cn): w.clear()
            self._schedule_save()

    def _del_ch_at(self, idx: int):
        if 0 <= idx < len(self._cfg.monitored_channels):
            self._cfg.monitored_channels.pop(idx)
            self._refresh_ch(); self._schedule_save()

    def _refresh_ch(self):
        for row in self._ch_rows:
            self._ch_vlay.removeWidget(row); row.deleteLater()
        self._ch_rows.clear()

        for i, ch in enumerate(self._cfg.monitored_channels):
            row = ChannelRow(ch)
            row.changed.connect(self._schedule_save)
            row.delete_requested.connect(lambda _i=i: self._del_ch_at(_i))
            self._ch_vlay.addWidget(row); self._ch_rows.append(row)

        if not self._cfg.monitored_channels:
            empty = QLabel("  No channels added yet.")
            empty.setStyleSheet(f"color: {C['dim']}; font-size: 11px; padding: 14px;")
            self._ch_vlay.addWidget(empty)
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
        self._cfg.close_roblox_after_join = self._chk_close.isChecked()
        self._cfg.auto_join_delay_ms      = self._spn.value()
        self._cfg.pause_after_snipe_s     = self._spn_pause.value()
        self._cfg.anti_bait_enabled       = self._chk_ab.isChecked()
        # Cooldown TTLs
        self._cfg.cooldown_guild_ttl      = float(self._spn_cd_guild.value())
        self._cfg.cooldown_profile_ttl    = float(self._spn_cd_profile.value())
        self._cfg.cooldown_link_ttl       = float(self._spn_cd_link.value())
        if self._dev:
            self._cfg.log_to_file    = self._chk_lf.isChecked()
            self._cfg.log_tail_bytes = self._spn_tail.value()
        self._cfg.ensure_global()
        # Sync profile priorities before save so they persist
        self._sync_profile_priorities()
        for p in self._cfg.profiles: p.compile()
        self._cfg.save()
        self._set_save_status("saved")
        self.config_saved.emit(self._cfg)

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

        # Level filter
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

        # Buffer for filtered replay
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
        clr, tag = {
            LogLevel.INFO:    (C["green"],  "INF"),
            LogLevel.SUCCESS: (C["green2"], "OK "),
            LogLevel.WARN:    (C["yellow"], "WRN"),
            LogLevel.ERROR:   (C["red2"],   "ERR"),
            LogLevel.DEBUG:   (C["purple"], "DBG"),
            LogLevel.SNIPE:   (C["orange"], "SNP"),
        }.get(e.level, (C["green"], "   "))
        html = (f'<span style="color:{C["dim"]}">[{e.ts}]</span> '
                f'<span style="color:{clr};font-weight:bold">[{tag}]</span> '
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

# ─────────────────────────────────────────────────────────────────────────────
# PAGE: BLACKLIST
# ─────────────────────────────────────────────────────────────────────────────

class BlacklistPage(QWidget):
    """
    Manages the user blacklist — shows all blacklisted Discord users,
    lets the operator remove entries, and displays offense counts.
    Requires core.blacklist.BlacklistManager (optional dependency).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = None   # set via set_manager()
        self._build()

    def set_manager(self, manager):
        """Inject the BlacklistManager instance from the engine."""
        self._manager = manager
        self.refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 16)
        lay.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(3)
        col.addWidget(lbl("Blacklist", "PageTitle"))
        col.addWidget(lbl("Users who sent fake or invalid links are listed here.", "PageSub"))
        hdr.addLayout(col); hdr.addStretch()

        refresh_btn = QPushButton("⟳ Refresh")
        refresh_btn.setObjectName("GhostBtn")
        refresh_btn.clicked.connect(self.refresh)
        hdr.addWidget(refresh_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.setObjectName("GhostBtn")
        clear_btn.clicked.connect(self._clear_all)
        hdr.addWidget(clear_btn)

        lay.addLayout(hdr)
        lay.addWidget(hdiv())

        # Stat label
        self._stat_lbl = lbl("0 users blacklisted", "FieldHint")
        lay.addWidget(self._stat_lbl)

        # Scroll list
        scroll = SmoothScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._wrap = QWidget()
        self._list_lay = QVBoxLayout(self._wrap)
        self._list_lay.setContentsMargins(0, 4, 6, 10)
        self._list_lay.setSpacing(6)
        scroll.setWidget(self._wrap)
        lay.addWidget(scroll)

        # Empty state placeholder
        self._empty_lbl = QLabel("No blacklisted users.")
        self._empty_lbl.setStyleSheet(
            f"color: {C['dim']}; font-size: 12px; padding: 20px;")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_lay.addWidget(self._empty_lbl)
        self._list_lay.addStretch()

        self._rows: list[QFrame] = []

    def refresh(self):
        """Re-read entries from BlacklistManager and rebuild the list."""
        for row in self._rows:
            self._list_lay.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        if self._manager is None:
            self._stat_lbl.setText("Blacklist system not loaded.")
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
        name_lbl = QLabel(entry.username or "unknown")
        name_lbl.setStyleSheet(
            f"color: {C['text']}; font-size: 12px; font-weight: 600;")
        reason_lbl = QLabel(f"Reason: {entry.reason}  ·  Offenses: {entry.count}")
        reason_lbl.setStyleSheet(
            f"color: {C['muted']}; font-size: 10px;")
        col.addWidget(name_lbl); col.addWidget(reason_lbl)
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


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: PLUGINS
# ─────────────────────────────────────────────────────────────────────────────

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

        # Auto-update
        self._updater = AutoUpdater(self)
        self._updater.update_available.connect(self._on_update_available)
        QTimer.singleShot(3000, self._updater.check_async)

        # System tray for desktop notifications
        self._tray: Optional[QSystemTrayIcon] = None
        self._setup_tray()

        # Pre-load plugins at startup so the Plugins tab works before engine starts
        self._init_plugin_loader()

    def _init_plugin_loader(self):
        """Create the PluginLoader at startup so the Plugins page works immediately."""
        if getattr(sys, "frozen", False):
            _base = Path(os.path.dirname(sys.executable))
        else:
            _base = Path(os.path.dirname(os.path.abspath(__file__)))
        pl = PluginLoader(_base / "plugins")
        pl.discover()
        self._startup_plugin_loader = pl
        self._ppg.set_loader(pl)

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
        self._pl  = LogsPage(self._dev)
        self._pn  = NotificationsPage(self._cfg)
        self._pbl = BlacklistPage()     # Blacklist page
        self._ppg = PluginsPage()       # Plugins page

        for pg in (self._pd, self._pse, self._pl, self._pn, self._pbl, self._ppg):
            self._stk.addWidget(pg)

        body.addWidget(self._stk); v.addLayout(body)
        self._grip = QSizeGrip(self); self._grip.setFixedSize(14, 14)

    def _connect(self):
        self._sb.page_changed.connect(self._stk.setCurrentIndex)
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

        # Wire blacklist and plugin pages (managers available only after engine init)
        self._sb.page_changed.connect(self._on_page_changed)

    def _shortcuts(self):
        sc = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        sc.activated.connect(self._toggle_dev)

    def _on_page_changed(self, idx: int):
        """Lazy-refresh data pages when user navigates to them."""
        # idx 4 = Blacklist, idx 5 = Plugins
        if idx == 4:
            self._pbl.refresh()
        elif idx == 5:
            self._ppg.refresh()

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
            # Use custom icon if provided (QImage), otherwise default
            if icon:
                self._tray.showMessage(title, message, QIcon(QPixmap.fromImage(icon)), 3000)
            else:
                self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def _send_webhook(self, event_type: str, **kwargs):
        if not self._cfg.webhook.enabled or not self._cfg.webhook.url:
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
        self._br.start()
        self._run = True
        self._pd.on_start()

        # Wire subsystem pages to the engine's injected managers
        engine = self._br.engine
        self._pbl.set_manager(engine.blacklist)
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
        # Webhook — engine no longer sends lifecycle events, this is the single sender
        self._send_webhook("start")

        if self._is_paused: self._toggle_pause_state()

    def _stop(self):
        if self._br:
            self._br.stop()
            self._br = None
        self._run       = False
        self._is_paused = False
        self._pd.on_stop()

        self._tb.badge.set_state("off")
        self._pd.badge.set_state("off")
        self._pd.c_status.set_value("STOPPED")

        self._tray_notify("Sniper Stopped", "Engine has been shut down.", get_tray_icon_img())
        self._send_webhook("stop")

    def _on_log(self, e: LogEntry):
        self._pl.append(e)
        if self._is_snipe_log(e):
            self._pd.append(e, self._dev)

    def _on_biome(self, expected: str, detected: str, matched: bool):
        self._send_webhook("biome", expected=expected, detected=detected, match=matched)

    def _on_engine_paused(self, paused: bool):
        if paused:
            self._tb.badge.set_state("idle")
            self._pd.badge.set_state("idle")
            self._pd.c_status.set_value("AUTO-PAUSED")
            e = LogEntry(LogLevel.WARN, "[ENGINE] Auto-paused after snipe.")
            self._pl.append(e); self._pd.append(e, self._dev)
        else:
            if not self._is_paused:
                self._tb.badge.set_state("on")
                self._pd.badge.set_state("on")
                self._pd.c_status.set_value("ON")
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

        # Single webhook send — passes full dict as kwargs
        self._send_webhook("snipe", **data)

    def _on_ping(self, p: float):
        self._pd.c_ping.set_value(f"{p:.0f}")

    def _on_cfg(self, cfg: SniperConfig):
        self._cfg = cfg
        if self._br: self._br.reload(cfg)

    def _on_update_available(self, sha: str):
        msg = QMessageBox(self)
        msg.setWindowTitle("Update Available")
        msg.setText(
            f"A new version is available (commit {sha}).\n\n"
            "The app will rebuild from source and restart automatically.\n\n"
            "Update now?")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if msg.exec() == QMessageBox.StandardButton.Yes:
            self._pd.show_notification(
                f"Rebuilding from source (commit {sha})…", "warning")
            self._stop()
            threading.Thread(
                target=self._updater.rebuild_and_restart,
                daemon=True, name="AutoRebuild").start()
        else:
            self._pd.show_notification(f"Update {sha} skipped.", "warning")

    def _is_snipe_log(self, e: LogEntry) -> bool:
        if e.level in (LogLevel.SNIPE, LogLevel.SUCCESS, LogLevel.ERROR, LogLevel.WARN):
            return True
        return any(tag in e.message for tag in ("[SNIPER]", "[FILTER]", "[CONFIG]", "[ANTI-BAIT]"))

    def _tick(self):
        if self._br:
            if self._br.ping_ms > 0:
                self._pd.c_ping.set_value(f"{self._br.ping_ms:.0f}")
            uptime = int(self._br.uptime_seconds)
            self._pd.c_uptime.set_value(str(uptime))
            # Push engine metrics to the grid cards
            self._pd.update_engine_metrics(self._br.engine.metrics)
        # Roblox running indicator (uses psutil — run import guard)
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
        super().resizeEvent(e); self._sb.adapt(self.width())
        if hasattr(self, "_grip"):
            self._grip.move(self.width() - 14, self.height() - 14)
        self._tb._update_max_icon()

    def closeEvent(self, e):
        self._stop(); self._cfg.save(); e.accept()

# ENTRY POINT

def main():
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

    # Splash screen → show main window when done
    splash = SplashScreen()
    win    = MainWindow()

    def _on_splash_done():
        win.show()

    splash.finished.connect(_on_splash_done)
    splash.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
