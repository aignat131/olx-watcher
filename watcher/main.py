from __future__ import annotations

import argparse
import logging
import random
import sys
import time

from watcher.config import AppConfig
from watcher.filters import apply_filters
from watcher.notify import (
    notify_new_offers,
    send_error_alert,
    send_seed_message,
)
from watcher.sources.olx import fetch_offers
from watcher import state as st

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="OLX Watcher")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print to console instead of sending Telegram messages",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--state-file",
        default="seen.json",
        help="Path to state file (default: seen.json)",
    )
    args = parser.parse_args()

    config = AppConfig.load(config_path=args.config, dry_run=args.dry_run)
    seen = st.load(args.state_file)

    # Cleanup old entries
    removed = st.cleanup_old_entries(seen)
    if removed:
        logger.info("Cleaned up %d old entries", removed)

    had_errors = False

    for search in config.searches:
        logger.info("=== Processing: %s ===", search.name)
        try:
            offers = fetch_offers(search.url)
            logger.info("Fetched %d raw offers", len(offers))

            # Apply filters
            filtered = apply_filters(offers, search)
            logger.info("After filters: %d offers", len(filtered))

            # Check for new offers
            all_ids = [o.id for o in filtered]
            first_run = st.is_first_run(seen, search.name)

            if first_run:
                # Seed run: mark everything as seen, send info message
                st.mark_seen(seen, search.name, all_ids)
                logger.info("First run — seeded %d offers", len(all_ids))
                if config.dry_run:
                    logger.info(
                        "[DRY RUN] ✅ Monitorizez: %s (%d anunțuri existente)",
                        search.name,
                        len(all_ids),
                    )
                else:
                    send_seed_message(
                        config.telegram_bot_token,
                        config.telegram_chat_id,
                        search.name,
                        len(all_ids),
                    )
            else:
                new_ids = st.get_new_offer_ids(seen, search.name, all_ids)
                if new_ids:
                    new_offers = [o for o in filtered if o.id in set(new_ids)]
                    logger.info("Found %d new offers", len(new_offers))
                    notify_new_offers(
                        config.telegram_bot_token,
                        config.telegram_chat_id,
                        new_offers,
                        search.name,
                        dry_run=config.dry_run,
                    )
                    st.mark_seen(seen, search.name, new_ids)
                else:
                    logger.info("No new offers")

            # Clear error counter on success
            st.clear_errors(seen, search.name)

        except Exception as exc:
            logger.error("Search '%s' failed: %s", search.name, exc)
            had_errors = True
            count = st.record_error(seen, search.name)
            logger.warning("Consecutive error count: %d", count)

            if st.should_alert_error(seen, search.name):
                if config.dry_run:
                    logger.warning(
                        "[DRY RUN] ⚠️ %s a eșuat de 3 ori: %s",
                        search.name,
                        exc,
                    )
                else:
                    try:
                        send_error_alert(
                            config.telegram_bot_token,
                            config.telegram_chat_id,
                            search.name,
                            str(exc),
                        )
                    except Exception as alert_exc:
                        logger.error("Failed to send error alert: %s", alert_exc)
                st.mark_error_alerted(seen, search.name)

        # Random delay between searches
        if search != config.searches[-1]:
            delay = random.uniform(2.0, 5.0)
            logger.info("Waiting %.1fs before next search", delay)
            time.sleep(delay)

    # Save state
    st.save(seen, args.state_file)
    logger.info("State saved to %s", args.state_file)

    # Always exit 0 so the GitHub Actions workflow doesn't get disabled
    sys.exit(0)
