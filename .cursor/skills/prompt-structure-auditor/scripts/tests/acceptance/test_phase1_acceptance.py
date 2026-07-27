"""Phase 1 Acceptance Test Suite (A/D/P/R/REP/G/CLI/I)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from psa.core.canon import dumps
from psa.core.config import DEFAULT_CONFIG
from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS, MemoryRepoFS
from psa.discovery import discover
from psa.model.builder import build_model
from psa.report.inventory import render_human, render_inventory
from psa.rules import run_rules
from tests.conftest import FIXTURES, LIVE_VR1, LIVE_VR2, LIVE_VR3

SCRIPTS = Path(__file__).resolve().parents[2]
FABRICATED = {
    "score",
    "cache_score",
    "stable_prefix",
    "hit_rate",
    "latency",
    "cost",
    "token_saving",
    "token_savings",
}


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _rule_ids(audit) -> set[str]:
    return {f.rule_id for f in audit.findings}


# ---------------------------------------------------------------------------
# A. Core Architecture
# ---------------------------------------------------------------------------


def test_A001_deterministic_output_ten_runs():
    fs = LocalRepoFS(FIXTURES / "vr3_demo")
    outputs = [dumps(analyze(fs, tool_version="0.1.0").to_dict()) for _ in range(10)]
    assert len(set(outputs)) == 1
    payload = json.loads(outputs[0])
    blob = outputs[0].lower()
    assert "timestamp" not in blob
    assert "created_at" not in blob
    ids = [f["id"] for f in payload["findings"]]
    assert ids == sorted(ids) or len(ids) == len(set(ids))


def test_A002_read_only_analysis(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# Hi\n\n## Architecture\nStable.\n", encoding="utf-8")
    before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    # init git so status is meaningful
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    analyze(LocalRepoFS(repo), tool_version="0.1.0")
    render_inventory(analyze(LocalRepoFS(repo), tool_version="0.1.0").inventory)
    after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert before == after == ""


def test_A003_prompt_model_immutability():
    sources = discover(LocalRepoFS(FIXTURES / "vr3_demo"))
    model = build_model(sources)
    before_seg = tuple((s.id, s.stability, s.order) for s in model.segments)
    before_edge = tuple((e.kind, e.src, e.dst) for e in model.edges)
    _ = list(run_rules(model, DEFAULT_CONFIG))
    after_seg = tuple((s.id, s.stability, s.order) for s in model.segments)
    after_edge = tuple((e.kind, e.src, e.dst) for e in model.edges)
    assert before_seg == after_seg
    assert before_edge == after_edge


def test_A004_stable_finding_ids_across_unrelated_edit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    agents = (FIXTURES / "vr3_demo" / "AGENTS.md").read_text(encoding="utf-8")
    (repo / "AGENTS.md").write_text(agents, encoding="utf-8")
    (repo / "README.md").write_text("v1\n", encoding="utf-8")
    a = analyze(LocalRepoFS(repo), tool_version="0.1.0")
    (repo / "README.md").write_text("v1\n# unrelated comment\n", encoding="utf-8")
    b = analyze(LocalRepoFS(repo), tool_version="0.1.0")
    assert [f.id for f in a.findings] == [f.id for f in b.findings]
    assert [f.rule_id for f in a.findings] == [f.rule_id for f in b.findings]
    # evidence paths/excerpts for ORDER001 unchanged
    a_ord = [f for f in a.findings if f.rule_id == "ORDER001"]
    b_ord = [f for f in b.findings if f.rule_id == "ORDER001"]
    assert [e.excerpt for f in a_ord for e in f.evidence] == [
        e.excerpt for f in b_ord for e in f.evidence
    ]


# ---------------------------------------------------------------------------
# B. Discovery
# ---------------------------------------------------------------------------


def test_D001_empty_repository():
    audit = analyze(LocalRepoFS(FIXTURES / "empty_repo"), tool_version="0.1.0")
    text = render_human(audit)
    assert audit.findings == ()
    assert "Inventory" in text or "Prompt Surface Inventory" in text
    assert "No prompt instruction surface" in text or "Honest empty" in text


def test_D002_agents_discovery():
    sources = discover(LocalRepoFS(FIXTURES / "vr3_demo"))
    agents = [s for s in sources if s.path.endswith("AGENTS.md")]
    assert len(agents) == 1
    assert agents[0].subtype == "instruction"
    model = build_model(tuple(sources))
    assert any(s.provenance.path.endswith("AGENTS.md") for s in model.segments)


def test_D003_claude_discovery():
    sources = discover(LocalRepoFS(FIXTURES / "with_claude"))
    claude = [s for s in sources if s.path.endswith("CLAUDE.md")]
    assert len(claude) == 1
    assert claude[0].default_ownership == "user"
    inv = analyze(LocalRepoFS(FIXTURES / "with_claude"), tool_version="0.1.0").inventory
    assert any(
        r.status == "present" and r.label.endswith("CLAUDE.md") for r in inv.rows
    )


def test_D004_cursor_rules_discovery():
    sources = discover(LocalRepoFS(FIXTURES / "vr2_latetrain"))
    mdcs = [s for s in sources if s.path.endswith(".mdc")]
    assert len(mdcs) == 3
    model = build_model(tuple(sources))
    assert any(s.provenance.anchor == ("(frontmatter)",) for s in model.segments)


def test_D005_config_classification():
    sources = discover(LocalRepoFS(FIXTURES / "vr1_empty"))
    configs = [s for s in sources if s.subtype == "config"]
    assert any("serena" in s.path for s in configs)
    sources2 = discover(LocalRepoFS(FIXTURES / "vr2_latetrain"))
    assert any(s.adapter == "opencode" and s.subtype == "config" for s in sources2)
    assert not any(s.subtype == "instruction" and "serena" in s.path for s in sources)
    assert not any(s.subtype == "instruction" and "opencode" in s.path for s in sources2)


def test_D006_research_exclusion():
    sources = discover(LocalRepoFS(FIXTURES / "vr1_empty"))
    data = [s for s in sources if s.subtype == "data"]
    assert any("research" in s.path for s in data)
    audit = analyze(LocalRepoFS(FIXTURES / "vr1_empty"), tool_version="0.1.0")
    assert not any("research" in e.path for f in audit.findings for e in f.evidence)


# ---------------------------------------------------------------------------
# C. Prompt Model
# ---------------------------------------------------------------------------


def test_P001_segment_classification():
    model = build_model(discover(LocalRepoFS(FIXTURES / "vr3_demo")))
    by_anchor = {s.provenance.anchor[0]: s for s in model.segments if s.provenance.anchor}
    assert by_anchor["CSV Format"].stability == "stable"
    assert by_anchor["Current Focus: CSV Import"].stability == "volatile"
    assert by_anchor["Current Focus: CSV Import"].is_prefix_poison is True
    # On Hold is worklog volatile, not prefix poison
    hold = next(s for s in model.segments if "On Hold" in (s.provenance.anchor[0] if s.provenance.anchor else ""))
    assert hold.is_prefix_poison is False


def test_P002_relationship_generation():
    model = build_model(discover(LocalRepoFS(FIXTURES / "vr2_latetrain")))
    kinds = [e.kind for e in model.edges]
    assert "precedes" in kinds
    assert "governs" in kinds
    assert len(model.edges) == len(set((e.kind, e.src, e.dst) for e in model.edges))


def test_P003_ownership_classification():
    model = build_model(discover(LocalRepoFS(FIXTURES / "vr3_demo")))
    for seg in model.segments:
        assert seg.ownership in {"user", "tool", "provider", "unknown"}
        assert seg.evidence
        assert seg.confidence in {"high", "medium", "low"}


# ---------------------------------------------------------------------------
# D. Rule Validation
# ---------------------------------------------------------------------------


def test_R001_order001_positive():
    assert "ORDER001" in _rule_ids(analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0"))


def test_R002_order001_negative_stable_first():
    assert "ORDER001" not in _rule_ids(analyze(LocalRepoFS(FIXTURES / "order_ok"), tool_version="0.1.0"))


def test_R003_order001_reference_false_positive():
    assert "ORDER001" not in _rule_ids(analyze(LocalRepoFS(FIXTURES / "vr2_latetrain"), tool_version="0.1.0"))


def test_R004_act001_positive():
    assert "ACT001" in _rule_ids(analyze(LocalRepoFS(FIXTURES / "vr2_latetrain"), tool_version="0.1.0"))


def test_R005_act001_negative_proper_metadata():
    assert "ACT001" not in _rule_ids(analyze(LocalRepoFS(FIXTURES / "act_ok"), tool_version="0.1.0"))


def test_R006_act002_positive():
    assert "ACT002" in _rule_ids(analyze(LocalRepoFS(FIXTURES / "vr2_latetrain"), tool_version="0.1.0"))


def test_R007_style001_positive():
    assert "STYLE001" in _rule_ids(analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0"))


def test_R008_style001_negative():
    assert "STYLE001" not in _rule_ids(analyze(LocalRepoFS(FIXTURES / "style_ok"), tool_version="0.1.0"))


def test_R009_dup001_positive():
    assert "DUP001" in _rule_ids(analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0"))


def test_R010_dup001_negative():
    assert "DUP001" not in _rule_ids(analyze(LocalRepoFS(FIXTURES / "dup_ok"), tool_version="0.1.0"))


# ---------------------------------------------------------------------------
# E. Report Validation
# ---------------------------------------------------------------------------


def test_REP001_human_report_sections():
    text = render_human(analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0"))
    assert "Prompt Surface Inventory" in text
    assert "Executive Summary" in text
    assert "Findings" in text
    assert "Honesty note" in text


def test_REP002_json_schema_fields():
    audit = analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0")
    assert audit.findings
    for f in audit.findings:
        d = f.to_dict()
        for key in ("id", "rule_id", "priority", "verification", "ownership", "evidence", "confidence"):
            assert key in d
            assert d[key] not in (None, "", [])


def test_REP003_no_fabricated_metrics():
    blob = dumps(analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0").to_dict()).lower()
    for bad in FABRICATED:
        assert bad not in blob


# ---------------------------------------------------------------------------
# F. Golden / live validation repos
# ---------------------------------------------------------------------------


def test_G001_vr1_fixture():
    audit = analyze(LocalRepoFS(FIXTURES / "vr1_empty"), tool_version="0.1.0")
    assert audit.findings == ()
    text = render_inventory(audit.inventory)
    assert any(r.status == "out_of_scope" for r in audit.inventory.rows) or "research" in text.lower()


@pytest.mark.skipif(not LIVE_VR1.is_dir(), reason="VR1 missing")
def test_G001_vr1_live():
    audit = analyze(LocalRepoFS(LIVE_VR1), tool_version="0.1.0")
    assert "ORDER001" not in _rule_ids(audit)
    assert not any("research" in e.path and f.rule_id.startswith("ORDER") for f in audit.findings for e in f.evidence)


def test_G002_vr2_fixture():
    audit = analyze(LocalRepoFS(FIXTURES / "vr2_latetrain"), tool_version="0.1.0")
    ids = _rule_ids(audit)
    assert "ACT001" in ids
    assert "ACT002" in ids
    assert "DUP001" in ids
    assert "ORDER001" not in ids


@pytest.mark.skipif(not LIVE_VR2.is_dir(), reason="VR2 missing")
def test_G002_vr2_live():
    audit = analyze(LocalRepoFS(LIVE_VR2), tool_version="0.1.0")
    ids = _rule_ids(audit)
    assert "ACT001" in ids
    assert "ACT002" in ids
    assert "ORDER001" not in ids


def test_G003_vr3_fixture_order_not_noisy():
    audit = analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0")
    ids = _rule_ids(audit)
    assert "ORDER001" in ids
    assert "STYLE001" in ids
    assert "DUP001" in ids
    order_titles = [f.title for f in audit.findings if f.rule_id == "ORDER001"]
    assert len(order_titles) == 1
    assert "Current Focus" in order_titles[0]
    assert not any("On Hold" in t or "Debugging" in t for t in order_titles)


@pytest.mark.skipif(not LIVE_VR3.is_dir(), reason="VR3 missing")
def test_G003_vr3_live_finance_tracker_healthy():
    audit = analyze(LocalRepoFS(LIVE_VR3), tool_version="0.1.0")
    assert audit.findings == ()
    assert sum(1 for r in audit.inventory.rows if r.status == "present") >= 1
    assert "ORDER001" not in _rule_ids(audit)


# ---------------------------------------------------------------------------
# G. CLI
# ---------------------------------------------------------------------------


def test_CLI001_doctor():
    proc = subprocess.run(
        [sys.executable, "-m", "psa", "doctor", str(FIXTURES / "vr3_demo")],
        cwd=str(SCRIPTS),
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )
    assert proc.returncode == 0
    assert "Doctor" in proc.stdout
    assert "Instruction Sources" in proc.stdout


def test_CLI002_audit():
    proc = subprocess.run(
        [sys.executable, "-m", "psa", "audit", str(FIXTURES / "vr3_demo")],
        cwd=str(SCRIPTS),
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )
    assert proc.returncode == 0
    assert "Summary" in proc.stdout
    assert "Findings" in proc.stdout
    assert "| Field | Result |" in proc.stdout


def test_CLI003_format_json():
    proc = subprocess.run(
        [sys.executable, "-m", "psa", "audit", str(FIXTURES / "vr3_demo"), "--format", "json"],
        cwd=str(SCRIPTS),
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert "findings" in data
    assert dumps(data) == proc.stdout if proc.stdout.endswith("\n") else dumps(data).rstrip("\n") == proc.stdout.rstrip("\n")


def test_CLI004_out_only_when_requested(tmp_path):
    out = tmp_path / "audit.json"
    repo = FIXTURES / "empty_repo"
    # without --out, no file created in repo
    before = set(p.name for p in repo.iterdir())
    subprocess.run(
        [sys.executable, "-m", "psa", "audit", str(repo)],
        cwd=str(SCRIPTS),
        capture_output=True,
        text=True,
        env=_env(),
        check=True,
    )
    after = set(p.name for p in repo.iterdir())
    assert before == after
    subprocess.run(
        [sys.executable, "-m", "psa", "audit", str(repo), "--format", "json", "--out", str(out)],
        cwd=str(SCRIPTS),
        capture_output=True,
        text=True,
        env=_env(),
        check=True,
    )
    assert out.is_file()
    json.loads(out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# H. Engineering Integrity
# ---------------------------------------------------------------------------


def test_I001_to_I005_finding_integrity():
    from psa.rules import _REGISTRY

    known_rules = {rule_id for _, rule_id, _ in _REGISTRY}
    for fixture in ("vr3_demo", "vr2_latetrain", "vr1_empty"):
        audit = analyze(LocalRepoFS(FIXTURES / fixture), tool_version="0.1.0")
        for f in audit.findings:
            assert f.ownership in {"user", "tool", "provider", "unknown"}
            assert f.verification in {"confirmed", "requires-verification"}
            assert f.evidence
            assert f.confidence in {"high", "medium", "low"}
            assert f.rule_id in known_rules


def test_I006_every_rule_one_pack():
    from psa.rules import _REGISTRY

    by_rule: dict[str, set[str]] = {}
    for pack, rule_id, _ in _REGISTRY:
        by_rule.setdefault(rule_id, set()).add(pack)
    assert all(len(packs) == 1 for packs in by_rule.values())


def test_I007_inventory_always_generated():
    for fixture in ("empty_repo", "vr1_empty", "vr3_demo"):
        audit = analyze(LocalRepoFS(FIXTURES / fixture), tool_version="0.1.0")
        assert audit.inventory.rows


def test_I008_no_duplicate_findings_same_evidence():
    audit = analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0")
    keys = []
    for f in audit.findings:
        ev = tuple((e.path, e.span, e.excerpt) for e in f.evidence)
        keys.append((f.rule_id, ev))
    assert len(keys) == len(set(keys))
