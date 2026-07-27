"""CLI for Prompt Structure Auditor."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from psa.core.canon import dumps
from psa.core.config import DEFAULT_CONFIG, ConfigView
from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS
from psa.discovery import discover
from psa.lifecycle.baseline import load_baseline, save_baseline
from psa.lifecycle.diff import diff_audits
from psa.patch.apply import apply_patch
from psa.patch.generate import preview_patch
from psa.patch.validate import validate_patch
from psa.report.audit_view import render_audit, repo_display_name
from psa.report.doctor import render_doctor
from psa.report.plan_view import render_plan


def _add_ignore_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--no-default-ignores",
        action="store_true",
        help="Include paths normally excluded (tests/, fixtures/, skill test trees)",
    )


def _config_from_args(args: argparse.Namespace) -> ConfigView:
    if getattr(args, "no_default_ignores", False):
        return DEFAULT_CONFIG.with_no_default_ignores()
    return DEFAULT_CONFIG


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="psa",
        description=(
            "Prompt Structure Auditor — "
            "audit (health) · plan (remediation) · doctor · patch lifecycle"
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser(
        "audit",
        help="What do I have, and is it healthy? (factual assessment)",
    )
    p_audit.add_argument("path", nargs="?", default=".", help="Repository path")
    p_audit.add_argument("--format", choices=("text", "json"), default="text")
    p_audit.add_argument("--out", default=None, help="Write output to file")
    _add_ignore_flag(p_audit)

    p_plan = sub.add_parser(
        "plan",
        help="What should I fix first, and why? (Recommended Plan)",
    )
    p_plan.add_argument("path", nargs="?", default=".", help="Repository path")
    p_plan.add_argument("--format", choices=("text", "json"), default="text")
    p_plan.add_argument("--out", default=None, help="Write output to file")
    _add_ignore_flag(p_plan)

    p_doc = sub.add_parser(
        "doctor",
        help="Why was (or wasn't) something analysed? (diagnostics)",
    )
    p_doc.add_argument("path", nargs="?", default=".", help="Repository path")
    _add_ignore_flag(p_doc)

    p_base = sub.add_parser("baseline", help="Baseline operations")
    base_sub = p_base.add_subparsers(dest="base_cmd", required=True)
    p_save = base_sub.add_parser("save", help="Save baseline audit JSON")
    p_save.add_argument("path", nargs="?", default=".", help="Repository path")
    p_save.add_argument("--out", required=True, help="Baseline output path")
    _add_ignore_flag(p_save)

    p_diff = sub.add_parser("diff", help="Diff current audit against a baseline")
    p_diff.add_argument("path", nargs="?", default=".", help="Repository path")
    p_diff.add_argument("--baseline", required=True, help="Baseline JSON path")
    p_diff.add_argument("--format", choices=("text", "json"), default="text")
    p_diff.add_argument(
        "--fail-on-introduced",
        action="store_true",
        help="Exit 1 if any findings were introduced (CI ratchet)",
    )
    _add_ignore_flag(p_diff)

    p_patch = sub.add_parser("patch", help="Patch preview / validate / apply")
    patch_sub = p_patch.add_subparsers(dest="patch_cmd", required=True)

    def _add_finding_path(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "finding_id",
            help="Finding id (f_…) or rule id (e.g. ORDER001)",
        )
        p.add_argument("path", nargs="?", default=".", help="Repository path")
        _add_ignore_flag(p)

    p_prev = patch_sub.add_parser("preview", help="Preview mechanical patch (no writes)")
    _add_finding_path(p_prev)

    p_val = patch_sub.add_parser("validate", help="Re-audit scratch copy; must not worsen")
    _add_finding_path(p_val)
    p_val.add_argument("--format", choices=("text", "json"), default="text")

    p_app = patch_sub.add_parser("apply", help="Apply validated patch on a new git branch")
    _add_finding_path(p_app)
    p_app.add_argument("--branch", default=None, help="Branch name override")
    p_app.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation flag to write to the repository",
    )

    args = parser.parse_args(argv)
    cfg = _config_from_args(args)

    if args.cmd == "baseline" and args.base_cmd == "save":
        root = Path(args.path).resolve()
        if not root.exists():
            print(f"path not found: {root}", file=sys.stderr)
            return 2
        audit = analyze(LocalRepoFS(root), config=cfg)
        save_baseline(audit, args.out)
        print(f"baseline saved: {args.out}")
        return 0

    if args.cmd == "patch":
        root = Path(args.path).resolve()
        if not root.exists():
            print(f"path not found: {root}", file=sys.stderr)
            return 2
        fs = LocalRepoFS(root)
        audit = analyze(fs, config=cfg)
        try:
            patch = preview_patch(fs, audit, args.finding_id)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        if args.patch_cmd == "preview":
            print(patch.diff, end="")
            return 0

        if args.patch_cmd == "validate":
            result = validate_patch(fs, audit, patch)
            if args.format == "json":
                print(dumps(result.to_dict()), end="")
            else:
                print("Patch Validation")
                print(f"  Target:     {patch.rule_id} ({patch.finding_id})")
                print(f"  Result:     {'PASS' if result.ok else 'FAIL'}")
                print(f"  Resolved:   {len(result.resolved)}")
                print(f"  Introduced: {len(result.introduced)}")
                print(f"  Worsened:   {len(result.worsened)}")
                for msg in result.failures:
                    print(f"  - {msg}")
                if result.introduced:
                    print("  Introduced ids:")
                    for i in result.introduced:
                        print(f"    - {i}")
            return 0 if result.ok else 1

        if args.patch_cmd == "apply":
            if not args.yes:
                print(
                    "Refusing to apply without --yes. "
                    "Run validate first, then: psa patch apply … --yes",
                    file=sys.stderr,
                )
                return 2
            result = validate_patch(fs, audit, patch)
            if not result.ok:
                print("Validation failed; apply aborted.", file=sys.stderr)
                for msg in result.failures:
                    print(f"  - {msg}", file=sys.stderr)
                return 1
            try:
                applied = apply_patch(
                    root,
                    audit,
                    patch,
                    validated=True,
                    validation=result,
                    branch=args.branch,
                )
            except (ValueError, OSError, subprocess.CalledProcessError) as exc:
                print(f"apply failed: {exc}", file=sys.stderr)
                return 1
            print("Patch Applied")
            print(f"  Branch:  {applied.branch}")
            print(f"  Commit:  {applied.commit}")
            print(f"  Path:    {applied.path}")
            print(f"  Message: {applied.message}")
            print(applied.rollback_instructions)
            return 0

        return 1

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"path not found: {root}", file=sys.stderr)
        return 2

    fs = LocalRepoFS(root)

    if args.cmd == "doctor":
        print(render_doctor(discover(fs, cfg), cfg), end="")
        return 0

    audit = analyze(fs, config=cfg)

    if args.cmd == "audit":
        if args.format == "json":
            out = dumps(audit.to_dict())
        else:
            out = render_audit(audit, repo_name=repo_display_name(root))
        if args.out:
            Path(args.out).write_text(out, encoding="utf-8")
        else:
            print(out, end="")
        return 0

    if args.cmd == "plan":
        if args.format == "json":
            graph = audit.dependency_graph
            out = dumps(
                {
                    "repository": repo_display_name(root),
                    "findings_considered": len(audit.findings),
                    "plan": [p.to_dict() for p in (graph.plan if graph else ())],
                }
            )
        else:
            out = render_plan(audit, repo_name=repo_display_name(root))
        if args.out:
            Path(args.out).write_text(out, encoding="utf-8")
        else:
            print(out, end="")
        return 0

    if args.cmd == "diff":
        baseline = load_baseline(args.baseline)
        d = diff_audits(current=audit, baseline=baseline)
        if args.format == "json":
            print(dumps(d.to_dict()), end="")
        else:
            print("Audit Diff")
            print(f"  Resolved:   {len(d.resolved)}")
            for i in d.resolved:
                print(f"    - {i}")
            print(f"  Introduced: {len(d.introduced)}")
            for i in d.introduced:
                print(f"    - {i}")
            print(f"  Unchanged:  {len(d.unchanged)}")
            if d.reprioritised:
                print(f"  Reprioritised: {len(d.reprioritised)}")
                for fid, old, new in d.reprioritised:
                    print(f"    - {fid}: {old} -> {new}")
        if args.fail_on_introduced and d.introduced:
            return 1
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
