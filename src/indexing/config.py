"""Connection and model settings for the indexing layer."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class IndexingSettings(BaseSettings):
    qdrant_url: str = ":memory:"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "financial_chunks"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")