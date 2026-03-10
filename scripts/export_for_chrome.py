"""Export stroke data as sorted JSON for the Chrome extension.

Characters with multiple stroke sequence variants (from Conway's regex
alternatives) are exported as separate entries so the binary-search prefix
match in the extension finds the character regardless of which stroke
convention the user follows.
"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from stroke_input.data.serializer import load_msgpack

records = load_msgpack(Path("data/stroke_db.msgpack"))

# Build sorted array: [sequence_string, character, frequency]
# Multiple entries per character are expected (one per stroke variant)
data = []
seen: set[tuple[str, str]] = set()
for r in records:
    seq = "".join(str(s) for s in r.stroke_sequence)
    key = (seq, r.character)
    if key not in seen:
        seen.add(key)
        data.append([seq, r.character, round(r.frequency, 4)])

data.sort(key=lambda x: x[0])

out = Path("chrome-extension/data/strokes.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
print(f"{len(data)} entries, {out.stat().st_size:,} bytes")

# Also export phrases
phrases_path = Path("data/phrases.tsv")
phrases = {}
for line in phrases_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split("\t")
    phrase = parts[0].strip()
    freq = float(parts[1]) if len(parts) >= 2 else 0.0
    if len(phrase) >= 2:
        first = phrase[0]
        if first not in phrases:
            phrases[first] = []
        phrases[first].append([phrase, freq])

# Sort each bucket by frequency desc
for k in phrases:
    phrases[k].sort(key=lambda x: -x[1])

out2 = Path("chrome-extension/data/phrases.json")
out2.write_text(json.dumps(phrases, ensure_ascii=False), encoding="utf-8")
print(f"{sum(len(v) for v in phrases.values())} phrases, {out2.stat().st_size:,} bytes")
