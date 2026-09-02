from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TableParquetExportArtifact:
    output_path: str
    row_count: int
    file_size_bytes: int
    compression: str


class TableParquetExportPort(Protocol):
    def export_table(
        self,
        *,
        source_table: str,
        output_path: str,
        where: dict[str, object] | None = None,
        compression: str = "snappy",
    ) -> TableParquetExportArtifact:
        ...
