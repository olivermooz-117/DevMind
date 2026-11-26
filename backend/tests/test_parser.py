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


def test_decorated_functions_get_real_names(tmp_path):
    source = tmp_path / "routes.py"
    source.write_text(
        "@app.get('/health')\n"
        "def health():\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )

    chunks = parse_source_file(source)

    assert [chunk["symbol"] for chunk in chunks] == ["health"]
    assert "@app.get" in chunks[0]["content"]


def test_import_only_nodes_are_not_chunked(tmp_path):
    source = tmp_path / "module.py"
    source.write_text(
        "import os\n"
        "from pathlib import Path\n\n"
        "def run():\n"
        "    return os.getcwd()\n",
        encoding="utf-8",
    )

    chunks = parse_source_file(source)

    assert [chunk["symbol"] for chunk in chunks] == ["run"]


def test_large_class_is_split_into_methods(tmp_path):
    methods = "".join(
        f"    def method_{n}(self):\n        return '{'x' * 700}'\n\n"
        for n in range(8)
    )
    source = tmp_path / "big.py"
    source.write_text("class Big:\n" + methods, encoding="utf-8")

    symbols = [chunk["symbol"] for chunk in parse_source_file(source)]

    assert "Big.method_0" in symbols
    assert "Big.method_7" in symbols


def test_discover_source_files_ignores_generated_directories(tmp_path):
    (tmp_path / "main.py").write_text("def main(): pass", encoding="utf-8")

    generated_dirs = [
        "frontend/playwright-report",
        "frontend/test-results",
        "evaluation-results",
        "node_modules",
        ".next",
    ]

    for directory in generated_dirs:
        generated = tmp_path / directory
        generated.mkdir(parents=True)
        (generated / "generated.py").write_text(
            "def generated(): pass",
            encoding="utf-8",
        )

    root, files = discover_source_files(tmp_path)

    relative_files = {
        file.relative_to(root).as_posix()
        for file in files
    }

    assert "main.py" in relative_files
    assert len(relative_files) == 1


def test_discover_source_files_ignores_lockfiles(tmp_path):
    (tmp_path / "main.py").write_text("def main(): pass", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text(
        '{"packages": {}}',
        encoding="utf-8",
    )
    (tmp_path / "yarn.lock").write_text("example@1.0.0:", encoding="utf-8")

    root, files = discover_source_files(tmp_path)

    relative_files = {
        file.relative_to(root).as_posix()
        for file in files
    }

    assert relative_files == {"main.py"}


def test_discover_source_files_excludes_evaluation_datasets_but_keeps_code(
    tmp_path,
):
    evaluation = tmp_path / "evaluation"
    prompts = evaluation / "prompts"
    prompts.mkdir(parents=True)

    (evaluation / "harness.py").write_text(
        "def evaluate(): pass",
        encoding="utf-8",
    )
    (evaluation / "llm_questions.json").write_text(
        '{"questions": []}',
        encoding="utf-8",
    )
    (evaluation / "questions.json").write_text(
        '{"questions": []}',
        encoding="utf-8",
    )
    (prompts / "variants.json").write_text(
        '{"baseline": "example"}',
        encoding="utf-8",
    )

    root, files = discover_source_files(tmp_path)

    relative_files = {
        file.relative_to(root).as_posix()
        for file in files
    }

    assert "evaluation/harness.py" in relative_files
    assert "evaluation/llm_questions.json" not in relative_files
    assert "evaluation/questions.json" not in relative_files
    assert "evaluation/prompts/variants.json" not in relative_files
