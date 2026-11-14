// ESP-Flash-Tool MK1 – Oberfläche für esptool-js (komplett offline)
// Funktionsumfang entspricht https://espressif.github.io/esptool-js/
// plus: Drag & Drop, automatische Adressvorschläge, Flash-Backup, Senden in der Konsole.

import { ESPLoader, Transport, WebUSBSerialPort, parseIntelHex } from "esptool-js";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import SparkMD5 from "spark-md5";
import { serial as serialPolyfill } from "web-serial-polyfill";

/* global __APP_VERSION__, __ESPTOOL_VERSION__ */
const APP_VERSION = __APP_VERSION__;
const ESPTOOL_VERSION = __ESPTOOL_VERSION__;

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ------------------------------------------------------------------ */
/* DOM                                                                 */
/* ------------------------------------------------------------------ */
const el = {
  appVersion: $("appVersion"), footerInfo: $("footerInfo"), browserWarn: $("browserWarn"),
  statusPill: $("statusPill"), statusText: $("statusText"), topDevice: $("topDevice"), topMode: $("topMode"),
  tabProgram: $("tabProgram"), tabConsole: $("tabConsole"), pageProgram: $("pageProgram"), pageConsole: $("pageConsole"),
  baudrates: $("baudrates"), beforeMode: $("beforeMode"), debugLogging: $("debugLogging"), useWebUsb: $("useWebUsb"),
  connectButton: $("connectButton"), disconnectButton: $("disconnectButton"), copyTraceButton: $("copyTraceButton"),
  connMeta: $("connMeta"), chipCard: $("chipCard"),
  ciChip: $("ciChip"), ciFeatures: $("ciFeatures"), ciCrystal: $("ciCrystal"), ciMac: $("ciMac"), ciFlash: $("ciFlash"), ciBoot: $("ciBoot"),
  tableBody: $("tableBody"), filesMeta: $("filesMeta"), dropzone: $("dropzone"),
  addFile: $("addFile"), addHexFile: $("addHexFile"), clearFiles: $("clearFiles"),
  binFileInput: $("binFileInput"), hexFileInput: $("hexFileInput"),
  flashMode: $("flashMode"), flashFreq: $("flashFreq"), flashSize: $("flashSize"), afterMode: $("afterMode"),
  compress: $("compress"), verifyMd5: $("verifyMd5"), eraseAll: $("eraseAll"),
  progressBlock: $("progressBlock"), progressText: $("progressText"), progressPct: $("progressPct"), progressFill: $("progressFill"),
  programButton: $("programButton"), eraseButton: $("eraseButton"),
  readAddr: $("readAddr"), readSize: $("readSize"), readFullButton: $("readFullButton"), readButton: $("readButton"),
  consoleBaudrates: $("consoleBaudrates"), reconnectDelay: $("reconnectDelay"), maxRetries: $("maxRetries"),
  colorize: $("colorize"), timestamps: $("timestamps"),
  consoleStartButton: $("consoleStartButton"), consoleStopButton: $("consoleStopButton"), resetButton: $("resetButton"),
  consoleMeta: $("consoleMeta"), sendInput: $("sendInput"), lineEnding: $("lineEnding"), sendButton: $("sendButton"),
  saveLogButton: $("saveLogButton"), clearTermButton: $("clearTermButton"), toasts: $("toasts"),
};

el.appVersion.textContent = "v" + APP_VERSION;
el.footerInfo.textContent = `ESP-Flash-Tool MK1 v${APP_VERSION} · esptool-js ${ESPTOOL_VERSION} (Apache-2.0)`;

/* ------------------------------------------------------------------ */
/* Terminal                                                            */
/* ------------------------------------------------------------------ */
const term = new Terminal({
  convertEol: true,
  cursorBlink: true,
  fontFamily: '"Cascadia Mono", Consolas, "JetBrains Mono", monospace',
  fontSize: 13,
  scrollback: 20000,
  theme: {
    background: "#06080a",
    foreground: "#d7dde3",
    cursor: "#f5a524",
    cursorAccent: "#06080a",
    selectionBackground: "rgba(245,165,36,0.30)",
    black: "#0a0d10", red: "#f0524f", green: "#3ddc84", yellow: "#f5a524",
    blue: "#5aa9ff", magenta: "#c792ea", cyan: "#2dd4bf", white: "#d7dde3",
    brightBlack: "#56626d", brightRed: "#ff7a77", brightGreen: "#6cf0a8", brightYellow: "#ffcf6e",
    brightBlue: "#8cc4ff", brightMagenta: "#e0b3ff", brightCyan: "#7cf0e0", brightWhite: "#ffffff",
  },
});
const fitAddon = new FitAddon();
term.loadAddon(fitAddon);
term.open($("terminal"));
const refit = () => { try { fitAddon.fit(); } catch { /* ignorieren */ } };
new ResizeObserver(refit).observe($("terminal"));
setTimeout(refit, 50);

const ANSI = { RED: "\x1b[1;31m", GREEN: "\x1b[0;32m", YELLOW: "\x1b[0;33m", CYAN: "\x1b[0;36m", AMBER: "\x1b[38;2;245;165;36m", DIM: "\x1b[2m", NORMAL: "\x1b[0m" };
const sys = (msg, color = ANSI.AMBER) => term.writeln(`${color}» ${msg}${ANSI.NORMAL}`);

