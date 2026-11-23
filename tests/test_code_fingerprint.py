"""Der Code-Fingerabdruck des Plans muss jedes Modul des Studienpfads abdecken.

Statische Import-Verfolgung (auch Importe innerhalb von Funktionen, z. B. die
Nachrecherche in compare_architectures) ab dem Studienlauf und dem
Bewertungsbogen. Neue Module ohne Eintrag in CODE_FILES lassen den Test scheitern.
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_study  # noqa: E402

STARTS = ("scripts/run_study.py", "rating_panel.py")


def _local(name: str):
    top = name.split(".")[0]
    for candidate in (ROOT / f"{top}.py", ROOT / "scripts" / f"{top}.py"):
        if candidate.is_file():
            return candidate
    return None


def study_path_modules() -> set[str]:
    seen, todo = set(), [ROOT / s for s in STARTS]
    while todo:
        path = todo.pop()
        rel = path.relative_to(ROOT).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                found = _local(name)
                if found is not None:
                    todo.append(found)
    return seen


def test_every_study_module_is_in_code_fingerprint():
    modules = study_path_modules()
    assert {"follow_up.py", "compare_architectures.py", "rating_panel.py"} <= modules
    missing = sorted(m for m in modules if m not in run_study.CODE_FILES)
    assert not missing, f"In CODE_FILES fehlen: {missing}"


def test_fingerprint_changes_when_follow_up_changes(monkeypatch):
    before = run_study.code_fingerprint()
    original = pathlib.Path.read_bytes

    def patched(self):
        data = original(self)
        return data + b"#x" if self.name == "follow_up.py" else data

    monkeypatch.setattr(pathlib.Path, "read_bytes", patched)
    assert run_study.code_fingerprint() != before
