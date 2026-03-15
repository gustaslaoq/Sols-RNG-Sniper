"""
plugins/example_plugin.py — Example Plugin for Slaoq's Sniper
--------------------------------------------------------------
Copy this file as a starting point for your own plugins.

Required metadata:
    PLUGIN_NAME        — display name shown in the Plugins page
    PLUGIN_ICON        — SVG icon key (home/settings/logs/bell/lock/zap/trash/check/info/webhook)
    PLUGIN_DESCRIPTION — one-line description

Optional hooks (all are optional — implement only what you need):
    init(engine, ui)   — called once when the engine starts
    on_snipe(data)     — called on every successful snipe
    on_stop()          — called when the engine stops
"""

PLUGIN_NAME        = "Example Plugin"
PLUGIN_ICON        = "bell"
PLUGIN_DESCRIPTION = "Logs every snipe event to the console."

PLUGIN_CONFIG: dict = {
    "enabled": True,
    "prefix":  "[ExPlugin]",
}


def init(engine, ui) -> None:
    """Called once after the plugin is loaded. engine and ui may be None in some contexts."""
    print(f"{PLUGIN_CONFIG['prefix']} Plugin loaded. Engine available: {engine is not None}")


def on_snipe(data: dict) -> None:
    """
    Called on every successful snipe.
    data keys: place_id, code, uri, profile, author, raw_message, link, jump_url
    """
    if not PLUGIN_CONFIG.get("enabled"):
        return
    p   = PLUGIN_CONFIG.get("prefix", "[Plugin]")
    lnk = data.get("link", "")[:60]
    print(f"{p} Snipe! Profile={data.get('profile')}  Author={data.get('author')}  Link={lnk}")


def on_stop() -> None:
    """Called when the sniper engine stops."""
    print(f"{PLUGIN_CONFIG['prefix']} Engine stopped.")