term.writeln(`${ANSI.AMBER}ESP-FLASH-TOOL MK1${ANSI.NORMAL} v${APP_VERSION}  ${ANSI.DIM}(esptool-js ${ESPTOOL_VERSION}, offline)${ANSI.NORMAL}`);
term.writeln(`${ANSI.DIM}Board per USB anschließen und „Verbinden“ (Programmieren) oder „Start“ (Konsole) wählen.${ANSI.NORMAL}`);
term.writeln("");

const espLoaderTerminal = {
  clean() { term.clear(); },
  writeLine(data) { term.writeln(data); },
  write(data) { term.write(data); },
};

/* ------------------------------------------------------------------ */
/* Meldungen / Status                                                  */
/* ------------------------------------------------------------------ */
function toast(msg, type = "ok", ms = 4500) {
  const t = document.createElement("div");
  t.className = "toast " + (type === "ok" ? "" : type);
  t.textContent = msg;
  el.toasts.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

function setStatus(text, kind = "") {
  el.statusText.textContent = text;
  el.statusPill.className = "pill " + kind;
}

/* ------------------------------------------------------------------ */
/* Web Serial / WebUSB                                                 */
/* ------------------------------------------------------------------ */
const serialLib = !navigator.serial && navigator.usb ? serialPolyfill : navigator.serial;
if (!navigator.serial && !navigator.usb) {
  el.browserWarn.classList.remove("hidden");
}

let device = null;
let deviceInfo = null;
let usingWebUsb = false;
let transport = null;
let esploader = null;
let chip = null;
let detectedFlashSize = null;
let mode = "idle"; // idle | program | console
let busy = false;

async function requestDevice() {
  if (el.useWebUsb.checked) {
    if (!navigator.usb) throw new Error("WebUSB wird von diesem Browser nicht unterstützt.");
    usingWebUsb = true;
    const port = await WebUSBSerialPort.requestPort();
    return port.asSerialPort();
  }
  if (!serialLib) throw new Error("Web Serial wird von diesem Browser nicht unterstützt (Edge oder Chrome verwenden).");
  usingWebUsb = false;
  return serialLib.requestPort({});
}

function describePort(info) {
  if (!info || info.usbVendorId === undefined) return "Serieller Port";
  const vid = info.usbVendorId.toString(16).padStart(4, "0").toUpperCase();
  const pid = info.usbProductId.toString(16).padStart(4, "0").toUpperCase();
  const known = {
    "10C4": "CP210x", "1A86": "CH34x", "0403": "FTDI", "303A": "Espressif USB", "067B": "PL2303",
  };
  return `${known[vid] || "USB"} ${vid}:${pid}`;
}

function cleanUp() {
  device = null;
  deviceInfo = null;
  usingWebUsb = false;
  transport = null;
  esploader = null;
  chip = null;
  detectedFlashSize = null;
}

if (navigator.serial) {
  navigator.serial.addEventListener("disconnect", (ev) => {
    if (mode === "program" && device && ev.target === device) {
      sys("Gerät wurde getrennt (USB abgezogen).", ANSI.RED);
      toast("Gerät wurde getrennt.", "err");
      cleanUp();
      mode = "idle";
      updateUi();
    }
  });
}

/* ------------------------------------------------------------------ */
/* UI-Zustand                                                          */
/* ------------------------------------------------------------------ */
function showTab(name) {
  el.tabProgram.classList.toggle("active", name === "program");
  el.tabConsole.classList.toggle("active", name === "console");
  el.pageProgram.classList.toggle("hidden", name !== "program");
  el.pageConsole.classList.toggle("hidden", name !== "console");
}
el.tabProgram.onclick = () => showTab("program");
el.tabConsole.onclick = () => showTab("console");

function updateUi() {
  const connected = mode === "program" && !!esploader;
  const consoleOn = mode === "console";

  // Tabs sperren, solange der jeweils andere Modus aktiv ist
  el.tabConsole.disabled = connected;
  el.tabProgram.disabled = consoleOn;

  // Verbindung
  el.connectButton.classList.toggle("hidden", connected);
  el.disconnectButton.classList.toggle("hidden", !connected);
  el.copyTraceButton.classList.toggle("hidden", !transport || consoleOn);
  el.chipCard.classList.toggle("hidden", !connected);
  el.connectButton.disabled = busy;
  el.disconnectButton.disabled = busy;
  for (const x of [el.baudrates, el.beforeMode, el.debugLogging, el.useWebUsb]) x.disabled = connected || busy || consoleOn;
  el.connMeta.textContent = connected ? (chip || "verbunden") : "nicht verbunden";

  // Flash
  el.programButton.disabled = !connected || busy || files.length === 0;
  el.eraseButton.disabled = !connected || busy;
  el.readButton.disabled = !connected || busy;
  el.readFullButton.disabled = !connected || busy || !detectedFlashSize;
  for (const x of [el.addFile, el.addHexFile, el.clearFiles, el.flashMode, el.flashFreq, el.flashSize, el.afterMode, el.compress, el.verifyMd5, el.eraseAll]) x.disabled = busy;
  el.tableBody.querySelectorAll("input,button").forEach((x) => { x.disabled = busy || x.dataset.ro === "1"; });

  // Konsole
  el.consoleStartButton.classList.toggle("hidden", consoleOn);
  el.consoleStopButton.classList.toggle("hidden", !consoleOn);
  el.resetButton.classList.toggle("hidden", !consoleOn);
  el.consoleStartButton.disabled = busy;
  el.consoleBaudrates.disabled = consoleOn;
  el.sendInput.disabled = !consoleOn;
  el.sendButton.disabled = !consoleOn;
  el.consoleMeta.textContent = consoleOn ? `läuft · ${el.consoleBaudrates.value} Baud` : "gestoppt";

  // Kopfzeile
  if (busy) setStatus("AKTIV", "busy");
  else if (connected) setStatus("VERBUNDEN", "ok");
  else if (consoleOn) setStatus("KONSOLE", "ok");
  else setStatus("GETRENNT", "");
  el.topMode.textContent = busy ? "ARBEITET" : connected ? "PROGRAMMIEREN" : consoleOn ? "KONSOLE" : "BEREIT";
  el.topDevice.textContent = connected ? chip : consoleOn ? describePort(deviceInfo) : "—";
}

/* ------------------------------------------------------------------ */
/* Dateien                                                             */
/* ------------------------------------------------------------------ */
let files = []; // {id, name, kind: 'bin'|'hex', data, address(string), role}
let nextId = 1;

const fmtHex = (n) => "0x" + n.toString(16);
function fmtSize(n) {
  if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(2) + " MB";
  if (n >= 1024) return (n / 1024).toFixed(1) + " KB";
  return n + " B";
}
function parseAddr(s) {
  const t = String(s).trim().toLowerCase();
  if (!/^(0x[0-9a-f]+|\d+)$/.test(t)) return NaN;
  return t.startsWith("0x") ? parseInt(t, 16) : parseInt(t, 10);
}

function bootloaderOffset() {
  if (esploader && esploader.chip && typeof esploader.chip.BOOTLOADER_FLASH_OFFSET === "number") {
    return esploader.chip.BOOTLOADER_FLASH_OFFSET;
  }
  return 0x1000;
}

function guessRole(name) {
  const n = name.toLowerCase();
  if (/merged|factory|combined|full[_-]?flash|_full\b/.test(n)) return "merged";
  if (/bootloader/.test(n)) return "bootloader";
  if (/partition/.test(n)) return "partitions";
  if (/boot_app0/.test(n)) return "boot_app0";
  if (/ota_data/.test(n)) return "otadata";
  return "app";
}
function addrForRole(role) {
  switch (role) {
    case "merged": return 0x0;
    case "bootloader": return bootloaderOffset();
    case "partitions": return 0x8000;
    case "boot_app0": return 0xe000;
    case "otadata": return 0xd000;
    default: return 0x10000;
  }
}

function renderFiles() {
  el.tableBody.innerHTML = "";
  if (files.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty";
    tr.innerHTML = `<td colspan="4">Noch keine Dateien – .bin oder .hex hinzufügen</td>`;
    el.tableBody.appendChild(tr);
  }
  for (const f of files) {
    const tr = document.createElement("tr");
    tr.dataset.id = f.id;

    const tdA = document.createElement("td");
    const inp = document.createElement("input");
    inp.type = "text";
    inp.value = f.address;
    inp.spellcheck = false;
    if (f.kind === "hex") { inp.readOnly = true; inp.dataset.ro = "1"; inp.title = "Adresse stammt aus der HEX-Datei"; }
    inp.oninput = () => {
      f.address = inp.value;
      f.role = "manual";
      inp.classList.toggle("bad", Number.isNaN(parseAddr(inp.value)));
    };
    tdA.appendChild(inp);

    const tdN = document.createElement("td");
    tdN.innerHTML = `<div class="fname" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}${f.kind === "hex" ? '<span class="tag-hex">HEX</span>' : ""}</div><div class="row-bar"><div></div></div>`;
    f.bar = tdN.querySelector(".row-bar");

    const tdS = document.createElement("td");
    tdS.className = "fsize";
    tdS.textContent = fmtSize(f.data.length);

    const tdX = document.createElement("td");
    const rm = document.createElement("button");
    rm.className = "icon-btn";
    rm.textContent = "✕";
    rm.title = "Entfernen";
    rm.onclick = () => { files = files.filter((x) => x !== f); renderFiles(); };
    tdX.appendChild(rm);

    tr.append(tdA, tdN, tdS, tdX);
    el.tableBody.appendChild(tr);
  }
  const total = files.reduce((s, f) => s + f.data.length, 0);
  el.filesMeta.textContent = `${files.length} ${files.length === 1 ? "Datei" : "Dateien"}${files.length ? " · " + fmtSize(total) : ""}`;
  saveOffsets();
  updateUi();
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Zuletzt verwendete Adressen je Dateiname merken
function loadOffsetMemory() {
  try { return JSON.parse(localStorage.getItem("espflash.offsets") || "{}"); } catch { return {}; }
}
function saveOffsets() {
  try {
    const mem = loadOffsetMemory();
    for (const f of files) if (f.kind === "bin" && f.role === "manual" && !Number.isNaN(parseAddr(f.address))) mem[f.name] = f.address;
    localStorage.setItem("espflash.offsets", JSON.stringify(mem));
  } catch { /* ignorieren */ }
}

async function addBinFile(file) {
  const data = new Uint8Array(await file.arrayBuffer());
  if (data.length === 0) { toast(`${file.name} ist leer.`, "warn"); return; }
  const remembered = loadOffsetMemory()[file.name];
  const role = remembered ? "manual" : guessRole(file.name);
  const address = remembered || fmtHex(addrForRole(role));
  // gleiche Datei erneut hinzugefügt → ersetzen
  const existing = files.find((f) => f.kind === "bin" && f.name === file.name);
  if (existing) { existing.data = data; toast(`${file.name} aktualisiert.`); return; }
  files.push({ id: nextId++, name: file.name, kind: "bin", data, address, role });
}

async function addHexFile(file) {
  const raw = new Uint8Array(await file.arrayBuffer());
  const segments = parseIntelHex(raw);
  if (!segments.length) throw new Error("Die Intel-HEX-Datei enthält keine Daten.");
  for (const seg of segments) {
    files.push({ id: nextId++, name: `${file.name} @${fmtHex(seg.address)}`, kind: "hex", data: seg.data, address: fmtHex(seg.address), role: "hex" });
  }
  if (el.eraseAll.checked) el.eraseAll.checked = false;
}

async function addFiles(list) {
  for (const file of list) {
    const n = file.name.toLowerCase();
    try {
      if (n.endsWith(".hex")) await addHexFile(file);
      else if (n.endsWith(".bin")) await addBinFile(file);
      else toast(`${file.name}: nur .bin- und .hex-Dateien werden unterstützt.`, "warn");
    } catch (e) {
      toast(`${file.name}: ${e.message || e}`, "err");
    }
  }
  sortFiles();
  renderFiles();
}

function sortFiles() {
  files.sort((a, b) => (parseAddr(a.address) || 0) - (parseAddr(b.address) || 0));
}

el.addFile.onclick = () => el.binFileInput.click();
el.addHexFile.onclick = () => el.hexFileInput.click();
el.clearFiles.onclick = () => { files = []; renderFiles(); };
el.binFileInput.onchange = async () => { await addFiles([...el.binFileInput.files]); el.binFileInput.value = ""; };
el.hexFileInput.onchange = async () => { await addFiles([...el.hexFileInput.files]); el.hexFileInput.value = ""; };

// Drag & Drop – auf die Dropzone und auf das ganze Fenster
let dragDepth = 0;
window.addEventListener("dragenter", (e) => { e.preventDefault(); dragDepth++; el.dropzone.classList.add("over"); });
window.addEventListener("dragleave", (e) => { e.preventDefault(); if (--dragDepth <= 0) { dragDepth = 0; el.dropzone.classList.remove("over"); } });
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", async (e) => {
  e.preventDefault();
  dragDepth = 0;
  el.dropzone.classList.remove("over");
  if (busy) { toast("Bitte warten, bis der laufende Vorgang beendet ist.", "warn"); return; }
  const list = [...(e.dataTransfer?.files || [])];
  if (list.length) { showTab(mode === "console" ? "console" : "program"); await addFiles(list); }
});

