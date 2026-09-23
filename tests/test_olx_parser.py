"""Tests for OLX offer parsing using a real API response fixture."""

import json
from pathlib import Path

from watcher.sources.olx import (
    Offer,
    _extract_api_params,
    _parse_api_response,
    _build_api_url,
    _parse_search_url_filters,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture() -> dict:
    with open(FIXTURES / "api_response.json", encoding="utf-8") as f:
        return json.load(f)


class TestParseApiResponse:
    def test_returns_offers(self):
        data = load_fixture()
        offers = _parse_api_response(data)
        assert len(offers) > 0
        assert all(isinstance(o, Offer) for o in offers)

    def test_offer_has_required_fields(self):
        data = load_fixture()
        offers = _parse_api_response(data)
        offer = offers[0]
        assert offer.id
        assert offer.title
        assert offer.url.startswith("https://")
        assert offer.created_at
        assert isinstance(offer.is_promoted, bool)

    def test_offer_id_is_string(self):
        data = load_fixture()
        offers = _parse_api_response(data)
        for offer in offers:
            assert isinstance(offer.id, str)

    def test_price_extraction(self):
        data = load_fixture()
        offers = _parse_api_response(data)
        # At least some offers should have prices
        priced = [o for o in offers if o.price is not None]
        assert len(priced) > 0
        for o in priced:
            assert isinstance(o.price, (int, float))
            assert o.currency in ("RON", "EUR", "USD", "")

    def test_location_extraction(self):
        data = load_fixture()
        offers = _parse_api_response(data)
        located = [o for o in offers if o.location]
        assert len(located) > 0

    def test_photo_url_formatted(self):
        data = load_fixture()
        offers = _parse_api_response(data)
        with_photos = [o for o in offers if o.image_url]
        assert len(with_photos) > 0
        for o in with_photos:
            assert "{width}" not in o.image_url
            assert "800x600" in o.image_url

    def test_no_duplicate_ids(self):
        data = load_fixture()
        offers = _parse_api_response(data)
        ids = [o.id for o in offers]
        assert len(ids) == len(set(ids))

    def test_empty_data(self):
        offers = _parse_api_response({"data": []})
        assert offers == []

    def test_missing_data_key(self):
        offers = _parse_api_response({})
        assert offers == []


class TestExtractApiParams:
    def test_extracts_from_friendly_links(self):
        html = (
            'blah "friendlyLinks":{"data":{"category_id":909,'
            '"region_id":2,"city_id":52953}} blah'
        )
        params = _extract_api_params(html)
        assert params == {
            "category_id": "909",
            "region_id": "2",
            "city_id": "52953",
        }

    def test_extracts_from_escaped_friendly_links(self):
        html = (
            'blah \\"friendlyLinks\\":{\\"data\\":'
            '{\\"category_id\\":909,\\"region_id\\":2,'
            '\\"city_id\\":52953}} blah'
        )
        params = _extract_api_params(html)
        assert params == {
            "category_id": "909",
            "region_id": "2",
            "city_id": "52953",
        }

    def test_returns_none_for_no_match(self):
        assert _extract_api_params("no data here") is None

    def test_extracts_from_real_snippet(self):
        snippet_file = FIXTURES / "page_snippet.txt"
        if snippet_file.exists():
            html = snippet_file.read_text(encoding="utf-8")
            params = _extract_api_params(html)
            if params:
                assert "category_id" in params
                assert "region_id" in params


class TestBuildApiUrl:
    def test_basic_url(self):
        url = _build_api_url(
            {"category_id": "909", "region_id": "2", "city_id": "52953"},
            {},
        )
        assert "category_id=909" in url
        assert "region_id=2" in url
        assert "city_id=52953" in url
        assert "sort_by=created_at%3Adesc" in url
        assert "limit=40" in url

    def test_with_url_filters(self):
        url = _build_api_url(
            {"category_id": "909"},
            {"filter_float_price:to": "500"},
        )
        assert "filter_float_price" in url


class TestParseSearchUrlFilters:
    def test_empty_url(self):
        filters = _parse_search_url_filters(
            "https://www.olx.ro/imobiliare/apartamente/"
        )
        assert filters == {}

    def test_order_filter(self):
        filters = _parse_search_url_filters(
            "https://www.olx.ro/imobiliare/?search[order]=created_at:desc"
        )
        assert filters["sort_by"] == "created_at:desc"

    def test_price_filter(self):
        filters = _parse_search_url_filters(
            "https://www.olx.ro/imobiliare/"
            "?search[filter_float_price:from]=100"
            "&search[filter_float_price:to]=500"
        )
        assert filters["filter_float_price:from"] == "100"
        assert filters["filter_float_price:to"] == "500"
