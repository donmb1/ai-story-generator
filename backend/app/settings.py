"""Konfiguration ausschließlich über Umgebungsvariablen (siehe backend/.env.example)."""

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # claude_cli | anthropic | openai | fake
    provider: str = os.environ.get("STORY_PROVIDER", "claude_cli").lower()
    anthropic_model: str = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
    # low | medium | high – niedriger = schneller, Kinder warten ungern
    anthropic_effort: str = os.environ.get("ANTHROPIC_EFFORT", "medium")
    openai_model: str = os.environ.get("OPENAI_MODEL", "gpt-5")
    # Claude Code CLI (Anmeldung über CLAUDE_CODE_OAUTH_TOKEN aus `claude setup-token`, kein API-Key)
    claude_bin: str = os.environ.get("CLAUDE_BIN", "claude")

    # Statischer Geräte-Token, den der Kindle mitschickt
    device_token: str = os.environ.get("DEVICE_TOKEN", "")

    llm_timeout_s: int = _int("LLM_TIMEOUT_S", 150)
    llm_max_retries: int = _int("LLM_MAX_RETRIES", 2)

    # Rate-Limits pro Gerät
    stories_per_hour: int = _int("STORIES_PER_HOUR", 12)
    requests_per_minute: int = _int("REQUESTS_PER_MINUTE", 240)

    data_dir: Path = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
    keep_stories: int = _int("KEEP_STORIES", 50)

    # Displaygröße Kindle Paperwhite 3 (Hochformat)
    screen_w: int = _int("SCREEN_W", 1072)
    screen_h: int = _int("SCREEN_H", 1448)


settings = Settings()