/* ------------------------------------------------------------------ */
/* Fortschritt                                                         */
/* ------------------------------------------------------------------ */
function progress(text, pct, variant = "") {
  el.progressBlock.classList.remove("hidden");
  el.progressText.textContent = text;
  el.progressPct.textContent = Math.floor(pct) + " %";
  el.progressFill.style.width = Math.min(100, pct) + "%";
  el.progressFill.className = "bar-fill " + variant;
}

/* ------------------------------------------------------------------ */
/* Programmieren: Verbinden / Trennen                                  */
/* ------------------------------------------------------------------ */
function populateFlashDropdowns() {
  if (!esploader || !esploader.chip) return;
  const freqOrder = ["80m", "60m", "48m", "40m", "30m", "26m", "24m", "20m", "16m", "15m", "12m"];
  const sizeOrder = ["256KB", "512KB", "1MB", "2MB", "2MB-c1", "4MB", "4MB-c1", "8MB", "16MB", "32MB", "64MB", "128MB"];
  const sorter = (order) => (a, b) => {
    const ia = order.indexOf(a), ib = order.indexOf(b);
    if (ia !== -1 && ib !== -1) return ia - ib;
    if (ia !== -1) return -1;
    if (ib !== -1) return 1;
    return a.localeCompare(b);
  };
  el.flashFreq.innerHTML = '<option value="keep">keep</option>';
  for (const f of Object.keys(esploader.chip.FLASH_FREQUENCY || {}).sort(sorter(freqOrder))) {
    el.flashFreq.add(new Option(f, f));
  }
  el.flashSize.innerHTML = '<option value="detect">detect</option><option value="keep" selected>keep</option>';
  for (const s of Object.keys(esploader.chip.FLASH_SIZES || {}).sort(sorter(sizeOrder))) {
    el.flashSize.add(new Option(s, s));
  }
  el.flashSize.value = "keep";
}

