"""Unit tests for StrokeEngine prefix matching."""

import pytest

from stroke_input.data.models import CharacterRecord, StrokeType
from stroke_input.engine.stroke_engine import StrokeEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_records() -> list[CharacterRecord]:
    """Build a small set of known character records for testing."""
    return [
        CharacterRecord(character="一", stroke_sequence=[1], frequency=0.9),
        CharacterRecord(character="二", stroke_sequence=[1, 1], frequency=0.8),
        CharacterRecord(character="三", stroke_sequence=[1, 1, 1], frequency=0.7),
        CharacterRecord(character="十", stroke_sequence=[1, 2], frequency=0.85),
        CharacterRecord(character="大", stroke_sequence=[1, 3, 4], frequency=0.95),
        CharacterRecord(character="人", stroke_sequence=[3, 4], frequency=0.92),
        CharacterRecord(character="丁", stroke_sequence=[1, 2], frequency=0.3),
    ]


@pytest.fixture
def engine() -> StrokeEngine:
    return StrokeEngine(_make_records())


# ---------------------------------------------------------------------------
# Index & query basics
# ---------------------------------------------------------------------------

class TestPrefixMatching:
    """Tests for prefix-based candidate lookup."""

    def test_empty_sequence_returns_all(self, engine: StrokeEngine):
        results = engine.query([])
        chars = {r.character for r in results}
        assert chars == {"一", "二", "三", "十", "大", "人", "丁"}

    def test_single_stroke_prefix(self, engine: StrokeEngine):
        results = engine.query([1])
        chars = {r.character for r in results}
        # All characters starting with HENG(1)
        assert chars == {"一", "二", "三", "十", "大", "丁"}
        assert "人" not in chars  # starts with PIE(3)

    def test_two_stroke_prefix(self, engine: StrokeEngine):
        results = engine.query([1, 1])
        chars = {r.character for r in results}
        assert chars == {"二", "三"}

    def test_exact_match(self, engine: StrokeEngine):
        results = engine.query([3, 4])
        chars = {r.character for r in results}
        assert "人" in chars

    def test_no_match_returns_empty(self, engine: StrokeEngine):
        results = engine.query([5, 5, 5, 5])
        assert results == []

    def test_query_uses_current_sequence_when_none(self, engine: StrokeEngine):
        engine.append_stroke(1)
        engine.append_stroke(3)
        results = engine.query()
        chars = {r.character for r in results}
        assert chars == {"大"}

    def test_multiple_records_at_same_sequence(self, engine: StrokeEngine):
        # 十 and 丁 both have [1, 2]
        results = engine.query([1, 2])
        chars = {r.character for r in results}
        assert "十" in chars
        assert "丁" in chars


# ---------------------------------------------------------------------------
# Stroke sequence manipulation
# ---------------------------------------------------------------------------

class TestSequenceManipulation:
    """Tests for append_stroke, remove_last_stroke, clear_sequence."""

    def test_append_stroke(self, engine: StrokeEngine):
        engine.append_stroke(StrokeType.HENG)
        assert engine.current_sequence == [1]
        engine.append_stroke(StrokeType.SHU)
        assert engine.current_sequence == [1, 2]

    def test_remove_last_stroke(self, engine: StrokeEngine):
        engine.append_stroke(1)
        engine.append_stroke(2)
        engine.remove_last_stroke()
        assert engine.current_sequence == [1]

    def test_remove_last_stroke_on_empty(self, engine: StrokeEngine):
        engine.remove_last_stroke()  # should not raise
        assert engine.current_sequence == []

    def test_clear_sequence(self, engine: StrokeEngine):
        engine.append_stroke(1)
        engine.append_stroke(2)
        engine.append_stroke(3)
        engine.clear_sequence()
        assert engine.current_sequence == []

    def test_current_sequence_is_copy(self, engine: StrokeEngine):
        engine.append_stroke(1)
        seq = engine.current_sequence
        seq.append(999)
        assert engine.current_sequence == [1]  # internal state unchanged


# ---------------------------------------------------------------------------
# Empty engine
# ---------------------------------------------------------------------------

class TestEmptyEngine:
    """Edge cases with no records."""

    def test_empty_db_returns_empty(self):
        engine = StrokeEngine([])
        assert engine.query([1]) == []
        assert engine.query([]) == []


