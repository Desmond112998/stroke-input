# 筆畫輸入法 — Stroke Input Method

A Chinese stroke-based input method available as a **Chrome extension** and a **Python engine library**. Type Chinese characters by entering their stroke order — five basic strokes mapped to keyboard keys, with real-time candidate matching, phrase suggestions, and Cantonese-optimized ranking.

## Chrome Extension

The primary interface is a Chrome extension that works in any text field on any webpage. A floating overlay shows stroke input, candidates, and phrase suggestions without leaving the browser.

### Features

- Five basic strokes (J/K/L/U/I/O) plus wildcard key
- Real-time prefix matching with binary search on a sorted stroke index
- Fuzzy one-stroke correction when exact matches are scarce (< 3)
- Optional 五筆劃 (頭四尾一) short codes for characters with more than 5 strokes
- Mid-typing association characters from bigrams (marked 聯)
- Composite ranking: static frequency, user adaptation, bigram/trigram context, recency, position
- Cantonese frequency boosts — common Cantonese characters (係、唔、咗、嘅、冇…) rank higher
- Bigram model for contextual prediction (P(char₂ | char₁) from phrase co-occurrence)
- Phrase suggestions after character selection (Cantonese collocations included)
- Compatible with multiple stroke order standards (macOS, Nokia, Conway)
- User frequency adaptation persisted via `chrome.storage`
- Shift to toggle Chinese/English mode; configurable toggle key (default backtick `` ` ``) to toggle on/off
- Options page: toggle key, password fields, 五筆劃, associations, numpad strokes, Chinese punctuation
- Arrow key navigation (◀▶ to highlight candidates, ▲▼ to page)
- Works with `<input>`, `<textarea>`, and `contenteditable` elements (password fields off by default)
- Overlay follows the caret / text field (drag once to pin a manual position)
- Global state sync across all tabs via background service worker
- Lightweight — no special permissions; usage stats stay in local extension storage only

### Key Mapping

| Key | Stroke | Name | Symbol |
|-----|--------|------|--------|
| J   | 橫 Horizontal | héng | 一 |
| K   | 豎 Vertical   | shù  | 丨 |
| L   | 撇 Left-falling | piě | 丿 |
| U   | 點 Dot        | diǎn | 丶 |
| I   | 折 Turning    | zhé  | 乙 |
| O   | 萬用 Wildcard | —    | ＊ |

### Controls

| Key | Action |
|-----|--------|
| Toggle key (default `` ` ``) | Toggle input method on/off (configurable in extension options) |
| Shift | Toggle Chinese / English mode |
| J / K / L / U / I / O | Enter strokes (only when a text field is focused; never with Ctrl/Cmd/Alt) |
| Numpad 1–6 | Same strokes when「數字鍵盤輸入筆畫」is enabled in options |
| `,` `.` `?` `!` `;` `:` | Full-width Chinese punctuation when buffer is empty (option; default on) |
| 1–9 | Select candidate or phrase |
| ◀ / ▶ | Highlight prev/next candidate |
| ▲ / ▼ | Previous / next page |
| Space | Confirm highlighted candidate (or the only candidate) |
| Page Down | Next page |
| Page Up | Previous page (only while composing) |
| Enter | Confirm highlighted candidate |
| Backspace | Remove last stroke (or dismiss phrases) |
| Escape | Clear composition (only while composing; page Escape otherwise) |

### Installation

Install from the Chrome Web Store, or load unpacked from the `chrome-extension/` directory for development.

### Packaging

```bash
python scripts/package_extension.py
```

This rebuilds the stroke database, exports data, validates the manifest, and produces `stroke-input-extension.zip` ready for Web Store upload.

## Python Engine Library

The `stroke_input` package provides the core engine, data tools, and ranking logic used to build the extension's data files.

### Engine Architecture

