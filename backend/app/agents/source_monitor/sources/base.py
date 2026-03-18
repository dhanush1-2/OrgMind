"""Abstract base class for all source connectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.core.logger import get_logger
from app.models.documents import RawDocument, SourceType


class BaseSource(ABC):
    source_type: SourceType

    def __init__(self) -> None:
        self.log = get_logger(f"source.{self.source_type.value}")

    @abstractmethod
    async def fetch_since(self, since: datetime) -> list[RawDocument]:
        """
        Fetch all new documents created/updated after `since`.
        Returns a (possibly empty) list of RawDocument.
        """
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the required credentials are present."""
        ...
