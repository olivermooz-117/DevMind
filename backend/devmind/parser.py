from pathlib import Path

from tree_sitter_language_pack import get_parser

from .config import (
    SUPPORTED_EXTENSIONS,
    IGNORED_DIRS,
    IGNORED_FILES,
    IGNORED_PATHS,
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
    """Split text into chunks under max_chars, tracking line ranges.

    Returns a list of (content, start_line, end_line) tuples where
    line numbers are 1-indexed.
    """
    chunks = []
    current = []
    current_length = 0
    current_start_line = 1

    for line_index, line in enumerate(text.splitlines(), start=1):
        line_length = len(line) + 1

        if current and current_length + line_length > max_chars:
            end_line = line_index - 1
            chunks.append(("\n".join(current), current_start_line, end_line))
            current = []
            current_length = 0
            current_start_line = line_index

        current.append(line)
        current_length += line_length

    if current:
        end_line = len(text.splitlines())
        chunks.append(("\n".join(current), current_start_line, end_line))

    return chunks


def node_line_range(node):
    """Return (start_line, end_line) as 1-indexed integers from a Tree-sitter node."""
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    return start_line, end_line


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

    start_line, end_line = node_line_range(target)

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
        else [(content, start_line, end_line)]
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
            "start_line": line_start,
            "end_line": line_end,
        }
        for piece_index, (piece, line_start, line_end) in enumerate(pieces, start=1)
    ]


def _is_binary(data, sample_size=512):
    """Detect binary content by checking for null bytes in the sample."""
    return b"\x00" in data[:sample_size]


def parse_source_file(file_path):
    path = Path(file_path)
    language = SUPPORTED_EXTENSIONS.get(path.suffix.lower())

    if not language:
        return []

    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return []

        source = path.read_bytes()

        if _is_binary(source):
            return []

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
            pieces = split_large_text(text)
            return [
                {
                    "file_path": str(path),
                    "language": language,
                    "symbol": f"file_chunk_{index}",
                    "content": piece,
                    "start_line": line_start,
                    "end_line": line_end,
                }
                for index, (piece, line_start, line_end) in enumerate(pieces, start=1)
            ]

        return chunks

    except Exception:
        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace"
            )

            pieces = split_large_text(text)
            return [
                {
                    "file_path": str(path),
                    "language": language,
                    "symbol": f"fallback_chunk_{index}",
                    "content": piece,
                    "start_line": line_start,
                    "end_line": line_end,
                }
                for index, (piece, line_start, line_end) in enumerate(pieces, start=1)
            ]
        except OSError:
            return []


def discover_source_files(repo_path):
    root = Path(repo_path).expanduser().resolve()

    if not root.exists() or not root.is_dir():
        raise ValueError("Repository path must be an existing directory")

    files = []

    for current_dir in root.rglob("*"):
        # Follow only real files; skip broken links and non-files.
        try:
            if not current_dir.is_file():
                continue
        except OSError:
            continue

        # Reject symlinks (or hard paths) that resolve outside the repo root.
        try:
            resolved = current_dir.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if root not in resolved.parents and resolved != root:
            continue
        # Relative path must still be under root for display/indexing.
        try:
            relative_path = resolved.relative_to(root)
        except ValueError:
            continue

        relative_parts = relative_path.parts

        if any(part in IGNORED_DIRS for part in relative_parts[:-1]):
            continue

        if resolved.name in IGNORED_FILES:
            continue

        if relative_path.as_posix() in IGNORED_PATHS:
            continue

        if resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        try:
            if resolved.stat().st_size <= MAX_FILE_BYTES:
                files.append(resolved)
        except OSError:
            continue

    return root, files
