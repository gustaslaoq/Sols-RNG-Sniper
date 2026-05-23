from __future__ import annotations

from datetime import datetime, timezone
import json
import platform
import re
import shutil
import sys
import traceback
import zipfile
from pathlib import Path

from slaoq_sniper_v2.app_paths import (
    app_data_dir,
    app_log_path,
    blacklist_path,
    config_path,
    crash_logs_dir,
    debug_exports_dir,
    history_path,
)
from slaoq_sniper_v2.models import BlacklistEntry, SnipeHistoryEntry


SECRET_PATTERNS = (
    (re.compile(r"(mfa\.[A-Za-z0-9_\-]{20,})"), "token"),
    (re.compile(r"([A-Za-z0-9_\-]{23,28}\.[A-Za-z0-9_\-]{6,7}\.[A-Za-z0-9_\-]{20,})"), "token"),
    (re.compile(r"(https://discord(?:app)?\.com/api/webhooks/[^\s]+)", re.IGNORECASE), "webhook"),
    (re.compile(r"(https?://(?:www\.)?roblox\.com/games/[^\s?]+\?[^\s]*privateServerLinkCode=[^\s]+)", re.IGNORECASE), "roblox_link"),
    (re.compile(r"(https?://(?:www\.)?roblox\.com/share\?code=[^\s&]+(?:&type=Server)?)", re.IGNORECASE), "roblox_link"),
    (re.compile(r"(roblox://[^\s]+)", re.IGNORECASE), "roblox_link"),
)


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def sanitize_text(text: str) -> str:
    sanitized = text
    for pattern, kind in SECRET_PATTERNS:
        if kind == "token":
            sanitized = pattern.sub(lambda match: mask_secret(match.group(1)), sanitized)
        else:
            sanitized = pattern.sub(f"[redacted {kind}]", sanitized)
    return sanitized


def _read_json(path: Path, fallback):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)
    temp_path.replace(path)


def _migrate_legacy_json(path: Path, filename: str) -> None:
    if path.exists():
        return
    for legacy in (
        Path.cwd() / filename,
        Path(sys.executable).resolve().parent / filename,
        Path.home() / ".config" / "slaoq-sniper" / filename,
    ):
        if legacy.exists() and legacy.resolve() != path.resolve():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, path)
            return


def write_crash_report(exc_type, exc_value, exc_traceback) -> Path:
    crash_logs_dir().mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = crash_logs_dir() / f"crash-{timestamp}.log"
    stack = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    content = "\n".join(
        (
            "Slaoq Sniper V2 Crash Report",
            f"Time UTC: {datetime.now(timezone.utc).isoformat()}",
            f"Data Dir: {app_data_dir()}",
            "",
            sanitize_text(stack),
        )
    )
    path.write_text(content, encoding="utf-8")
    return path


def export_debug_report(destination: Path | None = None) -> Path:
    debug_exports_dir().mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = destination or debug_exports_dir() / f"debug-report-{timestamp}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("summary.json", json.dumps(_debug_summary(), indent=2))
        _write_redacted_json(archive, "config.redacted.json", config_path())
        _write_redacted_json(archive, "history.redacted.json", history_path())
        _write_redacted_json(archive, "blacklist.summary.json", blacklist_path(), summarize_blacklist=True)
        _write_redacted_text(archive, "logs/app.log", app_log_path())
        for crash_log in sorted(crash_logs_dir().glob("*.log"))[-5:]:
            _write_redacted_text(archive, f"crash_logs/{crash_log.name}", crash_log)
    return target


def _debug_summary() -> dict:
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "data_dir": "[local app data]",
    }


def _write_redacted_json(
    archive: zipfile.ZipFile,
    name: str,
    path: Path,
    summarize_blacklist: bool = False,
) -> None:
    raw = _read_json(path, {} if summarize_blacklist else None)
    if summarize_blacklist and isinstance(raw, dict):
        payload = {
            "entry_count": len(raw),
            "reasons": sorted({str(item.get("reason", "unknown")) for item in raw.values() if isinstance(item, dict)}),
        }
    else:
        payload = _redact_json(raw)
    archive.writestr(name, json.dumps(payload, indent=2, ensure_ascii=False))


