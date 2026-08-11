"""Shared ranking configuration — single source of truth for Python and JS.

Exported to ``chrome-extension/data/ranking_config.json`` by
``scripts/export_for_chrome.py``. Keep these numbers explainable; changes
are user-visible and must update tests/docs.
"""

from __future__ import annotations

from typing import Any

# Composite score weights (must sum ~1.0 excluding traditionalBoost).
# After T1.1, bigram/trigram JSON scores are both add-k smoothed probabilities
# on the same scale, so trigram is no longer drowned out by max-normalized bigrams.
WEIGHT_STATIC_FREQ = 0.35
WEIGHT_USER_FREQ = 0.20
WEIGHT_BIGRAM = 0.15       # JS bigram table / Python phrase context_boost peer
WEIGHT_TRIGRAM = 0.15
WEIGHT_RECENCY = 0.10
WEIGHT_POSITION = 0.05
# Match quality is applied in Python InferenceEngine path; JS enables it when fuzzy lands (T2.2).
WEIGHT_MATCH_QUALITY = 0.10  # documented for Python RankerWeights parity; not in JS sum until fuzzy
# Prefer characters whose full stroke length is close to the typed prefix.
# Exact complete matches (len(seq) == len(prefix)) score 1.0; longer chars decay.
# Additive outside the ~1.0 weight sum (same pattern as traditionalBoost).
WEIGHT_STROKE_PROXIMITY = 0.40
STROKE_PROXIMITY_PARTIAL = 0.35  # scale for incomplete (extra strokes remain)

USER_FREQ_CAP = 100.0
RECENCY_TAU_DAYS = 30.0
# Tie-breaker only — 0.05 previously outranked ~0.14 of static frequency.
TRADITIONAL_BOOST = 0.01
MATCH_QUALITY_EXACT = 1.0
MATCH_QUALITY_FUZZY = 0.5
TRIGRAM_BADGE_MIN_CONTRIBUTION = 0.02

# Zipf–Mandelbrot ranking → frequency mapping (download_stroke_data.parse_ranking)
# freq_i = (1 / (i + ZIPF_S) ** ZIPF_A) / max_raw, floored at ZIPF_FLOOR
ZIPF_S = 1.0
ZIPF_A = 1.0
ZIPF_FLOOR = 0.01

# Ngram count weighting: each PhraseEntry contributes
# max(1, 1 + round(frequency * NGRAM_FREQ_WEIGHT_K)) to raw counts.
NGRAM_FREQ_WEIGHT_K = 10.0


def to_chrome_dict() -> dict[str, Any]:
    """JSON-serializable config consumed by chrome-extension/engine.js."""
    return {
        "version": 1,
        "weights": {
            "staticFreq": WEIGHT_STATIC_FREQ,
            "userFreq": WEIGHT_USER_FREQ,
            "bigram": WEIGHT_BIGRAM,
            "trigram": WEIGHT_TRIGRAM,
            "recency": WEIGHT_RECENCY,
            "position": WEIGHT_POSITION,
        },
        "userFreqCap": USER_FREQ_CAP,
        "recencyTauDays": RECENCY_TAU_DAYS,
        "traditionalBoost": TRADITIONAL_BOOST,
        "weightStrokeProximity": WEIGHT_STROKE_PROXIMITY,
        "strokeProximityPartial": STROKE_PROXIMITY_PARTIAL,
        "weightMatchQuality": WEIGHT_MATCH_QUALITY,
        "matchQualityExact": MATCH_QUALITY_EXACT,
        "matchQualityFuzzy": MATCH_QUALITY_FUZZY,
        "trigramBadgeMinContribution": TRIGRAM_BADGE_MIN_CONTRIBUTION,
    }
