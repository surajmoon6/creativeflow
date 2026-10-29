"""Storage abstraction. Only LocalStorage exists today; an S3/R2 backend needs the same four methods."""
import shutil
from pathlib import Path


class LocalStorage:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def save(self, key: str, fileobj) -> int:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as out:
            shutil.copyfileobj(fileobj, out)
        return p.stat().st_size

    def save_bytes(self, key: str, data: bytes) -> int:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return len(data)

    def open(self, key: str):
        return open(self._path(key), "rb")

    def local_path(self, key: str) -> str:
        """For send_file. A cloud backend would return a short-lived presigned URL instead."""
        return str(self._path(key))

    def delete(self, key: str):
        self._path(key).unlink(missing_ok=True)


_storage = None


def get_storage():
    from flask import current_app
    global _storage
    root = current_app.config["STORAGE_DIR"]
    if _storage is None or str(_storage.root) != str(Path(root).resolve()):
        _storage = LocalStorage(root)
    return _storage
