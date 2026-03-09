# Implementation Plan: 筆畫輸入法 (Stroke Input Method)

## Overview

Incremental implementation of a Python-based standalone stroke input method for Windows. Development proceeds from data layer → core engine → GUI → integration → robustness, ensuring each step builds on the previous and no code is left unwired.

## Tasks

- [ ] 1. Project scaffolding and data layer
  - [x] 1.1 Create project structure and core data models
    - Create directory layout: `src/stroke_input/` with subpackages `data/`, `engine/`, `gui/`, `output/`, `config/`
    - Define dataclasses: `CharacterRecord` (character, stroke_sequence: list[int], stroke_count: int, frequency: float), `PhraseEntry` (phrase: str, frequency: float)
    - Define enums: `StrokeType` (HENG=1, SHU=2, PIE=3, DIAN=4, ZHE=5, WILDCARD=6)
    - Define key mapping constants matching macOS Stroke - Traditional: J=橫(1), K=豎(2), L=撇(3), U=點(4), I=折(5), O=萬用(6)
    - Create `__init__.py` files and a `main.py` entry point stub
    - _Requirements: 1.3, 1.6_

  - [x] 1.2 Implement Make Me a Hanzi parser (`dictionary.txt` + `graphics.txt`)
    - Parse `dictionary.txt` JSON lines into character records (character, decomposition, radical, pinyin)
    - Parse `graphics.txt` JSON lines to extract `medians` coordinate sequences per stroke
    - Implement stroke classifier: analyze median start/end points and direction changes to classify each stroke as 橫(1)/豎(2)/撇(3)/點(4)/折(5)
    - Combine parsed data into `CharacterRecord` objects with stroke sequences
    - Log warnings with line numbers for malformed entries and skip them
    - _Requirements: 1.1, 1.2, 10.1, 10.2, 10.6_

  - [ ]* 1.3 Write property test for stroke classification
    - **Property 1: Stroke type completeness — every classified stroke is one of the 5 valid types (1-5)**
    - **Validates: Requirements 1.2**

  - [x] 1.4 Implement database serializer and deserializer
    - Serialize `list[CharacterRecord]` to JSON (human-readable, for debug) and msgpack (compact binary, for production)
    - Implement loader that reads JSON or msgpack back into `list[CharacterRecord]`
    - Implement pretty-printer that formats database into human-readable text
    - _Requirements: 1.6, 10.3, 10.4_

  - [ ]* 1.5 Write property test for database round-trip
    - **Property 2: Round-trip consistency — parse → serialize → parse produces equivalent records**
    - **Validates: Requirements 1.5, 10.5**

  - [ ]* 1.6 Write property test for config round-trip
    - **Property 3: Config round-trip — save → load produces equivalent configuration**
    - **Validates: Requirements 12.5**

  - [x] 1.7 Implement phrase dictionary loader
    - Load phrase data (at least 50,000 Traditional Chinese phrases) from a text/JSON source file
    - Store as a trie or dict keyed by first character for fast lookup
    - Prioritize Traditional Chinese phrases (Taiwan/Hong Kong usage)
    - _Requirements: 6.1, 6.4_

  - [x] 1.8 Implement user frequency store
    - Create `UserFreqStore` class that persists per-character selection counts to a JSON file
    - Support increment on character selection, load on startup, save on shutdown and periodically
    - _Requirements: 5.4, 13.8_

  - [x] 1.9 Implement settings/config manager
    - Define `AppConfig` dataclass: global_hotkey, page_size, auto_start, window_opacity, memory_threshold_mb, log settings
    - Load from JSON config file on startup; fall back to defaults if missing/corrupted (log warning)
    - Save config to JSON on change
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 13.5_

