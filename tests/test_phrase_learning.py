"""Tests for B3: user phrase auto-learning in UserFreqStore.

When the user consecutively selects two or more characters without clearing
stroke input, those characters are auto-recorded as a learned phrase.  The
learned phrase is stored in a ``phrase_freq`` table (dict of phrase → count).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stroke_input.data.user_freq_store import UserFreqStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh(tmp_path: Path) -> UserFreqStore:
    return UserFreqStore(tmp_path / "freq.json")


# ===========================================================================
# record_phrase  /  get_phrase_count
# ===========================================================================

class TestRecordPhrase:
    def test_record_phrase_increments_count(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.record_phrase("香港")
        assert store.get_phrase_count("香港") == 1

    def test_record_phrase_multiple_times(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.record_phrase("你好")
        store.record_phrase("你好")
        store.record_phrase("你好")
        assert store.get_phrase_count("你好") == 3

    def test_unknown_phrase_returns_zero(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        assert store.get_phrase_count("中文") == 0

    def test_record_single_char_is_ignored(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.record_phrase("你")
        assert store.get_phrase_count("你") == 0

    def test_record_empty_string_is_ignored(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.record_phrase("")
        assert store.get_phrase_count("") == 0

    def test_different_phrases_tracked_independently(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.record_phrase("香港")
        store.record_phrase("中文")
        store.record_phrase("中文")
        assert store.get_phrase_count("香港") == 1
        assert store.get_phrase_count("中文") == 2


# ===========================================================================
# top_phrases
# ===========================================================================

class TestTopPhrases:
    def test_returns_sorted_by_count_descending(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.record_phrase("香港")
        store.record_phrase("中文")
        store.record_phrase("中文")
        store.record_phrase("你好")
        store.record_phrase("你好")
        store.record_phrase("你好")
        top = store.top_phrases(n=3)
        assert [p for p, _ in top] == ["你好", "中文", "香港"]
        assert [c for _, c in top] == [3, 2, 1]

    def test_n_limits_results(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        for phrase in ["AB", "CD", "EF", "GH", "IJ"]:
            store.record_phrase(phrase)
        top = store.top_phrases(n=2)
        assert len(top) <= 2

    def test_empty_store_returns_empty(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        assert store.top_phrases() == []


# ===========================================================================
# auto_learn_phrase — helper method
# ===========================================================================

class TestAutoLearnPhrase:
    """auto_learn_phrase(chars) joins consecutive chars and records phrase."""

    def test_two_chars_learned(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.auto_learn_phrase(["香", "港"])
        assert store.get_phrase_count("香港") == 1

    def test_three_chars_learned(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.auto_learn_phrase(["中", "文", "字"])
        assert store.get_phrase_count("中文字") == 1

    def test_single_char_not_learned(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.auto_learn_phrase(["你"])
        assert store.get_phrase_count("你") == 0

    def test_empty_list_not_learned(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.auto_learn_phrase([])
        assert store.top_phrases() == []


# ===========================================================================
# Persistence round-trip
# ===========================================================================

class TestPhrasePersistence:
    def test_phrase_freq_saved_and_loaded(self, tmp_path: Path) -> None:
        fp = tmp_path / "freq.json"
        store = UserFreqStore(fp)
        store.record_phrase("香港")
        store.record_phrase("香港")
        store.save()

        loaded = UserFreqStore(fp)
        loaded.load()
        assert loaded.get_phrase_count("香港") == 2

    def test_old_json_without_phrase_freq_loads_cleanly(self, tmp_path: Path) -> None:
        fp = tmp_path / "freq.json"
        fp.write_text('{"你": 5, "好": 3}', encoding="utf-8")
        store = UserFreqStore(fp)
        store.load()
        # No phrase data in old format → phrase count = 0
        assert store.get_phrase_count("你好") == 0

    def test_v2_json_without_phrase_freq_loads_cleanly(self, tmp_path: Path) -> None:
        import json as _json
        fp = tmp_path / "freq.json"
        fp.write_text(
            _json.dumps({"v": 2, "counts": {"你": 5}, "timestamps": {}, "positions": {}}),
            encoding="utf-8",
        )
        store = UserFreqStore(fp)
        store.load()
        assert store.get_phrase_count("你好") == 0
        # Basic counts still work
        assert store.get_score("你") == 5
