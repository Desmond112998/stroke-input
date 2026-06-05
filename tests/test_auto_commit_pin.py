"""Tests for C1 (auto-commit on unique) and C2 (smart pin) engine APIs.

C1: InferenceEngine / StrokeEngine should expose `is_unique_candidate()`
    so the extension can show an auto-commit hint.

C2: UserFreqStore.pin_character(stroke_seq, char) stores a permanent pin
    that `position_score` honours above all other candidates.
    After K consecutive same selections under a prefix, the pin is set
    automatically via `maybe_auto_pin(stroke_seq, char, threshold)`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stroke_input.data.models import CharacterRecord
from stroke_input.data.user_freq_store import UserFreqStore
from stroke_input.engine.stroke_engine import StrokeEngine
from stroke_input.engine.inference_engine import InferenceEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _records(*chars: str) -> list[CharacterRecord]:
    return [
        CharacterRecord(character=ch, stroke_sequence=[1, 2], frequency=0.5)
        for ch in chars
    ]


def _engine(*chars: str) -> StrokeEngine:
    return StrokeEngine(_records(*chars))


def _fresh(tmp_path: Path) -> UserFreqStore:
    return UserFreqStore(tmp_path / "freq.json")


# ===========================================================================
# C1 — Auto-commit on unique candidate
# ===========================================================================

class TestIsUniqueCandidate:
    def test_single_candidate_is_unique(self) -> None:
        se = _engine("你")
        ie = InferenceEngine(se)
        result = ie.query([1, 2])
        assert ie.is_unique_candidate(result) is True

    def test_multiple_candidates_not_unique(self) -> None:
        # Two chars share same stroke sequence [1,2]
        records = [
            CharacterRecord(character="你", stroke_sequence=[1, 2], frequency=0.5),
            CharacterRecord(character="好", stroke_sequence=[1, 2], frequency=0.4),
        ]
        se = StrokeEngine(records)
        ie = InferenceEngine(se)
        result = ie.query([1, 2])
        assert ie.is_unique_candidate(result) is False

    def test_empty_candidates_not_unique(self) -> None:
        se = _engine("你")
        ie = InferenceEngine(se)
        assert ie.is_unique_candidate([]) is False

    def test_is_unique_candidate_is_method(self) -> None:
        ie = InferenceEngine(_engine("你"))
        assert callable(ie.is_unique_candidate)


# ===========================================================================
# C2 — Smart Pin
# ===========================================================================

class TestPinCharacter:
    def test_pin_gives_max_position_score(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.pin_character("jk", "你")
        score = store.position_score("jk", "你")
        # Pinned character should score 1.0
        assert score == pytest.approx(1.0)

    def test_pin_overrides_low_avg_rank(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        # Record this char at rank 8 (low score)
        for _ in range(5):
            store.record_position("jk", "你", rank=8)
        # After pinning, score should become 1.0
        store.pin_character("jk", "你")
        assert store.position_score("jk", "你") == pytest.approx(1.0)

    def test_unpin_removes_pin(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        store.pin_character("jk", "你")
        store.unpin_character("jk", "你")
        # Without any rank history, back to 0
        assert store.position_score("jk", "你") == 0.0

    def test_is_pinned(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        assert store.is_pinned("jk", "你") is False
        store.pin_character("jk", "你")
        assert store.is_pinned("jk", "你") is True

    def test_pin_persists_through_save_load(self, tmp_path: Path) -> None:
        fp = tmp_path / "freq.json"
        store = UserFreqStore(fp)
        store.pin_character("jk", "你")
        store.save()
        loaded = UserFreqStore(fp)
        loaded.load()
        assert loaded.is_pinned("jk", "你") is True
        assert loaded.position_score("jk", "你") == pytest.approx(1.0)


class TestMaybeAutoPinning:
    def test_below_threshold_does_not_pin(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        for _ in range(2):
            store.record_position("jk", "你", rank=0)
        store.maybe_auto_pin("jk", "你", threshold=3)
        assert store.is_pinned("jk", "你") is False

    def test_at_threshold_with_rank_zero_pins(self, tmp_path: Path) -> None:
        store = _fresh(tmp_path)
        for _ in range(3):
            store.record_position("jk", "你", rank=0)
        store.maybe_auto_pin("jk", "你", threshold=3)
        assert store.is_pinned("jk", "你") is True

    def test_high_avg_rank_does_not_pin(self, tmp_path: Path) -> None:
        """Only pin when user consistently selects at rank 0."""
        store = _fresh(tmp_path)
        for _ in range(5):
            store.record_position("jk", "你", rank=3)
        store.maybe_auto_pin("jk", "你", threshold=3)
        assert store.is_pinned("jk", "你") is False

    def test_auto_pin_default_threshold(self, tmp_path: Path) -> None:
        from stroke_input.data.user_freq_store import AUTO_PIN_THRESHOLD
        store = _fresh(tmp_path)
        for _ in range(AUTO_PIN_THRESHOLD):
            store.record_position("jk", "你", rank=0)
        store.maybe_auto_pin("jk", "你")
        assert store.is_pinned("jk", "你") is True
