"""BE-01: примеры валидны, контракт непротиворечив."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "tools"))

import check_examples  # noqa: E402


def test_examples_validate_against_openapi():
    assert check_examples.main() == 0
