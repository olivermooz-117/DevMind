# DevMind

A local-first AI engineering workbench. Index a codebase, search it
semantically, and ask questions about it. Everything runs on your machine
with [Ollama](https://ollama.com); no cloud AI APIs.

## How it works

1. **Ingest:** Tree-sitter splits source files into function/class/method chunks.
2. **Embed:** Ollama (`nomic-embed-text`) embeds each chunk, and the vectors are stored in SQLite.
3. **Retrieve:** the question is embedded and the closest chunks are ranked by cosine similarity.
4. **Answer:** `llama3.2:1b` answers using only the retrieved code and lists its sources.

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

The `/health` endpoint is a liveness check and does not depend on Ollama.
`/ready` checks SQLite, Ollama connectivity, and both required models; it
returns HTTP 503 with per-check statuses when a dependency is unavailable or
a model is missing.

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
cd ../frontend && npm run lint && npm run build
npm audit --audit-level=high
```

Retrieval evaluation (hit@5 and MRR), after indexing a repository:

```bash
DEVMIND_REPO_PATH=/path/to/DevMind python evaluation/evaluate.py
```

## Known limitations

- Indexing is synchronous and re-indexes the whole repository each time.
- Embeddings are stored as JSON in SQLite and compared in memory; this suits
  small and medium repositories, not large vector workloads.
- A 1B-parameter model can still give weak or wrong answers; always check the
  cited sources.
