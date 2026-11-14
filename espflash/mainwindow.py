"""Hauptfenster des ESP-Flash-Tool MK1."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QTableWidget, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)
from serial.tools import list_ports

from . import APP_NAME, APP_TITLE, APP_VERSION
from .console import SerialConsole
from .logbridge import install_logger
from .session import ChipInfo, FlashSession
from .terminal import TerminalView
from .theme import enable_dark_titlebar

import esptool

KNOWN_VIDS = {0x10C4: "CP210x", 0x1A86: "CH34x", 0x0403: "FTDI", 0x303A: "Espressif USB", 0x067B: "PL2303"}
BAUDRATES = ["921600", "460800", "230400", "115200"]
CONSOLE_BAUDS = ["115200", "74880", "9600", "19200", "38400", "57600", "230400", "460800", "921600", "1500000", "2000000"]
FREQ_ORDER = ["80m", "60m", "48m", "40m", "30m", "26m", "24m", "20m", "16m", "15m", "12m"]
SIZE_ORDER = ["256KB", "512KB", "1MB", "2MB", "2MB-c1", "4MB", "4MB-c1", "8MB", "16MB", "32MB", "64MB", "128MB"]


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def fmt_hex(n: int) -> str:
    return f"0x{n:x}"


def fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def parse_addr(s: str) -> int | None:
    t = str(s).strip().lower().replace("_", "")
    if re.fullmatch(r"0x[0-9a-f]+", t):
        return int(t, 16)
    if re.fullmatch(r"\d+", t):
        return int(t)
    return None


def guess_role(name: str) -> str:
    n = name.lower()
    if re.search(r"merged|factory|combined|full[_-]?flash|_full\b", n):
        return "merged"
    if "bootloader" in n:
        return "bootloader"
    if "partition" in n:
        return "partitions"
    if "boot_app0" in n:
        return "boot_app0"
    if "ota_data" in n:
        return "otadata"
    return "app"


def sort_key(order: list[str]):
    def key(v: str):
        return (order.index(v), v) if v in order else (len(order), v)
    return key


@dataclass
class FileEntry:
    name: str
    path: str
    kind: str          # bin | hex
    data: bytes
    address: str
    role: str
    widgets: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# kleine UI-Bausteine
# ---------------------------------------------------------------------------
def make_panel(title: str, meta: str = "") -> tuple[QFrame, QVBoxLayout, QLabel]:
    frame = QFrame()
    frame.setObjectName("panel")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 11, 14, 13)
    lay.setSpacing(9)
    head = QHBoxLayout()
    t = QLabel(title.upper())
    t.setObjectName("panelTitle")
    m = QLabel(meta)
    m.setObjectName("panelMeta")
    head.addWidget(t)
    head.addStretch(1)
    head.addWidget(m)
    lay.addLayout(head)
    return frame, lay, m


def labeled(text: str, w: QWidget) -> QWidget:
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    lab = QLabel(text.upper())
    lab.setObjectName("fieldLabel")
    v.addWidget(lab)
    v.addWidget(w)
    return box


def button(text: str, kind: str = "", size: str = "") -> QPushButton:
    b = QPushButton(text.upper())
    if kind:
        b.setProperty("kind", kind)
    if size:
        b.setProperty("size", size)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def combo(items: list[str], editable: bool = False) -> QComboBox:
    c = QComboBox()
    c.addItems(items)
    c.setEditable(editable)
    return c


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


class Expander(QWidget):
    """Einklappbarer Bereich (wie <details>)."""

    def __init__(self, title: str, content: QWidget, opened: bool = False) -> None:
        super().__init__()
        self._title = title.upper()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.btn = QToolButton()
        self.btn.setObjectName("expander")
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.clicked.connect(self.toggle)
        self.content = content
        lay.addWidget(self.btn)
        lay.addWidget(content)
        self.set_open(opened)

    def set_open(self, o: bool) -> None:
        self._open = o
        self.content.setVisible(o)
        self.btn.setText(("▾  " if o else "▸  ") + self._title)

    def toggle(self) -> None:
        self.set_open(not self._open)


class Toast(QLabel):
    def __init__(self, parent: QWidget, text: str, kind: str) -> None:
        super().__init__(text, parent)
        self.setObjectName("toast")
        self.setProperty("kind", kind)
        self.setWordWrap(True)
        self.setMaximumWidth(420)
        self.setMinimumWidth(260)
        self.adjustSize()


# ---------------------------------------------------------------------------
# Hauptfenster
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, icon_path: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE}  v{APP_VERSION}")
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))
        self.resize(1400, 900)
        self.setMinimumSize(1000, 640)
        self.setAcceptDrops(True)

        self.settings = QSettings(APP_NAME, APP_NAME)
        self.logger = install_logger()
        self.session = FlashSession()
        self.console = SerialConsole()
        self.files: list[FileEntry] = []
        self.mode = "idle"            # idle | program | console
        self.task = ""                 # laufende Aufgabe
        self.flash_sizes: list[int] = []
        self.flash_idx = 0
        self._p_last = (-1, -1)
        self._t0 = 0.0
        self._known_ports: list[str] = []
        self._toasts: list[Toast] = []

        self._build_ui(icon_path)
        self._wire()
        self._load_settings()
        self.refresh_ports(initial=True)
        self._port_timer = QTimer(self)
        self._port_timer.timeout.connect(self.refresh_ports)
        self._port_timer.start(1500)

        self.term.write_kind("ESP-FLASH-TOOL MK1", "sys")
        self.term.write_kind(f"  v{APP_VERSION}  ", "info")
        self.term.write_kind(f"(esptool {esptool.__version__}, offline)\n", "debug")
        self.term.write_kind("Board per USB anschließen, Port wählen und „Verbinden“ (Programmieren) "
                             "oder „Start“ (Konsole) klicken.\n\n", "debug")
        self.render_files()
        self.update_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self, icon_path: str | None) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Kopfzeile ---
        top = QFrame()
        top.setObjectName("topbar")
        th = QHBoxLayout(top)
        th.setContentsMargins(18, 10, 18, 10)
        th.setSpacing(12)
        logo = QLabel()
        if icon_path:
            logo.setPixmap(QPixmap(icon_path).scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio,
                                                      Qt.TransformationMode.SmoothTransformation))
        th.addWidget(logo)
        tbox = QVBoxLayout()
        tbox.setSpacing(2)
        title = QLabel('ESP-FLASH-TOOL <span style="color:#f5a524">MK1</span>')
        title.setObjectName("title")
        title.setTextFormat(Qt.TextFormat.RichText)
        sub = QLabel("Serieller Flasher für Espressif-Chips · vollständig offline")
        sub.setObjectName("subtitle")
        tbox.addWidget(title)
        tbox.addWidget(sub)
        th.addLayout(tbox)
        th.addStretch(1)

        def stat(label: str) -> QLabel:
            box = QVBoxLayout()
            box.setSpacing(0)
            l1 = QLabel(label)
            l1.setObjectName("statLabel")
            l1.setAlignment(Qt.AlignmentFlag.AlignRight)
            l2 = QLabel("—")
            l2.setObjectName("statValue")
            l2.setAlignment(Qt.AlignmentFlag.AlignRight)
            box.addWidget(l1)
            box.addWidget(l2)
            th.addLayout(box)
            th.addSpacing(10)
            return l2

        self.top_device = stat("GERÄT")
        self.top_mode = stat("MODUS")
        self.pill = QLabel("●  GETRENNT")
        self.pill.setObjectName("pill")
        th.addWidget(self.pill)
        ver = QLabel(f"v{APP_VERSION}")
        ver.setObjectName("version")
        th.addWidget(ver)
        outer.addWidget(top)

        # --- Hauptbereich ---
        body = QHBoxLayout()
        body.setContentsMargins(18, 14, 18, 14)
        body.setSpacing(14)
        outer.addLayout(body, 1)

        left = QWidget()
        left.setFixedWidth(520)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(10)

        # Port-Panel (für beide Modi)
        pp, pl, self.port_meta = make_panel("Serieller Port")
        row = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.port_combo.setMinimumContentsLength(20)
        self.refresh_btn = button("↻", "ghost")
        self.refresh_btn.setToolTip("Portliste aktualisieren")
        self.refresh_btn.setFixedWidth(42)
        row.addWidget(self.port_combo, 1)
        row.addWidget(self.refresh_btn)
        pl.addLayout(row)
        lv.addWidget(pp)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        lv.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_program_page(), "PROGRAMMIEREN")
        self.tabs.addTab(self._build_console_page(), "KONSOLE")
        body.addWidget(left)

        # Terminal
        tp, tl, _ = make_panel("Terminal")
        head = tl.itemAt(0).layout()
        self.copy_log_btn = button("Kopieren", "ghost", "small")
        self.save_log_btn = button("Log speichern", "ghost", "small")
        self.clear_btn = button("Leeren", "ghost", "small")
        for b in (self.copy_log_btn, self.save_log_btn, self.clear_btn):
            head.addWidget(b)
        self.term = TerminalView()
        tl.addWidget(self.term, 1)
        body.addWidget(tp, 1)

        # Fußzeile
        foot = QFrame()
        foot.setObjectName("footer")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(18, 5, 18, 5)
        f1 = QLabel(f"ESP-FLASH-TOOL MK1 v{APP_VERSION} · esptool {esptool.__version__} (GPL-2.0+) · Qt/PySide6")
        f1.setObjectName("footerText")
        f2 = QLabel("Läuft lokal · keine Internetverbindung nötig")
        f2.setObjectName("footerText")
        fh.addWidget(f1)
        fh.addStretch(1)
        fh.addWidget(f2)
        outer.addWidget(foot)

    def _scroll(self, inner: QWidget) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setWidget(inner)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        return sa

    def _build_program_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 10, 6, 0)
        v.setSpacing(12)

        # --- Verbindung ---
        p, l, self.conn_meta = make_panel("Verbindung", "nicht verbunden")
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        self.baud_combo = combo(BAUDRATES, editable=True)
        self.before_combo = combo(["default-reset", "usb-reset", "no-reset", "no-reset-no-sync"])
        g.addWidget(labeled("Baudrate", self.baud_combo), 0, 0)
        g.addWidget(labeled("Reset vor Verbindung", self.before_combo), 0, 1)
        l.addLayout(g)
        chk_row = QHBoxLayout()
        self.trace_chk = QCheckBox("Debug-Log / Trace anzeigen")
        self.nostub_chk = QCheckBox("Ohne Flasher-Stub")
        self.nostub_chk.setToolTip("Entspricht esptool --no-stub: direkt mit dem ROM-Bootloader arbeiten "
                                   "(langsamer, für Sonderfälle).")
        chk_row.addWidget(self.trace_chk)
        chk_row.addSpacing(16)
        chk_row.addWidget(self.nostub_chk)
        chk_row.addStretch(1)
        l.addLayout(chk_row)
        br = QHBoxLayout()
        self.connect_btn = button("Verbinden", "primary")
        self.disconnect_btn = button("Trennen", "warn")
        br.addWidget(self.connect_btn)
        br.addWidget(self.disconnect_btn)
        br.addStretch(1)
        l.addLayout(br)

        self.chip_card = QFrame()
        self.chip_card.setObjectName("chipCard")
        cg = QGridLayout(self.chip_card)
        cg.setContentsMargins(12, 10, 12, 10)
        cg.setHorizontalSpacing(16)
        cg.setVerticalSpacing(8)
        self.ci: dict[str, QLabel] = {}

        def kv(key: str, label: str, r: int, c: int, span: int = 1, plain: bool = False):
            box = QVBoxLayout()
            box.setSpacing(1)
            k = QLabel(label.upper())
            k.setObjectName("kvKey")
            val = QLabel("—")
            val.setObjectName("kvValPlain" if plain else "kvVal")
            val.setWordWrap(plain)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.addWidget(k)
            box.addWidget(val)
            cg.addLayout(box, r, c, 1, span)
            self.ci[key] = val

        kv("chip", "Chip", 0, 0, 2)
        kv("features", "Features", 1, 0, 2, plain=True)
        kv("crystal", "Quarz", 2, 0)
        kv("mac", "MAC", 2, 1)
        kv("flash", "Flash-Größe", 3, 0)
        kv("boot", "Bootloader @", 3, 1)
        l.addWidget(self.chip_card)
        v.addWidget(p)

        # --- Dateien ---
        p, l, self.files_meta = make_panel("Flash-Dateien", "0 Dateien")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ADRESSE", "DATEI", "GRÖSSE", ""])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 112)
        self.table.setColumnWidth(2, 78)
        self.table.setColumnWidth(3, 34)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setShowGrid(False)
        l.addWidget(self.table)

        self.dropzone = QFrame()
        self.dropzone.setObjectName("dropzone")
        dz = QVBoxLayout(self.dropzone)
        dz.setContentsMargins(10, 10, 10, 10)
        dt = QLabel(".bin / .hex hierher ziehen (auch ins ganze Fenster)")
        dt.setObjectName("dzText")
        dt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz.addWidget(dt)
        dr = QHBoxLayout()
        dr.addStretch(1)
        self.add_bin_btn = button("+ BIN-Datei", "ghost", "small")
        self.add_hex_btn = button("+ HEX-Datei", "ghost", "small")
        self.clear_files_btn = button("Liste leeren", "ghost", "small")
        for b in (self.add_bin_btn, self.add_hex_btn, self.clear_files_btn):
            dr.addWidget(b)
        dr.addStretch(1)
        dz.addLayout(dr)
        l.addWidget(self.dropzone)

        hint = QLabel("Adressen werden anhand des Dateinamens vorgeschlagen (bootloader → je nach Chip, "
                      "partition-table → 0x8000, ota_data → 0xd000, boot_app0 → 0xe000, merged/factory → 0x0, "
                      "Anwendung → 0x10000) und lassen sich jederzeit ändern.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        l.addWidget(hint)

        opts = QWidget()
        og = QGridLayout(opts)
        og.setContentsMargins(0, 0, 0, 0)
        og.setHorizontalSpacing(10)
        og.setVerticalSpacing(8)
        self.mode_combo = combo(["keep", "dio", "qio", "dout", "qout"])
        self.freq_combo = combo(["keep"])
        self.size_combo = combo(["keep", "detect"])
        self.after_combo = combo(["hard-reset", "soft-reset", "no-reset", "no-reset-stub", "watchdog-reset"])
        og.addWidget(labeled("Flash-Modus", self.mode_combo), 0, 0)
        og.addWidget(labeled("Flash-Frequenz", self.freq_combo), 0, 1)
        og.addWidget(labeled("Flash-Größe", self.size_combo), 0, 2)
        og.addWidget(labeled("Nach dem Flashen", self.after_combo), 1, 0, 1, 2)
        ch = QVBoxLayout()
        self.compress_chk = QCheckBox("Komprimiert übertragen")
        self.compress_chk.setChecked(True)
        self.skip_chk = QCheckBox("Unveränderte Inhalte überspringen")
        self.skip_chk.setToolTip("Prüft per MD5, ob die Datei bereits im Flash steht, und überspringt sie dann.")
        ch.addWidget(self.compress_chk)
        ch.addWidget(self.skip_chk)
        og.addLayout(ch, 1, 2)
        self.opts_exp = Expander("Flash-Optionen", opts)
        l.addWidget(self.opts_exp)

        self.erase_all_chk = QCheckBox("Gesamten Flash vorher löschen")
        self.erase_all_chk.setObjectName("danger")
        l.addWidget(self.erase_all_chk)

        self.progress_box = QWidget()
        pb = QVBoxLayout(self.progress_box)
        pb.setContentsMargins(0, 2, 0, 2)
        pb.setSpacing(5)
        prow = QHBoxLayout()
        self.progress_text = QLabel("—")
        self.progress_text.setObjectName("progressText")
        self.progress_pct = QLabel("0 %")
        self.progress_pct.setObjectName("progressText")
        prow.addWidget(self.progress_text, 1)
        prow.addWidget(self.progress_pct)
        pb.addLayout(prow)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        pb.addWidget(self.progress)
        self.progress_box.setVisible(False)
        l.addWidget(self.progress_box)

        ar = QHBoxLayout()
        self.program_btn = button("Programmieren", "primary", "big")
        self.erase_btn = button("Flash löschen", "danger", "big")
        ar.addWidget(self.program_btn, 1)
        ar.addWidget(self.erase_btn)
        l.addLayout(ar)
        v.addWidget(p)

        # --- Auslesen ---
        p, l, _ = make_panel("Flash auslesen (Backup)")
        rd = QWidget()
        rg = QGridLayout(rd)
        rg.setContentsMargins(0, 0, 0, 0)
        rg.setHorizontalSpacing(10)
        self.read_addr = QLineEdit("0x0")
        self.read_size = QLineEdit("0x400000")
        self.read_full_btn = button("Ganzer Flash", "ghost")
        rg.addWidget(labeled("Startadresse", self.read_addr), 0, 0)
        rg.addWidget(labeled("Länge", self.read_size), 0, 1)
        rg.addWidget(labeled(" ", self.read_full_btn), 0, 2)
        self.read_btn = button("Auslesen & speichern", "teal")
        rg.addWidget(self.read_btn, 1, 0, 1, 3)
        self.read_exp = Expander("Bereich wählen", rd)
        l.addWidget(self.read_exp)
        v.addWidget(p)
        v.addStretch(1)
        return self._scroll(page)

    def _build_console_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 10, 6, 0)
        v.setSpacing(12)

        p, l, self.console_meta = make_panel("Serielle Konsole", "gestoppt")
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        self.cbaud_combo = combo(CONSOLE_BAUDS, editable=True)
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(100, 10000)
        self.delay_spin.setSingleStep(100)
        self.delay_spin.setValue(1000)
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(1, 20)
        self.retry_spin.setValue(5)
        g.addWidget(labeled("Baudrate", self.cbaud_combo), 0, 0)
        g.addWidget(labeled("Reconnect-Pause (ms)", self.delay_spin), 0, 1)
        g.addWidget(labeled("Max. Versuche", self.retry_spin), 0, 2)
        l.addLayout(g)
        cr = QHBoxLayout()
        self.color_chk = QCheckBox("IDF-Logs einfärben (E/W/I)")
        self.color_chk.setChecked(True)
        self.stamp_chk = QCheckBox("Zeitstempel")
        cr.addWidget(self.color_chk)
        cr.addSpacing(16)
        cr.addWidget(self.stamp_chk)
        cr.addStretch(1)
        l.addLayout(cr)
        br = QHBoxLayout()
        self.cstart_btn = button("Start", "primary")
        self.cstop_btn = button("Stopp", "warn")
        self.creset_btn = button("Reset", "ghost")
        self.creset_btn.setToolTip("Chip über RTS/EN neu starten")
        for b in (self.cstart_btn, self.cstop_btn, self.creset_btn):
            br.addWidget(b)
        br.addStretch(1)
        l.addLayout(br)
        v.addWidget(p)

        p, l, _ = make_panel("Senden")
        sr = QHBoxLayout()
        self.send_edit = QLineEdit()
        self.send_edit.setPlaceholderText("Text an das Gerät senden …")
        self.eol_combo = combo(["CR+LF", "LF", "CR", "keins"])
        self.eol_combo.setFixedWidth(90)
        self.send_btn = button("Senden", "teal")
        sr.addWidget(self.send_edit, 1)
        sr.addWidget(self.eol_combo)
        sr.addWidget(self.send_btn)
        l.addLayout(sr)
        h = QLabel("Tastatureingaben direkt im Terminal werden ebenfalls an das Gerät gesendet, solange die Konsole läuft "
                   "(Strg+C kopiert eine Markierung, ohne Markierung wird ^C gesendet).")
        h.setObjectName("hint")
        h.setWordWrap(True)
        l.addWidget(h)
        v.addWidget(p)
        v.addStretch(1)
        return self._scroll(page)

    # ------------------------------------------------------------------ Verdrahtung
    def _wire(self) -> None:
        self.logger.signals.text.connect(self.term.write_kind)
        self.logger.signals.progress.connect(self.on_progress)
        self.session.signals.finished.connect(self.on_task_finished)
        self.session.signals.failed.connect(self.on_task_failed)
        self.console.signals.data.connect(self.term.write_ansi)
        self.console.signals.status.connect(lambda t, k: self.term.sys(t, k))
        self.console.signals.stopped.connect(self.on_console_stopped)

        self.refresh_btn.clicked.connect(lambda: self.refresh_ports(manual=True))
        self.connect_btn.clicked.connect(self.do_connect)
        self.disconnect_btn.clicked.connect(self.do_disconnect)
        self.add_bin_btn.clicked.connect(lambda: self.pick_files("bin"))
        self.add_hex_btn.clicked.connect(lambda: self.pick_files("hex"))
        self.clear_files_btn.clicked.connect(self.clear_files)
        self.program_btn.clicked.connect(self.do_program)
        self.erase_btn.clicked.connect(self.do_erase)
        self.read_full_btn.clicked.connect(self.set_full_read)
        self.read_btn.clicked.connect(self.do_read)

        self.cstart_btn.clicked.connect(self.console_start)
        self.cstop_btn.clicked.connect(self.console_stop)
        self.creset_btn.clicked.connect(self.console_reset)
        self.send_btn.clicked.connect(self.send_line)
        self.send_edit.returnPressed.connect(self.send_line)
        self.eol_combo.currentIndexChanged.connect(self._update_eol)
        self.color_chk.toggled.connect(lambda v: setattr(self.console, "colorize", v))
        self.stamp_chk.toggled.connect(lambda v: setattr(self.console, "timestamps", v))

        self.copy_log_btn.clicked.connect(self.copy_log)
        self.save_log_btn.clicked.connect(self.save_log)
        self.clear_btn.clicked.connect(self.term.clear)

    # ------------------------------------------------------------------ Einstellungen
    _PERSIST = {
        "baud": "baud_combo", "before": "before_combo", "mode": "mode_combo", "after": "after_combo",
        "cbaud": "cbaud_combo", "eol": "eol_combo",
    }
    _PERSIST_CHK = {"trace": "trace_chk", "nostub": "nostub_chk", "compress": "compress_chk", "skip": "skip_chk",
                    "color": "color_chk", "stamp": "stamp_chk"}

    def _load_settings(self) -> None:
        s = self.settings
        for key, attr in self._PERSIST.items():
            val = s.value(key)
            if val:
                w: QComboBox = getattr(self, attr)
                i = w.findText(str(val))
                if i >= 0:
                    w.setCurrentIndex(i)
                elif w.isEditable():
                    w.setEditText(str(val))
        for key, attr in self._PERSIST_CHK.items():
            val = s.value(key)
            if val is not None:
                getattr(self, attr).setChecked(str(val).lower() in ("true", "1"))
        self.delay_spin.setValue(int(s.value("delay", 1000)))
        self.retry_spin.setValue(int(s.value("retries", 5)))
        geo = s.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.console.colorize = self.color_chk.isChecked()
        self.console.timestamps = self.stamp_chk.isChecked()
        self._update_eol()

    def _save_settings(self) -> None:
        s = self.settings
        for key, attr in self._PERSIST.items():
            s.setValue(key, getattr(self, attr).currentText())
        for key, attr in self._PERSIST_CHK.items():
            s.setValue(key, getattr(self, attr).isChecked())
        s.setValue("delay", self.delay_spin.value())
        s.setValue("retries", self.retry_spin.value())
        s.setValue("geometry", self.saveGeometry())
        s.setValue("port", self.current_port() or "")

    def _offsets(self) -> dict:
        try:
            return json.loads(self.settings.value("offsets", "{}"))
        except Exception:
            return {}

    def _remember_offsets(self) -> None:
        mem = self._offsets()
        for f in self.files:
            if f.kind == "bin" and f.role == "manual" and parse_addr(f.address) is not None:
                mem[f.name] = f.address
        self.settings.setValue("offsets", json.dumps(mem))

    def _last_dir(self) -> str:
        return str(self.settings.value("lastdir", str(Path.home())))

    # ------------------------------------------------------------------ Meldungen
    def toast(self, text: str, kind: str = "ok", ms: int = 4500) -> None:
        t = Toast(self, text, kind)
        t.show()
        self._toasts.append(t)
        self._layout_toasts()
        QTimer.singleShot(ms, lambda: self._drop_toast(t))

    def _drop_toast(self, t: Toast) -> None:
        if t in self._toasts:
            self._toasts.remove(t)
            t.deleteLater()
            self._layout_toasts()

    def _layout_toasts(self) -> None:
        y = self.height() - 40
        for t in reversed(self._toasts):
            t.adjustSize()
            y -= t.height()
            t.move(self.width() - t.width() - 20, y)
            t.raise_()
            y -= 8

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._layout_toasts()

    def set_pill(self, text: str, state: str = "") -> None:
        self.pill.setText("●  " + text)
        self.pill.setProperty("state", state)
        repolish(self.pill)

    # ------------------------------------------------------------------ Ports
    def current_port(self) -> str | None:
        d = self.port_combo.currentData()
        return d if d else None

    def refresh_ports(self, initial: bool = False, manual: bool = False) -> None:
        ports = sorted(list_ports.comports(), key=lambda p: p.device)
        devices = [p.device for p in ports]
        if devices == self._known_ports and not manual:
            return
        new = [d for d in devices if d not in self._known_ports]
        current = self.current_port() or (str(self.settings.value("port", "")) if initial else None)
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        for p in ports:
            vid = p.vid
            label = p.device
            desc = p.description if p.description and p.description != "n/a" else ""
            if vid is not None:
                chip = KNOWN_VIDS.get(vid, "USB")
                label += f"  –  {chip} {vid:04X}:{p.pid:04X}"
            elif desc:
                label += f"  –  {desc}"
            self.port_combo.addItem(label, p.device)
            self.port_combo.setItemData(self.port_combo.count() - 1, desc or label, Qt.ItemDataRole.ToolTipRole)
        if not ports:
            self.port_combo.addItem("Kein serieller Port gefunden", None)
        target = current
        if new and self._known_ports and not initial and self.mode == "idle":
            target = new[-1]
            self.toast(f"Neuer Port erkannt: {target}")
        idx = self.port_combo.findData(target) if target else -1
        if idx < 0 and ports:
            # bevorzugt bekannte USB-UART-Bridges / Espressif-USB
            pref = [i for i, p in enumerate(ports) if p.vid in KNOWN_VIDS]
            idx = pref[0] if pref else 0
        self.port_combo.setCurrentIndex(max(idx, 0))
        self.port_combo.blockSignals(False)
        gone = [d for d in self._known_ports if d not in devices]
        self._known_ports = devices
        self.port_meta.setText(f"{len(ports)} gefunden")
        if gone and self.mode == "program" and self.session.info and self.session.info.port in gone:
            self.term.sys("Gerät wurde getrennt (USB abgezogen).", "err")
            self.toast("Gerät wurde getrennt.", "err")
            if not self.session.busy:
                self.session.disconnect()
                self.mode = "idle"
        self.update_ui()

    # ------------------------------------------------------------------ Zustand
    def update_ui(self) -> None:
        busy = self.session.busy
        connected = self.mode == "program" and self.session.connected
        console_on = self.mode == "console"
        have_port = self.current_port() is not None

        self.tabs.setTabEnabled(1, not connected and not (busy and self.task == "connect"))
        self.tabs.setTabEnabled(0, not console_on)
        self.port_combo.setEnabled(not connected and not console_on and not busy)
        self.refresh_btn.setEnabled(not connected and not console_on and not busy)

        self.connect_btn.setVisible(not connected)
        self.disconnect_btn.setVisible(connected)
        self.connect_btn.setEnabled(not busy and have_port)
        self.disconnect_btn.setEnabled(not busy)
        for w in (self.baud_combo, self.before_combo, self.trace_chk, self.nostub_chk):
            w.setEnabled(not connected and not busy)
        self.chip_card.setVisible(connected)
        self.conn_meta.setText(self.session.info.name if connected and self.session.info else "nicht verbunden")

        self.program_btn.setEnabled(connected and not busy and bool(self.files))
        self.erase_btn.setEnabled(connected and not busy)
        self.read_btn.setEnabled(connected and not busy)
        self.read_full_btn.setEnabled(connected and not busy and bool(self.session.info and self.session.info.flash_bytes))
        for w in (self.add_bin_btn, self.add_hex_btn, self.clear_files_btn, self.mode_combo, self.freq_combo,
                  self.size_combo, self.after_combo, self.compress_chk, self.skip_chk, self.erase_all_chk):
            w.setEnabled(not busy)
        for f in self.files:
            for key in ("addr", "rm"):
                w = f.widgets.get(key)
                if w is not None:
                    w.setEnabled(not busy and not (key == "addr" and f.kind == "hex"))

        self.cstart_btn.setVisible(not console_on)
        self.cstop_btn.setVisible(console_on)
        self.creset_btn.setVisible(console_on)
        self.cstart_btn.setEnabled(have_port and not busy)
        self.cbaud_combo.setEnabled(not console_on)
        self.send_edit.setEnabled(console_on)
        self.send_btn.setEnabled(console_on)
        self.console_meta.setText(f"läuft · {self.console.port} @ {self.console.baud}" if console_on else "gestoppt")
        self.term.key_sink = self.console.write if console_on else None

        if busy:
            self.set_pill("AKTIV", "busy")
        elif connected:
            self.set_pill("VERBUNDEN", "ok")
        elif console_on:
            self.set_pill("KONSOLE", "ok")
        else:
            self.set_pill("GETRENNT", "")
        self.top_mode.setText("ARBEITET" if busy else "PROGRAMMIEREN" if connected else "KONSOLE" if console_on else "BEREIT")
        if connected and self.session.info:
            self.top_device.setText(self.session.info.name)
        elif console_on:
            self.top_device.setText(self.console.port)
        else:
            self.top_device.setText("—")

    # ------------------------------------------------------------------ Dateien
    def bootloader_offset(self) -> int:
        if self.session.info:
            return self.session.info.bootloader_offset
        return 0x1000

    def addr_for_role(self, role: str) -> int:
        return {
            "merged": 0x0, "bootloader": self.bootloader_offset(), "partitions": 0x8000,
            "boot_app0": 0xE000, "otadata": 0xD000,
        }.get(role, 0x10000)

    def pick_files(self, kind: str) -> None:
        if kind == "bin":
            paths, _ = QFileDialog.getOpenFileNames(self, "BIN-Dateien wählen", self._last_dir(),
                                                    "Binärdateien (*.bin);;Alle Dateien (*.*)")
        else:
            paths, _ = QFileDialog.getOpenFileNames(self, "HEX-Datei wählen", self._last_dir(),
                                                    "Intel-HEX (*.hex);;Alle Dateien (*.*)")
        if paths:
            self.settings.setValue("lastdir", str(Path(paths[0]).parent))
            self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> None:
        mem = self._offsets()
        for path in paths:
            p = Path(path)
            ext = p.suffix.lower()
            try:
                if ext == ".hex":
                    self._add_hex(p)
                elif ext == ".bin":
                    data = p.read_bytes()
                    if not data:
                        self.toast(f"{p.name} ist leer.", "warn")
                        continue
                    existing = next((f for f in self.files if f.kind == "bin" and f.name == p.name), None)
                    if existing:
                        existing.data, existing.path = data, str(p)
                        self.toast(f"{p.name} aktualisiert.")
                        continue
                    if p.name in mem:
                        role, addr = "manual", mem[p.name]
                    else:
                        role = guess_role(p.name)
                        addr = fmt_hex(self.addr_for_role(role))
                    self.files.append(FileEntry(p.name, str(p), "bin", data, addr, role))
                else:
                    self.toast(f"{p.name}: nur .bin- und .hex-Dateien werden unterstützt.", "warn")
            except Exception as exc:  # noqa: BLE001
                self.toast(f"{p.name}: {exc}", "err", 7000)
        self.sort_files()
        self.render_files()

    def _add_hex(self, p: Path) -> None:
        from intelhex import IntelHex
        ih = IntelHex()
        ih.loadhex(str(p))
        segs = ih.segments()
        if not segs:
            raise ValueError("Die Intel-HEX-Datei enthält keine Daten.")
        for start, stop in segs:
            data = ih.tobinstr(start=start, end=stop - 1)
            self.files.append(FileEntry(f"{p.name} @{fmt_hex(start)}", str(p), "hex", data, fmt_hex(start), "hex"))
        self.erase_all_chk.setChecked(False)

    def sort_files(self) -> None:
        self.files.sort(key=lambda f: parse_addr(f.address) if parse_addr(f.address) is not None else 1 << 40)

    def clear_files(self) -> None:
        self.files = []
        self.render_files()

    def remove_file(self, f: FileEntry) -> None:
        if f in self.files:
            self.files.remove(f)
        self.render_files()

    def render_files(self) -> None:
        self.table.setRowCount(0)
        if not self.files:
            self.table.setRowCount(1)
            empty = QLabel("Noch keine Dateien – .bin oder .hex hinzufügen")
            empty.setObjectName("hint")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setSpan(0, 0, 1, 4)
            self.table.setCellWidget(0, 0, empty)
        else:
            self.table.clearSpans()
            self.table.setRowCount(len(self.files))
        for r, f in enumerate(self.files):
            addr = QLineEdit(f.address)
            addr.setFrame(True)
            if f.kind == "hex":
                addr.setReadOnly(True)
                addr.setToolTip("Adresse stammt aus der HEX-Datei")

            def changed(text: str, f=f, w=addr):
                f.address = text
                f.role = "manual"
                w.setProperty("bad", parse_addr(text) is None)
                repolish(w)
            addr.textEdited.connect(changed)
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(4, 4, 4, 4)
            cl.addWidget(addr)
            self.table.setCellWidget(r, 0, cell)

            nm = QWidget()
            nl = QVBoxLayout(nm)
            nl.setContentsMargins(6, 4, 6, 4)
            nl.setSpacing(4)
            lab = QLabel(f.name + ("   [HEX]" if f.kind == "hex" else ""))
            lab.setToolTip(f.path)
            lab.setStyleSheet("font-size: 9pt;")
            bar = QProgressBar()
            bar.setObjectName("rowbar")
            bar.setRange(0, 1000)
            bar.setValue(0)
            bar.setTextVisible(False)
            nl.addWidget(lab)
            nl.addWidget(bar)
            self.table.setCellWidget(r, 1, nm)

            sz = QLabel(fmt_size(len(f.data)))
            sz.setStyleSheet("color:#7d8a96; padding-left:6px;")
            self.table.setCellWidget(r, 2, sz)

            rm = QToolButton()
            rm.setObjectName("rm")
            rm.setText("✕")
            rm.setToolTip("Entfernen")
            rm.setCursor(Qt.CursorShape.PointingHandCursor)
            rm.clicked.connect(lambda _=False, f=f: self.remove_file(f))
            self.table.setCellWidget(r, 3, rm)
            f.widgets = {"addr": addr, "bar": bar, "rm": rm}
        rows = max(1, len(self.files))
        self.table.setFixedHeight(self.table.horizontalHeader().height() + 44 * min(rows, 6) + 4)
        total = sum(len(f.data) for f in self.files)
        n = len(self.files)
        self.files_meta.setText(f"{n} {'Datei' if n == 1 else 'Dateien'}" + (f" · {fmt_size(total)}" if n else ""))
        self._remember_offsets()
        self.update_ui()

    def validate_files(self) -> str | None:
        if not self.files:
            return "Keine Datei ausgewählt."
        ranges = []
        for i, f in enumerate(self.files):
            a = parse_addr(f.address)
            if a is None:
                return f"Ungültige Adresse in Zeile {i + 1} ({f.name})."
            if any(r[0] == a for r in ranges):
                return f"Adresse {fmt_hex(a)} wird doppelt verwendet."
            ranges.append((a, a + len(f.data), f.name))
        ranges.sort()
        for prev, cur in zip(ranges, ranges[1:]):
            if cur[0] < prev[1]:
                return f"{prev[2]} (bis {fmt_hex(prev[1])}) überlappt mit {cur[2]} @ {fmt_hex(cur[0])}."
        if self.session.info and self.session.info.flash_bytes:
            end = max(r[1] for r in ranges)
            if end > self.session.info.flash_bytes:
                return (f"Die Daten reichen bis {fmt_hex(end)}, der Flash hat aber nur "
                        f"{self.session.info.flash_size}.")
        return None

    # ------------------------------------------------------------------ Drag & Drop
    def dragEnterEvent(self, e: QDragEnterEvent) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.dropzone.setProperty("over", True)
            repolish(self.dropzone)

    def dragLeaveEvent(self, e) -> None:  # noqa: N802
        self.dropzone.setProperty("over", False)
        repolish(self.dropzone)

    def dropEvent(self, e: QDropEvent) -> None:  # noqa: N802
        self.dropzone.setProperty("over", False)
        repolish(self.dropzone)
        if self.session.busy:
            self.toast("Bitte warten, bis der laufende Vorgang beendet ist.", "warn")
            return
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            if self.mode != "console":
                self.tabs.setCurrentIndex(0)
            self.settings.setValue("lastdir", str(Path(paths[0]).parent))
            self.add_paths(paths)

    # ------------------------------------------------------------------ Fortschritt
    def show_progress(self, text: str, frac: float, state: str = "") -> None:
        self.progress_box.setVisible(True)
        self.progress_text.setText(text)
        self.progress_pct.setText(f"{int(frac * 100)} %")
        self.progress.setValue(int(max(0.0, min(1.0, frac)) * 1000))
        if self.progress.property("state") != state:
            self.progress.setProperty("state", state)
            repolish(self.progress)

    def on_progress(self, cur: int, total: int, desc: str) -> None:
        if total <= 0:
            return
        frac = cur / total
        if self.task == "flash" and self.flash_sizes:
            prev = self.flash_idx
            last_cur, last_total = self._p_last
            if last_total != -1 and (total != last_total or cur < last_cur):
                self.flash_idx = min(self.flash_idx + 1, len(self.flash_sizes) - 1)
            self._p_last = (cur, total)
            i = self.flash_idx
            if i != prev and prev < len(self.files):
                self._mark_bar_done(self.files[prev])
            f = self.files[i] if i < len(self.files) else None
            if f and f.widgets.get("bar"):
                bar = f.widgets["bar"]
                bar.setValue(int(frac * 1000))
            done = sum(self.flash_sizes[:i]) + frac * self.flash_sizes[i]
            overall = done / max(1, sum(self.flash_sizes))
            self.show_progress(f"Schreibe {f.name if f else ''} ({i + 1}/{len(self.flash_sizes)})", overall)
        elif self.task == "read":
            self.show_progress(f"Lese {fmt_size(cur)} / {fmt_size(total)}", frac, "read")
        else:
            self.show_progress(desc or "Arbeite …", frac)

    def _mark_bar_done(self, f: FileEntry) -> None:
        bar = f.widgets.get("bar")
        if bar:
            bar.setValue(1000)
            bar.setProperty("state", "done")
            repolish(bar)

    # ------------------------------------------------------------------ Aktionen: Programmieren
    def _start(self, task: str, fn) -> bool:
        self.task = task
        self._t0 = time.monotonic()
        ok = self.session.run(task, fn)
        if not ok:
            self.toast("Es läuft bereits ein Vorgang.", "warn")
        self.update_ui()
        return ok

    def do_connect(self) -> None:
        port = self.current_port()
        if not port:
            self.toast("Kein serieller Port ausgewählt.", "warn")
            return
        try:
            baud = int(self.baud_combo.currentText())
        except ValueError:
            self.toast("Ungültige Baudrate.", "err")
            return
        before = self.before_combo.currentText()
        trace = self.trace_chk.isChecked()
        no_stub = self.nostub_chk.isChecked()
        self.logger.set_verbosity("verbose" if trace else "auto")
        self.term.sys(f"Verbinde mit {port} @ {baud} Baud …")
        self._start("connect", lambda: self.session.connect(port, baud, before, trace, no_stub))

    def do_disconnect(self) -> None:
        self.session.disconnect()
        self.mode = "idle"
        self.freq_combo.clear()
        self.freq_combo.addItem("keep")
        self.size_combo.clear()
        self.size_combo.addItems(["keep", "detect"])
        self.term.sys("Verbindung getrennt.")
        self.update_ui()

    def _populate_flash_options(self) -> None:
        esp = self.session.esp
        freqs = sorted(getattr(esp, "FLASH_FREQUENCY", {}).keys(), key=sort_key(FREQ_ORDER))
        sizes = sorted(getattr(esp, "FLASH_SIZES", {}).keys(), key=sort_key(SIZE_ORDER))
        self.freq_combo.clear()
        self.freq_combo.addItems(["keep"] + freqs)
        self.size_combo.clear()
        self.size_combo.addItems(["keep", "detect"] + sizes)

    def do_program(self) -> None:
        err = self.validate_files()
        if err:
            self.toast(err, "err", 7000)
            self.term.sys(err, "err")
            return
        images = [(parse_addr(f.address), f.data) for f in self.files]
        self.flash_sizes = [len(f.data) for f in self.files]
        self.flash_idx = 0
        self._p_last = (-1, -1)
        for f in self.files:
            bar = f.widgets.get("bar")
            if bar:
                bar.setValue(0)
                bar.setProperty("state", "")
                repolish(bar)
        opts = dict(
            flash_mode=self.mode_combo.currentText(), flash_freq=self.freq_combo.currentText(),
            flash_size=self.size_combo.currentText(), erase_all=self.erase_all_chk.isChecked(),
            compress=self.compress_chk.isChecked(), skip_flashed=self.skip_chk.isChecked(),
            after=self.after_combo.currentText(),
        )
        total = sum(self.flash_sizes)
        self.term.sys(f"Programmiere {len(images)} Datei(en), {fmt_size(total)} …")
        self.show_progress("Starte …", 0)
        self._start("flash", lambda: self.session.flash(images, **opts))

    def do_erase(self) -> None:
        name = self.session.info.name if self.session.info else "dem Chip"
        r = QMessageBox.question(self, "Flash löschen", f"Den gesamten Flash von {name} wirklich löschen?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        self.show_progress("Lösche Flash … (kann bis zu 2 Minuten dauern)", 0)
        self.progress.setRange(0, 0)  # unbestimmt
        self._start("erase", self.session.erase)

    def set_full_read(self) -> None:
        if self.session.info and self.session.info.flash_bytes:
            self.read_addr.setText("0x0")
            self.read_size.setText(fmt_hex(self.session.info.flash_bytes))

    def do_read(self) -> None:
        addr = parse_addr(self.read_addr.text())
        size = parse_addr(self.read_size.text())
        if addr is None or size is None or size <= 0:
            self.toast("Startadresse oder Länge ungültig.", "err")
            return
        chip = re.sub(r"[^a-z0-9]+", "", (self.session.info.name if self.session.info else "esp").lower())
        default = str(Path(self._last_dir()) / f"flash_{chip}_{fmt_hex(addr)}_{fmt_hex(size)}.bin")
        path, _ = QFileDialog.getSaveFileName(self, "Flash-Inhalt speichern", default, "Binärdatei (*.bin)")
        if not path:
            return
        self.settings.setValue("lastdir", str(Path(path).parent))
        self._read_path = path
        self.show_progress(f"Lese {fmt_size(size)} ab {fmt_hex(addr)} …", 0, "read")
        self._start("read", lambda: self.session.read(addr, size, path))

    # ------------------------------------------------------------------ Ergebnisse
    def on_task_finished(self, task: str, result) -> None:
        secs = time.monotonic() - self._t0
        self.progress.setRange(0, 1000)
        if task == "connect":
            info: ChipInfo = result
            self.mode = "program"
            self._populate_flash_options()
            self.ci["chip"].setText(info.description or info.name)
            self.ci["features"].setText(", ".join(info.features) or "—")
            self.ci["crystal"].setText(info.crystal or "—")
            self.ci["mac"].setText(info.mac or "—")
            self.ci["flash"].setText(info.flash_size or "unbekannt")
            self.ci["boot"].setText(fmt_hex(info.bootloader_offset))
            if info.flash_bytes:
                self.read_size.setText(fmt_hex(info.flash_bytes))
            changed = False
            for f in self.files:
                if f.kind == "bin" and f.role == "bootloader":
                    a = fmt_hex(info.bootloader_offset)
                    if f.address != a:
                        f.address, changed = a, True
            if changed:
                self.sort_files()
                self.render_files()
                self.toast(f"Bootloader-Adresse für {info.name} auf {fmt_hex(info.bootloader_offset)} gesetzt.")
            self.term.sys(f"Verbunden: {info.description or info.name}", "ok")
            self.toast(f"Verbunden mit {info.name}")
        elif task == "flash":
            for f in self.files:
                self._mark_bar_done(f)
            total = sum(self.flash_sizes)
            self.show_progress(f"Fertig in {secs:.1f} s", 1.0, "done")
            self.term.sys(f"Programmieren abgeschlossen ({fmt_size(total)} in {secs:.1f} s).", "ok")
            self.toast(f"Erfolgreich programmiert ({secs:.1f} s).")
            if result in ("hard-reset", "soft-reset", "watchdog-reset"):
                self.term.sys("Chip wurde neu gestartet – Verbindung getrennt. Ausgabe über den Tab „Konsole“ ansehen.", "debug")
                self.do_disconnect()
        elif task == "erase":
            self.show_progress(f"Flash gelöscht ({secs:.1f} s)", 1.0, "done")
            self.term.sys(f"Flash vollständig gelöscht ({secs:.1f} s).", "ok")
            self.toast("Flash gelöscht.")
        elif task == "read":
            self.show_progress(f"Ausgelesen in {secs:.1f} s", 1.0, "done")
            self.term.sys(f"Gespeichert: {self._read_path}", "ok")
            self.toast(f"Gespeichert: {Path(self._read_path).name}")
        self.task = ""
        self.update_ui()

    def on_task_failed(self, task: str, msg: str) -> None:
        self.progress.setRange(0, 1000)
        first = msg.strip().splitlines()[0] if msg.strip() else "Unbekannter Fehler"
        self.term.write_kind(f"Fehler: {msg.strip()}\n", "err")
        labels = {"connect": "Verbindung fehlgeschlagen", "flash": "Programmieren fehlgeschlagen",
                  "erase": "Löschen fehlgeschlagen", "read": "Auslesen fehlgeschlagen"}
        self.toast(f"{labels.get(task, 'Fehler')}: {first}", "err", 8000)
        if task == "connect":
            self.mode = "idle"
            self.term.sys("Tipp: BOOT-Taste gedrückt halten und erneut verbinden, falls der Chip nicht antwortet.", "debug")
            self.progress_box.setVisible(False)
        else:
            self.show_progress(labels.get(task, "Fehler"), 1.0, "err")
        self.task = ""
        self.update_ui()

    # ------------------------------------------------------------------ Konsole
    def _update_eol(self) -> None:
        self.term.enter_sequence = {"CR+LF": b"\r\n", "LF": b"\n", "CR": b"\r", "keins": b"\r"}[self.eol_combo.currentText()]

    def console_start(self) -> None:
        port = self.current_port()
        if not port:
            self.toast("Kein serieller Port ausgewählt.", "warn")
            return
        try:
            baud = int(self.cbaud_combo.currentText())
        except ValueError:
            self.toast("Ungültige Baudrate.", "err")
            return
        self.console.reconnect_delay = self.delay_spin.value() / 1000
        self.console.max_retries = self.retry_spin.value()
        self.console.colorize = self.color_chk.isChecked()
        self.console.timestamps = self.stamp_chk.isChecked()
        try:
            self.console.start(port, baud)
        except Exception as exc:  # noqa: BLE001
            self.term.write_kind(f"Fehler: {exc}\n", "err")
            self.toast(f"Konsole konnte nicht gestartet werden: {exc}", "err", 8000)
            return
        self.mode = "console"
        self.term.sys(f"Konsole gestartet: {port} @ {baud} Baud", "note")
        self.update_ui()
        self.term.setFocus()

    def console_stop(self) -> None:
        self.console.stop()

    def on_console_stopped(self) -> None:
        if self.mode == "console":
            self.mode = "idle"
            self.term.sys("Konsole gestoppt.")
        self.update_ui()

    def console_reset(self) -> None:
        try:
            self.console.reset()
            self.term.sys("Reset ausgelöst.", "debug")
        except Exception as exc:  # noqa: BLE001
            self.toast(f"Reset fehlgeschlagen: {exc}", "err")

    def send_line(self) -> None:
        if self.mode != "console":
            return
        eol = {"CR+LF": "\r\n", "LF": "\n", "CR": "\r", "keins": ""}[self.eol_combo.currentText()]
        try:
            self.console.write((self.send_edit.text() + eol).encode("utf-8"))
            self.send_edit.clear()
        except Exception as exc:  # noqa: BLE001
            self.toast(f"Senden fehlgeschlagen: {exc}", "err")

    # ------------------------------------------------------------------ Terminal
    def copy_log(self) -> None:
        QGuiApplication.clipboard().setText(self.term.plain_text())
        self.toast("Terminal-Inhalt in die Zwischenablage kopiert.")

    def save_log(self) -> None:
        name = time.strftime("esp-log_%Y%m%d_%H%M%S.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Log speichern", str(Path(self._last_dir()) / name), "Textdatei (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(self.term.plain_text(), encoding="utf-8")
            self.toast(f"Gespeichert: {Path(path).name}")
        except OSError as exc:
            self.toast(f"Speichern fehlgeschlagen: {exc}", "err")

    # ------------------------------------------------------------------ Fenster
    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        enable_dark_titlebar(self)

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.session.busy:
            r = QMessageBox.question(self, "Vorgang läuft",
                                     "Es läuft gerade ein Flash-Vorgang. Wirklich beenden?\n"
                                     "Ein Abbruch kann eine unvollständige Firmware hinterlassen.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        self._save_settings()
        self._remember_offsets()
        try:
            self.console.stop()
        except Exception:
            pass
        if not self.session.busy:
            self.session.disconnect()
        e.accept()
