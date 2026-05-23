from __future__ import annotations

import os
import sys
from pathlib import Path

from slaoq_sniper_v2.app_info import APP_DATA_DIR_NAME


def app_data_dir() -> Path:
    override = os.getenv("SLAOQ_SNIPER_DATA_DIR")
    if override:
        return Path(override)
    local_app_data = os.getenv("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is not available.")
    return Path(local_app_data) / APP_DATA_DIR_NAME


def config_path() -> Path:
    return app_data_dir() / "config.json"


def blacklist_path() -> Path:
    return app_data_dir() / "blacklist.json"


def history_path() -> Path:
    return app_data_dir() / "snipe_history.json"


def crash_logs_dir() -> Path:
    return app_data_dir() / "crash_logs"


def logs_dir() -> Path:
    return app_data_dir() / "logs"


def app_log_path() -> Path:
    return logs_dir() / "app.log"


def update_temp_dir() -> Path:
    return app_data_dir() / "update_temp"


def update_preferences_path() -> Path:
    return app_data_dir() / "update_preferences.json"


def debug_exports_dir() -> Path:
    return app_data_dir() / "debug_exports"


def asset_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "assets" / name
    root = Path(__file__).resolve().parents[1]
    return root / "assets" / name


def _ensure_dir(path: Path, required: bool = False) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return
    except FileExistsError:
        pass
    except PermissionError:
        if required:
            raise
        return

    try:
        if path.is_file():
            for index in range(1, 100):
                backup = path.with_name(f"{path.name}.file-backup-{index}")
                if not backup.exists():
                    path.replace(backup)
                    path.mkdir(parents=True, exist_ok=True)
                    return
    except OSError:
        if required:
            raise


def ensure_app_dirs() -> None:
    _ensure_dir(app_data_dir(), required=True)
    for path in (crash_logs_dir(), logs_dir(), update_temp_dir(), debug_exports_dir()):
        _ensure_dir(path)
