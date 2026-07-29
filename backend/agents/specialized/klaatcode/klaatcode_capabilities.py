"""KlaatCode Agent capabilities and task types (HOS-054C)."""

from enum import Enum


class KlaatCodeTaskType(str, Enum):
    """Task types the KlaatCodeAgent can handle."""

    CODE_ANALYSIS = "code_analysis"
    CODE_GENERATION = "code_generation"
    CODE_EDITING = "code_editing"
    REFACTORING = "refactoring"
    DIAGNOSTICS = "diagnostics"
    TEST_ANALYSIS = "test_analysis"
    PROJECT_NAVIGATION = "project_navigation"
    PATCH_GENERATION = "patch_generation"
    CODE_REVIEW = "code_review"


class KlaatCodeAgentStatus(str, Enum):
    """KlaatCodeAgent-specific operational status."""

    IDLE = "idle"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    EDITING = "editing"
    DIAGNOSING = "diagnosing"
    REVIEWING = "reviewing"


# Mapping from KlaatCode task types to Hermes agent capabilities
TASK_TO_CAPABILITY = {
    KlaatCodeTaskType.CODE_ANALYSIS: "analysis",
    KlaatCodeTaskType.CODE_GENERATION: "code_generation",
    KlaatCodeTaskType.CODE_EDITING: "code_generation",
    KlaatCodeTaskType.REFACTORING: "optimization",
    KlaatCodeTaskType.DIAGNOSTICS: "analysis",
    KlaatCodeTaskType.TEST_ANALYSIS: "testing",
    KlaatCodeTaskType.PROJECT_NAVIGATION: "analysis",
    KlaatCodeTaskType.PATCH_GENERATION: "code_generation",
    KlaatCodeTaskType.CODE_REVIEW: "code_review",
}

# Mapping from KlaatCode task types to MCP tool actions
TASK_TO_MCP_ACTION = {
    KlaatCodeTaskType.CODE_ANALYSIS: "analyze_project",
    KlaatCodeTaskType.CODE_GENERATION: "generate_code_plan",
    KlaatCodeTaskType.CODE_EDITING: "edit_file",
    KlaatCodeTaskType.REFACTORING: "edit_file",
    KlaatCodeTaskType.DIAGNOSTICS: "run_diagnostics",
    KlaatCodeTaskType.TEST_ANALYSIS: "run_diagnostics",
    KlaatCodeTaskType.PROJECT_NAVIGATION: "inspect_code",
    KlaatCodeTaskType.PATCH_GENERATION: "edit_file",
    KlaatCodeTaskType.CODE_REVIEW: "validate_changes",
}
