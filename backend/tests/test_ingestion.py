import pytest
import requests

from devmind import database, ingestion


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "devmind.db")
    database.initialize_database()


@pytest.fixture
def sample_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text(
        "def alpha():\n    return 1\n\n"
        "def beta():\n    return 2\n",
        encoding="utf-8",
    )
    return repo


def fake_embeddings(texts):
    return [[1.0, 0.0] for _ in texts]


def test_ingest_indexes_chunks(isolated_db, sample_repo, monkeypatch):
    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)

    result = ingestion.ingest_repository(str(sample_repo))

    assert result["files_discovered"] == 1
    assert result["chunks_indexed"] == 2
    stored = database.get_repository_chunks(result["repository"])
    assert {chunk["file_path"] for chunk in stored} == {"main.py"}
    assert {chunk["symbol"] for chunk in stored} == {"alpha", "beta"}


def test_failed_embedding_keeps_existing_index(
    isolated_db, sample_repo, monkeypatch
):
    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)
    first = ingestion.ingest_repository(str(sample_repo))

    def ollama_down(texts):
        raise requests.exceptions.ConnectionError("Ollama is down")

    monkeypatch.setattr(ingestion, "create_embeddings", ollama_down)

    with pytest.raises(requests.exceptions.ConnectionError):
        ingestion.ingest_repository(str(sample_repo))

    stored = database.get_repository_chunks(first["repository"])
    assert len(stored) == first["chunks_indexed"]


def test_empty_repository_is_rejected(isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(ValueError):
        ingestion.ingest_repository(str(empty))
