"""Unit tests for the Make Me a Hanzi parser."""

import json
import logging
from pathlib import Path

import pytest

from stroke_input.data.models import CharacterRecord, StrokeType
from stroke_input.data.parser import (
    classify_stroke,
    parse_dictionary_file,
    parse_graphics_file,
    parse_make_me_a_hanzi,
)


# ---------------------------------------------------------------------------
# Stroke classifier tests
# ---------------------------------------------------------------------------


class TestClassifyStroke:
    """Tests for classify_stroke using median coordinate sequences."""

    def test_horizontal_stroke(self):
        # A stroke going mainly right — 橫
        median = [[100, 500], [300, 500], [500, 490]]
        assert classify_stroke(median) == StrokeType.HENG

    def test_vertical_stroke(self):
        # A stroke going mainly downward — 豎
        median = [[500, 100], [500, 300], [500, 600]]
        assert classify_stroke(median) == StrokeType.SHU

    def test_left_falling_stroke(self):
        # A stroke going left and down — 撇
        median = [[500, 100], [300, 400], [100, 600]]
        assert classify_stroke(median) == StrokeType.PIE

    def test_dot_short_stroke(self):
        # A very short stroke — 點
        median = [[400, 400], [420, 430]]
        assert classify_stroke(median) == StrokeType.DIAN

    def test_right_falling_stroke(self):
        # A stroke going right and down — 點/捺
        median = [[200, 100], [300, 300], [500, 600]]
        assert classify_stroke(median) == StrokeType.DIAN

    def test_turning_stroke(self):
        # A stroke with a significant direction change — 折
        # Goes right, then turns down
        median = [[100, 400], [300, 400], [500, 400], [500, 600], [500, 800]]
        assert classify_stroke(median) == StrokeType.ZHE

    def test_single_point_is_dot(self):
        # Degenerate: single point
        median = [[300, 300]]
        assert classify_stroke(median) == StrokeType.DIAN

    def test_result_always_in_valid_range(self):
        """Every classified stroke must be one of the 5 basic types (1-5)."""
        test_medians = [
            [[100, 500], [500, 500]],
            [[500, 100], [500, 600]],
            [[500, 100], [100, 600]],
            [[400, 400], [420, 430]],
            [[100, 400], [300, 400], [300, 700]],
        ]
        for median in test_medians:
            result = classify_stroke(median)
            assert 1 <= result <= 5, f"Stroke type {result} out of range for {median}"


# ---------------------------------------------------------------------------
# dictionary.txt parser tests
# ---------------------------------------------------------------------------


