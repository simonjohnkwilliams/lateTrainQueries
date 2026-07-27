"""Release acceptance R1–R6 against fixtures + live IdeaProjects repos.

Every present target (fixtures always; live when on disk) is exercised so the
public audit format stays identical across repository runs. Later releases may
append behaviour but must not reshape the frozen R1 audit report.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS
from psa.patch.generate import preview_patch
from psa.patch.validate import validate_patch
from psa.report.audit_view import render_audit
from tests.conftest import (
    ALL_TARGETS,
    FIXTURES,
    LIVE_VR1,
    LIVE_VR2,
    LIVE_VR3,
    present_targets,
)
from tests.contract import assert_frozen_audit_structure, normalized_audit_structure

SCRIPTS = Path(__file__).resolve().parents[2]
FABRICATED = ("score", "hit_rate", "latency", "cost", "token_saving", "token_savings", "cache_score")


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "psa", *args],
        cwd=str(SCRIPTS),
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )


def _rule_ids(audit) -> set[str]:
    return {f.rule_id for f in audit.findings}


@pytest.fixture(params=present_targets(), ids=lambda t: t[0])
def target(request) -> tuple[str, Path, bool]:
    return request.param


# ---------------------------------------------------------------------------
# Cross-target format lock (all releases depend on this)
# ---------------------------------------------------------------------------


class TestFormatConsistency:
    def test_all_present_targets_share_identical_audit_structure(self):
        present = present_targets()
        assert any(not live for _, _, live in present), "fixtures must be present"
        structures: dict[str, str] = {}
        for name, path, _ in present:
            text = render_audit(
                analyze(LocalRepoFS(path), tool_version="0.1.0"),
                repo_name=path.name,
            )
            assert_frozen_audit_structure(text, name)
            structures[name] = normalized_audit_structure(text)
        canonical = next(iter(structures.values()))
        for name, block in structures.items():
            assert block == canonical, (
                f"{name} audit structure diverged from suite canonical form:\n{block}"
            )

    def test_cli_audit_matches_render_contract(self, target: tuple[str, Path, bool]):
        name, path, _ = target
        proc = _cli("audit", str(path))
        assert proc.returncode == 0, f"{name}: {proc.stderr}"
        assert_frozen_audit_structure(proc.stdout, name)
        assert proc.stdout.encode("ascii")


# ---------------------------------------------------------------------------
# R1 — Audit
# ---------------------------------------------------------------------------


class TestRelease1Audit:
    def test_r1_doctor_cli(self, target: tuple[str, Path, bool]):
        name, path, _ = target
        proc = _cli("doctor", str(path))
        assert proc.returncode == 0, f"{name}: {proc.stderr}"
        assert "Doctor" in proc.stdout
        assert "Instruction Sources" in proc.stdout

    def test_r1_audit_text_frozen(self, target: tuple[str, Path, bool]):
        name, path, _ = target
        text = render_audit(analyze(LocalRepoFS(path), tool_version="0.1.0"), repo_name=name)
        assert_frozen_audit_structure(text, name)

    def test_r1_audit_json_shape_no_fabricated(self, target: tuple[str, Path, bool]):
        name, path, _ = target
        proc = _cli("audit", str(path), "--format", "json")
        assert proc.returncode == 0, f"{name}: {proc.stderr}"
        data = json.loads(proc.stdout)
        for key in ("meta", "inventory", "findings", "dependency_graph", "guidance"):
            assert key in data, f"{name} missing {key}"

        def _walk_keys(obj) -> set[str]:
            keys: set[str] = set()
            if isinstance(obj, dict):
                keys.update(obj.keys())
                for v in obj.values():
                    keys |= _walk_keys(v)
            elif isinstance(obj, list):
                for v in obj:
                    keys |= _walk_keys(v)
            return keys

        keys_lower = {k.lower() for k in _walk_keys(data)}
        for bad in FABRICATED:
            assert bad not in keys_lower, f"{name} leaked fabricated metric key: {bad}"

    def test_r1_vr1_honest_empty(self):
        for name, path in (("VR1_fixture", FIXTURES / "vr1_empty"), ("VR1_live", LIVE_VR1)):
            if not path.is_dir():
                continue
            audit = analyze(LocalRepoFS(path), tool_version="0.1.0")
            assert audit.findings == (), f"{name} must not fabricate findings"
            assert "ORDER001" not in _rule_ids(audit)

    def test_r1_vr2_activation_surface(self):
        for name, path in (("VR2_fixture", FIXTURES / "vr2_latetrain"), ("VR2_live", LIVE_VR2)):
            if not path.is_dir():
                continue
            ids = _rule_ids(analyze(LocalRepoFS(path), tool_version="0.1.0"))
            assert "ACT001" in ids, name
            assert "ACT002" in ids, name
            assert "ORDER001" not in ids, name

    def test_r1_vr3_fixture_order_style_dup(self):
        path = FIXTURES / "vr3_demo"
        audit = analyze(LocalRepoFS(path), tool_version="0.1.0")
        ids = _rule_ids(audit)
        assert "ORDER001" in ids and "STYLE001" in ids and "DUP001" in ids
        order_titles = [f.title for f in audit.findings if f.rule_id == "ORDER001"]
        assert any("Current Focus" in t for t in order_titles)
        assert not any(
            "On Hold" in t or "Debugging" in t or "Known Issue" in t for t in order_titles
        )

    def test_r1_vr3_live_finance_tracker_healthy(self):
        if not LIVE_VR3.is_dir():
            pytest.skip("VR3 live missing")
        audit = analyze(LocalRepoFS(LIVE_VR3), tool_version="0.1.0")
        text = render_audit(audit, repo_name=LIVE_VR3.name)
        assert_frozen_audit_structure(text, "VR3_live")
        assert audit.findings == ()
        assert "Healthy" in text


# ---------------------------------------------------------------------------
# R2 — Prioritise (must not break R1 audit format)
# ---------------------------------------------------------------------------


class TestRelease2Plan:
    def test_r2_audit_stays_factual(self, target: tuple[str, Path, bool]):
        name, path, _ = target
        text = render_audit(analyze(LocalRepoFS(path), tool_version="0.1.0"), repo_name=name)
        assert_frozen_audit_structure(text, name)
        assert "Recommended Plan" not in text
        assert "Recommendation Details" not in text

    def test_r2_plan_cli_frozen_contract(self, target: tuple[str, Path, bool]):
        from tests.contract_plan import assert_frozen_plan_structure

        name, path, _ = target
        audit = analyze(LocalRepoFS(path), tool_version="0.1.0")
        proc = _cli("plan", str(path))
        assert proc.returncode == 0, f"{name}: {proc.stderr}"
        assert_frozen_plan_structure(proc.stdout, name)
        if not audit.findings:
            assert "No action needed" in proc.stdout, name
            assert "Already Healthy" in proc.stdout, name
        else:
            assert "Plan ready" in proc.stdout, name
            assert "Why now" in proc.stdout, name
            assert "Expected end state" in proc.stdout, name
            assert "Unblocks" not in proc.stdout, name

    def test_r2_plan_json(self, target: tuple[str, Path, bool]):
        name, path, _ = target
        proc = _cli("plan", str(path), "--format", "json")
        assert proc.returncode == 0, f"{name}: {proc.stderr}"
        data = json.loads(proc.stdout)
        assert "plan" in data
        assert "findings_considered" in data
        for step in data["plan"]:
            for key in (
                "why_now",
                "unblocks",
                "remaining_after",
                "estimated_effort",
                "depends_on",
                "findings",
            ):
                assert key in step, f"{name} plan step missing {key}"

    def test_r2_vr3_dependencies_order_in_plan(self):
        path = FIXTURES / "vr3_demo"
        audit = analyze(LocalRepoFS(path), tool_version="0.1.0")
        plan_rules = [p.rule_ids[0] for p in audit.dependency_graph.plan]
        assert "ORDER001" in plan_rules
        assert plan_rules.index("ORDER001") > min(
            i for i, r in enumerate(plan_rules) if r in {"DUP001", "STYLE001"}
        )


# ---------------------------------------------------------------------------
# R3 — Preview (matrix: patchable vs consistent refusal)
# ---------------------------------------------------------------------------


class TestRelease3Preview:
    def test_r3_preview_matrix(self, target: tuple[str, Path, bool]):
        name, path, _ = target
        audit = analyze(LocalRepoFS(path), tool_version="0.1.0")
        proc = _cli("patch", "preview", "ORDER001", str(path))
        if "ORDER001" in _rule_ids(audit):
            assert proc.returncode == 0, f"{name}: {proc.stderr}"
            assert "---" in proc.stdout or "@@" in proc.stdout
        else:
            assert proc.returncode != 0, f"{name}: preview must fail without ORDER001"
            assert proc.stderr.strip(), f"{name}: refusal must explain why"

    def test_r3_preview_no_writes_when_patchable(self):
        path = FIXTURES / "vr3_demo"
        agents = path / "AGENTS.md"
        before = agents.read_text(encoding="utf-8")
        assert _cli("patch", "preview", "ORDER001", str(path)).returncode == 0
        assert agents.read_text(encoding="utf-8") == before

    def test_r3_preview_api_matches_cli(self):
        path = FIXTURES / "vr3_demo"
        fs = LocalRepoFS(path)
        audit = analyze(fs, tool_version="0.1.0")
        patch = preview_patch(fs, audit, "ORDER001")
        proc = _cli("patch", "preview", "ORDER001", str(path))
        assert proc.returncode == 0
        assert patch.diff.strip() == proc.stdout.strip() or patch.diff in proc.stdout

    def test_r3_preview_non_patchable_errors(self):
        path = FIXTURES / "vr3_demo"
        proc = _cli("patch", "preview", "STYLE001", str(path))
        assert proc.returncode != 0


# ---------------------------------------------------------------------------
# R4 — Validate
# ---------------------------------------------------------------------------


class TestRelease4Validate:
    def test_r4_validate_matrix(self, target: tuple[str, Path, bool]):
        name, path, _ = target
        audit = analyze(LocalRepoFS(path), tool_version="0.1.0")
        proc = _cli("patch", "validate", "ORDER001", str(path))
        if "ORDER001" in _rule_ids(audit):
            assert proc.returncode == 0, f"{name}: {proc.stderr}\n{proc.stdout}"
            assert "Patch Validation" in proc.stdout
            assert "PASS" in proc.stdout
            assert "Introduced:" in proc.stdout
        else:
            assert proc.returncode != 0, f"{name}: validate must fail without ORDER001"

    def test_r4_validate_json_ok(self):
        path = FIXTURES / "vr3_demo"
        proc = _cli("patch", "validate", "ORDER001", str(path), "--format", "json")
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["ok"] is True
        assert data["introduced"] == []

    def test_r4_validate_api_invariant(self):
        path = FIXTURES / "vr3_demo"
        fs = LocalRepoFS(path)
        audit = analyze(fs, tool_version="0.1.0")
        patch = preview_patch(fs, audit, "ORDER001")
        result = validate_patch(fs, audit, patch, tool_version="0.1.0")
        assert result.ok is True, result.failures
        assert patch.finding_id in result.resolved
        assert result.introduced == ()


# ---------------------------------------------------------------------------
# R5 — Apply (never mutates live repos; refuse without --yes everywhere)
# ---------------------------------------------------------------------------


class TestRelease5Apply:
    def test_r5_refuse_without_yes_on_all_targets(self, target: tuple[str, Path, bool]):
        name, path, _ = target
        audit = analyze(LocalRepoFS(path), tool_version="0.1.0")
        proc = _cli("patch", "apply", "ORDER001", str(path))
        assert proc.returncode != 0, f"{name}: apply without --yes must not succeed"
        if "ORDER001" in _rule_ids(audit):
            assert proc.returncode == 2, f"{name}: expected refuse without --yes"
            assert "--yes" in proc.stderr
        # Live repos must never be mutated by the suite (no --yes path here).

    def test_r5_apply_on_temp_fixture_copy(self, tmp_path: Path):
        src = FIXTURES / "vr3_demo"
        demo = tmp_path / "apply-demo"
        shutil.copytree(src, demo)
        subprocess.run(["git", "init"], cwd=demo, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=demo, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
            cwd=demo,
            check=True,
            capture_output=True,
        )
        proc = _cli("patch", "apply", "ORDER001", str(demo), "--yes")
        assert proc.returncode == 0, proc.stderr + proc.stdout
        assert "Patch Applied" in proc.stdout
        assert "Branch:" in proc.stdout
        assert "Rollback" in proc.stdout or "checkout" in proc.stdout.lower()


# ---------------------------------------------------------------------------
# R6 — Continuous (baseline / diff) on every present target
# ---------------------------------------------------------------------------


class TestRelease6Continuous:
    def test_r6_baseline_and_diff_format(self, target: tuple[str, Path, bool], tmp_path: Path):
        name, path, _ = target
        base = tmp_path / f"{name}-baseline.json"
        save = _cli("baseline", "save", str(path), "--out", str(base))
        assert save.returncode == 0, f"{name}: {save.stderr}"
        assert base.is_file()
        data = json.loads(base.read_text(encoding="utf-8"))
        assert "findings" in data and "meta" in data

        # Diff against self → no introductions
        diff = _cli("diff", str(path), "--baseline", str(base))
        assert diff.returncode == 0, f"{name}: {diff.stderr}"
        assert "Audit Diff" in diff.stdout
        assert "Resolved:" in diff.stdout
        assert "Introduced:" in diff.stdout
        assert "Unchanged:" in diff.stdout

        fail = _cli("diff", str(path), "--baseline", str(base), "--fail-on-introduced")
        assert fail.returncode == 0, f"{name}: self-diff must not fail-on-introduced"

    def test_r6_fail_on_introduced_across_empty_to_issues(self, tmp_path: Path):
        empty = FIXTURES / "empty_repo"
        issues = FIXTURES / "vr3_demo"
        base = tmp_path / "empty.json"
        assert _cli("baseline", "save", str(empty), "--out", str(base)).returncode == 0
        diff = _cli("diff", str(issues), "--baseline", str(base), "--fail-on-introduced")
        assert diff.returncode == 1
        assert "Introduced:" in diff.stdout

    def test_r6_audit_format_still_frozen_after_lifecycle(self, target: tuple[str, Path, bool]):
        name, path, _ = target
        text = render_audit(analyze(LocalRepoFS(path), tool_version="0.1.0"), repo_name=name)
        assert_frozen_audit_structure(text, name)


# ---------------------------------------------------------------------------
# Release matrix summary (fixtures + live)
# ---------------------------------------------------------------------------


def test_r1_to_r6_matrix_summary(capsys, tmp_path: Path):
    """Print a concise release matrix for human feedback when pytest -s."""
    rows: list[str] = []
    for name, path, live in ALL_TARGETS:
        if not path.is_dir():
            rows.append(f"{name}: SKIP (missing)")
            continue
        audit = analyze(LocalRepoFS(path), tool_version="0.1.0")
        ids = sorted(_rule_ids(audit))
        text = render_audit(audit, repo_name=path.name)
        try:
            assert_frozen_audit_structure(text, name)
            r1 = "OK"
        except AssertionError:
            r1 = "FAIL"

        if not audit.findings:
            plan_out = _cli("plan", str(path)).stdout
            r2 = "OK" if "No action needed" in plan_out and "Recommended Plan" in plan_out else "FAIL"
        else:
            plan_out = _cli("plan", str(path)).stdout
            r2 = (
                "OK"
                if "Plan ready" in plan_out
                and "Why now" in plan_out
                and "Expected end state" in plan_out
                and "Recommended Plan" not in text
                else "FAIL"
            )

        r3 = r4 = "n/a"
        if "ORDER001" in ids:
            prev = _cli("patch", "preview", "ORDER001", str(path))
            val = _cli("patch", "validate", "ORDER001", str(path))
            r3 = "OK" if prev.returncode == 0 else "FAIL"
            r4 = "OK" if val.returncode == 0 and "PASS" in val.stdout else "FAIL"
        else:
            prev = _cli("patch", "preview", "ORDER001", str(path))
            r3 = "OK" if prev.returncode != 0 else "FAIL"
            r4 = "n/a"

        refuse = _cli("patch", "apply", "ORDER001", str(path))
        if "ORDER001" in ids:
            r5 = "OK" if refuse.returncode == 2 and "--yes" in refuse.stderr else "FAIL"
        else:
            r5 = "OK" if refuse.returncode != 0 else "FAIL"

        base = tmp_path / f"{name}.json"
        save = _cli("baseline", "save", str(path), "--out", str(base))
        diff = _cli("diff", str(path), "--baseline", str(base)) if save.returncode == 0 else None
        r6 = "OK" if save.returncode == 0 and diff and diff.returncode == 0 and "Audit Diff" in diff.stdout else "FAIL"

        kind = "live" if live else "fixture"
        rows.append(
            f"{name} ({kind}): findings={len(audit.findings)} rules={ids} "
            f"R1={r1} R2={r2} R3={r3} R4={r4} R5={r5} R6={r6}"
        )

    report = "\n".join(rows)
    print("\n=== R1–R6 release matrix (fixtures + live) ===\n" + report + "\n")
    assert any(r.startswith("VR3_fixture ") and "R4=OK" in r for r in rows)
    assert any(r.startswith("VR1_fixture ") and "findings=0" in r for r in rows)
    # Live targets: if present, must be green on format + R5 refuse + R6
    for name, path, live in present_targets():
        if not live:
            continue
        matching = [r for r in rows if r.startswith(f"{name} ")]
        assert matching, name
        assert "R1=OK" in matching[0], matching[0]
        assert "R5=OK" in matching[0], matching[0]
        assert "R6=OK" in matching[0], matching[0]