async function fillChipCard() {
  el.ciChip.textContent = chip || "—";
  el.ciBoot.textContent = fmtHex(bootloaderOffset());
  const c = esploader.chip;
  const safe = async (fn) => { try { return await fn(); } catch { return null; } };
  if (!esploader.secureDownloadMode) {
    const feats = await safe(() => c.getChipFeatures(esploader));
    const xtal = await safe(() => c.getCrystalFreq(esploader));
    const mac = await safe(() => c.readMac(esploader));
    el.ciFeatures.textContent = feats ? feats.join(", ") : "—";
    el.ciCrystal.textContent = xtal ? xtal + " MHz" : "—";
    el.ciMac.textContent = mac || "—";
    detectedFlashSize = await safe(() => esploader.detectFlashSize());
  } else {
    el.ciFeatures.textContent = "Secure Download Mode";
    el.ciCrystal.textContent = "—";
    el.ciMac.textContent = "—";
  }
  el.ciFlash.textContent = detectedFlashSize || "unbekannt";
  if (detectedFlashSize) {
    const bytes = esploader.flashSizeBytes(detectedFlashSize);
    if (bytes > 0) el.readSize.value = fmtHex(bytes);
  }
}

el.connectButton.onclick = async () => {
  if (busy) return;
  busy = true;
  updateUi();
  try {
    if (device === null) {
      device = await requestDevice();
      deviceInfo = device.getInfo();
      transport = new Transport(device, true);
    }
    sys(`Verbinde mit ${describePort(deviceInfo)} …`);
    esploader = new ESPLoader({
      transport,
      baudrate: parseInt(el.baudrates.value, 10),
      terminal: espLoaderTerminal,
      debugLogging: el.debugLogging.checked,
    });
    chip = await esploader.main(el.beforeMode.value);
    mode = "program";
    populateFlashDropdowns();
    await fillChipCard();

    // automatisch vorgeschlagene Bootloader-Adressen an den Chip anpassen
    let changed = false;
    for (const f of files) {
      if (f.kind === "bin" && f.role === "bootloader") {
        const a = fmtHex(bootloaderOffset());
        if (f.address !== a) { f.address = a; changed = true; }
      }
    }
    if (changed) { sortFiles(); toast(`Bootloader-Adresse für ${esploader.chip.CHIP_NAME} auf ${fmtHex(bootloaderOffset())} gesetzt.`); }
    renderFiles();
    sys(`Verbunden: ${chip}`, ANSI.CYAN);
    toast(`Verbunden mit ${chip}`);
  } catch (e) {
    console.error(e);
    const msg = e && e.message ? e.message : String(e);
    if (e && e.name === "NotFoundError") {
      sys("Kein Port ausgewählt.", ANSI.DIM);
    } else {
      term.writeln(`${ANSI.RED}Fehler: ${msg}${ANSI.NORMAL}`);
      toast("Verbindung fehlgeschlagen: " + msg, "err", 7000);
    }
    // Port wieder freigeben, damit ein neuer Versuch sauber startet
    try { if (transport && device && device.readable) await transport.disconnect(); } catch { /* ignorieren */ }
    cleanUp();
    mode = "idle";
  } finally {
    busy = false;
    updateUi();
  }
};

