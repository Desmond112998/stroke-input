# AI Agent Guide

This file is the root instruction entry point for AI coding agents working on this repository.

## Project snapshot

`stroke-input` is a Chinese stroke input method delivered as both:

- a Chrome Manifest V3 extension in `chrome-extension\`
- a Python 3.11+ engine and data tooling package in `src\stroke_input\`

The project maps five basic Chinese strokes to keyboard keys, performs prefix/fuzzy lookup, ranks candidates with frequency/context/user adaptation, and exports optimized JSON data for the browser extension.

Read these files before making substantial changes:

- `README.md` for user-facing behavior, setup, and project structure
- `docs\AI_BACKGROUND.md` for architecture and data-flow context
- `docs\AI_RULES.md` for repository-specific engineering rules
- `docs\AI_WORKFLOWS.md` for common development and validation commands

## High-level architecture

- `src\stroke_input\data\`: parsing, models, phrase loading, serialization, user frequency storage
- `src\stroke_input\engine\`: trie lookup, fuzzy inference, and ranking logic
- `scripts\`: data download, generation, export, packaging, and asset helpers
- `data\`: source and generated engine data
- `chrome-extension\`: browser runtime, UI, exported data, and store assets
- `tests\`: pytest coverage for engine/data behavior

## Working rules

- Preserve compatibility between Python engine outputs and `chrome-extension\data\*.json`.
- Do not edit generated data files unless the task explicitly requires regenerated data.
- Do not change keyboard mappings, ranking behavior, or extension shortcuts without updating tests/docs.
- Keep Python code compatible with Python 3.11+.
- Keep extension code compatible with Chrome Manifest V3.
- Prefer small, focused changes with tests that cover behavior.

## Validation

Use the existing project commands:

```powershell
pytest
python scripts\package_extension.py
```

Run the narrowest meaningful validation for the change. For data/export/extension packaging changes, run the packaging script when feasible.
