import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # --- Open WebUI connection (from environment / .env) ---
    url: str = os.environ.get("OPENWEBUI_URL", "https://gepeto.bsc.es/").rstrip("/")
    api_key: str = os.environ.get("OPENWEBUI_API_KEY", "sk-d0cd19326c6b49cbb5741890446abbb4")
    model: str = os.environ.get("OPENWEBUI_MODEL", "Qwen3.8-27B")

    # --- paths (relative to where you run the command) ---
    raw_dir: Path = Path("data/raw/01_assessments/ipcc_ar6_wg1")
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