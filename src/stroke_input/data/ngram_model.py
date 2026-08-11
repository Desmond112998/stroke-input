"""NgramModel — character-level unigram/bigram/trigram language model.

Builds from a list of PhraseEntry objects extracted from a phrase corpus.
Uses add-k (Laplace) smoothing with Jelinek-Mercer linear interpolation to
compute P(char | prev1, prev2) for candidate re-ranking.

Interpolation weights (trigram context available):
    score = λ3·P(c|p2,p1) + λ2·P(c|p1) + λ1·P(c)
    λ3=0.60, λ2=0.30, λ1=0.10

Bigram context only:
    score = λ2·P(c|p1) + λ1·P(c)
    λ2=0.70, λ1=0.30

No context:
    score = P(c)    (add-k smoothed unigram)

All probabilities are add-k smoothed so that unseen n-grams always return
a small positive value.
"""

from __future__ import annotations

import logging
from typing import Any

from stroke_input.config.ranking import NGRAM_FREQ_WEIGHT_K
from stroke_input.data.models import PhraseEntry

logger = logging.getLogger(__name__)

# Jelinek-Mercer interpolation weights
_LAMBDA_TRI = (0.10, 0.30, 0.60)   # (unigram, bigram, trigram)
_LAMBDA_BI = (0.30, 0.70)           # (unigram, bigram)

# Default add-k smoothing constant
_DEFAULT_K = 0.1


def _phrase_count_weight(frequency: float, k: float = NGRAM_FREQ_WEIGHT_K) -> int:
    """Map a PhraseEntry.frequency in [0, 1] to a positive integer count.

    Formula (documented for ranking honesty):
        weight = max(1, 1 + round(frequency * k))

    With default k=10, a freq=0.8 phrase contributes 9 counts; freq=0
    still contributes 1 so rare phrases are not dropped entirely.
    """
    return max(1, 1 + int(round(float(frequency) * k)))