async function disconnectProgram(silent = false) {
  try { if (transport) await transport.disconnect(); } catch (e) { console.warn(e); }
  cleanUp();
  mode = "idle";
  el.flashFreq.innerHTML = '<option value="keep">keep</option>';
  el.flashSize.innerHTML = '<option value="detect">detect</option><option value="keep" selected>keep</option>';
  if (!silent) sys("Verbindung getrennt.");
  updateUi();
}
el.disconnectButton.onclick = () => disconnectProgram(false);

el.copyTraceButton.onclick = async () => {
  if (!transport) return;
  try {
    await transport.returnTrace();
    toast("Trace in die Zwischenablage kopiert.");
  } catch (e) {
    toast("Trace konnte nicht kopiert werden: " + (e.message || e), "err");
  }
};

/* ------------------------------------------------------------------ */
/* Programmieren / Löschen / Auslesen                                  */
/* ------------------------------------------------------------------ */
function validateFiles() {
  if (files.length === 0) return "Keine Datei ausgewählt.";
  const ranges = [];
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    const a = parseAddr(f.address);
    if (Number.isNaN(a)) return `Ungültige Adresse in Zeile ${i + 1} (${f.name}).`;
    if (ranges.some((r) => r.a === a)) return `Adresse ${fmtHex(a)} wird doppelt verwendet.`;
    ranges.push({ a, e: a + f.data.length, name: f.name });
  }
  ranges.sort((x, y) => x.a - y.a);
  for (let i = 1; i < ranges.length; i++) {
    if (ranges[i].a < ranges[i - 1].e) {
      return `${ranges[i - 1].name} (bis ${fmtHex(ranges[i - 1].e)}) überlappt mit ${ranges[i].name} @ ${fmtHex(ranges[i].a)}.`;
    }
  }
  return null;
}

