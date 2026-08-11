#!/usr/bin/env python3
"""Generate a Python↔JS ranking parity fixture.

After T1.5, shared ranking_config.json aligns the weight constants.
JS still uses bigram/trigram tables while Python FrequencyRanker uses
phrase context_boost + optional ngram — score equality for full composites
may still differ; static-only cases should match when weights agree.

Usage:
    python scripts/generate_parity_fixture.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stroke_input.config.ranking import to_chrome_dict
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


def _case(
    char: str,
    seq: str,
    freq: float,
    *,
    is_exact: bool = True,
    context_boost: float = 0.0,
    script_flag: str = "",
) -> dict:
    rec = CharacterRecord(
        character=char,
        stroke_sequence=[int(d) for d in seq],
        frequency=freq,
        script_flag=script_flag,
    )
    cand = ScoredCandidate(record=rec, is_exact=is_exact, context_boost=context_boost)
    # Static-only weights for parity with JS computeScore({}, no context)
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
    py_score = ranker.composite_score(cand)
    return {
        "id": f"{char}-{seq}-exact{int(is_exact)}",
        "record": [seq, char, freq] + (["t"] if script_flag == "trad" else []),
        "is_exact": is_exact,
        "context_boost": context_boost,
        "python_score": round(py_score, 6),
        "notes": "Static-only Python score (user/context/trigram/recency/position off).",
    }


def main() -> None:
    chrome = to_chrome_dict()
    cases = [
        _case("一", "1", 0.9895),
        _case("係", "323554234", 0.99),
        _case("嘅", "25132511111535", 0.9853),
        _case("體", "1", 0.5, script_flag="trad"),
        _case("二", "11", 0.5, is_exact=False),
    ]

    aligned = abs(chrome["weights"]["staticFreq"] - DEFAULT_WEIGHT_STATIC_FREQ) < 1e-9

    fixture = {
        "version": 2,
        "aligned": aligned,
        "aligned_note": (
            "Weight constants come from stroke_input.config.ranking. "
            "Static-only scores should match when aligned=true."
        ),
        "python_weights": {
            "staticFreq": DEFAULT_WEIGHT_STATIC_FREQ,
            "userFreq": DEFAULT_WEIGHT_USER_FREQ,
            "contextBoost": DEFAULT_WEIGHT_CONTEXT_BOOST,
            "matchQuality": DEFAULT_WEIGHT_MATCH_QUALITY,
            "userFreqCap": chrome["userFreqCap"],
            "traditionalBoost": chrome["traditionalBoost"],
        },
        "js_weights": {
            **chrome["weights"],
            "userFreqCap": chrome["userFreqCap"],
        },
        "cases": cases,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(cases)} cases, aligned={aligned})")


if __name__ == "__main__":
    main()
