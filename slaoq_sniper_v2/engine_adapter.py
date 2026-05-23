from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import sys
import threading
from time import monotonic
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from slaoq_sniper_v2.config import ConfigStore
from slaoq_sniper_v2.models import AppConfig
from slaoq_sniper_v2.performance import detect_performance_profile
from slaoq_sniper_v2.storage import BlacklistStore, HistoryStore, sanitize_text


logger = logging.getLogger("slaoq_sniper_v2.engine_adapter")


@dataclass(frozen=True)
class EngineMetrics:
    status: str
    snipes: int
    uptime_seconds: int
    ping_ms: int
    messages: int
    roblox_running: bool
    paused: bool


class EngineAdapter(QObject):
    metrics_changed = Signal(object)
    log_added = Signal(str, str)
    history_changed = Signal()
    _engine_finished = Signal(str)

    def __init__(
        self,
        config_store: ConfigStore | None = None,
        blacklist_store: BlacklistStore | None = None,
        history_store: HistoryStore | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config_store = config_store
        self._blacklist_store = blacklist_store
        self._history_store = history_store
        self._engine: Any = None
        self._engine_module: Any = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._real_engine_available = self._can_use_real_engine()
        self._running = False
        self._paused = False
        self._status = "OFF"
        self._ping_ms = 0
        self._snipes = 0
        self._messages = 0
        self._started_at = 0.0
        self._paused_total = 0.0
        self._pause_started_at = 0.0
        self._performance = detect_performance_profile()

        self._timer = QTimer(self)
        self._timer.setInterval(self._performance.ui_metrics_interval_ms)
        self._timer.timeout.connect(self._tick)
        self._engine_finished.connect(self._on_engine_finished)
        logger.info("Using %s performance profile", self._performance.name)
        self._emit_metrics()

    def start(self) -> None:
        if self._running:
            return
        if self._real_engine_available and self._config_store:
            validation_error = self._validate_config(self._config_store.config)
            if validation_error:
                self._status = "ERROR"
                self.log_added.emit("warning", validation_error)
                self._emit_metrics()
                return
            self._start_real_engine()
            return
        self._running = True
        self._paused = False
        self._status = "ON"
        self._started_at = monotonic()
        self._paused_total = 0.0
        self._pause_started_at = 0.0
        self._timer.start()
        logger.info("Engine adapter started")
        self.log_added.emit("success", "Engine adapter started. Real engine integration is pending.")
        self._emit_metrics()

    def stop(self) -> None:
        if not self._running:
            return
        if self._engine and self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._engine.stop(), self._loop)
            self._running = False
            self._paused = False
            self._status = "STOPPING"
            self._timer.stop()
            self.log_added.emit("info", "Engine stop requested.")
            self._emit_metrics()
            return
        self._running = False
        self._paused = False
        self._status = "OFF"
        self._timer.stop()
        logger.info("Engine adapter stopped")
        self.log_added.emit("info", "Engine adapter stopped.")
        self._emit_metrics()

    def toggle_pause(self) -> None:
        if not self._running:
            self.log_added.emit("warning", "Start the engine before pausing.")
            return
        next_paused = not self._paused
        self._set_paused_state(next_paused)
        if self._engine:
            if hasattr(self._engine, "set_paused") and self._loop and self._loop.is_running():
                message = "[ENGINE] Manually paused." if next_paused else "[ENGINE] Manually resumed."
                self._loop.call_soon_threadsafe(self._engine.set_paused, next_paused, message)
            else:
                self._engine._paused = next_paused
        if not self._paused and self._status == "PAUSED":
            self._status = "CONNECTED" if self._engine else "ON"
        state = "paused" if self._paused else "resumed"
        logger.info("Engine adapter %s", state)
        self.log_added.emit("info", f"Engine adapter {state}.")
        self._emit_metrics()

    def _tick(self) -> None:
        if self._engine:
            self._messages = int(getattr(self._engine, "metrics", {}).get("messages_scanned", self._messages))
            self._snipes = int(getattr(self._engine, "snipe_count", self._snipes))
            self._paused = bool(getattr(self._engine, "_paused", self._paused))
        elif self._running and not self._paused:
            self._messages += 3
        self._emit_metrics()

    def _emit_metrics(self) -> None:
        if not self._running:
            status = self._status if self._status in {"ERROR", "STOPPED"} else "OFF"
            uptime = 0
            ping = 0
        else:
            status = "PAUSED" if self._paused else self._status
            uptime = int(getattr(self._engine, "uptime_seconds", 0) or self._simulated_uptime())
            ping = int(getattr(self._engine, "ping_ms", 0) or self._ping_ms)

        self.metrics_changed.emit(
            EngineMetrics(
                status=status,
                snipes=self._snipes,
                uptime_seconds=uptime,
                ping_ms=ping,
                messages=self._messages,
                roblox_running=self._is_roblox_running(),
                paused=self._paused,
            )
        )

    def _start_real_engine(self) -> None:
        try:
            self._engine_module = self._import_v1_engine()
            config = self._to_v1_config(self._engine_module, self._config_store.config)
            cooldown = _CooldownManager(config)
            self._engine = self._engine_module.SniperEngine(
                config,
                blacklist=self._blacklist_store,
                cooldown=cooldown,
            )
            self._wire_callbacks()
        except Exception as exc:
            logger.exception("Falling back to simulated engine: %s", exc)
            self.log_added.emit("warning", f"Real engine unavailable: {exc}")
            self._real_engine_available = False
            self.start()
            return

        self._running = True
        self._paused = False
        self._status = "CONNECTING"
        self._ping_ms = 0
        self._messages = 0
        self._snipes = 0
        self._started_at = monotonic()
        self._paused_total = 0.0
        self._pause_started_at = 0.0
        self._timer.start()
        self._thread = threading.Thread(target=self._run_engine_loop, daemon=True, name="SlaoqV2Engine")
        self._thread.start()
        logger.info("Real V1 engine bridge started")
        self.log_added.emit("success", "Real engine bridge started.")
        self._emit_metrics()

    def _run_engine_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        finish_status = "STOPPED"
        try:
            self._loop.run_until_complete(self._engine.start())
        except Exception as exc:
            finish_status = "ERROR"
            logger.exception("Engine loop failed: %s", exc)
            self.log_added.emit("error", f"Engine loop failed: {exc}")
        finally:
            self._loop.close()
            self._loop = None
            self._engine_finished.emit(finish_status)

    def _wire_callbacks(self) -> None:
        def on_log(entry: Any) -> None:
            level = getattr(getattr(entry, "level", None), "value", "info")
            message = getattr(entry, "message", str(entry))
            self.log_added.emit(str(level).lower(), sanitize_text(str(message)))

        def on_status(status: Any) -> None:
            value = getattr(status, "value", str(status))
            self._status = str(value).upper()
            self._running = self._status not in {"STOPPED", "IDLE"}
            self.log_added.emit("info", f"Engine status: {value}")
            self._emit_metrics()

        def on_ping(ping: float) -> None:
            self._ping_ms = int(ping)
            self._emit_metrics()

        def on_paused(paused: bool) -> None:
            self._set_paused_state(paused)
            self._emit_metrics()

        def on_snipe(data: dict) -> None:
            self._snipes = int(getattr(self._engine, "snipe_count", self._snipes))
            if self._history_store:
                from slaoq_sniper_v2.models import SnipeHistoryEntry

                self._history_store.add(
                    SnipeHistoryEntry(
                        profile=str(data.get("profile", "?")),
                        keyword=str(data.get("keyword", "")),
                        author=str(data.get("author_display") or data.get("author", "")),
                        raw_message=str(data.get("raw_message", "")),
                        timestamp=str(data.get("timestamp_iso", "")),
                        biome_verified=None,
                        expected_biome=str(data.get("verify_biome_name", "")),
                        roblox_url=str(data.get("roblox_web_url") or data.get("uri", "")),
                        jump_url=str(data.get("jump_url", "")),
                    )
                )
                self.history_changed.emit()
            self.log_added.emit("success", f"Snipe fired: {data.get('profile', 'Unknown')}")
            self._emit_metrics()

        def on_biome(expected: str, detected: str, matched: bool) -> None:
            if self._history_store and self._history_store.update_latest_biome_result(expected, detected, matched):
                self.history_changed.emit()

        self._engine.on_log = on_log
        self._engine.on_status = on_status
        self._engine.on_ping_update = on_ping
        self._engine.on_paused = on_paused
        self._engine.on_snipe = on_snipe
        self._engine.on_biome = on_biome

    def _on_engine_finished(self, status: str) -> None:
        self._running = False
        self._paused = False
        self._status = status
        self._timer.stop()
        self._engine = None
        self._thread = None
        self._emit_metrics()

    def _set_paused_state(self, paused: bool) -> None:
        if paused == self._paused:
            return
        now = monotonic()
        if paused:
            self._paused = True
            self._pause_started_at = now
        else:
            self._paused = False
            if self._pause_started_at:
                self._paused_total += max(0.0, now - self._pause_started_at)
            self._pause_started_at = 0.0

    def _simulated_uptime(self) -> float:
        if not self._started_at:
            return 0.0
        now = self._pause_started_at if self._paused and self._pause_started_at else monotonic()
        return max(0.0, now - self._started_at - self._paused_total)

    def reload_config(self) -> None:
        if not self._config_store or not self._engine or not self._engine_module:
            return
        converted = self._to_v1_config(self._engine_module, self._config_store.config)
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._engine.reload_config, converted)
        else:
            self._engine.reload_config(converted)
        self.log_added.emit("success", "Engine configuration reloaded.")
        self._emit_metrics()

    @staticmethod
    def _can_use_real_engine() -> bool:
        try:
            EngineAdapter._import_v1_engine()
            return True
        except Exception:
            return False

    @staticmethod
    def _import_v1_engine() -> Any:
        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import sniper_engine

        return sniper_engine

    @staticmethod
    def _to_v1_config(module: Any, config: AppConfig) -> Any:
        converted = module.SniperConfig()
        converted.token = config.token
        converted.monitored_channels = [
            module.ChannelConfig(
                guild_id=channel.guild_id,
                channel_id=channel.channel_id,
                name=channel.name,
                enabled=channel.enabled,
            )
            for channel in config.monitored_channels
        ]
        converted.profiles = []
        for profile in config.profiles:
            data = profile.to_dict()
            data.pop("category", None)
            converted.profiles.append(module.SnipeProfile.from_dict(data))
        converted.auto_join_enabled = config.auto_join_enabled
        converted.auto_join_delay_ms = config.auto_join_delay_ms
        converted.pause_after_snipe_s = config.pause_after_snipe_s
        converted.close_roblox_before_join = config.close_roblox_before_join
        converted.biome_leave_action = config.biome_leave_action
        converted.anti_bait_enabled = config.anti_bait_enabled
        converted.link_resolve_enabled = config.link_resolve_enabled
        converted.theme = config.theme
        converted.dev_mode = config.dev_mode
        converted.webhook = module.WebhookConfig.from_dict(config.webhook.to_dict())
        converted.cooldown_guild_ttl = config.cooldown_guild_ttl
        converted.cooldown_profile_ttl = config.cooldown_profile_ttl
        converted.cooldown_link_ttl = config.cooldown_link_ttl
        converted.sound_alert_enabled = config.sound_alert_enabled
        converted.sound_alert_freq = config.sound_alert_freq
        converted.sound_alert_dur_ms = config.sound_alert_dur_ms
        converted.delete_watch_seconds = config.delete_watch_seconds
        converted.extra_tokens = config.extra_tokens
        return converted

    @staticmethod
    def _validate_config(config: AppConfig) -> str | None:
        if not config.token.strip():
            return "Discord token is not configured."
        enabled_channels = [channel for channel in config.monitored_channels if channel.enabled]
        if not enabled_channels:
            return "Add at least one enabled Discord channel before starting."
        enabled_profiles = [profile for profile in config.profiles if profile.enabled]
        if not enabled_profiles:
            return "Enable at least one snipe profile before starting."
        return None

    def _is_roblox_running(self) -> bool:
        try:
            module = self._engine_module or self._import_v1_engine()
            return bool(module.ProcessManager.is_roblox_running())
        except Exception:
            return False


