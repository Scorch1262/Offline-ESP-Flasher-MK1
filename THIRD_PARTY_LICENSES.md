# Verwendete Fremdsoftware

Das ESP-Flash-Tool MK1 bündelt folgende Open-Source-Bibliotheken (alle offline in `web/dist/app.js` enthalten):

| Paket | Version | Lizenz | Quelle |
|---|---|---|---|
| esptool-js (inkl. Flasher-Stubs) | 0.7.1 | Apache-2.0 | https://github.com/espressif/esptool-js |
| @xterm/xterm | 6.0.0 | MIT | https://github.com/xtermjs/xterm.js |
| @xterm/addon-fit | 0.11.0 | MIT | https://github.com/xtermjs/xterm.js |
| web-serial-polyfill | 1.0.15 | Apache-2.0 | https://github.com/google/web-serial-polyfill |
| spark-md5 | 3.0.2 | MIT / WTFPL | https://github.com/satazor/js-spark-md5 |
| pako | 2.2.0 | MIT und Zlib | https://github.com/nodeca/pako |
| atob-lite | 2.0.0 | MIT | https://github.com/hughsk/atob-lite |

Die Windows-exe wird mit PyInstaller (GPL mit Bootloader-Ausnahme) aus Python (PSF-Lizenz) erzeugt.

Die vollständigen Lizenztexte liegen in den jeweiligen Paketen unter `node_modules/` bzw. in den verlinkten Repositories.
