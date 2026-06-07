import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.normalizer.hash import eb_dedup_hash, tasker_dedup_hash


class TestEbDedupHash:
    def test_deterministic(self):
        h1 = eb_dedup_hash("2024-01-15", -25.50, "Coffee Shop", "EUR")
        h2 = eb_dedup_hash("2024-01-15", -25.50, "Coffee Shop", "EUR")
        assert h1 == h2

    def test_uses_absolute_amount(self):
        assert eb_dedup_hash("2024-01-15", -25.50, "shop", "EUR") == eb_dedup_hash(
            "2024-01-15", 25.50, "shop", "EUR"
        )

    def test_case_insensitive_description(self):
        assert eb_dedup_hash("2024-01-15", 10.0, "Coffee Shop", "EUR") == eb_dedup_hash(
            "2024-01-15", 10.0, "COFFEE SHOP", "EUR"
        )

    def test_only_date_prefix_used(self):
        assert eb_dedup_hash("2024-01-15T12:30:00Z", 10.0, "shop", "EUR") == eb_dedup_hash(
            "2024-01-15", 10.0, "shop", "EUR"
        )

    def test_sha256_length(self):
        assert len(eb_dedup_hash("2024-01-15", 10.0, "shop", "EUR")) == 64

    def test_different_amounts_differ(self):
        assert eb_dedup_hash("2024-01-15", 10.00, "shop", "EUR") != eb_dedup_hash(
            "2024-01-15", 10.01, "shop", "EUR"
        )

    def test_different_currencies_differ(self):
        assert eb_dedup_hash("2024-01-15", 10.0, "shop", "EUR") != eb_dedup_hash(
            "2024-01-15", 10.0, "shop", "USD"
        )


class TestTaskerDedupHash:
    def test_deterministic(self):
        from datetime import datetime, timezone

        ts = datetime(2024, 1, 15, 14, 32, 0, tzinfo=timezone.utc)
        assert tasker_dedup_hash(ts, 12.50, "EUR") == tasker_dedup_hash(ts, 12.50, "EUR")

    def test_sha256_length(self):
        from datetime import datetime, timezone

        ts = datetime(2024, 1, 15, 14, 32, 0, tzinfo=timezone.utc)
        assert len(tasker_dedup_hash(ts, 12.50, "EUR")) == 64

    def test_differs_from_eb_hash(self):
        from datetime import datetime, timezone

        ts = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        eb = eb_dedup_hash("2024-01-15", 12.50, "shop", "EUR")
        tk = tasker_dedup_hash(ts, 12.50, "EUR")
        assert eb != tk

    def test_truncates_to_minute(self):
        from datetime import datetime, timezone

        ts1 = datetime(2024, 1, 15, 14, 32, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 15, 14, 32, 45, tzinfo=timezone.utc)
        assert tasker_dedup_hash(ts1, 12.50, "EUR") == tasker_dedup_hash(ts2, 12.50, "EUR")