- [x] 2. Checkpoint — Data layer complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Core stroke engine
  - [x] 3.1 Implement prefix matching in StrokeEngine
    - Build an in-memory index (trie or dict) from `StrokeDB` for fast prefix lookup
    - `query(stroke_sequence) -> list[CharacterRecord]`: return all characters whose stroke sequence starts with the given prefix
    - Support append_stroke, remove_last_stroke (Backspace), clear_sequence (Escape)
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_

  - [ ]* 3.2 Write property test for monotonic narrowing
    - **Property 4: Monotonic narrowing — for exact prefix matches, candidate set at length N+1 is a subset of candidate set at length N**
    - **Validates: Requirements 14.4, 14.7**

  - [x] 3.3 Implement wildcard matching
    - Extend `query()` to handle WILDCARD (code 6) at any position in the stroke sequence
    - When wildcard is present, match characters where any stroke type (1-5) can occupy that position
    - Support multiple wildcards in a single sequence
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 3.4 Implement InferenceEngine (fuzzy matching + contextual boost)
    - Approximate matching: tolerate up to one stroke substitution, rank below exact matches
    - When fewer than 3 exact prefix matches exist, supplement with fuzzy matches
    - Contextual boost: after a character is selected, boost candidates that commonly follow it in the phrase dictionary
    - All matching and ranking must complete within 50ms for 9000 characters
    - _Requirements: 2.4, 14.1, 14.2, 14.3, 14.5, 14.6_

  - [ ]* 3.5 Write property test for fuzzy match ranking
    - **Property 5: Exact-before-fuzzy — exact prefix matches always rank above fuzzy matches for the same query**
    - **Validates: Requirements 2.3, 3.2, 14.2**

  - [x] 3.6 Implement FrequencyRanker (composite scoring)
    - Composite score = weighted combination of: static frequency, user adaptation score, contextual relevance, match quality (exact > fuzzy)
    - Secondary sort by stroke count (fewer strokes first) when frequency is equal
    - Traditional Chinese forms ranked above Simplified when both exist
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 1.4, 4.4_

  - [ ]* 3.7 Write unit tests for StrokeEngine and FrequencyRanker
    - Test prefix matching with known characters
    - Test wildcard matching with single and multiple wildcards
    - Test frequency ranking order
    - Test contextual boost after character selection
    - _Requirements: 2.1, 2.3, 4.2, 5.2, 5.3_

- [x] 4. Checkpoint — Core engine complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Output module
  - [x] 5.1 Implement OutputModule with keyboard simulation and clipboard fallback
    - Primary: use `pyautogui` or `win32api` to simulate keyboard input of the selected character
    - Fallback: if keyboard simulation fails, copy to clipboard via `pyperclip` and notify user
    - If clipboard fallback also fails, log error and display inline error in InputWindow
    - Clear stroke sequence after successful output
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 5.2 Write unit tests for OutputModule
    - Test keyboard simulation call path (mock pyautogui)
    - Test clipboard fallback trigger on simulation failure
    - Test error logging on double failure
    - _Requirements: 8.1, 8.2, 8.3_

- [ ] 6. GUI layer (PyQt6/PySide6)
  - [x] 6.1 Implement floating InputWindow
    - Create borderless, always-on-top `QWidget` window
    - Make window draggable (handle mouse press/move events)
    - Display stroke input area showing current sequence as stroke symbols (一丨丿丶乙)
    - Retain visibility and state when losing focus
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 6.2 Implement CandidateList display widget
    - Show up to 9 candidates per page, each labeled 1-9
    - Support Page Up / Page Down for pagination
    - Number key (1-9) selects corresponding candidate and triggers OutputModule
    - Display stroke symbols alongside numeric codes for current sequence
    - Update within 100ms when stroke sequence changes
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 6.3 Implement phrase suggestion display
    - After character selection, show associated phrases from PhraseDict as secondary suggestions
    - When a phrase is selected, output all characters at once via OutputModule
    - _Requirements: 6.2, 6.3_

  - [x] 6.4 Wire InputWindow keyboard events to StrokeEngine
    - Capture key events: stroke keys J(橫), K(豎), L(撇), U(點), I(折), wildcard O(萬用), Backspace, Escape, number keys (1-9), Page Up/Down
    - Map keyboard keys to internal stroke codes: J→1, K→2, L→3, U→4, I→5, O→6 (matching macOS Stroke - Traditional layout)
    - Route to StrokeEngine.append_stroke / remove_last / clear as appropriate
    - Trigger candidate list refresh on every stroke sequence change
    - _Requirements: 2.1, 2.2, 2.5, 2.6, 3.1, 3.5_

