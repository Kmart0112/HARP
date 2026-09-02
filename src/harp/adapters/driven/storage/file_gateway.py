from __future__ import annotations

import shutil
from pathlib import Path


class LocalFileGatewayAdapter:
    def list_dirs(self, path: str) -> list[str]:
        base = Path(path)
        if not base.exists():
            return []
        dirs = [str(candidate) for candidate in base.rglob("*") if candidate.is_dir()]
        return sorted(dirs)

    def list_files(self, path: str) -> list[str]:
        base = Path(path)
        if not base.exists():
            return []
        files = [str(candidate) for candidate in base.rglob("*") if candidate.is_file()]
        return sorted(files)

    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def read_bytes(self, path: str) -> bytes:
        return Path(path).read_bytes()

    def write_text(self, path: str, content: str) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")

    def write_bytes(self, path: str, content: bytes) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)

    def copy(self, src: str, dst: str) -> None:
        src_path = Path(src)
        dst_path = Path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)

    def make_dir(self, path: str) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)

    def exists(self, path: str) -> bool:
        return Path(path).exists()
