# DevMind

A local-first AI engineering workbench. Index a codebase, search it
semantically, and ask questions about it. Everything runs on your machine
with [Ollama](https://ollama.com); no cloud AI APIs.

## How it works

1. **Ingest:** Tree-sitter splits source files into function/class/method chunks with line numbers.
2. **Embed:** Ollama (`nomic-embed-text`) embeds each chunk, and vectors are stored in SQLite.
3. **Retrieve:** the question is embedded and the closest chunks are ranked using hybrid semantic + keyword search.
4. **Answer:** `llama3.2:1b` answers using only the retrieved code, with file and line-number citations.
5. **Conversation:** Q&A turns are persisted in SQLite with conversation IDs for multi-turn context.
6. **Stream:** AI responses stream progressively from Ollama via Server-Sent Events.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/EVALUATION.md](docs/EVALUATION.md).

## Prerequisites

Use Python 3.12 and Node.js 22 (the same runtime versions used in CI).
The root `.python-version` and `.nvmrc` files record these versions.

Install [Ollama](https://ollama.com/download), then download both required
models:

```bash
ollama pull llama3.2:1b
ollama pull nomic-embed-text
```

## Run locally (development)

Repository paths are restricted to `~/projects` by default. Create that
directory and put the repositories you want to index beneath it, or set
`DEVMIND_ALLOWED_ROOT` to a different existing directory you own.

```bash
# Create the local repository allowlist root.
mkdir -p "$HOME/projects"

# Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DEVMIND_ALLOWED_ROOT="$HOME/projects" python app.py  # http://127.0.0.1:5000

# Frontend (new terminal)
cd frontend
npm ci
npm run dev                        # http://localhost:3000
```

For production or shared environments, set both `DEVMIND_ENV=production` and
an explicit `DEVMIND_ALLOWED_ROOT` pointing to an existing directory. Startup
does not disable path restrictions when that value is missing or invalid.

The backend creates the SQLite database automatically at
`backend/data/devmind.db`; set `DEVMIND_DATA_DIR` to change its containing
directory. Other backend settings are `OLLAMA_URL` (default
`http://127.0.0.1:11434`), `CHAT_MODEL` (default `llama3.2:1b`),
`EMBED_MODEL` (default `nomic-embed-text`), `HOST`, and `PORT`. `DEVMIND_ENV`
defaults to `development`; `DEVMIND_ALLOWED_ROOT` defaults to
`~/projects` only in development.

## API rate limiting

Write endpoints (`/ingest`, `/search`, `/explain`, `/chat`) are rate limited
to protect against excessive requests. Limits are configurable via environment
variables:

| Variable | Default | Endpoint |
|----------|---------|----------|
| `DEVMIND_RATE_LIMIT_INGEST` | 30/minute | `/ingest` |
| `DEVMIND_RATE_LIMIT_SEARCH` | 60/minute | `/search` |
| `DEVMIND_RATE_LIMIT_EXPLAIN` | 60/minute | `/explain` |
| `DEVMIND_RATE_LIMIT_CHAT` | 60/minute | `/chat` |

Health (`/health`) and readiness (`/ready`) endpoints are never rate limited.

When a rate limit is exceeded, the API returns HTTP 429 with a JSON error:

```json
{
  "error": "Too many requests. Please slow down and try again later."
}
```

The rate limiter is in-memory and per-process. In a multi-worker or
multi-container deployment, each instance tracks limits independently. For
single-instance local development (the intended use case), this is sufficient.

## Conversations

The Code Assistant supports multi-turn conversations with persistent history:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVMIND_RATE_LIMIT_CONVERSATION` | 120/minute | Conversation API endpoints |
| `DEVMIND_MAX_CONVERSATION_MESSAGES` | 50 | Max messages sent as context per turn |
| `DEVMIND_MAX_CONTEXT_CHUNKS` | 5 | Max search results used as answer context |
| `DEVMIND_MAX_SEARCH_RESULTS` | 10 | Max search results returned by `/search` |

### Conversation API

- `POST /conversations` — Create a new conversation (optional `repo_path`).
- `GET /conversations` — List all conversations, most recent first.
- `GET /conversations/<id>` — Get a conversation with all its messages.
- `DELETE /conversations/<id>` — Delete a conversation and its messages.
- `POST /chat` — Ask a question. Include `conversation_id` to continue an
  existing conversation; omit it to start a new one.

Each assistant response includes:
- `response` — the answer text
- `sources` — array of `{file_path, symbol, start_line, end_line, score}`
- `conversation_id` — the conversation ID (use this for follow-up turns)
- `citation_keys` — citation patterns found in the answer

### Citation format

Citations use the format `[FILE:path:line]` and reference specific source
files with line numbers. Example:

```
[FILE:src/auth.py:42]
```

In the frontend, citations are clickable and open the source file at the
referenced line.

## Streaming AI responses

Chat responses stream progressively from Ollama using Server-Sent Events
(SSE). The `/chat/stream` endpoint accepts the same request body as `/chat`
and returns `text/event-stream` with JSON data lines containing:
`{"text": "...", "done": bool, "sources": [...], "conversation_id": "...", "citation_keys": [...]}`.

The frontend displays generated text progressively and supports cancellation
via AbortController. Interrupted streams are handled gracefully — cancelled
requests do not leave incomplete assistant messages presented as successful
answers.

Rate limit: `DEVMIND_RATE_LIMIT_STREAM` (default: 60/minute).

## Conversation export and import

Conversations can be exported as JSON or Markdown and imported back:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVMIND_RATE_LIMIT_CONVERSATION` | 120/minute | Conversation API endpoints |

### Conversation API

- `POST /conversations` — Create a new conversation (optional `repo_path`).
- `GET /conversations` — List all conversations, most recent first.
- `GET /conversations/<id>` — Get a conversation with all its messages.
- `DELETE /conversations/<id>` — Delete a conversation and its messages.
- `GET /conversations/<id>/export?format=json|markdown` — Export a conversation.
- `POST /conversations/import` — Import a conversation from JSON.
- `POST /chat` — Ask a question. Include `conversation_id` to continue an
  existing conversation; omit it to start a new one.
- `POST /chat/stream` — Stream an AI response using SSE.

### Citation format

Citations use the format `[FILE:path:line]` and reference specific source
files with line numbers. Example:

```
[FILE:src/auth.py:42]
```

In the frontend, citations are clickable and open the source file at the
referenced line.

## Multi-repository intelligence

The `/search` endpoint supports searching across multiple repositories:

- `repo_path` (string, backward compatible) — Search a single repository.
- `repo_paths` (array of strings) — Search across multiple repositories.

Each result includes a `repo_path` field indicating which repository it came
from. Repository isolation is maintained — results never mix repositories
accidentally. All repository paths are validated against `DEVMIND_ALLOWED_ROOT`.

The frontend displays repository labels on search results and citations, and
supports selecting multiple repositories for comparison queries.

## Streaming architecture

The streaming endpoint uses Ollama's native streaming capability
(`stream: true`) and forwards text chunks via Server-Sent Events. Each SSE
data line contains a JSON object with the incremental text, a `done` flag,
sources, conversation ID, and citation keys. The frontend accumulates chunks
and persists the complete message when `done` is true.

- A failed re-index never destroys a previously valid index. Embeddings are
  generated before the existing index is replaced; if Ollama fails, the old
  index remains intact.
- Database changes are atomic: chunks and embedding metadata are written in a
  single transaction.
- Embeddings are validated before persistence (count match, non-zero
  dimensions, consistent dimensions across all chunks).
- Transient Ollama connection failures are retried with exponential backoff
  (up to 3 attempts).
- Binary files are automatically skipped during ingestion.
- Concurrent ingestion of the same repository is serialized per repository.

## SQLite concurrency

- WAL (Write-Ahead Logging) journal mode is enabled for concurrent reads.
- A 30-second busy timeout handles transient lock contention.
- Retry logic handles `database is locked` errors with up to 3 attempts.
- SQLite does not support connection pooling; each request opens its own
  connection. For high-concurrency deployments, consider running a single
  backend instance.

The `/health` endpoint is a liveness check and does not depend on Ollama.
`/ready` checks SQLite, Ollama connectivity, and both required models; it
returns HTTP 503 with per-check statuses when a dependency is unavailable or
a model is missing.

## Frontend testing

Run frontend unit tests with Vitest:

```bash
cd frontend
npm test
```

Tests mock network requests and do not require a running Ollama instance.

## End-to-end testing

Run browser-based E2E tests with Playwright:

```bash
cd frontend
npm run test:e2e
```

E2E tests mock API calls and do not require a running backend or Ollama instance.

## Logging and observability

The backend logs structured events for each request, including a unique
request ID, method, path, status code, and duration. Ingestion logs include
files discovered, files skipped, chunks indexed, embedding duration, and
database write duration. Database lock retries are logged as warnings.

Logs never include absolute filesystem paths, API secrets, or internal
exception traces.

## Ingestion reliability

- A failed re-index never destroys a previously valid index. Embeddings are
  generated before the existing index is replaced; if Ollama fails, the old
  index remains intact.
- Database changes are atomic: chunks and embedding metadata are written in a
  single transaction.
- Embeddings are validated before persistence (count match, non-zero
  dimensions, consistent dimensions across all chunks).
- Transient Ollama connection failures are retried with exponential backoff
  (up to 3 attempts).
- Binary files are automatically skipped during ingestion.
- Concurrent ingestion of the same repository is serialized per repository.

## SQLite concurrency

- WAL (Write-Ahead Logging) journal mode is enabled for concurrent reads.
- A 30-second busy timeout handles transient lock contention.
- Retry logic handles `database is locked` errors with up to 3 attempts.
- SQLite does not support connection pooling; each request opens its own
  connection. For high-concurrency deployments, consider running a single
  backend instance.

## Run with Docker

Ollama runs on the host, so it must listen on an address the container can
reach:

```bash
OLLAMA_HOST=0.0.0.0 ollama serve
```

Put (or symlink) the projects you want to index in one folder, then:

```bash
export DEVMIND_PROJECTS_DIR=$HOME/projects
docker compose up --build
```

For a reproducible Compose setup, copy `.env.example` to `.env` and set
`DEVMIND_PROJECTS_DIR` to an absolute path. Inside Docker, the permitted path
is `/repos`; Ollama is reached through `OLLAMA_URL` (default
`http://host.docker.internal:11434`).

Open http://localhost:3000 and enter the path **as the container sees it**,
for example `/repos/my-project`.

## Security notes

- Only the folder in `DEVMIND_PROJECTS_DIR` is mounted (read-only). In local
  development, repository paths must resolve inside `~/projects` or the
  configured `DEVMIND_ALLOWED_ROOT`; Docker restricts paths to `/repos`.
- The API resolves canonical paths before checking access, so parent traversal
  and symlinks escaping the allowed root are rejected.
- Docker publishes ports on `127.0.0.1` only. There is no authentication, so
  do not expose the API to a network.
- If you expose Ollama with `OLLAMA_HOST=0.0.0.0`, firewall port 11434.

## Tests and evaluation

```bash
cd backend && . .venv/bin/activate && python -m pytest -q
python -m compileall -q backend
cd ../frontend && npm run lint && npm run build && npm test
npm run test:e2e
npm audit --audit-level=high
```

Retrieval evaluation suite:

```bash
cd backend && . .venv/bin/activate && python -m pytest tests/test_retrieval_eval.py -q
```

The evaluation uses a synthetic test repository with known structure and
mocked embeddings. It verifies:

- Relevant-file retrieval (expected source is found)
- No duplicate results (deduplication by file_path + symbol)
- Result diversity across multiple files
- Citation validity (line numbers present for Tree-sitter parsed files)
- Deterministic retrieval (same query = same results)
- Hybrid search finds keyword matches

The evaluation mocks Ollama and does not require a running model.

## Prompt-injection protections

Repository files are treated as untrusted data:

- Retrieved repository content is never treated as privileged instructions.
- System instructions cannot be overridden by content embedded in source
  files, comments, or documentation.
- Environment variables, API keys, credentials, and secrets are never exposed.
- Repository code is never executed; no shell commands are run.
- Repository files are never modified by the assistant.
- Absolute host paths are never exposed in responses.
- Error messages are sanitized before being returned to clients.

Tests for prompt-injection attempts in repository files are included in
`backend/tests/test_conversations.py`.

## Known limitations

- Indexing is synchronous and re-indexes the whole repository each time.
- Embeddings are stored as JSON in SQLite and compared in memory; this suits
  small and medium repositories, not large vector workloads.
- A 1B-parameter model can still give weak or wrong answers; always check the
  cited sources.
- The API rate limiter is in-memory and per-process. In multi-worker or
  multi-container deployments, each instance tracks limits independently.
- Seven moderate-severity `minimatch` vulnerabilities (GHSA-g3hv-75wg-m249)
  remain in the frontend dependency chain via `@typescript-eslint` v8, which
  is the maximum version supported by `eslint-config-next` for Next.js 16. No
  patched version of `minimatch` exists within the affected range (7.0.0–11.0.0),
  and no `@typescript-eslint` v9 exists. This requires a future `@typescript-eslint`
  v9 release to resolve.
- Conversation history is limited to the most recent 50 messages per turn.
- Retrieval uses hybrid semantic + keyword search; results are deterministic
  but may miss relevant code if the embedding model doesn't capture it.
