# 筆畫輸入法 — Stroke Input Method

A desktop Chinese input method for Windows that lets you type Chinese characters by entering their stroke order. Built with Python and Qt (PySide6).

Type strokes using keyboard keys, pick candidates from a ranked list, and get phrase suggestions — all from a lightweight floating window that stays out of your way.

## How It Works

Chinese characters are composed of five basic stroke types. You enter strokes in writing order and the engine narrows down matching characters in real time:

| Key | Stroke | Name | Symbol |
|-----|--------|------|--------|
| J   | 橫 Horizontal | héng | 一 |
| K   | 豎 Vertical   | shù  | 丨 |
| L   | 撇 Left-falling | piě | 丿 |
| U   | 點 Dot        | diǎn | 丶 |
| I   | 折 Turning    | zhé  | 乙 |
| O   | 萬用 Wildcard | —    | ＊ |

For example, to type 大 (big), you'd press `K` `L` `U` (豎 撇 點) and select it from the candidate list.

## Features

- Trie-based prefix matching engine for fast character lookup
- Fuzzy matching — tolerates one stroke substitution when exact matches are few
- Contextual phrase suggestions after selecting a character
- Composite ranking that blends static frequency, user history, context, and match quality
- Traditional Chinese preference (slight ranking boost)
- Paginated candidate list (1–9 number keys, Page Up/Down)
- Floating borderless window — always-on-top, draggable, stays visible on focus loss
- Global hotkey toggle (default: `Ctrl+Shift+S`)
- System tray with show/hide, settings, and exit
- Settings dialog for hotkey, page size, opacity, and auto-start
- Auto-start on Windows login (registry-based)
- User frequency adaptation — characters you pick often rise in rank
- Crash recovery and resource monitoring
- Windows 10/11 compatibility layer

## Requirements

- Python 3.11+
- Windows 10 or 11

## Installation

```bash
pip install -e .
```

### Dependencies

The project uses PySide6 for the GUI and the `keyboard` library for global hotkeys. Install them if not pulled automatically:

```bash
pip install PySide6 keyboard
```

## Data Setup

The app needs two data sources:

### 1. Stroke Database

Character stroke data comes from the [Make Me a Hanzi](https://github.com/skishore/makemeahanzi) dataset. Place `dictionary.txt` and `graphics.txt` in the `data/` directory. On first run, the app parses these files and builds a serialized stroke database (`stroke_db.msgpack`).

### 2. Phrase Dictionary

A Traditional Chinese phrase dictionary (`data/phrases.tsv`) is included, sourced from CC-CEDICT (CC BY-SA 4.0). To regenerate it from the latest CEDICT data:

```bash
python scripts/generate_phrase_dict.py
```

## Usage

```bash
python -m stroke_input
```

Or after installation:

```python
from stroke_input.main import main
main()
```

### Controls

| Key | Action |
|-----|--------|
| J / K / L / U / I / O | Enter strokes |
| 1–9 | Select candidate or phrase |
| Backspace | Remove last stroke 
| Escape | Clear all strokes |
| Page Up / Page Down | Navigate candidate pages |
| Ctrl+Shift+S | Toggle input window (global) |

## Configuration

Settings are stored in `%LOCALAPPDATA%\StrokeInput\config.json` and can be edited through the settings dialog (right-click tray icon → Settings).

| Setting | Default | Description |
|---------|---------|-------------|
| `global_hotkey` | `ctrl+shift+s` | Toggle hotkey |
| `page_size` | `9` | Candidates per page (1–9) |
| `auto_start` | `false` | Launch on Windows login |
| `window_opacity` | `1.0` | Window opacity (0.1–1.0) |
| `memory_threshold_mb` | `200` | Memory limit before GC |
| `log_level` | `INFO` | Logging verbosity |

## Project Structure

```
src/stroke_input/
├── main.py                 # Application entry point
├── config/                 # Configuration, logging, autostart, crash recovery
├── data/                   # Data models, parsers, phrase loader, user frequency
├── engine/                 # Stroke engine (trie), inference (fuzzy), frequency ranker
├── gui/                    # Input window, candidate list, phrase suggestions, tray, settings
└── output/                 # Character output (keyboard simulation / clipboard)
```

## Testing

```bash
pytest
```

## License

Phrase dictionary data derived from CC-CEDICT, licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
