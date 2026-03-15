<div align="center">

<img src="https://raw.githubusercontent.com/gustaslaoq/Sols-RNG-Sniper/main/assets/logo.png" width="90" height="90" style="border-radius: 14px;" />

# Slaoq's Sol's RNG Sniper

**Automatic private server sniper for Sol's RNG on Roblox.**  
Monitors Discord channels in real time and joins verified server links instantly.

<br>

[![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org/downloads)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078d4?style=flat-square&logo=windows&logoColor=white)](#)
[![License](https://img.shields.io/github/license/gustaslaoq/Sols-RNG-Sniper?style=flat-square)](LICENSE)
[![Download](https://img.shields.io/badge/Download-build.bat-00c853?style=flat-square&logo=github)](https://github.com/gustaslaoq/Sols-RNG-Sniper/releases/latest/download/build.bat)

</div>

---

## What it does

This app connects to Discord using your account token and watches specific channels for Roblox private server links. The moment a matching link appears — based on your configured keywords and profiles — it opens the link in Roblox automatically. It also verifies the biome after joining so you don't get caught by bait servers.

Everything runs as a compiled `.exe`. There is no coding required. You run one script, it builds the app for you, and from that point you just configure and use it.

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [First-Time Setup](#first-time-setup)
  - [Discord Token](#1-discord-token)
  - [Monitored Channels](#2-monitored-channels)
  - [Snipe Profiles](#3-snipe-profiles)
- [Settings Reference](#settings-reference)
- [Dashboard](#dashboard)
- [Blacklist](#blacklist)
- [Logs](#logs)
- [Plugins](#plugins)
- [Auto-Update](#auto-update)
- [Hotkeys](#hotkeys)
- [Troubleshooting](#troubleshooting)
- [Disclaimer](#disclaimer)

---

## Requirements

Before you do anything, install the two tools below. Both are free and take about 2 minutes.

### Python 3.10 or newer

1. Go to [python.org/downloads](https://python.org/downloads)
2. Click the big yellow **Download Python** button
3. Run the installer
4. **Important:** on the first screen, tick the box that says **"Add Python to PATH"** before clicking Install

   If you skip this, the build script will not be able to find Python and will fail.

5. Click **Install Now** and wait for it to finish

To verify it worked, open Command Prompt (`Win + R` → type `cmd` → Enter) and run:
```
python --version
```
It should print something like `Python 3.12.0`. If it does, you're good.

### Git

1. Go to [git-scm.com](https://git-scm.com)
2. Click **Download for Windows**
3. Run the installer — the default options are fine, just keep clicking Next
4. Click **Install**

To verify, in Command Prompt run:
```
git --version
```
It should print `git version 2.x.x`.

Everything else the app needs (PySide6, PyInstaller, aiohttp, psutil, etc.) is downloaded and installed automatically when you run the build script.

---

## Installation

You only need one file: `build.bat`.

1. Download `build.bat` by clicking the **Download** badge above, or [direct download link](https://github.com/gustaslaoq/Sols-RNG-Sniper/releases/latest/download/build.bat)
2. Save it anywhere — Desktop, Downloads folder, wherever you prefer
3. Double-click `build.bat`
4. A console window opens and runs through 9 steps — this takes about 3–5 minutes
5. When the build finishes, press any key to launch the app

The script decides where to place the app automatically:

- **If `build.bat` is in a dedicated empty folder** — the app is installed directly there alongside the bat.
- **If `build.bat` is in a common location** (Downloads, Desktop, Documents, home folder, etc.) or a folder that already has other files — the script creates a `SlaoqSniper\` subfolder and installs there.

**Example — dedicated folder (empty):**
```
C:\Sniper\
├── build.bat
├── SlaoqSniper.exe     ← installed here
├── version.txt
├── assets\
└── plugins\
```

**Example — Downloads or Desktop:**
```
C:\Users\You\Downloads\
├── build.bat
└── SlaoqSniper\
    ├── SlaoqSniper.exe     ← isolated in subfolder
    ├── version.txt
    ├── assets\
    └── plugins\
```

**To update later:** just run `build.bat` again. It checks GitHub for new commits. If you're already on the latest version it skips the build and opens the app directly.

---

## First-Time Setup

When the app opens for the first time, go to the **Settings** page. You need to fill in three things before the sniper will work.

### 1. Discord Token

The sniper needs your Discord user token to connect to Discord's gateway and read messages. This is not your password — it's a separate authentication key.

**How to find your token:**

1. Open Discord in your **web browser** at [discord.com/app](https://discord.com/app) — the website, not the desktop app
2. Press `F12` to open Developer Tools
3. Click the **Network** tab at the top of the DevTools panel
4. In the filter box, type `science` and press Enter
5. Click on any request that appears in the list
6. On the right side, scroll down to **Request Headers**
7. Find the line that says `Authorization:` — the value after it is your token
8. Copy it and paste it into the **User Token** field in Settings

> **Never share your token with anyone.** It gives full access to your Discord account. The app stores it locally on your machine only.

If no requests appear after typing `science`, try clicking around in Discord (switching channels, opening DMs) to trigger some network activity.

### 2. Monitored Channels

These are the Discord channels the sniper watches for server links.

**Step 1 — Enable Developer Mode in Discord:**
1. Open Discord (app or browser)
2. Click the gear icon (User Settings) at the bottom left
3. Go to **Advanced**
4. Turn on **Developer Mode**

This lets you copy IDs by right-clicking things.

**Step 2 — Add a channel:**
1. Right-click the **server icon** (the server's logo in the left sidebar) → **Copy Server ID**
2. Paste it into the **Server ID** field in Settings
3. Right-click the **channel name** → **Copy Channel ID**
4. Paste it into the **Channel ID** field
5. Click **+ Add Channel**

The app automatically fetches the server and channel names. You can add as many channels as you want, from different servers.

### 3. Snipe Profiles

Profiles control what the sniper reacts to. Go to **Settings → Snipe Profiles**.

**The Global profile** is always active and cannot be deleted. It only has a blacklist — any message containing a blacklisted word is ignored before any other profile even looks at it. The default blacklist includes words like `ended`, `bait`, `fake`, `over`, `closed`, `gone`. Add any other words that typically appear in fake or expired server posts.

**Custom profiles** (like Glitched, Dreamspace, etc.) each have:

- **Trigger Keywords** — the sniper fires when a message contains any of these words. For example, a Glitched profile might have `glitch` and `glitched`.
- **Expected Biome Name** — after joining, the sniper reads your Roblox log to check that you actually landed in the right biome (e.g. `GLITCHED`). If the biome doesn't match, Roblox is closed automatically. Leave this empty if you don't need verification.
- **Use Regex** — advanced option. Lets you write regular expressions instead of plain keywords for complex matching.

Profiles are evaluated top to bottom. Use the ↑↓ buttons or drag-and-drop to change the order. Higher up = checked first.

---

## Settings Reference

### Auto-Join

| Setting | Description |
|---------|-------------|
| Auto-join on snipe | Automatically open Roblox when a link is detected |
| Close Roblox before joining | Force-close any running Roblox instance before opening the new link. Required if the game has an auto-rejoin system that would kick the incoming connection |
| Join delay (ms) | Wait this many milliseconds before joining. `0` = instant |
| Auto-pause after snipe | Stop scanning for N seconds after a snipe fires, so gameplay isn't interrupted |
| When biome ends | What to do when the biome watcher detects the biome has changed or ended: **Do nothing**, **Close Roblox**, or **Return to home** |

> **Return to home** is the fastest mode for repeated sniping. Instead of closing Roblox completely, it kills the game and reopens the Roblox launcher to the home screen. The app stays loaded in memory, so the next snipe only needs to load the game — not the full launcher from scratch.

### Cooldown

Prevents re-joining the same source too quickly.

| Setting | Description |
|---------|-------------|
| Guild cooldown | After a snipe, ignore all links from the same Discord server for N seconds |
| Profile cooldown | Per-profile cooldown. `0` = disabled |
| Link cooldown | Ignore the exact same Roblox URI for N seconds |

### Notifications

You can receive desktop toast notifications and Discord webhook messages when a snipe fires.

**Discord webhook setup:**
1. Open your Discord server → Server Settings → Integrations → Webhooks → New Webhook
2. Give it a name, choose a channel, click **Copy Webhook URL**
3. Paste the URL into the Webhook URL field in Settings and enable it

---

## Dashboard

The main screen. Shows live engine stats and has the Start / Stop / Pause controls.

| Card | What it shows |
|------|---------------|
| Snipes | Total successful snipes this session |
| Ping | Discord gateway latency in milliseconds |
| Status | Current engine state (CONNECTING, ON, PAUSED, etc.) |
| Roblox | Whether Roblox is currently running |
| Uptime | Seconds the engine has been running |
| Messages | Total Discord messages scanned |

**Start Sniper** — connects to Discord and begins monitoring channels.  
**Stop Sniper** — disconnects cleanly. Ping and uptime reset.  
**Pause / Resume** — temporarily stops scanning without disconnecting from Discord.

---

## Blacklist

Users whose messages are always ignored, regardless of keywords or profiles.

To manually block someone:
1. Go to the **Blacklist** page
2. Enter their Discord **User ID** — to find this, right-click their name in Discord (with Developer Mode on) → **Copy User ID**
3. Click **+ Add**

The app looks up their username automatically using your token.

---

## Logs

The Logs page shows a full record of everything the engine has processed. You can filter by log level using the buttons at the top.

**Dev Mode** (`Ctrl+Shift+D`) enables verbose logging — every message the engine receives, every filter decision, every link extraction attempt, and every deduplication step. Useful for diagnosing why something isn't sniping.

---

## Plugins

Plugins let you extend the sniper's behavior without modifying any core code. A plugin is a single `.py` file placed in the `plugins/` folder next to the exe.

**To install a plugin:**
1. Copy the `.py` file into the `plugins/` folder
2. Restart the app
3. The plugin appears in the **Plugins** tab — toggle it on or off with the switch

**To write a plugin**, use `plugins/example_plugin.py` as a starting point. It documents every available hook with parameter descriptions and examples.

Available hooks:

| Function | When it fires |
|----------|--------------|
| `init(engine, ui)` | Once when the engine starts. Store references to engine and UI here |
| `on_start(data)` | Engine started. `data["config"]` is the full SniperConfig |
| `on_stop()` | Engine stopped |
| `on_message_matched(data)` | Message passed the profile filter, before link extraction |
| `on_cooldown_blocked(data)` | Snipe was blocked by cooldown |
| `on_snipe(data)` | Successful snipe — Roblox link has been opened |
| `on_biome_verified(data)` | Anti-bait confirmed the biome is correct |
| `on_biome_left(data)` | Biome watcher detected the biome ended |

---

## Auto-Update

Every time you launch the app, it checks GitHub for new commits. If your build is outdated, the splash screen shows **"Update found"** and runs `build.bat --update` automatically.

The update process:
1. The app closes immediately
2. A build console window opens showing full progress
3. When the build finishes, press any key to launch the new version

---

## Hotkeys

Configure global keyboard shortcuts from the Dashboard page.

| Key | Action |
|-----|--------|
| Toggle key | Start or stop the sniper |
| Pause key | Temporarily pause scanning |

These work system-wide — even when the app window is minimized or in the background.

---

## Troubleshooting

**"Token not configured"** — go to Settings and paste your Discord token.

**"No monitored channels"** — add at least one channel in Settings before starting.

**Sniper connects but nothing happens** — open the Logs page and look for `[FILTER]` lines. Common causes:
- A global blacklist keyword matched — the log will say `[FILTER] Link detected but blocked — global blacklist keyword 'X'`. Check if your message contains a word like `over`, `ended`, or `closed`.
- Trigger keyword doesn't match — double-check the profile's trigger keywords against the actual message content.
- Cooldown is active — the log will say `[COOLDOWN] Blocked — guild cooldown (Xs left)`. Wait or lower the cooldown values.

**Sniper fires but joins wrong server / gets kicked instantly** — the game likely has an auto-rejoin system. Enable **Close Roblox before joining** in the Auto-Join settings.

**Build fails at step 1 (Python not found)** — you either didn't install Python or forgot to tick "Add Python to PATH". Reinstall Python from python.org and make sure that box is checked.

**Build fails at step 4 (clone failed)** — Git couldn't reach GitHub. Try running this in Command Prompt first to cache credentials:
```
git clone https://github.com/gustaslaoq/Sols-RNG-Sniper.git
```

**App shows error on startup after update** — this is a timing issue with PyInstaller's temp extraction. Press any key in the build console to launch manually instead of using the automatic launch.

---

## Disclaimer

This software uses a Discord user account token to automate message monitoring. This may violate Discord's Terms of Service. Use at your own risk. The authors are not responsible for any account actions taken by Discord.

---

## Credits

Inspired by [Sol Sniper V3](https://github.com/vexsyx/sniper-v3) by vexsyx.
