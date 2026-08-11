#!/usr/bin/env python3
"""Generate Cantonese-specific frequency data and phrase dictionary.

This script produces data files for the Chrome extension:
1. Cantonese character frequency adjustments (merged into strokes.json via export)
2. Cantonese phrase dictionary (supplements CC-CEDICT with Cantonese collocations)

Bigram/trigram JSON is built by ``export_for_chrome.py`` from a unified
:class:`~stroke_input.data.ngram_model.NgramModel` (same score scale).
Hand-tuned Cantonese pairs live in ``CANTONESE_BIGRAM_PAIRS`` and are
injected into that corpus at export time.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "chrome-extension" / "data"

# ── Cantonese-specific character frequency boosts ─────────────────
# Characters that are extremely common in written/spoken Cantonese
# but underrepresented in Mandarin frequency tables.
# Values represent target frequency (0-1 scale).
CANTONESE_FREQ_OVERRIDES: dict[str, float] = {
    # Ultra-common single-stroke / short characters (must surface on first keys)
    "一": 0.995,  # jat1 - numeral / generic "one"; Zipf alone buries it under colloquial overrides
    "丨": 0.40,   # stroke name char; keep modest
    "不": 0.70,   # bat1 - common negation (written)

    # Cantonese-exclusive function words (highest frequency)
    "係": 0.99,   # hai6 - "is" (copula)
    "唔": 0.99,   # m4 - "not" (negation)
    "咗": 0.98,   # zo2 - past tense marker
    "嘅": 0.98,   # ge3 - possessive/attributive particle
    "冇": 0.97,   # mou5 - "don't have"
    "嚟": 0.97,   # lai4 - "come"
    "咁": 0.96,   # gam3 - "so/like this"
    "邊": 0.95,   # bin1 - "which/where"
    "啲": 0.95,   # di1 - "some/a bit"
    "佢": 0.98,   # keoi5 - "he/she/it"
    "喺": 0.97,   # hai2 - "at/in" (locative)
    "度": 0.93,   # dou6 - "place/degree"
    "埋": 0.92,   # maai4 - "also/close"
    "嘢": 0.94,   # je5 - "thing/stuff"
    "點": 0.94,   # dim2 - "how/what"
    "乜": 0.93,   # mat1 - "what"
    "咩": 0.93,   # me1 - "what" (question)
    "嗰": 0.93,   # go2 - "that"
    "哋": 0.94,   # dei6 - plural marker
    "咪": 0.91,   # mai6 - "don't/isn't it"
    "嗮": 0.90,   # saai3 - "all/completely"
    "畀": 0.93,   # bei2 - "give"
    "睇": 0.93,   # tai2 - "look/see"
    "嘥": 0.85,   # saai1 - "waste"
    "攞": 0.90,   # lo2 - "take"
    "揾": 0.89,   # wan2 - "find/look for"
    "嗱": 0.82,   # naa4 - "here/now"
    "噉": 0.91,   # gam2 - "like that"
    "嚿": 0.80,   # gau6 - "piece/lump"
    "瞓": 0.85,   # fan3 - "sleep"
    "嬲": 0.84,   # nau1 - "angry"
    "慳": 0.83,   # haan1 - "save/thrifty"
    "嘈": 0.82,   # cou4 - "noisy"
    "掂": 0.86,   # dim6 - "settled/okay"
    "搞": 0.88,   # gaau2 - "do/handle"
    "傾": 0.86,   # king1 - "chat/talk"
    "諗": 0.88,   # nam2 - "think"
    "驚": 0.86,   # geng1 - "scared/afraid"
    "鍾": 0.87,   # zung1 - "fond of"
    "意": 0.90,   # ji3 - "meaning/intention"
    "抵": 0.85,   # dai2 - "worth it"
    "靚": 0.87,   # leng3 - "pretty/good"
    "勁": 0.87,   # ging6 - "strong/awesome"
    "正": 0.88,   # zeng3 - "great/correct"
    "衰": 0.84,   # seoi1 - "bad/unlucky"
    "曳": 0.80,   # jai5 - "naughty"
    "激": 0.84,   # gik1 - "angry/extreme"
    "煩": 0.83,   # faan4 - "annoying"
    "悶": 0.83,   # mun6 - "bored"
    "癲": 0.81,   # din1 - "crazy"
    "蝕": 0.80,   # sit6 - "lose money"

    # Common Cantonese pronouns and demonstratives
    "我": 0.99,   # ngo5 - "I/me"
    "你": 0.99,   # nei5 - "you"
    "佬": 0.88,   # lou2 - "guy/man"
    "仔": 0.91,   # zai2 - "son/boy/small"
    "女": 0.90,   # neoi5 - "girl/daughter"
    "嗰個": 0.85, # go2 go3 - "that one" (will be split)

    # Common verbs in Cantonese
    "食": 0.92,   # sik6 - "eat"
    "飲": 0.89,   # jam2 - "drink"
    "行": 0.91,   # haang4 - "walk"
    "企": 0.86,   # kei5 - "stand"
    "坐": 0.88,   # co5 - "sit"
    "瞓": 0.85,   # fan3 - "sleep"
    "著": 0.87,   # zoek3 - "wear"
    "買": 0.89,   # maai5 - "buy"
    "賣": 0.87,   # maai6 - "sell"
    "俾": 0.88,   # bei2 - variant of 畀

    # Sentence-final particles (very frequent in Cantonese)
    "呀": 0.92,   # aa3 - sentence final
    "啊": 0.91,   # aa3 - sentence final
    "喎": 0.88,   # wo3 - surprise
    "囉": 0.87,   # lo1 - assertion
    "啦": 0.91,   # laa1 - suggestion
    "嘞": 0.85,   # laak3 - completion
    "㗎": 0.89,   # gaa3 - emphasis
    "嘛": 0.87,   # maa3 - obvious
    "咯": 0.85,   # lok3 - confirmation
    "喇": 0.88,   # laa3 - change of state
    "吖": 0.86,   # aa1 - friendly
    "嚱": 0.80,   # he2 - question
    "咋": 0.84,   # zaa3 - "only/just"
    "啩": 0.82,   # gwaa3 - "I suppose"
    "噃": 0.80,   # bo3 - emphasis

    # Common nouns
    "錢": 0.89,   # cin2 - "money"
    "嘢": 0.94,   # je5 - "thing"
    "人": 0.95,   # jan4 - "person"
    "屋": 0.86,   # uk1 - "house"
    "車": 0.88,   # ce1 - "car"
    "路": 0.87,   # lou6 - "road"
    "舖": 0.84,   # pou3 - "shop"
    "檔": 0.83,   # dong3 - "stall"
}
# Remove any multi-char keys that slipped in
CANTONESE_FREQ_OVERRIDES = {k: v for k, v in CANTONESE_FREQ_OVERRIDES.items() if len(k) == 1}


# ── Cantonese phrase dictionary ───────────────────────────────────
# Common Cantonese collocations, expressions, and phrases
# Format: (phrase, frequency)
CANTONESE_PHRASES: list[tuple[str, float]] = [
    # Negation patterns
    ("唔好", 0.98),
    ("唔係", 0.97),
    ("唔使", 0.93),
    ("唔知", 0.95),
    ("唔想", 0.93),
    ("唔該", 0.95),
    ("唔得", 0.92),
    ("唔會", 0.94),
    ("唔可以", 0.90),
    ("唔記得", 0.88),
    ("唔緊要", 0.89),
    ("唔明白", 0.87),
    ("唔需要", 0.85),
    ("唔見咗", 0.84),
    ("唔好意思", 0.90),
    ("唔通", 0.85),
    ("唔夠", 0.86),
    ("唔同", 0.88),
    ("唔錯", 0.87),
    ("唔怕", 0.84),
    ("唔敢", 0.85),
    ("唔肯", 0.83),
    ("唔准", 0.82),
    ("唔理", 0.84),
    ("唔信", 0.83),

    # Question words
    ("點解", 0.95),
    ("點樣", 0.94),
    ("幾時", 0.93),
    ("幾多", 0.92),
    ("邊個", 0.94),
    ("邊度", 0.94),
    ("邊到", 0.90),
    ("乜嘢", 0.92),
    ("咩事", 0.91),
    ("咩嘢", 0.90),
    ("做乜", 0.90),
    ("做咩", 0.90),
    ("點算", 0.88),
    ("幾耐", 0.87),
    ("幾大", 0.85),

    # Time expressions
    ("而家", 0.95),
    ("依家", 0.94),
    ("頭先", 0.90),
    ("之前", 0.92),
    ("之後", 0.92),
    ("琴日", 0.89),
    ("尋日", 0.89),
    ("聽日", 0.90),
    ("今日", 0.93),
    ("今晚", 0.90),
    ("朝早", 0.88),
    ("晏晝", 0.85),
    ("夜晚", 0.88),
    ("第日", 0.85),
    ("嗰陣", 0.88),
    ("嗰時", 0.86),
    ("成日", 0.87),
    ("平時", 0.86),
    ("有時", 0.88),
    ("隨時", 0.84),

    # Common verb phrases
    ("食飯", 0.92),
    ("飲水", 0.88),
    ("飲茶", 0.90),
    ("返工", 0.92),
    ("放工", 0.90),
    ("返屋企", 0.90),
    ("出街", 0.88),
    ("行街", 0.88),
    ("搭車", 0.87),
    ("揸車", 0.86),
    ("泊車", 0.84),
    ("睇戲", 0.86),
    ("睇醫生", 0.85),
    ("睇書", 0.84),
    ("睇電視", 0.85),
    ("傾電話", 0.83),
    ("傾偈", 0.86),
    ("瞓覺", 0.86),
    ("沖涼", 0.86),
    ("煮飯", 0.85),
    ("洗衫", 0.83),
    ("買嘢", 0.88),
    ("賺錢", 0.84),
    ("慳錢", 0.83),
    ("畀錢", 0.87),
    ("攞嘢", 0.85),
    ("揾工", 0.85),
    ("揾食", 0.84),
    ("搞掂", 0.87),
    ("諗住", 0.86),
    ("鍾意", 0.92),
    ("開心", 0.90),
    ("唞氣", 0.80),

    # Adjective phrases
    ("好靚", 0.87),
    ("好勁", 0.86),
    ("好正", 0.87),
    ("好嘢", 0.86),
    ("好耐", 0.87),
    ("好多", 0.90),
    ("好少", 0.86),
    ("好快", 0.86),
    ("好慢", 0.83),
    ("好大", 0.87),
    ("好細", 0.84),
    ("好貴", 0.85),
    ("好平", 0.84),
    ("好忙", 0.85),
    ("好攰", 0.86),
    ("好悶", 0.84),
    ("好煩", 0.84),
    ("好難", 0.86),
    ("好易", 0.84),
    ("好似", 0.88),

    # Pronouns and demonstratives
    ("我哋", 0.94),
    ("你哋", 0.93),
    ("佢哋", 0.93),
    ("自己", 0.92),
    ("大家", 0.91),
    ("人哋", 0.89),
    ("呢個", 0.93),
    ("嗰個", 0.93),
    ("呢度", 0.92),
    ("嗰度", 0.91),
    ("呢啲", 0.90),
    ("嗰啲", 0.89),
    ("咁多", 0.88),
    ("咁樣", 0.90),
    ("噉樣", 0.88),

    # Aspect markers and complements
    ("咗啦", 0.85),
    ("緊呀", 0.82),
    ("得返", 0.83),
    ("唔到", 0.86),
    ("得到", 0.85),
    ("出嚟", 0.87),
    ("入去", 0.85),
    ("返嚟", 0.86),
    ("過嚟", 0.86),
    ("過去", 0.85),
    ("落去", 0.84),
    ("上嚟", 0.84),
    ("埋嚟", 0.83),

    # Sentence patterns
    ("係咪", 0.92),
    ("係唔係", 0.90),
    ("有冇", 0.93),
    ("得唔得", 0.87),
    ("好唔好", 0.88),
    ("要唔要", 0.85),
    ("知唔知", 0.86),
    ("去唔去", 0.83),
    ("食唔食", 0.82),
    ("想唔想", 0.83),
    ("啱唔啱", 0.82),

    # Greetings and social
    ("早晨", 0.90),
    ("你好", 0.93),
    ("多謝", 0.93),
    ("唔該", 0.95),
    ("對唔住", 0.90),
    ("唔好意思", 0.90),
    ("拜拜", 0.88),
    ("再見", 0.89),
    ("恭喜", 0.86),
    ("生日快樂", 0.85),
    ("新年快樂", 0.85),

    # Common expressions
    ("冇問題", 0.89),
    ("冇所謂", 0.86),
    ("冇辦法", 0.86),
    ("冇關係", 0.85),
    ("唔緊要", 0.89),
    ("算啦", 0.85),
    ("得啦", 0.86),
    ("好啦", 0.88),
    ("係啦", 0.86),
    ("知道", 0.90),
    ("明白", 0.89),
    ("當然", 0.88),
    ("其實", 0.90),
    ("不過", 0.91),
    ("所以", 0.92),
    ("因為", 0.92),
    ("如果", 0.91),
    ("雖然", 0.88),
    ("但係", 0.90),
    ("而且", 0.87),
    ("或者", 0.88),
    ("可能", 0.90),
    ("應該", 0.90),
    ("一定", 0.89),
    ("已經", 0.91),
    ("仲有", 0.88),
    ("仲係", 0.86),
    ("仲未", 0.87),
    ("差唔多", 0.87),
    ("差不多", 0.87),

    # Places and daily life (HK context)
    ("香港", 0.92),
    ("九龍", 0.85),
    ("新界", 0.83),
    ("港島", 0.82),
    ("地鐵", 0.86),
    ("巴士", 0.86),
    ("的士", 0.86),
    ("小巴", 0.84),
    ("茶餐廳", 0.85),
    ("酒樓", 0.83),
    ("街市", 0.83),
    ("超市", 0.84),
    ("商場", 0.83),
    ("屋企", 0.90),
    ("學校", 0.87),
    ("公司", 0.88),
    ("醫院", 0.85),
    ("銀行", 0.84),
    ("警察", 0.83),
]


def generate_cantonese_phrases() -> dict[str, list[list]]:
    """Build phrase dict indexed by first character, merging with existing CEDICT phrases."""
    # Load existing phrases
    existing_phrases_path = DATA_DIR / "phrases.tsv"
    existing: dict[str, list[list]] = {}
    if existing_phrases_path.exists():
        for line in existing_phrases_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            phrase = parts[0].strip()
            freq = float(parts[1]) if len(parts) >= 2 else 0.0
            if len(phrase) >= 2:
                first = phrase[0]
                if first not in existing:
                    existing[first] = []
                existing[first].append([phrase, freq])

    # Add Cantonese phrases (override if same phrase exists)
    all_cantonese = set()
    for phrase, freq in CANTONESE_PHRASES:
        if len(phrase) < 2:
            continue
        first = phrase[0]
        all_cantonese.add(phrase)
        if first not in existing:
            existing[first] = []
        # Check if phrase already exists, update freq if so
        found = False
        for entry in existing[first]:
            if entry[0] == phrase:
                entry[1] = max(entry[1], freq)  # Take higher frequency
                found = True
                break
        if not found:
            existing[first].append([phrase, freq])

    # Sort each bucket by frequency desc
    for k in existing:
        existing[k].sort(key=lambda x: -x[1])

    return existing


CANTONESE_BIGRAM_PAIRS: list[tuple[str, str, float]] = [
        # Pronoun + plural
        ("我", "哋", 2.0), ("你", "哋", 2.0), ("佢", "哋", 2.0),
        ("人", "哋", 1.5),
        # Negation patterns
        ("唔", "好", 2.5), ("唔", "係", 2.5), ("唔", "使", 2.0),
        ("唔", "知", 2.2), ("唔", "想", 2.0), ("唔", "該", 2.2),
        ("唔", "得", 2.0), ("唔", "會", 2.2), ("唔", "通", 1.8),
        ("唔", "夠", 1.8), ("唔", "同", 1.8), ("唔", "錯", 1.8),
        ("唔", "怕", 1.5), ("唔", "敢", 1.5), ("唔", "肯", 1.5),
        ("唔", "准", 1.5), ("唔", "理", 1.5), ("唔", "信", 1.5),
        # Question patterns
        ("點", "解", 2.2), ("點", "樣", 2.2), ("點", "算", 1.8),
        ("幾", "時", 2.0), ("幾", "多", 2.0), ("幾", "耐", 1.8),
        ("邊", "個", 2.2), ("邊", "度", 2.2), ("邊", "到", 1.8),
        ("乜", "嘢", 2.0), ("咩", "事", 1.8), ("咩", "嘢", 1.8),
        ("做", "乜", 1.8), ("做", "咩", 1.8),
        # Time
        ("而", "家", 2.2), ("依", "家", 2.0), ("頭", "先", 1.8),
        ("琴", "日", 1.8), ("尋", "日", 1.8), ("聽", "日", 1.8),
        ("今", "日", 2.0), ("今", "晚", 1.8),
        ("嗰", "陣", 1.8), ("嗰", "個", 2.0), ("嗰", "度", 1.8),
        ("嗰", "啲", 1.8),
        ("呢", "個", 2.0), ("呢", "度", 1.8), ("呢", "啲", 1.8),
        # Verb + object
        ("食", "飯", 2.0), ("飲", "水", 1.8), ("飲", "茶", 2.0),
        ("返", "工", 2.0), ("放", "工", 1.8), ("出", "街", 1.8),
        ("行", "街", 1.8), ("搭", "車", 1.8), ("揸", "車", 1.8),
        ("睇", "戲", 1.8), ("睇", "書", 1.5), ("傾", "偈", 1.8),
        ("買", "嘢", 2.0), ("攞", "嘢", 1.8), ("揾", "工", 1.8),
        ("搞", "掂", 2.0), ("諗", "住", 1.8), ("鍾", "意", 2.5),
        ("開", "心", 1.8), ("畀", "錢", 1.8), ("慳", "錢", 1.5),
        # Aspect/complement
        ("出", "嚟", 1.8), ("入", "去", 1.5), ("返", "嚟", 1.8),
        ("過", "嚟", 1.8), ("落", "去", 1.5), ("上", "嚟", 1.5),
        ("埋", "嚟", 1.5),
        # Adjective patterns
        ("好", "靚", 1.8), ("好", "勁", 1.8), ("好", "正", 1.8),
        ("好", "嘢", 1.8), ("好", "耐", 1.8), ("好", "多", 2.0),
        ("好", "似", 1.8), ("好", "攰", 1.5), ("好", "悶", 1.5),
        # Sentence patterns
        ("係", "咪", 2.0), ("有", "冇", 2.2),
        ("但", "係", 2.0), ("因", "為", 2.0), ("所", "以", 2.0),
        ("如", "果", 2.0), ("可", "能", 1.8), ("應", "該", 1.8),
        ("已", "經", 2.0), ("仲", "有", 1.8), ("仲", "係", 1.5),
        ("仲", "未", 1.8),
        # Common collocations
        ("屋", "企", 2.0), ("自", "己", 2.0), ("大", "家", 1.8),
        ("香", "港", 2.0), ("茶", "餐", 1.5),
]


def generate_bigram_model(phrases: dict[str, list[list]]) -> dict[str, dict[str, float]]:
    """Deprecated legacy exporter (max-normalized co-occurrence).

    Prefer ``export_for_chrome.py`` which builds smoothed bigrams/trigrams
    from :class:`NgramModel` on a unified corpus. Kept for one-off debugging.
    """
    MAX_BIGRAMS_PER_CHAR = 15
    co_occurrence: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    # Extract bigrams from all phrases
    for first_char, entries in phrases.items():
        for phrase, freq in entries:
            for i in range(len(phrase) - 1):
                c1 = phrase[i]
                c2 = phrase[i + 1]
                co_occurrence[c1][c2] += freq

    for c1, c2, score in CANTONESE_BIGRAM_PAIRS:
        co_occurrence[c1][c2] = max(co_occurrence[c1][c2], score)

    # Normalize and keep top N per character
    result: dict[str, dict[str, float]] = {}
    for c1, followers in co_occurrence.items():
        if not followers:
            continue
        max_score = max(followers.values())
        if max_score <= 0:
            continue
        # Normalize to [0, 1]
        normalized = {c2: round(s / max_score, 4) for c2, s in followers.items()}
        # Keep top N
        top = sorted(normalized.items(), key=lambda x: -x[1])[:MAX_BIGRAMS_PER_CHAR]
        result[c1] = dict(top)

    return result


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Step 1: Generating Cantonese frequency overrides...")
    freq_path = OUTPUT_DIR / "cantonese_freq.json"
    freq_path.write_text(
        json.dumps(CANTONESE_FREQ_OVERRIDES, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  {len(CANTONESE_FREQ_OVERRIDES)} character overrides -> {freq_path}")

    print("\nStep 2: Generating Cantonese phrase dictionary...")
    phrases = generate_cantonese_phrases()
    phrases_path = OUTPUT_DIR / "phrases.json"
    phrases_path.write_text(
        json.dumps(phrases, ensure_ascii=False),
        encoding="utf-8",
    )
    total_phrases = sum(len(v) for v in phrases.values())
    print(f"  {total_phrases} phrases ({len(phrases)} buckets) -> {phrases_path}")

    print("\nStep 3: Skipping legacy max-normalized bigrams")
    print("  (bigrams.json / trigrams.json are built by export_for_chrome.py")
    print("   from NgramModel on the unified phrase corpus)")

    print("\nDone!")


if __name__ == "__main__":
    main()
