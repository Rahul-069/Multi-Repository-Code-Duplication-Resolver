"""`LanguageAdapter` protocol -- the extension point for per-language chunk
extraction. `python_adapter.py` is the only implementation needed today;
future language support (e.g. a tree-sitter-based JS/TS adapter) plugs in
here without changing `normalize.py`, `compare.py`, or the MCP tools.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dupradar.fingerprint.models import FunctionChunk


@runtime_checkable
class LanguageAdapter(Protocol):
    """Extracts function/method chunks from one source file's text."""

    def extract_chunks(self, source: str, file_path: str) -> list[FunctionChunk]:
        """Parse `source` and return one `FunctionChunk` per function/method
        definition found at any nesting depth (top-level, nested, methods).

        `file_path` is carried through to each resulting `FunctionChunk` as
        metadata only -- implementations must not need to re-read the file
        themselves; `source` is the complete, already-read file contents.
        """
        ...