class NgramModel:
    """Character-level n-gram language model (unigram / bigram / trigram).

    Build using the class method::

        model = NgramModel.build_from_phrases(phrase_entries)

    Query using the unified API::

        p = model.score("字", prev1="文", prev2="中")

    Or component APIs::

        model.unigram_score("字")
        model.bigram_score("文", "字")
        model.trigram_score("中", "文", "字")

    Serialize / deserialize::

        data = model.to_dict()
        model2 = NgramModel.from_dict(data)
    """

    def __init__(self, k: float = _DEFAULT_K) -> None:
        self._k = k
        # Raw counts
        self._uni: dict[str, int] = {}       # char → count
        self._bi: dict[str, dict[str, int]] = {}   # prev → {char: count}
        self._tri: dict[str, dict[str, dict[str, int]]] = {}  # p2 → {p1 → {c: count}}
        self._uni_total: int = 0
        self._vocab: set[str] = set()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def build_from_phrases(
        cls,
        phrases: list[PhraseEntry],
        k: float = _DEFAULT_K,
    ) -> NgramModel:
        """Build an NgramModel by counting n-grams across all phrase texts.

        Each phrase contributes ``max(1, 1 + round(frequency * k))`` to the
        raw counts (see :func:`_phrase_count_weight`), so higher-frequency
        phrases influence the LM more than length-heuristic fillers.

        Single-character phrases contribute only unigram counts.
        Two-character phrases add bigrams.
        Three-or-more character phrases add bigrams and trigrams for each
        consecutive triple.

        Args:
            phrases: List of PhraseEntry objects (phrase text + frequency).
            k: Add-k smoothing constant (default 0.1).

        Returns:
            A fitted NgramModel.
        """
        model = cls(k=k)
        for entry in phrases:
            text = entry.phrase
            if not text:
                continue
            w = _phrase_count_weight(entry.frequency)
            # Unigrams
            for ch in text:
                model._uni[ch] = model._uni.get(ch, 0) + w
                model._uni_total += w
                model._vocab.add(ch)
            # Bigrams
            for i in range(1, len(text)):
                p1, c = text[i - 1], text[i]
                if p1 not in model._bi:
                    model._bi[p1] = {}
                model._bi[p1][c] = model._bi[p1].get(c, 0) + w
            # Trigrams
            for i in range(2, len(text)):
                p2, p1, c = text[i - 2], text[i - 1], text[i]
                if p2 not in model._tri:
                    model._tri[p2] = {}
                if p1 not in model._tri[p2]:
                    model._tri[p2][p1] = {}
                model._tri[p2][p1][c] = model._tri[p2][p1].get(c, 0) + w

        logger.info(
            "NgramModel built: vocab=%d, unigram_total=%d, bigram_contexts=%d, "
            "trigram_contexts=%d",
            len(model._vocab),
            model._uni_total,
            len(model._bi),
            len(model._tri),
        )
        return model

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def vocab_size(self) -> int:
        """Number of unique characters seen during training."""
        return len(self._vocab)

    @property
    def k(self) -> float:
        """Add-k smoothing constant."""
        return self._k

    # ------------------------------------------------------------------
    # Raw count accessors (for testing / inspection)
    # ------------------------------------------------------------------

    def unigram_count(self, char: str) -> int:
        """Raw unigram count for *char*."""
        return self._uni.get(char, 0)

    def bigram_count(self, prev: str, char: str) -> int:
        """Raw bigram count for the pair (prev, char)."""
        return self._bi.get(prev, {}).get(char, 0)

    def trigram_count(self, prev2: str, prev1: str, char: str) -> int:
        """Raw trigram count for the triple (prev2, prev1, char)."""
        return self._tri.get(prev2, {}).get(prev1, {}).get(char, 0)

    # ------------------------------------------------------------------
    # Smoothed probability estimates
    # ------------------------------------------------------------------

    def unigram_score(self, char: str) -> float:
        """Add-k smoothed unigram probability P_k(char).

        Uses a virtual vocabulary size of max(vocab_size, 1) to ensure the
        denominator is always positive even with an empty model.

        Returns:
            Probability in (0, 1].
        """
        v = max(self.vocab_size, 1)
        count = self._uni.get(char, 0)
        return (count + self._k) / (self._uni_total + self._k * v)

    def bigram_score(self, prev: str, char: str) -> float:
        """Add-k smoothed bigram probability P_k(char | prev).

        Falls back to ``unigram_score`` if *prev* was never seen as a
        first element of a bigram (i.e. it never appeared in non-final
        position in any phrase).

        Returns:
            Probability in (0, 1].
        """
        v = max(self.vocab_size, 1)
        context_counts = self._bi.get(prev)
        if context_counts is None:
            # Unknown context — interpolate fully with unigram
            return self.unigram_score(char)
        context_total = sum(context_counts.values())
        count = context_counts.get(char, 0)
        return (count + self._k) / (context_total + self._k * v)

    def trigram_score(self, prev2: str, prev1: str, char: str) -> float:
        """Add-k smoothed trigram probability P_k(char | prev2, prev1).

        Falls back to ``bigram_score(prev1, char)`` when the (prev2, prev1)
        context has never been seen.

        Returns:
            Probability in (0, 1].
        """
        v = max(self.vocab_size, 1)
        bi_ctx = self._tri.get(prev2)
        if bi_ctx is None:
            return self.bigram_score(prev1, char)
        context_counts = bi_ctx.get(prev1)
        if context_counts is None:
            return self.bigram_score(prev1, char)
        context_total = sum(context_counts.values())
        count = context_counts.get(char, 0)
        return (count + self._k) / (context_total + self._k * v)

    # ------------------------------------------------------------------
    # Unified interpolated score
    # ------------------------------------------------------------------

    def score(
        self,
        char: str,
        prev1: str | None = None,
        prev2: str | None = None,
    ) -> float:
        """Jelinek-Mercer interpolated score for P(char | context).

        Args:
            char: The character to score.
            prev1: The immediately preceding character (or None).
            prev2: The character before prev1 (or None).  Only used when
                   prev1 is also provided.

        Returns:
            Interpolated probability in (0, 1].
        """
        p_uni = self.unigram_score(char)

        if prev1 is None:
            return p_uni

        p_bi = self.bigram_score(prev1, char)

        if prev2 is None:
            lam_uni, lam_bi = _LAMBDA_BI
            return lam_uni * p_uni + lam_bi * p_bi

        p_tri = self.trigram_score(prev2, prev1, char)
        lam_uni, lam_bi, lam_tri = _LAMBDA_TRI
        return lam_uni * p_uni + lam_bi * p_bi + lam_tri * p_tri

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the model to a plain-Python dict (JSON-compatible).

        Returns:
            Dict with keys ``k``, ``uni``, ``bi``, ``tri``, ``uni_total``,
            and ``vocab`` for full round-trip fidelity.
        """
        return {
            "k": self._k,
            "uni_total": self._uni_total,
            "vocab": sorted(self._vocab),
            "uni": dict(self._uni),
            "bi": {p: dict(chars) for p, chars in self._bi.items()},
            "tri": {
                p2: {p1: dict(chars) for p1, chars in bi_ctx.items()}
                for p2, bi_ctx in self._tri.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NgramModel:
        """Deserialize a model previously produced by :meth:`to_dict`.

        Args:
            data: Dict produced by ``to_dict()``.

        Returns:
            A reconstructed NgramModel.
        """
        model = cls(k=float(data.get("k", _DEFAULT_K)))
        model._uni_total = int(data.get("uni_total", 0))
        model._vocab = set(data.get("vocab", []))
        model._uni = {k: int(v) for k, v in data.get("uni", {}).items()}
        model._bi = {
            p: {c: int(n) for c, n in chars.items()}
            for p, chars in data.get("bi", {}).items()
        }
        model._tri = {
            p2: {
                p1: {c: int(n) for c, n in chars.items()}
                for p1, chars in bi_ctx.items()
            }
            for p2, bi_ctx in data.get("tri", {}).items()
        }
        return model