- [x] 7. Checkpoint — GUI and output wired
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. System tray and application lifecycle
  - [x] 8.1 Implement TrayApp with system tray icon
    - Create `QSystemTrayIcon` with context menu: Show/Hide Input Window, Settings, Exit
    - Double-click tray icon toggles InputWindow visibility
    - Graceful shutdown: release hotkeys, tray icon, window handles; persist user frequency data
    - _Requirements: 9.1, 9.2, 9.3, 13.10_

  - [x] 8.2 Implement global hotkey registration
    - Register configurable global hotkey (default: Ctrl+Shift+S) using `keyboard` library or Win32 `RegisterHotKey`
    - Toggle InputWindow visibility on hotkey press; manage focus correctly
    - Detect and notify user of hotkey conflicts
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 8.3 Implement settings dialog
    - Create `QDialog` for configuring: global hotkey, candidate page size, auto-start on login, window opacity
    - Persist changes via config manager on save
    - Accessible from tray context menu
    - _Requirements: 12.1, 12.2, 12.3_

  - [x] 8.4 Implement auto-start on Windows login
    - Add/remove registry entry or startup shortcut based on user config
    - _Requirements: 9.4, 12.2_

- [ ] 9. Robustness and stability
  - [x] 9.1 Implement Error_Logger with rotating log files
    - Configure Python `logging` with `RotatingFileHandler`: max 10 MB per file, keep last 3 files
    - Wire all components to use the centralized logger
    - _Requirements: 13.6_

  - [x] 9.2 Implement ResourceMonitor
    - Track memory usage periodically (e.g., every 60s)
    - Trigger `gc.collect()` when memory exceeds configurable threshold (default: 200 MB)
    - _Requirements: 13.1, 13.2_

  - [x] 9.3 Implement global exception handler and crash recovery
    - Install `sys.excepthook` to catch unhandled exceptions, log them, and continue operation
    - On startup: detect missing/corrupted StrokeDB file → show error message and attempt rebuild from raw data
    - Show loading indicator if database loading exceeds 5 seconds
    - Persist user frequency data on unexpected shutdown (atexit handler)
    - _Requirements: 13.3, 13.4, 13.8, 13.9_

  - [ ]* 9.4 Write integration tests for application lifecycle
    - Test startup → load config → load database → show tray icon flow
    - Test graceful shutdown resource cleanup
    - Test crash recovery: corrupted DB triggers rebuild
    - _Requirements: 13.3, 13.4, 13.10_

- [ ] 10. Final integration and wiring
  - [x] 10.1 Wire all components together in main.py
    - Initialize: load config → setup logger → load StrokeDB (with loading indicator) → load PhraseDict → load UserFreq → create StrokeEngine → create InferenceEngine → create FrequencyRanker → create OutputModule → create InputWindow → create TrayApp
    - Connect signals/slots between GUI and engine components
    - Start Qt event loop
    - _Requirements: 7.5, 9.1, 13.7_

  - [x] 10.2 Implement Windows 10/11 compatibility handling
    - Handle OS-specific API differences for tray icon, hotkey registration, and keyboard simulation
    - Test on Windows 10 (1903+) and Windows 11
    - _Requirements: 8.5, 13.7_

- [x] 11. Final checkpoint — All features integrated
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design
- Implementation language: Python with PyQt6/PySide6 (as specified in design)
