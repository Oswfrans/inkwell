"""Configuration management using TOML files and platformdirs."""

from __future__ import annotations

from pathlib import Path

import platformdirs
from pydantic import BaseModel, Field

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

APP_NAME = "inkwell"


def config_dir() -> Path:
    return Path(platformdirs.user_config_dir(APP_NAME))


def cache_dir() -> Path:
    return Path(platformdirs.user_cache_dir(APP_NAME))


def data_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME))


class DownloadConfig(BaseModel):
    output_dir: Path = Field(default_factory=lambda: Path.cwd())
    rate_limit: float = 1.0  # seconds between requests
    max_retries: int = 3
    timeout: float = 30.0
    user_agent: str = (
        "Mozilla/5.0 (compatible; Inkwell/0.1; +https://github.com/inkwell)"
    )


class EpubConfig(BaseModel):
    include_images: bool = True
    include_cover: bool = True
    chapter_style: str = "default"


class Config(BaseModel):
    download: DownloadConfig = Field(default_factory=DownloadConfig)
    epub: EpubConfig = Field(default_factory=EpubConfig)

    @classmethod
    def load(cls) -> Config:
        """Load config from TOML file, falling back to defaults."""
        config_path = config_dir() / "inkwell.toml"
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            return cls.model_validate(data)
        return cls()
