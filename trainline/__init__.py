"""trainline — Late Train Query Engine.

Hexagonal package (ports & adapters) with a pure-function domain core:

- ``trainline.engine``   — pure domain core (models, delay, optimiser); no I/O.
- ``trainline.adapters`` — I/O adapters (hsp_client, storage, config).
- ``trainline.cli``      — composition root wiring config → hsp_client → engine → storage.

See the architecture spine (AD-1..AD-12) for the invariants this layout enforces.
"""
