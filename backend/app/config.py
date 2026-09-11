from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    mongodb_uri: str = ""
    mongodb_db: str = "dgdf_rag"

    pinecone_api_key: str = ""
    pinecone_index_name: str = "dgdf-rag"
    pinecone_namespace: str = "default"

    neo4j_uri: str = ""
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=(_BACKEND_ENV, _ROOT_ENV, ".env"),
        extra="ignore"
    )


settings = Settings()