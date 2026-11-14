#!/usr/bin/env python3
"""ESP-Flash-Tool MK1 – Startpunkt der Desktop-Anwendung."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Im PyInstaller-Fenstermodus gibt es keine Konsole – Ausgaben ins Leere leiten
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def resource(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def selftest(out: str) -> int:
    """Prüft im gebauten Programm, ob alle Bestandteile vorhanden sind (für GitHub Actions)."""
    lines, ok = [], True
    try:
        if not sys.platform.startswith("win"):
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import esptool
        from esptool.targets import CHIP_DEFS
        from PySide6.QtWidgets import QApplication
        from espflash import APP_VERSION
        stubs = list((Path(esptool.__file__).parent / "targets" / "stub_flasher").rglob("*.json"))
        lines.append(f"version={APP_VERSION} esptool={esptool.__version__} chips={len(CHIP_DEFS)} stubs={len(stubs)}")
        ok &= len(stubs) >= 10 and len(CHIP_DEFS) >= 10
        ok &= resource("assets", "icon.png").is_file()
        app = QApplication([sys.argv[0]])
        from espflash.mainwindow import MainWindow
        w = MainWindow(None)
        w._port_timer.stop()
        app.processEvents()
        lines.append("gui=ok")
    except Exception as exc:  # noqa: BLE001
        import traceback
        ok = False
        lines.append("FEHLER: " + "".join(traceback.format_exception(exc)))
    lines.append("SELFTEST OK" if ok else "SELFTEST FEHLGESCHLAGEN")
    Path(out).write_text("\n".join(lines), encoding="utf-8")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        code = selftest(sys.argv[i + 1] if i + 1 < len(sys.argv) else "selftest.txt")
        # sofort beenden – verhindert Abstürze beim Aufräumen der Qt-Objekte
        sys.stdout.flush()
        os._exit(code)

    if sys.platform.startswith("win"):
        try:  # eigenes Taskleisten-Symbol statt Python-Icon
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ESP-Flash-Tool-MK1")
        except Exception:
            pass

    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPen, QPixmap
    from PySide6.QtWidgets import QApplication

    from espflash import APP_NAME, APP_TITLE, APP_VERSION
    from espflash.theme import C, UI_FONTS, stylesheet

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_TITLE)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")

    pal = QPalette()
    for role, col in [
        (QPalette.ColorRole.Window, C["bg"]), (QPalette.ColorRole.WindowText, C["text"]),
        (QPalette.ColorRole.Base, C["bg"]), (QPalette.ColorRole.AlternateBase, C["panel"]),
        (QPalette.ColorRole.Text, C["text"]), (QPalette.ColorRole.Button, C["panel2"]),
        (QPalette.ColorRole.ButtonText, C["text"]), (QPalette.ColorRole.Highlight, C["amber"]),
        (QPalette.ColorRole.HighlightedText, "#1b1203"), (QPalette.ColorRole.ToolTipBase, C["panel2"]),
        (QPalette.ColorRole.ToolTipText, C["text"]), (QPalette.ColorRole.PlaceholderText, C["dim"]),
    ]:
        pal.setColor(role, QColor(col))
    app.setPalette(pal)

    font = QFont()
    font.setFamilies(UI_FONTS)
    font.setPointSizeF(9.5)
    app.setFont(font)

    # Häkchen für Checkboxen als kleine PNG-Datei erzeugen
    check = Path(tempfile.gettempdir()) / "esp-flash-tool-check.png"
    pm = QPixmap(26, 26)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#062420"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPolyline([QPointF(6, 13.5), QPointF(11, 18.5), QPointF(20, 8)])
    p.end()
    pm.save(str(check))
    arrow = Path(tempfile.gettempdir()) / "esp-flash-tool-arrow.png"
    pm = QPixmap(20, 12)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(C["muted"]), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPolyline([QPointF(3, 3), QPointF(10, 9), QPointF(17, 3)])
    p.end()
    pm.save(str(arrow))
    app.setStyleSheet(stylesheet(check.as_posix(), arrow.as_posix()))

    icon = resource("assets", "icon.png")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))

    from espflash.mainwindow import MainWindow
    win = MainWindow(str(icon) if icon.is_file() else None)
    win.show()

    # Dateien, die per "Öffnen mit" / auf die exe gezogen wurden, direkt übernehmen
    files = [a for a in sys.argv[1:] if Path(a).suffix.lower() in (".bin", ".hex") and Path(a).is_file()]
    if files:
        win.add_paths(files)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
