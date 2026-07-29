"""Multi-Agent Collaboration Engine (HOS-044).

Enables inter-agent communication, context sharing, delegation,
reviews, consensus, and conflict resolution.
"""

from backend.agents.collaboration.collaboration_models import (
    AgentMessage,
    MessageType,
    Delegation,
    DelegationStatus,
    Review,
    ReviewStatus,
    SharedContext,
    ConsensusProposal,
    ConsensusMode,
    ConsensusStatus,
    Conflict,
    ConflictType,
    ConflictStatus,
)
from backend.agents.collaboration.message_bus import MessageBus
from backend.agents.collaboration.context_sharing import ContextSharing
from backend.agents.collaboration.delegation_manager import DelegationManager
from backend.agents.collaboration.consensus_engine import ConsensusEngine
from backend.agents.collaboration.conflict_resolver import ConflictResolver
from backend.agents.collaboration.collaboration_engine import CollaborationEngine

__all__ = [
    "AgentMessage",
    "MessageType",
    "Delegation",
    "DelegationStatus",
    "Review",
    "ReviewStatus",
    "SharedContext",
    "ConsensusProposal",
    "ConsensusMode",
    "ConsensusStatus",
    "Conflict",
    "ConflictType",
    "ConflictStatus",
    "MessageBus",
    "ContextSharing",
    "DelegationManager",
    "ConsensusEngine",
    "ConflictResolver",
    "CollaborationEngine",
]
