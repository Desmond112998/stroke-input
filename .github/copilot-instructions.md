# Copilot Instructions

Use `AGENTS.md` as the primary project guide.

Before changing behavior, review:

- `README.md`
- `docs\AI_BACKGROUND.md`
- `docs\AI_RULES.md`
- relevant tests in `tests\`

Project priorities:

1. Preserve input-method correctness and predictable candidate ranking.
2. Keep generated data and extension runtime formats in sync.
3. Prefer tested changes in the Python engine before mirroring behavior in the Chrome extension.
4. Avoid broad rewrites of `chrome-extension\content.js`; make surgical changes and validate manually or with packaging checks.
5. Respect third-party data licenses documented in `README.md`.

Common commands:

```powershell
pip install -e .
pytest
python scripts\export_for_chrome.py
python scripts\package_extension.py
```
