# AI Background

This document gives AI agents the context needed to work safely in this repository.

## Product goal

The project provides a Chinese stroke-based input method optimized for Traditional Chinese and Cantonese usage. Users type stroke sequences with keyboard keys and receive ranked Chinese character and phrase candidates in real time.

## User-facing surfaces

### Chrome extension

The main product surface is `chrome-extension\`. It runs as a Manifest V3 extension and injects an overlay into editable web fields. Important files:

- `manifest.json`: extension metadata and permissions
- `background.js`: service worker and cross-tab state synchronization
- `engine.js`: pure search / ranking / phrase helpers (also loaded under Node tests)
- `content.js`: input handling, candidate UI, chrome.* wiring, overlay behavior
- `options.html` / `options.js`: user settings (`imeSettings` in `chrome.storage.local`)
- `style.css`: overlay presentation
- `data\*.json`: exported lookup/ranking data consumed at runtime (`strokes.json`, `strokes_wubi.json`, `phrases.json`, `bigrams.json`, `trigrams.json`, `ranking_config.json`, …)

### Python engine and tooling

The Python package in `src\stroke_input\` is the source of truth for engine behavior and data processing:

- `config\ranking.py`: shared ranking / Zipf / n-gram constants (exported to `ranking_config.json`)
- `data\models.py`: core character and stroke data structures
- `data\serializer.py`: msgpack persistence
- `data\phrase_loader.py`: phrase dictionary loading
- `data\user_freq_store.py`: user adaptation storage (counts, recency, positions, pins)
- `data\ngram_model.py`: character n-gram language model
- Conway stroke parsing lives in `scripts\download_stroke_data.py` (not a package module)
- `engine\stroke_engine.py`: trie-based prefix search and wildcard lookup
- `engine\inference_engine.py`: fuzzy inference and contextual phrase support
- `engine\frequency_ranker.py`: composite candidate scoring

## Data pipeline

The repository has both source and generated data. Treat generated files carefully.

1. `scripts\download_stroke_data.py` obtains/parses Conway stroke data into `data\stroke_db.msgpack`.
2. `scripts\build_hk_frequency.py` downloads and merges Hong Kong / Traditional Chinese character frequency data from Apple Daily, Cifu, and CUHK Lexis into `data\character_frequency_hk.json`.
3. `scripts\generate_phrase_dict.py` builds Traditional Chinese phrase data from CC-CEDICT-derived sources.
4. `scripts\generate_cantonese_data.py` creates Cantonese frequency overrides, phrase data, and bigram seed data.
5. `scripts\export_for_chrome.py` exports optimized JSON into `chrome-extension\data\` (full strokes, optional 五筆劃 index, unified n-grams, ranking config). Per-character stroke variants are capped on export.
6. `scripts\package_extension.py` rebuilds/validates/packages the extension zip.
7. `scripts\generate_parity_fixture.py` refreshes the Python↔JS ranking parity fixture used by tests.
8. Optional assets: `scripts\generate_icons.py`, `scripts\generate_screenshots.py` (Web Store images). `scripts\check_keys.py` is a local keyboard-name debug helper (requires the `keyboard` package; not part of the extension runtime).

## Ranking and inference intent

Candidate ordering blends several concerns:

- exact/prefix stroke match quality (fuzzy one-stroke substitution ranks after exact)
- static frequency (merged Hong Kong frequency table + Zipf-mapped fallback + Cantonese overrides)
- short-prefix exact-complete bucketing: for prefixes of 5 strokes or fewer, characters whose full stroke sequence is exactly the typed prefix are shown before longer continuations, so common short characters like 中 (2512) and 由 (25121) surface first
- Traditional Chinese preference (Conway `^` / `"t"` script tag)
- user frequency adaptation, recency, and position / pin history
- previous-character bigram and trigram context
- mid-typing association characters and phrase suggestions after selection (including auto-learned phrases)

Changes to ranking should be deliberate and covered by tests because small score changes can alter visible UX.

## Key mapping

The default stroke key mapping is:

| Key | Stroke | Symbol |
| --- | --- | --- |
| J | Horizontal | 一 |
| K | Vertical | 丨 |
| L | Left-falling | 丿 |
| U | Dot | 丶 |
| I | Turning | 乙 |
| O | Wildcard | ＊ |

Shortcuts are documented in `README.md`; update documentation when changing them.

## Licensing context

The project uses external language data:

- Conway stroke data: CC-BY-4.0
- CC-CEDICT-derived phrase dictionary: CC BY-SA 4.0
- Hong Kong character frequency data (merged from):
  - Apple Daily frequency list (chaaklau/appledaily-frequency): CC BY 4.0
  - Cifu (gwinterstein/Cifu): academic lexicon; cite Lai & Winterstein (2020) if used in research
  - CUHK Lexis Chinese Character Frequency Statistics: humanum.arts.cuhk.edu.hk/Lexis/chifreq/

Do not add undocumented third-party datasets or copied content.
