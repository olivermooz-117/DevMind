"""Retrieval evaluation tests using a deterministic test repository.

These tests verify that the retrieval system returns relevant results,
avoids duplicates, and provides accurate citations. Ollama is mocked
so tests do not require a running model.
"""

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ["DEVMIND_DATA_DIR"] = "/tmp/devmind-test-evaluation"

from devmind import database, ingestion, retrieval
from devmind.database import connect, initialize_database


@pytest.fixture
def eval_db(tmp_path, monkeypatch):
    """Isolated database for evaluation tests."""
    data_dir = tmp_path / "data"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "devmind.db")
    database.initialize_database()
    return data_dir


@pytest.fixture
def test_repo(tmp_path):
    """Create a deterministic test repository with known structure."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Authentication module
    (repo / "auth.py").write_text(
        "def authenticate(username, password):\n"
        "    \"\"\"Verify user credentials.\"\"\"\n"
        "    if not username or not password:\n"
        "        return False\n"
        "    return True\n\n"
        "def logout(session_id):\n"
        "    \"\"\"End a user session.\"\"\"\n"
        "    session.clear(session_id)\n",
        encoding="utf-8",
    )

    # Database module
    (repo / "database.py").write_text(
        "def connect(db_path):\n"
        "    \"\"\"Open a database connection.\"\"\"\n"
        "    import sqlite3\n"
        "    return sqlite3.connect(db_path)\n\n"
        "def query(conn, sql, params=None):\n"
        "    \"\"\"Execute a SQL query.\"\"\"\n"
        "    cursor = conn.cursor()\n"
        "    if params:\n"
        "        cursor.execute(sql, params)\n"
        "    else:\n"
        "        cursor.execute(sql)\n"
        "    return cursor.fetchall()\n",
        encoding="utf-8",
    )

    # API module that uses both auth and database
    (repo / "api.py").write_text(
        "from auth import authenticate, logout\n"
        "from database import connect, query\n\n"
        "def login_endpoint(username, password):\n"
        "    \"\"\"Handle login API requests.\"\"\"\n"
        "    if authenticate(username, password):\n"
        "        return {\"status\": \"ok\"}\n"
        "    return {\"status\": \"error\"}\n\n"
        "def get_user_data(user_id):\n"
        "    \"\"\"Retrieve user data from the database.\"\"\"\n"
        "    conn = connect(\"users.db\")\n"
        "    return query(conn, \"SELECT * FROM users WHERE id = ?\", (user_id,))\n",
        encoding="utf-8",
    )

    # Configuration file
    (repo / "config.yaml").write_text(
        "database:\n"
        "  host: localhost\n"
        "  port: 5432\n"
        "auth:\n"
        "  token_expiry: 3600\n",
        encoding="utf-8",
    )

    return repo


def fake_embeddings(texts):
    """Deterministic fake embeddings based on text content hash."""
    embeddings = []
    for text in texts:
        # Simple hash-based embedding for determinism
        vector = [0.0] * 8
        for i, char in enumerate(text[:8]):
            vector[i] = ord(char) / 255.0
        embeddings.append(vector)
    return embeddings


def _mock_ollama_embeddings(monkeypatch):
    """Mock Ollama embedding functions for both ingestion and retrieval."""
    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)
    monkeypatch.setattr(retrieval, "create_embedding", lambda text: fake_embeddings([text])[0])


def test_relevant_file_retrieval(eval_db, test_repo, monkeypatch):
    """Test that searching for a function returns the file containing it."""
    _mock_ollama_embeddings(monkeypatch)

    result = ingestion.ingest_repository(str(test_repo))
    assert result["chunks_indexed"] > 0

    # Search for "authenticate" - should find auth.py
    results = retrieval.search_code("authenticate function", repo_path=str(test_repo), limit=5)

    assert len(results) > 0
    # auth.py should be among the results
    file_paths = {r["file_path"] for r in results}
    assert "auth.py" in file_paths, f"Expected auth.py in results, got {file_paths}"


def test_find_function_retrieval(eval_db, test_repo, monkeypatch):
    """Test finding a specific function by name."""
    _mock_ollama_embeddings(monkeypatch)

    ingestion.ingest_repository(str(test_repo))

    # Search for "authenticate" - should find auth.py
    results = retrieval.search_code("authenticate", repo_path=str(test_repo), limit=5)

    assert len(results) > 0
    auth_results = [r for r in results if r["file_path"] == "auth.py"]
    assert len(auth_results) > 0, "Should find auth.py containing authenticate"


def test_no_duplicate_results(eval_db, test_repo, monkeypatch):
    """Test that search results don't contain duplicate chunks."""
    _mock_ollama_embeddings(monkeypatch)

    ingestion.ingest_repository(str(test_repo))

    results = retrieval.search_code("database connection", repo_path=str(test_repo), limit=10)
    # Check for duplicate (file_path, symbol) pairs
    keys = [(r["file_path"], r["symbol"]) for r in results]
    assert len(keys) == len(set(keys)), f"Duplicate results found: {keys}"


