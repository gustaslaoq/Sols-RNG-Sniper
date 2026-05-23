from __future__ import annotations

import sys
import logging
import ctypes
from pathlib import Path
from typing import Literal

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from slaoq_sniper_v2.app_info import APP_DISPLAY_NAME, APP_NAME, APP_VERSION
from slaoq_sniper_v2.app_paths import app_log_path, asset_path, ensure_app_dirs
from slaoq_sniper_v2.config import ConfigStore
from slaoq_sniper_v2.engine_adapter import EngineAdapter
from slaoq_sniper_v2.performance import detect_performance_profile
from slaoq_sniper_v2.storage import BlacklistStore, HistoryStore, write_crash_report
from slaoq_sniper_v2.storage import sanitize_text
from slaoq_sniper_v2.theme import app_stylesheet
from slaoq_sniper_v2.ui import StartupSplash, UpdatePromptDialog, create_window
from slaoq_sniper_v2.updater import (
    ReleaseManifest,
    UpdateInfo,
    UpdaterClient,
    load_update_preferences,
    remember_auto_update,
    remember_skipped_update,
)


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize_text(str(record.getMessage()))
        record.args = ()
        return True


def setup_logging() -> None:
    root = logging.getLogger("slaoq_sniper_v2")
    for handler in list(root.handlers):
        root.removeHandler(handler)

    try:
        handler = logging.FileHandler(app_log_path(), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handler.addFilter(SecretFilter())
    except OSError:
        handler = logging.NullHandler()

    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.propagate = False


def install_crash_hook() -> None:
    original_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        try:
            path = write_crash_report(exc_type, exc_value, exc_traceback)
            logging.getLogger("slaoq_sniper_v2.app").error("Unhandled exception written to %s", path)
        except Exception:
            logging.getLogger("slaoq_sniper_v2.app").error("Unhandled exception could not be written to crash log")
        finally:
            original_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception


def install_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Slaoq.SolsRngSniper.V2")
    except Exception:
        logging.getLogger("slaoq_sniper_v2.app").debug("Could not set Windows app user model id", exc_info=True)


class UpdateWorker(QObject):
    checked = Signal(object)
    downloaded = Signal(object)
    progress = Signal(int)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, mode: Literal["check", "download"], update: UpdateInfo | None = None) -> None:
        super().__init__()
        self._mode = mode
        self._update = update
        self._client = UpdaterClient()

    def run(self) -> None:
        try:
            if self._mode == "check":
                self.checked.emit(self._client.check(APP_VERSION))
            elif self._update:
                path = self._client.download(self._update, self._on_progress)
                self.downloaded.emit(path)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def _on_progress(self, downloaded: int, total: int) -> None:
        if total <= 0:
            self.progress.emit(0)
            return
        self.progress.emit(min(100, int(downloaded * 100 / total)))