def _write_redacted_text(archive: zipfile.ZipFile, name: str, path: Path) -> None:
    if not path.exists():
        return
    archive.writestr(name, sanitize_text(path.read_text(encoding="utf-8", errors="replace")))


def _redact_json(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(secret in lowered for secret in ("token", "webhook", "url", "uri", "roblox", "ping_target")):
                redacted[key] = "[redacted]" if item else item
            else:
                redacted[key] = _redact_json(item)
        return redacted
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


class BlacklistStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or blacklist_path()
        _migrate_legacy_json(self.path, "blacklist.json")
        self._entries: dict[str, BlacklistEntry] = {}
        self.load()

    def load(self) -> None:
        raw = _read_json(self.path, {})
        if isinstance(raw, list):
            self._entries = {
                str(item.get("user_id", "")): BlacklistEntry.from_dict(str(item.get("user_id", "")), item)
                for item in raw
                if isinstance(item, dict) and str(item.get("user_id", "")).strip()
            }
            if self._entries:
                self.save()
            return
        self._entries = {
            user_id: BlacklistEntry.from_dict(user_id, data)
            for user_id, data in raw.items()
            if isinstance(data, dict)
        } if isinstance(raw, dict) else {}

    def save(self) -> None:
        payload = {user_id: entry.to_dict() for user_id, entry in self._entries.items()}
        _write_json(self.path, payload)

    def add(self, user_id: str, username: str = "unknown", reason: str = "manual") -> None:
        if not user_id.strip():
            return
        existing = self._entries.get(user_id)
        if existing:
            existing.username = username or existing.username
            existing.reason = reason
            existing.count += 1
        else:
            self._entries[user_id] = BlacklistEntry(user_id=user_id.strip(), username=username or "unknown", reason=reason)
        self.save()

    def is_blacklisted(self, user_id: str) -> bool:
        return user_id in self._entries

    def get_entry(self, user_id: str) -> BlacklistEntry | None:
        return self._entries.get(user_id)

    def remove(self, user_id: str) -> None:
        self._entries.pop(user_id, None)
        self.save()

    def clear(self) -> None:
        self._entries.clear()
        self.save()

    def all_entries(self) -> list[BlacklistEntry]:
        return sorted(self._entries.values(), key=lambda entry: entry.last_event, reverse=True)


class HistoryStore:
    def __init__(self, path: Path | None = None, limit: int = 500) -> None:
        self.path = path or history_path()
        _migrate_legacy_json(self.path, "snipe_history.json")
        self.limit = limit
        self._entries: list[SnipeHistoryEntry] = []
        self.load()

    def load(self) -> None:
        raw = _read_json(self.path, [])
        self._entries = [SnipeHistoryEntry.from_dict(item) for item in raw if isinstance(item, dict)]

    def save(self) -> None:
        payload = [entry.to_dict() for entry in self._entries[: self.limit]]
        _write_json(self.path, payload)

    def add(self, entry: SnipeHistoryEntry) -> None:
        entry.raw_message = sanitize_text(entry.raw_message)
        entry.roblox_url = sanitize_text(entry.roblox_url)
        self._entries.insert(0, entry)
        self._entries = self._entries[: self.limit]
        self.save()

    def update_latest_biome_result(self, expected: str, detected: str, matched: bool) -> bool:
        expected_key = expected.strip().upper()
        for entry in self._entries:
            entry_expected = entry.expected_biome.strip().upper()
            if entry.biome_verified is not None:
                continue
            if entry_expected and entry_expected != expected_key:
                continue
            entry.expected_biome = expected
            entry.detected_biome = detected
            entry.biome_verified = matched
            self.save()
            return True
        return False

    def clear(self) -> None:
        self._entries.clear()
        self.save()

    def all_entries(self) -> list[SnipeHistoryEntry]:
        return list(self._entries)
