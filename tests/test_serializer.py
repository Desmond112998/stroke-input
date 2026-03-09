"""Unit tests for the stroke database serializer and deserializer."""

from pathlib import Path

import pytest

from stroke_input.data.models import CharacterRecord
from stroke_input.data.serializer import (
    load_database,
    load_json,
    load_msgpack,
    pretty_print,
    save_json,
    save_msgpack,
    serialize_json,
    serialize_msgpack,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_records() -> list[CharacterRecord]:
    return [
        CharacterRecord(character="一", stroke_sequence=[1], stroke_count=1, frequency=99.5),
        CharacterRecord(character="十", stroke_sequence=[1, 2], stroke_count=2, frequency=88.0),
        CharacterRecord(character="字", stroke_sequence=[1, 5, 1, 2, 1, 2], stroke_count=6, frequency=50.3),
    ]


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------

class TestJsonSerialization:

    def test_serialize_and_load_json_roundtrip(self, sample_records, tmp_path: Path):
        path = tmp_path / "db.json"
        save_json(sample_records, path)
        loaded = load_json(path)

        assert len(loaded) == len(sample_records)
        for orig, loaded_rec in zip(sample_records, loaded):
            assert loaded_rec.character == orig.character
            assert loaded_rec.stroke_sequence == orig.stroke_sequence
            assert loaded_rec.stroke_count == orig.stroke_count
            assert loaded_rec.frequency == pytest.approx(orig.frequency)

    def test_serialize_json_is_valid_json(self, sample_records):
        import json
        text = serialize_json(sample_records)
        data = json.loads(text)
        assert isinstance(data, list)
        assert len(data) == 3

    def test_empty_records(self, tmp_path: Path):
        path = tmp_path / "empty.json"
        save_json([], path)
        loaded = load_json(path)
        assert loaded == []


# ---------------------------------------------------------------------------
# msgpack round-trip
# ---------------------------------------------------------------------------

class TestMsgpackSerialization:

    def test_serialize_and_load_msgpack_roundtrip(self, sample_records, tmp_path: Path):
        path = tmp_path / "db.msgpack"
        save_msgpack(sample_records, path)
        loaded = load_msgpack(path)

        assert len(loaded) == len(sample_records)
        for orig, loaded_rec in zip(sample_records, loaded):
            assert loaded_rec.character == orig.character
            assert loaded_rec.stroke_sequence == orig.stroke_sequence
            assert loaded_rec.stroke_count == orig.stroke_count
            assert loaded_rec.frequency == pytest.approx(orig.frequency)

    def test_msgpack_is_compact(self, sample_records, tmp_path: Path):
        json_path = tmp_path / "db.json"
        msgpack_path = tmp_path / "db.msgpack"
        save_json(sample_records, json_path)
        save_msgpack(sample_records, msgpack_path)
        assert msgpack_path.stat().st_size < json_path.stat().st_size

    def test_empty_records(self, tmp_path: Path):
        path = tmp_path / "empty.msgpack"
        save_msgpack([], path)
        loaded = load_msgpack(path)
        assert loaded == []


# ---------------------------------------------------------------------------
# Unified loader (auto-detect)
# ---------------------------------------------------------------------------

class TestLoadDatabase:

    def test_load_json_by_extension(self, sample_records, tmp_path: Path):
        path = tmp_path / "db.json"
        save_json(sample_records, path)
        loaded = load_database(path)
        assert len(loaded) == len(sample_records)
        assert loaded[0].character == "一"

    def test_load_msgpack_by_extension(self, sample_records, tmp_path: Path):
        path = tmp_path / "db.msgpack"
        save_msgpack(sample_records, path)
        loaded = load_database(path)
        assert len(loaded) == len(sample_records)
        assert loaded[0].character == "一"

    def test_load_mpk_extension(self, sample_records, tmp_path: Path):
        path = tmp_path / "db.mpk"
        save_msgpack(sample_records, path)
        loaded = load_database(path)
        assert len(loaded) == len(sample_records)

    def test_unknown_extension_raises(self, tmp_path: Path):
        path = tmp_path / "db.xyz"
        path.write_text("dummy")
        with pytest.raises(ValueError, match="Unrecognized"):
            load_database(path)


# ---------------------------------------------------------------------------
# Pretty-printer
# ---------------------------------------------------------------------------

class TestPrettyPrint:

    def test_pretty_print_format(self, sample_records):
        output = pretty_print(sample_records)
        lines = output.strip().split("\n")
        assert len(lines) == 3
        # First record: 一
        assert lines[0].startswith("一")
        assert "[1]" in lines[0]
        assert "freq=99.50" in lines[0]

    def test_pretty_print_stroke_symbols(self):
        records = [
            CharacterRecord(character="測", stroke_sequence=[1, 2, 3, 4, 5], stroke_count=5, frequency=1.0),
        ]
        output = pretty_print(records)
        assert "一丨丿丶乙" in output
        assert "[1,2,3,4,5]" in output

    def test_pretty_print_empty(self):
        assert pretty_print([]) == ""
