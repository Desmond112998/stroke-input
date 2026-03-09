"""Tests for the user frequency store."""

import json
from pathlib import Path

import pytest

from stroke_input.data.user_freq_store import UserFreqStore


class TestIncrement:
    """Test incrementing character counts."""

    def test_increment_new_character(self) -> None:
        store = UserFreqStore(Path("dummy.json"))
        store.increment("你")
        assert store.get_score("你") == 1

    def test_increment_existing_character(self) -> None:
        store = UserFreqStore(Path("dummy.json"))
        store.increment("好")
        store.increment("好")
        store.increment("好")
        assert store.get_score("好") == 3

    def test_increment_empty_string_ignored(self) -> None:
        store = UserFreqStore(Path("dummy.json"))
        store.increment("")
        assert store.counts == {}


class TestGetScore:
    """Test score retrieval."""

    def test_unknown_character_returns_zero(self) -> None:
        store = UserFreqStore(Path("dummy.json"))
        assert store.get_score("X") == 0

    def test_returns_correct_count(self) -> None:
        store = UserFreqStore(Path("dummy.json"))
        store.increment("中")
        store.increment("中")
        assert store.get_score("中") == 2


class TestLoadSave:
    """Test JSON persistence round-trip."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        fp = tmp_path / "freq.json"
        store = UserFreqStore(fp)
        store.increment("你")
        store.increment("你")
        store.increment("好")
        store.save()

        loaded = UserFreqStore(fp)
        loaded.load()
        assert loaded.get_score("你") == 2
        assert loaded.get_score("好") == 1

    def test_load_missing_file_starts_fresh(self, tmp_path: Path) -> None:
        fp = tmp_path / "nonexistent.json"
        store = UserFreqStore(fp)
        store.load()
        assert store.counts == {}

    def test_load_corrupted_json_starts_fresh(self, tmp_path: Path) -> None:
        fp = tmp_path / "bad.json"
        fp.write_text("{not valid json!!!", encoding="utf-8")
        store = UserFreqStore(fp)
        store.load()
        assert store.counts == {}

    def test_load_non_dict_json_starts_fresh(self, tmp_path: Path) -> None:
        fp = tmp_path / "array.json"
        fp.write_text("[1, 2, 3]", encoding="utf-8")
        store = UserFreqStore(fp)
        store.load()
        assert store.counts == {}

    def test_load_skips_invalid_entries(self, tmp_path: Path) -> None:
        fp = tmp_path / "mixed.json"
        data = {"你": 5, "bad_key": "not_a_number", "好": 3}
        fp.write_text(json.dumps(data), encoding="utf-8")
        store = UserFreqStore(fp)
        store.load()
        assert store.get_score("你") == 5
        assert store.get_score("好") == 3
        assert store.get_score("bad_key") == 0

    def test_load_converts_float_to_int(self, tmp_path: Path) -> None:
        fp = tmp_path / "floats.json"
        fp.write_text('{"你": 3.7}', encoding="utf-8")
        store = UserFreqStore(fp)
        store.load()
        assert store.get_score("你") == 3

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        fp = tmp_path / "sub" / "dir" / "freq.json"
        store = UserFreqStore(fp)
        store.increment("中")
        store.save()
        assert fp.exists()

    def test_counts_property_returns_copy(self) -> None:
        store = UserFreqStore(Path("dummy.json"))
        store.increment("你")
        counts = store.counts
        counts["你"] = 999
        assert store.get_score("你") == 1  # original unchanged
