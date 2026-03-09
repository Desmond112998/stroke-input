"""Unit tests for core data models."""

import pytest

from stroke_input.data.models import (
    KEY_TO_STROKE,
    STROKE_NAMES,
    STROKE_SYMBOLS,
    STROKE_TO_KEY,
    CharacterRecord,
    PhraseEntry,
    StrokeType,
)


class TestStrokeType:
    """Tests for the StrokeType enum."""

    def test_stroke_values(self):
        assert StrokeType.HENG == 1
        assert StrokeType.SHU == 2
        assert StrokeType.PIE == 3
        assert StrokeType.DIAN == 4
        assert StrokeType.ZHE == 5
        assert StrokeType.WILDCARD == 6

    def test_five_basic_strokes_plus_wildcard(self):
        assert len(StrokeType) == 6

    def test_stroke_type_is_int(self):
        # StrokeType values can be used directly as ints
        assert StrokeType.HENG + StrokeType.SHU == 3


class TestKeyMapping:
    """Tests for key mapping constants matching macOS Stroke - Traditional."""

    def test_key_to_stroke_mapping(self):
        assert KEY_TO_STROKE["j"] == 1  # J → 橫
        assert KEY_TO_STROKE["k"] == 2  # K → 豎
        assert KEY_TO_STROKE["l"] == 3  # L → 撇
        assert KEY_TO_STROKE["u"] == 4  # U → 點
        assert KEY_TO_STROKE["i"] == 5  # I → 折
        assert KEY_TO_STROKE["o"] == 6  # O → 萬用

    def test_six_keys_mapped(self):
        assert len(KEY_TO_STROKE) == 6

    def test_reverse_mapping_consistency(self):
        for key, code in KEY_TO_STROKE.items():
            assert STROKE_TO_KEY[code] == key

    def test_stroke_symbols_for_all_types(self):
        for st in StrokeType:
            assert st.value in STROKE_SYMBOLS

    def test_stroke_names_for_all_types(self):
        for st in StrokeType:
            assert st.value in STROKE_NAMES


class TestCharacterRecord:
    """Tests for the CharacterRecord dataclass."""

    def test_basic_creation(self):
        rec = CharacterRecord(
            character="字",
            stroke_sequence=[4, 4, 5, 2, 1, 2],
            frequency=0.85,
        )
        assert rec.character == "字"
        assert rec.stroke_sequence == [4, 4, 5, 2, 1, 2]
        assert rec.stroke_count == 6
        assert rec.frequency == 0.85

    def test_auto_stroke_count(self):
        rec = CharacterRecord(character="大", stroke_sequence=[1, 3, 4])
        assert rec.stroke_count == 3

    def test_explicit_stroke_count_preserved(self):
        rec = CharacterRecord(
            character="大", stroke_sequence=[1, 3, 4], stroke_count=3
        )
        assert rec.stroke_count == 3

    def test_empty_defaults(self):
        rec = CharacterRecord(character="？")
        assert rec.stroke_sequence == []
        assert rec.stroke_count == 0
        assert rec.frequency == 0.0


class TestPhraseEntry:
    """Tests for the PhraseEntry dataclass."""

    def test_basic_creation(self):
        entry = PhraseEntry(phrase="你好", frequency=0.95)
        assert entry.phrase == "你好"
        assert entry.frequency == 0.95

    def test_default_frequency(self):
        entry = PhraseEntry(phrase="世界")
        assert entry.frequency == 0.0
