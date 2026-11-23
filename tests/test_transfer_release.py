import asyncio
import hashlib
import zipfile

import pytest
from starlette.requests import Request
from starlette.responses import Response

import server
from scripts import build_source_release as release
from scripts.verify_release import verify


def test_release_prunes_environments_runtime_secrets_and_symlinks(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    (tmp_path / "reuse.py").write_text("# source\n")
    (tmp_path / ".env").write_text("PRIVATE=local\n")
    for folder in (".venv", "runtime", "node_modules", "artifacts", "docs", "tests"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "file.py").write_text("# fixture\n")
    (tmp_path / "docs" / "outside-link").symlink_to(tmp_path / ".env")
    (tmp_path / "docs" / "runtime-link").symlink_to(tmp_path / "runtime", target_is_directory=True)
    assert [p.relative_to(tmp_path).as_posix() for p in release.selected_files()] == [
        "docs/file.py", "reuse.py", "tests/file.py"]


def test_release_blocks_known_secret_pattern(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    source = tmp_path / "bad.py"
    source.write_text("TOKEN = 'sk-" + "a" * 30 + "'\n")
    with pytest.raises(RuntimeError, match="Geheimnis"):
        release.validate([source])


def test_release_manifest_covers_every_packaged_file(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "OUTPUT_ROOT", tmp_path / "build")
    (tmp_path / "reuse.py").write_text("# portable\n")
    (tmp_path / "README.md").write_text("# Anleitung\n")
    archive_path = release.build()
    with zipfile.ZipFile(archive_path) as archive:
        manifest = archive.read("veriscout/MANIFEST.SHA256").decode()
        entries = [line.split("  ", 1) for line in manifest.splitlines()]
        assert len(entries) == 2
        assert len(archive.namelist()) == len(entries) + 1
        for digest, name in entries:
            assert hashlib.sha256(archive.read("veriscout/" + name)).hexdigest() == digest


def test_manifest_verifier_detects_modified_content(tmp_path):
    source = tmp_path / "a.py"
    source.write_bytes(b"original")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (tmp_path / "MANIFEST.SHA256").write_text(f"{digest}  a.py\n")
    assert verify(tmp_path) == 1
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="verändert"):
        verify(tmp_path)


@pytest.mark.parametrize("name", ["../outside.py", "/outside.py"])
def test_manifest_verifier_rejects_external_paths(tmp_path, name):
    (tmp_path / "MANIFEST.SHA256").write_text("a" * 64 + "  " + name + "\n")
    with pytest.raises(ValueError, match="Ungültiger"):
        verify(tmp_path)


@pytest.mark.parametrize("path,method,expected", [
    ("/api/comparison/workspace/validate", "POST", 204),
    ("/api/comparison/reuse/protocol", "GET", 204),
    ("/api/comparison/run", "POST", 401),
    ("/api/comparison/unblind", "POST", 401),
    ("/api/outreach", "POST", 404),
])
def test_transfer_routes_do_not_open_protected_actions(monkeypatch, path, method, expected):
    monkeypatch.setattr(server, "OPERATOR_TOKEN", "")
    monkeypatch.setattr(server, "LEGACY_API_ENABLED", False)
    called = []
    async def endpoint(request):
        called.append(request.url.path)
        return Response(status_code=204)
    request = Request({"type": "http", "method": method, "path": path,
                       "headers": [], "scheme": "http", "server": ("localhost", 8001),
                       "query_string": b""})
    response = asyncio.run(server._api_boundary(request, endpoint))
    assert response.status_code == expected
    assert bool(called) is (expected == 204)
