from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILE = "seen.json"
RETENTION_DAYS = 30


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: str = STATE_FILE) -> dict:
    """Load state from JSON file. Returns empty dict if file doesn't exist."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load state file %s: %s", path, exc)
        return {}


def save(state: dict, path: str = STATE_FILE) -> None:
    """Save state to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def is_first_run(state: dict, search_name: str) -> bool:
    """Check if this is the first run for a given search."""
    return search_name not in state


def get_new_offer_ids(
    state: dict, search_name: str, offer_ids: list[str]
) -> list[str]:
    """Return offer IDs that haven't been seen before."""
    seen = state.get(search_name, {})
    return [oid for oid in offer_ids if oid not in seen]


def mark_seen(
    state: dict, search_name: str, offer_ids: list[str]
) -> None:
    """Mark offer IDs as seen."""
    if search_name not in state:
        state[search_name] = {}
    now = _now_iso()
    for oid in offer_ids:
        if oid not in state[search_name]:
            state[search_name][oid] = now


def cleanup_old_entries(state: dict) -> int:
    """Remove entries older than RETENTION_DAYS. Returns count removed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    removed = 0

    for search_name in list(state.keys()):
        if search_name.startswith("_"):
            continue  # skip metadata keys like _errors
        entries = state[search_name]
        if not isinstance(entries, dict):
            continue
        for oid in list(entries.keys()):
            try:
                seen_at = datetime.fromisoformat(entries[oid])
                if seen_at < cutoff:
                    del entries[oid]
                    removed += 1
            except (ValueError, TypeError):
                pass

    return removed


def get_error_count(state: dict, search_name: str) -> int:
    """Get consecutive error count for a search."""
    errors = state.get("_errors", {})
    return errors.get(search_name, {}).get("count", 0)


def record_error(state: dict, search_name: str) -> int:
    """Increment error count. Returns new count."""
    if "_errors" not in state:
        state["_errors"] = {}
    if search_name not in state["_errors"]:
        state["_errors"][search_name] = {"count": 0, "alerted": False}
    state["_errors"][search_name]["count"] += 1
    return state["_errors"][search_name]["count"]


def clear_errors(state: dict, search_name: str) -> None:
    """Reset error count after a successful run."""
    errors = state.get("_errors", {})
    if search_name in errors:
        errors[search_name] = {"count": 0, "alerted": False}


def should_alert_error(state: dict, search_name: str) -> bool:
    """Check if we should send an error alert (3+ consecutive, not yet alerted)."""
    errors = state.get("_errors", {})
    entry = errors.get(search_name, {})
    return entry.get("count", 0) >= 3 and not entry.get("alerted", False)


def mark_error_alerted(state: dict, search_name: str) -> None:
    """Mark that we've sent the error alert."""
    if "_errors" in state and search_name in state["_errors"]:
        state["_errors"][search_name]["alerted"] = True
