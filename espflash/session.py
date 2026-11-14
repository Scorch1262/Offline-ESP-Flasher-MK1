"""Verbindung zum ESP-Chip über das offizielle Python-esptool.

Alle Chip-Operationen laufen in einem Hintergrund-Thread; Ergebnisse und Fehler
werden per Qt-Signal an die Oberfläche gemeldet.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from esptool.cmds import (
    attach_flash,
    connect_esp,
    detect_flash_size,
    erase_flash,
    erase_region,
    read_flash,
    reset_chip,
    run_stub,
    write_flash,
)
from esptool.loader import ESPLoader
from esptool.util import FatalError, NotImplementedInROMError
from esptool.logger import log
from esp_pylib.logger import EspLog
from PySide6.QtCore import QObject, Signal

ROM_BAUD = ESPLoader.ESP_ROM_BAUD  # 115200


@dataclass
class ChipInfo:
    name: str = ""
    description: str = ""
    features: list[str] = field(default_factory=list)
    crystal: str = ""
    mac: str = ""
    usb_mode: str = ""
    flash_size: str = ""
    flash_bytes: int = 0
    bootloader_offset: int = 0x1000
    secure_download: bool = False
    port: str = ""


def flash_size_bytes(size: str | None) -> int:
    if not size:
        return 0
    s = size.upper().split("-")[0]
    try:
        if s.endswith("KB"):
            return int(s[:-2]) * 1024
        if s.endswith("MB"):
            return int(s[:-2]) * 1024 * 1024
    except ValueError:
        pass
    return 0


def _flush_log() -> None:
    inst = EspLog.instance
    fn = getattr(inst, "flush_pending", None)
    if fn:
        fn()


class TaskSignals(QObject):
    finished = Signal(str, object)   # Aufgabe, Ergebnis
    failed = Signal(str, str)        # Aufgabe, Fehlermeldung


class FlashSession:
    """Hält die offene Verbindung (ESPLoader mit Stub) zwischen den Aktionen."""

    def __init__(self) -> None:
        self.esp: ESPLoader | None = None
        self.info: ChipInfo | None = None
        self.signals = TaskSignals()
        self.busy = False
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self.esp is not None

    # ------------------------------------------------------------------
    def run(self, name: str, fn: Callable[[], Any]) -> bool:
        """Führt fn() im Hintergrund aus. Gibt False zurück, falls bereits beschäftigt."""
        with self._lock:
            if self.busy:
                return False
            self.busy = True

        def worker():
            try:
                result = fn()
                _flush_log()
            except Exception as exc:  # noqa: BLE001
                _flush_log()
                msg = str(exc) or exc.__class__.__name__
                if not isinstance(exc, (FatalError, OSError)):
                    msg += "\n" + traceback.format_exc(limit=3)
                self.busy = False
                self.signals.failed.emit(name, msg)
                return
            self.busy = False
            self.signals.finished.emit(name, result)

        threading.Thread(target=worker, name=f"esp-{name}", daemon=True).start()
        return True

    # ------------------------------------------------------------------
    def connect(self, port: str, baud: int, before: str, trace: bool, no_stub: bool = False) -> ChipInfo:
        initial_baud = baud if before == "no-reset-no-sync" else min(ROM_BAUD, baud)
        log.print(f"Verbinde mit {port} …")
        esp = connect_esp(port=port, initial_baud=initial_baud, before=before, trace=trace)
        try:
            info = ChipInfo(name=esp.CHIP_NAME, port=port)
            info.secure_download = bool(esp.secure_download_mode)
            info.bootloader_offset = int(getattr(esp, "BOOTLOADER_FLASH_OFFSET", 0x1000))
            log.print(f"Verbunden mit {esp.CHIP_NAME} an {port}:")
            if esp.secure_download_mode:
                info.description = f"{esp.CHIP_NAME} (Secure Download Mode)"
                log.print(f"{'Chip-Typ:':<20}{info.description}")
            else:
                info.description = esp.get_chip_description()
                info.features = list(esp.get_chip_features())
                info.crystal = f"{esp.get_crystal_freq()} MHz"
                try:
                    usb = esp.get_usb_mode()
                    info.usb_mode = usb or ""
                except Exception:
                    pass
                try:
                    mac = esp.read_mac("BASE_MAC")
                    if mac:
                        info.mac = ":".join(f"{b:02x}" for b in mac)
                except Exception:
                    pass
                log.print(f"{'Chip-Typ:':<20}{info.description}")
                log.print(f"{'Features:':<20}{', '.join(info.features)}")
                log.print(f"{'Quarz:':<20}{info.crystal}")
                if info.usb_mode:
                    log.print(f"{'USB-Modus:':<20}{info.usb_mode}")
                if info.mac:
                    log.print(f"{'MAC:':<20}{info.mac}")

            if no_stub:
                log.print("Flasher-Stub deaktiviert – arbeite direkt mit dem ROM-Bootloader.")
            else:
                esp = run_stub(esp)
            if baud > initial_baud:
                try:
                    esp.change_baud(baud)
                except NotImplementedInROMError:
                    log.warn(f"ROM unterstützt keinen Baudratenwechsel – bleibe bei {initial_baud}.")
            attach_flash(esp)
            if not esp.secure_download_mode:
                try:
                    info.flash_size = detect_flash_size(esp) or ""
                except Exception as exc:  # noqa: BLE001
                    log.warn(f"Flash-Größe nicht ermittelbar: {exc}")
            info.flash_bytes = flash_size_bytes(info.flash_size)
            if info.flash_size:
                log.print(f"{'Flash-Größe:':<20}{info.flash_size}")
            log.print("Bereit.")
        except Exception:
            try:
                esp._port.close()
            except Exception:
                pass
            raise
        self.esp = esp
        self.info = info
        return info

    def disconnect(self) -> None:
        esp, self.esp, self.info = self.esp, None, None
        if esp is not None:
            try:
                esp._port.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def flash(self, images: list[tuple[int, bytes]], *, flash_mode: str, flash_freq: str,
              flash_size: str, erase_all: bool, compress: bool, skip_flashed: bool,
              after: str) -> str:
        assert self.esp is not None
        kwargs: dict[str, Any] = {"erase_all": erase_all}
        if compress:
            kwargs["compress"] = True
        else:
            kwargs["no_compress"] = True
        if skip_flashed and not erase_all:
            kwargs["skip_flashed"] = True
        write_flash(self.esp, images, flash_freq=flash_freq, flash_mode=flash_mode,
                    flash_size=flash_size, **kwargs)
        reset_chip(self.esp, after)
        return after

    def erase(self) -> None:
        assert self.esp is not None
        if self.esp.IS_STUB:
            erase_flash(self.esp)
            return
        # Der ROM-Bootloader kennt kein "Chip löschen" – Bereich über die volle Flash-Größe löschen
        size = self.info.flash_bytes if self.info and self.info.flash_bytes else 0
        if not size:
            raise FatalError("Flash-Größe unbekannt – Löschen ohne Flasher-Stub nicht möglich.")
        log.print(f"ROM-Modus: lösche Bereich 0x0 – {size:#x} …")
        erase_region(self.esp, 0, size)

    def read(self, address: int, size: int, path: str) -> int:
        assert self.esp is not None
        read_flash(self.esp, address, size, output=path)
        return size

    def reset(self, mode: str) -> None:
        assert self.esp is not None
        reset_chip(self.esp, mode)
