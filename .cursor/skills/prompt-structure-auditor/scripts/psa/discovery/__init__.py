"""Discovery: source adapters (RFC §5)."""
from __future__ import annotations

from dataclasses import dataclass

from psa.core.config import DEFAULT_CONFIG, ConfigView
from psa.core.ports import RepoFS
from psa.core.ignore_globs import IgnoreMatch, collapse_ignored, match_ignore
from psa.discovery.documentation import collect_guidance

ADAPTER_REASONS: dict[str, str] = {
    "claude": "Claude instruction source",
    "agents": "Agent instructions",
    "cursor_rules": "Cursor rule",
    "copilot": "Copilot instructions",
    "serena": "Tool config (Serena)",
    "opencode": "Tool config (OpenCode)",
    "claude_settings": "Tool config (Claude settings)",
    "research_data": "Data (not instruction)",
}


@dataclass(frozen=True)
class Source:
    source_id: str
    adapter: str
    subtype: str  # instruction | config | data
    path: str
    text: str
    default_ownership: str
    order_hint: int
    reason: str = ""

    def inclusion_reason(self) -> str:
        return self.reason or ADAPTER_REASONS.get(self.adapter, f"Discovered ({self.adapter})")


@dataclass(frozen=True)
class DiscoverResult:
    sources: tuple[Source, ...]
    ignored: tuple[IgnoreMatch, ...]
    guidance: tuple[str, ...] = ()

    @property
    def documentation(self) -> tuple[str, ...]:
        """Legacy alias for guidance (Guidance Surface)."""
        return self.guidance

    def __iter__(self):
        return iter(self.sources)

    def __len__(self) -> int:
        return len(self.sources)


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def discover(repo: RepoFS, config: ConfigView | None = None) -> DiscoverResult:
    cfg = config or DEFAULT_CONFIG
    patterns = cfg.effective_ignore_globs()
    files = [_norm(p) for p in repo.list_files()]
    found: list[Source] = []
    ignored_raw: list[IgnoreMatch] = []
    order = 0

    def add(adapter: str, subtype: str, path: str, ownership: str, text: str = "") -> None:
        nonlocal order
        found.append(
            Source(
                source_id=f"{adapter}:{path}",
                adapter=adapter,
                subtype=subtype,
                path=path,
                text=text,
                default_ownership=ownership,
                order_hint=order,
                reason=ADAPTER_REASONS.get(adapter, f"Discovered ({adapter})"),
            )
        )
        order += 1

    for path in files:
        hit = match_ignore(path, patterns) if patterns else None
        if hit is not None:
            ignored_raw.append(hit)
            continue

        name = path.rsplit("/", 1)[-1]

        if name.upper() in {"CLAUDE.MD", "CLAUDE.LOCAL.MD"} or name == "CLAUDE.md":
            add("claude", "instruction", path, "user", repo.read_text(path))
            continue
        if name == "CLAUDE.local.md":
            add("claude", "instruction", path, "user", repo.read_text(path))
            continue
        if name == "AGENTS.md":
            add("agents", "instruction", path, "user", repo.read_text(path))
            continue
        if "/.cursor/rules/" in f"/{path}" or path.startswith(".cursor/rules/"):
            if path.endswith((".mdc", ".md")):
                add("cursor_rules", "instruction", path, "user", repo.read_text(path))
                continue
            add("cursor_rules", "config", path, "unknown", "")
            continue
        if path.endswith("copilot-instructions.md"):
            add("copilot", "instruction", path, "user", repo.read_text(path))
            continue
        if path.startswith(".serena/") or "/.serena/" in path:
            if path.endswith((".yml", ".yaml")):
                add("serena", "config", path, "tool", "")
            continue
        if path.startswith(".opencode/") or "/.opencode/" in path:
            if path.endswith((".json", ".yaml", ".yml")) and "package-lock" not in path:
                add("opencode", "config", path, "tool", "")
            continue
        if path.startswith(".claude/skills/") or "/.claude/skills/" in path:
            continue
        if path.startswith(".claude/") and path.endswith(".json"):
            add("claude_settings", "config", path, "tool", "")
            continue
        if path.startswith(".agents/") or "/.agents/" in path:
            continue
        if "/research/" in f"/{path}" and path.endswith((".json", ".log")):
            add("research_data", "data", path, "unknown", "")
            continue
        if "claude-stdout.json" in name or "claude_dot_json" in name:
            add("research_data", "data", path, "unknown", "")
            continue

    sources = tuple(sorted(found, key=lambda s: (s.order_hint, s.path)))
    ignored = collapse_ignored(ignored_raw)
    ignored_file_paths = {m.path for m in ignored_raw}
    instruction_paths = {s.path for s in sources if s.subtype == "instruction"}
    guidance = collect_guidance(
        files,
        instruction_paths=instruction_paths,
        ignored_paths=ignored_file_paths,
    )
    return DiscoverResult(
        sources=sources,
        ignored=ignored,
        guidance=guidance,
    )


def render_discover(result: DiscoverResult) -> str:
    """Deprecated alias — prefer psa.report.doctor.render_doctor."""
    from psa.report.doctor import render_doctor

    return render_doctor(result)
