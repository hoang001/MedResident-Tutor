import asyncio
from pathlib import Path


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _resolve(self, relative_path: str) -> Path:
        target = (self.root / relative_path).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("Storage path escapes configured root")
        return target

    async def save(self, relative_path: str, content: bytes) -> str:
        target = self._resolve(relative_path)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, content)
        return relative_path

    async def delete(self, relative_path: str) -> None:
        target = self._resolve(relative_path)
        if await asyncio.to_thread(target.exists):
            await asyncio.to_thread(target.unlink)

    async def exists(self, relative_path: str) -> bool:
        return await asyncio.to_thread(self._resolve(relative_path).exists)
