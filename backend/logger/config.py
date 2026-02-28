from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "logger.db"
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
CORS_ORIGINS = ["http://localhost:5173"]
