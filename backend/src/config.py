from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "productlens"
    debug: bool = False

    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model: str = "grok-4.6"
    # Image-relevance filter. Same snapshot as the non-reasoning variant, just
    # allowed to think: it has to keep 8 photos straight against their index,
    # and the non-reasoning one kept photos of obviously different products.
    xai_filter_model: str = "grok-4.20-0309-reasoning"


@lru_cache
def get_settings() -> Settings:
    return Settings()
