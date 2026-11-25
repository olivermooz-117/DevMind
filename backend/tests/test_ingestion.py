import logging
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


def test_ingestion_records_embedding_model_metadata(
    isolated_db, sample_repo, monkeypatch
):
    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)

    result = ingestion.ingest_repository(str(sample_repo))

    metadata = database.get_repository_embedding_metadata(
        result["repository"]
    )

    assert metadata is not None
    assert metadata["embedding_model"] == ingestion.EMBED_MODEL
    assert metadata["embedding_dimensions"] == 2


def test_binary_files_are_skipped(isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (repo / "data.bin").write_bytes(b"\x00\x01\x02\x03binary\xff\xfe")

    result = ingestion.ingest_repository(str(repo))

    assert result["files_discovered"] == 1
    stored = database.get_repository_chunks(result["repository"])
    assert {chunk["file_path"] for chunk in stored} == {"main.py"}


def test_transient_embedding_failure_retries_and_succeeds(
    isolated_db, sample_repo, monkeypatch
):
    """A transient Ollama failure is retried and succeeds on the second try."""
    call_count = 0

    def flaky_embeddings(texts):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise requests.exceptions.ConnectionError("Temporary failure")
        return fake_embeddings(texts)

    monkeypatch.setattr(ingestion, "create_embeddings", flaky_embeddings)
    monkeypatch.setattr(ingestion, "_EMBED_MAX_RETRIES", 3)
    monkeypatch.setattr(ingestion, "_EMBED_RETRY_DELAY", 0.01)

    result = ingestion.ingest_repository(str(sample_repo))

    assert result["chunks_indexed"] == 2
    assert call_count == 2


def test_persistent_embedding_failure_keeps_existing_index(
    isolated_db, sample_repo, monkeypatch
):
    """A persistent Ollama failure leaves the previous index intact."""
    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)
    first = ingestion.ingest_repository(str(sample_repo))

    def ollama_down(texts):
        raise requests.exceptions.ConnectionError("Ollama is down")

    monkeypatch.setattr(ingestion, "create_embeddings", ollama_down)
    monkeypatch.setattr(ingestion, "_EMBED_MAX_RETRIES", 2)
    monkeypatch.setattr(ingestion, "_EMBED_RETRY_DELAY", 0.01)

    with pytest.raises(requests.exceptions.ConnectionError):
        ingestion.ingest_repository(str(sample_repo))

    stored = database.get_repository_chunks(first["repository"])
    assert len(stored) == first["chunks_indexed"]


def test_ingest_rejects_unsupported_extensions(
    isolated_db, tmp_path, monkeypatch
):
    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "readme.txt").write_text("Just some text", encoding="utf-8")
    (repo / "image.png").write_bytes(b"\x89PNG\r\n")

    with pytest.raises(ValueError, match="No supported source files"):
        ingestion.ingest_repository(str(repo))


def test_concurrent_ingestion_same_repo(isolated_db, sample_repo, monkeypatch):
    """Concurrent ingestion of the same repository is serialized."""
    import threading

    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)

    errors = []
    results = []

    def ingest():
        try:
            result = ingestion.ingest_repository(str(sample_repo))
            results.append(result)
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=ingest) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len(results) == 3

    # All ingestions should have indexed the same number of chunks
    for result in results:
        assert result["chunks_indexed"] == 2


def test_concurrent_reads_and_writes(isolated_db, sample_repo, monkeypatch):
    """Concurrent reads and writes do not corrupt the database."""
    import threading

    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)

    # First ingestion establishes the index
    first = ingestion.ingest_repository(str(sample_repo))
    initial_count = len(database.get_repository_chunks(first["repository"]))

    errors = []

    def write():
        try:
            ingestion.ingest_repository(str(sample_repo))
        except Exception as error:
            errors.append(error)

    def read():
        try:
            for _ in range(5):
                database.get_repository_chunks(str(sample_repo))
                database.get_repositories()
        except Exception as error:
            errors.append(error)

    threads = []
    for _ in range(2):
        threads.append(threading.Thread(target=write))
    for _ in range(2):
        threads.append(threading.Thread(target=read))

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    # Data should still be intact after concurrent access
    stored = database.get_repository_chunks(str(sample_repo))
    assert len(stored) == initial_count


def test_ingestion_logs_completion_metrics(
    isolated_db, sample_repo, monkeypatch, caplog
):
    """Ingestion logs files discovered, chunks indexed, and duration."""
    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)

    with caplog.at_level(logging.INFO, logger="devmind.ingestion"):
        result = ingestion.ingest_repository(str(sample_repo))

    info_records = [
        r for r in caplog.records
        if r.levelno == logging.INFO
        and "ingestion completed" in r.getMessage()
    ]
    assert len(info_records) == 1

    record = info_records[0]
    assert record.repository == sample_repo.name
    assert record.files_discovered == result["files_discovered"]
    assert record.chunks_indexed == result["chunks_indexed"]
    assert record.embedding_model == result["embedding_model"]
    assert record.total_duration_ms >= 0


def test_ingestion_logs_skipped_files(
    isolated_db, tmp_path, monkeypatch, caplog
):
    """Ingestion logs the number of skipped files."""
    monkeypatch.setattr(ingestion, "create_embeddings", fake_embeddings)

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "data.bin").write_bytes(b"\x00\x01\x02\x03binary\xff\xfe")
    (repo / "readme.txt").write_text("Just some text", encoding="utf-8")
    (repo / "image.png").write_bytes(b"\x89PNG\r\n")

    with caplog.at_level(logging.INFO, logger="devmind.ingestion"):
        try:
            ingestion.ingest_repository(str(repo))
        except ValueError:
            pass  # Expected: no supported files

    warning_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "No supported source files found" in r.getMessage()
    ]
    assert len(warning_records) == 1
    assert warning_records[0].files_discovered == 0
