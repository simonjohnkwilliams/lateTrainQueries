"""Doctor report — answers: why was (or wasn't) something analysed?"""
from __future__ import annotations

from psa.core.config import ConfigView
from psa.core.ignore_globs import DEFAULT_IGNORE_GLOBS
from psa.discovery import DiscoverResult


def render_doctor(result: DiscoverResult, config: ConfigView | None = None) -> str:
    """Verbose diagnostic output for `psa doctor`."""
    cfg = config
    instructions = [s for s in result.sources if s.subtype == "instruction"]
    configs = [s for s in result.sources if s.subtype == "config"]
    data = [s for s in result.sources if s.subtype == "data"]

    lines: list[str] = [
        "Doctor — discovery diagnostics",
        "",
        "Instruction Sources",
        f"  Count: {len(instructions)}",
    ]
    if instructions:
        for s in instructions:
            lines.append(f"  [x] {s.path}")
            lines.append(f"      Adapter: {s.adapter}")
            lines.append(f"      Reason: {s.inclusion_reason()}")
    else:
        lines.append("  (none)")

    lines.extend(["", "Configuration Sources", f"  Count: {len(configs)}"])
    if configs:
        for s in configs:
            lines.append(f"  [c] {s.path}")
            lines.append(f"      Adapter: {s.adapter}")
            lines.append(f"      Reason: {s.inclusion_reason()}")
    else:
        lines.append("  (none)")

    lines.extend(["", "Out of Scope (data)", f"  Count: {len(data)}"])
    if data:
        for s in data:
            lines.append(f"  [-] {s.path}")
            lines.append(f"      Reason: {s.inclusion_reason()}")
    else:
        lines.append("  (none)")

    docs = list(result.guidance)
    lines.extend(["", "Guidance Surface (non-runtime)", f"  Count: {len(docs)}"])
    if docs:
        for path in docs:
            lines.append(f"  [g] {path}")
            lines.append(
                "      Reason: Intended to shape assistant behaviour (not a runtime instruction)"
            )
    else:
        lines.append("  (none)")

    lines.extend(["", "Ignored", f"  Count: {len(result.ignored)}"])
    if result.ignored:
        for m in result.ignored:
            lines.append(f"  [!] {m.display_root}")
            lines.append(f"      Reason: {m.reason}")
            lines.append(f"      Pattern matched: {m.pattern}")
    else:
        lines.append("  (none)")

    lines.extend(["", "Ignore Patterns"])
    if cfg is None:
        patterns = DEFAULT_IGNORE_GLOBS
        apply_defaults = True
    else:
        patterns = cfg.effective_ignore_globs()
        apply_defaults = cfg.apply_default_ignores
    lines.append(f"  Default ignores active: {'yes' if apply_defaults else 'no'}")
    if patterns:
        for p in patterns:
            lines.append(f"  - {p}")
    else:
        lines.append("  (none — all matching prompt paths are eligible)")

    lines.extend(
        [
            "",
            "Adapters Not Found",
        ]
    )
    expected = (
        ("claude", "CLAUDE.md"),
        ("agents", "AGENTS.md"),
        ("cursor_rules", "Cursor rules"),
        ("copilot", "Copilot instructions"),
    )
    present = {s.adapter for s in instructions}
    missing = [(a, label) for a, label in expected if a not in present]
    if missing:
        for _a, label in missing:
            lines.append(f"  [ ] {label}")
    else:
        lines.append("  (all common instruction adapters present)")

    lines.extend(
        [
            "",
            "Parser Failures",
            "  (none tracked — sources that fail to read are omitted from discovery)",
            "",
            "Unsupported / Unclassified Files",
            "  (not enumerated — only known prompt adapters are classified)",
            "",
            "Configuration",
            f"  apply_default_ignores: {apply_defaults}",
            f"  effective_ignore_globs: {len(patterns)}",
            "",
            "Override: pass --no-default-ignores to include ignored paths.",
            "",
        ]
    )
    return "\n".join(lines)
