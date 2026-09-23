from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse, parse_qs

from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

API_BASE = "https://www.olx.ro/api/v1/offers/"
TIMEOUT = 20
MAX_RETRIES = 3


@dataclass
class Offer:
    id: str
    title: str
    price: float | None
    currency: str
    location: str
    created_at: str
    url: str
    image_url: str | None
    is_promoted: bool


def _get(url: str, headers: dict | None = None) -> curl_requests.Response:
    """GET with exponential backoff and Chrome TLS impersonation."""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)

    for attempt in range(MAX_RETRIES):
        try:
            resp = curl_requests.get(
                url,
                headers=hdrs,
                impersonate="chrome",
                timeout=TIMEOUT,
                allow_redirects=True,
            )
            resp.raise_for_status()
            return resp
        except Exception as exc:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0.5, 1.5)
            logger.warning("Retry %d for %s: %s (wait %.1fs)", attempt + 1, url, exc, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _extract_api_params(html: str) -> dict[str, str] | None:
    """Extract category_id, region_id, city_id from __PRERENDERED_STATE__.

    The embedded state is inside a JS string, so quotes may be
    escaped as \\" — we use \\\\?" to match both escaped and unescaped.
    """
    Q = r'\\?"'  # matches both " and \"

    # Look for friendlyLinks.data which has the resolved IDs
    m = re.search(
        Q + r'friendlyLinks' + Q + r'\s*:\s*\{\s*'
        + Q + r'data' + Q + r'\s*:\s*\{\s*'
        + Q + r'category_id' + Q + r'\s*:\s*(\d+)\s*,\s*'
        + Q + r'region_id' + Q + r'\s*:\s*(\d+)\s*,\s*'
        + Q + r'city_id' + Q + r'\s*:\s*(\d+)',
        html,
    )
    if m:
        return {
            "category_id": m.group(1),
            "region_id": m.group(2),
            "city_id": m.group(3),
        }

    # Fallback: look for the requestParams section
    m2 = re.search(
        Q + r'region_id' + Q + r'\s*:\s*(\d+)\s*,\s*'
        + Q + r'city_id' + Q + r'\s*:\s*(\d+)',
        html,
    )
    m3 = re.search(Q + r'categoryId' + Q + r'\s*:\s*(\d+)', html)
    if m2 and m3:
        return {
            "category_id": m3.group(1),
            "region_id": m2.group(1),
            "city_id": m2.group(2),
        }

    # Also try without city (some searches are region-wide)
    m4 = re.search(
        Q + r'friendlyLinks' + Q + r'\s*:\s*\{\s*'
        + Q + r'data' + Q + r'\s*:\s*\{\s*'
        + Q + r'category_id' + Q + r'\s*:\s*(\d+)\s*,\s*'
        + Q + r'region_id' + Q + r'\s*:\s*(\d+)',
        html,
    )
    if m4:
        return {
            "category_id": m4.group(1),
            "region_id": m4.group(2),
        }

    return None


def _parse_search_url_filters(url: str) -> dict[str, str]:
    """Extract any query string filters from the user's search URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    filters: dict[str, str] = {}

    # Map common OLX URL filters to API params
    for key, values in qs.items():
        val = values[0]
        if key == "search[order]":
            filters["sort_by"] = val
        elif key == "search[filter_float_price:from]":
            filters["filter_float_price:from"] = val
        elif key == "search[filter_float_price:to]":
            filters["filter_float_price:to"] = val
        elif key.startswith("search["):
            # Pass through other search filters
            api_key = key.replace("search[", "").rstrip("]")
            filters[api_key] = val

    return filters


def _build_api_url(params: dict[str, str], url_filters: dict[str, str]) -> str:
    """Build the API URL from resolved IDs and URL filters."""
    query: dict[str, str] = {
        "offset": "0",
        "limit": "40",
        "sort_by": "created_at:desc",
    }
    query.update(params)
    query.update(url_filters)
    # Ensure sort order
    if "sort_by" not in url_filters:
        query["sort_by"] = "created_at:desc"
    return API_BASE + "?" + urlencode(query)


def _parse_api_response(data: dict) -> list[Offer]:
    """Parse offers from the API JSON response."""
    offers: list[Offer] = []
    for item in data.get("data", []):
        price = None
        currency = ""
        for p in item.get("params", []):
            if p.get("key") == "price":
                val = p.get("value", {})
                price = val.get("value")
                currency = val.get("currency", "")
                break

        # Build location string
        loc = item.get("location", {})
        city = loc.get("city", {}).get("name", "")
        district = loc.get("district", {}).get("name", "")
        region = loc.get("region", {}).get("name", "")
        location_parts = [p for p in [city, district, region] if p]
        location_str = ", ".join(location_parts)

        # Photo URL
        photos = item.get("photos", [])
        image_url = None
        if photos:
            raw_link = photos[0].get("link", "")
            image_url = raw_link.replace("{width}x{height}", "800x600")

        # Promotion status
        promo = item.get("promotion", {})
        is_promoted = bool(
            promo.get("highlighted")
            or promo.get("top_ad")
            or promo.get("urgent")
        )

        offers.append(Offer(
            id=str(item["id"]),
            title=item.get("title", ""),
            price=price,
            currency=currency,
            location=location_str,
            created_at=item.get("created_time", ""),
            url=item.get("url", ""),
            image_url=image_url,
            is_promoted=is_promoted,
        ))
    return offers


def _parse_embedded_state(html: str) -> list[Offer] | None:
    """Fallback: parse offers from __PRERENDERED_STATE__ in the HTML."""
    # Try both escaped and unescaped variants
    idx = html.find('"ads":[{')
    if idx < 0:
        idx = html.find('\\"ads\\":[{')
    if idx < 0:
        idx = html.find('\\"ads\\":[{\\"')
    if idx < 0:
        return None

    offers: list[Offer] = []
    pos = idx + len('"ads":[')
    depth = 0
    obj_start = None

    while pos < len(html) and len(offers) < 50:
        ch = html[pos]
        if ch == "\\" and pos + 1 < len(html):
            pos += 2
            continue
        if ch == "{":
            if depth == 0:
                obj_start = pos
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                raw = html[obj_start : pos + 1]
                raw = raw.replace('\\"', '"')
                raw = raw.replace("\\\\u002F", "/")
                try:
                    ad = json.loads(raw)
                    offer = _parse_embedded_ad(ad)
                    if offer:
                        offers.append(offer)
                except (json.JSONDecodeError, KeyError):
                    pass
                obj_start = None
        elif ch == "]" and depth == 0:
            break
        pos += 1

    return offers if offers else None


def _parse_embedded_ad(ad: dict) -> Offer | None:
    """Parse a single ad from the embedded state."""
    ad_id = ad.get("id")
    if not ad_id:
        return None

    price = None
    currency = ""
    price_data = ad.get("price", {})
    if price_data:
        price_str = price_data.get("regularPrice", {}).get("value")
        if price_str:
            try:
                price = float(str(price_str).replace(",", ".").replace(" ", ""))
            except ValueError:
                pass
        currency = price_data.get("regularPrice", {}).get("currencyCode", "")

    if price is None:
        for p in ad.get("params", []):
            if p.get("key") == "price":
                val = p.get("value", {})
                price = val.get("value")
                currency = val.get("currency", "")
                break

    location = ad.get("location", {}).get("cityName", "")
    if not location:
        loc = ad.get("location", {})
        city = loc.get("city", {}).get("name", "")
        region = loc.get("region", {}).get("name", "")
        location = f"{city}, {region}" if city else region

    photos = ad.get("photos", [])
    image_url = None
    if photos:
        if isinstance(photos[0], str):
            image_url = photos[0]
        elif isinstance(photos[0], dict):
            image_url = photos[0].get("link", "").replace("{width}x{height}", "800x600")

    url = ad.get("url", "")
    if url and not url.startswith("http"):
        url = "https://www.olx.ro" + url

    return Offer(
        id=str(ad_id),
        title=ad.get("title", ""),
        price=price,
        currency=currency,
        location=location,
        created_at=ad.get("createdTime", ad.get("created_time", "")),
        url=url,
        image_url=image_url,
        is_promoted=ad.get("isPromoted", ad.get("promotion", {}).get("highlighted", False)),
    )


def fetch_offers(search_url: str) -> list[Offer]:
    """
    Fetch offers for a search URL.

    Strategy:
    1. Fetch the search page HTML to resolve API parameters (category_id, etc.)
    2. Call the internal JSON API with those parameters
    3. If the API fails, fall back to parsing the embedded state from HTML
    """
    # Step 1: Fetch search page to get API params
    logger.info("Fetching search page: %s", search_url)
    page_resp = _get(search_url)
    html = page_resp.text

    api_params = _extract_api_params(html)
    url_filters = _parse_search_url_filters(search_url)

    if api_params:
        # Step 2: Call the API
        api_url = _build_api_url(api_params, url_filters)
        logger.info("Calling API: %s", api_url)

        # Random delay between page fetch and API call
        time.sleep(random.uniform(1.0, 2.0))

        try:
            api_resp = _get(
                api_url,
                headers={
                    "Accept": "application/json",
                    "Referer": search_url,
                },
            )
            data = api_resp.json()
            offers = _parse_api_response(data)
            if offers:
                logger.info("API returned %d offers", len(offers))
                return offers
            logger.warning("API returned 0 offers, trying fallback")
        except Exception as exc:
            logger.warning("API call failed: %s, trying fallback", exc)

    # Step 3: Fallback – parse embedded state
    logger.info("Falling back to embedded state parsing")
    offers = _parse_embedded_state(html)
    if offers:
        logger.info("Embedded state returned %d offers", len(offers))
        return offers

    raise RuntimeError(
        f"Could not extract offers from {search_url} "
        "(API params not found and embedded state parsing failed)"
    )
