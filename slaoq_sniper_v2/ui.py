from __future__ import annotations

from collections.abc import Callable
from html import escape
import json
import os
import threading
import urllib.error
import urllib.request

import ctypes

from PySide6.QtCore import Property, QEvent, QEasingCurve, QObject, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QMouseEvent, QPainter, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QSizeGrip,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QSystemTrayIcon,
)

from slaoq_sniper_v2.app_info import APP_DISPLAY_NAME, APP_VERSION
from slaoq_sniper_v2.app_paths import asset_path
from slaoq_sniper_v2.config import ConfigStore
from slaoq_sniper_v2.engine_adapter import EngineAdapter, EngineMetrics
from slaoq_sniper_v2.icons import icon
from slaoq_sniper_v2.models import ChannelConfig, SnipeProfile
from slaoq_sniper_v2.storage import BlacklistStore, HistoryStore, export_debug_report, sanitize_text
from slaoq_sniper_v2.theme import SIDEBAR_COLLAPSED, SIDEBAR_EXPANDED, TITLE_BAR_HEIGHT

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


PAGES = (
    ("home", "Home", "home"),
    ("settings", "Settings", "settings"),
    ("channels", "Channels", "server"),
    ("profiles", "Profiles", "target"),
    ("notifications", "Notifications", "bell"),
    ("blacklist", "Blacklist", "lock"),
    ("logs", "Logs", "logs"),
    ("history", "History", "clock"),
)

BASE_PROFILE_CATEGORIES = ("Biomes", "Merchants", "Items")


LOG_LEVEL_COLORS = {
    "SUCCESS": "#00d084",
    "SNIPE": "#f5f5f5",
    "ERROR": "#ff4d4f",
    "WARNING": "#f5a524",
    "WARN": "#f5a524",
    "DEBUG": "#8b8b8b",
    "INFO": "#d8d8d8",
}


class _WinMsg(ctypes.Structure):
    _fields_ = (
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_size_t),
        ("time", ctypes.c_uint),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    )


WM_NCHITTEST = 0x0084
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17


def colored_log_line(level: str, message: str) -> str:
    normalized = level.upper()
    color = LOG_LEVEL_COLORS.get(normalized, "#d8d8d8")
    weight = "700" if normalized in {"SUCCESS", "SNIPE", "ERROR"} else "500"
    return (
        f'<span style="color:{color}; font-weight:{weight};">[{escape(normalized)}]</span>'
        f' <span style="color:#f5f5f5;">{escape(message)}</span>'
    )


def label(text: str, role: str | None = None) -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    widget.setWordWrap(True)
    return widget


def card() -> QFrame:
    frame = QFrame()
    frame.setProperty("role", "card")
    return frame


class AnimatedButton(QPushButton):
    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self._base_height = 34
        self._motion = "lift"
        self._normal_font = QFont(self.font())
        self._rest_geometry: QRect | None = None
        self._geometry_anim = QPropertyAnimation(self, b"geometry", self)
        self._geometry_anim.setDuration(135)
        self._geometry_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setMinimumHeight(self._base_height)
        self.setMaximumHeight(self._base_height + 2)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)
        if not enabled:
            self._clear_hover_state()

    def set_animation_height(self, height: int) -> None:
        self._base_height = height
        self.setMinimumHeight(height)
        self.setMaximumHeight(height + 2)

    def set_hover_motion(self, motion: str) -> None:
        self._motion = motion

    def enterEvent(self, event) -> None:
        if self.isEnabled():
            self._rest_geometry = self.geometry()
            self._apply_hover_state()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self.isEnabled():
            self._clear_hover_state()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self._apply_press_state()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.isEnabled():
            self._apply_hover_state() if self.underMouse() else self._clear_hover_state()
        super().mouseReleaseEvent(event)

    def _apply_hover_state(self) -> None:
        font = QFont(self._normal_font)
        if self._motion == "sidebar":
            font.setBold(True)
            font.setPointSize(max(font.pointSize() + 1, font.pointSize()))
        elif self._motion == "none":
            return
        self.setFont(font)
        self._animate_geometry(self._hover_geometry(), 150)

    def _apply_press_state(self) -> None:
        if self._motion == "none":
            return
        self._animate_geometry(self._pressed_geometry(), 80)

    def _clear_hover_state(self) -> None:
        self.setFont(QFont(self._normal_font))
        self._animate_geometry(self._rest_geometry, 155)

    def _hover_geometry(self) -> QRect:
        base = self._rest_geometry or self.geometry()
        if self._motion == "sidebar":
            return QRect(base.x() + 3, base.y() - 1, max(1, base.width() - 3), base.height() + 1)
        if self._motion == "none":
            return base
        return QRect(base.x() - 2, base.y() - 1, base.width() + 4, base.height() + 2)

    def _pressed_geometry(self) -> QRect:
        base = self._rest_geometry or self.geometry()
        if self._motion == "sidebar":
            return QRect(base.x() + 1, base.y(), max(1, base.width() - 1), base.height())
        if self._motion == "none":
            return base
        return QRect(base.x() + 1, base.y() + 1, max(1, base.width() - 2), max(1, base.height() - 2))

    def _animate_geometry(self, target: QRect | None, duration: int) -> None:
        if target is None:
            return
        self._geometry_anim.stop()
        self._geometry_anim.setDuration(duration)
        self._geometry_anim.setStartValue(self.geometry())
        self._geometry_anim.setEndValue(target)
        self._geometry_anim.start()


def button(text: str, icon_key: str | None = None, variant: str | None = None, color: str = "#b8b8b8") -> QPushButton:
    widget = AnimatedButton(text)
    if icon_key:
        widget.setIcon(icon(icon_key, color, 17))
        widget.setIconSize(QSize(17, 17))
    if variant:
        widget.setProperty("variant", variant)
    return widget


class HelpMark(QPushButton):
    def __init__(self, text: str) -> None:
        super().__init__("")
        self._help_text = text
        self.setProperty("variant", "help")
        self.setFixedSize(20, 20)
        self.setIcon(icon("help", "#8b8b8b", 14))
        self.setIconSize(QSize(14, 14))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(text)
        self.setToolTipDuration(10000)
        self.clicked.connect(self._show_help)

    def enterEvent(self, event) -> None:
        self._show_help()
        super().enterEvent(event)

    def _show_help(self) -> None:
        QToolTip.showText(self.mapToGlobal(self.rect().bottomRight()), self._help_text, self)


class ClearSelectionList(QListWidget):
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.itemAt(event.position().toPoint()) is None:
            self.clearSelection()
            self.setCurrentRow(-1)
            event.accept()
            return
        super().mousePressEvent(event)


class BufferedLogSink:
    def __init__(
        self,
        console: QTextEdit,
        summary: InfoStrip | None = None,
        placeholder: str = "",
        interval_ms: int = 140,
        batch_size: int = 80,
    ) -> None:
        self._console = console
        self._summary = summary
        self._placeholder = placeholder
        self._batch_size = batch_size
        self._pending: list[tuple[str, str]] = []
        self._timer = QTimer(console)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.flush)
        self._console.document().setMaximumBlockCount(700)

    def append(self, level: str, message: str) -> None:
        clean_level = sanitize_text(str(level))
        clean_message = sanitize_text(str(message))
        self._pending.append((clean_level, clean_message))
        if self._summary:
            self._summary.findChildren(QLabel)[2].setText(clean_level.upper())
        if not self._timer.isActive():
            self._timer.start()

    def flush(self) -> None:
        if not self._pending:
            self._timer.stop()
            return
        if self._console.toPlainText() == self._placeholder:
            self._console.clear()
        batch = self._pending[: self._batch_size]
        del self._pending[: self._batch_size]
        cursor = self._console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for level, message in batch:
            cursor.insertHtml(colored_log_line(level, message))
            cursor.insertBlock()
        self._console.setTextCursor(cursor)
        self._console.ensureCursorVisible()
        if not self._pending:
            self._timer.stop()

    def clear(self) -> None:
        self._pending.clear()
        self._timer.stop()
        self._console.clear()


class LazyPage(QWidget):
    def __init__(self, title: str, factory: Callable[[], QWidget]) -> None:
        super().__init__()
        self._factory = factory
        self._loaded: QWidget | None = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        loading = label(f"Loading {title}...", "muted")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addStretch(1)
        self._layout.addWidget(loading)
        self._layout.addStretch(1)

    def load(self) -> QWidget:
        if self._loaded is not None:
            return self._loaded
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._loaded = self._factory()
        self._layout.addWidget(self._loaded)
        return self._loaded


def fade_in_widget(widget: QWidget | None, duration: int = 150, slide: bool = True) -> None:
    if widget is None:
        return
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    group = QParallelAnimationGroup(widget)
    opacity = QPropertyAnimation(effect, b"opacity", widget)
    opacity.setDuration(duration)
    opacity.setStartValue(0.2)
    opacity.setEndValue(1.0)
    opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
    group.addAnimation(opacity)
    if slide:
        start = widget.pos() + QPoint(0, 10)
        end = widget.pos()
        widget.move(start)
        position = QPropertyAnimation(widget, b"pos", widget)
        position.setDuration(duration + 45)
        position.setStartValue(start)
        position.setEndValue(end)
        position.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(position)
    group.finished.connect(lambda: widget.setGraphicsEffect(None))
    group.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = checked
        self._hover = False
        self._knob_progress = 1.0 if checked else 0.0
        self._knob_anim = QPropertyAnimation(self, b"knobProgress", self)
        self._knob_anim.setDuration(145)
        self._knob_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        if checked != self._checked:
            self._checked = checked
            self._animate_knob()

    def getKnobProgress(self) -> float:
        return self._knob_progress

    def setKnobProgress(self, value: float) -> None:
        self._knob_progress = max(0.0, min(float(value), 1.0))
        self.update()

    knobProgress = Property(float, getKnobProgress, setKnobProgress)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
            self.toggled.emit(self._checked)
            event.accept()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def _animate_knob(self) -> None:
        self._knob_anim.stop()
        self._knob_anim.setStartValue(self._knob_progress)
        self._knob_anim.setEndValue(1.0 if self._checked else 0.0)
        self._knob_anim.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        radius = height / 2
        if self._checked:
            track = QColor("#f5f5f5")
            border = QColor("#f5f5f5")
            knob = QColor("#050505")
        else:
            track = QColor("#171717" if not self._hover else "#242424")
            border = QColor("#3a3a3a" if not self._hover else "#555555")
            knob = QColor("#8b8b8b")
        knob_x = 3 + (width - height) * self._knob_progress
        painter.setBrush(track)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(0, 0, width, height, radius, radius)
        painter.setBrush(knob)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(knob_x, 3, height - 6, height - 6)
        painter.end()