el.programButton.onclick = async () => {
  if (!esploader || busy) return;
  const err = validateFiles();
  if (err) { toast(err, "err", 6000); return; }

  busy = true;
  updateUi();
  const list = [...files];
  const total = list.reduce((s, f) => s + f.data.length, 0);
  const sizes = list.map((f) => f.data.length);
  list.forEach((f) => { f.bar.classList.remove("done"); f.bar.firstElementChild.style.width = "0"; });
  progress("Starte …", 0);
  const t0 = performance.now();

  try {
    await esploader.writeFlash({
      fileArray: list.map((f) => ({ data: f.data, address: parseAddr(f.address) })),
      flashMode: el.flashMode.value,
      flashFreq: el.flashFreq.value,
      flashSize: el.flashSize.value,
      eraseAll: el.eraseAll.checked,
      compress: el.compress.checked,
      reportProgress: (idx, written, tot) => {
        const pct = tot ? (written / tot) * 100 : 100;
        const f = list[idx];
        if (f && f.bar) {
          f.bar.firstElementChild.style.width = pct + "%";
          if (pct >= 100) f.bar.classList.add("done");
        }
        const before = sizes.slice(0, idx).reduce((s, n) => s + n, 0);
        const overall = total ? ((before + (pct / 100) * sizes[idx]) / total) * 100 : 100;
        progress(`Schreibe ${f ? f.name : ""} (${idx + 1}/${list.length})`, overall);
      },
      calculateMD5Hash: el.verifyMd5.checked
        ? (image) => SparkMD5.ArrayBuffer.hash(image.buffer.slice(image.byteOffset, image.byteOffset + image.byteLength))
        : undefined,
    });
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    progress(`Fertig in ${secs} s`, 100, "done");
    sys(`Programmieren abgeschlossen (${fmtSize(total)} in ${secs} s).`, ANSI.GREEN);

    const after = el.afterMode.value;
    await esploader.after(after);
    toast(`Erfolgreich programmiert (${secs} s).`);
    if (after === "hard_reset" || after === "soft_reset") {
      sys("Chip wurde neu gestartet – Verbindung wird getrennt. Ausgabe über den Tab „Konsole“ ansehen.", ANSI.DIM);
      busy = false;
      await disconnectProgram(true);
    }
  } catch (e) {
    console.error(e);
    progress("Fehler beim Programmieren", 100);
    el.progressFill.style.background = "var(--red)";
    term.writeln(`${ANSI.RED}Fehler: ${e.message || e}${ANSI.NORMAL}`);
    toast("Programmieren fehlgeschlagen: " + (e.message || e), "err", 8000);
  } finally {
    busy = false;
    setTimeout(() => { el.progressFill.style.background = ""; }, 3000);
    updateUi();
  }
};

el.eraseButton.onclick = async () => {
  if (!esploader || busy) return;
  if (!confirmAction(`Den gesamten Flash von ${chip} wirklich löschen?`)) return;
  busy = true;
  updateUi();
  progress("Lösche Flash … (kann bis zu 2 Minuten dauern)", 100, "");
  const t0 = performance.now();
  try {
    await esploader.eraseFlash();
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    progress(`Flash gelöscht (${secs} s)`, 100, "done");
    sys(`Flash vollständig gelöscht (${secs} s).`, ANSI.GREEN);
    toast("Flash gelöscht.");
  } catch (e) {
    console.error(e);
    term.writeln(`${ANSI.RED}Fehler: ${e.message || e}${ANSI.NORMAL}`);
    toast("Löschen fehlgeschlagen: " + (e.message || e), "err", 8000);
  } finally {
    busy = false;
    updateUi();
  }
};

function confirmAction(text) {
  return window.confirm(text);
}

el.readFullButton.onclick = () => {
  if (!esploader || !detectedFlashSize) return;
  el.readAddr.value = "0x0";
  el.readSize.value = fmtHex(esploader.flashSizeBytes(detectedFlashSize));
};

el.readButton.onclick = async () => {
  if (!esploader || busy) return;
  const addr = parseAddr(el.readAddr.value);
  const size = parseAddr(el.readSize.value);
  if (Number.isNaN(addr) || Number.isNaN(size) || size <= 0) { toast("Startadresse oder Länge ungültig.", "err"); return; }

  busy = true;
  updateUi();
  const t0 = performance.now();
  progress(`Lese ${fmtSize(size)} ab ${fmtHex(addr)} …`, 0, "read");
  try {
    const data = await esploader.readFlash(addr, size, (_packet, done, tot) => {
      progress(`Lese ${fmtSize(done)} / ${fmtSize(tot)}`, tot ? (done / tot) * 100 : 0, "read");
    });
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    progress(`Ausgelesen in ${secs} s`, 100, "done");
    sys(`Flash ausgelesen: ${fmtSize(data.length)} in ${secs} s, MD5 ${SparkMD5.ArrayBuffer.hash(data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength))}`, ANSI.GREEN);
    const chipName = (esploader.chip.CHIP_NAME || "esp").toLowerCase().replace(/[^a-z0-9]+/g, "");
    await saveBlob(new Blob([data], { type: "application/octet-stream" }), `flash_${chipName}_${fmtHex(addr)}_${fmtHex(size)}.bin`, ".bin");
  } catch (e) {
    console.error(e);
    term.writeln(`${ANSI.RED}Fehler: ${e.message || e}${ANSI.NORMAL}`);
    toast("Auslesen fehlgeschlagen: " + (e.message || e), "err", 8000);
  } finally {
    busy = false;
    updateUi();
  }
};

async function saveBlob(blob, suggestedName, ext) {
  if (window.showSaveFilePicker) {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName,
        types: [{ description: ext === ".bin" ? "Binärdatei" : "Textdatei", accept: { [blob.type || "application/octet-stream"]: [ext] } }],
      });
      const w = await handle.createWritable();
      await w.write(blob);
      await w.close();
      toast(`Gespeichert: ${handle.name}`);
      return;
    } catch (e) {
      if (e && e.name === "AbortError") return;
      console.warn("showSaveFilePicker fehlgeschlagen, nutze Download", e);
    }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = suggestedName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  toast(`Download gestartet: ${suggestedName}`);
}

