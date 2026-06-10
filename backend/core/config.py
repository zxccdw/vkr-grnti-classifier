from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_v1_prefix: str = "/api/v1"
    app_title: str = "GRNTI Web Classifier"
    app_version: str = "0.1.0"
    cors_origins: list[str] = ["*"]

    data_dir: Path = Path("data")
    ontology_path: Path = data_dir / "ontology_grnti.json"
    ontology_snapshots_dir: Path = data_dir / "snapshots"

    embeddings_url: str = "http://embeddings:80"
    embeddings_normalize: bool = True
    embeddings_timeout: float = 30.0

    openai_embeddings_base_url: str = ""
    openai_embeddings_token: str = ""
    openai_embeddings_model: str = "openai/text-embedding-3-small"
    openai_embeddings_verify_ssl: bool = True

    default_top_k: int = 12
    beam_width: int = 5

    llm_temperature: float = 0.3
    llm_max_tokens: int = 512
    llm_timeout: float = 60.0
    mock_llm: bool = False

    s3_bucket: str = ""
    s3_key: str = "ontology_grnti.json"
    s3_embeddings_key: str = "embeddings_cache.pkl.gz"
    s3_endpoint_url: str = "https://storage.yandexcloud.net"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    gigachat_base_url: str = ""
    gigachat_token: str = ""
    gigachat_credentials: str = ""
    gigachat_model: str = "GigaChat-Pro"
    gigachat_verify_ssl: bool = True

    yagpt_base_url: str = ""
    yagpt_token: str = ""
    yagpt_model: str = "yandexgpt"

    auth_username: str = "admin"
    auth_password: str = ""
    auth_realm: str = "GRNTI Web"


@lru_cache
def get_settings() -> Settings:
    return Settings()
