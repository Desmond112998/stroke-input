"""Tests for recency decay and position-aware features in UserFreqStore.

These tests cover the new A2 (recency) and A3 (position-aware) behaviour.
They are kept in a separate file to avoid touching the existing
test_user_freq_store.py contract tests.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import pytest

from stroke_input.data.user_freq_store import UserFreqStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh(tmp_path: Path) -> UserFreqStore:
    return UserFreqStore(tmp_path / "freq.json")


# ===========================================================================
# A2 — Recency Decay
# ===========================================================================

class TestRecencyScore:
    """recency_score(char, now, tau_days) → float in [0, 1]."""

    def test_never_selected_returns_zero(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        assert store.recency_score("你") == 0.0

    def test_just_selected_returns_near_one(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        now = time.time()
        store.record_selection("你", timestamp=now)
        score = store.recency_score("你", now=now, tau_days=30.0)
        assert score == pytest.approx(1.0, rel=1e-6)

    def test_decays_over_time(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        # Selected 30 days ago → exp(-1) ≈ 0.368
        thirty_days_ago = time.time() - 30 * 86400
        store.record_selection("好", timestamp=thirty_days_ago)
        score = store.recency_score("好", now=time.time(), tau_days=30.0)
        assert score == pytest.approx(math.exp(-1.0), rel=0.01)

    def test_older_selection_has_lower_score(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        now = time.time()
        store.record_selection("甲", timestamp=now - 10 * 86400)
        store.record_selection("乙", timestamp=now - 60 * 86400)
        assert store.recency_score("甲", now=now) > store.recency_score("乙", now=now)

    def test_uses_most_recent_selection(self, tmp_path: Path) -> None:
        """Multiple selections → recency should reflect the latest one."""
        store = _fresh(tmp_path)
        now = time.time()
        store.record_selection("中", timestamp=now - 90 * 86400)
        store.record_selection("中", timestamp=now - 1 * 86400)
        score = store.recency_score("中", now=now, tau_days=30.0)
        expected = math.exp(-1 / 30)
        assert score == pytest.approx(expected, rel=0.01)

    def test_recency_score_in_0_1_range(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        now = time.time()
        store.record_selection("香", timestamp=now - 5 * 86400)
        score = store.recency_score("香", now=now)
        assert 0.0 <= score <= 1.0

    def test_score_zero_without_any_record(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        assert store.recency_score("未知", now=time.time()) == 0.0

    def test_default_now_is_current_time(self, tmp_path: Path) -> None:
        """Calling without now= should not raise and should return ~1 for just-selected."""
        store = _fresh(tmp_path)
        store.record_selection("你", timestamp=time.time())
        score = store.recency_score("你")
        assert score == pytest.approx(1.0, abs=0.01)


class TestRecencyPersistence:
    """Timestamps must survive save/load round-trip."""

    def test_timestamps_saved_and_loaded(self, tmp_path: Path) -> None:
        fp = tmp_path / "freq.json"
        store = UserFreqStore(fp)
        ts = time.time() - 5 * 86400
        store.record_selection("好", timestamp=ts)
        store.save()

        loaded = UserFreqStore(fp)
        loaded.load()
        score = loaded.recency_score("好", now=time.time(), tau_days=30.0)
        expected = math.exp(-5 / 30)
        assert score == pytest.approx(expected, rel=0.01)

    def test_old_json_without_timestamps_loads_cleanly(self, tmp_path: Path) -> None:
        """Backwards-compat: existing JSON files without timestamps should load fine."""
        fp = tmp_path / "freq.json"
        fp.write_text('{"你": 5, "好": 3}', encoding="utf-8")
        store = UserFreqStore(fp)
        store.load()
        assert store.get_score("你") == 5
        # No timestamp → recency = 0
        assert store.recency_score("你") == 0.0


# ===========================================================================
# A3 — Position-Aware Learning
# ===========================================================================

class TestPositionRecord:
    """record_position(stroke_seq, char, rank) stores ranked selection data."""

    def test_record_and_retrieve_avg_rank(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.record_position("jk", "你", rank=0)
        store.record_position("jk", "你", rank=0)
        store.record_position("jk", "你", rank=2)
        # average rank = (0+0+2)/3 = 0.667
        assert store.average_rank("jk", "你") == pytest.approx(2 / 3, rel=1e-6)

    def test_unknown_stroke_seq_returns_none(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        assert store.average_rank("zz", "你") is None

    def test_unknown_char_for_known_seq_returns_none(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.record_position("jk", "你", rank=0)
        assert store.average_rank("jk", "他") is None

    def test_multiple_chars_same_seq(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.record_position("jk", "你", rank=0)
        store.record_position("jk", "他", rank=3)
        assert store.average_rank("jk", "你") == pytest.approx(0.0)
        assert store.average_rank("jk", "他") == pytest.approx(3.0)


class TestPositionScore:
    """position_score(stroke_seq, char) → float in [0, 1]."""

    def test_rank_zero_gives_score_one(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.record_position("jk", "你", rank=0)
        assert store.position_score("jk", "你") == pytest.approx(1.0, rel=1e-6)

    def test_unknown_gives_score_zero(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        assert store.position_score("jk", "你") == 0.0

    def test_higher_rank_gives_lower_score(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.record_position("jk", "你", rank=0)
        store.record_position("jk", "好", rank=5)
        assert store.position_score("jk", "你") > store.position_score("jk", "好")

    def test_score_in_0_1_range(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        for rank in [0, 1, 5, 8]:
            store.record_position("jk", "你", rank=rank)
        s = store.position_score("jk", "你")
        assert 0.0 <= s <= 1.0


class TestPositionPersistence:
    """Position data must survive save/load round-trip."""

    def test_position_data_saved_and_loaded(self, tmp_path: Path) -> None:
        fp = tmp_path / "freq.json"
        store = UserFreqStore(fp)
        store.record_position("jk", "你", rank=1)
        store.save()

        loaded = UserFreqStore(fp)
        loaded.load()
        assert loaded.average_rank("jk", "你") == pytest.approx(1.0)

    def test_old_json_without_position_loads_cleanly(self, tmp_path: Path) -> None:
        fp = tmp_path / "freq.json"
        fp.write_text('{"你": 5}', encoding="utf-8")
        store = UserFreqStore(fp)
        store.load()
        assert store.position_score("jk", "你") == 0.0
