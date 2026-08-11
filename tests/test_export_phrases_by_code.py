"""Export regression: G6 phrase-by-code index for Chrome (T2.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_香港_g6_code_in_live_export() -> None:
    """Acceptance: 香港 → 312441 (丿一丨 + 丶丶一)."""
    path = ROOT / "chrome-extension" / "data" / "phrases_by_code.json"
    if not path.exists():
        pytest.skip("phrases_by_code.json not exported yet")
    rows = json.loads(path.read_text(encoding="utf-8"))
    matches = [r for r in rows if r[1] == "香港" and r[0] == "312441"]
    assert matches, "expected 香港 → 312441 in phrases_by_code.json"


def test_export_phrases_by_code_builds_head3_tail3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.export_for_chrome as export_mod

    out = tmp_path / "chrome-out"
    out.mkdir()
    (out / "strokes.json").write_text(
        json.dumps(
            [
                ["312342511", "香", 0.8],
                ["441122134515", "港", 0.7],
                ["1", "一", 0.9],
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (out / "phrases.json").write_text(
        json.dumps({"香": [["香港", 1.0], ["香一", 0.2]]}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(export_mod, "OUT_DIR", out)
    export_mod.export_phrases_by_code()

    rows = json.loads((out / "phrases_by_code.json").read_text(encoding="utf-8"))
    assert ["312441", "香港", 1.0] in rows
    # 香一 → head3(香)+head3(一) = 312 + 1 = 3121
    assert any(r[1] == "香一" and r[0] == "3121" for r in rows)
