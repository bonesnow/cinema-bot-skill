from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import ResourceResult


class ResourceProvider(ABC):
    name = "base"

    @abstractmethod
    async def search(self, query: str) -> list[ResourceResult]:
        raise NotImplementedError
