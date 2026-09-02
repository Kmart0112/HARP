from __future__ import annotations

from typing import Protocol


class FileGatewayPort(Protocol):
    def list_dirs(self, path: str) -> list[str]:
        ...

    def list_files(self, path: str) -> list[str]:
        ...

    def read_text(self, path: str) -> str:
        ...

    def read_bytes(self, path: str) -> bytes:
        ...

    def write_text(self, path: str, content: str) -> None:
        ...

    def write_bytes(self, path: str, content: bytes) -> None:
        ...

    def copy(self, src: str, dst: str) -> None:
        ...

    def make_dir(self, path: str) -> None:
        ...

    def exists(self, path: str) -> bool:
        ...
