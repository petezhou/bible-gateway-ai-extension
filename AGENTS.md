# Project guidance

## Overview

BibleGateway Chrome extension with a local FastAPI backend. The extension sends
selected verse references and conversation history to the backend, which retrieves
ESV text and historic commentary and calls Anthropic for answers.

## Layout

- `backend/`: API, reference parsing, source retrieval, profiles, and prompts.
- `extension/`: unpacked Manifest V3 extension, selection UI, and settings.
- `scripts/`: source extraction and extension dependency packaging.
- `tests/`: backend unit tests and Playwright extension tests.
- `README.md`: setup, API behavior, and current implementation checkpoint.

## Working conventions

- Read `README.md` before changing behavior. Keep changes scoped to the request.
- Reproduce bugs through the user-facing flow before implementing fixes.
- Use spaces: 4 for Python and 2 for JavaScript and JSON. Match existing style.
- Use plain dashes, never em dashes.
- Keep secrets in ignored `.env`; never print, commit, or put keys in the extension.
- Preserve local commentary data and source documents; they are ignored assets.
- Do not manually edit generated `extension/vendor/markdown.js`; rebuild it with
  `npm run vendor:extension`. Preserve dependency license files.
- Do not manually edit changelogs or other generated files.
- Stay on the current branch. Leave changes uncommitted unless asked to commit.
- Tests should follow Arrange-Act-Assert; parameterize where existing style allows.
- Avoid live provider calls during routine checks because they incur charges.

## Validation

Run checks relevant to the change:

```sh
.venv/bin/python -m unittest discover -s tests -v
npm run test:extension
```

Install JavaScript dependencies with `npm ci` and browser binaries with
`npx playwright install chromium` when needed. Extension tests use a synthetic
passage and mock backend. For manual testing, run the backend on port 8001, reload
the unpacked extension, and refresh the BibleGateway tab. See `README.md` for details.