# ---------------------------------------------------------------------------
# Wildcard matching (Requirements 4.1, 4.2, 4.3)
# ---------------------------------------------------------------------------

class TestWildcardMatching:
    """Tests for wildcard (code 6) support in query()."""

    def test_single_wildcard_matches_all_first_strokes(self, engine: StrokeEngine):
        """A single wildcard at position 0 should match all characters (any first stroke)."""
        results = engine.query([StrokeType.WILDCARD])
        chars = {r.character for r in results}
        # All characters in the fixture start with stroke 1 or 3
        assert chars == {"一", "二", "三", "十", "大", "人", "丁"}

    def test_wildcard_at_second_position(self, engine: StrokeEngine):
        """Wildcard at second position: [1, *] should match all chars starting with HENG
        that have at least 2 strokes."""
        results = engine.query([1, StrokeType.WILDCARD])
        chars = {r.character for r in results}
        # 二=[1,1], 三=[1,1,1], 十=[1,2], 丁=[1,2], 大=[1,3,4]
        assert chars == {"二", "三", "十", "丁", "大"}
        # 一=[1] has only 1 stroke, so it shouldn't match a 2-stroke prefix
        assert "一" not in chars

    def test_wildcard_matches_specific_position(self, engine: StrokeEngine):
        """[1, *, 4] should match characters with HENG first, any second, DIAN third."""
        results = engine.query([1, StrokeType.WILDCARD, 4])
        chars = {r.character for r in results}
        # 大=[1,3,4] matches (wildcard covers 3 at position 1)
        assert "大" in chars
        # 三=[1,1,1] does not match (third stroke is 1, not 4)
        assert "三" not in chars

    def test_multiple_wildcards(self, engine: StrokeEngine):
        """Multiple wildcards: [*, *] should match all characters with >= 2 strokes."""
        results = engine.query([StrokeType.WILDCARD, StrokeType.WILDCARD])
        chars = {r.character for r in results}
        # All chars with 2+ strokes
        assert "二" in chars   # [1,1]
        assert "三" in chars   # [1,1,1]
        assert "十" in chars   # [1,2]
        assert "丁" in chars   # [1,2]
        assert "大" in chars   # [1,3,4]
        assert "人" in chars   # [3,4]
        # 一=[1] has only 1 stroke, should NOT match
        assert "一" not in chars

    def test_three_wildcards(self, engine: StrokeEngine):
        """[*, *, *] should match all characters with >= 3 strokes."""
        results = engine.query([StrokeType.WILDCARD, StrokeType.WILDCARD, StrokeType.WILDCARD])
        chars = {r.character for r in results}
        assert "三" in chars   # [1,1,1]
        assert "大" in chars   # [1,3,4]
        # Characters with fewer than 3 strokes should not match
        assert "一" not in chars  # 1 stroke
        assert "二" not in chars  # 2 strokes
        assert "人" not in chars  # 2 strokes

    def test_wildcard_with_no_match(self, engine: StrokeEngine):
        """Wildcards that exceed all character lengths return empty."""
        # No character in fixture has 4+ strokes
        results = engine.query([6, 6, 6, 6])
        assert results == []

    def test_wildcard_mixed_with_exact_strokes(self, engine: StrokeEngine):
        """[*, 4] should match characters with any first stroke and DIAN as second."""
        results = engine.query([StrokeType.WILDCARD, 4])
        chars = {r.character for r in results}
        # 人=[3,4] matches (wildcard covers 3, second is 4)
        assert "人" in chars
        # 十=[1,2] does not match (second stroke is 2, not 4)
        assert "十" not in chars

    def test_wildcard_via_append_stroke(self, engine: StrokeEngine):
        """Wildcard should work when appended via append_stroke()."""
        engine.append_stroke(StrokeType.WILDCARD)
        engine.append_stroke(StrokeType.DIAN)
        results = engine.query()
        chars = {r.character for r in results}
        assert "人" in chars  # [3,4]

    def test_wildcard_superset_of_exact(self, engine: StrokeEngine):
        """Wildcard results should be a superset of any specific stroke at that position."""
        exact_results = engine.query([1, 1])
        wildcard_results = engine.query([1, StrokeType.WILDCARD])
        exact_chars = {r.character for r in exact_results}
        wildcard_chars = {r.character for r in wildcard_results}
        assert exact_chars.issubset(wildcard_chars)
