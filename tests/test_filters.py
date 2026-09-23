"""Tests for offer filtering, including diacritics handling."""

from watcher.config import SearchConfig
from watcher.filters import apply_filters, _normalize
from watcher.sources.olx import Offer


def _make_offer(**kwargs) -> Offer:
    defaults = {
        "id": "1",
        "title": "Apartament 2 camere",
        "price": 300.0,
        "currency": "EUR",
        "location": "Cluj-Napoca",
        "created_at": "2026-09-01T10:00:00+03:00",
        "url": "https://www.olx.ro/oferta/test-IDabc.html",
        "image_url": None,
        "is_promoted": False,
    }
    defaults.update(kwargs)
    return Offer(**defaults)


def _make_config(**kwargs) -> SearchConfig:
    defaults = {
        "name": "test",
        "url": "https://www.olx.ro/imobiliare/",
        "max_price": None,
        "include_keywords": [],
        "exclude_keywords": [],
    }
    defaults.update(kwargs)
    return SearchConfig(**defaults)


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("ABC") == "abc"

    def test_romanian_diacritics(self):
        assert _normalize("ăâîșț") == "aaist"
        assert _normalize("ĂÂÎȘȚ") == "aaist"

    def test_mixed_text(self):
        assert _normalize("Închiriez Apartament") == "inchiriez apartament"

    def test_garsoniera_with_diacritics(self):
        norm = _normalize("Garsonieră în centru")
        assert "garsoniera" in norm
        assert "in" in norm


class TestMaxPrice:
    def test_filters_above_max(self):
        offers = [
            _make_offer(id="1", price=400),
            _make_offer(id="2", price=600),
            _make_offer(id="3", price=500),
        ]
        config = _make_config(max_price=500)
        result = apply_filters(offers, config)
        assert len(result) == 2
        assert {o.id for o in result} == {"1", "3"}

    def test_no_max_price_passes_all(self):
        offers = [_make_offer(price=10000)]
        config = _make_config(max_price=None)
        assert len(apply_filters(offers, config)) == 1

    def test_none_price_passes(self):
        offers = [_make_offer(price=None)]
        config = _make_config(max_price=500)
        assert len(apply_filters(offers, config)) == 1


class TestIncludeKeywords:
    def test_matches_keyword(self):
        offers = [
            _make_offer(id="1", title="Apartament 2 camere Untold"),
            _make_offer(id="2", title="Garsonieră centru"),
        ]
        config = _make_config(include_keywords=["untold"])
        result = apply_filters(offers, config)
        assert len(result) == 1
        assert result[0].id == "1"

    def test_case_insensitive(self):
        offers = [_make_offer(title="UNTOLD festival")]
        config = _make_config(include_keywords=["untold"])
        assert len(apply_filters(offers, config)) == 1

    def test_diacritics_insensitive(self):
        offers = [_make_offer(title="Garsonieră în centru")]
        config = _make_config(include_keywords=["garsoniera"])
        assert len(apply_filters(offers, config)) == 1

    def test_empty_include_passes_all(self):
        offers = [_make_offer()]
        config = _make_config(include_keywords=[])
        assert len(apply_filters(offers, config)) == 1

    def test_any_keyword_matches(self):
        offers = [_make_offer(title="Studio modern")]
        config = _make_config(include_keywords=["apartament", "studio"])
        assert len(apply_filters(offers, config)) == 1


class TestExcludeKeywords:
    def test_excludes_matching(self):
        offers = [
            _make_offer(id="1", title="Apartament 2 camere"),
            _make_offer(id="2", title="Cumpar apartament urgent"),
        ]
        config = _make_config(exclude_keywords=["cumpar"])
        result = apply_filters(offers, config)
        assert len(result) == 1
        assert result[0].id == "1"

    def test_diacritics_in_exclude(self):
        offers = [_make_offer(title="Caut garsonieră")]
        config = _make_config(exclude_keywords=["caut"])
        assert len(apply_filters(offers, config)) == 0

    def test_exclude_with_diacritics_in_keyword(self):
        offers = [_make_offer(title="Cumpăr apartament")]
        config = _make_config(exclude_keywords=["cumpar"])
        assert len(apply_filters(offers, config)) == 0


class TestCombinedFilters:
    def test_price_and_keywords(self):
        offers = [
            _make_offer(id="1", title="Apartament Untold", price=400),
            _make_offer(id="2", title="Apartament Untold", price=600),
            _make_offer(id="3", title="Cumpar apartament", price=300),
        ]
        config = _make_config(
            max_price=500,
            include_keywords=[],
            exclude_keywords=["cumpar"],
        )
        result = apply_filters(offers, config)
        assert len(result) == 1
        assert result[0].id == "1"
