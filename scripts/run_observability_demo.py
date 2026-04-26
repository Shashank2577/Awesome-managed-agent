from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.observability_service import run_demo


if __name__ == "__main__":
    report = run_demo("test command: evaluate observability stack and handoffs")
    print(json.dumps(report, indent=2))