- **StrokeEngine** — trie-based prefix matching for fast character lookup with wildcard support
- **InferenceEngine** — fuzzy matching (one-stroke substitution when exact matches < 3) and contextual phrase boosting
- **FrequencyRanker** — composite scoring blending static frequency, user history, context, and match quality with Traditional Chinese preference

### Requirements

- Python 3.11+
- `msgpack` (only runtime dependency)

### Installation

```bash
pip install -e .
```

### Data Setup


#### Stroke Database

Character stroke data comes from [Conway's stroke data](https://github.com/stroke-input/stroke-input-data) (CC-BY-4.0). The raw file `data/codepoint-character-sequence.txt` is parsed into a serialized database (`data/stroke_db.msgpack`).

```bash
python scripts/download_stroke_data.py
```

#### Phrase Dictionary

A Traditional Chinese phrase dictionary (`data/phrases.tsv`) sourced from CC-CEDICT (CC BY-SA 4.0):

```bash
python scripts/generate_phrase_dict.py
```

#### Cantonese Data

Generates Cantonese frequency overrides, phrase dictionary (with Cantonese collocations), and bigram model:

```bash
python scripts/generate_cantonese_data.py
```

#### Export for Chrome

Exports the stroke database with Cantonese frequency boosts as sorted JSON for the extension's binary search:

```bash
python scripts/export_for_chrome.py
```

### Testing

```bash
pytest
node --test chrome-extension/test/*.test.js
```

Regenerate the Python↔JS ranking parity fixture (documents weight drift until T1.5):

```bash
python scripts/generate_parity_fixture.py
```

## Project Structure

```
chrome-extension/           # Chrome extension (Manifest V3)
├── manifest.json           # Extension manifest
├── background.js           # Service worker for global state sync
├── engine.js               # Pure search/ranking/phrase helpers (Node-testable)
├── content.js              # Input handling, UI, chrome.* wiring
├── options.html / options.js
├── style.css               # Overlay styling
├── STORE_LISTING.md        # Chrome Web Store copy
├── test/                   # Node built-in test runner (node --test)
└── data/                   # Exported JSON data files
    ├── strokes.json        # Sorted [sequence, char, freq, scriptTag?]
    ├── strokes_wubi.json   # 五筆劃 short codes (頭四尾一), optional mode
    ├── phrases.json        # Phrase dict indexed by first char
    ├── bigrams.json        # Bigram model {char1: {char2: score}}
    ├── trigrams.json       # Trigram model {p2: {p1: {char: score}}}
    ├── ranking_config.json # Shared ranking weights (Python↔JS)
    └── cantonese_freq.json # Cantonese frequency overrides

src/stroke_input/           # Python engine library
├── config/                 # Shared ranking / Zipf / n-gram constants
├── data/                   # Models, phrase loader, serializer, n-grams, user freq
└── engine/                 # StrokeEngine (trie), InferenceEngine (fuzzy), FrequencyRanker

scripts/                    # Data generation and build tools
├── download_stroke_data.py # Download and parse Conway stroke data
├── generate_phrase_dict.py # Generate phrase dictionary from CC-CEDICT
├── generate_cantonese_data.py # Generate Cantonese freq, phrases, bigrams
├── export_for_chrome.py    # Export stroke DB + n-grams + ranking_config for extension
├── package_extension.py    # Package extension zip for Web Store
├── generate_parity_fixture.py # Python↔JS ranking parity fixture
├── generate_icons.py       # Generate extension icons
├── generate_screenshots.py # Promotional Web Store screenshots (Pillow)
└── check_keys.py           # Dev helper: print keyboard library key names
```

### Known limitations

- Cross-origin iframes, closed Shadow DOM, and canvas-based editors (e.g. Google Docs) are not supported; the overlay only targets normal editable fields in the page.
## License

- Stroke data: [Conway Stroke Data](https://github.com/stroke-input/stroke-input-data) (CC-BY-4.0)
- Phrase dictionary: derived from [CC-CEDICT](https://cc-cedict.org/) (CC BY-SA 4.0)
