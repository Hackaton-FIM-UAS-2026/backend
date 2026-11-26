import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _lista(nombre: str, defecto: str = "") -> list[str]:
    return [x.strip() for x in os.getenv(nombre, defecto).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    supabase_url: str = field(default_factory=lambda: os.environ["SUPABASE_URL"].rstrip("/"))
    supabase_anon_key: str = field(default_factory=lambda: os.environ["SUPABASE_ANON_KEY"])
    supabase_service_role_key: str = field(default_factory=lambda: os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    # Llave Fernet para el expediente sensible. Generar con:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    sensible_key: str = field(default_factory=lambda: os.environ["SENSIBLE_KEY"])

    anthropic_api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    claude_model: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-haiku-5-5"))
    llm_timeout_s: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_S", "6")))

    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "gemini-embedding-001"))
    embedding_dim: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "768")))

    cors_origins: list[str] = field(default_factory=lambda: _lista(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"))


@lru_cache
def settings() -> Settings:
    return Settings()
