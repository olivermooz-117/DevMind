from pathlib import Path

from tree_sitter_language_pack import get_parser

from .config import (
    SUPPORTED_EXTENSIONS,
    IGNORED_DIRS,
    MAX_FILE_BYTES,
    MAX_CHUNK_CHARS,
)


FUNCTION_NODES = {
    "function_definition",
    "function_declaration",
    "function_item",
    "method_definition",
    "method_declaration",
    "method",
    "arrow_function",
    "function",
    "function_expression",
    "constructor_declaration",
}

CLASS_NODES = {
    "class_definition",
    "class_declaration",
    "class_specifier",
    "struct_item",
    "struct_specifier",
    "interface_declaration",
    "enum_declaration",
}


def split_large_text(text, max_chars=MAX_CHUNK_CHARS):
    chunks = []
    current = []
    current_length = 0

    for line in text.splitlines():
        line_length = len(line) + 1

        if current and current_length + line_length > max_chars:
            chunks.append("\n".join(current))
            current = []
            current_length = 0

        current.append(line)
        current_length += line_length

    if current:
        chunks.append("\n".join(current))

    return chunks


def get_node_name(node, source):
    """Extract a useful identifier from a Tree-sitter node."""

    for child in node.children:
        if child.type in {"identifier", "name", "type_identifier"}:
            name = source[child.start_byte:child.end_byte].decode(
                "utf-8", errors="replace"
            ).strip()

            if name:
                return name

    # Some grammars place names inside declarators or nested nodes.
    for child in node.named_children:
        if child.type in {
            "function_declarator",
            "variable_declarator",
            "assignment",
        }:
            name = get_node_name(child, source)
            if name:
                return name

    return None


def get_symbol(node, source, index):
    node_type = node.type

    if node_type in FUNCTION_NODES:
        name = get_node_name(node, source)
        return name or f"function_{index}"

    if node_type in CLASS_NODES:
        name = get_node_name(node, source)
        return name or f"class_{index}"

    return f"{node_type}_{index}"


def parse_source_file(file_path):
    path = Path(file_path)
    language = SUPPORTED_EXTENSIONS.get(path.suffix.lower())

    if not language:
        return []

    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return []

        source = path.read_bytes()
        text = source.decode("utf-8", errors="replace")

        parser = get_parser(language)
        tree = parser.parse(source)
        root = tree.root_node

        chunks = []

        for index, node in enumerate(root.named_children, start=1):
            content = source[node.start_byte:node.end_byte].decode(
                "utf-8", errors="replace"
            ).strip()

            if not content:
                continue

            symbol = get_symbol(node, source, index)

            if len(content) > MAX_CHUNK_CHARS:
                pieces = split_large_text(content)
            else:
                pieces = [content]

            for piece_index, piece in enumerate(pieces, start=1):
                chunks.append({
                    "file_path": str(path),
                    "language": language,
                    "symbol": (
                        symbol if len(pieces) == 1
                        else f"{symbol}_part_{piece_index}"
                    ),
                    "content": piece,
                })

        if not chunks and text.strip():
            chunks = [
                {
                    "file_path": str(path),
                    "language": language,
                    "symbol": f"file_chunk_{index}",
                    "content": piece,
                }
                for index, piece in enumerate(
                    split_large_text(text), start=1
                )
            ]

        return chunks

    except Exception:
        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace"
            )

            return [
                {
                    "file_path": str(path),
                    "language": language,
                    "symbol": f"fallback_chunk_{index}",
                    "content": piece,
                }
                for index, piece in enumerate(
                    split_large_text(text), start=1
                )
            ]
        except OSError:
            return []


def discover_source_files(repo_path):
    root = Path(repo_path).expanduser().resolve()

    if not root.exists() or not root.is_dir():
        raise ValueError("Repository path must be an existing directory")

    files = []

    for current_dir in root.rglob("*"):
        if not current_dir.is_file():
            continue

        if any(part in IGNORED_DIRS for part in current_dir.parts):
            continue

        if current_dir.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        try:
            if current_dir.stat().st_size <= MAX_FILE_BYTES:
                files.append(current_dir)
        except OSError:
            continue

    return root, files
