"""Tests for Conway stroke-data parsing in scripts/download_stroke_data.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from download_stroke_data import expand_sequence_regex, parse_stroke_data  # noqa: E402


class TestExpandSequenceRegex:
    def test_plain_sequence(self) -> None:
        assert expand_sequence_regex("12345") == ["12345"]

    def test_invalid_plain_returns_empty(self) -> None:
        assert expand_sequence_regex("12a45") == []

    def test_alternatives(self) -> None:
        out = expand_sequence_regex("(135|153)")
        assert sorted(out) == ["135", "153"]

    def test_prefix_with_alternatives(self) -> None:
        out = expand_sequence_regex("(1|3)12")
        assert sorted(out) == ["112", "312"]

    def test_mid_alternatives(self) -> None:
        out = expand_sequence_regex("12(5|25)1")
        assert sorted(out) == ["12251", "1251"]

    def test_backreference(self) -> None:
        out = expand_sequence_regex(r"(1534|1543)\1")
        assert sorted(out) == ["15341534", "15431543"]


class TestParseStrokeData:
    def test_parses_variants_and_rankings(self, tmp_path: Path) -> None:
        raw = tmp_path / "codepoint-character-sequence.txt"
        raw.write_text(
            "# comment\n"
            "U+4F60\t你\t3235234\n"
            "U+4E00\t一^\t1\n"
            "U+4E8C\t二\t(11|12)\n",
            encoding="utf-8",
        )
        rankings = {"你": 0.9, "一": 0.99, "二": 0.5}
        records = parse_stroke_data(raw, rankings)

        by_char: dict[str, list] = {}
        for r in records:
            by_char.setdefault(r.character, []).append(r)

        assert "你" in by_char
        assert by_char["你"][0].stroke_sequence == [3, 2, 3, 5, 2, 3, 4]
        assert by_char["你"][0].frequency == 0.9

        # Traditional marker ^ is stripped for the character key
        assert "一" in by_char
        assert by_char["一"][0].stroke_sequence == [1]

        # Alternatives expand to two records
        assert len(by_char["二"]) == 2
        seqs = sorted("".join(str(s) for s in r.stroke_sequence) for r in by_char["二"])
        assert seqs == ["11", "12"]

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        raw = tmp_path / "codepoint-character-sequence.txt"
        raw.write_text(
            "not-a-codepoint\t一\t1\n"
            "U+4E00\tabc\t1\n"
            "U+4E00\t一\t1\n",
            encoding="utf-8",
        )
        records = parse_stroke_data(raw, {"一": 1.0})
        assert len(records) == 1
        assert records[0].character == "一"


@pytest.mark.skipif(
    not (ROOT / "data" / "stroke_db.msgpack").exists(),
    reason="stroke_db.msgpack not present",
)
def test_ni_sequence_in_real_db() -> None:
    """Regression: Conway DB stores 你 as 3235234 (not the old 3235354 comment)."""
    from stroke_input.data.serializer import load_msgpack

    records = load_msgpack(ROOT / "data" / "stroke_db.msgpack")
    ni = [r for r in records if r.character == "你"]
    assert ni
    assert ni[0].stroke_sequence == [3, 2, 3, 5, 2, 3, 4]
