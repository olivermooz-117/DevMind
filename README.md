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

```bash
ollama pull llama3.2:1b
ollama pull nomic-embed-text
```

## Run locally (development)

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py                      # http://127.0.0.1:5000

# Frontend (new terminal)
cd frontend
npm install
npm run dev                        # http://localhost:3000
```

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

Open http://localhost:3000 and enter the path **as the container sees it**,
for example `/repos/my-project`.

## Security notes

- Only the folder in `DEVMIND_PROJECTS_DIR` is mounted (read-only), and the
  API refuses repository paths outside `DEVMIND_ALLOWED_ROOT` (`/repos` in Docker).
- Docker publishes ports on `127.0.0.1` only. There is no authentication, so
  do not expose the API to a network.
- If you expose Ollama with `OLLAMA_HOST=0.0.0.0`, firewall port 11434.

## Tests and evaluation

```bash
cd backend && python -m pytest -v
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
