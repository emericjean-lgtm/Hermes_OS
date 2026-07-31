"""AST Adapter (HOS-055C).

Exploits Oh My Pi's tree-sitter to convert code structure into
Knowledge Graph nodes. Detects: functions, classes, imports,
dependencies, complexity.

Pipeline: AST → KnowledgeGraph → RetrievalEngine
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from backend.memory.knowledge_graph import KnowledgeGraph
from backend.memory.memory_models import KnowledgeNode


@dataclass
class ASTNode:
    name: str = ""; node_type: str = ""; file_path: str = ""
    line_start: int = 0; line_end: int = 0; complexity: float = 0.0
    children: list[ASTNode] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

@dataclass
class ASTAnalysis:
    file_path: str = ""; language: str = ""; total_lines: int = 0
    functions: list[ASTNode] = field(default_factory=list)
    classes: list[ASTNode] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    complexity_score: float = 0.0


class ASTAdapter:
    def __init__(self, knowledge_graph: Optional[KnowledgeGraph] = None,
                 on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._kg = knowledge_graph; self._on_event = on_event
        self._analyses: dict[str, ASTAnalysis] = {}
        self._nodes: dict[str, ASTNode] = {}

    def analyze(self, file_path: str, language: str = "",
                functions: Optional[list[dict]] = None,
                classes: Optional[list[dict]] = None,
                imports: Optional[list[str]] = None,
                total_lines: int = 0) -> ASTAnalysis:
        funcs = [ASTNode(name=f.get("name", ""), node_type="function", file_path=file_path,
                          line_start=f.get("line_start", 0), line_end=f.get("line_end", 0),
                          complexity=self._estimate_complexity(f))
                 for f in (functions or [])]
        clses = [ASTNode(name=c.get("name", ""), node_type="class", file_path=file_path,
                          line_start=c.get("line_start", 0), line_end=c.get("line_end", 0),
                          complexity=self._estimate_complexity(c))
                  for c in (classes or [])]

        complexity = self._calculate_file_complexity(funcs, clses, total_lines)
        analysis = ASTAnalysis(file_path=file_path, language=language, total_lines=total_lines,
                                functions=funcs, classes=clses, imports=imports or [],
                                complexity_score=round(complexity, 1))
        self._analyses[file_path] = analysis

        if self._kg:
            fn = self._ensure_file_node(file_path, language)
            for fnode in funcs:
                self._nodes[f"{file_path}::{fnode.name}"] = fnode
                kn = KnowledgeNode(node_type="function", label=f"{file_path}::{fnode.name}",
                    properties={"name": fnode.name, "file": file_path, "complexity": fnode.complexity,
                                "entity_type": "function"})
                self._kg.add_node(kn)
                if fn: self._kg.add_edge(fn.node_id, kn.node_id, "CONTAINS")
            for cnode in clses:
                self._nodes[f"{file_path}::{cnode.name}"] = cnode
                kn = KnowledgeNode(node_type="class", label=f"{file_path}::{cnode.name}",
                    properties={"name": cnode.name, "file": file_path, "complexity": cnode.complexity})
                self._kg.add_node(kn)
                if fn: self._kg.add_edge(fn.node_id, kn.node_id, "CONTAINS")
            for imp in (imports or []):
                dep_fn = self._ensure_file_node(imp, language)
                if fn and dep_fn: self._kg.add_edge(fn.node_id, dep_fn.node_id, "IMPORTS")

        if self._on_event:
            self._on_event("ohmypi.ast.analyzed", {"file": file_path, "functions": len(funcs),
                            "classes": len(clses), "complexity": complexity})
        return analysis

    def get_analysis(self, file_path: str) -> Optional[ASTAnalysis]:
        return self._analyses.get(file_path)

    def detect_complex_functions(self, threshold: float = 10.0) -> list[ASTNode]:
        return [n for n in self._nodes.values() if n.complexity >= threshold]

    def get_dependencies(self, file_path: str) -> list[str]:
        a = self._analyses.get(file_path)
        return a.imports if a else []

    def stats(self) -> dict:
        return {"files_analyzed": len(self._analyses), "total_nodes": len(self._nodes),
                "total_functions": sum(len(a.functions) for a in self._analyses.values()),
                "total_classes": sum(len(a.classes) for a in self._analyses.values()),
                "avg_complexity": round(sum(a.complexity_score for a in self._analyses.values()) / max(len(self._analyses), 1), 1)}

    @staticmethod
    def _estimate_complexity(node: dict) -> float:
        lines = max(node.get("line_end", 0) - node.get("line_start", 0), 1)
        params = len(node.get("parameters", []))
        return round(lines * 0.1 + params * 1.5 + 1.0, 1)

    @staticmethod
    def _calculate_file_complexity(funcs: list, clses: list, total_lines: int) -> float:
        base = total_lines * 0.01 if total_lines > 0 else 1.0
        fc = sum(f.complexity for f in funcs)
        cc = sum(c.complexity for c in clses)
        return round(base + fc * 0.5 + cc * 0.3, 1)

    def _ensure_file_node(self, path: str, lang: str) -> Optional[KnowledgeNode]:
        if not self._kg: return None
        for n in self._kg.find_nodes(node_type="file", label_contains=path):
            if n.label == path: return n
        node = KnowledgeNode(node_type="file", label=path, properties={"path": path, "language": lang})
        self._kg.add_node(node)
        return node
