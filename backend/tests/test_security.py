import os
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DEVMIND_DATA_DIR", "/tmp/devmind-test-data")

from app import app


def make_dirs(tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    return allowed, outside


def test_ingest_rejects_path_outside_allowed_root(tmp_path, monkeypatch):
    allowed, outside = make_dirs(tmp_path)
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(allowed))

    response = app.test_client().post(
        "/ingest", json={"repo_path": str(outside)}
    )

    assert response.status_code == 400
    assert "outside the allowed directory" in response.json["error"]


def test_ingest_rejects_parent_traversal(tmp_path, monkeypatch):
    allowed, _ = make_dirs(tmp_path)
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(allowed))

    response = app.test_client().post(
        "/ingest", json={"repo_path": str(allowed / ".." / "outside")}
    )

    assert response.status_code == 400


def test_search_rejects_path_outside_allowed_root(tmp_path, monkeypatch):
    allowed, outside = make_dirs(tmp_path)
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(allowed))

    response = app.test_client().post(
        "/search", json={"query": "x", "repo_path": str(outside)}
    )

    assert response.status_code == 400


def test_ingest_error_details_are_not_leaked(tmp_path, monkeypatch):
    allowed, _ = make_dirs(tmp_path)
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(allowed))

    with patch("app.ingest_repository", side_effect=RuntimeError("secret detail")):
        response = app.test_client().post(
            "/ingest", json={"repo_path": str(allowed)}
        )

    assert response.status_code == 500
    assert "secret detail" not in response.get_data(as_text=True)
