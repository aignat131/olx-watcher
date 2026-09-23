from __future__ import annotations

import html
import logging
import time

from curl_cffi import requests as curl_requests

from watcher.sources.olx import Offer

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_NOTIFICATIONS = 10


def _call_telegram(
    token: str,
    method: str,
    data: dict,
    max_retries: int = 3,
) -> dict:
    """Call Telegram Bot API with rate limit handling."""
    url = TELEGRAM_API.format(token=token, method=method)

    for attempt in range(max_retries):
        resp = curl_requests.post(url, data=data, timeout=30)

        if resp.status_code == 429:
            body = resp.json()
            retry_after = body.get("parameters", {}).get("retry_after", 5)
            logger.warning("Telegram rate limit, waiting %ds", retry_after)
            time.sleep(retry_after)
            continue

        resp.raise_for_status()
        return resp.json()

    raise RuntimeError("Telegram rate limit exceeded after retries")


def _format_offer_caption(offer: Offer, search_name: str) -> str:
    """Format an offer as Telegram HTML caption."""
    title = html.escape(offer.title)
    location = html.escape(offer.location) if offer.location else "N/A"

    price_str = "Preț negociabil"
    if offer.price is not None:
        price_str = f"{offer.price:,.0f} {offer.currency}".replace(",", ".")

    # Parse date for display
    created = offer.created_at
    if "T" in created:
        created = created.split("T")[0] + " " + created.split("T")[1][:5]

    tag = html.escape(search_name)

    lines = [
        f"<b>{title}</b>",
        f"💰 {price_str}",
        f"📍 {location}",
        f"🕐 {created}",
        f'🔗 <a href="{offer.url}">Vezi anunțul</a>',
        f"#{tag.replace(' ', '_').replace('-', '_')}",
    ]
    return "\n".join(lines)


def send_offer(
    token: str,
    chat_id: str,
    offer: Offer,
    search_name: str,
) -> None:
    """Send a single offer notification to Telegram."""
    caption = _format_offer_caption(offer, search_name)

    if offer.image_url:
        _call_telegram(token, "sendPhoto", {
            "chat_id": chat_id,
            "photo": offer.image_url,
            "caption": caption,
            "parse_mode": "HTML",
        })
    else:
        _call_telegram(token, "sendMessage", {
            "chat_id": chat_id,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": "false",
        })


def send_seed_message(
    token: str,
    chat_id: str,
    search_name: str,
    count: int,
) -> None:
    """Send the initial seed message when a search is first set up."""
    text = f"✅ Monitorizez: <b>{html.escape(search_name)}</b> ({count} anunțuri existente)"
    _call_telegram(token, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    })


def send_overflow_message(
    token: str,
    chat_id: str,
    search_name: str,
    extra_count: int,
) -> None:
    """Notify that there are more new offers than we sent."""
    text = f"➕ <b>{html.escape(search_name)}</b>: + încă {extra_count} anunțuri noi"
    _call_telegram(token, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    })


def send_error_alert(
    token: str,
    chat_id: str,
    search_name: str,
    error_msg: str,
) -> None:
    """Send error alert after 3 consecutive failures."""
    text = (
        f"⚠️ <b>{html.escape(search_name)}</b> a eșuat de 3 ori consecutiv.\n"
        f"Eroare: <code>{html.escape(error_msg[:200])}</code>"
    )
    _call_telegram(token, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    })


def notify_new_offers(
    token: str,
    chat_id: str,
    offers: list[Offer],
    search_name: str,
    dry_run: bool = False,
) -> None:
    """Send notifications for new offers, respecting the 10-message limit."""
    to_send = offers[:MAX_NOTIFICATIONS]
    overflow = len(offers) - MAX_NOTIFICATIONS

    for offer in to_send:
        if dry_run:
            logger.info(
                "[DRY RUN] %s | %s | %s %s | %s",
                offer.title,
                offer.location,
                offer.price,
                offer.currency,
                offer.url,
            )
        else:
            send_offer(token, chat_id, offer, search_name)
            time.sleep(0.5)  # small delay between messages

    if overflow > 0:
        if dry_run:
            logger.info("[DRY RUN] + încă %d anunțuri noi", overflow)
        else:
            send_overflow_message(token, chat_id, search_name, overflow)
