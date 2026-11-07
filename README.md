# BibleGateway AI extension

Local Bible study backend using ESV chapter text, historic commentary, and
Westminster Shorter Catechism context. Highlight verses on BibleGateway to open a
chat with the local backend.

## Run locally

Use Python 3.11 or newer. From the project directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Create `.env` using `.env.example` as a guide. If `.env` already exists, edit it
without overwriting existing keys. Set `ESV_API_KEY` to the bare ESV key and
`ANTHROPIC_API_KEY` to your Anthropic API key. Optionally set `ANTHROPIC_MODEL`;
the default is `claude-sonnet-5-5`. Environment variables override `.env`.

```dotenv
ESV_API_KEY=your-esv-key
ANTHROPIC_API_KEY=your-anthropic-key
ANTHROPIC_MODEL=claude-sonnet-5-5
```

Do not include `Authorization: Token` in the ESV value; the backend adds the
authorization header. Both API keys were configured in this local workspace
during setup. Actual key values are not included in this README.

The local assets `backend/data/commentary.db` and
`backend/documents/westminster-shorter-catechism.md` must exist. They are already
present in this workspace; a fresh copy needs the extraction scripts under `scripts/`.

```sh
.venv/bin/python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8001
```

Open http://127.0.0.1:8001/docs to try the API. `/health` reports missing keys;
the server can start without keys, but generation returns HTTP 503 until both
are configured. Restart the server after changing `.env`.
Port 8001 is the shared default for these instructions and the extension. If you
use another port, update the URLs and the extension's server setting together.
Allow up to three minutes for generation requests when configuring an HTTP client.

## Requests

```sh
curl http://127.0.0.1:8001/health
curl --max-time 240 http://127.0.0.1:8001/summary \
  -H 'Content-Type: application/json' \
  -d '{"reference":"John.3"}'
curl --max-time 240 http://127.0.0.1:8001/chat \
  -H 'Content-Type: application/json' \
  -d '{"reference":"John.3.16","question":"Who is the world here?"}'
```

References use OSIS: `John.3`, `John.3.16`, or `John.3.14-John.3.19`.
Cross-chapter ranges are unsupported. Both endpoints accept optional `tradition`
and `reading_level` fields. The default tradition is `westminster-pca`; levels
are `lay-devotional` (default), `pastor`, and `scholar`.

For a question about contiguous verses, send the complete OSIS range:

```json
{
  "reference": "John.3.14-John.3.19",
  "question": "How does the bronze serpent connect to belief in Jesus?"
}
```

The backend retrieves the full chapter for context and gathers commentary notes
overlapping the selected range, preserving the notes' original verse spans.

Chat accepts `history`, an array of alternating `user` and `assistant` messages
with `role` and `content`, ending with an assistant reply. Send completed turns
for the same passage, followed by the new `question`. Clear history when changing
the passage. The server does not persist conversations.

```json
{
  "reference": "John.3.14-John.3.19",
  "question": "How do those interpretations differ?",
  "history": [
    {
      "role": "user",
      "content": "How does the bronze serpent connect to belief in Jesus?"
    },
    {
      "role": "assistant",
      "content": "Replace this with the previous response's text."
    }
  ]
}
```

History accepts up to ten completed user/assistant pairs. The extension manages
this history automatically and sends the most recent ten pairs.

Responses contain Markdown `text`, reference, translation, supplied sources,
omitted commentary modules, model, prompt version, and token usage. Supplied
sources describe model context, not a guarantee that the answer cites each source.
Generation requests make billable Anthropic calls; health checks do not.

## Load the development extension

Start the backend on port 8001 (the extension's default):

```sh
.venv/bin/python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8001
```

1. Open `chrome://extensions` and enable **Developer mode**.
2. Click **Load unpacked** and select this project's `extension/` directory.
3. Open or refresh a BibleGateway passage, for example
   https://www.biblegateway.com/passage/?search=John+3&version=NIV.
4. Drag to highlight words across one or more contiguous verses in one chapter.
5. Click **Ask AI** beside the highlight toolbar. Enter a question or click
   **Summarize**. Use the same panel for follow-up questions.

Partial verse highlights include the full verses they touch. A new verse range
starts a new conversation. Chat stays in this tab until you reload the page.
Answers use backend ESV text regardless of the page's translation. Cross-chapter
and multiple-translation selections show an explanation instead of sending a request.

Click the extension's toolbar icon, or **Details > Extension options**, to change
the local server address if you use another port. No API keys go in the extension.

The extension uses a background service worker to call the local server. Its UI
has separate styles in a shadow root, and Markdown answers are rendered with
packaged Marked and DOMPurify libraries. The highlight action anchors beside the
native toolbar when available and falls back to the text selection. Enter sends
a question; Shift+Enter inserts a new line. Errors preserve the question for retry.

After editing extension files, click **Reload** on its card in `chrome://extensions`,
then refresh the BibleGateway tab. The packaged extension includes its Markdown
libraries and needs no build step to load. To rebuild those libraries:

```sh
npm ci
npm run vendor:extension
```

## Checks and checkpoint

```sh
.venv/bin/python -m unittest discover -s tests -v
npm ci
npx playwright install chromium
npm run test:extension
```

### Checkpoint: October 13, 2026

The local prototype is implemented and ready for manual feedback. Both servers
on ports 8000 and 8001 were stopped at the user's request. Start the server using
the command above before trying the extension again.

Completed:

- Extracted Matthew Henry's Concise Commentary, Jamieson-Fausset-Brown, and
  Geneva Bible Notes. Extraction checkpoints cover all 66 books and 1,189
  chapters per source. Westminster Shorter Catechism text is present locally.
- Implemented book/reference parsing, ESV retrieval and process-lifetime caching,
  commentary lookup with accurate verse spans, and tradition/reading-level profiles.
- Implemented source-attributed summary and chat prompts with cacheable context.
- Added FastAPI health, summary, and chat endpoints with input validation,
  configuration reporting, provider errors, source metadata, and token usage.
- Built the unpacked Manifest V3 Chrome extension with highlight detection,
  floating Ask AI action, chat panel, summaries, follow-up history, sanitized
  Markdown, and configurable local server address.

Verification completed during implementation on October 12:

- Seven backend test methods passed with real commentary data and mocked providers.
- Nine browser checks passed using the actual unpacked extension, a synthetic
  passage, and a mock local server. Coverage includes partial verse selections,
  multiple verses, numbered books, history, new selections, invalid selections,
  provider errors/retry, Markdown sanitization, toolbar placement, and a delayed answer.
- Live ESV retrieval and live backend summary/chat requests succeeded.
- A mouse-drag highlight on live BibleGateway NIV selected John 3:10-12 correctly,
  opened the chat panel, and received an answer through the extension and local API.

Remaining limits and next steps:

- Collect manual feedback on highlight placement and the chat interaction.
- Selections must be contiguous and stay within one chapter and one translation
  panel. Partial highlights expand to the full verses they touch.
- The backend always uses ESV reference text; other page translations are not
  fetched by the backend. Reformed/Westminster is the only implemented tradition.
- Conversations are held in the tab and are lost on refresh. Changing the selected
  verse range starts a new conversation. Responses arrive as complete answers.
- This is an unpacked development extension; it has not been published to the
  Chrome Web Store.

Project layout: `backend/` contains the API and study logic, `extension/` contains
the loadable Chrome extension, `scripts/` contains data extraction/prompt inspection
and library build tools, and `tests/` contains backend and extension checks.
This workspace had no Git repository or project `AGENTS.md` when work began.
No commits were made; this README is the project handoff/checkpoint.
