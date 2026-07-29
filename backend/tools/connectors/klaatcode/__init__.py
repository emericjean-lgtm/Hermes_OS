"""KlaatCode connector — MCP-based coding agent integration (HOS-054B)."""

from .klaatcode_client import KlaatCodeClient
from .klaatcode_mcp_adapter import KlaatCodeMCPAdapter
from .klaatcode_models import (
    DiagnosticSeverity,
    KlaatCodeAction,
    KlaatCodeCapability,
    KlaatCodeDiagnostic,
    KlaatCodeProject,
    KlaatCodeRequest,
    KlaatCodeResponse,
    KlaatCodeStatus,
)
from .registration import (
    register_klaatcode,
    get_registered_mcp_server,
    get_registered_tools,
)

__all__ = [
    # Models
    "KlaatCodeRequest",
    "KlaatCodeResponse",
    "KlaatCodeProject",
    "KlaatCodeDiagnostic",
    "KlaatCodeCapability",
    "KlaatCodeAction",
    "KlaatCodeStatus",
    "DiagnosticSeverity",
    # Components
    "KlaatCodeClient",
    "KlaatCodeMCPAdapter",
    # Registration
    "register_klaatcode",
    "get_registered_mcp_server",
    "get_registered_tools",
]
