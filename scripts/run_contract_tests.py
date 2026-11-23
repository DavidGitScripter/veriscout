#!/usr/bin/env python3
"""Run the complete offline contract suite through pytest.

An earlier fallback called every ``test_*`` function directly.  That silently
stopped being complete once tests used fixtures and ``pytest.raises``.  A
scientific test count must not depend on which runner happened to be used, so
this entry point now delegates to the same pytest collection as CI.
"""
from __future__ import annotations

import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
def main() -> int:
    sys.path.insert(0, str(ROOT))
    try:
        import pytest
    except ImportError:
        print(
            "pytest fehlt. Zuerst die festgeschriebenen Entwicklungs-"
            "abhaengigkeiten aus requirements-dev.txt installieren.",
            file=sys.stderr,
        )
        return 2
    return int(pytest.main([str(ROOT / "tests"), "-q"]))


if __name__ == "__main__":
    raise SystemExit(main())
