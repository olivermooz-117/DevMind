from pathlib import Path

from devmind.parser import (
    parse_source_file,
    split_large_text,
    discover_source_files,
)


def test_parse_python_extracts_function_name(tmp_path):
    source = tmp_path / "sample.py"
    source.write_text(
        "def calculate_total(price, tax):\n"
        "    return price + tax\n",
        encoding="utf-8",
    )

    chunks = parse_source_file(source)

    assert chunks
    assert any(chunk["symbol"] == "calculate_total" for chunk in chunks)


def test_parse_python_extracts_class_name(tmp_path):
    source = tmp_path / "sample.py"
    source.write_text(
        "class PricingService:\n"
        "    def calculate(self):\n"
        "        return 100\n",
        encoding="utf-8",
    )

    chunks = parse_source_file(source)

    assert any(chunk["symbol"] == "PricingService" for chunk in chunks)


def test_unsupported_extension_returns_empty(tmp_path):
    source = tmp_path / "sample.unknown"
    source.write_text("some content", encoding="utf-8")

    assert parse_source_file(source) == []


def test_large_text_is_split():
    text = "\n".join(["x" * 20 for _ in range(20)])

    chunks = split_large_text(text, max_chars=50)

    assert len(chunks) > 1
    assert all(chunks)


def test_discover_source_files_ignores_directories(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")

    ignored = tmp_path / "venv"
    ignored.mkdir()
    (ignored / "ignored.py").write_text("print('ignored')", encoding="utf-8")

    root, files = discover_source_files(tmp_path)

    assert root == tmp_path.resolve()
    assert len(files) == 1
    assert files[0].name == "main.py"
