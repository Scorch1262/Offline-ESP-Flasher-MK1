#!/usr/bin/env python3
"""ESP-Flash-Tool MK1 – Offline-Version von esptool-js.

Startet einen kleinen lokalen Webserver (nur 127.0.0.1) und öffnet die
Oberfläche als eigenes App-Fenster in Microsoft Edge oder Google Chrome
(Web Serial wird nur von Chromium-Browsern unterstützt).
Der Server beendet sich automatisch, sobald das Fenster geschlossen wurde.

Aufruf:
    ESP-Flash-Tool-MK1.exe              normal starten
    ESP-Flash-Tool-MK1.exe --port 8775  festen Port verwenden
    ESP-Flash-Tool-MK1.exe --no-browser nur Server starten (Adresse wird ausgegeben)
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP_NAME = "ESP-Flash-Tool-MK1"
APP_VERSION = "1.0.0"
HOST = "127.0.0.1"
DEFAULT_PORT = 8775  # bewusst abseits der im Netz belegten Ports (5000-5003, 8000-8097)

# Wie lange ohne Lebenszeichen gewartet wird, bevor sich der Server beendet.
# Großzügig gewählt, weil Browser Timer in Hintergrundfenstern drosseln.
IDLE_TIMEOUT = 180.0
BYE_GRACE = 6.0          # nach dem Schließen des letzten Fensters (Reload abfangen)
STARTUP_TIMEOUT = 120.0  # wenn nie ein Fenster verbunden hat

# Im PyInstaller-Fenstermodus gibt es keine Konsole – Ausgaben ins Leere leiten
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")


def resource_dir() -> Path:
    """Ordner mit den Web-Dateien – im PyInstaller-Paket oder neben app.py."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "web"


def data_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    d = Path(root) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


class ClientTracker:
    """Merkt sich offene Fenster anhand ihrer Pings."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.clients: dict[str, float] = {}
        self.ever_connected = False
        self.last_empty: float | None = None
        self.started = time.monotonic()

    def ping(self, cid: str) -> None:
        with self.lock:
            self.clients[cid] = time.monotonic()
            self.ever_connected = True
            self.last_empty = None

    def bye(self, cid: str) -> None:
        with self.lock:
            self.clients.pop(cid, None)
            if not self.clients:
                self.last_empty = time.monotonic()

    def should_exit(self) -> bool:
        now = time.monotonic()
        with self.lock:
            for cid, ts in list(self.clients.items()):
                if now - ts > IDLE_TIMEOUT:
                    del self.clients[cid]
                    if not self.clients:
                        self.last_empty = now
            if not self.ever_connected:
                return now - self.started > STARTUP_TIMEOUT
            if self.clients:
                return False
            return self.last_empty is not None and now - self.last_empty > BYE_GRACE


TRACKER = ClientTracker()


class Handler(SimpleHTTPRequestHandler):
    server_version = f"{APP_NAME}/{APP_VERSION}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(resource_dir()), **kwargs)

    def log_message(self, fmt, *args):  # ruhig bleiben
        if os.environ.get("ESPFLASH_DEBUG"):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _json(self, obj, status=HTTPStatus.OK):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api(self):
        url = urlparse(self.path)
        if not url.path.startswith("/api/"):
            return False
        cid = (parse_qs(url.query).get("id") or [""])[0][:64]
        if url.path == "/api/ping" and cid:
            TRACKER.ping(cid)
            self._json({"ok": True})
        elif url.path == "/api/bye" and cid:
            TRACKER.bye(cid)
            self._json({"ok": True})
        elif url.path == "/api/info":
            self._json({"app": APP_NAME, "version": APP_VERSION})
        else:
            self._json({"error": "unbekannt"}, HTTPStatus.NOT_FOUND)
        return True

    def do_GET(self):
        if not self._api():
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(min(length, 65536))
        if not self._api():
            self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
            return True
        except OSError:
            return False


def running_instance(port: int) -> bool:
    """Prüft, ob auf dem Port bereits dieses Programm läuft."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/info", timeout=1.5) as r:
            return json.loads(r.read().decode()).get("app") == APP_NAME
    except Exception:
        return False


def find_browser() -> str | None:
    """Sucht Edge oder Chrome (Chromium-basiert, unterstützt Web Serial)."""
    candidates: list[str] = []
    if sys.platform.startswith("win"):
        for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if not base:
                continue
            candidates += [
                os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(base, "Chromium", "Application", "chrome.exe"),
                os.path.join(base, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            ]
    elif sys.platform == "darwin":
        candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
            p = shutil.which(name)
            if p:
                candidates.append(p)
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def open_window(url: str) -> None:
    browser = find_browser()
    if browser:
        profile = data_dir() / "browser-profile"
        args = [
            browser,
            f"--app={url}",
            f"--user-data-dir={profile}",
            "--window-size=1400,900",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate",
        ]
        try:
            flags = 0
            if sys.platform.startswith("win"):
                flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(args, close_fds=True, creationflags=flags,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception as exc:  # pragma: no cover
            print(f"Browser konnte nicht gestartet werden: {exc}")
    print("Kein Edge/Chrome gefunden – öffne Standardbrowser (Web Serial nur in Chromium-Browsern).")
    webbrowser.open(url)


def show_error(msg: str) -> None:
    print(msg, file=sys.stderr)
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, APP_NAME, 0x10)
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(prog=APP_NAME, description="Offline-Version von esptool-js")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port (Standard {DEFAULT_PORT})")
    ap.add_argument("--no-browser", action="store_true", help="kein Fenster öffnen, Server läuft bis Strg+C")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    args = ap.parse_args()

    if not (resource_dir() / "index.html").is_file():
        show_error(f"Web-Dateien nicht gefunden: {resource_dir()}")
        return 1
    if not (resource_dir() / "dist" / "app.js").is_file():
        show_error("web/dist/app.js fehlt – bitte zuerst 'npm install' und 'npm run build' ausführen.")
        return 1

    port = args.port
    if running_instance(port):
        # Programm läuft schon → nur ein weiteres Fenster öffnen
        open_window(f"http://{HOST}:{port}/")
        return 0
    if not port_free(port):
        for p in range(port + 1, port + 50):
            if port_free(p):
                port = p
                break
        else:
            show_error("Kein freier lokaler Port gefunden.")
            return 1

    server = ThreadingHTTPServer((HOST, port), Handler)
    server.daemon_threads = True
    url = f"http://{HOST}:{port}/"
    print(f"{APP_NAME} v{APP_VERSION} läuft auf {url}")

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    if args.no_browser:
        print("Beenden mit Strg+C")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        open_window(url)
        try:
            while not TRACKER.should_exit():
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    server.shutdown()
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
