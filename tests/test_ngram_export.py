"""Tests for A5: trigram export helper and content.js-aligned scoring."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from stroke_input.data.models import PhraseEntry
from stroke_input.data.ngram_model import NgramModel
from stroke_input.data.ngram_export import export_trigrams_for_chrome, export_bigrams_for_chrome


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model(*phrases: str) -> NgramModel:
    entries = [PhraseEntry(phrase=p, frequency=1.0) for p in phrases]
    return NgramModel.build_from_phrases(entries)


# ---------------------------------------------------------------------------
# export_trigrams_for_chrome
# ---------------------------------------------------------------------------

class TestExportTrigramsForChrome:
    def test_returns_dict(self) -> None:
        m = _model("中文字")
        result = export_trigrams_for_chrome(m)
        assert isinstance(result, dict)

    def test_known_trigram_present(self) -> None:
        m = _model("香港人")
        result = export_trigrams_for_chrome(m)
        # Should have entry for prev2="香" -> prev1="港" -> char="人"
        assert "香" in result
        assert "港" in result["香"]
        assert "人" in result["香"]["港"]

    def test_scores_are_floats_in_0_1(self) -> None:
        m = _model("中文字", "中文書", "中文版")
        result = export_trigrams_for_chrome(m)
        for p2, bi in result.items():
            for p1, chars in bi.items():
                for c, score in chars.items():
                    assert isinstance(score, float), f"score not float: {p2}→{p1}→{c}={score}"
                    assert 0.0 < score <= 1.0, f"score out of range: {p2}→{p1}→{c}={score}"

    def test_min_count_filters_rare_trigrams(self) -> None:
        # "中文字" appears once; "香港人" appears 5 times
        entries = [PhraseEntry(phrase="香港人", frequency=1.0)] * 5 + \
                  [PhraseEntry(phrase="中文字", frequency=1.0)]
        m = NgramModel.build_from_phrases(entries)
        # min_count=3: only "香港人" trigram should survive
        result = export_trigrams_for_chrome(m, min_count=3)
        assert "香" in result
        assert result["香"]["港"]["人"] > 0
        # "中文字" trigram should be filtered out
        assert "中" not in result or "文" not in result.get("中", {}) or \
               "字" not in result.get("中", {}).get("文", {})

    def test_json_serializable(self) -> None:
        m = _model("香港人", "香港島")
        result = export_trigrams_for_chrome(m)
        serialized = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed == result

    def test_empty_model_returns_empty_dict(self) -> None:
        m = _model()
        assert export_trigrams_for_chrome(m) == {}


# ---------------------------------------------------------------------------
# export_bigrams_for_chrome
# ---------------------------------------------------------------------------

class TestExportBigramsForChrome:
    def test_known_bigram_present(self) -> None:
        m = _model("你好", "你們")
        result = export_bigrams_for_chrome(m)
        assert "你" in result
        assert "好" in result["你"]
        assert "們" in result["你"]

    def test_scores_in_0_1(self) -> None:
        m = _model("香港人", "中文字")
        result = export_bigrams_for_chrome(m)
        for p, chars in result.items():
            for c, score in chars.items():
                assert 0.0 < score <= 1.0

    def test_more_frequent_bigram_higher_score(self) -> None:
        # "你好" appears 3 times, "你壞" once
        entries = [PhraseEntry(phrase="你好", frequency=1.0)] * 3 + \
                  [PhraseEntry(phrase="你壞", frequency=1.0)]
        m = NgramModel.build_from_phrases(entries)
        result = export_bigrams_for_chrome(m)
        assert result["你"]["好"] > result["你"]["壞"]

    def test_empty_model_returns_empty_dict(self) -> None:
        m = _model()
        assert export_bigrams_for_chrome(m) == {}


# ---------------------------------------------------------------------------
# Round-trip: write JSON files and load them back
# ---------------------------------------------------------------------------

class TestExportRoundTrip:
    def test_write_and_load_trigrams(self, tmp_path: Path) -> None:
        m = _model("香港人", "香港島")
        data = export_trigrams_for_chrome(m)
        fp = tmp_path / "trigrams.json"
        fp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        loaded = json.loads(fp.read_text(encoding="utf-8"))
        assert loaded["香"]["港"]["人"] == pytest.approx(data["香"]["港"]["人"], rel=1e-6)

    def test_write_and_load_bigrams(self, tmp_path: Path) -> None:
        m = _model("你好", "你們")
        data = export_bigrams_for_chrome(m)
        fp = tmp_path / "bigrams.json"
        fp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        loaded = json.loads(fp.read_text(encoding="utf-8"))
        assert loaded["你"]["好"] == pytest.approx(data["你"]["好"], rel=1e-6)
