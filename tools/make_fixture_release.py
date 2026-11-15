"""Собирает фикстурный пакет CT-09 из packages/contracts/fixtures_entities.json.

    python3 tools/make_fixture_release.py [out_dir] [assets_dir]

* Ревизия переименовывается в fixture-20261115-r1, чтобы никогда не совпасть с реальным выпуском AI 1.
* Для FLEX создается локальный asset (CSV с пятью контрольными строками приложения А) с настоящим sha256.
* Это НЕ научный корпус: он не проходит профиль p0 и нужен только для разработки и тестов бэкенда/FE.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from fire_atlas_api.importer import write_release  # noqa: E402

FIXTURE_REV = "fixture-20261115-r1"
FLEX_CSV = (
    "Test ID,Initial diameter (mm),Burn time (s),Pressure (mmHg),Outcome\n"
    "20CAL08,1.69,4.3,757.7,Disruption\n"
    "20CAL10,1.86,5.0,762,Extinction\n"
    "20CAL12,1.61,3.2,764.2,Extinction\n"
    "30CAL02,2.06,7.64,760,Extinction\n"
    "30CAL03,1.92,6.34,760,Extinction\n"
)


def build(out_dir: Path, assets_dir: Path) -> Path:
    fx = json.loads((ROOT / "packages" / "contracts" / "fixtures_entities.json").read_text(encoding="utf-8"))
    src_rev = fx["data_revision"]
    raw = json.dumps(fx, ensure_ascii=False).replace(f'"{src_rev}"', f'"{FIXTURE_REV}"')
    fx = json.loads(raw)

    assets_dir.mkdir(parents=True, exist_ok=True)
    asset = assets_dir / "asset_psi69_exptable_v5.csv"
    asset.write_text(FLEX_CSV, encoding="utf-8")
    fx["sources"]["src_psi69_exptable"]["sha256"] = hashlib.sha256(asset.read_bytes()).hexdigest()

    entities = {
        "investigation": list(fx["investigations"].values()),
        "material": list(fx["materials"].values()),
        "run": list(fx["runs"].values()),
        "source": list(fx["sources"].values()),
        "evidence": list(fx["evidence"].values()),
        "claim": list(fx["claims"].values()),
    }
    return write_release(out_dir, FIXTURE_REV, entities, producer="backend-fixtures (fixture=true, not a corpus)",
                         created_at="2026-11-15T08:30:00Z")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests" / "fixtures" / "data_release_fixture"
    assets = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "var" / "assets"
    print(build(out, assets))
