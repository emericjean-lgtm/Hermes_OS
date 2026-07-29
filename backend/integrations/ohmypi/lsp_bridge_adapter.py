"""LSP Bridge Adapter (HOS-055C).

Bridges Oh My Pi LSP diagnostics, symbols, and references into
Hermes Knowledge Graph (HOS-047) and Validation Engine (HOS-050).

Relations: File→Symbol, Symbol→Function, Function→Dependency,
Error→Location, Patch→Resolution.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from backend.memory.knowledge_graph import KnowledgeGraph
from backend.memory.memory_models import KnowledgeNode


@dataclass
class LSPSymbol:
    name: str = ""; kind: str = ""; file_path: str = ""
    line: int = 0; column: int = 0
    container_name: str = ""; signature: str = ""

@dataclass
class LSPReference:
    symbol_name: str = ""; file_path: str = ""; line: int = 0; column: int = 0

@dataclass
class LSPDiagnostic:
    file_path: str = ""; severity: str = ""; line: int = 0; message: str = ""
    code: str = ""; source: str = "lsp"

@dataclass
class CodeStructure:
    file_path: str = ""; language: str = ""
    symbols: list[LSPSymbol] = field(default_factory=list)
    diagnostics: list[LSPDiagnostic] = field(default_factory=list)


class LSPBridgeAdapter:
    def __init__(self, knowledge_graph: Optional[KnowledgeGraph] = None,
                 on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._kg = knowledge_graph; self._on_event = on_event
        self._symbols: dict[str, LSPSymbol] = {}
        self._diagnostics: dict[str, list[LSPDiagnostic]] = {}
        self._structures: dict[str, CodeStructure] = {}

    def index_symbols(self, file_path: str, symbols: list[LSPSymbol]) -> int:
        count = 0
        for sym in symbols:
            key = f"{sym.file_path}::{sym.name}"
            self._symbols[key] = sym; count += 1
            if self._kg:
                node = KnowledgeNode(node_type="symbol", label=key,
                    properties={"name": sym.name, "kind": sym.kind, "file": file_path,
                                "line": sym.line, "signature": sym.signature})
                self._kg.add_node(node)
                fn = self._find_file_node(file_path)
                if fn: self._kg.add_edge(fn.node_id, node.node_id, "DEFINES")
        if self._on_event:
            self._on_event("ohmypi.lsp.symbols_indexed", {"file": file_path, "count": count})
        return count

    def index_diagnostics(self, file_path: str, diagnostics: list[LSPDiagnostic]) -> dict:
        self._diagnostics[file_path] = diagnostics
        errors = sum(1 for d in diagnostics if d.severity == "error")
        warnings = sum(1 for d in diagnostics if d.severity == "warning")
        if self._on_event:
            self._on_event("ohmypi.lsp.diagnostics", {"file": file_path, "errors": errors, "warnings": warnings})
        return {"file": file_path, "errors": errors, "warnings": warnings, "total": len(diagnostics)}

    def index_structure(self, structure: CodeStructure) -> int:
        self._structures[structure.file_path] = structure
        return self.index_symbols(structure.file_path, structure.symbols)

    def find_symbol(self, name: str, file_path: str = "") -> Optional[LSPSymbol]:
        if file_path: return self._symbols.get(f"{file_path}::{name}")
        for k, v in self._symbols.items():
            if v.name == name: return v
        return None

    def find_references(self, name: str) -> list[LSPReference]:
        return [LSPReference(symbol_name=name, file_path=v.file_path, line=v.line, column=v.column)
                for v in self._symbols.values() if v.name == name]

    def get_diagnostics(self, file_path: str = "") -> list[LSPDiagnostic]:
        if file_path: return self._diagnostics.get(file_path, [])
        result = []
        for diags in self._diagnostics.values(): result.extend(diags)
        return result

    def get_code_structure(self, file_path: str) -> Optional[CodeStructure]:
        return self._structures.get(file_path)

    def stats(self) -> dict:
        return {"files_indexed": len(self._structures), "symbols": len(self._symbols),
                "files_with_diagnostics": len(self._diagnostics),
                "total_diagnostics": sum(len(d) for d in self._diagnostics.values()) if self._diagnostics else 0}

    def _find_file_node(self, path: str) -> Optional[KnowledgeNode]:
        if not self._kg: return None
        for n in self._kg.find_nodes(node_type="file", label_contains=path):
            if n.label == path or n.properties.get("path") == path: return n
        return None
