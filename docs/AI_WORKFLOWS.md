# AI Development Workflows

Use these workflows for common agent tasks.

## Environment setup

```powershell
pip install -e .
```

The package requires Python 3.11+ and uses `msgpack` as the runtime dependency.

## Run tests

```powershell
pytest
node --test chrome-extension/test/*.test.js
```

Use targeted tests while iterating, then run the full suite before finishing Python behavior changes. JS pure helpers live in `chrome-extension/engine.js` and are covered by the Node built-in test runner (no extra dependencies).

## Refresh data

Run only the scripts needed for the task:

```powershell
python scripts\download_stroke_data.py
python scripts\generate_phrase_dict.py
python scripts\generate_cantonese_data.py
python scripts\export_for_chrome.py
```

After changing exported data formats or extension-consumed data, verify that `chrome-extension\data\` is regenerated consistently.

## Package the Chrome extension

```powershell
python scripts\package_extension.py
```

This rebuilds data, validates the manifest, and creates the distributable extension zip.

## Typical task playbooks

### Engine lookup or inference change

1. Inspect relevant engine/data modules under `src\stroke_input\`.
2. Add or update focused tests under `tests\`.
3. Implement behavior in Python.
4. Run pytest.
5. Export/package only if browser data or extension behavior is affected.

### Ranking change

1. Read `src\stroke_input\engine\frequency_ranker.py`.
2. Identify expected ordering changes with concrete characters or phrases.
3. Update tests to lock the intended order or score relationship.
4. Keep scoring explainable and avoid arbitrary constants unless documented in code.

### Chrome extension behavior change

1. Inspect `chrome-extension\content.js`, `background.js`, and `style.css` as needed.
2. Keep changes small because runtime coverage is limited.
3. Validate editable target behavior for `input`, `textarea`, and `contenteditable`.
4. Run packaging validation when manifest/data/assets are involved.

### Data generation change

1. Inspect the relevant script in `scripts\`.
2. Confirm source data and license implications.
3. Update parsing/export tests when possible.
4. Regenerate outputs intentionally and document the command used.
