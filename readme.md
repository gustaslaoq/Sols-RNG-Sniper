<div align="center">

<img src="https://raw.githubusercontent.com/gustaslaoq/Sols-RNG-Sniper/main/assets/logo.png" width="92" height="92" />

# Slaoq's Sol's RNG Sniper V2

Automatic private server sniper for **Sol's RNG** on Roblox.

The app monitors Discord channels, detects matching private server links, and opens Roblox automatically.

[![Windows](https://img.shields.io/badge/Windows-10%2B-0078d4?style=flat-square&logo=windows&logoColor=white)](#requirements)
[![Download](https://img.shields.io/badge/Download-GitHub%20Releases-00c853?style=flat-square&logo=github)](https://github.com/gustaslaoq/Sols-RNG-Sniper/releases)
[![Version](https://img.shields.io/badge/Version-2.0.1-white?style=flat-square)](#)

</div>

---

## Read This First

This sniper uses a **Discord user account token** to read messages. This is user-account automation/selfbot behavior and may violate Discord's Terms of Service.

Important recommendations:

- Use an alternate Discord account, not your main account.
- Never share your Discord token.
- Never share webhook URLs.
- Never publish logs/configs that may contain private server links.
- The Discord account must be in the servers and channels you want to monitor.
- Use this tool at your own risk.

The app redacts Discord tokens, webhook URLs, and Roblox private links in logs/debug exports, but you should still treat your local data as sensitive.

---

## Quick Start

Read only this section if you want the shortest setup path.

1. Download `SlaoqSniper.exe` from the latest GitHub Release.
2. Open the app.
3. Go to **Settings** and paste your Discord token.
4. Go to **Channels** and confirm the default Sol's RNG channels are enabled.
5. Go to **Profiles** and enable the profiles you want.
6. Make sure Roblox is installed.
7. Click **Start Sniper** on the Home page.

For the sniper to work, the Discord account used by the sniper must be inside the Sol's RNG server and must have permission to read the private-server-link channels. You can access the server channel here:

https://discord.com/channels/1186570213077041233/1435494951050805338

---

## Requirements

- At least Windows 10
- Roblox installed
- A Discord account that can access the channels you want to monitor
- The Discord token for that account
- A stable internet connection

Normal users do not need Python, Git, pip, or any development tools.

---

## Download

1. Open the [**Releases**](https://github.com/gustaslaoq/Sols-RNG-Sniper/releases) page for this repository.
2. Download `SlaoqSniper.exe`.
3. Put the executable in its own folder.
4. Run it.

Windows SmartScreen may show a warning because the executable is not digitally signed.

---

## Main Tutorial

This section explains the normal setup flow without going too deep into every advanced option.

### 1. Get Your Discord Token

Using an alternate account is strongly recommended.

1. Open https://discord.com/app in your browser.
2. Log in to the Discord account that the sniper will use.
3. Press `F12` or `Ctrl+Shift+I`.
4. Open the **Network** tab.
5. Type `science` in the request filter.
6. Click one of the requests that appears.
7. Look in **Request Headers** for `Authorization`.
8. Copy the full value.
9. Paste it into **Settings > Discord Token** in the app.

If no `science` request appears, change channels in Discord or refresh the page with `Ctrl+R` while DevTools is open.

Do not share this token. Anyone with it can access the account.

### 2. Check Monitored Channels

V2 already includes two enabled Sol's RNG channels:

```text
1282542323590496277 / 🌌・biomes
1282543762425516083 / 🃏・merchants
```

Open **Channels** and confirm they are enabled.

To add another channel:

1. Enable **Developer Mode** in Discord.
2. Right-click the server icon and choose **Copy Server ID**.
3. Right-click the channel and choose **Copy Channel ID**.
4. Paste both IDs into the **Channels** page.
5. Click **Add Channel**.

The token account must be able to read the channel. If the account cannot access the channel, the sniper cannot see messages from it.

### 3. Enable Profiles

Profiles decide what counts as a snipe.

Default profile groups:

- **Biomes**: Dreamspace, Cyberspace, Glitched
- **Merchants**: Mari, Jester, Rin
- **Items**: Void Coin, Oblivion Potion
- **System**: Global blacklist terms for bait/fake messages

Recommended first setup:

1. Open **Profiles**.
2. Pick a category.
3. Enable the profiles you care about.
4. Adjust keywords only if needed.

Biome profiles can use anti-bait biome verification. Item and merchant profiles usually do not need biome verification.

### 4. Configure Auto-Join

Open **Settings**.

Useful settings:

- **Auto-join on snipe**: opens Roblox when a matching link is detected.
- **Close Roblox before joining**: closes the current Roblox process before joining.
- **Join delay**: waits before opening the link.
- **Auto-pause after snipe**: pauses scanning after a successful snipe.
- **When biome ends**: chooses what the app does after the target biome ends.

Recommended starting values:

```text
Auto-join: On
Close Roblox before joining: Off
Join delay: 0-500 ms
Auto-pause after snipe: 15-60 s
When biome ends: Do nothing or Return to home
```

### 5. Start the Sniper

On the **Home** page:

1. Make sure the token is saved.
2. Make sure at least one channel is enabled.
3. Make sure at least one profile is enabled.
4. Click **Start Sniper**.

The Home page shows connection status, Discord ping, scanned messages, successful snipes, uptime, and Roblox process status.

---

## Discord Webhook

Webhooks are optional. They send Discord embeds when important events happen.

Supported events:

- Snipe detected
- Biome verification result
- Sniper started
- Sniper stopped

Setup:

1. Open your Discord server settings.
2. Go to **Integrations > Webhooks**.
3. Create a webhook.
4. Copy the webhook URL.
5. Paste it in **Notifications > Discord Webhook**.
6. Enable the events you want.

You can also configure a user or role ping. If you use a user/role ID, test the webhook once and confirm the mention is formatted correctly.

Never share the webhook URL. Anyone with it can send messages to that webhook channel.

---

## Extra Accounts

Extra accounts are additional Discord tokens used only for listening. They can help when one account receives messages slowly or inconsistently.

Recommendations:

- Use an alternate account for the main token.
- Use extra accounts only if you understand the risk.
- Do not use accounts you cannot afford to lose.

This is also user-account automation and may cause Discord account restrictions or bans.

---

## Blacklist and Anti-Bait

### Blacklist

The blacklist blocks specific Discord users from triggering snipes.

You can:

- add users manually;
- remove users;
- clear the list;
- auto-blacklist users who delete a message that triggered a snipe.

### Delete Watch

The **Blacklist** page includes a watch window setting. It controls how long the app watches whether a sniped message gets deleted.

Example:

```text
Watch window: 30 s
```

If the author deletes the triggering message during that time, the user is added to the blacklist.

### Biome Verification

For biome profiles, the app can read Roblox logs to verify the actual biome after joining.

If the detected biome does not match the expected biome, the app can close Roblox depending on the profile and **When biome ends** settings.

---

## Where Data Is Stored

User data is stored in:

```text
%LOCALAPPDATA%\SlaoqSniper\
```

Common files:

```text
config.json
blacklist.json
snipe_history.json
logs\
crash_logs\
update_temp\
debug_exports\
```

These files may contain sensitive information. Do not upload your local data folder.

---

## Updates

V2 updates through GitHub Releases.

Public releases should include:

```text
SlaoqSniper.exe
manifest.json
```

The app checks the manifest, compares versions, downloads the new executable, verifies SHA256, and only then replaces the old file.

---

## Troubleshooting

### The app opens, but nothing is detected

Check:

- the Discord token is saved;
- the token account is in the server;
- the token account can read the monitored channels;
- channels are enabled in **Channels**;
- at least one profile is enabled;
- logs are not showing cooldown, blacklist, or filter mismatch messages.

### Invalid token

Get the token again from the browser. Tokens can stop working after logging out, changing password, or Discord invalidating the session.

### Roblox does not open

Check:

- Roblox is installed;
- `roblox://` links work on Windows;
- Auto-join is enabled;
- antivirus/security tools are not blocking the app.

### The sniper joins the wrong biome

Enable biome verification for biome profiles and check the wrong-biome action settings.

### Webhook does not send

Check:

- the webhook URL is correct;
- the webhook still exists in Discord;
- the event is enabled in the app;
- the webhook channel allows messages.

### Config reset or disappeared

Check:

```text
%LOCALAPPDATA%\SlaoqSniper\
```

If `config.json.corrupt` exists, the app found invalid JSON and reset to defaults.

---

## For Developers

Normal users do not need this section.

Development install:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Run from source:

```powershell
.\.venv\Scripts\python.exe main.py
```

Build the executable:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --onefile --noconsole --name SlaoqSniper --icon assets\app_icon.ico --paths . --add-data "assets;assets" main.py
```

Generate a release manifest:

```powershell
.\.venv\Scripts\python.exe .\release\make_manifest.py --version 2.0.1 --exe .\dist\SlaoqSniper.exe --output .\manifest.json --notes-file .\release-notes.txt
```

Main public source layout:

```text
main.py
sniper_engine.py
slaoq_sniper_v2/
release/
assets/
requirements.txt
requirements-dev.txt
readme.md
```

Do not commit user configs, logs, `.exe` files, `.venv`, `dist`, `build`, or local planning notes.

---

## Final Disclaimer

This project automates message monitoring through a Discord user token. This may violate Discord's Terms of Service and may result in account restrictions or bans.

Use it responsibly, preferably with an alternate account, and never share tokens, webhooks, sensitive logs, or private server links.

---

## Credits

Inspired by [Sol Sniper V3](https://github.com/vexsyx/sniper-v3) by vexsyx
