"""Compact, generation-scoped element snapshots for agent use."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable


class SnapshotRefError(LookupError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass
class SnapshotIndex:
    generation: int = 0

    def __post_init__(self) -> None:
        self._refs: dict[str, str] = {}

    def build(self, url: str, title: str, elements: Iterable[dict[str, Any]]) -> dict[str, Any]:
        self.generation += 1
        self._refs = {}
        compact = []
        for raw in elements:
            if not raw.get("visible", True) or not raw.get("backend_id"):
                continue
            ref = f"e{len(compact) + 1}"
            self._refs[ref] = str(raw["backend_id"])
            item = {"ref": ref, "role": str(raw.get("role") or "generic"),
                    "name": str(raw.get("name") or ""), "visible": True}
            if raw.get("value") not in (None, ""):
                item["value"] = str(raw["value"])
            compact.append(item)
        return {"generation": self.generation, "url": url, "title": title, "elements": compact}

    def resolve(self, ref: str, generation: int) -> str:
        if generation != self.generation:
            raise SnapshotRefError("STALE_REF", f"stale element ref generation {generation}; current is {self.generation}")
        try:
            return self._refs[ref]
        except KeyError as exc:
            raise SnapshotRefError("REF_NOT_FOUND", f"element ref {ref!r} not found") from exc
