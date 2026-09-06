"""Le pont unique entre Hermes OS et Hermes Agent (HOS-265).

Un seul module parle au gateway de l'agent. Hermes OS garde toutes ses
autorités — Mission, Run Ledger, Aegis, ResourceManager, AdaptiveRouter,
RAL — et le pont n'en crée aucune : il **rapporte** ce que le runtime sait
faire et **relaie** les appels. Il ne choisit pas de modèle, n'admet rien
et n'ordonnance rien.
"""

from backend.bridge.hermes_agent_bridge import (
    CapaciteRuntime,
    HermesAgentBridge,
    NegociationRuntime,
)

__all__ = ["CapaciteRuntime", "HermesAgentBridge", "NegociationRuntime"]
