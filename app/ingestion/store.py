"""Trusted document store.

The local profile uses a directory that behaves like an object bucket.
Keys are logical object names. Callers must not display filesystem paths.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.errors import StorageError


class TrustedDocumentStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or key.startswith(("/", "\\")) or ".." in key.split("/"):
            raise StorageError("The object key is not allowed.")
        path = (self.root / key).resolve()
        if self.root != path and self.root not in path.parents:
            raise StorageError("The object key escapes the store.")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise StorageError("The object was not found in the trusted store.")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()
