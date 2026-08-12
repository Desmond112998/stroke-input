"""Export stroke data as sorted JSON for the Chrome extension.

Characters with multiple stroke sequence variants (from Conway's regex
alternatives) are exported as separate entries so the binary-search prefix
match in the extension finds the character regardless of which stroke
convention the user follows.

Also applies Cantonese frequency overrides, exports unified bigram + trigram
data from :class:`NgramModel`, and writes ``ranking_config.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))

from generate_cantonese_data import CANTONESE_BIGRAM_PAIRS  # noqa: E402
from stroke_input.config.ranking import to_chrome_dict  # noqa: E402
from stroke_input.data.models import PhraseEntry  # noqa: E402
from stroke_input.data.ngram_export import (  # noqa: E402
    export_bigrams_for_chrome,
    export_trigrams_for_chrome,
)
from stroke_input.data.ngram_model import NgramModel  # noqa: E402
from stroke_input.data.phrase_loader import load_phrase_dict  # noqa: E402
from stroke_input.data.serializer import load_msgpack  # noqa: E402

OUT_DIR = _ROOT / "chrome-extension" / "data"

# Cap stroke-sequence variants per character (Conway regex expansions).
# Keep highest-frequency encodings; rare glyphs can otherwise explode to ~90 rows.
MAX_VARIANTS_PER_CHAR = 12


def _script_tag(flag: str) -> str | None:
    if flag == "trad":
        return "t"
    if flag == "simp":
        return "s"
    return None


def export_strokes() -> None:
    records = load_msgpack(_ROOT / "data/stroke_db.msgpack")

    cantonese_freq_path = OUT_DIR / "cantonese_freq.json"
    cantonese_freq: dict[str, float] = {}
    if cantonese_freq_path.exists():
        cantonese_freq = json.loads(cantonese_freq_path.read_text(encoding="utf-8"))
        print(f"Loaded {len(cantonese_freq)} Cantonese frequency overrides")

    data = []
    wubi_data = []
    seen: set[tuple[str, str]] = set()
    wubi_seen: set[tuple[str, str]] = set()
    for r in records:
        seq = "".join(str(s) for s in r.stroke_sequence)
        key = (seq, r.character)
        if key in seen:
            continue
        seen.add(key)
        freq = r.frequency
        if r.character in cantonese_freq:
            freq = max(freq, cantonese_freq[r.character])
        row: list = [seq, r.character, round(freq, 4)]
        tag = _script_tag(getattr(r, "script_flag", "") or "")
        if tag:
            row.append(tag)
        data.append(row)

        # Wubi-hua (頭四尾一): only for characters with more than 5 strokes
        if len(r.stroke_sequence) > 5:
            wubi_seq = "".join(
                str(s) for s in (r.stroke_sequence[:4] + [r.stroke_sequence[-1]])
            )
            wkey = (wubi_seq, r.character)
            if wkey not in wubi_seen:
                wubi_seen.add(wkey)
                wrow: list = [wubi_seq, r.character, round(freq, 4)]
                if tag:
                    wrow.append(tag)
                wubi_data.append(wrow)

    # Cap per-character variants (keep highest frequency)
    from collections import defaultdict

    by_char: dict[str, list] = defaultdict(list)
    for row in data:
        by_char[row[1]].append(row)
    capped: list = []
    for rows in by_char.values():
        rows.sort(key=lambda x: -x[2])
        capped.extend(rows[:MAX_VARIANTS_PER_CHAR])
    if len(capped) < len(data):
        print(
            f"  Variant cap {MAX_VARIANTS_PER_CHAR}/char: "
            f"{len(data)} → {len(capped)} stroke rows"
        )
    data = capped

    data.sort(key=lambda x: x[0])
    out = OUT_DIR / "strokes.json"
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"{len(data)} stroke entries -> {out} ({out.stat().st_size:,} bytes)")

    wubi_data.sort(key=lambda x: x[0])
    wubi_out = OUT_DIR / "strokes_wubi.json"
    wubi_out.write_text(json.dumps(wubi_data, ensure_ascii=False), encoding="utf-8")
    print(f"{len(wubi_data)} wubi-hua entries -> {wubi_out} ({wubi_out.stat().st_size:,} bytes)")


def _phrase_entries_from_json(path: Path) -> list[PhraseEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries: list[PhraseEntry] = []
    for bucket in raw.values():
        for phrase, freq in bucket:
            if isinstance(phrase, str) and len(phrase) >= 2:
                entries.append(PhraseEntry(phrase=phrase, frequency=float(freq)))
    return entries


def export_ngrams() -> None:
    """Build one NgramModel from phrases.json + Cantonese pairs; always rewrite JSON."""
    phrases_json = OUT_DIR / "phrases.json"
    phrase_tsv = _ROOT / "data/phrases.tsv"

    entries: list[PhraseEntry] = []
    if phrases_json.exists():
        entries.extend(_phrase_entries_from_json(phrases_json))
        print(f"Loaded {len(entries)} phrases from {phrases_json.name}")
    elif phrase_tsv.exists():
        phrase_dict = load_phrase_dict(phrase_tsv)
        entries = [e for bucket in phrase_dict._index.values() for e in bucket]
        print(f"Loaded {len(entries)} phrases from {phrase_tsv.name}")
    else:
        print("No phrase corpus found; skipping n-gram export")
        return

    # Inject hand-tuned Cantonese collocations (freq scaled into [0,1])
    for c1, c2, raw in CANTONESE_BIGRAM_PAIRS:
        entries.append(PhraseEntry(phrase=c1 + c2, frequency=min(1.0, raw / 2.5)))

    ngram = NgramModel.build_from_phrases(entries)
    print(
        f"  vocab={ngram.vocab_size}, bigram_contexts={len(ngram._bi)}, "
        f"trigram_contexts={sum(len(b) for b in ngram._tri.values())}"
    )

    bigrams_json = OUT_DIR / "bigrams.json"
    bigram_data = export_bigrams_for_chrome(ngram, min_count=1)
    bigrams_json.write_text(json.dumps(bigram_data, ensure_ascii=False), encoding="utf-8")
    print(
        f"  bigrams.json: {len(bigram_data)} prev-contexts, "
        f"{bigrams_json.stat().st_size:,} bytes"
    )

    trigrams_json = OUT_DIR / "trigrams.json"
    trigram_data = export_trigrams_for_chrome(ngram, min_count=2)
    trigrams_json.write_text(json.dumps(trigram_data, ensure_ascii=False), encoding="utf-8")
    n_tri = sum(len(bi) for bi in trigram_data.values())
    print(
        f"  trigrams.json: {len(trigram_data)} p2-contexts, {n_tri} (p2,p1) pairs, "
        f"{trigrams_json.stat().st_size:,} bytes"
    )


def export_ranking_config() -> None:
    cfg = to_chrome_dict()
    path = OUT_DIR / "ranking_config.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ranking_config.json -> {path}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    export_strokes()
    # Ensure phrases exist (Cantonese generator may have written them already)
    phrases_json = OUT_DIR / "phrases.json"
    if not phrases_json.exists():
        phrases_path = _ROOT / "data/phrases.tsv"
        phrases: dict[str, list] = {}
        for line in phrases_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            phrase = parts[0].strip()
            freq = float(parts[1]) if len(parts) >= 2 else 0.0
            if len(phrase) >= 2:
                phrases.setdefault(phrase[0], []).append([phrase, freq])
        for k in phrases:
            phrases[k].sort(key=lambda x: -x[1])
        phrases_json.write_text(json.dumps(phrases, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote fallback phrases.json ({sum(len(v) for v in phrases.values())} phrases)")

    export_ngrams()
    export_ranking_config()


if __name__ == "__main__":
    main()
