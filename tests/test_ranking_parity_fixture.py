"""Validate the Python↔JS ranking parity fixture.

Regenerate with: python scripts/generate_parity_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stroke_input.config.ranking import WEIGHT_STATIC_FREQ, to_chrome_dict
from stroke_input.data.models import CharacterRecord
from stroke_input.engine.frequency_ranker import (
    DEFAULT_WEIGHT_STATIC_FREQ,
    FrequencyRanker,
    RankerWeights,
)
from stroke_input.engine.inference_engine import ScoredCandidate

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "chrome-extension"
    / "test"
    / "fixtures"
    / "ranking_parity.json"
)


@pytest.fixture(scope="module")
def fixture() -> dict:
    assert FIXTURE.exists(), (
        f"Missing {FIXTURE}; run: python scripts/generate_parity_fixture.py"
    )
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_shared_config_matches_python_defaults() -> None:
    chrome = to_chrome_dict()
    assert chrome["weights"]["staticFreq"] == WEIGHT_STATIC_FREQ
    assert chrome["weights"]["staticFreq"] == DEFAULT_WEIGHT_STATIC_FREQ


def test_fixture_documents_alignment(fixture: dict) -> None:
    assert fixture["aligned"] is True
    assert fixture["python_weights"]["staticFreq"] == fixture["js_weights"]["staticFreq"]


def test_fixture_python_scores_match_ranker(fixture: dict) -> None:
    ranker = FrequencyRanker(
        weights=RankerWeights(
            static_freq=DEFAULT_WEIGHT_STATIC_FREQ,
            user_freq=0.0,
            context_boost=0.0,
            match_quality=0.0,
            trigram=0.0,
            recency=0.0,
            position=0.0,
        )
    )
    for case in fixture["cases"]:
        seq, char, freq, *rest = case["record"]
        script = "trad" if rest == ["t"] else ""
        rec = CharacterRecord(
            character=char,
            stroke_sequence=[int(d) for d in seq],
            frequency=freq,
            script_flag=script,
        )
        cand = ScoredCandidate(
            record=rec,
            is_exact=case["is_exact"],
            context_boost=case["context_boost"],
        )
        score = ranker.composite_score(cand)
        assert abs(score - case["python_score"]) < 1e-5, case["id"]
