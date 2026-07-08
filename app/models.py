from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ResourceResult:
    title: str
    share_url: str
    source: str = "authorized"
    quality: str = ""
    size: str = ""
    provider: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def searchable_text(self) -> str:
        return " ".join(
            value for value in (self.title, self.quality, self.size) if value
        ).lower()
