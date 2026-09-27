"""Runtime settings, read once from the environment (.env is loaded if present)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    hindsight_url: str = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")
    hindsight_api_key: str | None = os.getenv("HINDSIGHT_API_KEY") or None
    bank_id: str = os.getenv("HINDSIGHT_BANK_ID", "paylane-oncall")
    groq_api_key: str | None = os.getenv("GROQ_API_KEY") or None
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    groq_fallback_model: str = os.getenv("GROQ_FALLBACK_MODEL", "qwen/qwen3-32b")

    def missing(self) -> list[str]:
        """Names of required settings that are not configured."""
        out = []
        if not self.groq_api_key:
            out.append("GROQ_API_KEY")
        if "vectorize.io" in self.hindsight_url and not self.hindsight_api_key:
            out.append("HINDSIGHT_API_KEY")
        return out


settings = Settings()
