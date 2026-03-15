<div align="center">

<img src="https://raw.githubusercontent.com/gustaslaoq/Sols-RNG-Sniper/main/assets/logo.png" width="90" height="90" style="border-radius: 14px;" />

# Slaoq's Sol's RNG Sniper

**Automatic private server sniper for Sol's RNG on Roblox.**  
Monitors Discord channels in real time and joins verified server links instantly.

<br>

[![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org/downloads)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078d4?style=flat-square&logo=windows&logoColor=white)](#)
[![License](https://img.shields.io/badge/License-GPL%20v3-blue?style=flat-square)](LICENSE)
[![Download](https://img.shields.io/badge/Download-build.bat-00c853?style=flat-square&logo=github)](https://github.com/gustaslaoq/Sols-RNG-Sniper/releases/latest/download/build.bat)

</div>

---

## What it does

This app connects to Discord using your account token and watches specific channels for Roblox private server links. The moment a matching link appears it opens the link in Roblox automatically and verifies the biome so you don't get caught by bait servers.

Everything runs as a compiled `.exe`. There is no coding required. Run `build.bat` once, configure, and use.

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [First-Time Setup](#first-time-setup)
- [Settings Reference](#settings-reference)
- [Dashboard](#dashboard)
- [Snipe History](#snipe-history)
- [Blacklist](#blacklist)
- [Logs](#logs)
- [Plugins](#plugins)
- [Auto-Update](#auto-update)
- [Hotkeys](#hotkeys)
- [Troubleshooting](#troubleshooting)
- [Disclaimer](#disclaimer)

---

## Requirements

### Python 3.10 or newer

1. Go to [python.org/downloads](https://python.org/downloads) and install Python
2. **Important:** tick **"Add Python to PATH"** on the first installer screen

### Git

1. Go to [git-scm.com](https://git-scm.com) and install Git (default options are fine)

Everything else (PySide6, PyInstaller, aiohttp, psutil, etc.) installs automatically via `build.bat`.

---

## Installation

1. Download `build.bat` from the badge above
2. Double-click it — a console window runs through 9 build steps (~3–5 min)
3. Press any key when done to launch

The script automatically picks the right install location. Running from Downloads or Desktop creates a `SlaoqSniper\` subfolder; running from a dedicated empty folder installs inline.

**To update:** run `build.bat` again. It detects new commits and rebuilds automatically.

---

## First-Time Setup

Open **Settings** when the app first launches.

### 1. Discord Token

1. Open [discord.com/app](https://discord.com/app) in your **browser**
2. Press `F12` → Network tab → filter for `science`
3. Click any request → Request Headers → copy the `Authorization:` value
4. Paste it into the **User Token** field

> Never share your token. It gives full access to your Discord account.

### 2. Monitored Channels

Enable Developer Mode in Discord (Settings → Advanced → Developer Mode), then:

1. Right-click the server icon → **Copy Server ID**
2. Right-click the channel → **Copy Channel ID**
3. Paste both IDs into Settings and click **+ Add Channel**

### 3. Snipe Profiles

All major Sol's RNG biomes are pre-configured out of the box: **Glitched, Dreamspace, Cyberspace, Null, Starlight, Heaven, Corrupted, Abyssal**. Each profile has the correct trigger keywords and biome verification name already set. Enable or disable them individually, or create new profiles for anything not covered.

**The Global profile** runs first on every message and acts as a universal blacklist. Words like `ended`, `bait`, `fake`, `over`, `closed`, `gone` are blocked by default.

---

## Settings Reference

### Auto-Join

| Setting | Description |
|---------|-------------|
| Auto-join on snipe | Automatically open Roblox when a link is detected |
| Close Roblox before joining | Force-close any running Roblox instance first |
| Join delay (ms) | Wait before joining. `0` = instant |
| Auto-pause after snipe | Pause scanning for N seconds after a snipe fires |
| When biome ends | Action when biome watcher detects the biome ended: Do nothing / Close Roblox / Return to home |

> **Return to home** kills the game and reopens the Roblox launcher to the home screen — faster for repeated sniping since the launcher stays loaded.

### Cooldown

| Setting | Description |
|---------|-------------|
| Guild cooldown | Ignore all links from the same Discord server for N seconds after a snipe |
| Profile cooldown | Per-profile cooldown. `0` = disabled |
| Link cooldown | Ignore the exact same Roblox URI for N seconds |

### Sound Alert

Plays a beep when a snipe fires — useful when the app runs in the background.

| Setting | Description |
|---------|-------------|
| Enable sound alert on snipe | Toggle the beep on/off |
| Frequency (Hz) | Pitch of the beep (default 1000 Hz) |
| Duration (ms) | Length of the beep (default 200 ms) |

Click **▶ Test Sound** to preview without triggering a snipe. Sound alerts use `winsound` and only work on Windows.

### Extra Discord Tokens

Add additional Discord account tokens to monitor the same channels simultaneously. Each extra token runs a second gateway in **listen-only mode** — it receives messages and feeds them into the full snipe pipeline, but does not affect the status shown in the dashboard. One primary token is always enough; extra tokens are optional for increased coverage.

**To add:** Settings → Extra Discord Tokens → paste token → **+ Add**.

You can add and remove extra tokens at any time without restarting.

> Using multiple self-bot tokens simultaneously may violate Discord's Terms of Service. Use at your own risk.

### Notifications

Configure desktop toast notifications and Discord webhook delivery for snipe events, biome verification, engine start/stop, and auto-blacklist events.

**Webhook setup:** Discord server → Server Settings → Integrations → Webhooks → New Webhook → copy URL → paste into Settings.

---

## Dashboard

| Card | What it shows |
|------|---------------|
| Snipes | Total snipes this session |
| Ping | Discord gateway latency (ms) |
| Status | Engine state (CONNECTING / ON / PAUSED / etc.) |
| Roblox | Whether Roblox is running |
| Uptime | Seconds running |
| Messages | Total messages scanned |

---

## Snipe History

The **History** tab (clock icon in the sidebar) shows a persistent log of every snipe — across sessions. Saved to `snipe_history.json` in the app data folder, survives restarts, keeps up to 500 entries.

Each entry shows the profile and keyword that triggered the snipe, the author, a timestamp, the biome verification result (✓ / ✗), a preview of the raw message, and action buttons to **Open in Roblox** or **Jump to Message** in Discord.

---

## Blacklist

Users whose messages are always ignored regardless of keywords.

**Manual add:** Blacklist page → enter Discord User ID → **+ Add** (username is looked up automatically).

### Auto-Blacklist on Message Delete

Configure an automatic blacklist that triggers when a sniped user deletes their message within a configurable watch window.

This setting is at the bottom of the Blacklist page under **AUTO-BLACKLIST ON MESSAGE DELETE**.

| Setting | Description |
|---------|-------------|
| Watch window (seconds) | How long to observe after a snipe. `0` = disabled |

When a deletion is detected within the window, the user is blacklisted automatically and a webhook embed is sent:

> **123456789 (@username)** has been blacklisted for deleting their message.

Recommended value: 30–60 seconds.

---

## Logs

Full record of everything the engine processed. Filter by log level with the buttons at the top.

**Dev Mode** (`Ctrl+Shift+D`) enables verbose logging — every message, every filter decision, every link extraction and deduplication step.

---

## Plugins

Drop `.py` files into the `plugins/` folder next to the exe, restart, then toggle them in the **Plugins** tab.

Available hooks:

| Hook | When it fires |
|------|--------------|
| `init(engine, ui)` | Engine starts |
| `on_start(data)` | Sniper started |
| `on_stop()` | Sniper stopped |
| `on_message_matched(data)` | Message passed the profile filter |
| `on_cooldown_blocked(data)` | Snipe blocked by cooldown |
| `on_snipe(data)` | Snipe fired — link opened |
| `on_biome_verified(data)` | Anti-bait confirmed correct biome |
| `on_biome_left(data)` | Biome watcher: biome ended |

The `on_snipe` payload includes: `author_id`, `author_display`, `author_avatar_url`, `keyword`, `roblox_web_url`, `timestamp_iso`, `jump_url`, and `raw_message`.

---

## Auto-Update

Every launch checks GitHub for new commits. If outdated, the splash screen shows **"Update found"** and launches `build.bat --update` automatically.

---

## Hotkeys

Configure global shortcuts in the Dashboard.

| Key | Action |
|-----|--------|
| Toggle key | Start / stop the sniper |
| Pause key | Temporarily pause scanning |

---

## Troubleshooting

**"Token not configured"** — paste your Discord token in Settings.

**"No monitored channels"** — add at least one channel in Settings.

**Sniper connects but nothing snipes** — check the Logs page for `[FILTER]` lines:
- `global blacklist keyword 'X'` — a global blacklist word matched the message
- `no profile trigger matched` — no profile keyword found in the message
- `[COOLDOWN] Blocked` — cooldown is active, lower the values or wait

**Joins wrong server / gets kicked instantly** — enable **Close Roblox before joining**.

**Sound alert not working** — `winsound` is Windows-only. Check system volume.

**History tab empty after reinstall** — history is in `%LOCALAPPDATA%\SlaoqSniper\snipe_history.json`.

**Build fails — Python not found** — reinstall Python and tick **"Add Python to PATH"**.

**Build fails — clone failed** — run `git clone https://github.com/gustaslaoq/Sols-RNG-Sniper.git` in cmd first to cache credentials.

---

## Disclaimer

This software uses a Discord user account token to automate message monitoring. This may violate Discord's Terms of Service. Use at your own risk. The authors are not responsible for any account actions taken by Discord.

---

## Credits

Inspired by [Sol Sniper V3](https://github.com/vexsyx/sniper-v3) by vexsyx.
