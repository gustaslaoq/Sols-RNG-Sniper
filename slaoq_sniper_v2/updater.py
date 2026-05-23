from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from packaging.version import InvalidVersion, Version

from slaoq_sniper_v2.app_info import GITHUB_OWNER, GITHUB_REPO
from slaoq_sniper_v2.app_paths import update_preferences_path, update_temp_dir
from slaoq_sniper_v2.performance import detect_performance_profile


logger = logging.getLogger("slaoq_sniper_v2.updater")


ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    mandatory: bool
    min_supported_version: str
    asset_name: str
    sha256: str
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ReleaseManifest":
        return cls(
            version=str(data["version"]),
            mandatory=bool(data.get("mandatory", False)),
            min_supported_version=str(data.get("min_supported_version", "0.0.0")),
            asset_name=str(data["asset_name"]),
            sha256=str(data["sha256"]).lower(),
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True)
class UpdateInfo:
    manifest: ReleaseManifest
    exe_url: str
    release_url: str
    required: bool


@dataclass
class UpdatePreferences:
    auto_update: bool = False
    skipped_version: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "UpdatePreferences":
        return cls(
            auto_update=bool(data.get("auto_update", False)),
            skipped_version=str(data.get("skipped_version", "")),
        )

    def to_dict(self) -> dict:
        return {
            "auto_update": self.auto_update,
            "skipped_version": self.skipped_version,
        }

    def should_skip(self, version: str) -> bool:
        return bool(self.skipped_version and normalize_version(self.skipped_version) == normalize_version(version))


def load_update_preferences() -> UpdatePreferences:
    path = update_preferences_path()
    if not path.exists():
        return UpdatePreferences()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read update preferences; using defaults", exc_info=True)
        return UpdatePreferences()
    if not isinstance(raw, dict):
        return UpdatePreferences()
    return UpdatePreferences.from_dict(raw)


def save_update_preferences(preferences: UpdatePreferences) -> None:
    path = update_preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(preferences.to_dict(), indent=2), encoding="utf-8")


def remember_auto_update() -> None:
    save_update_preferences(UpdatePreferences(auto_update=True, skipped_version=""))


def remember_skipped_update(version: str) -> None:
    save_update_preferences(UpdatePreferences(auto_update=False, skipped_version=version))


def normalize_version(value: str) -> Version:
    cleaned = value.strip()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    if cleaned.endswith("-dev"):
        cleaned = cleaned[:-4]
    try:
        return Version(cleaned)
    except InvalidVersion:
        return Version("0.0.0")


