"""Tests for the phrase dictionary loader."""

from pathlib import Path
from textwrap import dedent

import pytest

from stroke_input.data.models import PhraseEntry
from stroke_input.data.phrase_loader import PhraseDict, load_phrase_dict


# ---------------------------------------------------------------------------
# TSV loading
# ---------------------------------------------------------------------------


class TestLoadTSV:
    """Test loading phrase dictionaries from TSV files."""

    def test_basic_tsv_loading(self, tmp_path: Path) -> None:
        tsv = tmp_path / "phrases.tsv"
        tsv.write_text("你好\t0.9\n中文\t0.7\n電腦\t0.5\n", encoding="utf-8")

        pd = load_phrase_dict(tsv)
        assert pd.total == 3

    def test_lookup_returns_matching_phrases(self, tmp_path: Path) -> None:
        tsv = tmp_path / "phrases.tsv"
        tsv.write_text("你好\t0.9\n你們\t0.8\n中文\t0.7\n", encoding="utf-8")

        pd = load_phrase_dict(tsv)
        results = pd.lookup("你")
        assert len(results) == 2
        assert results[0].phrase == "你好"
        assert results[1].phrase == "你們"

    def test_lookup_sorted_by_frequency(self, tmp_path: Path) -> None:
        tsv = tmp_path / "phrases.tsv"
        tsv.write_text("中文\t0.3\n中國\t0.9\n中心\t0.6\n", encoding="utf-8")

        pd = load_phrase_dict(tsv)
        results = pd.lookup("中")
        freqs = [e.frequency for e in results]
        assert freqs == sorted(freqs, reverse=True)

    def test_lookup_missing_character_returns_empty(self, tmp_path: Path) -> None:
        tsv = tmp_path / "phrases.tsv"
        tsv.write_text("你好\t0.9\n", encoding="utf-8")

        pd = load_phrase_dict(tsv)
        assert pd.lookup("X") == []

    def test_skips_single_char_entries(self, tmp_path: Path) -> None:
        tsv = tmp_path / "phrases.tsv"
        tsv.write_text("你\t0.9\n你好\t0.8\n", encoding="utf-8")

        pd = load_phrase_dict(tsv)
        assert pd.total == 1

    def test_skips_comments_and_blank_lines(self, tmp_path: Path) -> None:
        content = "# comment\n\n你好\t0.9\n\n# another comment\n中文\t0.7\n"
        tsv = tmp_path / "phrases.tsv"
        tsv.write_text(content, encoding="utf-8")

        pd = load_phrase_dict(tsv)
        assert pd.total == 2

    def test_default_frequency_when_missing(self, tmp_path: Path) -> None:
        tsv = tmp_path / "phrases.tsv"
        tsv.write_text("你好\n", encoding="utf-8")

        pd = load_phrase_dict(tsv)
        results = pd.lookup("你")
        assert len(results) == 1
        assert results[0].frequency == 0.0

    def test_invalid_frequency_defaults_to_zero(self, tmp_path: Path) -> None:
        tsv = tmp_path / "phrases.tsv"
        tsv.write_text("你好\tabc\n", encoding="utf-8")

        pd = load_phrase_dict(tsv)
        results = pd.lookup("你")
        assert len(results) == 1
        assert results[0].frequency == 0.0


# ---------------------------------------------------------------------------
# JSON lines loading
# ---------------------------------------------------------------------------


class TestLoadJSONL:
    """Test loading phrase dictionaries from JSON lines files."""

    def test_basic_jsonl_loading(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "phrases.jsonl"
        lines = [
            '{"phrase": "你好", "frequency": 0.9}',
            '{"phrase": "中文", "frequency": 0.7}',
        ]
        jsonl.write_text("\n".join(lines), encoding="utf-8")

        pd = load_phrase_dict(jsonl)
        assert pd.total == 2

    def test_jsonl_skips_invalid_json(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "phrases.jsonl"
        lines = [
            '{"phrase": "你好", "frequency": 0.9}',
            "not valid json",
            '{"phrase": "中文", "frequency": 0.7}',
        ]
        jsonl.write_text("\n".join(lines), encoding="utf-8")

        pd = load_phrase_dict(jsonl)
        assert pd.total == 2


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error conditions."""

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_phrase_dict(tmp_path / "nonexistent.tsv")

    def test_unrecognized_extension(self, tmp_path: Path) -> None:
        bad = tmp_path / "phrases.xml"
        bad.write_text("<data/>", encoding="utf-8")
        with pytest.raises(ValueError, match="Unrecognized"):
            load_phrase_dict(bad)


# ---------------------------------------------------------------------------
# PhraseDict unit tests
# ---------------------------------------------------------------------------


class TestPhraseDict:
    """Test PhraseDict directly."""

    def test_empty_dict(self) -> None:
        pd = PhraseDict()
        assert pd.total == 0
        assert pd.lookup("你") == []

    def test_build_index_groups_by_first_char(self) -> None:
        entries = [
            PhraseEntry(phrase="你好", frequency=0.9),
            PhraseEntry(phrase="你們", frequency=0.8),
            PhraseEntry(phrase="中文", frequency=0.7),
        ]
        pd = PhraseDict()
        pd._build_index(entries)
        assert pd.total == 3
        assert len(pd.lookup("你")) == 2
        assert len(pd.lookup("中")) == 1


# ---------------------------------------------------------------------------
# Integration: load real phrase file
# ---------------------------------------------------------------------------


class TestRealPhraseFile:
    """Integration test with the generated phrase data file."""

    PHRASE_FILE = Path(__file__).resolve().parent.parent / "data" / "phrases.tsv"

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / "data" / "phrases.tsv").exists(),
        reason="Generated phrase file not available",
    )
    def test_loads_at_least_50000_phrases(self) -> None:
        pd = load_phrase_dict(self.PHRASE_FILE)
        assert pd.total >= 50_000, f"Expected ≥50,000 phrases, got {pd.total}"

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / "data" / "phrases.tsv").exists(),
        reason="Generated phrase file not available",
    )
    def test_lookup_common_character(self) -> None:
        pd = load_phrase_dict(self.PHRASE_FILE)
        # 中 is extremely common as a first character
        results = pd.lookup("中")
        assert len(results) > 0, "Expected phrases starting with 中"
