"""Make Me a Hanzi data parser.

Parses dictionary.txt and graphics.txt from the Make Me a Hanzi dataset,
classifies strokes from median coordinate sequences, and produces
CharacterRecord objects with stroke sequences.

Data format reference:
- dictionary.txt: JSON lines with character, definition, pinyin, decomposition, radical, matches
- graphics.txt: JSON lines with character, strokes (SVG paths), medians (coordinate sequences)
"""

import json
import logging
import math
from pathlib import Path
from typing import Any

from stroke_input.data.models import CharacterRecord, StrokeType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stroke classification from median coordinates
# ---------------------------------------------------------------------------

def _angle_deg(dx: float, dy: float) -> float:
    """Return the angle in degrees of a vector (dx, dy).

    Note: In Make Me a Hanzi coordinate system, y increases downward,
    so positive dy means the stroke goes downward on screen.
    """
    return math.degrees(math.atan2(dy, dx))


def _segment_angles(median: list[list[int | float]]) -> list[float]:
    """Compute the angle (degrees) of each segment between consecutive points."""
    angles: list[float] = []
    for i in range(len(median) - 1):
        dx = median[i + 1][0] - median[i][0]
        dy = median[i + 1][1] - median[i][1]
        angles.append(_angle_deg(dx, dy))
    return angles


def _has_significant_turn(angles: list[float], threshold: float = 60.0) -> bool:
    """Check if there is a significant direction change between consecutive segments."""
    for i in range(len(angles) - 1):
        diff = abs(angles[i + 1] - angles[i])
        # Normalize to [0, 180]
        if diff > 180:
            diff = 360 - diff
        if diff >= threshold:
            return True
    return False


def _stroke_length(median: list[list[int | float]]) -> float:
    """Compute the total path length of a median."""
    total = 0.0
    for i in range(len(median) - 1):
        dx = median[i + 1][0] - median[i][0]
        dy = median[i + 1][1] - median[i][1]
        total += math.hypot(dx, dy)
    return total


