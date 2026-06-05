# AI Background

This document gives AI agents the context needed to work safely in this repository.

## Product goal

The project provides a Chinese stroke-based input method optimized for Traditional Chinese and Cantonese usage. Users type stroke sequences with keyboard keys and receive ranked Chinese character and phrase candidates in real time.

## User-facing surfaces

### Chrome extension

The main product surface is `chrome-extension\`. It runs as a Manifest V3 extension and injects an overlay into editable web fields. Important files:

- `manifest.json`: extension metadata and permissions
- `background.js`: service worker and cross-tab state synchronization
- `content.js`: input handling, candidate search, ranking, phrase suggestion, and overlay behavior
- `style.css`: overlay presentation
- `data\*.json`: exported lookup/ranking data consumed at runtime

### Python engine and tooling

The Python package in `src\stroke_input\` is the source of truth for engine behavior and data processing:

- `data\models.py`: core character and stroke data structures
- `data\parser.py`: source stroke-data parsing
- `data\serializer.py`: msgpack persistence
- `data\phrase_loader.py`: phrase dictionary loading
- `data\user_freq_store.py`: user adaptation storage
- `engine\stroke_engine.py`: trie-based prefix search and wildcard lookup
- `engine\inference_engine.py`: fuzzy inference and contextual phrase support
- `engine\frequency_ranker.py`: composite candidate scoring

## Data pipeline

The repository has both source and generated data. Treat generated files carefully.

1. `scripts\download_stroke_data.py` obtains/parses Conway stroke data.
2. `scripts\generate_phrase_dict.py` builds Traditional Chinese phrase data from CC-CEDICT-derived sources.
3. `scripts\generate_cantonese_data.py` creates Cantonese frequency, phrase, and bigram data.
4. `scripts\export_for_chrome.py` exports optimized JSON into `chrome-extension\data\`.
5. `scripts\package_extension.py` rebuilds/validates/package the extension.

## Ranking and inference intent

Candidate ordering blends several concerns:

- exact/prefix stroke match quality
- static frequency
- Traditional Chinese preference
- Cantonese frequency boosts
- user frequency adaptation
- previous-character context and bigram scores
- phrase suggestions after character selection

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

Do not add undocumented third-party datasets or copied content.
