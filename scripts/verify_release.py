"""Check a source package against its included manifest, without network access.

This detects accidental changes. The manifest is not a digital signature and
does not authenticate the person supplying the package.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re


def verify(root: Path) -> int:
    root = root.resolve()
    manifest = root / "MANIFEST.SHA256"
    if not manifest.is_file():
        raise ValueError("Kein Paketmanifest vorhanden. Bitte das Quellpaket entpacken.")
    checked = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if "  " not in line:
            raise ValueError("Ungültige Manifestzeile.")
        digest, name = line.split("  ", 1)
        relative = Path(name)
        if (not re.fullmatch(r"[a-f0-9]{64}", digest) or not name
                or relative.is_absolute() or ".." in relative.parts
                or name in checked):
            raise ValueError("Ungültiger oder doppelter Manifesteintrag.")
        path = root / relative
        if (path.is_symlink() or not path.resolve().is_relative_to(root)
                or not path.is_file()):
            raise ValueError(f"Paketdatei fehlt oder ist nicht zulässig: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Paketdatei wurde verändert: {name}")
        checked.add(name)
    if not checked:
        raise ValueError("Leeres Manifest.")
    return len(checked)


if __name__ == "__main__":
    try:
        count = verify(Path(__file__).resolve().parents[1])
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(f"{count} Paketdateien entsprechen dem beiliegenden Manifest.")
    print("Keine digitale Signatur. Zusätzliche lokale Dateien werden nicht bewertet.")
