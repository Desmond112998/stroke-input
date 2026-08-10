#!/usr/bin/env python3
"""Generate a Python↔JS ranking parity fixture.

Writes chrome-extension/test/fixtures/ranking_parity.json describing:
- Python FrequencyRanker default composite scores for fixed candidates
- The JS runtime weight constants (for documentation / future alignment)

Until T1.5 (shared ranking_config.json), JS and Python weights diverge.
The JS parity test documents that drift and is marked todo until aligned.

Usage:
    python scripts/generate_parity_fixture.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stroke_input.data.models import CharacterRecord
from stroke_input.engine.frequency_ranker import (
    DEFAULT_WEIGHT_CONTEXT_BOOST,
    DEFAULT_WEIGHT_MATCH_QUALITY,
    DEFAULT_WEIGHT_STATIC_FREQ,
    DEFAULT_WEIGHT_USER_FREQ,
    FrequencyRanker,
    RankerWeights,
)
from stroke_input.engine.inference_engine import ScoredCandidate

OUT = ROOT / "chrome-extension" / "test" / "fixtures" / "ranking_parity.json"

# Documented JS runtime weights (chrome-extension/engine.js DEFAULT_WEIGHTS)
JS_WEIGHTS = {
    "staticFreq": 0.30,
    "userFreq": 0.25,
    "bigram": 0.15,
    "trigram": 0.15,
    "recency": 0.10,
    "position": 0.05,
    "userFreqCap": 50,
}

PYTHON_WEIGHTS = {
    "staticFreq": DEFAULT_WEIGHT_STATIC_FREQ,
    "userFreq": DEFAULT_WEIGHT_USER_FREQ,
    "contextBoost": DEFAULT_WEIGHT_CONTEXT_BOOST,
    "matchQuality": DEFAULT_WEIGHT_MATCH_QUALITY,
    "trigram": 0.0,
    "recency": 0.0,
    "position": 0.0,
    "userFreqCap": 100,
    "traditionalBoost": 0.05,
}


def _case(
    char: str,
    seq: str,
    freq: float,
    *,
    is_exact: bool = True,
    context_boost: float = 0.0,
) -> dict:
    rec = CharacterRecord(
        character=char,
        stroke_sequence=[int(d) for d in seq],
        frequency=freq,
    )
    cand = ScoredCandidate(record=rec, is_exact=is_exact, context_boost=context_boost)
    ranker = FrequencyRanker(weights=RankerWeights())
    py_score = ranker.composite_score(cand)
    return {
        "id": f"{char}-{seq}-exact{int(is_exact)}",
        "record": [seq, char, freq],
        "is_exact": is_exact,
        "context_boost": context_boost,
        "python_score": round(py_score, 6),
        "notes": (
            "Python default ranker: static/user/context/match_quality only; "
            "optional trigram/recency/position weights are 0."
        ),
    }


def main() -> None:
    cases = [
        _case("一", "1", 0.9895),
        _case("係", "323554234", 0.99),
        _case("嘅", "25132511111535", 0.9853),
        _case("二", "11", 0.5, is_exact=False, context_boost=0.0),
        _case("港", "44111215", 0.8, context_boost=0.9),
    ]

    fixture = {
        "version": 1,
        "aligned": False,
        "aligned_note": (
            "JS and Python ranking weights currently diverge. "
            "Set aligned=true after T1.5 (shared ranking_config.json)."
        ),
        "python_weights": PYTHON_WEIGHTS,
        "js_weights": JS_WEIGHTS,
        "cases": cases,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(cases)} cases)")
    print(f"  Python weights: {PYTHON_WEIGHTS}")
    print(f"  JS weights:     {JS_WEIGHTS}")
    print(f"  aligned={fixture['aligned']}")


if __name__ == "__main__":
    main()
