"""Behaviour: discovery classifies instruction vs config vs data."""
from __future__ import annotations

from tests.conftest import VR1, VR2, VR3

from psa.core.ports import LocalRepoFS
from psa.discovery import discover


def test_vr1_has_no_instruction_sources():
    sources = discover(LocalRepoFS(VR1))
    instructions = [s for s in sources if s.subtype == "instruction"]
    assert instructions == []
    configs = [s for s in sources if s.subtype == "config"]
    assert any(s.path.endswith("settings.local.json") or "serena" in s.path for s in configs)
    data = [s for s in sources if s.subtype == "data"]
    assert any("research" in s.path and s.path.endswith(".json") for s in data)


def test_vr2_discovers_cursor_rules_as_instruction():
    sources = discover(LocalRepoFS(VR2))
    paths = {s.path.replace("\\", "/") for s in sources if s.subtype == "instruction"}
    assert ".cursor/rules/architecture.mdc" in paths
    assert ".cursor/rules/bmad-builder.mdc" in paths
    assert ".cursor/rules/implementation.mdc" in paths


def test_vr3_discovers_agents_md():
    sources = discover(LocalRepoFS(VR3))
    agents = [s for s in sources if s.path.replace("\\", "/") == "AGENTS.md"]
    assert len(agents) == 1
    assert agents[0].subtype == "instruction"
    assert agents[0].default_ownership == "user"
    assert "Current Focus" in agents[0].text
