"""Erzeugt die Windows-Versionsinfo (Dateieigenschaften der exe) für PyInstaller."""

import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
init = (root / "espflash" / "__init__.py").read_text(encoding="utf-8")
version = re.search(r'APP_VERSION = "([^"]+)"', init).group(1)
parts = [int(x) for x in re.findall(r"\d+", version)][:3] + [0]
while len(parts) < 4:
    parts.insert(-1, 0)
t = tuple(parts[:4])

text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704b0', [
      StringStruct('FileDescription', 'ESP-Flash-Tool MK1 – Offline-Flasher für Espressif-Chips'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'ESP-Flash-Tool-MK1'),
      StringStruct('OriginalFilename', 'ESP-Flash-Tool-MK1.exe'),
      StringStruct('ProductName', 'ESP-Flash-Tool MK1'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
"""
out = Path(sys.argv[1] if len(sys.argv) > 1 else "version_info.txt")
out.write_text(text, encoding="utf-8")
print(f"Versionsinfo {version} -> {out}")