class AnimatedCheckBox(QCheckBox):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._hover = False
        self._check_opacity = 1.0 if self.isChecked() else 0.0
        self._opacity_anim = QPropertyAnimation(self, b"checkOpacity", self)
        self._opacity_anim.setDuration(120)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(24)

    def setChecked(self, checked: bool) -> None:
        changed = checked != self.isChecked()
        super().setChecked(checked)
        if changed:
            self._animate_check()

    def getCheckOpacity(self) -> float:
        return self._check_opacity

    def setCheckOpacity(self, value: float) -> None:
        self._check_opacity = max(0.0, min(float(value), 1.0))
        self.update()

    checkOpacity = Property(float, getCheckOpacity, setCheckOpacity)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        previous = self.isChecked()
        super().mouseReleaseEvent(event)
        if previous != self.isChecked():
            self._animate_check()

    def _animate_check(self) -> None:
        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(self._check_opacity)
        self._opacity_anim.setEndValue(1.0 if self.isChecked() else 0.0)
        self._opacity_anim.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = self.rect()
        box_size = 18
        box_rect = box.adjusted(0, (box.height() - box_size) // 2, 0, 0)
        box_rect.setWidth(box_size)
        box_rect.setHeight(box_size)
        painter.setPen(QPen(QColor("#4a4a4a" if self._hover else "#2a2a2a"), 1))
        painter.setBrush(QColor("#f5f5f5" if self.isChecked() else "#0d0d0d"))
        painter.drawRoundedRect(box_rect, 5, 5)
        if self._check_opacity > 0.0:
            check_color = QColor("#050505")
            check_color.setAlphaF(self._check_opacity)
            pen = QPen(check_color, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            x, y = box_rect.x(), box_rect.y()
            painter.drawLine(x + 5, y + 10, x + 8, y + 13)
            painter.drawLine(x + 8, y + 13, x + 14, y + 5)
        painter.setPen(QColor("#f5f5f5"))
        painter.drawText(28, 0, max(0, self.width() - 28), self.height(), Qt.AlignmentFlag.AlignVCenter, self.text())
        painter.end()


class SmoothProgressBar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._value = 0.0
        self._target = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._step_toward_target)
        self.setFixedHeight(12)
        self.setMinimumWidth(200)

    def getValue(self) -> float:
        return self._value

    def setValue(self, value: float) -> None:
        self._value = max(0.0, min(float(value), 100.0))
        self.update()

    value = Property(float, getValue, setValue)

    def setTarget(self, value: float) -> None:
        self._target = max(0.0, min(float(value), 100.0))
        if not self._timer.isActive():
            self._timer.start()

    def _step_toward_target(self) -> None:
        distance = self._target - self._value
        if abs(distance) < 0.18:
            self.setValue(self._target)
            self._timer.stop()
            return
        self.setValue(self._value + distance * 0.22)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 1, 0, -1)
        radius = rect.height() / 2
        painter.setPen(QPen(QColor("#2a2a2a"), 1))
        painter.setBrush(QColor("#080808"))
        painter.drawRoundedRect(rect, radius, radius)
        if self._value > 0:
            inner = rect.adjusted(2, 2, -2, -2)
            fill_width = max(4, int(inner.width() * self._value / 100))
            fill = inner
            fill.setWidth(fill_width)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#f2f2f2"))
            painter.drawRoundedRect(fill, max(1, fill.height() / 2), max(1, fill.height() / 2))
        painter.end()


class RowToggle(QFrame):
    clicked = Signal()

    def __init__(self, checked: bool) -> None:
        super().__init__()
        self.setProperty("role", "row_toggle")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(156, 34)
        self._label = QLabel("Enabled" if checked else "Disabled")
        self._label.setProperty("role", "row_toggle_text")
        self._switch = ToggleSwitch(checked)
        self._switch.toggled.connect(self._on_switch_toggled)
        self._pending_emit = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(11, 5, 7, 5)
        layout.setSpacing(9)
        layout.addWidget(self._label, 1)
        layout.addWidget(self._switch)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._switch.setChecked(not self._switch.isChecked())
            self._set_label(self._switch.isChecked())
            self._schedule_clicked()
            event.accept()
            return
        super().mousePressEvent(event)

    def _on_switch_toggled(self, checked: bool) -> None:
        self._set_label(checked)
        self._schedule_clicked()

    def _set_label(self, checked: bool) -> None:
        self._label.setText("Enabled" if checked else "Disabled")

    def _schedule_clicked(self) -> None:
        if self._pending_emit:
            return
        self._pending_emit = True
        QTimer.singleShot(165, self._emit_clicked)

    def _emit_clicked(self) -> None:
        self._pending_emit = False
        self.clicked.emit()


class FormToggle(QFrame):
    toggled = Signal(bool)

    def __init__(self, title: str, detail: str = "") -> None:
        super().__init__()
        self.setProperty("role", "form_toggle")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title = label(title, "row_title")
        self._detail = label(detail, "row_meta")
        self._switch = ToggleSwitch(False)
        self._switch.toggled.connect(self._emit_toggled)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        texts.addWidget(self._title)
        if detail:
            texts.addWidget(self._detail)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(10)
        layout.addLayout(texts, 1)
        layout.addWidget(self._switch)
        self.setMinimumHeight(48)

    def isChecked(self) -> bool:
        return self._switch.isChecked()

    def setChecked(self, checked: bool) -> None:
        self._switch.setChecked(checked)
        self.setProperty("checked", "true" if checked else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self.isChecked())
            self.toggled.emit(self.isChecked())
            event.accept()
            return
        super().mousePressEvent(event)

    def _emit_toggled(self, checked: bool) -> None:
        self.setChecked(checked)
        self.toggled.emit(checked)


def field_label(text: str, help_text: str | None = None) -> QWidget:
    container = QWidget()
    container.setProperty("role", "field_row")
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    layout.addWidget(label(text, "field"))
    if help_text:
        layout.addWidget(HelpMark(help_text))
    layout.addStretch(1)
    return container


def install_clear_selection_filters(owner: QObject, root: QWidget) -> None:
    root.installEventFilter(owner)
    for child in root.findChildren(QWidget):
        child.installEventFilter(owner)


def should_keep_list_selection(widget: QObject) -> bool:
    keep_types = (
        QLineEdit,
        QPlainTextEdit,
        QTextEdit,
        QComboBox,
        QPushButton,
        FormToggle,
        ToggleSwitch,
        RowToggle,
        QListWidget,
    )
    current: QObject | None = widget
    while current is not None:
        if isinstance(current, keep_types):
            return True
        current = current.parent()
    return False


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str, badge: str | None = None) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        title_label = label(title, "title")
        subtitle_label = label(subtitle, "subtitle")

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(5)
        texts.addWidget(title_label)
        texts.addWidget(subtitle_label)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addLayout(texts, 1)
        if badge:
            pill = QLabel(badge)
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setFixedHeight(28)
            pill.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            pill.setStyleSheet("border: 1px solid #303030; border-radius: 8px; padding: 0 12px; color: #b8b8b8;")
            top.addWidget(pill)

        separator = QFrame()
        separator.setObjectName("PageHeaderSeparator")
        separator.setFixedHeight(1)
        separator.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(top)
        layout.addWidget(separator)


class EmptyState(QFrame):
    def __init__(self, icon_key: str, title: str, body: str, action: QPushButton | None = None) -> None:
        super().__init__()
        self.setProperty("role", "empty")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMaximumHeight(160)
        symbol = QLabel()
        symbol.setPixmap(icon(icon_key, "#707070", 26).pixmap(QSize(26, 26)))
        symbol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label = label(title, "empty_title")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body_label = label(body, "empty_body")
        body_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(symbol)
        layout.addWidget(title_label)
        layout.addWidget(body_label)
        if action:
            layout.addWidget(action, alignment=Qt.AlignmentFlag.AlignCenter)


class InfoStrip(QFrame):
    def __init__(self, icon_key: str, title: str, detail: str) -> None:
        super().__init__()
        self.setProperty("role", "strip")
        symbol = QLabel()
        symbol.setPixmap(icon(icon_key, "#b8b8b8", 17).pixmap(QSize(17, 17)))
        title_label = label(title, "soft")
        detail_label = label(detail, "muted")
        detail_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(symbol)
        layout.addWidget(title_label, 1)
        layout.addWidget(detail_label)


def add_list_card(
    list_widget: QListWidget,
    icon_key: str,
    title: str,
    subtitle: str,
    status: str,
    meta: str,
    accent: str = "#b8b8b8",
    toggle_callback: Callable[[], None] | None = None,
) -> None:
    item = QListWidgetItem()
    item.setSizeHint(QSize(0, 68))

    frame = QFrame()
    frame.setProperty("role", "list_card")
    symbol = QLabel()
    symbol.setPixmap(icon(icon_key, accent, 18).pixmap(QSize(18, 18)))
    symbol.setFixedWidth(24)
    symbol.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

    title_label = label(title, "row_title")
    subtitle_label = label(subtitle, "soft")
    meta_label = label(meta, "row_meta")
    for text_label in (title_label, subtitle_label, meta_label):
        text_label.setWordWrap(False)
        text_label.setMinimumHeight(16)
    status_widget: QWidget
    if toggle_callback:
        status_widget = RowToggle(status == "Enabled")
        status_widget.clicked.connect(toggle_callback)
    else:
        status_button = QPushButton(status)
        status_button.setProperty("variant", "state_on" if status in {"Enabled", "Verified", "ON"} else "state_off")
        status_button.setFixedSize(112, 30)
        status_button.setCursor(Qt.CursorShape.ArrowCursor)
        status_widget = status_button

    text_layout = QVBoxLayout()
    text_layout.setContentsMargins(0, 0, 0, 0)
    text_layout.setSpacing(2)
    text_layout.addWidget(title_label)
    text_layout.addWidget(subtitle_label)
    text_layout.addWidget(meta_label)

    layout = QHBoxLayout(frame)
    layout.setContentsMargins(10, 7, 10, 7)
    layout.setSpacing(8)
    layout.addWidget(symbol)
    layout.addLayout(text_layout, 1)
    layout.addWidget(status_widget)

    list_widget.addItem(item)
    list_widget.setItemWidget(item, frame)


def page_layout(page: QWidget) -> QVBoxLayout:
    layout = QVBoxLayout(page)
    layout.setContentsMargins(26, 24, 26, 24)
    layout.setSpacing(14)
    return layout


