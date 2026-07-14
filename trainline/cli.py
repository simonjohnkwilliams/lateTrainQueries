"""Composition root (AD-8) — the only MVP orchestrator.

Stub for Story 1.1 (scaffold). Implemented in Story 3.3. Wires
config → hsp_client → engine.optimise → storage. May import everything (AD-2);
a future Lambda handler would be a second composition root calling the same
``engine.optimise``.
"""
