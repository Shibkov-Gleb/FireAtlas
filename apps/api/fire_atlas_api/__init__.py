"""Fire Atlas public API (Backend Engineer)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_contracts = REPO_ROOT / "packages" / "contracts"
if str(_contracts) not in sys.path:
    sys.path.insert(0, str(_contracts))