class TitleBar(QFrame):
    def __init__(self, window: QMainWindow) -> None:
        super().__init__()
        self._window = window
        self._drag_pos: QPoint | None = None
        self.setObjectName("TitleBar")
        self.setFixedHeight(TITLE_BAR_HEIGHT)

        title = label("SLAOQ'S SOL'S RNG SNIPER", "soft")
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        version = label(f"v{APP_VERSION}", "muted")
        self.badge = QLabel("IDLE")
        self.badge.setProperty("role", "status_badge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFixedSize(92, 28)
        self.badge.setStyleSheet("border: 1px solid #4c4300; border-radius: 8px; color: #ffcc00; font-weight: 700;")

        self._connection = QLabel("Ready")
        self._connection.setProperty("role", "muted")

        minimize = QPushButton("")
        minimize.setIcon(icon("minimize", "#9a9a9a", 14))
        maximize = QPushButton("")
        maximize.setIcon(icon("maximize", "#9a9a9a", 14))
        close = QPushButton("")
        close.setIcon(icon("close", "#d8d8d8", 14))
        for button in (minimize, maximize):
            button.setProperty("variant", "window")
            button.setFixedSize(34, 28)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setProperty("variant", "window_close")
        for button in (close,):
            button.setFixedSize(34, 28)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        minimize.clicked.connect(window.showMinimized)
        maximize.clicked.connect(self._toggle_maximized)
        close.clicked.connect(window.close)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 8, 0)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(self._connection)
        layout.addWidget(version)
        layout.addWidget(self.badge)
        layout.addWidget(minimize)
        layout.addWidget(maximize)
        layout.addWidget(close)

    def set_status(self, status: str) -> None:
        normalized = status.upper()
        self.badge.setText(normalized)
        if normalized in {"CONNECTED", "RUNNING", "ON"}:
            self._connection.setText("Online")
            border, color = "#116b4b", "#00d084"
        elif normalized in {"CONNECTING", "STARTING", "STOPPING"}:
            self._connection.setText("Working")
            border, color = "#5b4b00", "#ffcc00"
        elif normalized == "PAUSED":
            self._connection.setText("Paused")
            border, color = "#5b4b00", "#ffcc00"
        elif normalized == "ERROR":
            self._connection.setText("Needs attention")
            border, color = "#6b2020", "#ff4d4f"
        else:
            self._connection.setText("Ready")
            border, color = "#4c4300", "#ffcc00"
        self.badge.setStyleSheet(
            f"border: 1px solid {border}; border-radius: 8px; color: {color}; font-weight: 700;"
        )

    def _toggle_maximized(self) -> None:
        self._window.showNormal() if self._window.isMaximized() else self._window.showMaximized()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton and not self._window.isMaximized():
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class Sidebar(QFrame):
    def __init__(self, on_select: Callable[[int], None]) -> None:
        super().__init__()
        self._expanded = True
        self._buttons: list[QPushButton] = []
        self._on_select = on_select
        self._width_anim: QPropertyAnimation | None = None
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIDEBAR_EXPANDED)

        self._logo = QLabel()
        self._logo_pixmap = QPixmap(str(asset_path("logo.png")))
        self._set_logo_size(72)
        self._logo.setFixedHeight(82)
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._brand = label("SLAOQ'S", "brand")
        self._brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._brand_sub = label("Sol's RNG SNIPER", "brand_sub")
        self._brand_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._toggle = QPushButton("")
        self._toggle.setIcon(icon("chevron-left", "#8b8b8b", 15))
        self._toggle.setToolTip("Collapse navigation")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self.toggle)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 16, 6, 10)
        layout.setSpacing(8)
        layout.addWidget(self._logo)
        layout.addWidget(self._brand)
        layout.addWidget(self._brand_sub)
        layout.addSpacing(14)

        for index, (_, text, icon_key) in enumerate(PAGES):
            button = AnimatedButton(f"  {text}")
            button.set_animation_height(42)
            button.set_hover_motion("sidebar")
            button.setProperty("variant", "nav")
            button.setProperty("collapsed", "false")
            button.setIcon(icon(icon_key, "#b8b8b8", 19))
            button.setIconSize(QSize(19, 19))
            button.setToolTip(text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(42)
            button.clicked.connect(lambda checked=False, i=index: self._select(i))
            self._buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)
        layout.addWidget(self._toggle)
        self.set_active(0)

    def toggle(self) -> None:
        self.set_collapsed(self._expanded)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == (not self._expanded):
            return
        self._expanded = not self._expanded
        start = self.width()
        end = SIDEBAR_EXPANDED if self._expanded else SIDEBAR_COLLAPSED
        self._width_anim = QPropertyAnimation(self, b"minimumWidth", self)
        self._width_anim.setDuration(180)
        self._width_anim.setStartValue(start)
        self._width_anim.setEndValue(end)
        self._width_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._width_anim.valueChanged.connect(lambda value: self.setMaximumWidth(int(value)))
        self._width_anim.finished.connect(lambda: self.setFixedWidth(end))
        self._width_anim.start()

        self._toggle.setIcon(icon("chevron-left" if self._expanded else "chevron-right", "#8b8b8b", 15))
        self._toggle.setToolTip("Collapse navigation" if self._expanded else "Expand navigation")
        self._set_logo_size(72 if self._expanded else 42)
        self._brand.setVisible(self._expanded)
        self._brand_sub.setVisible(self._expanded)
        for (_, text, _), button in zip(PAGES, self._buttons, strict=True):
            button.setText(f"  {text}" if self._expanded else "")
            button.setProperty("collapsed", "false" if self._expanded else "true")
            button.style().unpolish(button)
            button.style().polish(button)

    def set_active(self, index: int) -> None:
        for i, button in enumerate(self._buttons):
            button.setProperty("active", "true" if i == index else "false")
            button.style().unpolish(button)
            button.style().polish(button)

    def _select(self, index: int) -> None:
        self.set_active(index)
        self._on_select(index)

    def _set_logo_size(self, size: int) -> None:
        if not self._logo_pixmap.isNull():
            self._logo.setPixmap(
                self._logo_pixmap.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )


class MetricCard(QFrame):
    def __init__(self, title: str, icon_key: str, value: str = "-", detail: str = "Live") -> None:
        super().__init__()
        self.setProperty("role", "card")
        self._accent = "#f5f5f5"
        self._value = label(value, "metric")
        self._detail = label(detail, "metric_sub")
        symbol = QLabel()
        symbol.setPixmap(icon(icon_key, "#8b8b8b", 18).pixmap(QSize(18, 18)))
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(label(title.upper(), "muted"))
        header.addStretch(1)
        header.addWidget(symbol)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self._value)
        layout.addWidget(self._detail)

    def set_value(self, value: str, accent: str | None = None) -> None:
        if accent:
            self._accent = accent
        changed = value != self._value.text()
        self._value.setText(value)
        self._value.setStyleSheet(f"color: {'#d8d8d8' if changed else self._accent};")
        if changed:
            QTimer.singleShot(150, lambda: self._value.setStyleSheet(f"color: {self._accent};"))

    def set_detail(self, value: str) -> None:
        self._detail.setText(value)


class DashboardPage(QWidget):
    def __init__(self, adapter: EngineAdapter) -> None:
        super().__init__()
        self._metrics: dict[str, MetricCard] = {}
        self._start = button("Start Sniper", "play", "primary", "#050505")
        self._pause = button("Pause Sniper", "pause", "warning", "#ffcc00")
        self._stop = button("Stop Sniper", "stop", "danger", "#ff4d4f")
        self._pause.setEnabled(False)
        self._stop.setEnabled(False)
        self._status_strip = InfoStrip("activity", "Engine state", "Standing by")
        self._last_event = InfoStrip("wifi", "Gateway", "Not connected")

        self._start.clicked.connect(adapter.start)
        self._pause.clicked.connect(adapter.toggle_pause)
        self._stop.clicked.connect(adapter.stop)
        for action_button in (self._start, self._pause, self._stop):
            action_button.clicked.connect(lambda checked=False, btn=action_button: self._pulse_button(btn))

        layout = page_layout(self)
        layout.addWidget(PageHeader("Dashboard", "Control and monitor the sniper runtime.", "Runtime"))

        hero = card()
        hero.setProperty("role", "hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(12)
        hero_layout.addWidget(self._status_strip, 1)
        hero_layout.addWidget(self._last_event, 1)
        layout.addWidget(hero)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        metric_defs = (
            ("Snipes", "target", "Successful joins"),
            ("Ping", "wifi", "Discord latency"),
            ("Status", "activity", "Adapter state"),
            ("Roblox", "rocket", "Client process"),
            ("Uptime", "clock", "Current session"),
            ("Messages", "logs", "Messages scanned"),
        )
        for index, (name, icon_key, detail) in enumerate(metric_defs):
            metric = MetricCard(name, icon_key, detail=detail)
            self._metrics[name.lower()] = metric
            grid.addWidget(metric, index // 3, index % 3)
        layout.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self._start)
        actions.addWidget(self._stop)
        actions.addWidget(self._pause)
        actions.addSpacing(8)
        copy_logs = button("Copy Logs", "copy", "ghost")
        copy_logs.clicked.connect(self._copy_logs)
        actions.addWidget(copy_logs)
        actions.addStretch(1)
        layout.addLayout(actions)

        layout.addWidget(label("RECENT ACTIVITY", "muted"))
        self._activity = QTextEdit()
        self._activity.setReadOnly(True)
        self._activity.setMinimumHeight(210)
        self._activity.setHtml('<span style="color:#8b8b8b;">Waiting for connection...</span>')
        self._activity_sink = BufferedLogSink(
            self._activity,
            self._last_event,
            placeholder="Waiting for connection...",
            interval_ms=160,
            batch_size=50,
        )
        layout.addWidget(self._activity)
        layout.addStretch(1)

    def update_metrics(self, metrics: EngineMetrics) -> None:
        ping_accent = "#707070"
        if metrics.ping_ms:
            ping_accent = "#00d084" if metrics.ping_ms < 160 else "#f5a524" if metrics.ping_ms < 320 else "#ff4d4f"
        status = metrics.status.upper()
        status_accent = "#707070"
        if status in {"RUNNING", "CONNECTED", "STARTING"}:
            status_accent = "#00d084"
        elif status in {"PAUSED", "IDLE"}:
            status_accent = "#ffcc00"
        elif status == "ERROR":
            status_accent = "#ff4d4f"
        self._metrics["snipes"].set_value(str(metrics.snipes), "#f5f5f5")
        self._metrics["uptime"].set_value(self._format_uptime(metrics.uptime_seconds), "#f5f5f5")
        self._metrics["ping"].set_value(f"{metrics.ping_ms} ms" if metrics.ping_ms else "-", ping_accent)
        self._metrics["status"].set_value(metrics.status, status_accent)
        self._metrics["roblox"].set_value("Running" if metrics.roblox_running else "Closed", "#00d084" if metrics.roblox_running else "#707070")
        self._metrics["messages"].set_value(str(metrics.messages), "#f5f5f5")
        self._pause.setText("Resume Sniper" if metrics.paused else "Pause Sniper")
        self._pause.setIcon(icon("play" if metrics.paused else "pause", "#ffcc00", 15))
        active = status not in {"OFF", "STOPPED", "ERROR"}
        self._start.setEnabled(not active)
        self._pause.setEnabled(active)
        self._stop.setEnabled(active)
        self._status_strip.findChildren(QLabel)[2].setText("Paused" if metrics.paused else metrics.status.title())
        self._last_event.findChildren(QLabel)[2].setText(f"{metrics.messages} scanned")

    def append_activity(self, level: str, message: str) -> None:
        self._activity_sink.append(level, message)

    def _copy_logs(self) -> None:
        self._activity_sink.flush()
        QApplication.clipboard().setText(self._activity.toPlainText())

    def _pulse_button(self, target: QPushButton) -> None:
        effect = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", target)
        animation.setDuration(170)
        animation.setStartValue(0.55)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: target.setGraphicsEffect(None))
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    @staticmethod
    def _format_uptime(seconds: int) -> str:
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"


def _fetch_discord_channel_label(token: str, guild_id: str, channel_id: str) -> tuple[str, str]:
    channel = _discord_api_get(token, f"https://discord.com/api/v10/channels/{channel_id}")
    channel_name = str(channel.get("name", "")).strip()
    fetched_guild_id = str(channel.get("guild_id", guild_id)).strip()
    guild_name = ""
    if fetched_guild_id:
        try:
            guild = _discord_api_get(token, f"https://discord.com/api/v10/guilds/{fetched_guild_id}")
            guild_name = str(guild.get("name", "")).strip()
        except RuntimeError:
            guild_name = ""
    if channel_name and guild_name:
        return fetched_guild_id, f"{guild_name} / #{channel_name}"
    if channel_name:
        return fetched_guild_id, f"#{channel_name}"
    return fetched_guild_id, f"Channel {channel_id}"


