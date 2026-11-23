"""Erzeugt ein manifestgebundenes VeriScout-Quellpaket ohne lokale Altstände."""
from __future__ import annotations

import datetime
import hashlib
import os
import re
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT.parent / "releases"
INCLUDE_DIRECTORIES = {
    ".github", "config", "data", "docs", "scripts", "static", "templates",
    "tests", "studie",
}
# Aus "studie/" nur Vorlagen und Auswahlregel: Aufgabenliste, Fallblaetter,
# Plan und Kostenbuch koennen Namen von Partnerunternehmen enthalten.
STUDY_PUBLIC_FILES = {"aufgaben_vorlage.csv", "fallblaetter_vorlage.json",
                      "AUSWAHLREGEL.md"}
INCLUDE_ROOT_FILES = {
    ".dockerignore", ".env.example", ".gitignore", ".releaseignore",
    "Dockerfile", "README.md", "SECURITY.md", "pyproject.toml",
    "requirements.txt", "requirements-dev.txt",
}
EXCLUDED_PARTS = {
    "__pycache__", ".pytest_cache", "runtime", "artifacts", "reports",
    ".venv", "venv", "node_modules", ".git",
}
SENSITIVE_PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"(?m)^(?!#)[A-Z][A-Z0-9_]*API_KEY\s*=\s*[^\s#]{16,}"),
    re.compile(rb"PIPEDRIVE_API_TOKEN\s*=\s*[A-Za-z0-9]{32,}"),
)


def selected_files() -> list[Path]:
    files: list[Path] = []
    for directory, children, names in os.walk(ROOT, followlinks=False):
        children[:] = [name for name in children if name not in EXCLUDED_PARTS
                       and not (Path(directory) / name).is_symlink()
                       and (Path(directory) != ROOT or name in INCLUDE_DIRECTORIES)]
        for name in names:
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if len(relative.parts) == 1:
                if path.name in INCLUDE_ROOT_FILES or path.suffix == ".py":
                    files.append(path)
            elif relative.parts[0] == "studie":
                if path.name in STUDY_PUBLIC_FILES:
                    files.append(path)
            elif relative.parts[0] in INCLUDE_DIRECTORIES:
                files.append(path)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def validate(files: list[Path]) -> None:
    forbidden_names = {".env", "audit_log.jsonl", "memory_store.json",
                       "vorqualifiziert.db", ".DS_Store"}
    for path in files:
        if path.name in forbidden_names:
            raise RuntimeError(f"Nicht freigabefaehige Datei: {path.name}")
        data = path.read_bytes()
        if any(pattern.search(data) for pattern in SENSITIVE_PATTERNS):
            raise RuntimeError(
                "Moegliches Geheimnis in " + path.relative_to(ROOT).as_posix())


def build() -> Path:
    files = selected_files()
    validate(files)
    manifest_lines = []
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_lines.append(f"{digest}  {relative}")
    manifest = "\n".join(manifest_lines) + "\n"
    release_hash = hashlib.sha256(manifest.encode("utf-8")).hexdigest()[:16]
    OUTPUT_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    date = datetime.date.today().isoformat()
    destination = OUTPUT_ROOT / f"veriscout-source-{date}-{release_hash}.zip"
    with zipfile.ZipFile(
            destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, f"veriscout/{path.relative_to(ROOT).as_posix()}")
        archive.writestr("veriscout/MANIFEST.SHA256", manifest)
    return destination


if __name__ == "__main__":
    print(build())
