# AI Development Rules

Follow these repository-specific rules when implementing changes.

## Code changes

- Keep changes focused on the requested behavior.
- Prefer modifying the Python engine and tests first when behavior is shared with the extension.
- Do not silently change public key mappings, shortcuts, data formats, or ranking defaults.
- Keep Python code compatible with Python 3.11+.
- Keep extension code compatible with Chrome Manifest V3 and standard browser APIs available to content scripts.
- Avoid new runtime dependencies unless the task clearly requires them.

## Data files

- Treat these as generated outputs unless the task is specifically about data refresh/export:
  - `data\stroke_db.msgpack`
  - `data\strokes.json`
  - `chrome-extension\data\*.json`
- If regenerated data changes, explain which script produced it.
- Do not add large new source datasets without documenting source, license, and generation path.

## Testing

- Add or update pytest tests for engine/data behavior changes.
- Run `pytest` after Python changes.
- Run `python scripts\package_extension.py` after extension manifest, exported data, packaging, or browser asset changes when feasible.
- For JavaScript behavior in `content.js`, prefer small changes and manually reason through editable target types: `input`, `textarea`, and `contenteditable`.

## UX and language behavior

- Preserve real-time responsiveness in the extension overlay.
- Candidate ordering is user-visible; avoid score tweaks without clear rationale.
- Preserve Traditional Chinese and Cantonese optimization unless intentionally changing scope.
- Be careful with fallback behavior: fuzzy matching should improve suggestions without hiding exact matches.

## Error handling

- Surface data parsing/export errors clearly.
- Do not add broad catches that hide malformed data or extension initialization failures.
- Keep validation strict for generated browser data so broken packages fail early.

## Documentation

- Update `README.md` when changing setup, commands, key mappings, controls, packaging, or user-visible features.
- Update `docs\AI_BACKGROUND.md` when architecture or data flow changes.
- Update this file when adding project conventions agents should follow.