def _discord_api_get(token: str, url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": token,
            "User-Agent": "SlaoqSniperV2",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise RuntimeError("Discord rejected the token or permissions.") from exc
        if exc.code == 404:
            raise RuntimeError("Discord channel was not found.") from exc
        raise RuntimeError(f"Discord returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not reach Discord: {exc}") from exc


class ChannelsPage(QWidget):
    _metadata_resolved = Signal(int, str, str, str)

    def __init__(self, store: ConfigStore, on_change: Callable[[], None] | None = None) -> None:
        super().__init__()
        self._store = store
        self._on_change = on_change
        self._pending_selected_row: int | None = None
        self._list = ClearSelectionList()
        self._list.setSpacing(4)
        self._fetched_name = label("Channel name is fetched from Discord when available.", "muted")
        self._guild = QLineEdit()
        self._channel = QLineEdit()
        self._enabled = FormToggle("Monitor channel", "Toggle this route on or off.")
        self._enabled.setChecked(True)
        self._guild.setPlaceholderText("Server ID")
        self._channel.setPlaceholderText("Channel ID")
        self._summary = InfoStrip("server", "Configured channels", "0 total")
        self._empty = EmptyState("server", "No channels yet", "Use the form above to add the Discord channels that should be monitored.")

        add = button("Add Channel", "server", "primary", "#050505")
        save = button("Save Selected", "check")
        remove = button("Remove Selected", "close", "danger", "#ff4d4f")
        refresh_names = button("Refresh Names", "wifi")
        add.clicked.connect(self._add_channel)
        save.clicked.connect(self._save_selected)
        remove.clicked.connect(self._remove_selected)
        refresh_names.clicked.connect(self._refresh_channel_names)
        self._metadata_resolved.connect(self._apply_channel_metadata)
        self._list.currentRowChanged.connect(self._load_selected)
        self._list.itemSelectionChanged.connect(self._sync_add_mode)

        layout = page_layout(self)
        layout.addWidget(PageHeader("Channels", "Discord channels monitored by the sniper.", "Routing"))

        form = card()
        self._form = form
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(14, 14, 14, 14)
        form_layout.setSpacing(10)
        form_layout.addWidget(field_label("Server ID", "Discord server ID that owns the monitored channel."), 0, 0)
        form_layout.addWidget(field_label("Channel ID", "Discord channel ID to scan for snipe messages."), 0, 1)
        form_layout.addWidget(self._fetched_name, 0, 2)
        form_layout.addWidget(self._guild, 1, 0)
        form_layout.addWidget(self._channel, 1, 1)
        form_layout.addWidget(self._enabled, 1, 2)
        form_layout.addWidget(add, 2, 0)
        form_layout.addWidget(save, 2, 1)
        form_layout.addWidget(remove, 2, 2)
        form_layout.addWidget(refresh_names, 3, 0, 1, 3)
        layout.addWidget(form)
        layout.addWidget(self._empty)
        layout.addWidget(self._list, 1)
        install_clear_selection_filters(self, self)
        self.refresh()

    def refresh(self) -> None:
        scroll = self._list.verticalScrollBar().value()
        selected = self._pending_selected_row if self._pending_selected_row is not None else self._list.currentRow()
        self._pending_selected_row = None
        self._list.clear()
        channels = self._store.config.monitored_channels
        self._summary.findChildren(QLabel)[2].setText(f"{len(channels)} total")
        self._empty.setVisible(not channels)
        self._list.setVisible(bool(channels))
        server_counts: dict[str, int] = {}
        for channel in channels:
            server_counts[channel.guild_id] = server_counts.get(channel.guild_id, 0) + 1
        for index, channel in enumerate(channels):
            state = "Enabled" if channel.enabled else "Disabled"
            server_total = server_counts.get(channel.guild_id, 1)
            server_note = f"{server_total} channels on this server" if server_total > 1 else "Only channel from this server"
            add_list_card(
                self._list,
                "server",
                channel.name,
                f"Server {channel.guild_id} / Channel {channel.channel_id}",
                state,
                server_note,
                "#00d084" if channel.enabled else "#707070",
                lambda row=index: self._toggle_channel(row),
            )
        if channels and selected >= 0:
            self._list.setCurrentRow(min(max(selected, 0), len(channels) - 1))
            self._list.verticalScrollBar().setValue(scroll)

    def _add_channel(self) -> None:
        guild_id = self._guild.text().strip()
        channel_id = self._channel.text().strip()
        if not guild_id or not channel_id:
            return
        self._store.config.monitored_channels.append(ChannelConfig(guild_id, channel_id, f"Channel {channel_id}", self._enabled.isChecked()))
        index = len(self._store.config.monitored_channels) - 1
        self._store.save()
        if self._on_change:
            self._on_change()
        self._fetch_channel_name(index)
        self._guild.clear()
        self._channel.clear()
        self._enabled.setChecked(True)
        self._fetched_name.setText("Channel name is fetched from Discord when available.")
        self.refresh()

    def _save_selected(self) -> None:
        row = self._list.currentRow()
        if not 0 <= row < len(self._store.config.monitored_channels):
            return
        guild_id = self._guild.text().strip()
        channel_id = self._channel.text().strip()
        if not guild_id or not channel_id:
            return
        channel = self._store.config.monitored_channels[row]
        channel.guild_id = guild_id
        channel.channel_id = channel_id
        channel.enabled = self._enabled.isChecked()
        self._store.save()
        if self._on_change:
            self._on_change()
        self._fetch_channel_name(row)
        self.refresh()

    def _load_selected(self, row: int) -> None:
        if not 0 <= row < len(self._store.config.monitored_channels):
            self._guild.clear()
            self._channel.clear()
            self._enabled.setChecked(True)
            self._fetched_name.setText("Channel name is fetched from Discord when available.")
            return
        channel = self._store.config.monitored_channels[row]
        self._fetched_name.setText(f"Fetched name: {channel.name}")
        self._guild.setText(channel.guild_id)
        self._channel.setText(channel.channel_id)
        self._enabled.setChecked(channel.enabled)

    def _sync_add_mode(self) -> None:
        if self._list.currentRow() == -1:
            self._load_selected(-1)

    def _remove_selected(self) -> None:
        row = self._list.currentRow()
        if row >= 0:
            del self._store.config.monitored_channels[row]
            self._store.save()
            if self._on_change:
                self._on_change()
            self.refresh()

    def _refresh_channel_names(self) -> None:
        for index in range(len(self._store.config.monitored_channels)):
            self._fetch_channel_name(index)

    def _fetch_channel_name(self, index: int) -> None:
        if not 0 <= index < len(self._store.config.monitored_channels):
            return
        tokens = self._metadata_tokens()
        if not tokens:
            self._fetched_name.setText("Add a Discord token in Settings to fetch channel names.")
            return
        channel = self._store.config.monitored_channels[index]
        self._fetched_name.setText("Fetching channel name...")
        threading.Thread(
            target=self._fetch_channel_name_worker,
            args=(index, tokens, channel.guild_id, channel.channel_id),
            daemon=True,
            name="SlaoqChannelMetadata",
        ).start()

    def _metadata_tokens(self) -> list[str]:
        tokens: list[str] = []
        for token in [self._store.config.token, *self._store.config.extra_tokens]:
            token = token.strip()
            if token and token not in tokens:
                tokens.append(token)
        return tokens

    def _fetch_channel_name_worker(self, index: int, tokens: list[str], guild_id: str, channel_id: str) -> None:
        last_error = ""
        for token in tokens:
            try:
                fetched_guild_id, display_name = _fetch_discord_channel_label(token, guild_id, channel_id)
                self._metadata_resolved.emit(index, fetched_guild_id, display_name, "")
                return
            except Exception as exc:
                last_error = str(exc)
        self._metadata_resolved.emit(index, guild_id, "", last_error or "No token could read this channel")

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and self._list.currentRow() != -1:
            if isinstance(watched, QWidget) and not should_keep_list_selection(watched):
                self._clear_selection()
        return super().eventFilter(watched, event)

    def _apply_channel_metadata(self, index: int, guild_id: str, display_name: str, error: str) -> None:
        if not 0 <= index < len(self._store.config.monitored_channels):
            return
        channel = self._store.config.monitored_channels[index]
        if error:
            if self._list.currentRow() == index:
                self._fetched_name.setText(f"Name fetch failed: {error}")
            return
        channel.guild_id = guild_id or channel.guild_id
        channel.name = display_name or channel.name
        self._store.save()
        if self._on_change:
            self._on_change()
        if self._list.currentRow() == index:
            self._fetched_name.setText(f"Fetched name: {channel.name}")
        self._pending_selected_row = index if self._list.currentRow() == index else None
        self.refresh()

    def _clear_selection(self) -> None:
        self._list.clearSelection()
        self._list.setCurrentRow(-1)

    def _toggle_channel(self, row: int) -> None:
        if row >= 0:
            channel = self._store.config.monitored_channels[row]
            channel.enabled = not channel.enabled
            self._pending_selected_row = row
            self._store.save()
            if self._on_change:
                self._on_change()
            self.refresh()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._list.currentRow() != -1:
            position = event.position().toPoint()
            if not self._list.geometry().contains(position) and not self._form.geometry().contains(position):
                self._clear_selection()
        super().mousePressEvent(event)


class ProfilesPage(QWidget):
    def __init__(self, store: ConfigStore, on_change: Callable[[], None] | None = None) -> None:
        super().__init__()
        self._store = store
        self._on_change = on_change
        self._selected_category = "Biomes"
        self._pending_selected_row: int | None = None
        self._visible_profiles: list[SnipeProfile] = []
        self._category_buttons: dict[str, QPushButton] = {}
        self._custom_categories: set[str] = set()
        self._list = ClearSelectionList()
        self._list.setSpacing(4)
        self._name = QLineEdit()
        self._category = QComboBox()
        self._triggers = QPlainTextEdit()
        self._biome = QLineEdit()
        self._enabled = FormToggle("Enabled")
        self._enabled.setChecked(True)
        self._name.setPlaceholderText("Profile name")
        self._triggers.setPlaceholderText("One trigger per line, or comma separated")
        self._triggers.setFixedHeight(66)
        self._biome.setPlaceholderText("Biome verification name")
        self._category.currentTextChanged.connect(self._on_category_dropdown_changed)
        self._summary = InfoStrip("target", "Snipe profiles", "0 total")
        self._empty = EmptyState("target", "No custom profiles yet", "Create profiles to group trigger words, biome checks, and alert behavior.")

        add = button("Add Profile", "target", "primary", "#050505")
        save = button("Save Selected", "check")
        remove = button("Remove Selected", "close", "danger", "#ff4d4f")
        add.clicked.connect(self._add_profile)
        save.clicked.connect(self._save_selected)
        remove.clicked.connect(self._remove_selected)
        self._list.currentRowChanged.connect(self._load_selected)
        self._list.itemSelectionChanged.connect(self._sync_add_mode)

        layout = page_layout(self)
        layout.addWidget(PageHeader("Profiles", "Snipe rules, triggers, and biome verification targets.", "Rules"))

        self._category_bar = QHBoxLayout()
        self._category_bar.setSpacing(6)
        layout.addLayout(self._category_bar)
        self._rebuild_category_bar()

        form = card()
        self._form = form
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(14, 14, 14, 14)
        form_layout.setSpacing(10)
        form_layout.setColumnStretch(0, 1)
        form_layout.setColumnStretch(1, 1)
        form_layout.setColumnStretch(2, 1)
        form_layout.addWidget(field_label("Profile Name", "Shown in logs, history, and notifications."), 0, 0)
        form_layout.addWidget(field_label("Category", "Profiles are grouped by target type. Biomes can use biome verification."), 0, 1)
        form_layout.addWidget(field_label("Triggers", "Words or phrases that make this profile match a Discord message."), 0, 2)
        form_layout.addWidget(self._name, 1, 0)
        form_layout.addWidget(self._category, 1, 1)
        form_layout.addWidget(self._triggers, 1, 2, 2, 1)
        form_layout.addWidget(field_label("Biome Check", "Only biome profiles need a verification name. Merchants and items normally leave this disabled."), 2, 0)
        form_layout.addWidget(self._biome, 3, 0)
        form_layout.addWidget(self._enabled, 3, 1)
        form_layout.addWidget(add, 4, 0)
        form_layout.addWidget(save, 4, 1)
        form_layout.addWidget(remove, 4, 2)
        layout.addWidget(form)
        layout.addWidget(self._empty)
        layout.addWidget(self._list, 1)
        install_clear_selection_filters(self, self)
        self.refresh()

    def _normalize_category(self, category: str) -> str:
        value = " ".join(category.strip().split())
        if not value:
            return self._selected_category
        for base in (*BASE_PROFILE_CATEGORIES, "System", "Custom"):
            if value.casefold() == base.casefold():
                return base
        return value

    def _normalize_profile_categories(self) -> None:
        changed = False
        for profile in self._store.config.profiles:
            normalized = self._normalize_category(profile.category)
            if normalized != profile.category:
                profile.category = normalized
                changed = True
        if changed:
            self._store.save()

    def _is_custom_category(self, category: str) -> bool:
        category = self._normalize_category(category)
        return category not in {*BASE_PROFILE_CATEGORIES, "System", "Custom"}

    def _categories(self) -> list[str]:
        self._normalize_profile_categories()
        base = list(BASE_PROFILE_CATEGORIES)
        existing = {
            profile.category
            for profile in self._store.config.profiles
            if profile.category and profile.category not in {"System", "Custom", *BASE_PROFILE_CATEGORIES}
        }
        custom = {self._normalize_category(category) for category in self._custom_categories}
        categories = base + sorted(category for category in existing | custom if category not in base)
        return categories

    def _rebuild_category_bar(self) -> None:
        while self._category_bar.count():
            item = self._category_bar.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._category_buttons.clear()
        for category in self._categories():
            chip = button(category, None, "chip")
            chip.set_hover_motion("none")
            width = max(84, chip.fontMetrics().horizontalAdvance(category) + 34)
            chip.setMinimumWidth(width)
            chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            chip.clicked.connect(lambda checked=False, value=category: self._select_category(value))
            if self._is_custom_category(category):
                chip.setToolTip("Right-click to delete this category")
                chip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                chip.customContextMenuRequested.connect(
                    lambda position, value=category, source=chip: self._show_category_menu(value, source, position)
                )
            self._category_buttons[category] = chip
            self._category_bar.addWidget(chip)
        add_category = button("+", None, "ghost")
        add_category.set_hover_motion("none")
        add_category.setFixedWidth(36)
        add_category.setToolTip("Add category")
        add_category.clicked.connect(self._add_category)
        self._category_bar.addWidget(add_category)
        self._category_bar.addStretch(1)
        self._refresh_category_dropdown()
        self._sync_category_buttons()

    def _sync_category_buttons(self) -> None:
        for category, chip in self._category_buttons.items():
            chip.setProperty("active", "true" if category == self._selected_category else "false")
            chip.style().unpolish(chip)
            chip.style().polish(chip)

    def _select_category(self, category: str) -> None:
        category = self._normalize_category(category)
        if category == self._selected_category:
            return
        self._selected_category = category
        self._set_form_category(category)
        self._sync_category_buttons()
        self._apply_category_rules()
        self.refresh()
        fade_in_widget(self._list)
        fade_in_widget(self._empty)

    def _add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Category", "Category name:")
        category = self._normalize_category(name)
        if ok and category:
            if category in {"System", "Custom"}:
                return
            self._custom_categories.add(category)
            self._selected_category = category
            self._rebuild_category_bar()
            self._set_form_category(category)
            self.refresh()

    def _show_category_menu(self, category: str, source: QWidget, position: QPoint) -> None:
        if not self._is_custom_category(category):
            return
        menu = QMenu(self)
        action = menu.addAction("Delete Category")
        selected = menu.exec(source.mapToGlobal(position))
        if selected == action:
            self._delete_category(category)

    def _delete_category(self, category: str) -> None:
        category = self._normalize_category(category)
        if not self._is_custom_category(category):
            return
        profiles = [profile for profile in self._store.config.profiles if profile.category == category]
        if profiles:
            answer = QMessageBox.question(
                self,
                "Delete Category",
                f"Delete '{category}' and {len(profiles)} profile(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._store.config.profiles = [profile for profile in self._store.config.profiles if profile.category != category]
            self._store.save()
            if self._on_change:
                self._on_change()
        self._custom_categories.discard(category)
        if self._selected_category == category:
            self._selected_category = "Biomes"
        self._rebuild_category_bar()
        self._set_form_category(self._selected_category)
        self.refresh()

    def refresh(self) -> None:
        scroll = self._list.verticalScrollBar().value()
        selected = self._pending_selected_row if self._pending_selected_row is not None else self._list.currentRow()
        self._pending_selected_row = None
        self._list.clear()
        profiles = self._store.config.profiles
        counts: dict[str, int] = {}
        for profile in profiles:
            if profile.category == "System":
                continue
            counts[profile.category] = counts.get(profile.category, 0) + 1
        summary = ", ".join(f"{name}: {count}" for name, count in counts.items()) or "0 total"
        self._summary.findChildren(QLabel)[2].setText(summary)
        self._visible_profiles = [profile for profile in profiles if profile.category == self._selected_category]
        self._set_form_category(self._selected_category)
        self._empty.setVisible(not self._visible_profiles)
        self._list.setVisible(bool(self._visible_profiles))
        self._empty.findChildren(QLabel)[1].setText(f"No {self._selected_category.lower()} profiles")
        for index, profile in enumerate(self._visible_profiles):
            state = "Enabled" if profile.enabled else "Disabled"
            triggers = ", ".join(profile.trigger_keywords[:4]) or "all messages"
            biome = profile.verify_biome_name or "No biome check"
            add_list_card(
                self._list,
                "target",
                profile.name,
                f"Triggers: {triggers}",
                state,
                f"{profile.category} / {biome}",
                "#00d084" if profile.enabled else "#707070",
                None if profile.locked else lambda row=index: self._toggle_profile(row),
            )
        if self._visible_profiles and selected >= 0:
            self._apply_category_rules()
            self._list.setCurrentRow(min(max(selected, 0), len(self._visible_profiles) - 1))
            self._list.verticalScrollBar().setValue(scroll)
        else:
            self._apply_category_rules()

    def _add_profile(self) -> None:
        name = self._name.text().strip()
        if not name:
            return
        triggers = self._read_triggers()
        category = self._form_category()
        if self._is_custom_category(category):
            self._custom_categories.add(category)
        self._store.config.profiles.append(
            SnipeProfile(
                name=name,
                category=category,
                enabled=self._enabled.isChecked(),
                trigger_keywords=triggers,
                verify_biome_name=self._biome.text().strip() if category == "Biomes" else "",
            )
        )
        self._store.save()
        if self._on_change:
            self._on_change()
        self._name.clear()
        self._triggers.clear()
        self._biome.clear()
        self._enabled.setChecked(True)
        self._rebuild_category_bar()
        self.refresh()

    def _save_selected(self) -> None:
        row = self._list.currentRow()
        if not 0 <= row < len(self._visible_profiles):
            return
        profile = self._visible_profiles[row]
        if profile.locked:
            return
        name = self._name.text().strip()
        if not name:
            return
        profile.name = name
        profile.category = self._form_category()
        if self._is_custom_category(profile.category):
            self._custom_categories.add(profile.category)
        profile.trigger_keywords = self._read_triggers()
        profile.verify_biome_name = self._biome.text().strip() if profile.category == "Biomes" else ""
        profile.enabled = self._enabled.isChecked()
        self._store.save()
        if self._on_change:
            self._on_change()
        self._selected_category = profile.category
        self._rebuild_category_bar()
        self.refresh()

    def _load_selected(self, row: int) -> None:
        if not 0 <= row < len(self._visible_profiles):
            self._name.clear()
            self._set_form_category(self._selected_category)
            self._triggers.clear()
            self._biome.clear()
            self._enabled.setChecked(True)
            self._apply_category_rules()
            return
        profile = self._visible_profiles[row]
        self._name.setText(profile.name)
        self._set_form_category(profile.category)
        self._triggers.setPlainText("\n".join(profile.trigger_keywords))
        self._biome.setText(profile.verify_biome_name)
        self._enabled.setChecked(profile.enabled)
        self._apply_category_rules()

    def _sync_add_mode(self) -> None:
        if self._list.currentRow() == -1:
            self._load_selected(-1)

    def _read_triggers(self) -> list[str]:
        raw = self._triggers.toPlainText().replace("\n", ",")
        return [value.strip() for value in raw.split(",") if value.strip()]

    def _apply_category_rules(self) -> None:
        category = self._form_category()
        biome_enabled = category == "Biomes"
        self._biome.setEnabled(biome_enabled)
        if not biome_enabled:
            self._biome.clear()
            self._biome.setPlaceholderText("Biome check disabled for this category")
        else:
            self._biome.setPlaceholderText("Biome verification name")

    def _toggle_profile(self, row: int) -> None:
        if row < 0:
            return
        profile = self._visible_profiles[row]
        if not profile.locked:
            profile.enabled = not profile.enabled
            self._pending_selected_row = row
            self._store.save()
            if self._on_change:
                self._on_change()
            self.refresh()

    def _form_category(self) -> str:
        return self._normalize_category(self._category.currentText() or self._selected_category)

    def _set_form_category(self, category: str) -> None:
        category = self._normalize_category(category)
        if not category:
            return
        blocked = self._category.blockSignals(True)
        if self._category.findText(category) == -1:
            self._category.addItem(category)
        self._category.setCurrentText(category)
        self._category.blockSignals(blocked)

    def _refresh_category_dropdown(self) -> None:
        current = self._normalize_category(self._selected_category)
        self._category.blockSignals(True)
        self._category.clear()
        self._category.addItems(self._categories())
        self._category.setCurrentText(current)
        self._category.blockSignals(False)

    def _on_category_dropdown_changed(self, category: str) -> None:
        if not category:
            return
        category = self._normalize_category(category)
        changed = category != self._selected_category
        self._selected_category = category
        self._sync_category_buttons()
        self._apply_category_rules()
        if self._list.currentRow() == -1:
            self._name.clear()
            self._triggers.clear()
            self._biome.clear()
            self._enabled.setChecked(True)
        self.refresh()
        if changed:
            fade_in_widget(self._list)
            fade_in_widget(self._empty)

    def _clear_selection(self) -> None:
        self._list.clearSelection()
        self._list.setCurrentRow(-1)

    def _remove_selected(self) -> None:
        row = self._list.currentRow()
        if row >= 0 and not self._visible_profiles[row].locked:
            self._store.config.profiles.remove(self._visible_profiles[row])
            self._store.save()
            if self._on_change:
                self._on_change()
            self.refresh()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and self._list.currentRow() != -1:
            if isinstance(watched, QWidget) and not should_keep_list_selection(watched):
                self._clear_selection()
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._list.currentRow() != -1:
            position = event.position().toPoint()
            if not self._list.geometry().contains(position) and not self._form.geometry().contains(position):
                self._clear_selection()
        super().mousePressEvent(event)


class HistoryPage(QWidget):
    def __init__(self, store: HistoryStore) -> None:
        super().__init__()
        self._store = store
        self._list = ClearSelectionList()
        self._list.setSpacing(4)
        self._summary = InfoStrip("clock", "Saved snipes", "0 total")
        self._empty = EmptyState("clock", "No snipe history yet", "Successful snipes will appear here after the engine records them.")
        clear = button("Clear History", "close", "danger", "#ff4d4f")
        clear.clicked.connect(self._clear)
        layout = page_layout(self)
        layout.addWidget(PageHeader("History", "Persistent record of previous snipes.", "Audit"))
        layout.addWidget(self._summary)
        layout.addWidget(clear, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._empty)
        layout.addWidget(self._list, 1)
        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        entries = self._store.all_entries()
        self._summary.findChildren(QLabel)[2].setText(f"{len(entries)} total")
        self._summary.setVisible(bool(entries))
        self._empty.setVisible(not entries)
        self._list.setVisible(bool(entries))
        for entry in entries:
            keyword = entry.keyword or "No keyword"
            if entry.biome_verified is True:
                biome = "Verified"
                accent = "#00d084"
                detail = "Biome matched"
            elif entry.biome_verified is False:
                biome = "Wrong biome"
                accent = "#ff4d4f"
                detail = f"Expected {entry.expected_biome or '?'} / got {entry.detected_biome or '?'}"
            else:
                if entry.expected_biome:
                    biome = "Pending"
                    accent = "#f5a524"
                    detail = f"Waiting for {entry.expected_biome}"
                else:
                    biome = "Not verified"
                    accent = "#8b8b8b"
                    detail = "No biome check"
            raw = entry.raw_message.strip().replace("\n", " ")
            preview = raw[:90] if raw else detail
            add_list_card(
                self._list,
                "clock",
                f"{entry.profile} / {keyword}",
                preview,
                biome,
                f"{entry.author or 'Unknown'} / {entry.timestamp[:19]} / {detail}",
                accent,
            )

    def _clear(self) -> None:
        self._store.clear()
        self.refresh()


class BlacklistPage(QWidget):
    def __init__(self, store: BlacklistStore) -> None:
        super().__init__()
        self._store = store
        self._list = ClearSelectionList()
        self._list.setSpacing(4)
        self._user_id = QLineEdit()
        self._username = QLineEdit()
        self._reason = QLineEdit()
        self._user_id.setPlaceholderText("Discord user ID")
        self._username.setPlaceholderText("Username")
        self._reason.setPlaceholderText("Reason (Optional)")
        self._summary = InfoStrip("shield", "Ignored users", "0 total")
        self._empty = EmptyState("shield", "Blacklist is empty", "Add users here to ignore messages from them across every profile.")
        self._empty.setMaximumHeight(16777215)
        self._empty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        add = button("Add User", "shield", "primary", "#050505")
        remove = button("Remove Selected", "close", "danger", "#ff4d4f")
        clear = button("Clear All", "alert", "warning", "#ffcc00")
        add.clicked.connect(self._add)
        remove.clicked.connect(self._remove_selected)
        clear.clicked.connect(self._clear)

        layout = page_layout(self)
        layout.addWidget(PageHeader("Blacklist", "Users ignored by every profile.", "Safety"))
        layout.addWidget(self._summary)
        form = card()
        form.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(8)
        form_layout.addWidget(field_label("Discord User ID"), 0, 0)
        form_layout.addWidget(field_label("Username"), 0, 1)
        form_layout.addWidget(field_label("Reason (Optional)"), 0, 2)
        form_layout.addWidget(self._user_id, 1, 0)
        form_layout.addWidget(self._username, 1, 1)
        form_layout.addWidget(self._reason, 1, 2)
        form_layout.addWidget(add, 2, 0)
        form_layout.addWidget(remove, 2, 1)
        form_layout.addWidget(clear, 2, 2)
        layout.addWidget(form)
        layout.addWidget(self._empty, 1)
        layout.addWidget(self._list, 1)
        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        entries = self._store.all_entries()
        self._summary.findChildren(QLabel)[2].setText(f"{len(entries)} total")
        self._summary.setVisible(bool(entries))
        self._empty.setVisible(not entries)
        self._list.setVisible(bool(entries))
        for entry in entries:
            add_list_card(
                self._list,
                "shield",
                entry.username,
                f"Reason: {entry.reason}",
                f"{entry.count} events",
                f"ID {entry.user_id}",
            )

    def _add(self) -> None:
        user_id = self._user_id.text().strip()
        if not user_id:
            return
        self._store.add(user_id, self._username.text().strip() or "unknown", self._reason.text().strip() or "manual")
        self._user_id.clear()
        self._username.clear()
        self._reason.clear()
        self.refresh()

    def _remove_selected(self) -> None:
        row = self._list.currentRow()
        entries = self._store.all_entries()
        if 0 <= row < len(entries):
            self._store.remove(entries[row].user_id)
            self.refresh()

    def _clear(self) -> None:
        self._store.clear()
        self.refresh()


class LogsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._console = QTextEdit()
        self._console.setReadOnly(True)
        self._summary = InfoStrip("logs", "Runtime log stream", "Waiting")
        self._sink = BufferedLogSink(self._console, self._summary)
        clear = button("Clear", "close")
        clear.clicked.connect(self._sink.clear)
        layout = page_layout(self)
        layout.addWidget(PageHeader("Logs", "Runtime events emitted by the adapter and engine.", "Console"))
        layout.addWidget(self._summary)
        layout.addWidget(clear, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._console, 1)

    def append_log(self, level: str, message: str) -> None:
        self._sink.append(level, message)


class SettingsPage(QWidget):
    def __init__(self, store: ConfigStore, on_save: Callable[[], None] | None = None) -> None:
        super().__init__()
        self._store = store
        self._on_save = on_save
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(350)
        self._autosave_timer.timeout.connect(self._save)
        config = store.config
        self._token = QLineEdit(config.token)
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        self._token.setPlaceholderText("Paste your Discord token")
        self._auto_join = AnimatedCheckBox("Auto-join on snipe")
        self._auto_join.setChecked(config.auto_join_enabled)
        self._close_roblox = AnimatedCheckBox("Close Roblox before joining")
        self._close_roblox.setChecked(config.close_roblox_before_join)
        self._biome_action = QComboBox()
        self._biome_action.addItem("Do nothing after biome verification", "none")
        self._biome_action.addItem("Close Roblox after verification", "kill")
        self._biome_action.addItem("Return Roblox to home after verification", "home")
        index = max(0, self._biome_action.findData(config.biome_leave_action))
        self._biome_action.setCurrentIndex(index)
        self._join_delay = QSpinBox()
        self._join_delay.setRange(0, 30000)
        self._join_delay.setSuffix(" ms")
        self._join_delay.setValue(config.auto_join_delay_ms)
        self._pause_after_snipe = QSpinBox()
        self._pause_after_snipe.setRange(0, 3600)
        self._pause_after_snipe.setSuffix(" s")
        self._pause_after_snipe.setValue(config.pause_after_snipe_s)
        self._guild_cooldown = QSpinBox()
        self._guild_cooldown.setRange(0, 3600)
        self._guild_cooldown.setSuffix(" s")
        self._guild_cooldown.setValue(int(config.cooldown_guild_ttl))
        self._link_cooldown = QSpinBox()
        self._link_cooldown.setRange(0, 3600)
        self._link_cooldown.setSuffix(" s")
        self._link_cooldown.setValue(int(config.cooldown_link_ttl))
        self._anti_bait = AnimatedCheckBox("Enable biome anti-bait verification")
        self._anti_bait.setChecked(config.anti_bait_enabled)
        self._link_resolve = AnimatedCheckBox("Resolve shortened links")
        self._link_resolve.setChecked(config.link_resolve_enabled)
        self._sound_alert = AnimatedCheckBox("Enable sound alert")
        self._sound_alert.setChecked(config.sound_alert_enabled)
        self._sound_path = QLineEdit(config.sound_alert_path)
        self._sound_path.setPlaceholderText("Optional global sound file")
        self._sound_freq = QSpinBox()
        self._sound_freq.setRange(200, 5000)
        self._sound_freq.setSuffix(" Hz")
        self._sound_freq.setValue(config.sound_alert_freq)
        self._sound_duration = QSpinBox()
        self._sound_duration.setRange(50, 3000)
        self._sound_duration.setSuffix(" ms")
        self._sound_duration.setValue(config.sound_alert_dur_ms)
        self._delete_watch = QSpinBox()
        self._delete_watch.setRange(0, 120)
        self._delete_watch.setSuffix(" s")
        self._delete_watch.setValue(config.delete_watch_seconds)
        self._extra_tokens = QPlainTextEdit()
        self._extra_tokens.setPlaceholderText("One extra token per line")
        self._extra_tokens.setPlainText("\n".join(config.extra_tokens))
        self._dev_mode = AnimatedCheckBox("Developer mode")
        self._dev_mode.setChecked(config.dev_mode)
        self._debug_export = button("Export Debug Report", "download", "ghost")
        self._debug_export.clicked.connect(self._export_debug_report)
        browse_sound = button("Browse", "download", "ghost")
        browse_sound.clicked.connect(self._browse_sound)
        self._browse_sound = browse_sound

        layout = page_layout(self)
        layout.addWidget(PageHeader("Settings", "Grouped configuration for account, joining, cooldowns, alerts, and advanced behavior.", "Config"))
        self._save_state = QLabel("Saved")
        self._save_state.setProperty("role", "autosave")
        self._save_state.setProperty("state", "saved")
        self._save_state.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._save_state)

        tabs = QTabWidget()
        tabs.currentChanged.connect(lambda index: fade_in_widget(tabs.currentWidget(), 135))
        layout.addWidget(tabs, 1)
        tabs.addTab(self._tab_account(), "Account")
        tabs.addTab(self._tab_joining(), "Auto-Join")
        tabs.addTab(self._tab_timing(), "Timing")
        tabs.addTab(self._tab_alerts(), "Alerts")
        tabs.addTab(self._tab_advanced(), "Advanced")

        self._wire_autosave()

    def _tab_account(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(InfoStrip("key", "Primary token", "Masked at rest in the UI"))
        layout.addWidget(field_label("Discord Token", "Used to connect to Discord Gateway. The UI masks it after entry."))
        layout.addWidget(self._token)
        layout.addWidget(field_label("Extra Tokens", "Optional listen-only secondary accounts. Use one token per line."))
        layout.addWidget(self._extra_tokens)
        layout.addStretch(1)
        return tab

    def _tab_joining(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(InfoStrip("rocket", "Join behavior", "Controls how the app opens Roblox links"))
        layout.addWidget(self._auto_join)
        layout.addWidget(self._close_roblox)
        layout.addWidget(field_label("Join Delay", "Wait before opening the Roblox link after a snipe is detected."))
        layout.addWidget(self._join_delay)
        layout.addWidget(field_label("After Biome Verification", "What to do after a biome is confirmed or rejected by anti-bait checks."))
        layout.addWidget(self._biome_action)
        layout.addStretch(1)
        return tab

    def _tab_timing(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(InfoStrip("clock", "Cooldowns", "Reduces duplicate joins and noisy events"))
        layout.addWidget(field_label("Pause After Snipe", "Temporarily pauses scanning after a successful snipe."))
        layout.addWidget(self._pause_after_snipe)
        layout.addWidget(field_label("Server Cooldown", "Avoids repeated joins from the same Discord server."))
        layout.addWidget(self._guild_cooldown)
        layout.addWidget(field_label("Link Cooldown", "Avoids opening the same Roblox link repeatedly."))
        layout.addWidget(self._link_cooldown)
        layout.addStretch(1)
        return tab

    def _tab_alerts(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(InfoStrip("bell", "Local alerts", "Webhook settings live in Notifications"))
        layout.addWidget(self._sound_alert)
        sound_row = QHBoxLayout()
        sound_row.setContentsMargins(0, 0, 0, 0)
        sound_row.addWidget(self._sound_path, 1)
        sound_row.addWidget(self._browse_sound)
        layout.addWidget(field_label("Global Sound", "Optional file used for the global sound alert. If empty, the default beep is used."))
        layout.addLayout(sound_row)
        layout.addWidget(field_label("Alert Frequency", "Frequency used by the default beep."))
        layout.addWidget(self._sound_freq)
        layout.addWidget(field_label("Alert Duration", "Duration used by the default beep."))
        layout.addWidget(self._sound_duration)
        layout.addStretch(1)
        return tab

    def _tab_advanced(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(InfoStrip("sliders", "Advanced behavior", "Use carefully while testing"))
        layout.addWidget(self._anti_bait)
        layout.addWidget(self._link_resolve)
        layout.addWidget(field_label("Delete Watch Window", "Auto-blacklist users who delete bait messages shortly after posting."))
        layout.addWidget(self._delete_watch)
        layout.addWidget(self._dev_mode)
        layout.addWidget(self._debug_export, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return tab

    def _save(self) -> None:
        self._store.config.token = self._token.text().strip()
        self._store.config.auto_join_enabled = self._auto_join.isChecked()
        self._store.config.close_roblox_before_join = self._close_roblox.isChecked()
        self._store.config.biome_leave_action = str(self._biome_action.currentData())
        self._store.config.auto_join_delay_ms = self._join_delay.value()
        self._store.config.pause_after_snipe_s = self._pause_after_snipe.value()
        self._store.config.cooldown_guild_ttl = float(self._guild_cooldown.value())
        self._store.config.cooldown_link_ttl = float(self._link_cooldown.value())
        self._store.config.anti_bait_enabled = self._anti_bait.isChecked()
        self._store.config.link_resolve_enabled = self._link_resolve.isChecked()
        self._store.config.sound_alert_enabled = self._sound_alert.isChecked()
        self._store.config.sound_alert_path = self._sound_path.text().strip()
        self._store.config.sound_alert_freq = self._sound_freq.value()
        self._store.config.sound_alert_dur_ms = self._sound_duration.value()
        self._store.config.delete_watch_seconds = self._delete_watch.value()
        self._store.config.extra_tokens = [line.strip() for line in self._extra_tokens.toPlainText().splitlines() if line.strip()]
        self._store.config.dev_mode = self._dev_mode.isChecked()
        self._store.save()
        self._save_state.setText("Saved")
        self._save_state.setProperty("state", "saved")
        self._save_state.style().unpolish(self._save_state)
        self._save_state.style().polish(self._save_state)
        if self._on_save:
            self._on_save()

    def _queue_save(self) -> None:
        self._save_state.setText("Auto saving...")
        self._save_state.setProperty("state", "saving")
        self._save_state.style().unpolish(self._save_state)
        self._save_state.style().polish(self._save_state)
        self._autosave_timer.start()

    def _wire_autosave(self) -> None:
        for widget in (
            self._auto_join,
            self._close_roblox,
            self._anti_bait,
            self._link_resolve,
            self._sound_alert,
            self._dev_mode,
        ):
            widget.toggled.connect(self._queue_save)
        for widget in (
            self._join_delay,
            self._pause_after_snipe,
            self._guild_cooldown,
            self._link_cooldown,
            self._sound_freq,
            self._sound_duration,
            self._delete_watch,
        ):
            widget.valueChanged.connect(self._queue_save)
        self._token.textChanged.connect(self._queue_save)
        self._sound_path.textChanged.connect(self._queue_save)
        self._extra_tokens.textChanged.connect(self._queue_save)
        self._biome_action.currentIndexChanged.connect(self._queue_save)

    def _export_debug_report(self) -> None:
        try:
            path = export_debug_report()
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", f"Could not export debug report:\n{exc}")
            return
        QApplication.clipboard().setText(str(path))
        QMessageBox.information(self, "Debug Report Exported", f"Saved debug report:\n{path}")

    def _browse_sound(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Sound",
            "",
            "Audio Files (*.wav *.mp3 *.ogg);;All Files (*)",
        )
        if path:
            self._sound_path.setText(path)


class NotificationsPage(QWidget):
    def __init__(self, store: ConfigStore, on_save: Callable[[], None] | None = None) -> None:
        super().__init__()
        self._store = store
        self._on_save = on_save
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(350)
        self._autosave_timer.timeout.connect(self._save)
        webhook = store.config.webhook
        config = store.config
        self._desktop_enabled = AnimatedCheckBox("Enable desktop notifications")
        self._desktop_enabled.setChecked(config.desktop_notifications_enabled)
        self._desktop_snipe = AnimatedCheckBox("Desktop alert on snipe")
        self._desktop_snipe.setChecked(config.desktop_on_snipe)
        self._desktop_error = AnimatedCheckBox("Desktop alert on errors")
        self._desktop_error.setChecked(config.desktop_on_error)
        self._enabled = AnimatedCheckBox("Enable Discord webhook")
        self._enabled.setChecked(webhook.enabled)
        self._url = QLineEdit(webhook.url)
        self._url.setEchoMode(QLineEdit.EchoMode.Password)
        self._url.setPlaceholderText("Webhook URL")
        self._on_snipe = AnimatedCheckBox("Send on successful snipe")
        self._on_snipe.setChecked(webhook.on_snipe)
        self._on_biome = AnimatedCheckBox("Send on biome verification")
        self._on_biome.setChecked(webhook.on_biome)
        self._on_start = AnimatedCheckBox("Send when sniper starts")
        self._on_start.setChecked(webhook.on_start)
        self._on_stop = AnimatedCheckBox("Send when sniper stops")
        self._on_stop.setChecked(webhook.on_stop)
        self._ping_target = QLineEdit(webhook.ping_target)
        self._ping_target.setPlaceholderText("Optional role or user ID to ping")

        layout = page_layout(self)
        layout.addWidget(PageHeader("Notifications", "Desktop alerts and webhook delivery.", "Alerts"))
        layout.addWidget(InfoStrip("bell", "Delivery routes", "Desktop and webhook notifications"))
        panel = card()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 16, 16, 16)
        panel_layout.setSpacing(12)
        panel_layout.addWidget(field_label("Desktop Notifications", "Uses Windows notification support when available."))
        panel_layout.addWidget(self._desktop_enabled)
        panel_layout.addWidget(self._desktop_snipe)
        panel_layout.addWidget(self._desktop_error)
        panel_layout.addSpacing(8)
        panel_layout.addWidget(field_label("Discord Webhook", "Optional webhook delivery for snipe and status events."))
        panel_layout.addWidget(self._enabled)
        panel_layout.addWidget(self._url)
        panel_layout.addWidget(self._on_snipe)
        panel_layout.addWidget(self._on_biome)
        panel_layout.addWidget(self._on_start)
        panel_layout.addWidget(self._on_stop)
        panel_layout.addWidget(self._ping_target)
        layout.addWidget(panel)
        layout.addStretch(1)
        self._wire_autosave()

    def _save(self) -> None:
        self._store.config.desktop_notifications_enabled = self._desktop_enabled.isChecked()
        self._store.config.desktop_on_snipe = self._desktop_snipe.isChecked()
        self._store.config.desktop_on_error = self._desktop_error.isChecked()
        self._store.config.webhook.enabled = self._enabled.isChecked()
        self._store.config.webhook.url = self._url.text().strip()
        self._store.config.webhook.on_snipe = self._on_snipe.isChecked()
        self._store.config.webhook.on_biome = self._on_biome.isChecked()
        self._store.config.webhook.on_start = self._on_start.isChecked()
        self._store.config.webhook.on_stop = self._on_stop.isChecked()
        self._store.config.webhook.ping_target = self._ping_target.text().strip()
        self._store.save()
        if self._on_save:
            self._on_save()

    def _queue_save(self) -> None:
        self._autosave_timer.start()

    def _wire_autosave(self) -> None:
        for widget in (
            self._desktop_enabled,
            self._desktop_snipe,
            self._desktop_error,
            self._enabled,
            self._on_snipe,
            self._on_biome,
            self._on_start,
            self._on_stop,
        ):
            widget.toggled.connect(self._queue_save)
        self._url.textChanged.connect(self._queue_save)
        self._ping_target.textChanged.connect(self._queue_save)


class StartupSplash(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("SplashWindow")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowIcon(QIcon(str(asset_path("app_icon.ico"))))
        self.setFixedSize(500, 350)
        self._step = 0
        self._target_step = 88
        self._last_message_index = -1
        self._messages = (
            "Loading UI framework",
            "Loading configuration",
            "Preparing engine adapter",
            "Checking local storage",
            "Opening workspace",
        )

        logo_box = QFrame()
        logo_box.setObjectName("SplashLogoBox")
        logo_box.setFixedSize(132, 104)
        logo = QLabel()
        logo.setFixedSize(104, 76)
        pixmap = QPixmap(str(asset_path("logo.png")))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(104, 76, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_layout = QVBoxLayout(logo_box)
        logo_layout.setContentsMargins(14, 14, 14, 14)
        logo_layout.addWidget(logo)

        self._message = label(self._messages[0], "soft")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = label(APP_DISPLAY_NAME, "title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version = label(f"v{APP_VERSION}", "muted")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._phase = QLabel("STARTUP")
        self._phase.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._phase.setFixedSize(86, 24)
        self._phase.setStyleSheet("border: 1px solid #303030; border-radius: 8px; color: #b8b8b8; font-size: 11px; font-weight: 700;")
        self._percent = label("0%", "muted")
        self._percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._progress = SmoothProgressBar()

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addStretch(1)
        title_row.addWidget(self._phase)
        title_row.addStretch(1)

        progress_header = QGridLayout()
        progress_header.setContentsMargins(0, 0, 0, 0)
        progress_header.setSpacing(0)
        progress_header.addWidget(self._message, 0, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        progress_header.addWidget(self._percent, 0, 0, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        panel = QFrame()
        panel.setObjectName("SplashRoot")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        shell = QVBoxLayout(self)
        shell.setContentsMargins(8, 8, 8, 8)
        shell.setSpacing(0)
        shell.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(38, 28, 38, 30)
        layout.setSpacing(12)
        layout.addWidget(logo_box, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addLayout(title_row)
        layout.addSpacing(8)
        layout.addLayout(progress_header)
        layout.addWidget(self._progress)
        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(70)
        self._message_effect = QGraphicsOpacityEffect(self._message)
        self._message.setGraphicsEffect(self._message_effect)
        self._message_effect.setOpacity(0.0)
        self._message_anim = QPropertyAnimation(self._message_effect, b"opacity", self)
        self._message_anim.setDuration(180)
        self._message_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._intro_widgets = (logo_box, title, version, self._phase, self._message, self._percent, self._progress)
        self._intro_effects: dict[QWidget, QGraphicsOpacityEffect] = {self._message: self._message_effect}
        for widget in self._intro_widgets:
            if widget is self._message:
                continue
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)
            self._intro_effects[widget] = effect
        self._fade_anim: QPropertyAnimation | None = None
        self._pos_anim: QPropertyAnimation | None = None

    def show_centered(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        end_pos = screen.center() - self.rect().center()
        self.move(end_pos + QPoint(0, 12))
        self.setWindowOpacity(0.0)
        self.show()
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(360)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()
        self._pos_anim = QPropertyAnimation(self, b"pos", self)
        self._pos_anim.setDuration(430)
        self._pos_anim.setStartValue(self.pos())
        self._pos_anim.setEndValue(end_pos)
        self._pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._pos_anim.start()
        QTimer.singleShot(20, self._animate_intro)

    def _animate_intro(self) -> None:
        for index, widget in enumerate(self._intro_widgets):
            effect = self._intro_effects.get(widget)
            if effect is None:
                continue
            group = QParallelAnimationGroup(widget)
            opacity = QPropertyAnimation(effect, b"opacity", widget)
            opacity.setDuration(360)
            opacity.setStartValue(effect.opacity())
            opacity.setEndValue(1.0)
            opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(opacity)
            if widget is not self._message:
                group.finished.connect(lambda target=widget: target.setGraphicsEffect(None))
            QTimer.singleShot(index * 35, lambda animation=group: animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped))

    def _advance(self) -> None:
        if self._step >= self._target_step:
            return
        self._step = min(self._step + 1, self._target_step)
        self._set_progress_value(self._step)
        index = min(self._step * len(self._messages) // 101, len(self._messages) - 1)
        if index != self._last_message_index:
            self._last_message_index = index
            self.set_message(self._messages[index])

    def set_message(self, message: str) -> None:
        if message == self._message.text():
            return
        self._message.setText(message)
        self._message_anim.stop()
        self._message_effect.setOpacity(0.45)
        self._message_anim.setStartValue(0.45)
        self._message_anim.setEndValue(1.0)
        self._message_anim.start()

    def set_phase(self, phase: str) -> None:
        self._phase.setText(phase.upper())

    def set_progress(self, value: int) -> None:
        self._step = max(0, min(value, 100))
        self._target_step = max(self._target_step, self._step)
        self._set_progress_value(self._step)

    def _set_progress_value(self, value: int) -> None:
        self._progress.setTarget(value)
        self._percent.setText(f"{value}%")


class UpdatePromptDialog(QDialog):
    def __init__(self, current_version: str, next_version: str, notes: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("UpdatePrompt")
        self.setWindowTitle("Update Detected")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedSize(520, 620)

        logo_box = QFrame()
        logo_box.setObjectName("UpdateLogoBox")
        logo_box.setFixedSize(96, 78)
        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(76, 56)
        pixmap = QPixmap(str(asset_path("logo.png")))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(76, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo_layout = QVBoxLayout(logo_box)
        logo_layout.setContentsMargins(10, 10, 10, 10)
        logo_layout.addWidget(logo)

        title = label("UPDATE DETECTED", "title")
        subtitle = label(f"{current_version} -> {next_version}", "soft")
        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(6)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(16)
        header.addLayout(title_layout, 1)
        header.addWidget(logo_box)

        separator = QFrame()
        separator.setObjectName("PageHeaderSeparator")
        separator.setFixedHeight(1)

        notes_label = label("Update Log:", "field")
        notes_box = QTextEdit()
        notes_box.setObjectName("UpdateNotes")
        notes_box.setReadOnly(True)
        notes_box.setPlainText(notes.strip() or "No update notes were provided.")

        self._remember = AnimatedCheckBox("Don't ask me again")
        remember_hint = label(
            "Update will enable automatic updates. Dismiss will skip only this version.",
            "muted",
        )

        dismiss = button("Dismiss")
        dismiss.setObjectName("UpdateDismiss")
        dismiss.setMinimumHeight(42)
        dismiss.clicked.connect(self.reject)
        update = button("Update", None, "primary")
        update.setMinimumHeight(42)
        update.clicked.connect(self.accept)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(12)
        actions.addWidget(dismiss)
        actions.addWidget(update)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addWidget(separator)
        layout.addWidget(notes_label)
        layout.addWidget(notes_box, 1)
        layout.addWidget(self._remember)
        layout.addWidget(remember_hint)
        layout.addLayout(actions)

    def remember_decision(self) -> bool:
        return self._remember.isChecked()


class MainWindow(QMainWindow):
    def __init__(
        self,
        adapter: EngineAdapter,
        config_store: ConfigStore,
        blacklist_store: BlacklistStore,
        history_store: HistoryStore,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Slaoq's Sol's RNG Sniper")
        self.setWindowIcon(QIcon(str(asset_path("runtime_icon.ico"))))
        self.setMinimumSize(1080, 680)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._first_show = True
        self._window_anim: QPropertyAnimation | None = None

        root = QWidget()
        root.setObjectName("Root")
        root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCentralWidget(root)
        self._resize_grip = QSizeGrip(root)
        self._resize_grip.setFixedSize(16, 16)

        self._title_bar = TitleBar(self)
        self._stack = QStackedWidget()
        self._stack.currentChanged.connect(self._fade_current_page)
        self._dashboard = DashboardPage(adapter)
        self._logs = LogsPage()
        self._config_store = config_store
        self._page_hosts: dict[int, LazyPage] = {}
        self._last_desktop_status = ""
        self._tray = QSystemTrayIcon(self)
        self._tray_logo_icon = QIcon(str(asset_path("runtime_icon.ico")))
        self._tray_pause_icon = icon("pause", "#ffcc00", 18)
        self._tray.setIcon(self._tray_logo_icon)
        self._tray.setToolTip("Slaoq's Sol's RNG Sniper")
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.show()

        pages: tuple[QWidget, ...] = (
            self._dashboard,
            LazyPage("Settings", lambda: SettingsPage(config_store, adapter.reload_config)),
            LazyPage("Channels", lambda: ChannelsPage(config_store, adapter.reload_config)),
            LazyPage("Profiles", lambda: ProfilesPage(config_store, adapter.reload_config)),
            LazyPage("Notifications", lambda: NotificationsPage(config_store, adapter.reload_config)),
            LazyPage("Blacklist", lambda: BlacklistPage(blacklist_store)),
            self._logs,
            LazyPage("History", lambda: HistoryPage(history_store)),
        )
        for index, page in enumerate(pages):
            if isinstance(page, LazyPage):
                self._page_hosts[index] = page
            self._stack.addWidget(page)

        sidebar = Sidebar(self._select_page)
        self._sidebar = sidebar
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(sidebar)
        body.addWidget(self._stack, 1)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._title_bar)
        layout.addLayout(body, 1)

        adapter.metrics_changed.connect(self._dashboard.update_metrics)
        adapter.metrics_changed.connect(lambda metrics: self._title_bar.set_status(metrics.status))
        adapter.metrics_changed.connect(self._update_tray_status)
        adapter.log_added.connect(self._logs.append_log)
        adapter.log_added.connect(self._dashboard.append_activity)
        adapter.log_added.connect(self._notify_desktop)
        adapter.history_changed.connect(self._refresh_history_page)

    def _select_page(self, index: int) -> None:
        self._ensure_page_loaded(index)
        self._stack.setCurrentIndex(index)

    def _ensure_page_loaded(self, index: int) -> QWidget | None:
        host = self._page_hosts.get(index)
        if host is not None:
            return host.load()
        return self._stack.widget(index)

    def _refresh_history_page(self) -> None:
        page = self._ensure_page_loaded(7) if self._stack.currentIndex() == 7 else self._stack.widget(7)
        if isinstance(page, LazyPage) and not page._loaded:
            return
        if isinstance(page, LazyPage):
            page = page.load()
        if isinstance(page, HistoryPage):
            page.refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_resize_grip"):
            self._resize_grip.move(self.width() - self._resize_grip.width() - 4, self.height() - self._resize_grip.height() - 4)
        if hasattr(self, "_sidebar"):
            self._sidebar.set_collapsed(self.width() < 1120)

    def nativeEvent(self, event_type, message):
        result = self._windows_resize_hit_test(message)
        if result is not None:
            return True, result
        return super().nativeEvent(event_type, message)

    def _windows_resize_hit_test(self, message) -> int | None:
        if os.name != "nt" or self.isMaximized():
            return None
        try:
            msg = _WinMsg.from_address(int(message))
        except (TypeError, ValueError):
            return None
        if msg.message != WM_NCHITTEST:
            return None

        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        frame = self.frameGeometry()
        margin = 8
        left = x < frame.left() + margin
        right = x >= frame.right() - margin
        top = y < frame.top() + margin
        bottom = y >= frame.bottom() - margin

        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
        return None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._first_show:
            return
        self._first_show = False
        self.setWindowOpacity(0.0)
        self._window_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._window_anim.setDuration(220)
        self._window_anim.setStartValue(0.0)
        self._window_anim.setEndValue(1.0)
        self._window_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._window_anim.start()

    def _fade_current_page(self) -> None:
        page = self._stack.currentWidget()
        if page is None:
            return
        if isinstance(page, LazyPage):
            page = page.load()
        layout = page.layout()
        animated_any = self._fade_layout_content(layout) if layout is not None else False
        if not animated_any:
            fade_in_widget(page, 190, slide=True)

    def _fade_layout_content(self, layout) -> bool:
        animated_any = False
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                if isinstance(widget, PageHeader):
                    continue
                fade_in_widget(widget, 190, slide=True)
                animated_any = True
                continue
            child_layout = item.layout()
            if child_layout is not None:
                animated_any = self._fade_layout_content(child_layout) or animated_any
        return animated_any

    def _notify_desktop(self, level: str, message: str) -> None:
        message = sanitize_text(message)
        config = self._config_store.config
        if not config.desktop_notifications_enabled or not self._tray.isVisible():
            return
        normalized = level.lower()
        message_lower = message.lower()
        is_snipe = normalized == "snipe" or "snipe fired" in message_lower or "[sniper]" in message_lower
        is_connected = normalized == "info" and message_lower.strip() == "engine status: connected"
        should_notify = (
            is_snipe and config.desktop_on_snipe
            or is_connected and self._last_desktop_status != "connected"
            or normalized == "error" and config.desktop_on_error
        )
        if should_notify:
            if is_connected:
                self._last_desktop_status = "connected"
                message = "Engine connected."
            self._tray.showMessage("Slaoq Sniper", message[:220], QSystemTrayIcon.MessageIcon.Information, 4500)

    def _update_tray_status(self, metrics: EngineMetrics) -> None:
        if metrics.status.upper() not in {"CONNECTED", "RUNNING", "ON"}:
            self._last_desktop_status = ""
        if not self._tray.isVisible():
            return
        self._tray.setIcon(self._tray_pause_icon if metrics.paused else self._tray_logo_icon)
        memory = self._process_memory_mb()
        uptime = DashboardPage._format_uptime(metrics.uptime_seconds)
        tooltip = (
            "Slaoq's Sol's RNG Sniper\n"
            f"Status: {metrics.status}\n"
            f"Uptime: {uptime}\n"
            f"Memory: {memory} MB"
        )
        self._tray.setToolTip(tooltip)

    @staticmethod
    def _process_memory_mb() -> int:
        if psutil is None:
            return 0
        try:
            return max(1, int(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)))
        except Exception:
            return 0


def create_window(
    adapter: EngineAdapter,
    config_store: ConfigStore,
    blacklist_store: BlacklistStore,
    history_store: HistoryStore,
) -> MainWindow:
    window = MainWindow(adapter, config_store, blacklist_store, history_store)
    desktop = QApplication.primaryScreen().availableGeometry()
    window.resize(1195, 720)
    window.move(desktop.center() - window.rect().center())
    return window
