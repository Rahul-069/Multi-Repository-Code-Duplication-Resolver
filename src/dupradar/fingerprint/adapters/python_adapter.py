"""AST-based Python `LanguageAdapter` -- the only adapter needed today.

Walks the full `ast` tree of a `.py` file and extracts one `FunctionChunk`
per `FunctionDef`/`AsyncFunctionDef`, at any nesting depth (top-level,
nested functions, methods -- including methods of nested classes).

`qualified_name` is built by joining the names of enclosing `ClassDef`/
`FunctionDef`/`AsyncFunctionDef` scopes with ".", e.g. a method `validate`
on class `OrderValidator` gets `"OrderValidator.validate"`; a function
`inner` nested inside top-level `outer` gets `"outer.inner"`. Only
Class/Function scopes contribute a qualifier segment -- a `def` nested
inside an `if`/`for`/`try`/`with` block does NOT pick up a segment for that
block, matching Python's own lexical scoping rules.
"""

from __future__ import annotations

import ast

from dupradar.fingerprint.models import FunctionChunk, FunctionDefNode

_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


class PythonAdapter:
    """Implements `LanguageAdapter` for `.py` source via the stdlib `ast`."""

    def extract_chunks(self, source: str, file_path: str) -> list[FunctionChunk]:
        tree = ast.parse(source, filename=file_path)
        chunks: list[FunctionChunk] = []
        self._walk(tree, scope_path=(), file_path=file_path, out=chunks)
        return chunks

    def _walk(
        self,
        node: ast.AST,
        scope_path: tuple[str, ...],
        file_path: str,
        out: list[FunctionChunk],
    ) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _DEF_TYPES):
                qualified_name = ".".join((*scope_path, child.name))
                out.append(self._to_chunk(child, qualified_name, file_path))
                # Descend so nested defs/methods inside this one are also
                # extracted as their own chunks, qualified by this def's name.
                self._walk(child, (*scope_path, child.name), file_path, out)
            elif isinstance(child, ast.ClassDef):
                self._walk(child, (*scope_path, child.name), file_path, out)
            else:
                # Any other statement (If/For/While/Try/With/...) may still
                # contain nested defs below it; keep descending WITHOUT
                # extending scope_path, since only Class/Function scopes
                # contribute a qualifier segment.
                self._walk(child, scope_path, file_path, out)

    @staticmethod
    def _to_chunk(node: FunctionDefNode, qualified_name: str, file_path: str) -> FunctionChunk:
        end_line = node.end_lineno if node.end_lineno is not None else node.lineno
        return FunctionChunk(
            qualified_name=qualified_name,
            file_path=file_path,
            start_line=node.lineno,
            end_line=end_line,
            node=node,
        )
