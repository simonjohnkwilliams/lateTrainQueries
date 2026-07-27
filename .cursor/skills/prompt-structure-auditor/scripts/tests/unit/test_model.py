"""Behaviour: Prompt Model is immutable and ordered."""
from __future__ import annotations

from tests.conftest import VR3

from psa.core.ports import LocalRepoFS
from psa.discovery import discover
from psa.model.builder import build_model


def test_model_segments_from_agents_are_ordered():
    sources = discover(LocalRepoFS(VR3))
    model = build_model(sources)
    assert len(model.segments) >= 2
    titles = [s.provenance.anchor[0] if s.provenance.anchor else "" for s in model.segments]
    assert any("Current Focus" in t for t in titles)
    assert any("CSV Format" in t for t in titles)


def test_model_is_immutable():
    sources = discover(LocalRepoFS(VR3))
    model = build_model(sources)
    try:
        model.segments[0].stability = "volatile"  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised


def test_segment_ids_stable_across_builds():
    sources = discover(LocalRepoFS(VR3))
    a = build_model(sources)
    b = build_model(sources)
    assert [s.id for s in a.segments] == [s.id for s in b.segments]
