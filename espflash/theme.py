"""Dashboard-Design (dunkel, Amber/Teal) als Qt-Stylesheet."""

from __future__ import annotations

import sys

C = {
    "bg": "#0a0d10",
    "bg2": "#0e1216",
    "panel": "#12171c",
    "panel2": "#161c22",
    "line": "#222a32",
    "line2": "#2c3640",
    "text": "#d7dde3",
    "muted": "#7d8a96",
    "dim": "#56626d",
    "amber": "#f5a524",
    "amber_hi": "#ffb941",
    "teal": "#2dd4bf",
    "red": "#f0524f",
    "green": "#3ddc84",
    "blue": "#5aa9ff",
    "magenta": "#c792ea",
    "black": "#0a0d10",
    "term": "#06080a",
}

MONO_FONTS = ["Cascadia Mono", "Cascadia Code", "Consolas", "JetBrains Mono", "DejaVu Sans Mono", "monospace"]
UI_FONTS = ["Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", "sans-serif"]

MONO = ", ".join(f'"{f}"' for f in MONO_FONTS)
UI = ", ".join(f'"{f}"' for f in UI_FONTS)


def stylesheet(check_png: str = "", arrow_png: str = "") -> str:
    c = C
    return f"""
* {{ outline: 0; }}
QWidget {{ background: transparent; color: {c['text']}; font-family: {UI}; font-size: 9.5pt; }}
QMainWindow, #root {{ background: {c['bg']}; }}
QToolTip {{ background: {c['panel2']}; color: {c['text']}; border: 1px solid {c['line2']}; padding: 4px 6px; }}

/* Kopfzeile */
#topbar {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #0f1418, stop:1 #0b0f12);
           border-bottom: 1px solid #3a2a10; }}
#title {{ font-family: {MONO}; font-size: 12pt; font-weight: 600; letter-spacing: 2px; }}
#subtitle {{ color: {c['muted']}; font-size: 8.5pt; }}
#statLabel {{ font-family: {MONO}; font-size: 7.5pt; color: {c['dim']}; letter-spacing: 2px; }}
#statValue {{ font-family: {MONO}; font-size: 9pt; font-weight: 600; letter-spacing: 1px; }}
#version {{ font-family: {MONO}; font-size: 8.5pt; color: {c['muted']}; border: 1px solid {c['line2']};
            border-radius: 4px; padding: 3px 8px; }}
#pill {{ font-family: {MONO}; font-size: 8.5pt; font-weight: 600; letter-spacing: 2px; border-radius: 12px;
         padding: 4px 12px; border: 1px solid {c['line2']}; color: {c['muted']}; background: {c['bg2']}; }}
#pill[state="ok"] {{ color: {c['teal']}; border-color: rgba(45,212,191,0.45); background: rgba(45,212,191,0.12); }}
#pill[state="busy"] {{ color: {c['amber']}; border-color: rgba(245,165,36,0.5); background: rgba(245,165,36,0.13); }}
#pill[state="err"] {{ color: {c['red']}; border-color: rgba(240,82,79,0.5); background: rgba(240,82,79,0.13); }}

/* Tabs */
QTabWidget::pane {{ border: none; border-top: 1px solid {c['line']}; top: -1px; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{ background: transparent; color: {c['muted']}; font-family: {MONO}; font-size: 8.5pt; font-weight: 600;
                letter-spacing: 2px; padding: 9px 16px; border: none; border-bottom: 2px solid transparent; margin-right: 4px; }}
QTabBar::tab:hover:!selected {{ color: {c['text']}; }}
QTabBar::tab:selected {{ color: {c['amber']}; border-bottom: 2px solid {c['amber']}; }}
QTabBar::tab:disabled {{ color: #34404a; }}

/* Panels */
#panel {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['panel']}, stop:1 {c['bg2']});
          border: 1px solid {c['line']}; border-left: 2px solid {c['amber']}; border-radius: 6px; }}
#panelTitle {{ font-family: {MONO}; font-size: 8.5pt; font-weight: 600; letter-spacing: 2px; }}
#panelMeta {{ font-family: {MONO}; font-size: 8.5pt; color: {c['muted']}; }}
#fieldLabel {{ font-family: {MONO}; font-size: 7.5pt; color: {c['dim']}; letter-spacing: 1px; }}
#hint {{ color: {c['dim']}; font-size: 8.5pt; }}
#chipCard {{ border: 1px solid rgba(45,212,191,0.28); background: rgba(45,212,191,0.04); border-radius: 4px; }}
#kvKey {{ font-family: {MONO}; font-size: 7.5pt; color: {c['dim']}; letter-spacing: 1px; }}
#kvVal {{ font-family: {MONO}; font-size: 9pt; font-weight: 600; color: {c['teal']}; }}
#kvValPlain {{ font-family: {MONO}; font-size: 8.5pt; color: {c['text']}; }}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['line2']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3b4854; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; }}
QScrollBar::handle:horizontal {{ background: {c['line2']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* Eingaben */
QComboBox, QLineEdit, QSpinBox {{ background: {c['bg']}; border: 1px solid {c['line2']}; border-radius: 4px;
    padding: 5px 8px; font-family: {MONO}; font-size: 9pt; selection-background-color: rgba(245,165,36,0.35); }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{ border-color: {c['amber']}; }}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled {{ color: {c['dim']}; border-color: {c['line']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({arrow_png}); width: 10px; height: 6px; margin-right: 8px; }}
QComboBox::down-arrow:disabled {{ image: none; }}
QComboBox QAbstractItemView {{ background: {c['panel']}; border: 1px solid {c['line2']}; padding: 2px;
    selection-background-color: rgba(245,165,36,0.22); selection-color: {c['text']}; outline: 0; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QLineEdit[bad="true"] {{ border-color: {c['red']}; }}

QCheckBox {{ color: {c['muted']}; spacing: 7px; }}
QCheckBox:hover {{ color: {c['text']}; }}
QCheckBox:disabled {{ color: #3a4650; }}
QCheckBox::indicator {{ width: 13px; height: 13px; border: 1px solid {c['line2']}; border-radius: 3px; background: {c['bg']}; }}
QCheckBox::indicator:checked {{ background: {c['teal']}; border-color: {c['teal']}; image: url({check_png}); }}
QCheckBox#danger::indicator:checked {{ background: {c['red']}; border-color: {c['red']}; }}

/* Buttons */
QPushButton {{ font-family: {MONO}; font-size: 8.5pt; font-weight: 600; letter-spacing: 1px;
    padding: 7px 14px; border-radius: 4px; border: 1px solid {c['line2']}; background: {c['panel2']}; color: {c['text']}; }}
QPushButton:hover {{ border-color: {c['muted']}; }}
QPushButton:disabled {{ color: #3e4a55; border-color: {c['line']}; background: {c['bg2']}; }}
QPushButton[kind="primary"] {{ background: {c['amber']}; border-color: {c['amber']}; color: #1b1203; }}
QPushButton[kind="primary"]:hover {{ background: {c['amber_hi']}; border-color: {c['amber_hi']}; }}
QPushButton[kind="primary"]:disabled {{ background: #4a3a1a; border-color: #4a3a1a; color: #7a6540; }}
QPushButton[kind="teal"] {{ background: rgba(45,212,191,0.12); border-color: rgba(45,212,191,0.5); color: {c['teal']}; }}
QPushButton[kind="teal"]:hover {{ background: rgba(45,212,191,0.22); }}
QPushButton[kind="warn"] {{ background: rgba(245,165,36,0.12); border-color: rgba(245,165,36,0.5); color: {c['amber']}; }}
QPushButton[kind="danger"] {{ background: rgba(240,82,79,0.12); border-color: rgba(240,82,79,0.5); color: {c['red']}; }}
QPushButton[kind="danger"]:hover {{ background: rgba(240,82,79,0.24); }}
QPushButton[kind="danger"]:disabled, QPushButton[kind="teal"]:disabled, QPushButton[kind="warn"]:disabled {{
    background: {c['bg2']}; border-color: {c['line']}; color: #3e4a55; }}
QPushButton[kind="ghost"] {{ background: transparent; color: {c['muted']}; }}
QPushButton[kind="ghost"]:hover {{ color: {c['text']}; }}
QPushButton[size="small"] {{ padding: 4px 10px; font-size: 7.5pt; }}
QPushButton[size="big"] {{ padding: 10px 14px; font-size: 9.5pt; }}
QToolButton#rm {{ border: none; color: {c['dim']}; font-size: 11pt; padding: 0 4px; border-radius: 3px; }}
QToolButton#rm:hover {{ color: {c['red']}; background: rgba(240,82,79,0.14); }}
QToolButton#expander {{ border: none; color: {c['muted']}; font-family: {MONO}; font-size: 8pt; font-weight: 600;
    letter-spacing: 2px; text-align: left; padding: 2px 0; }}
QToolButton#expander:hover {{ color: {c['text']}; }}

/* Dateitabelle */
QTableWidget {{ background: {c['bg']}; border: 1px solid {c['line']}; border-radius: 4px; gridline-color: {c['line']};
    font-family: {MONO}; font-size: 9pt; selection-background-color: rgba(245,165,36,0.12); selection-color: {c['text']}; }}
QTableWidget::item {{ padding: 2px 4px; border-bottom: 1px solid {c['line']}; }}
QHeaderView::section {{ background: {c['panel2']}; color: {c['dim']}; font-family: {MONO}; font-size: 7.5pt;
    letter-spacing: 1px; border: none; border-bottom: 1px solid {c['line']}; padding: 6px 6px; }}
QTableCornerButton::section {{ background: {c['panel2']}; border: none; }}

#dropzone {{ border: 1px dashed {c['line2']}; border-radius: 4px; }}
#dropzone[over="true"] {{ border-color: {c['amber']}; background: rgba(245,165,36,0.10); }}
#dzText {{ color: {c['muted']}; }}

QProgressBar {{ background: {c['bg']}; border: 1px solid {c['line']}; border-radius: 3px; height: 7px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {c['amber']}, stop:1 #ffcf6e); border-radius: 2px; }}
QProgressBar[state="done"]::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {c['teal']}, stop:1 {c['green']}); }}
QProgressBar[state="read"]::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {c['teal']}, stop:1 #7cf0e0); }}
QProgressBar[state="err"]::chunk {{ background: {c['red']}; }}
QProgressBar#rowbar {{ border: none; background: {c['line']}; max-height: 3px; min-height: 3px; }}
QProgressBar#rowbar[state="done"]::chunk {{ background: {c['green']}; }}
#progressText {{ font-family: {MONO}; font-size: 8.5pt; color: {c['muted']}; }}

/* Terminal */
#terminal {{ background: {c['term']}; border: 1px solid {c['line']}; border-radius: 4px; padding: 4px;
    selection-background-color: rgba(245,165,36,0.30); }}

#footer {{ border-top: 1px solid {c['line']}; }}
#footerText {{ font-family: {MONO}; font-size: 7.5pt; color: {c['dim']}; letter-spacing: 1px; }}

QMessageBox, QDialog {{ background: {c['panel']}; }}
QMessageBox QLabel {{ color: {c['text']}; }}
QMenu {{ background: {c['panel']}; border: 1px solid {c['line2']}; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; border-radius: 3px; }}
QMenu::item:selected {{ background: rgba(245,165,36,0.18); }}

#toast {{ background: {c['panel2']}; border: 1px solid {c['line2']}; border-left: 3px solid {c['teal']}; border-radius: 4px; padding: 10px 14px; }}
#toast[kind="err"] {{ border-left-color: {c['red']}; }}
#toast[kind="warn"] {{ border-left-color: {c['amber']}; }}
"""


def enable_dark_titlebar(widget) -> None:
    """Dunkle Windows-Titelleiste (Windows 10 20H1+/11)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        value = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (neu/alt)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
        # Rahmen-/Titelfarbe (Windows 11)
        color = ctypes.c_int(0x00100D0A)  # BGR von #0a0d10
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))
    except Exception:
        pass
