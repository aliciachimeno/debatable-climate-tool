import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # --- Open WebUI connection (from environment / .env) ---
    url: str = os.environ.get("OPENWEBUI_URL", "http://localhost:3000").rstrip("/")
    api_key: str = os.environ.get("OPENWEBUI_API_KEY", "")
    model: str = os.environ.get("OPENWEBUI_MODEL", "")

    # --- paths (relative to where you run the command) ---
    raw_dir: Path = Path("data/raw")
    index_dir: Path = Path("data/index")
    runs_dir: Path = Path("runs")

    # --- index-time: changing these requires `claims index --rebuild` ---
    emb_model: str = "BAAI/bge-small-en-v1.5"
    min_words: int = 8          # shorter sentences are stored for context but not embedded

    # --- query-time: free to change, no rebuild ---
    context: int = 7            # sentences kept before AND after each hit
    top_k: int = 6             # sentence hits per query

    llm_timeout: int = int(os.environ.get("LLM_TIMEOUT", "600"))   # seconds


settings = Settings()