class TestParseDictionaryFile:
    """Tests for parse_dictionary_file."""

    def test_parse_valid_lines(self, tmp_path: Path):
        data = tmp_path / "dictionary.txt"
        lines = [
            json.dumps({
                "character": "字",
                "definition": "letter",
                "pinyin": ["zì"],
                "decomposition": "⿱宀子",
                "radical": "子",
                "matches": [],
            }),
            json.dumps({
                "character": "大",
                "definition": "big",
                "pinyin": ["dà"],
                "decomposition": "⿻一人",
                "radical": "大",
                "matches": [],
            }),
        ]
        data.write_text("\n".join(lines), encoding="utf-8")

        result = parse_dictionary_file(data)
        assert len(result) == 2
        assert "字" in result
        assert result["字"]["decomposition"] == "⿱宀子"
        assert result["字"]["radical"] == "子"
        assert result["大"]["pinyin"] == ["dà"]

    def test_skip_malformed_json(self, tmp_path: Path, caplog):
        data = tmp_path / "dictionary.txt"
        lines = [
            json.dumps({"character": "好", "pinyin": ["hǎo"], "decomposition": "", "radical": "女"}),
            "this is not json{{{",
            json.dumps({"character": "人", "pinyin": ["rén"], "decomposition": "", "radical": "人"}),
        ]
        data.write_text("\n".join(lines), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = parse_dictionary_file(data)

        assert len(result) == 2
        assert "好" in result
        assert "人" in result
        assert any("malformed JSON" in msg for msg in caplog.messages)

    def test_skip_missing_character_field(self, tmp_path: Path, caplog):
        data = tmp_path / "dictionary.txt"
        lines = [
            json.dumps({"definition": "no char field"}),
            json.dumps({"character": "中", "pinyin": ["zhōng"], "decomposition": "", "radical": "丨"}),
        ]
        data.write_text("\n".join(lines), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = parse_dictionary_file(data)

        assert len(result) == 1
        assert "中" in result
        assert any("missing or invalid" in msg for msg in caplog.messages)

    def test_empty_file(self, tmp_path: Path):
        data = tmp_path / "dictionary.txt"
        data.write_text("", encoding="utf-8")
        result = parse_dictionary_file(data)
        assert result == {}


# ---------------------------------------------------------------------------
# graphics.txt parser tests
# ---------------------------------------------------------------------------


class TestParseGraphicsFile:
    """Tests for parse_graphics_file."""

    def test_parse_valid_lines(self, tmp_path: Path):
        data = tmp_path / "graphics.txt"
        lines = [
            json.dumps({
                "character": "一",
                "strokes": ["M 100 500 L 800 500"],
                "medians": [[[100, 500], [800, 500]]],
            }),
        ]
        data.write_text("\n".join(lines), encoding="utf-8")

        result = parse_graphics_file(data)
        assert "一" in result
        assert len(result["一"]) == 1
        assert result["一"][0] == [[100, 500], [800, 500]]

    def test_skip_malformed_json(self, tmp_path: Path, caplog):
        data = tmp_path / "graphics.txt"
        lines = [
            "not valid json!!!",
            json.dumps({
                "character": "丨",
                "strokes": ["M 500 100 L 500 800"],
                "medians": [[[500, 100], [500, 800]]],
            }),
        ]
        data.write_text("\n".join(lines), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = parse_graphics_file(data)

        assert len(result) == 1
        assert "丨" in result

    def test_skip_missing_medians(self, tmp_path: Path, caplog):
        data = tmp_path / "graphics.txt"
        lines = [
            json.dumps({"character": "X", "strokes": ["M 0 0"]}),
            json.dumps({
                "character": "丿",
                "strokes": ["M 500 100 L 100 800"],
                "medians": [[[500, 100], [100, 800]]],
            }),
        ]
        data.write_text("\n".join(lines), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = parse_graphics_file(data)

        assert len(result) == 1
        assert "丿" in result


# ---------------------------------------------------------------------------
# Combined parser tests
# ---------------------------------------------------------------------------


class TestParseMakeMeAHanzi:
    """Tests for the combined parse_make_me_a_hanzi function."""

    def _write_files(self, tmp_path: Path, dict_lines: list[str], graph_lines: list[str]):
        dict_path = tmp_path / "dictionary.txt"
        graph_path = tmp_path / "graphics.txt"
        dict_path.write_text("\n".join(dict_lines), encoding="utf-8")
        graph_path.write_text("\n".join(graph_lines), encoding="utf-8")
        return dict_path, graph_path

    def test_produces_character_records(self, tmp_path: Path):
        dict_lines = [
            json.dumps({"character": "一", "pinyin": ["yī"], "decomposition": "", "radical": "一"}),
        ]
        graph_lines = [
            json.dumps({
                "character": "一",
                "strokes": ["M 100 500 L 800 500"],
                "medians": [[[100, 500], [800, 500]]],
            }),
        ]
        dict_path, graph_path = self._write_files(tmp_path, dict_lines, graph_lines)

        records = parse_make_me_a_hanzi(dict_path, graph_path)
        assert len(records) == 1
        assert records[0].character == "一"
        assert records[0].stroke_count == 1
        # Horizontal stroke → HENG (1)
        assert records[0].stroke_sequence == [StrokeType.HENG]

    def test_multi_stroke_character(self, tmp_path: Path):
        # "十" has 2 strokes: horizontal then vertical
        dict_lines = [
            json.dumps({"character": "十", "pinyin": ["shí"], "decomposition": "", "radical": "十"}),
        ]
        graph_lines = [
            json.dumps({
                "character": "十",
                "strokes": ["M ...", "M ..."],
                "medians": [
                    [[100, 500], [800, 500]],   # horizontal
                    [[450, 100], [450, 800]],   # vertical
                ],
            }),
        ]
        dict_path, graph_path = self._write_files(tmp_path, dict_lines, graph_lines)

        records = parse_make_me_a_hanzi(dict_path, graph_path)
        assert len(records) == 1
        assert records[0].character == "十"
        assert records[0].stroke_count == 2
        assert records[0].stroke_sequence[0] == StrokeType.HENG
        assert records[0].stroke_sequence[1] == StrokeType.SHU

    def test_character_in_graphics_but_not_dictionary(self, tmp_path: Path):
        """Characters with graphics data but no dictionary entry are still included."""
        dict_lines: list[str] = []
        graph_lines = [
            json.dumps({
                "character": "丶",
                "strokes": ["M ..."],
                "medians": [[[400, 400], [420, 430]]],
            }),
        ]
        dict_path, graph_path = self._write_files(tmp_path, dict_lines, graph_lines)

        records = parse_make_me_a_hanzi(dict_path, graph_path)
        assert len(records) == 1
        assert records[0].character == "丶"

    def test_character_in_dictionary_but_not_graphics_is_skipped(self, tmp_path: Path, caplog):
        """Characters without graphics data are skipped (no stroke info)."""
        dict_lines = [
            json.dumps({"character": "龍", "pinyin": ["lóng"], "decomposition": "", "radical": "龍"}),
        ]
        graph_lines: list[str] = []
        dict_path, graph_path = self._write_files(tmp_path, dict_lines, graph_lines)

        with caplog.at_level(logging.INFO):
            records = parse_make_me_a_hanzi(dict_path, graph_path)

        assert len(records) == 0

    def test_all_stroke_codes_in_valid_range(self, tmp_path: Path):
        """Every stroke in every record must be in range 1-5."""
        dict_lines = [
            json.dumps({"character": "字", "pinyin": ["zì"], "decomposition": "", "radical": "子"}),
        ]
        # Provide varied medians to exercise different classification paths
        graph_lines = [
            json.dumps({
                "character": "字",
                "strokes": ["M"] * 6,
                "medians": [
                    [[300, 200], [600, 200]],                          # horizontal
                    [[300, 200], [300, 200], [600, 200], [600, 500]],  # turning
                    [[200, 300], [700, 300]],                          # horizontal
                    [[450, 100], [450, 600]],                          # vertical
                    [[200, 400], [600, 400]],                          # horizontal
                    [[450, 400], [450, 800]],                          # vertical
                ],
            }),
        ]
        dict_path, graph_path = self._write_files(tmp_path, dict_lines, graph_lines)

        records = parse_make_me_a_hanzi(dict_path, graph_path)
        for rec in records:
            for code in rec.stroke_sequence:
                assert 1 <= code <= 5, f"Invalid stroke code {code} in {rec.character}"