class StartupController(QObject):
    def __init__(self, app: QApplication, splash: StartupSplash, window) -> None:
        super().__init__()
        self._app = app
        self._splash = splash
        self._window = window
        self._threads: list[QThread] = []
        self._min_splash_done = False
        self._open_requested = False
        self._opened = False
        self._dialog_open = False
        self._update_check_pending = False
        self._update_prompt: UpdatePromptDialog | None = None
        QTimer.singleShot(850, self._mark_min_splash_done)
        QTimer.singleShot(7000, self._force_open)

    def start(self) -> None:
        self._splash.set_phase("Startup")
        self._splash.set_progress(14)
        if "--force-update-prompt" in sys.argv:
            self._splash.set_phase("Update")
            self._splash.set_message("Update detected")
            self._splash.set_progress(100)
            QTimer.singleShot(520, self._show_forced_update_prompt)
            return
        if self._should_check_updates():
            self._splash.set_phase("Check")
            self._splash.set_message("Checking for updates")
            self._splash.set_progress(28)
            self._start_worker(UpdateWorker("check"))
        else:
            self._splash.set_message("Opening workspace")
            self._splash.set_progress(82)
            self._open_when_ready()

    def _mark_min_splash_done(self) -> None:
        self._min_splash_done = True
        if self._open_requested:
            self._open_when_ready()

    def _should_check_updates(self) -> bool:
        if "--skip-update-check" in sys.argv or "--smoke-test" in sys.argv:
            return False
        return bool(getattr(sys, "frozen", False) or "--force-update-check" in sys.argv)

    def _start_worker(self, worker: UpdateWorker) -> None:
        thread = QThread(self)
        self._threads.append(thread)
        if worker._mode == "check":
            self._update_check_pending = True
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.checked.connect(self._on_update_checked)
        worker.downloaded.connect(self._on_update_downloaded)
        worker.progress.connect(self._on_update_progress)
        worker.failed.connect(self._on_update_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.start()

    def _on_update_checked(self, update: UpdateInfo | None) -> None:
        self._update_check_pending = False
        if update is None:
            self._splash.set_message("No updates found")
            self._splash.set_progress(74)
            self._open_when_ready()
            return
        if update.required:
            self._splash.set_phase("Update")
            self._splash.set_message(f"Required update v{update.manifest.version}")
            self._splash.set_progress(100)
            QTimer.singleShot(420, lambda: self._download_update(update))
            return
        preferences = load_update_preferences()
        if preferences.auto_update:
            self._splash.set_phase("Update")
            self._splash.set_message(f"Auto-updating to v{update.manifest.version}")
            self._splash.set_progress(100)
            QTimer.singleShot(420, lambda: self._download_update(update))
            return
        if preferences.should_skip(update.manifest.version):
            self._splash.set_message(f"Skipped update v{update.manifest.version}")
            self._splash.set_progress(74)
            self._open_when_ready()
            return
        self._splash.set_phase("Update")
        self._splash.set_message("Update detected")
        self._splash.set_progress(100)
        QTimer.singleShot(520, lambda: self._show_optional_update_prompt(update))

    def _show_forced_update_prompt(self) -> None:
        update = UpdateInfo(
            manifest=ReleaseManifest(
                version="2.0.1",
                mandatory=False,
                min_supported_version="0.0.0",
                asset_name="SlaoqSniper.exe",
                sha256="",
                notes=(
                    "Local update prompt preview.\n\n"
                    "- This mode only verifies the confirmation window.\n"
                    "- Dismiss opens the app normally.\n"
                    "- Update returns to the splash without installing anything."
                ),
            ),
            exe_url="",
            release_url="local prompt preview",
            required=False,
        )
        self._show_optional_update_prompt(update)

    def _show_optional_update_prompt(self, update: UpdateInfo) -> None:
        if self._opened:
            return
        self._dialog_open = True
        self._splash.close()
        dialog = UpdatePromptDialog(APP_VERSION, update.manifest.version, update.manifest.notes)
        self._update_prompt = dialog
        dialog.accepted.connect(lambda: self._on_optional_update_accepted(update))
        dialog.rejected.connect(lambda: self._on_optional_update_dismissed(update))
        dialog.finished.connect(lambda _result: setattr(self, "_dialog_open", False))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        QTimer.singleShot(40, dialog.raise_)
        QTimer.singleShot(60, dialog.activateWindow)

    def _on_optional_update_accepted(self, update: UpdateInfo) -> None:
        remember = bool(self._update_prompt and self._update_prompt.remember_decision())
        self._update_prompt = None
        self._dialog_open = False
        self._splash.show_centered()
        if not update.exe_url:
            self._splash.set_phase("Update")
            self._splash.set_message("Update preview complete")
            self._splash.set_progress(100)
            QTimer.singleShot(820, self._open_when_ready)
            return
        if remember:
            remember_auto_update()
        self._download_update(update)

    def _on_optional_update_dismissed(self, update: UpdateInfo) -> None:
        prompt = self._update_prompt
        if prompt and prompt.remember_decision() and update.exe_url:
            remember_skipped_update(update.manifest.version)
        self._update_prompt = None
        self._dialog_open = False
        if self._opened:
            return
        self._opened = True
        self._show_window()

    def _download_update(self, update: UpdateInfo) -> None:
        self._splash.set_phase("Download")
        self._splash.set_message("Downloading update")
        self._splash.set_progress(0)
        self._start_worker(UpdateWorker("download", update))

    def _on_update_progress(self, progress: int) -> None:
        self._splash.set_progress(progress)
        self._splash.set_message(f"Downloading update ({progress}%)")

    def _on_update_downloaded(self, path: Path) -> None:
        self._splash.set_phase("Install")
        self._splash.set_message("Installing update")
        try:
            UpdaterClient().install_on_exit(path)
        except Exception as exc:
            self._on_update_failed(str(exc))
            return
        self._show_message(
            QMessageBox.Icon.Information,
            "Update Ready",
            "The update was verified and will be installed after the app closes.",
        )
        self._app.quit()

    def _on_update_failed(self, message: str) -> None:
        self._update_check_pending = False
        logging.getLogger("slaoq_sniper_v2.app").warning("Update flow failed: %s", message)
        self._splash.set_progress(72)
        self._show_message(
            QMessageBox.Icon.Warning,
            "Update Failed",
            f"The app could not complete the update check.\n\n{message}",
        )
        self._splash.set_message("Opening workspace")
        self._open_when_ready()

    def _show_question(self, title: str, text: str, detail: str) -> QMessageBox.StandardButton:
        box = self._message_box(QMessageBox.Icon.Question, title, text, detail)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        return QMessageBox.StandardButton(box.exec())

    def _show_message(self, icon: QMessageBox.Icon, title: str, text: str) -> None:
        box = self._message_box(icon, title, text, "")
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def _message_box(self, icon: QMessageBox.Icon, title: str, text: str, detail: str) -> QMessageBox:
        self._dialog_open = True
        self._splash.show()
        self._splash.raise_()
        self._splash.activateWindow()
        box = QMessageBox(self._splash)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        if detail:
            box.setInformativeText(detail)
        box.setWindowModality(Qt.WindowModality.ApplicationModal)
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        box.finished.connect(lambda _result: setattr(self, "_dialog_open", False))
        QTimer.singleShot(30, box.raise_)
        QTimer.singleShot(35, box.activateWindow)
        return box

    def _open_when_ready(self) -> None:
        if self._opened:
            return
        if not self._min_splash_done:
            self._open_requested = True
            QTimer.singleShot(80, self._open_when_ready)
            return
        self._opened = True
        self._splash.set_phase("Ready")
        self._splash.set_message("Ready")
        self._splash.set_progress(100)
        QTimer.singleShot(560, self._show_window)

    def _show_window(self) -> None:
        self._splash.close()
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _force_open(self) -> None:
        if self._opened:
            return
        if self._update_check_pending:
            self._splash.set_message("Still checking for updates")
            QTimer.singleShot(7000, self._force_open)
            return
        if self._dialog_open:
            QTimer.singleShot(7000, self._force_open)
            return
        logging.getLogger("slaoq_sniper_v2.app").warning("Startup splash timeout reached; opening workspace")
        self._min_splash_done = True
        self._splash.set_message("Opening workspace")
        self._splash.set_progress(96)
        self._open_when_ready()


def main() -> int:
    ensure_app_dirs()
    setup_logging()
    install_crash_hook()
    logging.getLogger("slaoq_sniper_v2.app").info("Starting V2 shell")
    performance = detect_performance_profile()
    logging.getLogger("slaoq_sniper_v2.app").info("Performance profile: %s", performance.name)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    install_windows_app_id()
    app.setWindowIcon(QIcon(str(asset_path("runtime_icon.ico"))))
    app.setStyleSheet(app_stylesheet())

    config_store = ConfigStore()
    blacklist_store = BlacklistStore()
    history_store = HistoryStore()
    adapter = EngineAdapter(config_store, blacklist_store, history_store)
    window = create_window(adapter, config_store, blacklist_store, history_store)

    if "--smoke-test" in sys.argv:
        QTimer.singleShot(100, app.quit)
    else:
        splash = StartupSplash()
        splash.show_centered()
        controller = StartupController(app, splash, window)
        app._slaoq_startup_controller = controller
        controller.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
