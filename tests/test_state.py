"""Tests for state management: seeding, new offer detection, cleanup, error tracking."""

import json
from datetime import datetime, timedelta, timezone

from watcher import state as st


class TestFirstRun:
    def test_empty_state_is_first_run(self):
        assert st.is_first_run({}, "test-search")

    def test_existing_search_is_not_first_run(self):
        state = {"test-search": {"123": "2026-01-01T00:00:00+00:00"}}
        assert not st.is_first_run(state, "test-search")

    def test_different_search_is_first_run(self):
        state = {"other-search": {"123": "2026-01-01T00:00:00+00:00"}}
        assert st.is_first_run(state, "test-search")


class TestMarkSeen:
    def test_creates_search_entry(self):
        state = {}
        st.mark_seen(state, "s1", ["100", "200"])
        assert "s1" in state
        assert "100" in state["s1"]
        assert "200" in state["s1"]

    def test_does_not_overwrite_existing(self):
        state = {"s1": {"100": "2026-01-01T00:00:00+00:00"}}
        st.mark_seen(state, "s1", ["100", "200"])
        # Original timestamp preserved
        assert state["s1"]["100"] == "2026-01-01T00:00:00+00:00"
        assert "200" in state["s1"]


class TestNewOfferIds:
    def test_all_new(self):
        state = {"s1": {"100": "..."}}
        new = st.get_new_offer_ids(state, "s1", ["200", "300"])
        assert new == ["200", "300"]

    def test_some_seen(self):
        state = {"s1": {"100": "...", "200": "..."}}
        new = st.get_new_offer_ids(state, "s1", ["100", "200", "300"])
        assert new == ["300"]

    def test_none_new(self):
        state = {"s1": {"100": "...", "200": "..."}}
        new = st.get_new_offer_ids(state, "s1", ["100", "200"])
        assert new == []

    def test_first_run_all_new(self):
        new = st.get_new_offer_ids({}, "s1", ["100", "200"])
        assert new == ["100", "200"]


class TestCleanup:
    def test_removes_old_entries(self):
        old_date = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        new_date = datetime.now(timezone.utc).isoformat()
        state = {
            "s1": {
                "old1": old_date,
                "old2": old_date,
                "new1": new_date,
            }
        }
        removed = st.cleanup_old_entries(state)
        assert removed == 2
        assert "old1" not in state["s1"]
        assert "new1" in state["s1"]

    def test_keeps_recent_entries(self):
        new_date = datetime.now(timezone.utc).isoformat()
        state = {"s1": {"a": new_date, "b": new_date}}
        removed = st.cleanup_old_entries(state)
        assert removed == 0
        assert len(state["s1"]) == 2

    def test_skips_errors_metadata(self):
        state = {
            "_errors": {"s1": {"count": 3, "alerted": False}},
            "s1": {},
        }
        # Should not crash on _errors key
        st.cleanup_old_entries(state)
        assert "_errors" in state


class TestErrorTracking:
    def test_initial_error_count_is_zero(self):
        assert st.get_error_count({}, "s1") == 0

    def test_record_error_increments(self):
        state = {}
        assert st.record_error(state, "s1") == 1
        assert st.record_error(state, "s1") == 2
        assert st.record_error(state, "s1") == 3

    def test_clear_errors_resets(self):
        state = {"_errors": {"s1": {"count": 5, "alerted": True}}}
        st.clear_errors(state, "s1")
        assert st.get_error_count(state, "s1") == 0

    def test_should_alert_at_three(self):
        state = {}
        st.record_error(state, "s1")
        st.record_error(state, "s1")
        assert not st.should_alert_error(state, "s1")
        st.record_error(state, "s1")
        assert st.should_alert_error(state, "s1")

    def test_alert_only_once(self):
        state = {}
        for _ in range(3):
            st.record_error(state, "s1")
        assert st.should_alert_error(state, "s1")
        st.mark_error_alerted(state, "s1")
        assert not st.should_alert_error(state, "s1")

    def test_alert_resets_after_success(self):
        state = {}
        for _ in range(3):
            st.record_error(state, "s1")
        st.mark_error_alerted(state, "s1")
        st.clear_errors(state, "s1")
        # After success + 3 new failures, should alert again
        for _ in range(3):
            st.record_error(state, "s1")
        assert st.should_alert_error(state, "s1")


class TestSaveLoad:
    def test_roundtrip(self, tmp_path):
        path = str(tmp_path / "test_seen.json")
        state = {"s1": {"100": "2026-01-01T00:00:00+00:00"}}
        st.save(state, path)
        loaded = st.load(path)
        assert loaded == state

    def test_load_missing_file(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        assert st.load(path) == {}

    def test_load_corrupt_file(self, tmp_path):
        path = str(tmp_path / "bad.json")
        with open(path, "w") as f:
            f.write("not json{{{")
        assert st.load(path) == {}