/* ------------------------------------------------------------------ */
/* Konsole                                                             */
/* ------------------------------------------------------------------ */
let isConsoleClosed = true;
let isReconnecting = false;
const IDF_LOG_LEVEL_REGEX = /^(I|W|E) \([\d.: -]+\)/;
let atLineStart = true;

function colorizeIdfLine(line) {
  if (!el.colorize.checked) return line;
  const m = IDF_LOG_LEVEL_REGEX.exec(line);
  if (!m) return line;
  const color = m[1] === "E" ? ANSI.RED : m[1] === "W" ? ANSI.YELLOW : ANSI.GREEN;
  return color + line + ANSI.NORMAL;
}
function stamp() {
  if (!el.timestamps.checked) return "";
  const d = new Date();
  const p = (n, l = 2) => String(n).padStart(l, "0");
  return `${ANSI.DIM}[${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}]${ANSI.NORMAL} `;
}

let flushTimer = null;
async function startConsoleReading() {
  if (isConsoleClosed || !transport) return;
  const decoder = new TextDecoder("utf-8");
  let lineBuffer = "";
  const flushPartial = () => {
    flushTimer = null;
    if (!lineBuffer.length) return;
    // unvollständige Zeile (z. B. Eingabe-Prompt) ohne Zeilenende anzeigen
    term.write((atLineStart ? stamp() : "") + lineBuffer);
    atLineStart = false;
    lineBuffer = "";
  };
  try {
    await transport.rawRead(
      (value) => {
        if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
        lineBuffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = lineBuffer.indexOf("\n")) !== -1) {
          const lineWithEol = lineBuffer.slice(0, idx + 1);
          lineBuffer = lineBuffer.slice(idx + 1);
          const stripped = lineWithEol.replace(/\r?\n$/, "");
          const eol = lineWithEol.slice(stripped.length);
          term.write((atLineStart ? stamp() + colorizeIdfLine(stripped) : stripped) + eol);
          atLineStart = true;
        }
        if (lineBuffer.length) flushTimer = setTimeout(flushPartial, 60);
      },
      () => isConsoleClosed,
    );
    if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
    if (lineBuffer.length > 0) term.write(colorizeIdfLine(lineBuffer));
  } catch (error) {
    if (!isConsoleClosed) term.writeln(`\r\n${ANSI.RED}[KONSOLE-FEHLER] ${error instanceof Error ? error.message : String(error)}${ANSI.NORMAL}`);
  }
  if (!isConsoleClosed && !isReconnecting) {
    term.writeln(`\r\n${ANSI.AMBER}[KONSOLE] Verbindung unterbrochen, warte auf Wiederverbindung …${ANSI.NORMAL}`);
  }
}

async function tryReconnect() {
  if (isConsoleClosed || isReconnecting) return;
  isReconnecting = true;
  setStatus("WIEDERVERBINDEN", "busy");
  term.writeln(`\r\n${ANSI.AMBER}[GERÄT GETRENNT] Versuche erneut zu verbinden …${ANSI.NORMAL}`);
  const delay = Math.max(100, parseInt(el.reconnectDelay.value, 10) || 1000);
  const maxRetries = Math.max(1, parseInt(el.maxRetries.value, 10) || 5);
  await sleep(delay);

  for (let attempt = 1; attempt <= maxRetries && !isConsoleClosed; attempt++) {
    term.writeln(`${ANSI.AMBER}[RECONNECT] Versuch ${attempt}/${maxRetries} …${ANSI.NORMAL}`);
    let newDevice = null;
    try {
      if (usingWebUsb && navigator.usb) {
        const usbDevices = await navigator.usb.getDevices();
        const match = usbDevices.find((u) => u.vendorId === deviceInfo.usbVendorId && u.productId === deviceInfo.usbProductId);
        if (match) newDevice = new WebUSBSerialPort(match).asSerialPort();
      } else if (serialLib && serialLib.getPorts) {
        const ports = await serialLib.getPorts();
        newDevice = ports.find((p) => p.getInfo().usbVendorId === deviceInfo.usbVendorId && p.getInfo().usbProductId === deviceInfo.usbProductId);
      }
      if (newDevice) {
        device = newDevice;
        transport.updateDevice(device);
        await transport.connect(parseInt(el.consoleBaudrates.value, 10));
        term.writeln(`${ANSI.GREEN}[RECONNECT] Erfolgreich wieder verbunden.${ANSI.NORMAL}`);
        isReconnecting = false;
        updateUi();
        startConsoleReading();
        return;
      }
    } catch (e) {
      term.writeln(`${ANSI.RED}[RECONNECT] ${e.message || e}${ANSI.NORMAL}`);
    }
    if (attempt < maxRetries) await sleep(delay);
  }
  if (!isConsoleClosed) {
    term.writeln(`${ANSI.RED}[RECONNECT] Nach ${maxRetries} Versuchen nicht wieder verbunden. Bitte Konsole stoppen und neu starten.${ANSI.NORMAL}`);
    setStatus("GETRENNT", "err");
  }
  isReconnecting = false;
}

