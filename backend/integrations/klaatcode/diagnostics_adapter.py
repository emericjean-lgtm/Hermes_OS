"""Diagnostics Adapter (HOS-054D).

Bridges KlaatCode diagnostics into the Hermes Validation Engine (HOS-050).
Supports compilation errors, test errors, code quality, fix suggestions,
and patch validation.

Pipeline:
    Patch generated → Diagnostics → Validation → Accept/Reject
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.execution.execution_models import TaskExecution, ValidationOutcome


# ── Data classes ────────────────────────────────────────────

@dataclass
class DiagnosticIssue:
    """A single diagnostic issue from KlaatCode analysis."""
    file_path: str = ""
    severity: str = ""  # error, warning, info, hint
    line: int = 0
    column: int = 0
    message: str = ""
    rule_id: str = ""
    category: str = ""  # compilation, test, quality, security, style
    suggestion: str = ""
    source: str = "klaatcode"


@dataclass
class DiagnosticsReport:
    """Aggregated diagnostics report for a file or project."""
    report_id: str = ""
    target: str = ""  # file path or project
    issues: list[DiagnosticIssue] = field(default_factory=list)
    total_errors: int = 0
    total_warnings: int = 0
    total_hints: int = 0
    needs_human_review: bool = False
    auto_fixable_count: int = 0
    validation_outcome: Optional[ValidationOutcome] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PatchValidationResult:
    """Result of validating a generated patch."""
    patch_id: str = ""
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diagnostics: Optional[DiagnosticsReport] = None
    accepted: bool = False
    reason: str = ""


# ── Adapter ─────────────────────────────────────────────────

class DiagnosticsAdapter:
    """Transforms KlaatCode diagnostics into Validation Engine outcomes.

    Thread-safe. Bridges KlaatCode → Validation Engine (HOS-050).
    """

    def __init__(
        self,
        validation_engine: Any = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._validation_engine = validation_engine
        self._on_event = on_event
        self._reports: dict[str, DiagnosticsReport] = {}
        self._patch_results: dict[str, PatchValidationResult] = {}
        self._validated_count = 0

    # ── Diagnostics Analysis ────────────────────────────────

    def analyze_diagnostics(
        self,
        diagnostics_data: Any,
        target: str = "",
    ) -> DiagnosticsReport:
        """Analyze KlaatCode diagnostics output and produce a report.

        Args:
            diagnostics_data: Raw diagnostics from KlaatCode MCP.
            target: File or project path being analyzed.

        Returns:
            DiagnosticsReport with categorized issues and auto-fix counts.
        """
        report = DiagnosticsReport(
            report_id=f"diag_{int(datetime.now(timezone.utc).timestamp())}",
            target=target,
        )

        # Parse diagnostics from KlaatCode response
        if isinstance(diagnostics_data, dict):
            raw_issues = diagnostics_data.get("diagnostics", [])
            if not raw_issues:
                raw = diagnostics_data.get("raw", "")
                if raw:
                    raw_issues = self._parse_raw_diagnostics(raw)
        elif isinstance(diagnostics_data, list):
            raw_issues = diagnostics_data
        else:
            raw_issues = []

        for issue in raw_issues:
            diag = DiagnosticIssue(
                file_path=issue.get("file_path", ""),
                severity=issue.get("severity", "warning"),
                line=issue.get("line", 0),
                column=issue.get("column", 0),
                message=issue.get("message", ""),
                rule_id=issue.get("rule_id", ""),
                category=issue.get("category", self._categorize(issue)),
                suggestion=issue.get("suggestion", ""),
                source="klaatcode",
            )
            report.issues.append(diag)

            if diag.severity == "error":
                report.total_errors += 1
            elif diag.severity == "warning":
                report.total_warnings += 1
            else:
                report.total_hints += 1

            if diag.suggestion:
                report.auto_fixable_count += 1

        report.needs_human_review = (
            report.total_errors > 5 or
            any(i.severity == "error" and i.category == "security" for i in report.issues)
        )

        with self._lock:
            self._reports[report.report_id] = report
            self._validated_count += 1

        if self._on_event:
            self._on_event("klaatcode.diagnostics.analyzed", {
                "target": target,
                "errors": report.total_errors,
                "warnings": report.total_warnings,
                "auto_fixable": report.auto_fixable_count,
            }, severity="info" if report.total_errors == 0 else "warning")

        return report

    # ── Patch Validation ────────────────────────────────────

    def validate_patch(
        self,
        patch_id: str,
        file_path: str,
        diagnostics: Optional[DiagnosticsReport] = None,
        task: Optional[TaskExecution] = None,
    ) -> PatchValidationResult:
        """Validate a generated patch against diagnostics.

        Pipeline: Patch → Diagnostics → Validation → Accept/Reject

        Args:
            patch_id: Identifier for the patch.
            file_path: File being patched.
            diagnostics: Optional pre-computed diagnostics report.
            task: Optional task execution for integration with ValidationEngine.

        Returns:
            PatchValidationResult with accept/reject decision.
        """
        result = PatchValidationResult(patch_id=patch_id)

        if diagnostics is None:
            # Mark as needing diagnostics
            result.valid = False
            result.errors.append("No diagnostics available for validation")
            result.reason = "missing_diagnostics"
            return result

        if diagnostics.total_errors > 0:
            result.valid = False
            result.errors = [
                f"{i.file_path}:{i.line}:{i.column} - {i.message}"
                for i in diagnostics.issues if i.severity == "error"
            ]
            result.reason = f"{diagnostics.total_errors} errors found"
        elif diagnostics.total_warnings > 10:
            result.valid = False
            result.errors = [f"Too many warnings ({diagnostics.total_warnings})"]
            result.reason = "excessive_warnings"
        elif diagnostics.needs_human_review:
            result.reason = "needs_human_review"
            # Still valid but flagged
        else:
            result.valid = True
            result.warnings = [
                f"{i.file_path}:{i.line} - {i.message}"
                for i in diagnostics.issues if i.severity == "warning"
            ]
            result.reason = "passed"

        result.diagnostics = diagnostics
        result.accepted = result.valid and not diagnostics.needs_human_review

        # Integrate with Validation Engine if available
        if task and self._validation_engine:
            try:
                outcome = self._to_validation_outcome(result)
                task.validation_outcome = outcome
                if hasattr(self._validation_engine, 'validate'):
                    self._validation_engine.validate(task)
            except Exception:
                pass

        with self._lock:
            self._patch_results[patch_id] = result

        if self._on_event:
            self._on_event("klaatcode.patch.validated", {
                "patch_id": patch_id,
                "file": file_path,
                "accepted": result.accepted,
                "reason": result.reason,
            }, severity="info" if result.accepted else "warning")

        return result

    # ── Suggestions ─────────────────────────────────────────

    def get_fix_suggestions(
        self, diagnostics: DiagnosticsReport, limit: int = 10
    ) -> list[str]:
        """Extract auto-fix suggestions from diagnostics."""
        suggestions = []
        for issue in diagnostics.issues:
            if issue.suggestion:
                suggestions.append(f"{issue.file_path}:{issue.line} - {issue.suggestion}")
        return suggestions[:limit]

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            accepted = sum(1 for r in self._patch_results.values() if r.accepted)
            return {
                "reports_generated": len(self._reports),
                "patches_validated": len(self._patch_results),
                "patches_accepted": accepted,
                "acceptance_rate": round(accepted / max(len(self._patch_results), 1) * 100, 1),
                "total_validations": self._validated_count,
            }

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _categorize(issue: dict) -> str:
        """Categorize a diagnostic issue."""
        msg = issue.get("message", "").lower()
        rule = issue.get("rule_id", "").lower()
        if "test" in msg or "assert" in msg:
            return "test"
        if "import" in msg or "module" in msg or "unresolved" in msg:
            return "compilation"
        if "security" in msg or "inject" in msg or "xss" in msg:
            return "security"
        if "unused" in msg or "dead" in msg:
            return "quality"
        if "style" in msg or "format" in msg or "lint" in rule:
            return "style"
        return "quality"

    @staticmethod
    def _parse_raw_diagnostics(raw: str) -> list[dict]:
        """Parse raw diagnostic text into structured issues."""
        issues = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            issues.append({
                "file_path": "",
                "severity": "warning",
                "line": 0,
                "message": line,
            })
        return issues

    @staticmethod
    def _to_validation_outcome(result: PatchValidationResult) -> ValidationOutcome:
        """Map patch validation result to ValidationOutcome."""
        if result.accepted:
            return ValidationOutcome.PASS
        if result.reason == "needs_human_review":
            return ValidationOutcome.NEEDS_REVIEW
        return ValidationOutcome.FAIL
