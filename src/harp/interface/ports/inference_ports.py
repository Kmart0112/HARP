from __future__ import annotations

from typing import Any, Protocol


class ModelLoaderPort(Protocol):
    def load_model_payload(
        self,
        path: str,
    ) -> dict[str, Any]:
        ...
