from __future__ import annotations

import unicodedata

from watcher.config import SearchConfig
from watcher.sources.olx import Offer


_DIACRITICS_MAP = str.maketrans(
    "ăâîșțĂÂÎȘȚ",
    "aaistaaist",
)


def _normalize(text: str) -> str:
    """Lowercase, strip diacritics (Romanian-specific + general)."""
    text = text.lower().translate(_DIACRITICS_MAP)
    # Also handle combining characters from other normalization forms
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


def apply_filters(offers: list[Offer], config: SearchConfig) -> list[Offer]:
    """Filter offers based on search config rules."""
    result: list[Offer] = []

    for offer in offers:
        # Price filter
        if config.max_price is not None and offer.price is not None:
            if offer.price > config.max_price:
                continue

        title_norm = _normalize(offer.title)

        # Include keywords: at least one must match (if list is non-empty)
        if config.include_keywords:
            keywords_norm = [_normalize(kw) for kw in config.include_keywords]
            if not any(kw in title_norm for kw in keywords_norm):
                continue

        # Exclude keywords: none must match
        if config.exclude_keywords:
            keywords_norm = [_normalize(kw) for kw in config.exclude_keywords]
            if any(kw in title_norm for kw in keywords_norm):
                continue

        result.append(offer)

    return result
