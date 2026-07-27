"""Guidance Surface — non-runtime assets that shape assistant behaviour.

Product vocabulary (mutually exclusive buckets):

  Instruction Assets  — runtime prompt surfaces (CLAUDE.md, AGENTS.md, rules, …)
  Guidance Surface    — docs intended to shape assistant behaviour (not executed)

Everything PSA discovers belongs in exactly one bucket. Nothing belongs in both.
Guidance is counted for honesty/context only — it never produces findings.
"""
from __future__ import annotations

import re

# "Is this document intended to shape assistant behaviour?"
_GUIDANCE_SIGNAL = re.compile(
    r"(prompt|agents?|claude|cursor|copilot|llm|"
    r"ai[-_ ]?(guid|workflow|coding|assistant|prompt)|"
    r"coding[-_ ]?standard|assistant|system[-_ ]?prompt|"
    r"prompt[-_ ]?engineer|llm[-_ ]?guid|ai[-_ ]?guid)",
    re.IGNORECASE,
)

_DOC_EXTS = (".md", ".mdx", ".rst", ".adoc", ".txt")

# Installed skills / tool packs are not project guidance.
_EXCLUDE_PREFIXES = (
    ".cursor/skills/",
    ".claude/skills/",
    ".claude/commands/",
    ".agents/",
    ".agents/skills/",
    "node_modules/",
    "vendor/",
)

_EXCLUDE_NAMES = frozenset(
    {
        "license",
        "license.md",
        "license.txt",
        "licence",
        "licence.md",
        "changelog",
        "changelog.md",
        "changelog.rst",
        "changes.md",
        "history.md",
        "news.md",
        "releases.md",
        "release-notes.md",
        "releasenotes.md",
        "contributing.md",
        "contribute.md",
        "code_of_conduct.md",
        "security.md",
        "authors.md",
        "readme",
        "readme.md",
        "readme.rst",
        "readme.txt",
        "todo.md",
        "roadmap.md",
        "skill.md",
    }
)

_EXCLUDE_PATH = re.compile(
    r"(^|/)("
    r"changelog|change[-_ ]?log|release[-_ ]?notes?|releases?|"
    r"api[-_ ]?(doc|docs|reference)|openapi|swagger|"
    r"contributing|code_of_conduct|license|licence|"
    r"research/"
    r")",
    re.IGNORECASE,
)

# Entire trees treated as Guidance Surface by placement intent.
_GUIDANCE_ROOTS = (
    "docs/ai/",
    "docs/prompts/",
    "docs/prompt/",
    "docs/assistant/",
    "docs/llm/",
    "ai-guidance/",
    "guidance/",
)


def is_guidance_path(path: str, *, instruction_paths: set[str]) -> bool:
    """True if path is Guidance Surface (never an Instruction Asset)."""
    norm = path.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    if norm in instruction_paths:
        return False
    lower = norm.lower()
    name = norm.rsplit("/", 1)[-1]
    name_lower = name.lower()
    if not any(lower.endswith(ext) for ext in _DOC_EXTS):
        return False
    if name_lower in _EXCLUDE_NAMES:
        return False
    if any(lower.startswith(p) or f"/{p}" in f"/{lower}" for p in _EXCLUDE_PREFIXES):
        return False
    if _EXCLUDE_PATH.search(lower):
        return False
    if any(seg in ("node_modules", ".git", "vendor") for seg in norm.split("/")):
        return False
    if any(lower.startswith(root) for root in _GUIDANCE_ROOTS):
        return True
    under_docs = any(
        lower == d or lower.startswith(d)
        for d in ("docs/", "documentation/", "doc/")
    )
    if _GUIDANCE_SIGNAL.search(name):
        return True
    if under_docs and _GUIDANCE_SIGNAL.search(norm):
        return True
    return False


# Back-compat alias for older tests/imports.
def is_documentation_path(path: str, *, instruction_paths: set[str]) -> bool:
    return is_guidance_path(path, instruction_paths=instruction_paths)


def collect_guidance(
    files: list[str],
    *,
    instruction_paths: set[str],
    ignored_paths: set[str] | None = None,
) -> tuple[str, ...]:
    ignored = ignored_paths or set()
    found: list[str] = []
    for path in files:
        norm = path.replace("\\", "/")
        while norm.startswith("./"):
            norm = norm[2:]
        if norm in ignored:
            continue
        if is_guidance_path(norm, instruction_paths=instruction_paths):
            found.append(norm)
    return tuple(sorted(set(found)))


def collect_documentation(
    files: list[str],
    *,
    instruction_paths: set[str],
    ignored_paths: set[str] | None = None,
) -> tuple[str, ...]:
    return collect_guidance(
        files,
        instruction_paths=instruction_paths,
        ignored_paths=ignored_paths,
    )
