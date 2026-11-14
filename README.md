# ESP-Flash-Tool MK1

Vollständig **offline** lauffähige Version von [esptool-js](https://espressif.github.io/esptool-js/) – dem seriellen Flasher für Espressif-Chips – als Windows-Programm im Dashboard-Design.

![Screenshot](assets/screenshot.png)

**Version:** 1.0.0 · **esptool-js:** 0.7.1

## Funktionen

Alles, was die Original-Seite kann:

- **Verbinden** mit ESP32, ESP32-S2/S3, C2/C3/C5/C6/C61, H2/H4, P4, ESP8266 u. a. (Baudrate 115200 – 921600)
- **Programmieren** beliebig vieler `.bin`-Dateien mit frei wählbarer Adresse
- **Intel-HEX-Dateien** (`.hex`) – jedes Segment wird mit seiner Adresse übernommen
- Flash-Modus, Flash-Frequenz und Flash-Größe (Auswahl passend zum erkannten Chip)
- **Gesamten Flash löschen** bzw. vor dem Programmieren komplett löschen
- **Konsole** (serieller Monitor) mit automatischer Wiederverbindung, Reset-Taste und IDF-Log-Einfärbung (E/W/I)
- Debug-Log, Trace kopieren, WebUSB-Modus für CH340

Zusätzlich:

- **Drag & Drop** von `.bin`/`.hex` auf das Fenster
- **Automatische Adressvorschläge** anhand des Dateinamens (bootloader → chipabhängig 0x0/0x1000/0x2000, partition-table → 0x8000, ota_data → 0xd000, boot_app0 → 0xe000, merged/factory → 0x0, Anwendung → 0x10000); manuell geänderte Adressen werden pro Dateiname gemerkt
- Prüfung auf doppelte oder **überlappende Adressen**
- **Chip-Infokarte** (Chip, Features, Quarz, MAC, Flash-Größe, Bootloader-Adresse)
- **Flash auslesen (Backup)** als `.bin` – ganzer Flash oder Bereich
- Reset-Modus vor/nach dem Flashen, Komprimierung und MD5-Prüfung abschaltbar
- **Text senden** in der Konsole (CR+LF / LF / CR), Tastatureingabe direkt im Terminal, Zeitstempel
- Terminal-**Log speichern**
- Einstellungen bleiben erhalten

## Benutzung

1. ZIP aus dem GitHub-Release (oder dem Actions-Artefakt) entpacken.
2. `ESP-Flash-Tool-MK1.exe` starten – es öffnet sich ein eigenes Programmfenster.
3. Board per USB anschließen, **Verbinden** klicken und den COM-Port auswählen.
4. Dateien hinzufügen, Adressen prüfen, **Programmieren**.

Das Fenster nutzt die Web-Serial-Schnittstelle von **Microsoft Edge** (bei Windows 10/11 immer vorhanden) oder **Google Chrome**. Das Programm startet dafür automatisch ein separates App-Fenster mit eigenem Profil; eine Internetverbindung wird nie benötigt. Beim Schließen des Fensters beendet sich das Programm nach wenigen Sekunden selbst.

Treiber für USB-UART-Wandler (CP210x, CH34x, FTDI) müssen wie bei jedem Flash-Tool installiert sein.

### Startoptionen

```
ESP-Flash-Tool-MK1.exe --port 8775     anderen lokalen Port verwenden (Standard 8775)
ESP-Flash-Tool-MK1.exe --no-browser    nur Server starten, Adresse selbst in Edge/Chrome öffnen
ESP-Flash-Tool-MK1.exe --version
```

Der Server lauscht ausschließlich auf `127.0.0.1` (Web Serial funktioniert nur in einem sicheren Kontext, also lokal).

## Projektaufbau

```
.github/workflows/build-exe.yml   GitHub Actions: Frontend bauen → exe (PyInstaller) → ZIP / Release
app.py                            Python-Starter: lokaler Webserver + App-Fenster (nur Standardbibliothek)
src/main.js                       Oberfläche & Logik (nutzt esptool-js)
web/index.html, web/style.css     Layout und Dashboard-Design
web/dist/                         gebündeltes Frontend (wird durch "npm run build" erzeugt)
build.mjs                         esbuild-Konfiguration
assets/                           Icon und Screenshot
```

## Build per GitHub Actions

- Jeder Push auf `main`/`master` erzeugt ein Artefakt `ESP-Flash-Tool-MK1-v<Version>-windows.zip` (exe + README + Lizenzen).
- Ein Tag `v*` (z. B. `v1.0.0`) erzeugt zusätzlich ein GitHub-Release mit der ZIP-Datei.
- Die Versionsnummer steht in `package.json` **und** `app.py` (`APP_VERSION`) – der Workflow bricht ab, wenn sie nicht übereinstimmen.

## Lokal bauen / starten

```bash
npm ci
npm run build
python app.py                 # startet ohne exe
pip install pyinstaller
pyinstaller --onefile --windowed --name ESP-Flash-Tool-MK1 --icon assets/icon.ico --add-data "web;web" app.py
```

## Lizenzen

Basiert auf [esptool-js](https://github.com/espressif/esptool-js) von Espressif (Apache-2.0). Übersicht aller gebündelten Bibliotheken: [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
