from __future__ import annotations


class Palette:
    bg = "#0a0a0a"
    bg_alt = "#050505"
    panel = "#111111"
    panel_deep = "#070707"
    surface = "#171717"
    surface_hover = "#202020"
    surface_soft = "#131313"
    border = "#2a2a2a"
    border_soft = "#202020"
    border_active = "#ffffff"
    text = "#f5f5f5"
    text_soft = "#b8b8b8"
    text_muted = "#707070"
    success = "#00d084"
    warning = "#f5a524"
    error = "#ff4d4f"
    yellow = "#ffcc00"


SIDEBAR_COLLAPSED = 68
SIDEBAR_EXPANDED = 236
TITLE_BAR_HEIGHT = 38


def app_stylesheet() -> str:
    return f"""
    QWidget {{
        background: {Palette.bg};
        color: {Palette.text};
        font-family: "Segoe UI";
        font-size: 13px;
    }}

    QLabel {{
        background: transparent;
    }}

    QMainWindow {{
        background: {Palette.bg};
    }}

    #Root {{
        background: {Palette.bg};
        border: 1px solid {Palette.border};
        border-radius: 10px;
    }}

    #TitleBar {{
        background: {Palette.bg};
        border-bottom: 1px solid {Palette.border};
    }}

    #Sidebar {{
        background: {Palette.panel};
        border-right: 1px solid {Palette.border};
    }}

    #SplashRoot {{
        background: #020202;
        border: 1px solid #1e1e1e;
        border-radius: 16px;
    }}

    QWidget#SplashWindow {{
        background: transparent;
    }}

    #SplashLogoBox {{
        background: #070707;
        border: 1px solid #242424;
        border-radius: 14px;
    }}

    #UpdatePrompt {{
        background: #050505;
        border: 1px solid #242424;
        border-radius: 14px;
    }}

    #UpdateLogoBox {{
        background: #070707;
        border: 1px solid #242424;
        border-radius: 14px;
    }}

    QTextEdit#UpdateNotes {{
        background: #151515;
        border: 1px solid #2d2d2d;
        border-radius: 8px;
        padding: 10px;
        color: {Palette.text};
        font-family: "Segoe UI";
        font-size: 13px;
    }}

    QPushButton {{
        background: {Palette.surface};
        border: 1px solid {Palette.border};
        border-radius: 8px;
        padding: 7px 12px;
        color: {Palette.text};
        min-height: 20px;
    }}

    QPushButton:hover {{
        background: {Palette.surface_hover};
        border-color: #3a3a3a;
    }}

    QPushButton:pressed {{
        background: #0f0f0f;
    }}

    QPushButton:disabled {{
        color: #3f3f3f;
        border-color: #111111;
        background: #080808;
    }}

    QPushButton[variant="primary"] {{
        background: #f5f5f5;
        color: #050505;
        border-color: #f5f5f5;
        font-weight: 600;
        min-width: 112px;
    }}

    QPushButton[variant="primary"]:disabled {{
        background: #141414;
        color: #4a4a4a;
        border-color: #1c1c1c;
    }}

    QPushButton#UpdateDismiss {{
        background: #050505;
        color: {Palette.text};
        border-color: {Palette.border_active};
        font-weight: 700;
    }}

    QPushButton#UpdateDismiss:hover {{
        background: #2a0f0f;
        color: {Palette.error};
        border-color: {Palette.error};
    }}

    QPushButton#UpdateDismiss:pressed {{
        background: #160808;
    }}

    QPushButton[variant="danger"] {{
        color: {Palette.error};
        border-color: {Palette.error};
        background: transparent;
        min-width: 120px;
    }}

    QPushButton[variant="danger"]:disabled {{
        color: #4a2727;
        border-color: #201515;
        background: transparent;
    }}

    QPushButton[variant="warning"] {{
        color: {Palette.yellow};
        border-color: #4c4300;
        background: transparent;
    }}

    QPushButton[variant="warning"]:disabled {{
        color: #4a4218;
        border-color: #1f1c09;
        background: transparent;
    }}

    QPushButton[variant="ghost"] {{
        background: transparent;
        border-color: transparent;
        color: {Palette.text_soft};
    }}

    QPushButton[variant="ghost"]:hover {{
        background: {Palette.surface};
        border-color: {Palette.border};
    }}

    QPushButton[variant="window"],
    QPushButton[variant="window_close"] {{
        background: #171717;
        border: 1px solid #2a2a2a;
        border-radius: 8px;
        padding: 0px;
        min-height: 0px;
    }}

    QPushButton[variant="window"]:hover {{
        background: #242424;
        border-color: #4a4a4a;
    }}

    QPushButton[variant="window"]:pressed {{
        background: #101010;
    }}

    QPushButton[variant="window_close"]:hover {{
        background: #3a1717;
        border-color: {Palette.error};
    }}

    QPushButton[variant="window_close"]:pressed {{
        background: #240d0d;
    }}

    QPushButton[variant="nav"] {{
        text-align: left;
        padding: 9px 14px;
        border-radius: 8px;
        color: {Palette.text_soft};
        border-color: transparent;
        background: transparent;
    }}

    QPushButton[variant="nav"]:hover {{
        background: #191919;
        border-color: {Palette.border_active};
        color: {Palette.text};
        font-weight: 700;
    }}

    QPushButton[variant="nav"][active="true"]:hover {{
        background: #1f1f1f;
        border-color: {Palette.border_active};
        color: {Palette.text};
        font-weight: 700;
    }}

    QPushButton[collapsed="true"] {{
        text-align: center;
        padding: 8px 0px;
    }}

    QPushButton[variant="help"] {{
        background: #101010;
        border: 1px solid #333333;
        border-radius: 10px;
        padding: 0px;
        color: {Palette.text_muted};
    }}

    QPushButton[variant="help"]:hover {{
        background: {Palette.surface_hover};
        border-color: {Palette.text_soft};
    }}

    QPushButton[variant="chip"] {{
        background: {Palette.surface_soft};
        border-color: {Palette.border};
        color: {Palette.text_soft};
        padding: 8px 14px;
    }}

    QPushButton[variant="chip"][active="true"] {{
        background: {Palette.text};
        color: #050505;
        border-color: {Palette.text};
        font-weight: 700;
    }}

    QPushButton[variant="state_on"] {{
        background: rgba(0, 208, 132, 0.10);
        border-color: rgba(0, 208, 132, 0.55);
        color: {Palette.success};
        border-radius: 15px;
        padding: 0px;
        font-size: 12px;
        font-weight: 700;
    }}

    QPushButton[variant="state_off"] {{
        background: #101010;
        border-color: #333333;
        color: {Palette.text_muted};
        border-radius: 15px;
        padding: 0px;
        font-size: 12px;
        font-weight: 700;
    }}

    QPushButton[variant="state_on"]:hover {{
        background: rgba(0, 208, 132, 0.18);
        border-color: {Palette.success};
    }}

    QPushButton[variant="state_off"]:hover {{
        background: #181818;
        border-color: #555555;
        color: {Palette.text_soft};
    }}

    QPushButton[active="true"] {{
        border-color: {Palette.border_active};
        background: #1f1f1f;
        font-weight: 700;
    }}

    #PageHeaderSeparator {{
        background: rgba(245, 245, 245, 0.58);
        border: none;
    }}

    QCheckBox {{
        spacing: 8px;
        background: transparent;
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {Palette.border};
        border-radius: 5px;
        background: #0d0d0d;
    }}

    QCheckBox::indicator:checked {{
        background: {Palette.text};
        border-color: {Palette.text};
    }}

    QLabel[role="muted"] {{
        color: {Palette.text_muted};
    }}

    QLabel[role="soft"] {{
        color: {Palette.text_soft};
    }}

    QLabel[role="title"] {{
        font-size: 22px;
        font-weight: 700;
    }}

    QLabel[role="subtitle"] {{
        color: {Palette.text_soft};
        font-size: 12px;
    }}

    QLabel[role="eyebrow"] {{
        color: {Palette.text_muted};
        font-size: 11px;
        font-weight: 700;
    }}

    QLabel[role="brand"] {{
        font-size: 18px;
        font-weight: 800;
        letter-spacing: 0px;
    }}

    QLabel[role="brand_sub"] {{
        color: {Palette.text_soft};
        font-size: 16px;
    }}

    QLabel[role="metric"] {{
        font-size: 24px;
        font-weight: 700;
    }}

    QLabel[role="metric_sub"] {{
        color: {Palette.text_muted};
        font-size: 11px;
    }}

    QLabel[role="empty_title"] {{
        color: {Palette.text};
        font-size: 15px;
        font-weight: 700;
    }}

    QLabel[role="empty_body"] {{
        color: {Palette.text_muted};
        font-size: 12px;
    }}

    QLabel[role="field"] {{
        color: {Palette.text_soft};
        font-size: 12px;
        font-weight: 600;
    }}

    QLabel[role="autosave"] {{
        color: {Palette.text_muted};
        font-size: 11px;
        font-weight: 700;
        padding-right: 4px;
    }}

    QLabel[role="autosave"][state="saving"] {{
        color: {Palette.warning};
    }}

    QLabel[role="autosave"][state="saved"] {{
        color: {Palette.success};
    }}

    QWidget[role="field_row"] {{
        background: transparent;
    }}

    QLabel[role="row_title"] {{
        color: {Palette.text};
        font-size: 13px;
        font-weight: 700;
    }}

    QLabel[role="row_meta"] {{
        color: {Palette.text_muted};
        font-size: 12px;
    }}

    QLabel[role="row_status"] {{
        color: {Palette.text_soft};
        font-size: 11px;
        font-weight: 700;
    }}

    QLabel[role="row_toggle_text"] {{
        color: {Palette.text_soft};
        font-size: 12px;
        font-weight: 700;
    }}

    QFrame[role="card"] {{
        background: {Palette.surface};
        border: 1px solid {Palette.border};
        border-radius: 8px;
    }}

    QFrame[role="card"]:hover {{
        border-color: #3a3a3a;
        background: {Palette.surface_hover};
    }}

    QFrame[role="hero"] {{
        background: {Palette.panel_deep};
        border: 1px solid {Palette.border};
        border-radius: 8px;
    }}

    QFrame[role="empty"] {{
        background: {Palette.surface_soft};
        border: 1px dashed #303030;
        border-radius: 8px;
    }}

    QFrame[role="strip"] {{
        background: {Palette.surface_soft};
        border: 1px solid {Palette.border_soft};
        border-radius: 8px;
    }}

    QFrame[role="list_card"] {{
        background: #141414;
        border: 1px solid {Palette.border};
        border-radius: 8px;
    }}

    QFrame[role="list_card"]:hover {{
        background: {Palette.surface_hover};
        border-color: #3a3a3a;
    }}

    QFrame[role="row_toggle"] {{
        background: #0e0e0e;
        border: 1px solid #333333;
        border-radius: 17px;
    }}

    QFrame[role="row_toggle"]:hover {{
        background: #171717;
        border-color: #555555;
    }}

    QFrame[role="form_toggle"] {{
        background: #0d0d0d;
        border: 1px solid {Palette.border};
        border-radius: 8px;
    }}

    QFrame[role="form_toggle"]:hover {{
        background: #161616;
        border-color: #4a4a4a;
    }}

    QFrame[role="form_toggle"][checked="true"] {{
        border-color: rgba(245, 245, 245, 0.70);
        background: #171717;
    }}

    QFrame[role="toolbar"] {{
        background: {Palette.surface};
        border: 1px solid {Palette.border};
        border-radius: 8px;
    }}

    QFrame[role="section"] {{
        background: transparent;
        border: none;
    }}

    QListWidget {{
        background: {Palette.surface};
        border: 1px solid {Palette.border};
        border-radius: 8px;
        padding: 6px;
    }}

    QListWidget::item {{
        padding: 2px;
        border-radius: 6px;
    }}

    QListWidget::item:selected {{
        background: #222222;
        color: {Palette.text};
    }}

    QToolTip {{
        background: #171717;
        color: {Palette.text};
        border: 1px solid #3a3a3a;
        border-radius: 6px;
        padding: 6px;
    }}

    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{
        background: #0d0d0d;
        border: 1px solid {Palette.border};
        border-radius: 8px;
        padding: 8px;
        color: {Palette.text};
        selection-background-color: #3a3a3a;
        min-height: 20px;
    }}

    QPlainTextEdit, QTextEdit {{
        font-family: "Cascadia Code", "Consolas";
        font-size: 12px;
    }}

    QProgressBar {{
        background: #0d0d0d;
        border: 1px solid {Palette.border};
        border-radius: 6px;
        height: 8px;
        text-align: center;
        color: transparent;
    }}

    QProgressBar::chunk {{
        background: {Palette.text};
        border-radius: 5px;
    }}

    QProgressBar#SplashProgress {{
        background: #080808;
        border: 1px solid #2a2a2a;
        border-radius: 6px;
        min-height: 10px;
        max-height: 10px;
    }}

    QProgressBar#SplashProgress::chunk {{
        background: #f2f2f2;
        border-radius: 5px;
    }}

    QTabWidget::pane {{
        border: 1px solid {Palette.border};
        border-radius: 8px;
        background: {Palette.surface};
        top: 0px;
    }}

    QTabBar::tab {{
        background: #0d0d0d;
        color: {Palette.text_soft};
        border: 1px solid {Palette.border};
        border-bottom-color: {Palette.border};
        padding: 9px 16px;
        min-width: 92px;
        margin-right: -1px;
    }}

    QTabBar::tab:first {{
        border-top-left-radius: 8px;
    }}

    QTabBar::tab:last {{
        border-top-right-radius: 8px;
    }}

    QTabBar::tab:selected {{
        background: {Palette.surface};
        color: {Palette.text};
        border-color: #3a3a3a;
        border-bottom-color: {Palette.surface};
        font-weight: 600;
    }}

    QTabBar::tab:hover {{
        background: #191919;
        color: {Palette.text};
        border-color: #4a4a4a;
    }}

    QScrollArea {{
        border: none;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 4px 2px 4px 2px;
    }}

    QScrollBar::handle:vertical {{
        background: #282828;
        border-radius: 5px;
        min-height: 32px;
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """
