"""Start Marc's local transfer review. No provider calls or external writes."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def transfer_environment(root: Path) -> dict[str, str]:
    runtime = root / "runtime" / "transfer_review"
    return {"OPENAI_API_KEY": "", "PIPEDRIVE_API_TOKEN": "", "PIPEDRIVE_LIVE": "0",
            "SCOUTREF_EVAL_LIVE_ENABLED": "0", "SCOUTREF_ENABLE_LEGACY_API": "0",
            "SCOUTREF_OPERATOR_TOKEN": "", "SCOUTREF_LOCAL_REVIEW_MODE": "0",
            "SCOUTREF_TRANSFER_REVIEW_MODE": "1",
            "SCOUTREF_RUNTIME_ROOT": str(runtime), "DATABASE_URL": "",
            "SCOUTREF_SQLITE_PATH": str(runtime / "transfer.db"),
            "SCOUTREF_STUDY_BUDGET_LEDGER": str(runtime / "unused_budget.json"),
            "SCOUTREF_UNBLINDING_STORE": str(runtime / "unused_unblinding.json"),
            "SCOUTREF_HOLDOUT_MANIFEST": "",
            "SCOUTREF_HOLDOUT_EXECUTIONS": str(runtime / "unused_holdout.json")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    os.environ.update(transfer_environment(ROOT))
    sys.path.insert(0, str(ROOT))
    import uvicorn
    print(f"Kostenfreie Transferprüfung: http://127.0.0.1:{args.port}", flush=True)
    print("Live-Suche, CRM und Outlook sind in diesem Startprofil gesperrt.", flush=True)
    uvicorn.run("server:app", host="127.0.0.1", port=args.port, reload=False)


if __name__ == "__main__":
    main()