def classify_stroke(median: list[list[int | float]]) -> StrokeType:
    """Classify a single stroke from its median coordinate sequence.

    The classification uses the overall direction (start→end) and checks
    for significant turning points to distinguish the five basic types:
      橫(1): mainly horizontal (large |Δx|, small |Δy|)
      豎(2): mainly vertical (large |Δy|, small |Δx|)
      撇(3): left-falling (negative Δx, positive Δy — goes left and down)
      點(4): short stroke or right-falling (positive Δx, positive Δy)
      折(5): direction has significant turning (multi-segment direction changes)

    Args:
        median: List of [x, y] coordinate points along the stroke midline.

    Returns:
        One of StrokeType.HENG/SHU/PIE/DIAN/ZHE (values 1-5).
    """
    if len(median) < 2:
        # Degenerate stroke — treat as dot
        return StrokeType.DIAN

    # Check for turning first — if there's a significant direction change,
    # classify as 折 (ZHE / turning stroke)
    angles = _segment_angles(median)
    if len(angles) >= 2 and _has_significant_turn(angles):
        return StrokeType.ZHE

    # Use overall start→end direction for the remaining four types
    start = median[0]
    end = median[-1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    abs_dx = abs(dx)
    abs_dy = abs(dy)

    # Short strokes are classified as 點 (dot)
    length = _stroke_length(median)
    if length < 80:
        return StrokeType.DIAN

    # Determine dominant direction
    # In Make Me a Hanzi coords: x increases right, y increases downward
    if abs_dx > abs_dy:
        # Primarily horizontal
        if dx < 0 and abs_dy > 0 and dy > 0:
            # Going left and down — left-falling 撇
            return StrokeType.PIE
        # Otherwise horizontal 橫
        return StrokeType.HENG
    else:
        # Primarily vertical
        if dx < 0 and dy > 0:
            # Going left and down — left-falling 撇
            return StrokeType.PIE
        if dx > 0 and dy > 0:
            # Going right and down — dot/right-falling 點
            return StrokeType.DIAN
        # Straight down or up — vertical 豎
        return StrokeType.SHU


# ---------------------------------------------------------------------------
# dictionary.txt parser
# ---------------------------------------------------------------------------

def parse_dictionary_file(path: Path) -> dict[str, dict[str, Any]]:
    """Parse Make Me a Hanzi dictionary.txt into a dict keyed by character.

    Each line is a JSON object with fields: character, definition, pinyin,
    decomposition, radical, matches.

    Args:
        path: Path to dictionary.txt.

    Returns:
        Dict mapping character → parsed dict with keys:
        character, decomposition, radical, pinyin.
    """
    records: dict[str, dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(
                    "dictionary.txt line %d: malformed JSON — %s", line_num, e
                )
                continue

            char = data.get("character")
            if not char or not isinstance(char, str):
                logger.warning(
                    "dictionary.txt line %d: missing or invalid 'character' field",
                    line_num,
                )
                continue

            records[char] = {
                "character": char,
                "decomposition": data.get("decomposition", ""),
                "radical": data.get("radical", ""),
                "pinyin": data.get("pinyin", []),
            }
    return records


# ---------------------------------------------------------------------------
# graphics.txt parser
# ---------------------------------------------------------------------------

def parse_graphics_file(path: Path) -> dict[str, list[list[list[int | float]]]]:
    """Parse Make Me a Hanzi graphics.txt to extract medians per character.

    Each line is a JSON object with fields: character, strokes, medians.
    The medians field contains a list of stroke medians, where each median
    is a list of [x, y] coordinate points.

    Args:
        path: Path to graphics.txt.

    Returns:
        Dict mapping character → list of medians (each median is a list of [x,y] points).
    """
    result: dict[str, list[list[list[int | float]]]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(
                    "graphics.txt line %d: malformed JSON — %s", line_num, e
                )
                continue

            char = data.get("character")
            if not char or not isinstance(char, str):
                logger.warning(
                    "graphics.txt line %d: missing or invalid 'character' field",
                    line_num,
                )
                continue

            medians = data.get("medians")
            if not medians or not isinstance(medians, list):
                logger.warning(
                    "graphics.txt line %d: missing or invalid 'medians' field for '%s'",
                    line_num,
                    char,
                )
                continue

            result[char] = medians
    return result


# ---------------------------------------------------------------------------
# Combined parser: dictionary + graphics → CharacterRecord list
# ---------------------------------------------------------------------------

def parse_make_me_a_hanzi(
    dictionary_path: Path,
    graphics_path: Path,
) -> list[CharacterRecord]:
    """Parse Make Me a Hanzi data files and produce CharacterRecord objects.

    Combines dictionary.txt (character metadata) with graphics.txt (stroke
    medians) to classify each stroke and build complete records.

    Characters present in graphics.txt but missing from dictionary.txt are
    still included (with empty metadata). Characters in dictionary.txt but
    missing from graphics.txt are skipped (no stroke data available).

    Args:
        dictionary_path: Path to dictionary.txt.
        graphics_path: Path to graphics.txt.

    Returns:
        List of CharacterRecord with classified stroke sequences.
    """
    dict_data = parse_dictionary_file(dictionary_path)
    graphics_data = parse_graphics_file(graphics_path)

    records: list[CharacterRecord] = []

    for char, medians in graphics_data.items():
        stroke_sequence: list[int] = []
        for median in medians:
            stroke_type = classify_stroke(median)
            stroke_sequence.append(int(stroke_type))

        record = CharacterRecord(
            character=char,
            stroke_sequence=stroke_sequence,
            frequency=0.0,  # frequency will be set later by frequency ranker
        )
        records.append(record)

    # Log characters in dictionary but not in graphics
    dict_only = set(dict_data.keys()) - set(graphics_data.keys())
    if dict_only:
        logger.info(
            "%d characters in dictionary.txt but not in graphics.txt (no stroke data)",
            len(dict_only),
        )

    return records
