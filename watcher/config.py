from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SearchConfig:
    name: str
    url: str
    max_price: float | None = None
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    searches: list[SearchConfig]
    telegram_bot_token: str
    telegram_chat_id: str
    dry_run: bool = False

    @classmethod
    def load(cls, config_path: str = "config.yaml", dry_run: bool = False) -> AppConfig:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw or "searches" not in raw:
            raise ValueError("Config must contain 'searches' key")

        searches = []
        for s in raw["searches"]:
            if "name" not in s or "url" not in s:
                raise ValueError("Each search must have 'name' and 'url'")
            if not s["url"].startswith("https://www.olx.ro/"):
                raise ValueError(f"URL must be an OLX.ro search URL: {s['url']}")
            searches.append(SearchConfig(
                name=s["name"],
                url=s["url"],
                max_price=s.get("max_price"),
                include_keywords=s.get("include_keywords", []),
                exclude_keywords=s.get("exclude_keywords", []),
            ))

        if not searches:
            raise ValueError("At least one search must be defined")

        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not dry_run and (not token or not chat_id):
            raise ValueError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set "
                "(or use --dry-run)"
            )

        return cls(
            searches=searches,
            telegram_bot_token=token,
            telegram_chat_id=chat_id,
            dry_run=dry_run,
        )