el.consoleStartButton.onclick = async () => {
  if (busy) return;
  busy = true;
  updateUi();
  try {
    if (device === null) {
      device = await requestDevice();
      deviceInfo = device.getInfo();
      transport = new Transport(device, true);
      transport.setDeviceLostCallback(() => { tryReconnect(); });
    }
    await transport.connect(parseInt(el.consoleBaudrates.value, 10));
    isConsoleClosed = false;
    isReconnecting = false;
    atLineStart = true;
    mode = "console";
    sys(`Konsole gestartet: ${describePort(deviceInfo)} @ ${el.consoleBaudrates.value} Baud`, ANSI.CYAN);
    busy = false;
    updateUi();
    term.focus();
    startConsoleReading();
  } catch (e) {
    console.error(e);
    if (!(e && e.name === "NotFoundError")) {
      term.writeln(`${ANSI.RED}Fehler: ${e.message || e}${ANSI.NORMAL}`);
      toast("Konsole konnte nicht gestartet werden: " + (e.message || e), "err", 7000);
    } else {
      sys("Kein Port ausgewählt.", ANSI.DIM);
    }
    cleanUp();
    mode = "idle";
  } finally {
    busy = false;
    updateUi();
  }
};

el.consoleStopButton.onclick = async () => {
  isConsoleClosed = true;
  isReconnecting = false;
  if (transport) {
    try {
      await transport.disconnect();
      await transport.waitForUnlock(1500);
    } catch (e) { console.warn(e); }
  }
  sys("Konsole gestoppt.");
  cleanUp();
  mode = "idle";
  updateUi();
};

el.resetButton.onclick = async () => {
  if (!transport) return;
  try {
    // wie im Original: EN über DTR kurz ziehen; zusätzlich RTS-Variante für USB-UART-Bridges
    await transport.setDTR(false);
    await transport.setRTS(true);
    await sleep(100);
    await transport.setDTR(true);
    await transport.setRTS(false);
    await sleep(50);
    await transport.setDTR(false);
    sys("Reset ausgelöst.", ANSI.DIM);
  } catch (e) {
    toast("Reset fehlgeschlagen: " + (e.message || e), "err");
  }
};

const encoder = new TextEncoder();
async function sendRaw(text) {
  if (mode !== "console" || !device || !device.writable) return;
  const writer = device.writable.getWriter();
  try { await writer.write(encoder.encode(text)); } finally { writer.releaseLock(); }
}
const lineEndingValue = () => el.lineEnding.value.replace(/\\r/g, "\r").replace(/\\n/g, "\n");
async function sendLine() {
  const text = el.sendInput.value;
  try {
    await sendRaw(text + lineEndingValue());
    el.sendInput.value = "";
  } catch (e) {
    toast("Senden fehlgeschlagen: " + (e.message || e), "err");
  }
}
el.sendButton.onclick = sendLine;
el.sendInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); sendLine(); } });
term.onData((data) => { if (mode === "console") sendRaw(data).catch(() => {}); });

/* ------------------------------------------------------------------ */
/* Terminal-Werkzeuge                                                  */
/* ------------------------------------------------------------------ */
el.clearTermButton.onclick = () => { term.clear(); };
el.saveLogButton.onclick = async () => {
  const buf = term.buffer.active;
  const lines = [];
  for (let i = 0; i < buf.length; i++) lines.push(buf.getLine(i)?.translateToString(true) ?? "");
  while (lines.length && lines[lines.length - 1] === "") lines.pop();
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  const name = `esp-log_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}.txt`;
  await saveBlob(new Blob([lines.join("\r\n")], { type: "text/plain" }), name, ".txt");
};

/* ------------------------------------------------------------------ */
/* Einstellungen merken                                                */
/* ------------------------------------------------------------------ */
const persisted = ["baudrates", "beforeMode", "debugLogging", "consoleBaudrates", "reconnectDelay", "maxRetries", "colorize", "timestamps", "afterMode", "compress", "verifyMd5", "lineEnding"];
try {
  const saved = JSON.parse(localStorage.getItem("espflash.settings") || "{}");
  for (const k of persisted) {
    if (!(k in saved)) continue;
    if (el[k].type === "checkbox") el[k].checked = !!saved[k];
    else el[k].value = saved[k];
  }
} catch { /* ignorieren */ }
for (const k of persisted) {
  el[k].addEventListener("change", () => {
    try {
      const s = {};
      for (const kk of persisted) s[kk] = el[kk].type === "checkbox" ? el[kk].checked : el[kk].value;
      localStorage.setItem("espflash.settings", JSON.stringify(s));
    } catch { /* ignorieren */ }
  });
}

/* ------------------------------------------------------------------ */
/* Lebenszeichen an den lokalen Server (beendet ihn nach dem Schließen) */
/* ------------------------------------------------------------------ */
const clientId = Math.random().toString(36).slice(2) + Date.now().toString(36);
const ping = () => fetch(`/api/ping?id=${clientId}`, { cache: "no-store" }).catch(() => {});
ping();
setInterval(ping, 5000);
window.addEventListener("pagehide", () => {
  try { navigator.sendBeacon(`/api/bye?id=${clientId}`); } catch { /* ignorieren */ }
});
window.addEventListener("beforeunload", (e) => {
  if (busy) { e.preventDefault(); e.returnValue = ""; }
});

renderFiles();
updateUi();
