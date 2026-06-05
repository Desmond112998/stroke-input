"""Export helpers for the Chrome extension's trigram and bigram data files.

Converts an :class:`NgramModel` into compact JSON-serializable dicts
suitable for use in ``chrome-extension/data/trigrams.json`` and
``chrome-extension/data/bigrams.json``.

Export formats
--------------
**trigrams.json** (written by :func:`export_trigrams_for_chrome`)::

    {
        "<prev2>": {
            "<prev1>": {
                "<char>": <score: float 0-1>,
                ...
            },
            ...
        },
        ...
    }

**bigrams.json** (written by :func:`export_bigrams_for_chrome`)::

    {
        "<prev>": {
            "<char>": <score: float 0-1>,
            ...
        },
        ...
    }

Scores are add-k smoothed conditional probabilities derived from the
NgramModel's internal counts.  Entries with raw count below ``min_count``
are omitted to keep file sizes manageable.
"""

from __future__ import annotations

import logging

from stroke_input.data.ngram_model import NgramModel

logger = logging.getLogger(__name__)


def export_trigrams_for_chrome(
    model: NgramModel,
    min_count: int = 1,
) -> dict[str, dict[str, dict[str, float]]]:
    """Export trigram conditional probabilities as a nested dict.

    Only trigram contexts whose raw count meets *min_count* are exported.
    All scores are add-k smoothed probabilities in (0, 1].

    Args:
        model: A fitted NgramModel.
        min_count: Minimum raw trigram count to include.  Default 1 (all).

    Returns:
        Nested dict ``{prev2: {prev1: {char: score}}}``.
    """
    result: dict[str, dict[str, dict[str, float]]] = {}

    for prev2, bi_ctx in model._tri.items():
        for prev1, char_counts in bi_ctx.items():
            for char, count in char_counts.items():
                if count < min_count:
                    continue
                score = round(model.trigram_score(prev2, prev1, char), 6)
                if prev2 not in result:
                    result[prev2] = {}
                if prev1 not in result[prev2]:
                    result[prev2][prev1] = {}
                result[prev2][prev1][char] = score

    logger.info(
        "Exported %d trigram contexts",
        sum(len(bi) for bi in result.values()),
    )
    return result


def export_bigrams_for_chrome(
    model: NgramModel,
    min_count: int = 1,
) -> dict[str, dict[str, float]]:
    """Export bigram conditional probabilities as a nested dict.

    Designed to replace or supplement the existing ``bigrams.json`` with
    model-derived smoothed probabilities instead of raw co-occurrence scores.

    Args:
        model: A fitted NgramModel.
        min_count: Minimum raw bigram count to include.  Default 1 (all).

    Returns:
        Nested dict ``{prev: {char: score}}``.
    """
    result: dict[str, dict[str, float]] = {}

    for prev, char_counts in model._bi.items():
        for char, count in char_counts.items():
            if count < min_count:
                continue
            score = round(model.bigram_score(prev, char), 6)
            if prev not in result:
                result[prev] = {}
            result[prev][char] = score

    logger.info(
        "Exported %d bigram contexts for Chrome",
        len(result),
    )
    return result
