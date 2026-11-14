"""Leitet die Ausgaben von esptool (Logger + Fortschritt) in die Qt-Oberfläche um."""

from __future__ import annotations

import re
from typing import Any

from esp_pylib.logger import EspLogBase
from esptool.logger import log
from PySide6.QtCore import QObject, Signal

try:
    from rich.markup import render as _render_markup
except Exception:  # pragma: no cover
    _render_markup = None

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _plain(text: str) -> str:
    """Entfernt Rich-Markup ([bold] …) aus esptool-Meldungen."""
    if _render_markup is not None and "[" in text:
        try:
            return _render_markup(text).plain
        except Exception:
            return text
    return text


class LogSignals(QObject):
    text = Signal(str, str)               # Text, Art (info|note|warn|err|debug)
    progress = Signal(int, int, str)      # aktuell, gesamt, Beschreibung


class GuiLogger(EspLogBase):
    """esptool-Logger, der alles per Qt-Signal an die Oberfläche schickt (threadsicher)."""

    def __init__(self) -> None:
        self.signals = LogSignals()
        self.verbose = False
        self._pending = ""

    # --- Ausgabe -----------------------------------------------------------
    def _emit(self, text: str, kind: str = "info") -> None:
        self.signals.text.emit(text, kind)

    def print(self, *args: Any, **kwargs: Any) -> None:
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        text = _plain(sep.join(str(a) for a in args))
        text = _ANSI_RE.sub("", text)
        if kwargs.get("style") == "dim":  # Trace-Ausgaben
            self.flush_pending()
            self._emit(text.lstrip("\n") + ("\n" if end else ""), "debug")
            return
        self._pending += text + end
        if "\n" in self._pending:
            head, _, rest = self._pending.rpartition("\n")
            self._pending = rest
            self._emit(head + "\n")

    def flush_pending(self) -> None:
        if self._pending:
            self._emit(self._pending + "\n")
            self._pending = ""

    def note(self, *args: Any) -> None:
        self.flush_pending()
        self._emit("Hinweis: " + _plain(" ".join(str(a) for a in args)) + "\n", "note")

    def hint(self, *args: Any) -> None:
        self.flush_pending()
        self._emit(_plain(" ".join(str(a) for a in args)) + "\n", "note")

    def warn(self, *args: Any, suggestion: str | None = None) -> None:
        self.flush_pending()
        msg = _plain(" ".join(str(a) for a in args))
        if suggestion:
            msg += "\n  " + _plain(suggestion)
        self._emit("Warnung: " + msg + "\n", "warn")

    def err(self, *args: Any, suggestion: str | None = None) -> None:
        self.flush_pending()
        msg = _plain(" ".join(str(a) for a in args))
        if suggestion:
            msg += "\n  " + _plain(suggestion)
        self._emit("Fehler: " + msg + "\n", "err")

    # Kompatibilitäts-Aliase
    def warning(self, message: str, suggestion: str | None = None) -> None:
        self.warn(message, suggestion=suggestion)

    def error(self, message: str, suggestion: str | None = None) -> None:
        self.err(message, suggestion=suggestion)

    def debug(self, *args: Any) -> None:
        if self.verbose:
            self.flush_pending()
            self._emit(_plain("".join(str(a) for a in args)) + "\n", "debug")

    def die(self, *args: Any, exit_code: int = 1, suggestion: str | None = None):
        # Niemals das Programm beenden – stattdessen Ausnahme an den Worker geben
        self.err(*args, suggestion=suggestion)
        raise RuntimeError(" ".join(str(a) for a in args))

    def stage(self, finish: bool = False) -> None:
        pass

    def set_verbosity(self, mode: int | str) -> None:
        self.verbose = str(mode).lower() in ("verbose", "debug", "2", "3")

    def progress_bar(self, cur_iter: int, total_iters: int, prefix: str = "",
                     suffix: str = "", bar_length: int = 30) -> None:
        self.signals.progress.emit(int(cur_iter), int(total_iters), _plain(str(prefix)).strip())


_LOGGER: GuiLogger | None = None


def install_logger() -> GuiLogger:
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = GuiLogger()
        log.set_logger(_LOGGER)
    return _LOGGER
