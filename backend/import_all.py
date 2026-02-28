"""Batch import all legacy CSV data from data/ directory."""

import asyncio
import sys
from pathlib import Path

# Add the backend directory to path
sys.path.insert(0, str(Path(__file__).parent))

from logger.config import DATA_DIR
from logger.database import init_db, async_session
from logger.services.import_service import preview_import, confirm_import


# Ordered from oldest to newest
SESSION_PAIRS = [
    ("2022_fall_study.csv", "2022_fall_text.csv"),
    ("2023_winter_study.csv", "2023_winter_text.csv"),
    ("2023_spring_study.csv", "2023_spring_text.csv"),
    ("2023_summer_study.csv", "2023_summer_text.csv"),
    ("2023_fall_study.csv", "2023_fall_text.csv"),
    ("2024_winter_study.csv", "2024_winter_text.csv"),
    ("2024_spring_study.csv", "2024_spring_text.csv"),
    ("2024_summer_study.csv", "2024_summer_text.csv"),
    ("2024_fall_study.csv", "2024_fall_text.csv"),
    ("2025_winter_study.csv", "2025_winter_text.csv"),
    ("2025_spring_study.csv", "2025_spring_text.csv"),
    ("2025_summer_study.csv", "2025_summer_text.csv"),
    ("2025_fall_study.csv", "2025_fall_text.csv"),
]


async def main():
    await init_db()

    total_sessions = 0
    total_records = 0
    total_observations = 0
    total_text = 0

    for study_file, text_file in SESSION_PAIRS:
        study_path = DATA_DIR / study_file
        text_path = DATA_DIR / text_file

        if not study_path.exists():
            print(f"  SKIP: {study_file} not found")
            continue

        study_content = study_path.read_bytes()
        text_content = text_path.read_bytes() if text_path.exists() else None

        print(f"Importing {study_file}...", end=" ")

        try:
            preview = await preview_import(
                study_content=study_content,
                study_filename=study_file,
                text_content=text_content,
                text_filename=text_file if text_content else None,
            )

            if preview["warnings"]:
                print(f"  Warnings: {preview['warnings']}")

            async with async_session() as db:
                result = await confirm_import(preview["preview_id"], db)

            total_sessions += 1
            total_records += result["daily_records_created"]
            total_observations += result["observations_created"]
            total_text += result["text_entries_created"]

            print(
                f"OK - {result['categories_created']} cats, "
                f"{result['daily_records_created']} days, "
                f"{result['observations_created']} obs, "
                f"{result['text_entries_created']} text"
            )
        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\n{'='*60}")
    print(f"Total sessions imported: {total_sessions}")
    print(f"Total daily records:     {total_records}")
    print(f"Total observations:      {total_observations}")
    print(f"Total text entries:      {total_text}")


if __name__ == "__main__":
    asyncio.run(main())
