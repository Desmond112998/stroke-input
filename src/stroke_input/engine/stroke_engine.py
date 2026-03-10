"""StrokeEngine: core prefix-matching engine for stroke input.

Builds an in-memory trie index from a list of CharacterRecords for fast
prefix lookup.  Maintains the current stroke sequence and provides methods
to append, remove, and clear strokes.
"""

from __future__ import annotations

import logging
from typing import Optional

from stroke_input.data.models import CharacterRecord, StrokeType

logger = logging.getLogger(__name__)


class _TrieNode:
    """Internal trie node used by StrokeEngine."""

    __slots__ = ("children", "records")

    def __init__(self) -> None:
        # Maps stroke code (1-5) to child node
        self.children: dict[int, _TrieNode] = {}
        # Characters whose full stroke sequence ends exactly at this node
        self.records: list[CharacterRecord] = []


class StrokeEngine:
    """Prefix-matching engine that maps stroke sequences to candidate characters.

    The engine indexes all character records in a trie keyed by stroke sequence.
    ``query()`` returns every character whose stroke sequence starts with the
    current prefix (i.e. all records stored at or below the prefix node).

    Typical usage::

        engine = StrokeEngine(records)
        engine.append_stroke(StrokeType.HENG)
        candidates = engine.query()
        engine.remove_last_stroke()
        engine.clear_sequence()
    """

    def __init__(self, records: list[CharacterRecord]) -> None:
        self._root = _TrieNode()
        self._sequence: list[int] = []
        self._build_index(records)

    # ------------------------------------------------------------------
    # Index construction
    # ------------------------------------------------------------------

    def _build_index(self, records: list[CharacterRecord]) -> None:
        """Insert every record into the trie keyed by its stroke_sequence."""
        for rec in records:
            node = self._root
            for code in rec.stroke_sequence:
                if code not in node.children:
                    node.children[code] = _TrieNode()
                node = node.children[code]
            node.records.append(rec)
        logger.info("StrokeEngine indexed %d character records", len(records))

    # ------------------------------------------------------------------
    # Stroke sequence manipulation
    # ------------------------------------------------------------------

    @property
    def current_sequence(self) -> list[int]:
        """Return a copy of the current stroke sequence."""
        return list(self._sequence)

    def append_stroke(self, stroke: int) -> None:
        """Append a stroke code to the current sequence.

        Args:
            stroke: A stroke code (1-6). Values 1-5 are the basic strokes;
                    6 is the wildcard (handled at query time).
        """
        self._sequence.append(int(stroke))

    def remove_last_stroke(self) -> None:
        """Remove the last stroke from the current sequence (Backspace)."""
        if self._sequence:
            self._sequence.pop()

    def clear_sequence(self) -> None:
        """Clear the entire current stroke sequence (Escape)."""
        self._sequence.clear()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(self, stroke_sequence: Optional[list[int]] = None) -> list[CharacterRecord]:
        """Return all characters whose stroke sequence starts with the given prefix.

        If *stroke_sequence* is ``None``, the engine's internal current
        sequence is used.

        Args:
            stroke_sequence: An explicit prefix to query, or ``None`` to use
                the current sequence maintained via append/remove/clear.

        Returns:
            A list of matching ``CharacterRecord`` objects (unranked).
            Returns an empty list when the prefix has no matches.
        """
        seq = stroke_sequence if stroke_sequence is not None else self._sequence
        if not seq:
            # Empty sequence → return all characters
            return self._collect_all(self._root)

        # Walk the trie following the prefix
        nodes = [self._root]
        for code in seq:
            next_nodes: list[_TrieNode] = []
            for node in nodes:
                if code == StrokeType.WILDCARD:
                    # Wildcard matches any stroke type (1-5)
                    next_nodes.extend(
                        child for child in node.children.values()
                    )
                else:
                    child = node.children.get(code)
                    if child is not None:
                        next_nodes.append(child)
            if not next_nodes:
                return []
            nodes = next_nodes

        # Collect all records at and below the matched nodes
        results: list[CharacterRecord] = []
        for node in nodes:
            self._collect_all_into(node, results)

        # Deduplicate: a character may appear multiple times due to stroke
        # sequence variants (e.g. 該 can be indexed under both 1111251415334
        # and 4111251415334). Keep the first occurrence per character.
        seen: set[str] = set()
        deduped: list[CharacterRecord] = []
        for rec in results:
            if rec.character not in seen:
                seen.add(rec.character)
                deduped.append(rec)
        return deduped

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_all(self, node: _TrieNode) -> list[CharacterRecord]:
        """Recursively collect all records at and below *node*."""
        result: list[CharacterRecord] = []
        self._collect_all_into(node, result)
        return result

    def _collect_all_into(self, node: _TrieNode, out: list[CharacterRecord]) -> None:
        """Recursively append all records at and below *node* into *out*."""
        out.extend(node.records)
        for child in node.children.values():
            self._collect_all_into(child, out)
