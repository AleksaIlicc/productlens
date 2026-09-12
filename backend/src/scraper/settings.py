from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BACKEND_DIR / "data"
CACHE_DIR = DATA_DIR / "scraper_cache"
RUNS_DIR = DATA_DIR / "scraper_runs"


class ScraperSettings(BaseSettings):
    """Config for the scraper; shares the app .env, ignores unrelated keys."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    firecrawl_api_key: str = ""
    exa_api_key: str = ""
    firecrawl_base_url: str = "https://api.firecrawl.dev/v2"
    exa_base_url: str = "https://api.exa.ai"

    http_timeout: float = 120.0
    scrape_timeout_ms: int = 45000
    scrape_concurrency: int = 4
    search_concurrency: int = 6
    retry_attempts: int = 3

    cache_enabled: bool = True
    cache_ttl_hours: int = 24
    max_markdown_chars: int = 20000
    max_images: int = 12
    max_image_bytes: int = 8 * 1024 * 1024


@lru_cache
def get_scraper_settings() -> ScraperSettings:
    return ScraperSettings()
