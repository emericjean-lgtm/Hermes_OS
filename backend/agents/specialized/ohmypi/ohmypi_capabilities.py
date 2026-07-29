"""Oh My Pi Agent capabilities (HOS-055B)."""

from enum import Enum


class OhMyPiTaskType(str, Enum):
    CODE_EDITING = "code_editing"
    DEBUGGING = "debugging"
    CODE_EXECUTION = "code_execution"
    AST_MANIPULATION = "ast_manipulation"
    LSP_NAVIGATION = "lsp_navigation"
    RUNTIME_TESTING = "runtime_testing"
    GIT_OPERATION = "git_operation"
    CODE_SEARCH = "code_search"


TASK_TO_CAPABILITY = {
    OhMyPiTaskType.CODE_EDITING: "code_generation",
    OhMyPiTaskType.DEBUGGING: "analysis",
    OhMyPiTaskType.CODE_EXECUTION: "testing",
    OhMyPiTaskType.AST_MANIPULATION: "code_generation",
    OhMyPiTaskType.LSP_NAVIGATION: "analysis",
    OhMyPiTaskType.RUNTIME_TESTING: "testing",
    OhMyPiTaskType.GIT_OPERATION: "custom",
    OhMyPiTaskType.CODE_SEARCH: "analysis",
}

TASK_TO_MCP_ACTION = {
    OhMyPiTaskType.CODE_EDITING: "lsp_edit",
    OhMyPiTaskType.DEBUGGING: "debug_start",
    OhMyPiTaskType.CODE_EXECUTION: "execute_python",
    OhMyPiTaskType.AST_MANIPULATION: "ast_transform",
    OhMyPiTaskType.LSP_NAVIGATION: "lsp_open_file",
    OhMyPiTaskType.RUNTIME_TESTING: "execute_python",
    OhMyPiTaskType.GIT_OPERATION: "git_operation",
    OhMyPiTaskType.CODE_SEARCH: "code_search",
}
