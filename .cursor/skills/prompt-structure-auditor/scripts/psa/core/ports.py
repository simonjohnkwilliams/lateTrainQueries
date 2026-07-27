"""Read-only repository filesystem ports (ADR D11)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Protocol


class RepoFS(Protocol):
    def list_files(self) -> tuple[str, ...]: ...

    def read_text(self, path: str) -> str: ...

    def exists(self, path: str) -> bool: ...

    def root(self) -> str: ...


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


class MemoryRepoFS:
    def __init__(self, files: Mapping[str, str]) -> None:
        self._files = {_norm(k): v for k, v in files.items()}

    def list_files(self) -> tuple[str, ...]:
        return tuple(sorted(self._files))

    def read_text(self, path: str) -> str:
        return self._files[_norm(path)]

    def exists(self, path: str) -> bool:
        return _norm(path) in self._files

    def root(self) -> str:
        return "<memory>"


class LocalRepoFS:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def root(self) -> str:
        return str(self._root)

    def list_files(self) -> tuple[str, ...]:
        out: list[str] = []
        skip = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "target", "out"}
        for p in self._root.rglob("*"):
            if not p.is_file():
                continue
            rel_parts = p.relative_to(self._root).parts
            if any(part in skip for part in rel_parts):
                continue
            out.append(_norm(str(Path(*rel_parts))))
        return tuple(sorted(out))

    def read_text(self, path: str) -> str:
        return (self._root / _norm(path)).read_text(encoding="utf-8")

    def exists(self, path: str) -> bool:
        return (self._root / _norm(path)).is_file()
