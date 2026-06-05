"""PhrasePredictor — beam-search multi-step phrase prediction.

Given a seed string (one or more characters the user has already typed) the
predictor extends the string step-by-step using a trigram/bigram language
model and returns the top-N predicted phrase continuations ranked by their
joint log-probability.

Algorithm (beam search)
-----------------------
1. Start with a single beam state: ``(seed, log_prob=0.0)``.
2. At each step, for every state in the current beam expand the next
   character by querying :meth:`NgramModel.score` for all characters in the
   model vocabulary.
3. Keep the top ``beam_width`` states ordered by cumulative log-prob.
4. Continue until ``max_depth`` extensions have been explored or the beam
   is empty.
5. Collect every state whose phrase is *longer* than the seed (i.e. at
   least one extension was added).  Return them sorted by score descending.

The language model uses the last two characters of each beam state as the
trigram context, ensuring the beam search stays coherent with the bigram /
trigram probabilities already learned from the phrase corpus.

Usage::

    ngram = NgramModel.build_from_phrases(phrase_entries)
    pred = PhrasePredictor(ngram, beam_width=5, max_depth=3)

    results = pred.predict("香")
    # -> [PredictedPhrase("香港", 0.72), PredictedPhrase("香港人", 0.41), ...]

    results = pred.continue_prediction("中文")
    # -> [PredictedPhrase("中文字", 0.55), PredictedPhrase("中文書", 0.38), ...]
"""

from __future__ import annotations

import heapq
import logging
import math
from dataclasses import dataclass
from typing import Optional

from stroke_input.data.ngram_model import NgramModel

logger = logging.getLogger(__name__)

# Default beam parameters
_DEFAULT_BEAM_WIDTH = 5
_DEFAULT_MAX_DEPTH = 3
_DEFAULT_MAX_RESULTS = 9

# Minimum probability for a character to be considered during expansion.
# Characters whose P(c | context) falls below this threshold are skipped
# to keep the vocabulary expansion tractable.
_MIN_EXPAND_PROB = 1e-5


@dataclass
class PredictedPhrase:
    """A predicted phrase continuation.

    Attributes:
        phrase: The full phrase string (includes the original seed).
        score: Geometric-mean probability (exp of average log-prob per step).
               Higher is better.  In range (0, 1].
    """

    phrase: str
    score: float


class PhrasePredictor:
    """Beam-search phrase predictor backed by an NgramModel.

    Args:
        ngram_model: A fitted NgramModel.
        beam_width: Maximum beam states per step (default 5).
        max_depth: Maximum extension depth beyond the seed (default 3).
    """

    def __init__(
        self,
        ngram_model: NgramModel,
        beam_width: int = _DEFAULT_BEAM_WIDTH,
        max_depth: int = _DEFAULT_MAX_DEPTH,
    ) -> None:
        self._ngram = ngram_model
        self._beam_width = beam_width
        self._max_depth = max_depth

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(
        self,
        seed: str,
        max_results: int = _DEFAULT_MAX_RESULTS,
        max_depth: Optional[int] = None,
    ) -> list[PredictedPhrase]:
        """Predict phrase continuations starting from *seed*.

        Args:
            seed: A string of one or more characters already committed.
                  Must be non-empty.
            max_results: Maximum number of results to return.
            max_depth: Override the predictor's default max_depth.

        Returns:
            List of :class:`PredictedPhrase` sorted by score descending,
            containing at most *max_results* entries.  Each phrase starts
            with *seed*.  Returns ``[]`` if *seed* is empty.
        """
        if not seed:
            return []

        depth = max_depth if max_depth is not None else self._max_depth
        all_results = self._beam_search(seed, depth)

        # Sort by score descending and deduplicate
        seen: set[str] = set()
        unique: list[PredictedPhrase] = []
        for p in sorted(all_results, key=lambda x: x.score, reverse=True):
            if p.phrase not in seen:
                seen.add(p.phrase)
                unique.append(p)
            if len(unique) >= max_results:
                break

        return unique

    def continue_prediction(
        self,
        committed_text: str,
        max_results: int = _DEFAULT_MAX_RESULTS,
    ) -> list[PredictedPhrase]:
        """Continue prediction from an already-committed text string.

        Equivalent to ``predict(committed_text)`` but explicitly named for
        the use-case where the user has committed multiple characters and
        wants phrase-completion suggestions.

        Args:
            committed_text: The text already committed (one or more chars).

        Returns:
            Same as :meth:`predict`.  Returns ``[]`` if *committed_text* is
            empty.
        """
        return self.predict(committed_text, max_results=max_results)

    # ------------------------------------------------------------------
    # Internal beam search
    # ------------------------------------------------------------------

    def _beam_search(self, seed: str, max_depth: int) -> list[PredictedPhrase]:
        """Run beam search for *max_depth* steps from *seed*.

        Returns all states (longer than seed) discovered during the search.

        Beam state: ``(neg_log_prob_sum, step_count, phrase_str)``
        Uses a min-heap (Python's heapq) keyed by neg_log_prob (so the
        smallest neg value → highest probability sits at the top).
        """
        vocab = list(self._ngram._vocab)
        if not vocab:
            return []

        # Each beam entry: (neg_log_prob_total, steps, phrase)
        # neg_log_prob_total is the sum of -log(p) for each extension step
        beam: list[tuple[float, int, str]] = [(0.0, 0, seed)]

        collected: list[PredictedPhrase] = []

        for _step in range(max_depth):
            if not beam:
                break

            candidates: list[tuple[float, int, str]] = []

            for neg_lp_total, steps, phrase in beam:
                prev2 = phrase[-2] if len(phrase) >= 2 else None
                prev1 = phrase[-1] if phrase else None

                for char in vocab:
                    p = self._ngram.score(char, prev1=prev1, prev2=prev2)
                    if p < _MIN_EXPAND_PROB:
                        continue
                    new_neg_lp = neg_lp_total + (-math.log(p))
                    new_phrase = phrase + char
                    candidates.append((new_neg_lp, steps + 1, new_phrase))

            if not candidates:
                break

            # Keep top beam_width by neg_log_prob (lower = better)
            beam = heapq.nsmallest(self._beam_width, candidates, key=lambda x: x[0])

            # Collect all states extended beyond seed
            for neg_lp, steps, phrase in beam:
                if len(phrase) > len(seed):
                    # Score = geometric mean probability per step
                    avg_log_prob = -neg_lp / steps
                    score = math.exp(avg_log_prob)
                    collected.append(PredictedPhrase(phrase=phrase, score=score))

        return collected
