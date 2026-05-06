from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    api_v1_prefix: str = "/api/v1"
    app_title: str = "GRNTI Web Classifier"
    app_version: str = "0.1.0"
    cors_origins: list[str] = ["*"]

    data_dir: Path = Path("data")
    ontology_path: Path = data_dir / "ontology_grnti.json"

    embeddings_url: str = "http://embeddings:80"
    embeddings_normalize: bool = True
    embeddings_timeout: float = 30.0

    default_top_k: int = 5
    beam_width: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
