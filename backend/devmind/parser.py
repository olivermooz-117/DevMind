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

# Nodes that wrap the real definition (decorators, `export ...`).
WRAPPER_NODES = {
    "decorated_definition",
    "export_statement",
}

# Import-only nodes add noise to retrieval, so they are not indexed alone.
IMPORT_NODES = {
    "import_statement",
    "import_from_statement",
    "future_import_statement",
    "import_declaration",
    "use_declaration",
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


def node_text(node, source):
    return source[node.start_byte:node.end_byte].decode(
        "utf-8", errors="replace"
    ).strip()


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


def unwrap(node):
    """Return the real definition inside a decorator/export wrapper."""
    if node.type in WRAPPER_NODES:
        for field in ("definition", "declaration"):
            inner = node.child_by_field_name(field)
            if inner is not None:
                return inner

    return node


def get_symbol(node, source, index):
    node_type = node.type

    if node_type in FUNCTION_NODES:
        name = get_node_name(node, source)
        return name or f"function_{index}"

    if node_type in CLASS_NODES:
        name = get_node_name(node, source)
        return name or f"class_{index}"

    return f"{node_type}_{index}"


def collect_chunks(node, source, index, path, language):
    if node.type in IMPORT_NODES:
        return []

    content = node_text(node, source)

    if not content:
        return []

    target = unwrap(node)
    symbol = get_symbol(target, source, index)

    # A large class is split into one chunk per member (Class.method).
    if target.type in CLASS_NODES and len(content) > MAX_CHUNK_CHARS:
        body = target.child_by_field_name("body")

        if body is not None and body.named_children:
            members = []

            for member_index, member in enumerate(
                body.named_children, start=1
            ):
                for item in collect_chunks(
                    member, source, member_index, path, language
                ):
                    item["symbol"] = f"{symbol}.{item['symbol']}"
                    members.append(item)

            if members:
                return members

    pieces = (
        split_large_text(content)
        if len(content) > MAX_CHUNK_CHARS
        else [content]
    )

    return [
        {
            "file_path": str(path),
            "language": language,
            "symbol": (
                symbol if len(pieces) == 1
                else f"{symbol}_part_{piece_index}"
            ),
            "content": piece,
        }
        for piece_index, piece in enumerate(pieces, start=1)
    ]


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
            chunks.extend(
                collect_chunks(node, source, index, path, language)
            )

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
