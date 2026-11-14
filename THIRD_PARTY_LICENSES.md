# Verwendete Fremdsoftware

Die Windows-exe des ESP-Flash-Tool MK1 enthält folgende Open-Source-Komponenten:

| Paket | Version | Lizenz | Quelle |
|---|---|---|---|
| esptool (inkl. Flasher-Stubs) | 5.6.0 | GPL-2.0-or-later | https://github.com/espressif/esptool |
| esp-pylib | 1.x | Apache-2.0 | https://github.com/espressif/esp-pylib |
| PySide6 / Qt | 6.12.0 | LGPL-3.0 | https://www.qt.io/qt-for-python |
| pyserial | 3.5 | BSD-3-Clause | https://github.com/pyserial/pyserial |
| intelhex | 2.x | BSD-3-Clause | https://github.com/python-intelhex/intelhex |
| rich, rich-click, click | – | MIT / BSD | https://github.com/Textualize/rich |
| cryptography, reedsolo, PyYAML | – | Apache-2.0/BSD, Public Domain/MIT, MIT | (Abhängigkeiten von esptool) |
| Python | 3.12 | PSF-2.0 | https://www.python.org |
| PyInstaller-Bootloader | – | GPL-2.0 mit Ausnahme für gebündelte Programme | https://pyinstaller.org |

Weil esptool unter der GPL-2.0-or-later steht, wird die gebaute exe ebenfalls unter **GPL-2.0-or-later** weitergegeben. Der vollständige Quelltext liegt in diesem Repository; der Lizenztext von esptool liegt der ZIP-Datei als `LICENSE-esptool-GPL-2.0.txt` bei.

PySide6/Qt wird unter der LGPL-3.0 genutzt (dynamisch gelinkte Qt-Bibliotheken innerhalb des PyInstaller-Pakets).
