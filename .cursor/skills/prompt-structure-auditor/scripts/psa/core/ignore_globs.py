"""Default discovery ignore patterns (Release 1 trust fix)."""
from __future__ import annotations

from dataclasses import dataclass

# Paths relative to the audited repository root.
# Segment forms (tests/**, fixtures/**) match that directory at any depth
# so an installed skill's scripts/tests/fixtures are excluded.
DEFAULT_IGNORE_GLOBS: tuple[str, ...] = (
    ".cursor/skills/**/scripts/tests/**",
    ".cursor/skills/**/tests/**",
    "tests/**",
    "test/**",
    "fixtures/**",
    "__fixtures__/**",
)

DEFAULT_IGNORE_REASON = "Ignored (default exclusion)"


@dataclass(frozen=True)
class IgnoreMatch:
    path: str
    pattern: str
    display_root: str
    reason: str = DEFAULT_IGNORE_REASON


def match_ignore(path: str, patterns: tuple[str, ...]) -> IgnoreMatch | None:
    """Return the first matching ignore pattern for a normalized repo-relative path."""
    norm = path.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    for pattern in patterns:
        root = _match_root(norm, pattern)
        if root is not None:
            return IgnoreMatch(path=norm, pattern=pattern, display_root=root)
    return None


def collapse_ignored(matches: list[IgnoreMatch]) -> tuple[IgnoreMatch, ...]:
    """One entry per display_root (stable order by root, then pattern)."""
    best: dict[str, IgnoreMatch] = {}
    for m in matches:
        prev = best.get(m.display_root)
        if prev is None or len(m.pattern) < len(prev.pattern):
            best[m.display_root] = IgnoreMatch(
                path=m.display_root,
                pattern=m.pattern,
                display_root=m.display_root,
                reason=m.reason,
            )
    return tuple(sorted(best.values(), key=lambda m: (m.display_root, m.pattern)))


def _match_root(path: str, pattern: str) -> str | None:
    pat = pattern.replace("\\", "/")
    while pat.startswith("./"):
        pat = pat[2:]
    if pat.endswith("/**"):
        pat = pat[:-3]

    # Explicit skill-tree globs with ** in the middle
    if "**" in pat:
        return _match_glob_prefix(path, pat)

    # Directory-name patterns: tests/**, fixtures/**, etc.
    # Match path == name, path.startswith(name/), or /name/ as a segment.
    name = pat.rstrip("/")
    if not name or "/" in name:
        # non-** multi-segment without middle **: treat as prefix
        if path == name or path.startswith(name + "/"):
            return name if name.endswith("/") else name + "/"
        return None

    parts = path.split("/")
    for i, part in enumerate(parts):
        if part == name:
            return "/".join(parts[: i + 1]) + "/"
    return None


def _match_glob_prefix(path: str, pat: str) -> str | None:
    """Match patterns like '.cursor/skills/**/scripts/tests' against path."""
    parts = path.split("/")
    segs = pat.split("/")
    if not _glob_match_parts(parts, segs):
        return None
    # Display root: up through the last concrete segment before a trailing empty
    # Prefer the matched directory that ends at the last non-** segment.
    return _display_root_for_glob(path, segs)


def _glob_match_parts(parts: list[str], segs: list[str]) -> bool:
    """True if path parts match glob segments (only ** wildcards supported)."""

    def rec(pi: int, si: int) -> bool:
        if si == len(segs):
            return pi == len(parts)
        if segs[si] == "**":
            # ** may consume zero or more path parts; must leave room for rest
            if si == len(segs) - 1:
                return True
            for k in range(pi, len(parts) + 1):
                if rec(k, si + 1):
                    return True
            return False
        if pi >= len(parts):
            return False
        if segs[si] != parts[pi]:
            return False
        return rec(pi + 1, si + 1)

    # Pattern without trailing file: allow path to continue under matched dir
    # e.g. segs match a prefix of parts
    def rec_prefix(pi: int, si: int) -> bool:
        if si == len(segs):
            return pi <= len(parts)  # matched full pattern; path may continue
        if segs[si] == "**":
            if si == len(segs) - 1:
                return True
            for k in range(pi, len(parts) + 1):
                if rec_prefix(k, si + 1):
                    return True
            return False
        if pi >= len(parts):
            return False
        if segs[si] != parts[pi]:
            return False
        return rec_prefix(pi + 1, si + 1)

    return rec_prefix(0, 0)


def _display_root_for_glob(path: str, segs: list[str]) -> str:
    """Build a stable display directory for a matched glob."""
    # Walk matching to find end index of pattern against path
    parts = path.split("/")
    # Reconstruct: take path up to and including last literal segment matched
    literal_tail = None
    for s in reversed(segs):
        if s != "**":
            literal_tail = s
            break
    if literal_tail is None:
        return parts[0] + "/" if parts else path
    # Find first occurrence of the full concrete suffix after skills prefix
    # Prefer longest path prefix ending with literal_tail that is under the match
    for i, part in enumerate(parts):
        if part == literal_tail:
            return "/".join(parts[: i + 1]) + "/"
    return parts[0] + "/"
