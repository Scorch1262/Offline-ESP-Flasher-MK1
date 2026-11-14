"""Serieller Monitor (Konsole) mit automatischer Wiederverbindung."""

from __future__ import annotations

import codecs
import re
import threading
import time
from datetime import datetime

import serial
from serial.tools import list_ports
from PySide6.QtCore import QObject, Signal

IDF_LOG_RE = re.compile(r"^(I|W|E) \([\d.: -]+\)")
RED, GREEN, YELLOW, DIM, NORMAL = "\x1b[1;31m", "\x1b[0;32m", "\x1b[0;33m", "\x1b[2m", "\x1b[0m"


def port_identity(device: str) -> tuple | None:
    for p in list_ports.comports():
        if p.device == device:
            return (p.vid, p.pid, p.serial_number)
    return None


def find_port(device: str, identity: tuple | None) -> str | None:
    ports = list(list_ports.comports())
    for p in ports:
        if p.device == device:
            return p.device
    if identity and identity[0] is not None:
        for p in ports:
            if (p.vid, p.pid, p.serial_number) == identity:
                return p.device
    return None


class ConsoleSignals(QObject):
    data = Signal(str)          # aufbereiteter Text (mit ANSI-Farben)
    status = Signal(str, str)   # Meldung, Art
    stopped = Signal()


class SerialConsole:
    def __init__(self) -> None:
        self.signals = ConsoleSignals()
        self.ser: serial.Serial | None = None
        self.port = ""
        self.baud = 115200
        self.colorize = True
        self.timestamps = False
        self.reconnect_delay = 1.0
        self.max_retries = 5
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._identity: tuple | None = None
        self._write_lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    def _open(self, device: str) -> serial.Serial:
        s = serial.serial_for_url(device, do_not_open=True)
        s.baudrate = self.baud
        s.timeout = 0.05
        s.write_timeout = 2
        # DTR/RTS vor dem Öffnen inaktiv lassen, damit der Chip nicht im Reset hängt
        s.dtr = False
        s.rts = False
        s.open()
        return s

    def start(self, port: str, baud: int) -> None:
        if self.running:
            return
        self.port = port
        self.baud = baud
        self._identity = port_identity(port)
        self.ser = self._open(port)   # Fehler gehen direkt an den Aufrufer
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="serial-console", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        self._close()

    def _close(self) -> None:
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    # ------------------------------------------------------------------
    def write(self, data: bytes) -> None:
        with self._write_lock:
            if self.ser is not None and self.ser.is_open:
                self.ser.write(data)

    def reset(self) -> None:
        """Chip über RTS (EN) neu starten – wie esptool 'hard_reset'."""
        if self.ser is None:
            return
        with self._write_lock:
            s = self.ser
            s.dtr = False
            s.rts = True
            s.dtr = s.dtr  # Windows-Workaround: DTR erneut setzen, damit RTS wirkt
            time.sleep(0.1)
            s.rts = False
            s.dtr = s.dtr

    # ------------------------------------------------------------------
    def _stamp(self) -> str:
        if not self.timestamps:
            return ""
        return f"{DIM}[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}]{NORMAL} "

    def _color(self, line: str) -> str:
        if not self.colorize:
            return line
        m = IDF_LOG_RE.match(line)
        if not m:
            return line
        c = RED if m.group(1) == "E" else YELLOW if m.group(1) == "W" else GREEN
        return c + line + NORMAL

    def _loop(self) -> None:
        buf = ""
        at_line_start = True
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        last_rx = time.monotonic()
        while not self._stop.is_set():
            try:
                assert self.ser is not None
                chunk = self.ser.read(self.ser.in_waiting or 1)
            except Exception as exc:  # Gerät getrennt
                if self._stop.is_set():
                    break
                if buf:
                    self.signals.data.emit((self._stamp() if at_line_start else "") + buf)
                    buf, at_line_start = "", False
                self.signals.status.emit(f"Gerät getrennt ({exc.__class__.__name__}). Versuche erneut zu verbinden …", "warn")
                if not self._reconnect():
                    break
                continue

            out = []
            if chunk:
                last_rx = time.monotonic()
                buf += decoder.decode(chunk)
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.rstrip("\r")
                    out.append((self._stamp() + self._color(line) if at_line_start else line) + "\n")
                    at_line_start = True
            elif buf and time.monotonic() - last_rx > 0.06:
                # unvollständige Zeile (z. B. Eingabe-Prompt) trotzdem anzeigen
                out.append((self._stamp() if at_line_start else "") + buf)
                buf, at_line_start = "", False
            if out:
                self.signals.data.emit("".join(out))

        self._close()
        self.signals.stopped.emit()

    def _reconnect(self) -> bool:
        self._close()
        for attempt in range(1, self.max_retries + 1):
            if self._stop.wait(self.reconnect_delay):
                return False
            self.signals.status.emit(f"[RECONNECT] Versuch {attempt}/{self.max_retries} …", "warn")
            dev = find_port(self.port, self._identity)
            if dev:
                try:
                    self.ser = self._open(dev)
                    self.port = dev
                    self.signals.status.emit(f"[RECONNECT] Wieder verbunden ({dev}).", "ok")
                    return True
                except Exception as exc:  # noqa: BLE001
                    self.signals.status.emit(f"[RECONNECT] {exc}", "warn")
        self.signals.status.emit(
            f"[RECONNECT] Nach {self.max_retries} Versuchen nicht wieder verbunden. Konsole gestoppt.", "err")
        return False
