import pytest

from devmind import database, retrieval
from devmind.config import EMBED_MODEL


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "devmind.db")
    database.initialize_database()

    database.replace_repository_chunks(
        "/repo",
        [
            {
                "file_path": "a.py",
                "language": "python",
                "symbol": "a",
                "content": "def a(): pass",
                "embedding": [1.0, 0.0],
            },
            {
                "file_path": "b.py",
                "language": "python",
                "symbol": "b",
                "content": "def b(): pass",
                "embedding": [0.0, 1.0],
            },
        ],
        embedding_model=EMBED_MODEL,
        embedding_dimensions=2,
    )


def test_search_ranks_most_similar_chunk_first(seeded_db, monkeypatch):
    monkeypatch.setattr(
        retrieval,
        "create_embedding",
        lambda text: [0.9, 0.1],
    )

    results = retrieval.search_code(
        "anything",
        repo_path="/repo",
        limit=2,
    )

    assert [item["file_path"] for item in results] == ["a.py", "b.py"]
    assert results[0]["score"] > results[1]["score"]


def test_search_rejects_different_embedding_model(seeded_db, monkeypatch):
    with database.connect() as connection:
        connection.execute("""
            UPDATE repository_embedding_metadata
            SET embedding_model = ?
            WHERE repo_path = ?
        """, ("some-other-model", "/repo"))

    monkeypatch.setattr(
        retrieval,
        "create_embedding",
        lambda text: [1.0, 0.0],
    )

    with pytest.raises(retrieval.EmbeddingModelMismatchError):
        retrieval.search_code("anything", repo_path="/repo")


def test_search_rejects_wrong_embedding_dimensions(seeded_db, monkeypatch):
    monkeypatch.setattr(
        retrieval,
        "create_embedding",
        lambda text: [1.0, 0.0, 0.0],
    )

    with pytest.raises(retrieval.EmbeddingModelMismatchError):
        retrieval.search_code("anything", repo_path="/repo")


def test_search_with_no_index_returns_empty(seeded_db, monkeypatch):
    monkeypatch.setattr(
        retrieval,
        "create_embedding",
        lambda text: [1.0, 0.0],
    )

    assert retrieval.search_code(
        "anything",
        repo_path="/missing",
    ) == []


def test_search_rejects_index_without_metadata(seeded_db, monkeypatch):
    with database.connect() as connection:
        connection.execute("""
            DELETE FROM repository_embedding_metadata
            WHERE repo_path = ?
        """, ("/repo",))

    monkeypatch.setattr(
        retrieval,
        "create_embedding",
        lambda text: [1.0, 0.0],
    )

    with pytest.raises(retrieval.EmbeddingModelMismatchError):
        retrieval.search_code("anything", repo_path="/repo")
