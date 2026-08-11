"""Core data models for the stroke input method.

Defines the fundamental data structures: stroke types, character records,
phrase entries, and key mapping constants.
"""

from dataclasses import dataclass, field
from enum import IntEnum


class StrokeType(IntEnum):
    """Five basic stroke types plus wildcard, matching macOS Stroke - Traditional."""

    HENG = 1      # 橫 (一) Horizontal
    SHU = 2       # 豎 (丨) Vertical
    PIE = 3       # 撇 (丿) Left-falling
    DIAN = 4      # 點 (丶) Dot / Right-falling
    ZHE = 5       # 折 (乛) Hook / Turning
    WILDCARD = 6  # 萬用 (*) Wildcard — matches any stroke


# Stroke display symbols for visual representation in the candidate list
STROKE_SYMBOLS: dict[int, str] = {
    StrokeType.HENG: "一",
    StrokeType.SHU: "丨",
    StrokeType.PIE: "丿",
    StrokeType.DIAN: "丶",
    StrokeType.ZHE: "乙",
    StrokeType.WILDCARD: "＊",
}


# Key mapping: macOS Stroke - Traditional layout
# Maps keyboard key characters to internal stroke codes
KEY_TO_STROKE: dict[str, int] = {
    "j": StrokeType.HENG,      # J → 橫(1)
    "k": StrokeType.SHU,       # K → 豎(2)
    "l": StrokeType.PIE,       # L → 撇(3)
    "u": StrokeType.DIAN,      # U → 點(4)
    "i": StrokeType.ZHE,       # I → 折(5)
    "o": StrokeType.WILDCARD,  # O → 萬用(6)
}

# Reverse mapping: stroke code to key character
STROKE_TO_KEY: dict[int, str] = {v: k for k, v in KEY_TO_STROKE.items()}

# Stroke name labels (Traditional Chinese)
STROKE_NAMES: dict[int, str] = {
    StrokeType.HENG: "橫",
    StrokeType.SHU: "豎",
    StrokeType.PIE: "撇",
    StrokeType.DIAN: "點",
    StrokeType.ZHE: "折",
    StrokeType.WILDCARD: "萬用",
}


@dataclass
class CharacterRecord:
    """A single character entry in the stroke database.

    Attributes:
        character: The Chinese character (single char).
        stroke_sequence: Ordered list of stroke codes (1-5) representing the writing order.
        stroke_count: Total number of strokes (len of stroke_sequence).
        frequency: Usage frequency score (higher = more common).
        script_flag: Conway script marker — ``""`` (shared), ``"trad"`` (^),
            or ``"simp"`` (*).
    """

    character: str
    stroke_sequence: list[int] = field(default_factory=list)
    stroke_count: int = 0
    frequency: float = 0.0
    script_flag: str = ""

    def __post_init__(self) -> None:
        if self.stroke_count == 0 and self.stroke_sequence:
            self.stroke_count = len(self.stroke_sequence)
        if self.script_flag not in ("", "trad", "simp"):
            raise ValueError(f"invalid script_flag: {self.script_flag!r}")


@dataclass
class PhraseEntry:
    """A multi-character phrase or word entry.

    Attributes:
        phrase: The phrase string (two or more characters).
        frequency: Usage frequency score (higher = more common).
    """

    phrase: str
    frequency: float = 0.0
