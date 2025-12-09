import os
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

# Global limits and defaults
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_ROWS = 100_000  # hard limit on rows to read or generate
FAST_SAMPLE_ROWS = 5_000  # rows to sample in fast mode
DEFAULT_PARSE_MODE = "fast"

# Environment-driven config
PORT = int(os.getenv("PORT", "58008"))
CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]


class ParseMode(str, Enum):
    FAST = "fast"
    STRICT = "strict"
