from datetime import UTC

from fintracker.normalizer.hash import eb_dedup_hash, manual_dedup_hash, tasker_dedup_hash


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
        from datetime import datetime

        ts = datetime(2024, 1, 15, 14, 32, 0, tzinfo=UTC)
        assert tasker_dedup_hash(ts, 12.50, "EUR") == tasker_dedup_hash(ts, 12.50, "EUR")

    def test_sha256_length(self):
        from datetime import datetime

        ts = datetime(2024, 1, 15, 14, 32, 0, tzinfo=UTC)
        assert len(tasker_dedup_hash(ts, 12.50, "EUR")) == 64

    def test_differs_from_eb_hash(self):
        from datetime import datetime

        ts = datetime(2024, 1, 15, 0, 0, 0, tzinfo=UTC)
        eb = eb_dedup_hash("2024-01-15", 12.50, "shop", "EUR")
        tk = tasker_dedup_hash(ts, 12.50, "EUR")
        assert eb != tk

    def test_truncates_to_minute(self):
        from datetime import datetime

        ts1 = datetime(2024, 1, 15, 14, 32, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 15, 14, 32, 45, tzinfo=UTC)
        assert tasker_dedup_hash(ts1, 12.50, "EUR") == tasker_dedup_hash(ts2, 12.50, "EUR")


class TestManualDedupHash:
    def test_deterministic(self):
        h1 = manual_dedup_hash("2026-06-08T12:00:00", 12.5, "EUR")
        h2 = manual_dedup_hash("2026-06-08T12:00:00", 12.5, "EUR")
        assert h1 == h2

    def test_amount_sign_invariant(self):
        # positive and negative amounts with same magnitude -> same hash
        h_pos = manual_dedup_hash("2026-06-08T12:00:00", 12.5, "EUR")
        h_neg = manual_dedup_hash("2026-06-08T12:00:00", -12.5, "EUR")
        assert h_pos == h_neg

    def test_different_amounts_differ(self):
        h1 = manual_dedup_hash("2026-06-08T12:00:00", 12.5, "EUR")
        h2 = manual_dedup_hash("2026-06-08T12:00:00", 99.0, "EUR")
        assert h1 != h2

    def test_truncates_to_seconds(self):
        # datetime with sub-second precision truncated to [:19]
        h1 = manual_dedup_hash("2026-06-08T12:00:00.123456+00:00", 12.5, "EUR")
        h2 = manual_dedup_hash("2026-06-08T12:00:00", 12.5, "EUR")
        assert h1 == h2

    def test_differs_from_tasker_hash(self):
        from datetime import datetime

        dt = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
        manual_h = manual_dedup_hash("2026-06-08T12:00:00", 12.5, "EUR")
        tasker_h = tasker_dedup_hash(dt, 12.5, "EUR")
        assert manual_h != tasker_h
