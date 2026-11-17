"""Synthetic accounts, source records and PDF for the isolated study browser stack."""

import asyncio

from bank_fixtures import synthetic_pdf
from seed import main as seed_accounts

from app.core.config import get_settings


async def main():
    # Includes the app-env/database-name guards; never imports pilot records.
    await seed_accounts(synthetic_bank=True)
    settings = get_settings()
    root = settings.knowledge_data_root.resolve()
    assert root.is_relative_to(settings.file_storage_path.resolve())
    path = root / "raw-source/DVC.005844.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(synthetic_pdf())
    print("Isolated study fixtures ready")


if __name__ == "__main__":
    asyncio.run(main())