def test_citation_validity(eval_db, test_repo, monkeypatch):
    """Test that citations include valid file paths and line numbers."""
    _mock_ollama_embeddings(monkeypatch)

    ingestion.ingest_repository(str(test_repo))

    results = retrieval.search_code("authenticate", repo_path=str(test_repo), limit=5)

    for result in results:
        assert result["file_path"], "Result missing file_path"
        assert result["symbol"], "Result missing symbol"
        assert result["content"], "Result missing content"
        # Line numbers should be present for Tree-sitter parsed files
        if result["file_path"].endswith(".py"):
            assert result.get("start_line") is not None, f"Missing start_line for {result['file_path']}"
            assert result.get("end_line") is not None, f"Missing end_line for {result['file_path']}"


def test_result_diversity(eval_db, test_repo, monkeypatch):
    """Test that results span multiple files when available."""
    _mock_ollama_embeddings(monkeypatch)

    ingestion.ingest_repository(str(test_repo))

    results = retrieval.search_code("function", repo_path=str(test_repo), limit=10)

    if len(results) > 1:
        file_paths = {r["file_path"] for r in results}
        # Should retrieve from at least 2 different files
        assert len(file_paths) >= 2, f"Expected results from multiple files, got {file_paths}"


def test_retrieval_deterministic(eval_db, test_repo, monkeypatch):
    """Test that retrieval is deterministic (same query = same results)."""
    _mock_ollama_embeddings(monkeypatch)

    ingestion.ingest_repository(str(test_repo))

    results1 = retrieval.search_code("authenticate user", repo_path=str(test_repo), limit=5)
    results2 = retrieval.search_code("authenticate user", repo_path=str(test_repo), limit=5)

    assert results1 == results2, "Retrieval should be deterministic"


def test_empty_repository_search(eval_db, tmp_path, monkeypatch):
    """Test searching an empty repository returns no results."""
    _mock_ollama_embeddings(monkeypatch)

    empty = tmp_path / "empty_repo"
    empty.mkdir()

    with pytest.raises(ValueError):
        ingestion.ingest_repository(str(empty))

    # Search should return empty
    results = retrieval.search_code("anything", repo_path=str(empty), limit=5)
    assert results == []


def test_hybrid_search_finds_keyword_matches(eval_db, test_repo, monkeypatch):
    """Test that hybrid search finds keyword matches even with weak semantic similarity."""
    _mock_ollama_embeddings(monkeypatch)

    ingestion.ingest_repository(str(test_repo))

    # Search for a term that appears in config.yaml
    results = retrieval.search_code("database host port", repo_path=str(test_repo), limit=5)

    file_paths = {r["file_path"] for r in results}
    # config.yaml should be found due to keyword matching
    assert "config.yaml" in file_paths, f"Expected config.yaml in results, got {file_paths}"
