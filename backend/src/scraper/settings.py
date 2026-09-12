from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BACKEND_DIR / "data"
CACHE_DIR = DATA_DIR / "lab_cache"
RUNS_DIR = DATA_DIR / "lab_runs"


class LabSettings(BaseSettings):
    """Config for the scraping lab; shares the app .env, ignores unrelated keys."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    firecrawl_api_key: str = ""
    exa_api_key: str = ""
    firecrawl_base_url: str = "https://api.firecrawl.dev/v2"
    exa_base_url: str = "https://api.exa.ai"

    lab_http_timeout: float = 120.0
    lab_scrape_timeout_ms: int = 45000
    lab_scrape_concurrency: int = 4
    lab_search_concurrency: int = 6
    lab_retry_attempts: int = 3

    lab_cache_enabled: bool = True
    lab_cache_ttl_hours: int = 24
    lab_max_markdown_chars: int = 20000
    lab_max_images: int = 12
    lab_max_image_bytes: int = 8 * 1024 * 1024


@lru_cache
def get_lab_settings() -> LabSettings:
    return LabSettings()