class _CooldownManager:
    def __init__(self, config: Any) -> None:
        self.guild_ttl = getattr(config, "cooldown_guild_ttl", 30.0)
        self.profile_ttl = getattr(config, "cooldown_profile_ttl", 0.0)
        self.link_ttl = getattr(config, "cooldown_link_ttl", 10.0)
        self._state: dict[str, float] = {}

    def update_config(self, config: Any) -> None:
        self.guild_ttl = getattr(config, "guild_ttl", 30.0)
        self.profile_ttl = getattr(config, "profile_ttl", 0.0)
        self.link_ttl = getattr(config, "link_ttl", 10.0)

    def check(self, guild_id: str, profile_name: str, uri: str, bypass: bool = False) -> tuple[bool, str]:
        if bypass:
            return False, ""
        now = monotonic()
        for key, label in (
            (f"guild:{guild_id}", "guild cooldown"),
            (f"profile:{profile_name}", "profile cooldown"),
            (f"link:{uri.rstrip('/').lower()}", "link cooldown"),
        ):
            expires = self._state.get(key, 0)
            if now < expires:
                return True, f"{label} ({expires - now:.1f}s left)"
        return False, ""

    def mark(self, guild_id: str, profile_name: str, uri: str) -> None:
        now = monotonic()
        if self.guild_ttl > 0:
            self._state[f"guild:{guild_id}"] = now + self.guild_ttl
        if self.profile_ttl > 0:
            self._state[f"profile:{profile_name}"] = now + self.profile_ttl
        if self.link_ttl > 0:
            self._state[f"link:{uri.rstrip('/').lower()}"] = now + self.link_ttl

    def reset(self) -> None:
        self._state.clear()
