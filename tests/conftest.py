"""Testlaeufe schreiben keine Laufdateien in artifacts/runs."""
import os
import tempfile

os.environ.setdefault("SCOUTREF_RUNS_DIR", tempfile.mkdtemp(prefix="veriscout-runs-"))
