"""Architecture-level test package — HOS-000 foundation.

Tests under this package verify invariants that span the whole project:
the RAL isolation (HOS-001+), the EventBus contract, the singleton
discipline, the SDS front-end contract, etc. Tests live next to the
production code only when they test a single module; when they test
cross-cutting invariants, they live here.
"""
__all__: list[str] = []
