PLUGIN_NAME        = "Example Plugin"
PLUGIN_ICON        = "zap"
PLUGIN_DESCRIPTION = "Starter template — documents every available hook."
PLUGIN_VERSION     = "1.0"
PLUGIN_AUTHOR      = "Your Name"

PLUGIN_SETTINGS = {
    "log_every_match": False,
    "custom_label":    "MyPlugin",
}

_engine = None
_ui     = None


def init(engine, ui):
    """
    Called once when the engine starts (or when the plugin is loaded).

    engine  — SniperEngine. Useful:
        engine.config          SniperConfig (token, profiles, channels, etc.)
        engine.metrics         dict: messages_scanned, snipes_successful, ...
        engine.snipe_count     int
        engine.ping_ms         float
        engine.uptime_seconds  float

    ui      — MainWindow (may be None). Useful:
        ui._pd.show_notification("text", "warning"|"error")
        ui._pl.append(LogEntry(LogLevel.INFO, "msg"))
    """
    global _engine, _ui
    _engine = engine
    _ui     = ui
    _log("Plugin initialized.")


def on_start(data: dict):
    """Fired when the sniper engine starts.
    data = { "config": SniperConfig }
    """
    cfg = data.get("config")
    n = len(cfg.monitored_channels) if cfg else 0
    _log(f"Engine started — {n} channel(s) monitored.")


def on_stop():
    """Fired when the sniper engine stops."""
    _log("Engine stopped.")


def on_message_matched(data: dict):
    """Fired when a message passes the profile filter, before link extraction.
    data = { "profile": str, "author": str, "content": str, "full": str }
    """
    if PLUGIN_SETTINGS.get("log_every_match"):
        _log(f"Match — profile '{data['profile']}' from {data['author']}")


def on_cooldown_blocked(data: dict):
    """Fired when a snipe is blocked by cooldown.
    data = { "reason": str, "profile": str, "uri": str }
    """
    _log(f"Cooldown blocked — {data['reason']}")


def on_snipe(data: dict):
    """Fired on every successful snipe.
    data = {
        "place_id":    str   Roblox place ID
        "code":        str   private server link code
        "uri":         str   full roblox:// URI launched
        "profile":     str   profile name that triggered
        "author":      str   Discord username
        "raw_message": str   original message (up to 1000 chars)
        "link":        str   same as uri
        "jump_url":    str   discord.com/channels/... link
    }
    Use this to send webhooks, play sounds, write logs, call external APIs.
    """
    _log(f"SNIPE  profile={data.get('profile')}  place={data.get('place_id')}  by={data.get('author')}")

    if _ui:
        try:
            _ui._pd.show_notification(
                f"Plugin snipe: {data.get('author')} — {data.get('profile')}", "warning")
        except Exception:
            pass


def on_biome_verified(data: dict):
    """Fired when anti-bait confirms the biome is correct after joining.
    data = { "expected": str, "detected": str }
    """
    _log(f"Biome confirmed: {data.get('detected')}")


def on_biome_left(data: dict):
    """Fired when the biome watcher detects the biome ended/changed.
    data = { "action": str }  action is "kill" | "home" | "none"
    """
    _log(f"Biome ended — action: {data.get('action')}")


def _log(msg: str):
    label = PLUGIN_SETTINGS.get("custom_label", PLUGIN_NAME)
    print(f"[{label}] {msg}")
    if _ui:
        try:
            from sniper_engine import LogEntry, LogLevel
            _ui._pl.append(LogEntry(LogLevel.INFO, f"[{label}] {msg}"))
        except Exception:
            pass
