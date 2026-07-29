"""Code Intelligence Agent package (HOS-055D)."""

from .capabilities import (
    CI_EVENTS,
    CICapability,
    CodeIntelligenceAgentStatus,
    TASK_TO_CI_CAPABILITY,
)
from .code_intelligence_agent import (
    CITaskRecord,
    CodeIntelligenceAgent,
    create_code_intelligence_agent,
)
from .profile import CodeIntelligenceProfile

__all__ = [
    "CodeIntelligenceAgent",
    "CodeIntelligenceAgentStatus",
    "CodeIntelligenceProfile",
    "CICapability",
    "CI_EVENTS",
    "CITaskRecord",
    "TASK_TO_CI_CAPABILITY",
    "create_code_intelligence_agent",
]
