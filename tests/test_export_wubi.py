"""Export regression: 五筆劃 (頭四尾一) index for Chrome."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stroke_input.data.models import CharacterRecord
from stroke_input.data.serializer import load_msgpack, save_msgpack

ROOT = Path(__file__).resolve().parent.parent


def test_毓_wubi_code_in_live_export() -> None:
    """Acceptance: 毓 full sequence collapses to 31555 in strokes_wubi.json."""
    wubi_path = ROOT / "chrome-extension" / "data" / "strokes_wubi.json"
    if not wubi_path.exists():
        pytest.skip("strokes_wubi.json not exported yet")
    rows = json.loads(wubi_path.read_text(encoding="utf-8"))
    matches = [r for r in rows if r[1] == "毓" and r[0] == "31555"]
    assert matches, "expected 毓 → 31555 in strokes_wubi.json"


def test_export_strokes_writes_wubi_for_gt5_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.export_for_chrome as export_mod

    short = CharacterRecord(character="一", stroke_sequence=[1], frequency=0.9)
    long = CharacterRecord(
        character="毓",
        stroke_sequence=[3, 1, 5, 5, 4, 1, 4, 1, 5, 4, 3, 2, 5],
        frequency=0.4,
    )
    db = tmp_path / "stroke_db.msgpack"
    save_msgpack([short, long], db)

    out = tmp_path / "chrome-out"
    out.mkdir()
    monkeypatch.setattr(export_mod, "OUT_DIR", out)
    monkeypatch.setattr(export_mod, "_ROOT", tmp_path)
    # Point load_msgpack path used inside export_strokes
    real_load = export_mod.load_msgpack

    def _load(path: Path):
        if path.name == "stroke_db.msgpack":
            return real_load(db)
        return real_load(path)

    monkeypatch.setattr(export_mod, "load_msgpack", _load)
    export_mod.export_strokes()

    strokes = json.loads((out / "strokes.json").read_text(encoding="utf-8"))
    wubi = json.loads((out / "strokes_wubi.json").read_text(encoding="utf-8"))
    assert any(r[1] == "一" for r in strokes)
    assert not any(r[1] == "一" for r in wubi), "≤5 strokes must not appear in wubi index"
    assert any(r[0] == "31555" and r[1] == "毓" for r in wubi)