class UpdaterClient:
    def __init__(self, owner: str = GITHUB_OWNER, repo: str = GITHUB_REPO) -> None:
        self.owner = owner
        self.repo = repo
        self.api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        self.timeout_s = detect_performance_profile().update_check_timeout_s

    def check(self, current_version: str) -> UpdateInfo | None:
        local_update = self._check_local_override(current_version)
        if local_update is not None:
            return local_update

        release = self._get_json(self.api_url)
        assets = release.get("assets", [])
        manifest_asset = self._find_asset(assets, "manifest.json")
        if not manifest_asset:
            raise RuntimeError("The latest release does not include manifest.json.")

        manifest_raw = self._get_json(manifest_asset["browser_download_url"])
        manifest = ReleaseManifest.from_dict(manifest_raw)
        current = normalize_version(current_version)
        latest = normalize_version(manifest.version)
        min_supported = normalize_version(manifest.min_supported_version)

        if current >= latest and current >= min_supported:
            return None

        exe_asset = self._find_asset(assets, manifest.asset_name)
        if not exe_asset:
            raise RuntimeError(f"The latest release does not include {manifest.asset_name}.")

        required = manifest.mandatory or current < min_supported
        return UpdateInfo(
            manifest=manifest,
            exe_url=exe_asset["browser_download_url"],
            release_url=release.get("html_url", ""),
            required=required,
        )

    def download(self, update: UpdateInfo, progress: ProgressCallback | None = None) -> Path:
        update_temp_dir().mkdir(parents=True, exist_ok=True)
        destination = update_temp_dir() / update.manifest.asset_name
        self._download_file(update.exe_url, destination, progress)
        actual_hash = sha256_file(destination)
        if actual_hash.lower() != update.manifest.sha256.lower():
            destination.unlink(missing_ok=True)
            raise RuntimeError("Downloaded update failed SHA256 verification.")
        logger.info("Downloaded and verified update %s", update.manifest.version)
        return destination

    def install_on_exit(self, downloaded_exe: Path, current_exe: Path | None = None) -> None:
        current = current_exe or current_executable_path()
        script = update_temp_dir() / "install_update.ps1"
        script.write_text(_install_script(downloaded_exe, current), encoding="utf-8")
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(script),
            ],
            close_fds=True,
        )

    def _check_local_override(self, current_version: str) -> UpdateInfo | None:
        manifest_source = os.getenv("SLAOQ_SNIPER_UPDATE_MANIFEST", "").strip()
        if not manifest_source:
            return None
        manifest = ReleaseManifest.from_dict(self._get_json(manifest_source))
        current = normalize_version(current_version)
        latest = normalize_version(manifest.version)
        min_supported = normalize_version(manifest.min_supported_version)
        if current >= latest and current >= min_supported:
            return None
        exe_source = os.getenv("SLAOQ_SNIPER_UPDATE_EXE", "").strip()
        if not exe_source:
            manifest_path = Path(manifest_source)
            if manifest_path.exists():
                exe_source = str(manifest_path.with_name(manifest.asset_name))
        if not exe_source:
            raise RuntimeError("SLAOQ_SNIPER_UPDATE_EXE must point to a local test executable.")
        required = manifest.mandatory or current < min_supported
        return UpdateInfo(
            manifest=manifest,
            exe_url=exe_source,
            release_url="local update test",
            required=required,
        )

    def _get_json(self, url: str) -> dict:
        local_path = Path(url)
        if local_path.exists():
            return json.loads(local_path.read_text(encoding="utf-8"))
        request = urllib.request.Request(url, headers={"User-Agent": "SlaoqSniperV2"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Failed to read update metadata: {exc}") from exc

    @staticmethod
    def _find_asset(assets: list[dict], name: str) -> dict | None:
        return next((asset for asset in assets if asset.get("name") == name), None)

    def _download_file(self, url: str, destination: Path, progress: ProgressCallback | None) -> None:
        local_path = Path(url)
        if local_path.exists():
            total = local_path.stat().st_size
            copied = 0
            with local_path.open("rb") as source, destination.open("wb") as target:
                while True:
                    chunk = source.read(1024 * 256)
                    if not chunk:
                        break
                    target.write(chunk)
                    copied += len(chunk)
                    if progress:
                        progress(copied, total)
            return
        request = urllib.request.Request(url, headers={"User-Agent": "SlaoqSniperV2"})
        with urllib.request.urlopen(request, timeout=max(30, self.timeout_s * 2)) as response:
            total = int(response.headers.get("Content-Length", "0") or 0)
            downloaded = 0
            with destination.open("wb") as file:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    file.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_executable_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    raise RuntimeError("Update installation is only available from the packaged executable.")


def _install_script(downloaded_exe: Path, current_exe: Path) -> str:
    src = str(downloaded_exe).replace("'", "''")
    dst = str(current_exe).replace("'", "''")
    return f"""
$ErrorActionPreference = 'Stop'
$src = '{src}'
$dst = '{dst}'
$processName = [System.IO.Path]::GetFileNameWithoutExtension($dst)

while (Get-Process -Name $processName -ErrorAction SilentlyContinue) {{
    Start-Sleep -Milliseconds 300
}}

Move-Item -Force -LiteralPath $src -Destination $dst

Get-ChildItem Env: | Where-Object {{ $_.Name -like '_PYI_*' -or $_.Name -eq 'PYINSTALLER_RESET_ENVIRONMENT' }} | ForEach-Object {{
    Remove-Item -LiteralPath "Env:$($_.Name)" -ErrorAction SilentlyContinue
}}
$env:PYINSTALLER_RESET_ENVIRONMENT = '1'
Start-Process -FilePath $dst
""".strip()
