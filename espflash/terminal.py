"""Terminal-Anzeige mit ANSI-Farben und Tastatur-Weiterleitung an die Konsole."""

from __future__ import annotations

import re
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from .theme import C, MONO_FONTS

ANSI_RE = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")

BASE = [C["black"], C["red"], C["green"], C["amber"], C["blue"], C["magenta"], C["teal"], C["text"]]
BRIGHT = ["#56626d", "#ff7a77", "#6cf0a8", "#ffcf6e", "#8cc4ff", "#e0b3ff", "#7cf0e0", "#ffffff"]

KIND_COLORS = {
    "info": C["text"], "note": C["teal"], "warn": C["amber"], "err": C["red"],
    "debug": C["dim"], "sys": C["amber"], "ok": C["green"],
}


class TerminalView(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("terminal")
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setMaximumBlockCount(20000)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        font = QFont()
        font.setFamilies(MONO_FONTS)
        font.setPointSizeF(10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.key_sink: Callable[[bytes], None] | None = None
        self.enter_sequence = b"\r\n"
        self._fmt = self._default_fmt()
        self._fg_bold = False

    # ------------------------------------------------------------------
    def _default_fmt(self) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(C["text"]))
        return f

    def _at_bottom(self) -> bool:
        sb = self.verticalScrollBar()
        return sb.value() >= sb.maximum() - 4

    def _insert(self, text: str, fmt: QTextCharFormat) -> None:
        if not text:
            return
        cur = QTextCursor(self.document())
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertText(text, fmt)

    def write_ansi(self, text: str) -> None:
        """Text mit ANSI-SGR-Farbcodes anhängen."""
        follow = self._at_bottom()
        text = text.replace("\r\n", "\n").replace("\r", "")
        pos = 0
        for m in ANSI_RE.finditer(text):
            self._insert(text[pos:m.start()], self._fmt)
            pos = m.end()
            if m.group(2) == "m":
                self._apply_sgr(m.group(1))
        self._insert(text[pos:], self._fmt)
        if follow:
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def write_kind(self, text: str, kind: str = "info") -> None:
        follow = self._at_bottom()
        f = QTextCharFormat()
        f.setForeground(QColor(KIND_COLORS.get(kind, C["text"])))
        self._insert(text.replace("\r\n", "\n").replace("\r", ""), f)
        if follow:
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def sys(self, text: str, kind: str = "sys") -> None:
        self.write_kind(f"» {text}\n", kind)

    def _apply_sgr(self, params: str) -> None:
        codes = [int(p) if p.isdigit() else 0 for p in params.split(";")] if params else [0]
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                self._fmt = self._default_fmt()
                self._fg_bold = False
            elif c == 1:
                self._fg_bold = True
                self._fmt.setFontWeight(QFont.Weight.Bold)
            elif c == 2:
                self._fmt.setForeground(QColor(C["dim"]))
            elif c == 22:
                self._fmt.setFontWeight(QFont.Weight.Normal)
            elif 30 <= c <= 37:
                self._fmt.setForeground(QColor(BASE[c - 30]))
            elif 90 <= c <= 97:
                self._fmt.setForeground(QColor(BRIGHT[c - 90]))
            elif c == 39:
                self._fmt.setForeground(QColor(C["text"]))
            elif c == 38 and i + 1 < len(codes):
                if codes[i + 1] == 2 and i + 4 < len(codes):
                    r, g, b = codes[i + 2:i + 5]
                    self._fmt.setForeground(QColor(r, g, b))
                    i += 4
                elif codes[i + 1] == 5 and i + 2 < len(codes):
                    n = codes[i + 2]
                    if n < 8:
                        self._fmt.setForeground(QColor(BASE[n]))
                    elif n < 16:
                        self._fmt.setForeground(QColor(BRIGHT[n - 8]))
                    i += 2
            i += 1

    # ------------------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.matches(QKeySequence.StandardKey.Copy) and (self.key_sink is None or self.textCursor().hasSelection()):
            self.copy()
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            super().keyPressEvent(event)
            return
        if self.key_sink is None:
            super().keyPressEvent(event)
            return
        key = event.key()
        data = b""
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            data = self.enter_sequence or b"\r"
        elif key == Qt.Key.Key_Backspace:
            data = b"\x08"
        elif key == Qt.Key.Key_Tab:
            data = b"\t"
        elif key == Qt.Key.Key_Escape:
            data = b"\x1b"
        elif key == Qt.Key.Key_Up:
            data = b"\x1b[A"
        elif key == Qt.Key.Key_Down:
            data = b"\x1b[B"
        elif key == Qt.Key.Key_Right:
            data = b"\x1b[C"
        elif key == Qt.Key.Key_Left:
            data = b"\x1b[D"
        elif event.modifiers() & Qt.KeyboardModifier.ControlModifier and Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            data = bytes([key - Qt.Key.Key_A + 1])
        elif event.text():
            data = event.text().encode("utf-8")
        if data:
            self.key_sink(data)
        else:
            super().keyPressEvent(event)

    def plain_text(self) -> str:
        return self.toPlainText()
